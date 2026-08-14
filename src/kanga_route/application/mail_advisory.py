"""Cache-only, fail-open recipient advice for optional mail integrations."""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Sequence

from kanga_route.contracts import ICacheStore
from kanga_route.email_address import normalize_email_address
from kanga_route.models import VerificationResult, VerificationStatus


class AdviceAction(str, Enum):
    """Non-authoritative action recommended to a mail integration."""

    ALLOW = "allow"
    WARN = "warn"


class AdviceSource(str, Enum):
    """Where an advisory decision came from."""

    CACHE = "cache"
    MISS = "miss"
    UNAVAILABLE = "unavailable"
    LOCAL = "local"


@dataclass(frozen=True)
class RecipientAdvice:
    """One recipient's fail-open disposition and optional cached evidence."""

    email: str
    action: AdviceAction
    source: AdviceSource
    result: Optional[VerificationResult] = None

    def to_dict(self) -> dict:
        return {
            "email": self.email,
            "action": self.action.value,
            "source": self.source.value,
            "result": self.result.to_dict() if self.result is not None else None,
        }


@dataclass(frozen=True)
class MailAdvisoryOutcome:
    """A bounded multi-recipient response that is always safe to fail open."""

    recipients: tuple[RecipientAdvice, ...]
    fail_open: bool = True

    def to_dict(self) -> dict:
        return {
            "fail_open": self.fail_open,
            "recipients": [recipient.to_dict() for recipient in self.recipients],
        }


class MailAdvisoryService:
    """Read cached evidence without invoking DNS, SMTP, or the live engine.

    Cache misses and cache failures are normal allow decisions.  This service
    deliberately has no verification-engine dependency, so it cannot put live
    probing in a message-acceptance transaction.
    """

    def __init__(self, cache_store: ICacheStore, max_recipients: int = 100):
        if max_recipients < 1:
            raise ValueError("max_recipients must be greater than zero")
        self.cache_store = cache_store
        self.max_recipients = max_recipients

    def advise(self, recipients: Sequence[object]) -> MailAdvisoryOutcome:
        if len(recipients) > self.max_recipients:
            raise ValueError(
                f"recipient count cannot exceed {self.max_recipients}"
            )

        advice = []
        seen = set()
        for supplied in recipients:
            try:
                normalized = normalize_email_address(supplied)
            except ValueError:
                display = supplied.strip().lower() if isinstance(supplied, str) else ""
                identity = ("invalid", display)
                if identity in seen:
                    continue
                seen.add(identity)
                advice.append(
                    RecipientAdvice(
                        email=display,
                        action=AdviceAction.WARN,
                        source=AdviceSource.LOCAL,
                    )
                )
                continue

            identity = ("valid", normalized)
            if identity in seen:
                continue
            seen.add(identity)

            try:
                cached = self.cache_store.get(normalized)
            except Exception:
                advice.append(
                    RecipientAdvice(
                        email=normalized,
                        action=AdviceAction.ALLOW,
                        source=AdviceSource.UNAVAILABLE,
                    )
                )
                continue

            if cached is None:
                advice.append(
                    RecipientAdvice(
                        email=normalized,
                        action=AdviceAction.ALLOW,
                        source=AdviceSource.MISS,
                    )
                )
                continue

            action = (
                AdviceAction.WARN
                if cached.status == VerificationStatus.INVALID
                else AdviceAction.ALLOW
            )
            advice.append(
                RecipientAdvice(
                    email=normalized,
                    action=action,
                    source=AdviceSource.CACHE,
                    result=cached,
                )
            )

        return MailAdvisoryOutcome(recipients=tuple(advice))
