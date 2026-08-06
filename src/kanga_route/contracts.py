"""Strict interface contracts between Kanga-Route architectural components.

Enforces clear boundaries between Verification Engine, DynamoDB Cache, and HubSpot CRM Client.
"""

from abc import ABC, abstractmethod
from typing import List, Optional
from kanga_route.models import VerificationResult, HubSpotContact


class IVerificationStage(ABC):
    """Abstract interface for a single verification pipeline stage."""

    @abstractmethod
    def evaluate(
        self, email: str, context: Optional[dict] = None
    ) -> Optional[VerificationResult]:
        """Evaluates an email. Returns a VerificationResult if a terminal status is reached, or None to continue."""
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


class ICRMClient(ABC):
    """Abstract interface for CRM operations (HubSpot)."""

    @abstractmethod
    def fetch_unverified_contacts(self, limit: int = 100) -> List[HubSpotContact]:
        """Fetches batch of contacts requiring verification."""
        pass

    @abstractmethod
    def batch_update_verification_results(
        self, results: List[VerificationResult]
    ) -> bool:
        """Batch updates contact verification properties in the CRM."""
        pass
