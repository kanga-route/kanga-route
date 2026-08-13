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

    def to_hubspot_properties(self) -> dict:
        """Converts result into HubSpot custom property payload."""
        # HubSpot datetime properties accept Unix epoch milliseconds, while the
        # domain model deliberately retains a readable ISO-8601 timestamp.
        iso_timestamp = self.verified_at
        if iso_timestamp.endswith(("Z", "z")):
            iso_timestamp = f"{iso_timestamp[:-1]}+00:00"
        parsed_timestamp = datetime.fromisoformat(iso_timestamp)
        if parsed_timestamp.tzinfo is None:
            parsed_timestamp = parsed_timestamp.replace(tzinfo=timezone.utc)
        parsed_timestamp = parsed_timestamp.astimezone(timezone.utc)
        epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
        elapsed = parsed_timestamp - epoch
        epoch_milliseconds = (
            elapsed.days * 86_400_000
            + elapsed.seconds * 1_000
            + elapsed.microseconds // 1_000
        )

        return {
            "email_verification_status": self.status.value,
            "email_verification_reason": self.reason.value,
            "mailbox_provider": self.mailbox_provider.value,
            "is_role_account": str(self.is_role_account).lower(),
            "last_verified": str(epoch_milliseconds),
        }


class HubSpotContact(BaseModel):
    """HubSpot Contact representation."""

    id: str
    email: str
    properties: dict = Field(default_factory=dict)
