"""Explicit adapter discovery without importing products into shared code."""

import os
from collections.abc import Callable
from typing import Optional

from kanga_route.contracts import IVerificationAdapter

AdapterFactory = Callable[[], IVerificationAdapter]


def _hubspot_factory() -> IVerificationAdapter:
    from kanga_route.adapters.hubspot import HubSpotAdapter

    return HubSpotAdapter()


ADAPTER_FACTORIES: dict[str, AdapterFactory] = {
    "hubspot": _hubspot_factory,
}


def create_adapter(name: Optional[str] = None) -> IVerificationAdapter:
    """Construct the selected adapter from an allow-listed registry."""
    selected = (name or os.getenv("KANGA_ROUTE_ADAPTER", "hubspot")).strip().lower()
    try:
        factory = ADAPTER_FACTORIES[selected]
    except KeyError as exc:
        supported = ", ".join(sorted(ADAPTER_FACTORIES))
        raise ValueError(
            f"Unsupported KANGA_ROUTE_ADAPTER {selected!r}; choose: {supported}"
        ) from exc
    return factory()
