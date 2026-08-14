"""Product-neutral single-address verification application service."""

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional

from kanga_route.configuration import validate_smtp_identity
from kanga_route.contracts import ICacheStore, IVerificationPipeline
from kanga_route.engine.verifier import EMAIL_REGEX
from kanga_route.models import VerificationResult, VerificationStatus


class CachePolicy(str, Enum):
    """Whether a single verification may reuse definitive cached evidence."""

    USE = "use"
    REFRESH = "refresh"


class CacheStatus(str, Enum):
    """How the application service used the cache for one request."""

    HIT = "hit"
    MISS = "miss"
    BYPASSED = "bypassed"


class SingleVerificationError(RuntimeError):
    """A sanitized, stable application-service failure."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class SingleVerificationOutcome:
    """Neutral result plus non-sensitive cache disposition."""

    result: VerificationResult
    cache_status: CacheStatus


def normalize_email(value: object) -> str:
    """Normalize one address or raise before any network operation."""
    if not isinstance(value, str):
        raise SingleVerificationError("invalid_email")

    normalized = value.strip().lower()
    if (
        not normalized
        or len(normalized) > 254
        or EMAIL_REGEX.fullmatch(normalized) is None
    ):
        raise SingleVerificationError("invalid_email")
    return normalized


class SingleVerificationService:
    """Apply validation, cache policy, and verification for one address."""

    def __init__(
        self,
        cache_store: ICacheStore,
        engine: IVerificationPipeline,
        configuration_validator: Optional[Callable[[], None]] = (
            validate_smtp_identity
        ),
    ):
        self.cache_store = cache_store
        self.engine = engine
        self.configuration_validator = configuration_validator

    def verify(
        self,
        email: object,
        cache_policy: CachePolicy = CachePolicy.USE,
    ) -> SingleVerificationOutcome:
        """Verify one normalized address under an explicit cache policy."""
        normalized = normalize_email(email)

        if cache_policy == CachePolicy.USE:
            try:
                cached_result = self.cache_store.get(normalized)
            except Exception as exc:
                raise SingleVerificationError("cache_unavailable") from exc

            if (
                cached_result is not None
                and cached_result.status != VerificationStatus.UNKNOWN
            ):
                return SingleVerificationOutcome(
                    result=cached_result,
                    cache_status=CacheStatus.HIT,
                )
            cache_status = CacheStatus.MISS
        else:
            cache_status = CacheStatus.BYPASSED

        if self.configuration_validator is not None:
            try:
                self.configuration_validator()
            except Exception as exc:
                raise SingleVerificationError("configuration_invalid") from exc

        try:
            result = self.engine.verify(normalized)
        except Exception as exc:
            raise SingleVerificationError("verification_failed") from exc

        if result.status != VerificationStatus.UNKNOWN:
            try:
                cached = self.cache_store.put(result)
            except Exception as exc:
                raise SingleVerificationError("cache_unavailable") from exc
            if cached is False:
                raise SingleVerificationError("cache_unavailable")

        return SingleVerificationOutcome(
            result=result,
            cache_status=cache_status,
        )
