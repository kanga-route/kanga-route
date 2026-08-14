"""Unit tests for the Kanga-Route pipeline orchestrator."""

from unittest.mock import MagicMock, patch

import pytest

from kanga_route.cache.dynamodb import CacheError, DynamoDBCacheStore
from kanga_route.contracts import AdapterCapabilities, AdapterError
from kanga_route.main import (
    PipelineError,
    _validate_runtime_configuration,
    main,
    run_pipeline,
)
from kanga_route.models import (
    VerificationOutcome,
    VerificationTarget,
    VerificationReason,
    VerificationResult,
    VerificationStatus,
)


def _set_valid_runtime(monkeypatch):
    monkeypatch.setenv("HUBSPOT_ACCESS_TOKEN", "test-token")
    monkeypatch.setenv("SMTP_HELO_DOMAIN", "verifier.example.com")
    monkeypatch.setenv("SMTP_MAIL_FROM", "verify@example.com")
    monkeypatch.setenv("USE_LOCAL_DB", "true")


def _contact(record_id="201", email="newlead@company.com"):
    return VerificationTarget(record_id=record_id, email=email)


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


def _adapter():
    adapter = MagicMock()
    adapter.name = "test"
    adapter.capabilities = AdapterCapabilities(True, True, 10_000)
    return adapter


def test_verification_outcome_associates_evidence_without_embedding_identity():
    result = _result("shared@company.com")
    hubspot_target = _contact("hubspot-101", "shared@company.com")
    csv_target = _contact("row-7", "shared@company.com")

    hubspot_outcome = VerificationOutcome(
        target=hubspot_target, result=result
    )
    csv_outcome = VerificationOutcome(target=csv_target, result=result)

    assert hubspot_outcome.result == csv_outcome.result
    assert hubspot_outcome.target.record_id == "hubspot-101"
    assert csv_outcome.target.record_id == "row-7"
    assert "record_id" not in result.to_dict()


def test_verification_outcome_rejects_mismatched_email_pairing():
    with pytest.raises(ValueError, match="email addresses must match"):
        VerificationOutcome(
            target=_contact("201", "first@company.com"),
            result=_result("second@company.com"),
        )


def test_run_pipeline_orchestration():
    crm = _adapter()
    cache = MagicMock()
    engine = MagicMock()
    crm.fetch_targets.return_value = [_contact()]
    cache.get.return_value = None
    cache.put.return_value = True
    engine.verify.return_value = _result()
    crm.write_outcomes.return_value = True

    processed = run_pipeline(crm, cache, engine, batch_size=10)

    assert processed == 1
    crm.fetch_targets.assert_called_once_with(limit=10)
    cache.get.assert_called_once_with("newlead@company.com")
    engine.verify.assert_called_once_with("newlead@company.com")
    cache.put.assert_called_once()
    written = crm.write_outcomes.call_args.args[0]
    assert written[0].target.record_id == "201"
    assert written[0].result.email == "newlead@company.com"


def test_run_pipeline_cache_hit_skips_engine():
    crm = _adapter()
    cache = MagicMock()
    engine = MagicMock()
    crm.fetch_targets.return_value = [
        _contact("202", "cachedlead@company.com")
    ]
    cached_result = _result("cachedlead@company.com")
    cached_snapshot = cached_result.to_dict()
    cache.get.return_value = cached_result
    crm.write_outcomes.return_value = True

    assert run_pipeline(crm, cache, engine, batch_size=10) == 1

    engine.verify.assert_not_called()
    cache.put.assert_not_called()
    outcomes = crm.write_outcomes.call_args.args[0]
    assert outcomes[0].target.record_id == "202"
    assert outcomes[0].result is cached_result
    assert cached_result.to_dict() == cached_snapshot


def test_run_pipeline_preserves_record_pairing_for_mixed_batch():
    crm = _adapter()
    cache = MagicMock()
    engine = MagicMock()
    crm.fetch_targets.return_value = [
        _contact("fresh-301", "fresh@company.com"),
        _contact("cached-302", "cached@company.com"),
    ]
    cache.get.side_effect = [None, _result("cached@company.com")]
    cache.put.return_value = True
    engine.verify.return_value = _result("fresh@company.com")
    crm.write_outcomes.return_value = True

    assert run_pipeline(crm, cache, engine, batch_size=10) == 2

    outcomes = crm.write_outcomes.call_args.args[0]
    pairing = {
        outcome.target.record_id: outcome.result.email
        for outcome in outcomes
    }
    assert pairing == {
        "fresh-301": "fresh@company.com",
        "cached-302": "cached@company.com",
    }


def test_run_pipeline_unknown_result_is_written_back_but_not_cached():
    crm = _adapter()
    cache = MagicMock()
    engine = MagicMock()
    crm.fetch_targets.return_value = [_contact()]
    cache.get.return_value = None
    engine.verify.return_value = _result(
        status=VerificationStatus.UNKNOWN
    )
    crm.write_outcomes.return_value = True

    assert run_pipeline(crm, cache, engine) == 1

    cache.put.assert_not_called()
    crm.write_outcomes.assert_called_once()


def test_run_pipeline_cache_write_failure_is_fatal():
    crm = _adapter()
    cache = MagicMock()
    engine = MagicMock()
    crm.fetch_targets.return_value = [_contact()]
    cache.get.return_value = None
    cache.put.return_value = False
    engine.verify.return_value = _result()

    with pytest.raises(PipelineError, match="Cache rejected"):
        run_pipeline(crm, cache, engine)


def test_run_pipeline_writeback_failure_is_fatal():
    crm = _adapter()
    cache = MagicMock()
    engine = MagicMock()
    crm.fetch_targets.return_value = [_contact()]
    cache.get.return_value = _result()
    crm.write_outcomes.return_value = False

    with pytest.raises(PipelineError, match="incomplete"):
        run_pipeline(crm, cache, engine)


def test_run_pipeline_validates_batch_size():
    with pytest.raises(ValueError, match="greater than zero"):
        run_pipeline(MagicMock(), MagicMock(), MagicMock(), batch_size=0)

    adapter = _adapter()
    adapter.capabilities = AdapterCapabilities(False, True, 10_000)
    with pytest.raises(PipelineError, match="does not support"):
        run_pipeline(adapter, MagicMock(), MagicMock())

    adapter.capabilities = AdapterCapabilities(True, True, 10_000)
    with pytest.raises(ValueError, match="adapter limit 10,000"):
        run_pipeline(adapter, MagicMock(), MagicMock(), batch_size=10_001)


def test_run_pipeline_retries_cache_readiness():
    cache = object.__new__(DynamoDBCacheStore)
    cache.ensure_table_exists = MagicMock(
        side_effect=[
            CacheError("not ready"),
            None,
        ]
    )
    crm = _adapter()
    crm.fetch_targets.return_value = []

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
            _adapter(),
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

    with pytest.raises((ValueError, AdapterError), match=message):
        _validate_runtime_configuration()


def test_runtime_configuration_accepts_configured_identity(monkeypatch):
    _set_valid_runtime(monkeypatch)
    _validate_runtime_configuration()
