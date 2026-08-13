"""Product-neutral domain models and enums for Kanga-Route verification."""

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


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
    contact_id: Optional[str] = None
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


class HubSpotContact(BaseModel):
    """HubSpot Contact representation."""

    id: str
    email: str
    properties: dict = Field(default_factory=dict)
