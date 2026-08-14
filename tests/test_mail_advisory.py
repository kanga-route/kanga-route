"""Cache-only and fail-open mail advisory contract tests."""

from unittest.mock import MagicMock

import pytest

from kanga_route.application.mail_advisory import (
    AdviceAction,
    AdviceSource,
    MailAdvisoryService,
)
from kanga_route.models import (
    VerificationReason,
    VerificationResult,
    VerificationStatus,
)


def _result(email, status):
    return VerificationResult(
        email=email,
        status=status,
        reason=(
            VerificationReason.OK
            if status == VerificationStatus.VALID
            else VerificationReason.USER_NOT_FOUND
            if status == VerificationStatus.INVALID
            else VerificationReason.TIMEOUT
        ),
    )


def test_advice_uses_only_cache_and_preserves_safe_status_mapping():
    cache = MagicMock()
    cache.get.side_effect = [
        _result("valid@example.com", VerificationStatus.VALID),
        _result("invalid@example.com", VerificationStatus.INVALID),
        _result("unknown@example.com", VerificationStatus.UNKNOWN),
        None,
    ]
    service = MailAdvisoryService(cache)

    outcome = service.advise(
        [
            "Valid@Example.com",
            "invalid@example.com",
            "unknown@example.com",
            "missing@example.com",
        ]
    )

    assert outcome.fail_open is True
    assert [item.action for item in outcome.recipients] == [
        AdviceAction.ALLOW,
        AdviceAction.WARN,
        AdviceAction.ALLOW,
        AdviceAction.ALLOW,
    ]
    assert [item.source for item in outcome.recipients] == [
        AdviceSource.CACHE,
        AdviceSource.CACHE,
        AdviceSource.CACHE,
        AdviceSource.MISS,
    ]
    assert cache.get.call_count == 4


def test_advice_fails_open_on_cache_error_and_deduplicates():
    cache = MagicMock()
    cache.get.side_effect = RuntimeError("cache down")
    outcome = MailAdvisoryService(cache).advise(
        ["Person@Example.com", "person@example.com"]
    )

    assert len(outcome.recipients) == 1
    assert outcome.recipients[0].action == AdviceAction.ALLOW
    assert outcome.recipients[0].source == AdviceSource.UNAVAILABLE
    assert cache.get.call_count == 1


def test_invalid_syntax_warns_locally_without_touching_cache():
    cache = MagicMock()
    outcome = MailAdvisoryService(cache).advise(["not-an-address"])

    assert outcome.recipients[0].action == AdviceAction.WARN
    assert outcome.recipients[0].source == AdviceSource.LOCAL
    cache.get.assert_not_called()


def test_advice_enforces_recipient_bound():
    with pytest.raises(ValueError, match="cannot exceed 2"):
        MailAdvisoryService(MagicMock(), max_recipients=2).advise(
            ["one@example.com", "two@example.com", "three@example.com"]
        )
