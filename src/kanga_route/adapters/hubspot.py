"""HubSpot reference adapter for the stable verification-adapter port."""

from typing import Optional, Sequence

from kanga_route.contracts import (
    AdapterCapabilities,
    AdapterError,
    IVerificationAdapter,
)
from kanga_route.crm.hubspot import HubSpotClient, HubSpotError
from kanga_route.models import VerificationOutcome, VerificationTarget


class HubSpotAdapter(IVerificationAdapter):
    """Translate neutral targets and outcomes to the HubSpot API client."""

    _CAPABILITIES = AdapterCapabilities(
        can_read_targets=True,
        can_write_outcomes=True,
        max_batch_size=10_000,
    )

    def __init__(self, client: Optional[HubSpotClient] = None):
        self.client = client or HubSpotClient()

    @property
    def name(self) -> str:
        return "hubspot"

    @property
    def capabilities(self) -> AdapterCapabilities:
        return self._CAPABILITIES

    def validate_configuration(self) -> None:
        if not self.client.access_token:
            raise AdapterError("HUBSPOT_ACCESS_TOKEN is required")

    def fetch_targets(self, limit: int = 100) -> Sequence[VerificationTarget]:
        self.validate_configuration()
        try:
            return self.client.fetch_unverified_contacts(limit=limit)
        except HubSpotError as exc:
            raise AdapterError("hubspot target read failed") from exc

    def write_outcomes(
        self, outcomes: Sequence[VerificationOutcome]
    ) -> bool:
        self.validate_configuration()
        try:
            return self.client.batch_update_verification_results(list(outcomes))
        except HubSpotError as exc:
            raise AdapterError("hubspot outcome write failed") from exc
