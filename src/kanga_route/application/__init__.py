"""Product-neutral application services."""

from kanga_route.application.single_verification import (
    CachePolicy,
    CacheStatus,
    SingleVerificationError,
    SingleVerificationOutcome,
    SingleVerificationService,
    normalize_email,
)

__all__ = [
    "CachePolicy",
    "CacheStatus",
    "SingleVerificationError",
    "SingleVerificationOutcome",
    "SingleVerificationService",
    "normalize_email",
]
