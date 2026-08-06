"""Unit tests for Kanga-Route main pipeline orchestrator."""

from unittest.mock import MagicMock
import pytest

from kanga_route.main import run_pipeline
from kanga_route.models import (
    HubSpotContact,
    VerificationResult,
    VerificationStatus,
    VerificationReason,
)


def test_run_pipeline_orchestration():
    mock_crm = MagicMock()
    mock_cache = MagicMock()
    mock_engine = MagicMock()

    # 1 contact returned from CRM
    mock_crm.fetch_unverified_contacts.return_value = [
        HubSpotContact(id="201", email="newlead@company.com")
    ]
    # Cache miss
    mock_cache.get.return_value = None

    # Engine result
    engine_res = VerificationResult(
        email="newlead@company.com",
        status=VerificationStatus.VALID,
        reason=VerificationReason.OK,
    )
    mock_engine.verify.return_value = engine_res
    mock_crm.batch_update_verification_results.return_value = True

    processed = run_pipeline(mock_crm, mock_cache, mock_engine, batch_size=10)

    assert processed == 1
    mock_crm.fetch_unverified_contacts.assert_called_once_with(limit=10)
    mock_cache.get.assert_called_once_with("newlead@company.com")
    mock_engine.verify.assert_called_once_with("newlead@company.com")
    mock_cache.put.assert_called_once()
    mock_crm.batch_update_verification_results.assert_called_once()


def test_run_pipeline_cache_hit():
    mock_crm = MagicMock()
    mock_cache = MagicMock()
    mock_engine = MagicMock()

    mock_crm.fetch_unverified_contacts.return_value = [
        HubSpotContact(id="202", email="cachedlead@company.com")
    ]

    cached_res = VerificationResult(
        email="cachedlead@company.com",
        status=VerificationStatus.VALID,
        reason=VerificationReason.OK,
    )
    mock_cache.get.return_value = cached_res
    mock_crm.batch_update_verification_results.return_value = True

    processed = run_pipeline(mock_crm, mock_cache, mock_engine, batch_size=10)

    assert processed == 1
    mock_cache.get.assert_called_once_with("cachedlead@company.com")
    # Engine verify should NOT be called on cache hit
    mock_engine.verify.assert_not_called()
