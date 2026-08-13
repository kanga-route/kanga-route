"""HubSpot CRM client implementing ICRMClient (ADR 0003).

Pages contacts that need verification and performs batch property writebacks.
"""

import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import requests

from kanga_route.contracts import ICRMClient
from kanga_route.models import HubSpotContact, VerificationResult

logger = logging.getLogger(__name__)


class HubSpotError(RuntimeError):
    """Raised when HubSpot cannot complete a required CRM operation."""


class HubSpotClient(ICRMClient):
    """Client for interacting with HubSpot Contacts API v3."""

    BASE_URL = "https://api.hubapi.com/crm/v3/objects/contacts"

    def __init__(
        self,
        access_token: Optional[str] = None,
        session: Optional[requests.Session] = None,
        max_retries: int = 3,
        retry_backoff_seconds: float = 1.0,
        reverify_after_days: Optional[int] = None,
        unknown_retry_after_hours: Optional[int] = None,
    ):
        configured_token = (
            access_token
            if access_token is not None
            else os.getenv("HUBSPOT_ACCESS_TOKEN", "")
        )
        self.access_token = configured_token.strip()
        self.session = session or requests.Session()
        self.max_retries = max(1, max_retries)
        self.retry_backoff_seconds = max(0.0, retry_backoff_seconds)
        self.reverify_after_days = (
            reverify_after_days
            if reverify_after_days is not None
            else int(os.getenv("REVERIFY_AFTER_DAYS", "30"))
        )
        self.unknown_retry_after_hours = (
            unknown_retry_after_hours
            if unknown_retry_after_hours is not None
            else int(os.getenv("UNKNOWN_RETRY_AFTER_HOURS", "48"))
        )
        if self.reverify_after_days < 0:
            raise ValueError("REVERIFY_AFTER_DAYS must not be negative")
        if self.unknown_retry_after_hours < 1:
            raise ValueError("UNKNOWN_RETRY_AFTER_HOURS must be at least 1")

    def _require_token(self) -> None:
        if not self.access_token:
            raise HubSpotError("HUBSPOT_ACCESS_TOKEN is required")

    def _get_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    def _post(self, url: str, *, payload: Dict[str, Any], timeout: float):
        """POST with bounded retries for rate limits and transient failures."""
        last_error: Optional[BaseException] = None

        for attempt in range(self.max_retries):
            try:
                response = self.session.post(
                    url,
                    json=payload,
                    headers=self._get_headers(),
                    timeout=timeout,
                )
            except requests.RequestException as exc:
                last_error = exc
            else:
                if response.status_code != 429 and response.status_code < 500:
                    return response
                last_error = HubSpotError(
                    "HubSpot temporarily unavailable: "
                    f"{response.status_code} {response.text}"
                )
                if attempt + 1 < self.max_retries:
                    retry_after = response.headers.get("Retry-After")
                    try:
                        delay = (
                            float(retry_after)
                            if retry_after
                            else self.retry_backoff_seconds * (2**attempt)
                        )
                    except ValueError:
                        delay = self.retry_backoff_seconds * (2**attempt)
                    time.sleep(min(max(delay, 0.0), 60.0))
                    continue

            if attempt + 1 < self.max_retries:
                delay = self.retry_backoff_seconds * (2**attempt)
                time.sleep(min(delay, 60.0))

        raise HubSpotError(
            f"HubSpot request failed after {self.max_retries} attempt(s)"
        ) from last_error

    def _verification_filters(self) -> List[Dict[str, Any]]:
        """Build OR groups for new, retryable, and stale contacts."""
        now = datetime.now(timezone.utc)
        unknown_cutoff = now - timedelta(hours=self.unknown_retry_after_hours)
        groups: List[Dict[str, Any]] = [
            {
                "filters": [
                    {"propertyName": "email", "operator": "HAS_PROPERTY"},
                    {
                        "propertyName": "email_verification_status",
                        "operator": "NOT_HAS_PROPERTY",
                    },
                ]
            },
            {
                "filters": [
                    {"propertyName": "email", "operator": "HAS_PROPERTY"},
                    {
                        "propertyName": "email_verification_status",
                        "operator": "EQ",
                        "value": "Unknown",
                    },
                    {
                        "propertyName": "last_verified",
                        "operator": "NOT_HAS_PROPERTY",
                    },
                ]
            },
            {
                "filters": [
                    {"propertyName": "email", "operator": "HAS_PROPERTY"},
                    {
                        "propertyName": "email_verification_status",
                        "operator": "EQ",
                        "value": "Unknown",
                    },
                    {
                        "propertyName": "last_verified",
                        "operator": "LT",
                        "value": str(int(unknown_cutoff.timestamp() * 1000)),
                    },
                ]
            },
        ]

        if self.reverify_after_days > 0:
            cutoff = now - timedelta(
                days=self.reverify_after_days
            )
            groups.append(
                {
                    "filters": [
                        {"propertyName": "email", "operator": "HAS_PROPERTY"},
                        {
                            "propertyName": "last_verified",
                            "operator": "HAS_PROPERTY",
                        },
                        {
                            "propertyName": "last_verified",
                            "operator": "LT",
                            "value": str(int(cutoff.timestamp() * 1000)),
                        },
                        {
                            "propertyName": "email_verification_status",
                            "operator": "NEQ",
                            "value": "Unknown",
                        },
                    ]
                }
            )

        return groups

    def fetch_unverified_contacts(self, limit: int = 100) -> List[HubSpotContact]:
        """Fetch new, retryable, and stale contacts, following search paging."""
        self._require_token()
        if limit <= 0:
            return []

        search_url = f"{self.BASE_URL}/search"
        base_payload: Dict[str, Any] = {
            "filterGroups": self._verification_filters(),
            "properties": [
                "email",
                "email_verification_status",
                "last_verified",
            ],
        }
        contacts: List[HubSpotContact] = []
        seen_contact_ids = set()
        after: Optional[str] = None

        while len(contacts) < limit:
            payload = dict(base_payload)
            payload["limit"] = min(200, limit - len(contacts))
            if after is not None:
                payload["after"] = after

            response = self._post(search_url, payload=payload, timeout=10.0)
            if response.status_code != 200:
                raise HubSpotError(
                    "Failed to fetch contacts from HubSpot: "
                    f"{response.status_code} {response.text}"
                )

            try:
                data = response.json()
            except ValueError as exc:
                raise HubSpotError("HubSpot search returned invalid JSON") from exc

            for item in data.get("results", []):
                contact_id = str(item.get("id", "")).strip()
                properties = item.get("properties") or {}
                email = str(properties.get("email") or "").strip()
                if contact_id and email and contact_id not in seen_contact_ids:
                    seen_contact_ids.add(contact_id)
                    contacts.append(
                        HubSpotContact(
                            id=contact_id,
                            email=email,
                            properties=properties,
                        )
                    )
                    if len(contacts) >= limit:
                        break

            next_after = data.get("paging", {}).get("next", {}).get("after")
            if not next_after or str(next_after) == after:
                break
            after = str(next_after)

        return contacts

    def batch_update_verification_results(
        self, results: List[VerificationResult]
    ) -> bool:
        """Batch update contact verification properties (max 100 per call)."""
        self._require_token()
        if not results:
            return True

        batch_url = f"{self.BASE_URL}/batch/update"
        chunk_size = 100

        for index in range(0, len(results), chunk_size):
            chunk = results[index : index + chunk_size]
            inputs = []
            for result in chunk:
                if not result.contact_id:
                    raise HubSpotError(
                        f"Cannot update {result.email}: HubSpot contact_id is missing"
                    )
                inputs.append(
                    {
                        "id": result.contact_id,
                        "properties": result.to_hubspot_properties(),
                    }
                )

            response = self._post(
                batch_url,
                payload={"inputs": inputs},
                timeout=15.0,
            )
            if response.status_code != 200:
                raise HubSpotError(
                    "HubSpot batch writeback failed: "
                    f"{response.status_code} {response.text}"
                )

            try:
                response_data = response.json()
            except ValueError as exc:
                raise HubSpotError(
                    "HubSpot batch writeback returned invalid JSON"
                ) from exc
            if not isinstance(response_data, dict):
                raise HubSpotError(
                    "HubSpot batch writeback returned an invalid response"
                )
            batch_status = str(response_data.get("status", "")).upper()
            if batch_status != "COMPLETE":
                raise HubSpotError(
                    "HubSpot batch writeback did not complete: "
                    f"{batch_status or 'missing status'}"
                )

        return True
