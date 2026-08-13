"""Unit tests for the Kanga-Route pipeline orchestrator."""

from unittest.mock import MagicMock, patch

import pytest

from kanga_route.cache.dynamodb import CacheError, DynamoDBCacheStore
from kanga_route.main import (
    PipelineError,
    _validate_runtime_configuration,
    main,
    run_pipeline,
)
from kanga_route.models import (
    HubSpotContact,
    VerificationReason,
    VerificationResult,
    VerificationStatus,
)


def _set_valid_runtime(monkeypatch):
    monkeypatch.setenv("HUBSPOT_ACCESS_TOKEN", "test-token")
    monkeypatch.setenv("SMTP_HELO_DOMAIN", "verifier.example.com")
    monkeypatch.setenv("SMTP_MAIL_FROM", "verify@example.com")
    monkeypatch.setenv("USE_LOCAL_DB", "true")


def _contact(contact_id="201", email="newlead@company.com"):
    return HubSpotContact(id=contact_id, email=email)


def _result(email="newlead@company.com", status=VerificationStatus.VALID):
    reason = (
        VerificationReason.OK
        if status != VerificationStatus.UNKNOWN
        else VerificationReason.TIMEOUT
    )
    return VerificationResult(
        email=email,
        status=status,
        reason=reason,
    )


def test_run_pipeline_orchestration():
    crm = MagicMock()
    cache = MagicMock()
    engine = MagicMock()
    crm.fetch_unverified_contacts.return_value = [_contact()]
    cache.get.return_value = None
    cache.put.return_value = True
    engine.verify.return_value = _result()
    crm.batch_update_verification_results.return_value = True

    processed = run_pipeline(crm, cache, engine, batch_size=10)

    assert processed == 1
    crm.fetch_unverified_contacts.assert_called_once_with(limit=10)
    cache.get.assert_called_once_with("newlead@company.com")
    engine.verify.assert_called_once_with("newlead@company.com")
    cache.put.assert_called_once()
    written = crm.batch_update_verification_results.call_args.args[0]
    assert written[0].contact_id == "201"


def test_run_pipeline_cache_hit_skips_engine():
    crm = MagicMock()
    cache = MagicMock()
    engine = MagicMock()
    crm.fetch_unverified_contacts.return_value = [
        _contact("202", "cachedlead@company.com")
    ]
    cache.get.return_value = _result("cachedlead@company.com")
    crm.batch_update_verification_results.return_value = True

    assert run_pipeline(crm, cache, engine, batch_size=10) == 1

    engine.verify.assert_not_called()
    cache.put.assert_not_called()


def test_run_pipeline_unknown_result_is_written_back_but_not_cached():
    crm = MagicMock()
    cache = MagicMock()
    engine = MagicMock()
    crm.fetch_unverified_contacts.return_value = [_contact()]
    cache.get.return_value = None
    engine.verify.return_value = _result(
        status=VerificationStatus.UNKNOWN
    )
    crm.batch_update_verification_results.return_value = True

    assert run_pipeline(crm, cache, engine) == 1

    cache.put.assert_not_called()
    crm.batch_update_verification_results.assert_called_once()


def test_run_pipeline_cache_write_failure_is_fatal():
    crm = MagicMock()
    cache = MagicMock()
    engine = MagicMock()
    crm.fetch_unverified_contacts.return_value = [_contact()]
    cache.get.return_value = None
    cache.put.return_value = False
    engine.verify.return_value = _result()

    with pytest.raises(PipelineError, match="Cache rejected"):
        run_pipeline(crm, cache, engine)


def test_run_pipeline_writeback_failure_is_fatal():
    crm = MagicMock()
    cache = MagicMock()
    engine = MagicMock()
    crm.fetch_unverified_contacts.return_value = [_contact()]
    cache.get.return_value = _result()
    crm.batch_update_verification_results.return_value = False

    with pytest.raises(PipelineError, match="incomplete"):
        run_pipeline(crm, cache, engine)


def test_run_pipeline_validates_batch_size():
    with pytest.raises(ValueError, match="greater than zero"):
        run_pipeline(MagicMock(), MagicMock(), MagicMock(), batch_size=0)

    with pytest.raises(ValueError, match="10,000"):
        run_pipeline(MagicMock(), MagicMock(), MagicMock(), batch_size=10_001)


def test_run_pipeline_retries_cache_readiness():
    cache = object.__new__(DynamoDBCacheStore)
    cache.ensure_table_exists = MagicMock(
        side_effect=[
            CacheError("not ready"),
            None,
        ]
    )
    crm = MagicMock()
    crm.fetch_unverified_contacts.return_value = []

    assert run_pipeline(
        crm,
        cache,
        MagicMock(),
        cache_ready_attempts=2,
        cache_ready_delay_seconds=0,
    ) == 0
    assert cache.ensure_table_exists.call_count == 2


def test_run_pipeline_exhausted_cache_readiness_is_fatal():
    cache = object.__new__(DynamoDBCacheStore)
    cache.ensure_table_exists = MagicMock(
        side_effect=CacheError("not ready")
    )

    with pytest.raises(PipelineError, match="not ready"):
        run_pipeline(
            MagicMock(),
            cache,
            MagicMock(),
            cache_ready_attempts=2,
            cache_ready_delay_seconds=0,
        )


@patch("kanga_route.main.run_pipeline", side_effect=PipelineError("boom"))
def test_main_returns_nonzero_on_fatal_error(_run, monkeypatch):
    _set_valid_runtime(monkeypatch)
    assert main([]) == 1
    _run.assert_called_once()


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("HUBSPOT_ACCESS_TOKEN", " ", "HUBSPOT_ACCESS_TOKEN"),
        ("USE_LOCAL_DB", "tru", "USE_LOCAL_DB"),
        ("SMTP_HELO_DOMAIN", "verifier.example.invalid", "SMTP_HELO_DOMAIN"),
        ("SMTP_MAIL_FROM", "verify@example.invalid", "SMTP_MAIL_FROM"),
        ("SMTP_MAIL_FROM", "verify@", "SMTP_MAIL_FROM"),
    ],
)
def test_runtime_configuration_rejects_missing_or_placeholder_values(
    monkeypatch, name, value, message
):
    _set_valid_runtime(monkeypatch)
    monkeypatch.setenv(name, value)

    with pytest.raises(ValueError, match=message):
        _validate_runtime_configuration()


def test_runtime_configuration_accepts_configured_identity(monkeypatch):
    _set_valid_runtime(monkeypatch)
    _validate_runtime_configuration()
