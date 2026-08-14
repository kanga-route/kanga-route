"""Postfix policy adapter tests for fail-open behavior."""

from unittest.mock import MagicMock

from kanga_route.application.mail_advisory import MailAdvisoryService
from kanga_route.mail.postfix_policy import parse_policy_request, policy_action
from kanga_route.models import (
    VerificationReason,
    VerificationResult,
    VerificationStatus,
)


def _service(result=None, error=None):
    cache = MagicMock()
    cache.get.return_value = result
    cache.get.side_effect = error
    return MailAdvisoryService(cache)


def _invalid_result():
    return VerificationResult(
        email="bad@example.com",
        status=VerificationStatus.INVALID,
        reason=VerificationReason.USER_NOT_FOUND,
    )


def test_policy_parser_preserves_postfix_attributes():
    assert parse_policy_request(
        ["request=smtpd_access_policy", "recipient=person@example.com"]
    ) == {
        "request": "smtpd_access_policy",
        "recipient": "person@example.com",
    }


def test_policy_observe_mode_never_blocks_cached_invalid():
    assert policy_action(
        _service(_invalid_result()),
        {"recipient": "bad@example.com"},
        "observe",
    ) == "DUNNO"


def test_policy_enforcement_rejects_only_cached_invalid():
    assert policy_action(
        _service(_invalid_result()),
        {"recipient": "bad@example.com"},
        "enforce-cached-invalid",
    ).startswith("REJECT")
    assert policy_action(
        _service(None),
        {"recipient": "unknown@example.com"},
        "enforce-cached-invalid",
    ) == "DUNNO"
    assert policy_action(
        _service(error=RuntimeError("down")),
        {"recipient": "unknown@example.com"},
        "enforce-cached-invalid",
    ) == "DUNNO"
    assert policy_action(
        _service(),
        {},
        "enforce-cached-invalid",
    ) == "DUNNO"
