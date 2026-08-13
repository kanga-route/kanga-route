"""Product-neutral domain models and enums for Kanga-Route verification."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, model_validator


class VerificationStatus(str, Enum):
    """Granular email verification status."""

    VALID = "Valid"
    INVALID = "Invalid"
    CATCH_ALL = "Catch-All"
    UNKNOWN = "Unknown"


class VerificationReason(str, Enum):
    """Detailed reason for verification classification."""

    OK = "OK"
    SYNTAX_ERROR = "Syntax_Error"
    DISPOSABLE = "Disposable"
    NO_MX = "No_MX"
    USER_NOT_FOUND = "User_Not_Found"
    GREYLISTED = "Greylisted"
    TIMEOUT = "Timeout"
    CONNECTION_REFUSED = "Connection_Refused"
    UNKNOWN_HOST = "Unknown_Host"
    DNS_TIMEOUT = "DNS_Timeout"
    DNS_ERROR = "DNS_Error"
    SMTP_TEMPORARY_FAILURE = "SMTP_Temporary_Failure"
    SMTP_REJECTED = "SMTP_Rejected"


class MailboxProvider(str, Enum):
    """Fingerprinted email service provider based on MX records."""

    GOOGLE_WORKSPACE = "Google Workspace"
    MICROSOFT_365 = "Microsoft 365"
    PROTON = "Proton Mail"
    YAHOO = "Yahoo Mail"
    ICLOUD = "iCloud Mail"
    OTHER = "Other / Self-Hosted"


class VerificationResult(BaseModel):
    """Strict verification result contract."""

    email: str
    status: VerificationStatus
    reason: VerificationReason
    mailbox_provider: MailboxProvider = MailboxProvider.OTHER
    is_role_account: bool = False
    mx_records: List[str] = Field(default_factory=list)
    smtp_code: Optional[int] = None
    verified_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict:
        """Return the product-neutral JSON-compatible result representation."""
        return self.model_dump(mode="json")


class VerificationTarget(BaseModel):
    """Product-neutral record selected by an integration for verification."""

    record_id: str
    email: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class VerificationOutcome(BaseModel):
    """Associate adapter-owned record identity with verification evidence."""

    target: VerificationTarget
    result: VerificationResult

    @model_validator(mode="after")
    def target_and_result_emails_match(self):
        """Reject unsafe writeback pairings for different email addresses."""
        target_email = self.target.email.strip().casefold()
        result_email = self.result.email.strip().casefold()
        if target_email != result_email:
            raise ValueError("target and result email addresses must match")
        return self
