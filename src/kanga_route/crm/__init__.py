"""CRM integration subpackage."""

from kanga_route.crm.hubspot import HubSpotClient, HubSpotError

__all__ = ["HubSpotClient", "HubSpotError"]
