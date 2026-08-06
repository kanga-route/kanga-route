"""Unit tests for HubSpot CRM Client."""

from unittest.mock import MagicMock
import pytest

from kanga_route.crm.hubspot import HubSpotClient
from kanga_route.models import (
    VerificationResult,
    VerificationStatus,
    VerificationReason,
)


def test_hubspot_fetch_unverified_contacts_no_token():
    client = HubSpotClient(access_token="")
    contacts = client.fetch_unverified_contacts()
    assert contacts == []


def test_hubspot_fetch_unverified_contacts_success():
    mock_session = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "results": [
            {
                "id": "101",
                "properties": {"email": "lead1@acme.com"},
            },
            {
                "id": "102",
                "properties": {"email": "lead2@acme.com"},
            },
        ]
    }
    mock_session.post.return_value = mock_response

    client = HubSpotClient(access_token="test-token", session=mock_session)
    contacts = client.fetch_unverified_contacts(limit=10)
    assert len(contacts) == 2
    assert contacts[0].id == "101"
    assert contacts[0].email == "lead1@acme.com"


def test_hubspot_batch_update_verification_results():
    mock_session = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_session.post.return_value = mock_response

    client = HubSpotClient(access_token="test-token", session=mock_session)
    res = VerificationResult(
        email="lead1@acme.com",
        contact_id="101",
        status=VerificationStatus.VALID,
        reason=VerificationReason.OK,
    )

    ok = client.batch_update_verification_results([res])
    assert ok is True
    mock_session.post.assert_called_once()
