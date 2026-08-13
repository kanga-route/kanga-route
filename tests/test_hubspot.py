"""Unit tests for the HubSpot CRM client."""

from unittest.mock import MagicMock

import pytest
import requests

from kanga_route.crm.hubspot import HubSpotClient, HubSpotError
from kanga_route.models import (
    VerificationReason,
    VerificationResult,
    VerificationStatus,
)


def _response(status_code=200, data=None, text="", headers=None):
    response = MagicMock()
    response.status_code = status_code
    response.text = text
    response.headers = headers or {}
    response.json.return_value = data if data is not None else {}
    return response


def test_hubspot_fetch_requires_token():
    client = HubSpotClient(access_token="")

    with pytest.raises(HubSpotError, match="HUBSPOT_ACCESS_TOKEN"):
        client.fetch_unverified_contacts()


def test_hubspot_fetch_builds_retry_and_stale_filters():
    session = MagicMock()
    session.post.return_value = _response(
        data={
            "results": [
                {
                    "id": "101",
                    "properties": {"email": " lead1@acme.com "},
                }
            ]
        }
    )
    client = HubSpotClient(
        access_token="test-token",
        session=session,
        reverify_after_days=30,
        unknown_retry_after_hours=48,
    )

    contacts = client.fetch_unverified_contacts(limit=10)

    assert [(contact.id, contact.email) for contact in contacts] == [
        ("101", "lead1@acme.com")
    ]
    payload = session.post.call_args.kwargs["json"]
    assert payload["limit"] == 10
    assert len(payload["filterGroups"]) == 4
    missing_timestamp_group = payload["filterGroups"][1]["filters"]
    assert missing_timestamp_group[1]["value"] == "Unknown"
    assert missing_timestamp_group[2] == {
        "propertyName": "last_verified",
        "operator": "NOT_HAS_PROPERTY",
    }
    retry_group = payload["filterGroups"][2]["filters"]
    assert retry_group[1]["value"] == "Unknown"
    assert retry_group[2]["propertyName"] == "last_verified"
    assert retry_group[2]["operator"] == "LT"
    assert retry_group[2]["value"].isdigit()
    stale_filters = payload["filterGroups"][3]["filters"]
    stale_filter = stale_filters[2]
    assert stale_filter["propertyName"] == "last_verified"
    assert stale_filter["operator"] == "LT"
    assert stale_filter["value"].isdigit()
    assert stale_filters[3] == {
        "propertyName": "email_verification_status",
        "operator": "NEQ",
        "value": "Unknown",
    }


def test_stale_cohort_never_bypasses_unknown_cooldown():
    client = HubSpotClient(
        access_token="test-token",
        reverify_after_days=1,
        unknown_retry_after_hours=48,
    )

    groups = client._verification_filters()
    unknown_cutoff = int(groups[2]["filters"][2]["value"])
    stale_cutoff = int(groups[3]["filters"][2]["value"])
    stale_filters = groups[3]["filters"]

    assert stale_cutoff > unknown_cutoff
    assert {
        "propertyName": "email_verification_status",
        "operator": "NEQ",
        "value": "Unknown",
    } in stale_filters


def test_hubspot_fetch_follows_paging_up_to_limit():
    session = MagicMock()
    session.post.side_effect = [
        _response(
            data={
                "results": [
                    {"id": "101", "properties": {"email": "one@acme.com"}},
                    {"id": "102", "properties": {"email": "two@acme.com"}},
                ],
                "paging": {"next": {"after": "cursor-2"}},
            }
        ),
        _response(
            data={
                "results": [
                    {"id": "103", "properties": {"email": "three@acme.com"}}
                ]
            }
        ),
    ]
    client = HubSpotClient(access_token="token", session=session)

    contacts = client.fetch_unverified_contacts(limit=3)

    assert [contact.id for contact in contacts] == ["101", "102", "103"]
    assert session.post.call_count == 2
    first_payload = session.post.call_args_list[0].kwargs["json"]
    second_payload = session.post.call_args_list[1].kwargs["json"]
    assert first_payload["limit"] == 3
    assert second_payload["limit"] == 1
    assert second_payload["after"] == "cursor-2"


def test_hubspot_retries_rate_limit():
    session = MagicMock()
    session.post.side_effect = [
        _response(
            status_code=429,
            text="rate limited",
            headers={"Retry-After": "0"},
        ),
        _response(data={"results": []}),
    ]
    client = HubSpotClient(
        access_token="token",
        session=session,
        max_retries=2,
        retry_backoff_seconds=0,
    )

    assert client.fetch_unverified_contacts() == []
    assert session.post.call_count == 2


def test_hubspot_retries_network_failure_then_succeeds():
    session = MagicMock()
    session.post.side_effect = [
        requests.ConnectionError("offline"),
        _response(data={"results": []}),
    ]
    client = HubSpotClient(
        access_token="token",
        session=session,
        max_retries=2,
        retry_backoff_seconds=0,
    )

    assert client.fetch_unverified_contacts() == []


def test_hubspot_non_retryable_fetch_error_is_explicit():
    session = MagicMock()
    session.post.return_value = _response(
        status_code=401,
        text="invalid token",
    )
    client = HubSpotClient(access_token="bad-token", session=session)

    with pytest.raises(HubSpotError, match="401"):
        client.fetch_unverified_contacts()


def test_hubspot_batch_update_verification_results():
    session = MagicMock()
    session.post.return_value = _response(data={"status": "COMPLETE"})
    client = HubSpotClient(access_token="test-token", session=session)
    result = VerificationResult(
        email="lead1@acme.com",
        contact_id="101",
        status=VerificationStatus.VALID,
        reason=VerificationReason.OK,
    )

    assert client.batch_update_verification_results([result]) is True

    payload = session.post.call_args.kwargs["json"]
    assert payload["inputs"][0]["id"] == "101"
    assert payload["inputs"][0]["properties"]["email_verification_status"] == "Valid"


def test_hubspot_batch_update_requires_contact_id():
    client = HubSpotClient(access_token="test-token", session=MagicMock())
    result = VerificationResult(
        email="lead1@acme.com",
        status=VerificationStatus.VALID,
        reason=VerificationReason.OK,
    )

    with pytest.raises(HubSpotError, match="contact_id"):
        client.batch_update_verification_results([result])


def test_hubspot_batch_update_rejects_partial_response():
    session = MagicMock()
    session.post.return_value = _response(
        status_code=207,
        text="partial failure",
    )
    client = HubSpotClient(access_token="test-token", session=session)
    result = VerificationResult(
        email="lead1@acme.com",
        contact_id="101",
        status=VerificationStatus.VALID,
        reason=VerificationReason.OK,
    )

    with pytest.raises(HubSpotError, match="207"):
        client.batch_update_verification_results([result])


@pytest.mark.parametrize("status", ["PENDING", "PROCESSING", "CANCELED"])
def test_hubspot_batch_update_requires_complete_status(status):
    session = MagicMock()
    session.post.return_value = _response(data={"status": status})
    client = HubSpotClient(access_token="test-token", session=session)
    result = VerificationResult(
        email="lead1@acme.com",
        contact_id="101",
        status=VerificationStatus.VALID,
        reason=VerificationReason.OK,
    )

    with pytest.raises(HubSpotError, match="did not complete"):
        client.batch_update_verification_results([result])


def test_hubspot_batch_update_rejects_missing_status():
    session = MagicMock()
    session.post.return_value = _response(data={})
    client = HubSpotClient(access_token="test-token", session=session)
    result = VerificationResult(
        email="lead1@acme.com",
        contact_id="101",
        status=VerificationStatus.VALID,
        reason=VerificationReason.OK,
    )

    with pytest.raises(HubSpotError, match="missing status"):
        client.batch_update_verification_results([result])


def test_hubspot_batch_update_rejects_invalid_json():
    session = MagicMock()
    response = _response()
    response.json.side_effect = ValueError("not JSON")
    session.post.return_value = response
    client = HubSpotClient(access_token="test-token", session=session)
    result = VerificationResult(
        email="lead1@acme.com",
        contact_id="101",
        status=VerificationStatus.VALID,
        reason=VerificationReason.OK,
    )

    with pytest.raises(HubSpotError, match="invalid JSON"):
        client.batch_update_verification_results([result])
