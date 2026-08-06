"""Domain models and enums for Kanga-Route verification and CRM writebacks.

Refers to ADR 0003: Granular CRM Intelligence Writebacks.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class VerificationStatus(str, Enum):
    """Granular verification status for CRM update."""

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

    def to_hubspot_properties(self) -> dict:
        """Converts result into HubSpot custom property payload."""
        return {
            "email_verification_status": self.status.value,
            "email_verification_reason": self.reason.value,
            "mailbox_provider": self.mailbox_provider.value,
            "is_role_account": str(self.is_role_account).lower(),
            "last_verified": self.verified_at,
        }


class HubSpotContact(BaseModel):
    """HubSpot Contact representation."""

    id: str
    email: str
    properties: dict = Field(default_factory=dict)
