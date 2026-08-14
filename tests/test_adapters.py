"""Contract and registry tests for product-neutral verification adapters."""

from unittest.mock import MagicMock

import pytest

from kanga_route.adapters.hubspot import HubSpotAdapter
from kanga_route.adapters.registry import create_adapter
from kanga_route.contracts import AdapterError, IVerificationAdapter
from kanga_route.crm.hubspot import HubSpotError
from kanga_route.models import (
    VerificationOutcome,
    VerificationReason,
    VerificationResult,
    VerificationStatus,
    VerificationTarget,
)


def _outcome():
    email = "person@example.com"
    return VerificationOutcome(
        target=VerificationTarget(record_id="contact-1", email=email),
        result=VerificationResult(
            email=email,
            status=VerificationStatus.VALID,
            reason=VerificationReason.OK,
        ),
    )


def test_hubspot_satisfies_stable_adapter_contract_without_sdk_types():
    client = MagicMock()
    client.access_token = "token"
    client.fetch_unverified_contacts.return_value = [_outcome().target]
    client.batch_update_verification_results.return_value = True
    adapter = HubSpotAdapter(client)

    assert isinstance(adapter, IVerificationAdapter)
    assert adapter.name == "hubspot"
    assert adapter.capabilities.can_read_targets is True
    assert adapter.capabilities.can_write_outcomes is True
    assert adapter.capabilities.max_batch_size == 10_000
    assert adapter.fetch_targets(limit=25) == [_outcome().target]
    assert adapter.write_outcomes([_outcome()]) is True
    client.fetch_unverified_contacts.assert_called_once_with(limit=25)
    client.batch_update_verification_results.assert_called_once()


def test_hubspot_adapter_owns_configuration_and_translates_errors():
    client = MagicMock()
    client.access_token = ""
    adapter = HubSpotAdapter(client)
    with pytest.raises(AdapterError, match="HUBSPOT_ACCESS_TOKEN"):
        adapter.validate_configuration()

    client.access_token = "token"
    client.fetch_unverified_contacts.side_effect = HubSpotError("secret detail")
    with pytest.raises(AdapterError, match="target read") as captured:
        adapter.fetch_targets()
    assert isinstance(captured.value.__cause__, HubSpotError)
    assert "secret detail" not in str(captured.value)


def test_registry_defaults_to_hubspot_and_rejects_unknown(monkeypatch):
    monkeypatch.delenv("KANGA_ROUTE_ADAPTER", raising=False)
    assert create_adapter().name == "hubspot"

    monkeypatch.setenv("KANGA_ROUTE_ADAPTER", "not-installed")
    with pytest.raises(ValueError, match="Unsupported KANGA_ROUTE_ADAPTER"):
        create_adapter()
