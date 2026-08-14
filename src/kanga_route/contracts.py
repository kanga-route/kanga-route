"""Product-neutral ports between Kanga-Route architectural components.

Only domain types cross these boundaries.  Product SDK objects, product-specific
errors, authentication details, and field formatting belong behind an adapter.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Sequence

from kanga_route.models import (
    VerificationOutcome,
    VerificationResult,
    VerificationTarget,
)


class AdapterError(RuntimeError):
    """A stable application-facing failure raised by any integration adapter."""


@dataclass(frozen=True)
class AdapterCapabilities:
    """Operations and limits an adapter promises to the batch orchestrator."""

    can_read_targets: bool
    can_write_outcomes: bool
    max_batch_size: int

    def __post_init__(self) -> None:
        if self.max_batch_size < 1:
            raise ValueError("max_batch_size must be greater than zero")


class IVerificationStage(ABC):
    """Abstract interface for a single verification pipeline stage."""

    @abstractmethod
    def evaluate(
        self, email: str, context: Optional[dict] = None
    ) -> Optional[VerificationResult]:
        """Return a terminal result, or None to continue the pipeline."""
        pass


class IVerificationPipeline(ABC):
    """Abstract interface for the full verification engine."""

    @abstractmethod
    def verify(self, email: str) -> VerificationResult:
        """Runs an email through all verification stages and returns the result."""
        pass


class ICacheStore(ABC):
    """Abstract interface for DynamoDB caching (local or cloud)."""

    @abstractmethod
    def get(self, email: str) -> Optional[VerificationResult]:
        """Retrieves a cached verification result by email address."""
        pass

    @abstractmethod
    def put(self, result: VerificationResult, ttl_seconds: Optional[int] = None) -> bool:
        """Stores a verification result in the cache."""
        pass


class IVerificationAdapter(ABC):
    """Stable port implemented by every product or service integration.

    Adding an adapter must not require a verification-engine change.  Adapters
    select neutral targets and translate neutral outcomes into their own API.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the stable configuration name for this adapter."""
        pass

    @property
    @abstractmethod
    def capabilities(self) -> AdapterCapabilities:
        """Declare supported operations and the adapter's hard batch limit."""
        pass

    @abstractmethod
    def validate_configuration(self) -> None:
        """Raise AdapterError before I/O when required settings are absent."""
        pass

    @abstractmethod
    def fetch_targets(
        self, limit: int = 100
    ) -> Sequence[VerificationTarget]:
        """Return product-neutral records selected for verification."""
        pass

    @abstractmethod
    def write_outcomes(
        self, outcomes: Sequence[VerificationOutcome]
    ) -> bool:
        """Persist product-neutral outcomes using adapter-owned formatting."""
        pass
