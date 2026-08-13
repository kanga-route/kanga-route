"""CRM integration subpackage."""

from kanga_route.crm.hubspot import (
    HubSpotClient,
    HubSpotError,
    format_verification_properties,
)

__all__ = [
    "HubSpotClient",
    "HubSpotError",
    "format_verification_properties",
]
