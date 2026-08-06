"""HubSpot CRM Client implementing ICRMClient (ADR 0003).

Pages unverified contacts and performs batch property writebacks.
"""

import os
import logging
from typing import List, Optional, Dict, Any
import requests

from kanga_route.contracts import ICRMClient
from kanga_route.models import HubSpotContact, VerificationResult

logger = logging.getLogger(__name__)


class HubSpotClient(ICRMClient):
    """Client for interacting with HubSpot Contacts API v3."""

    BASE_URL = "https://api.hubapi.com/crm/v3/objects/contacts"

    def __init__(self, access_token: Optional[str] = None, session: Optional[requests.Session] = None):
        self.access_token = access_token or os.getenv("HUBSPOT_ACCESS_TOKEN", "")
        self.session = session or requests.Session()

    def _get_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    def fetch_unverified_contacts(self, limit: int = 100) -> List[HubSpotContact]:
        """Search contacts that have not been verified yet."""
        if not self.access_token:
            logger.warning("HUBSPOT_ACCESS_TOKEN not set; returning empty contacts list.")
            return []

        search_url = f"{self.BASE_URL}/search"
        payload: Dict[str, Any] = {
            "filterGroups": [
                {
                    "filters": [
                        {
                            "propertyName": "email",
                            "operator": "HAS_PROPERTY",
                        },
                        {
                            "propertyName": "email_verification_status",
                            "operator": "NOT_HAS_PROPERTY",
                        },
                    ]
                }
            ],
            "properties": ["email", "email_verification_status"],
            "limit": min(limit, 100),
        }

        try:
            resp = self.session.post(
                search_url, json=payload, headers=self._get_headers(), timeout=10.0
            )
            if resp.status_code != 200:
                logger.error(f"Failed to fetch contacts from HubSpot: {resp.status_code} {resp.text}")
                return []

            data = resp.json()
            results = data.get("results", [])
            contacts: List[HubSpotContact] = []
            for item in results:
                contact_id = item.get("id", "")
                props = item.get("properties", {})
                email = props.get("email", "").strip()
                if contact_id and email:
                    contacts.append(
                        HubSpotContact(id=contact_id, email=email, properties=props)
                    )
            return contacts

        except Exception as e:
            logger.exception(f"Error fetching unverified contacts: {e}")
            return []

    def batch_update_verification_results(
        self, results: List[VerificationResult]
    ) -> bool:
        """Batch update contact verification properties in HubSpot (max 100 per call)."""
        if not self.access_token:
            logger.warning("HUBSPOT_ACCESS_TOKEN not set; skipping writeback.")
            return False

        if not results:
            return True

        batch_url = f"{self.BASE_URL}/batch/update"

        # Group results into chunks of 100
        chunk_size = 100
        success = True

        # Map contact email to ID if needed; we pass updates based on ID or custom property mapping
        for i in range(0, len(results), chunk_size):
            chunk = results[i : i + chunk_size]
            inputs = []
            for res in chunk:
                # Expect res to carry contact_id or email lookup
                inputs.append(
                    {
                        "id": getattr(res, "contact_id", None) or res.email,
                        "properties": res.to_hubspot_properties(),
                    }
                )

            payload = {"inputs": inputs}
            try:
                resp = self.session.post(
                    batch_url, json=payload, headers=self._get_headers(), timeout=15.0
                )
                if resp.status_code not in (200, 207):
                    logger.error(
                        f"HubSpot batch writeback failed: {resp.status_code} {resp.text}"
                    )
                    success = False
            except Exception as e:
                logger.exception(f"Exception during HubSpot batch writeback: {e}")
                success = False

        return success
