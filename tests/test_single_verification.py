"""Tests for the product-neutral single-verification service."""

from unittest.mock import MagicMock

import pytest

from kanga_route.application.single_verification import (
    CachePolicy,
    CacheStatus,
    SingleVerificationError,
    SingleVerificationService,
    normalize_email,
)
from kanga_route.models import (
    VerificationReason,
    VerificationResult,
    VerificationStatus,
)


def _result(
    email="person@example.com",
    status=VerificationStatus.VALID,
):
    return VerificationResult(
        email=email,
        status=status,
        reason=(
            VerificationReason.OK
            if status != VerificationStatus.UNKNOWN
            else VerificationReason.TIMEOUT
        ),
        verified_at="2026-08-13T20:00:00+00:00",
    )


def _service(cache=None, engine=None, validator=None):
    return SingleVerificationService(
        cache_store=cache or MagicMock(),
        engine=engine or MagicMock(),
        configuration_validator=validator,
    )


def test_normalize_email_matches_engine_input_rules():
    assert normalize_email("  Person@Example.COM ") == "person@example.com"

    for invalid in (None, "", "not-an-email", "person@example"):
        with pytest.raises(SingleVerificationError, match="invalid_email"):
            normalize_email(invalid)


def test_invalid_email_stops_before_cache_or_engine_work():
    cache = MagicMock()
    engine = MagicMock()
    service = _service(cache=cache, engine=engine)

    with pytest.raises(SingleVerificationError, match="invalid_email"):
        service.verify("not-an-email")

    cache.get.assert_not_called()
    cache.put.assert_not_called()
    engine.verify.assert_not_called()


def test_definitive_cache_hit_skips_configuration_and_engine():
    cache = MagicMock()
    engine = MagicMock()
    validator = MagicMock()
    cached = _result()
    cache.get.return_value = cached
    service = _service(cache=cache, engine=engine, validator=validator)

    outcome = service.verify(" Person@Example.com ")

    assert outcome.result is cached
    assert outcome.cache_status == CacheStatus.HIT
    cache.get.assert_called_once_with("person@example.com")
    validator.assert_not_called()
    engine.verify.assert_not_called()
    cache.put.assert_not_called()


def test_cache_miss_verifies_normalized_address_and_stores_definitive_result():
    cache = MagicMock()
    engine = MagicMock()
    validator = MagicMock()
    cache.get.return_value = None
    cache.put.return_value = True
    engine.verify.return_value = _result()
    service = _service(cache=cache, engine=engine, validator=validator)

    outcome = service.verify("Person@Example.com")

    assert outcome.cache_status == CacheStatus.MISS
    validator.assert_called_once_with()
    engine.verify.assert_called_once_with("person@example.com")
    cache.put.assert_called_once_with(outcome.result)


def test_refresh_bypasses_read_but_updates_cache():
    cache = MagicMock()
    engine = MagicMock()
    cache.put.return_value = True
    engine.verify.return_value = _result()
    service = _service(cache=cache, engine=engine)

    outcome = service.verify("person@example.com", CachePolicy.REFRESH)

    assert outcome.cache_status == CacheStatus.BYPASSED
    cache.get.assert_not_called()
    cache.put.assert_called_once_with(outcome.result)


def test_unknown_result_is_returned_without_cache_write():
    cache = MagicMock()
    engine = MagicMock()
    cache.get.return_value = None
    engine.verify.return_value = _result(status=VerificationStatus.UNKNOWN)
    service = _service(cache=cache, engine=engine)

    outcome = service.verify("person@example.com")

    assert outcome.result.status == VerificationStatus.UNKNOWN
    assert outcome.cache_status == CacheStatus.MISS
    cache.put.assert_not_called()


@pytest.mark.parametrize(
    ("boundary", "side_effect", "expected_code"),
    [
        ("cache", RuntimeError("CACHE_CANARY"), "cache_unavailable"),
        ("engine", RuntimeError("ENGINE_CANARY"), "verification_failed"),
        ("validator", ValueError("CONFIG_CANARY"), "configuration_invalid"),
    ],
)
def test_boundary_failures_use_stable_codes(boundary, side_effect, expected_code):
    cache = MagicMock()
    engine = MagicMock()
    validator = MagicMock()
    cache.get.return_value = None
    cache.put.return_value = True
    engine.verify.return_value = _result()

    if boundary == "cache":
        cache.get.side_effect = side_effect
    elif boundary == "engine":
        engine.verify.side_effect = side_effect
    else:
        validator.side_effect = side_effect

    service = _service(cache=cache, engine=engine, validator=validator)

    with pytest.raises(SingleVerificationError) as raised:
        service.verify("person@example.com")

    assert raised.value.code == expected_code
    assert str(raised.value) == expected_code
