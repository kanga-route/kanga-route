"""4-layer email verification engine implementing IVerificationPipeline.

Layer 1: Syntax & Role Account Evaluation
Layer 2: Disposable Domain Blocklist Check
Layer 3: DNS Lookup & Mailbox Provider Fingerprinting
Layer 4: Direct SMTP Socket Handshake
"""

import os
import re
import socket
import smtplib
from typing import List, Optional, Tuple, Set
import dns.resolver

from kanga_route.contracts import IVerificationPipeline, IVerificationStage
from kanga_route.models import (
    VerificationResult,
    VerificationStatus,
    VerificationReason,
    MailboxProvider,
)

# Common role account prefixes
ROLE_PREFIXES: Set[str] = {
    "admin",
    "administrator",
    "info",
    "support",
    "sales",
    "contact",
    "billing",
    "help",
    "jobs",
    "careers",
    "security",
    "postmaster",
    "hostmaster",
    "webmaster",
    "marketing",
    "press",
    "media",
    "office",
    "team",
}

# Standard disposable email domains
DISPOSABLE_DOMAINS: Set[str] = {
    "mailinator.com",
    "10minutemail.com",
    "tempmail.com",
    "guerrillamail.com",
    "trashmail.com",
    "yopmail.com",
    "dispostable.com",
    "getnada.com",
    "throwawaymail.com",
    "temp-mail.org",
    "sharklasers.com",
}

# Basic RFC 5322 pattern check
EMAIL_REGEX = re.compile(
    r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+$"
)


class SyntaxAndRoleStage(IVerificationStage):
    """Layer 1: Evaluates email syntax and role account status."""

    def evaluate(
        self, email: str, context: Optional[dict] = None
    ) -> Optional[VerificationResult]:
        if not email or not isinstance(email, str):
            return VerificationResult(
                email=email or "",
                status=VerificationStatus.INVALID,
                reason=VerificationReason.SYNTAX_ERROR,
            )

        email_clean = email.strip().lower()
        if not EMAIL_REGEX.match(email_clean):
            return VerificationResult(
                email=email_clean,
                status=VerificationStatus.INVALID,
                reason=VerificationReason.SYNTAX_ERROR,
            )

        local_part = email_clean.split("@")[0]
        is_role = local_part in ROLE_PREFIXES

        if context is not None:
            context["is_role_account"] = is_role

        return None


class BlocklistStage(IVerificationStage):
    """Layer 2: Checks if domain is a known disposable provider."""

    def evaluate(
        self, email: str, context: Optional[dict] = None
    ) -> Optional[VerificationResult]:
        domain = email.strip().lower().split("@")[-1]
        if domain in DISPOSABLE_DOMAINS:
            is_role = context.get("is_role_account", False) if context else False
            return VerificationResult(
                email=email,
                status=VerificationStatus.INVALID,
                reason=VerificationReason.DISPOSABLE,
                is_role_account=is_role,
            )
        return None


class DNSStage(IVerificationStage):
    """Layer 3: Queries DNS for MX records and fingerprints provider."""

    def __init__(self, resolver: Optional[dns.resolver.Resolver] = None):
        self.resolver = resolver or dns.resolver.Resolver()

    def evaluate(
        self, email: str, context: Optional[dict] = None
    ) -> Optional[VerificationResult]:
        domain = email.strip().lower().split("@")[-1]
        mx_hosts: List[str] = []

        try:
            answers = self.resolver.resolve(domain, "MX")
            # Sort by preference
            sorted_answers = sorted(answers, key=lambda r: r.preference)
            mx_hosts = [str(r.exchange).rstrip(".") for r in sorted_answers]
        except Exception:
            # Fallback to A record if no MX
            try:
                a_answers = self.resolver.resolve(domain, "A")
                if a_answers:
                    mx_hosts = [domain]
            except Exception:
                pass

        if not mx_hosts:
            is_role = context.get("is_role_account", False) if context else False
            return VerificationResult(
                email=email,
                status=VerificationStatus.INVALID,
                reason=VerificationReason.NO_MX,
                is_role_account=is_role,
            )

        provider = self._fingerprint_provider(mx_hosts)

        if context is not None:
            context["mx_hosts"] = mx_hosts
            context["mailbox_provider"] = provider

        return None

    @staticmethod
    def _fingerprint_provider(mx_hosts: List[str]) -> MailboxProvider:
        mx_str = " ".join(mx_hosts).lower()
        if "google" in mx_str or "aspmx" in mx_str:
            return MailboxProvider.GOOGLE_WORKSPACE
        elif "outlook" in mx_str or "microsoft" in mx_str or "hotmail" in mx_str:
            return MailboxProvider.MICROSOFT_365
        elif "proton" in mx_str:
            return MailboxProvider.PROTON
        elif "yahoo" in mx_str:
            return MailboxProvider.YAHOO
        elif "icloud" in mx_str or "apple" in mx_str:
            return MailboxProvider.ICLOUD
        return MailboxProvider.OTHER


class SMTPSocketStage(IVerificationStage):
    """Layer 4: Performs direct SMTP TCP socket handshake."""

    def __init__(
        self,
        helo_domain: str = "verifier.kanga-route.internal",
        from_email: str = "verify@kanga-route.internal",
        timeout: float = 5.0,
    ):
        self.helo_domain = helo_domain
        self.from_email = from_email
        self.timeout = timeout

    def evaluate(
        self, email: str, context: Optional[dict] = None
    ) -> Optional[VerificationResult]:
        mx_hosts = context.get("mx_hosts", []) if context else []
        provider = (
            context.get("mailbox_provider", MailboxProvider.OTHER)
            if context
            else MailboxProvider.OTHER
        )
        is_role = context.get("is_role_account", False) if context else False

        if not mx_hosts:
            return VerificationResult(
                email=email,
                status=VerificationStatus.INVALID,
                reason=VerificationReason.NO_MX,
                is_role_account=is_role,
            )

        primary_mx = mx_hosts[0]
        try:
            smtp = smtplib.SMTP(timeout=self.timeout)
            code, msg = smtp.connect(primary_mx, 25)

            if code not in (220, 250):
                smtp.close()
                return VerificationResult(
                    email=email,
                    status=VerificationStatus.UNKNOWN,
                    reason=VerificationReason.CONNECTION_REFUSED,
                    mailbox_provider=provider,
                    is_role_account=is_role,
                    mx_records=mx_hosts,
                    smtp_code=code,
                )

            smtp.helo(self.helo_domain)
            smtp.mail(self.from_email)
            code, resp = smtp.rcpt(email)

            try:
                smtp.quit()
            except Exception:
                pass

            if code in (250, 251):
                return VerificationResult(
                    email=email,
                    status=VerificationStatus.VALID,
                    reason=VerificationReason.OK,
                    mailbox_provider=provider,
                    is_role_account=is_role,
                    mx_records=mx_hosts,
                    smtp_code=code,
                )
            elif code in (550, 551, 552, 553, 554):
                return VerificationResult(
                    email=email,
                    status=VerificationStatus.INVALID,
                    reason=VerificationReason.USER_NOT_FOUND,
                    mailbox_provider=provider,
                    is_role_account=is_role,
                    mx_records=mx_hosts,
                    smtp_code=code,
                )
            elif code in (450, 451, 452):
                return VerificationResult(
                    email=email,
                    status=VerificationStatus.CATCH_ALL,
                    reason=VerificationReason.GREYLISTED,
                    mailbox_provider=provider,
                    is_role_account=is_role,
                    mx_records=mx_hosts,
                    smtp_code=code,
                )
            else:
                return VerificationResult(
                    email=email,
                    status=VerificationStatus.UNKNOWN,
                    reason=VerificationReason.UNKNOWN_HOST,
                    mailbox_provider=provider,
                    is_role_account=is_role,
                    mx_records=mx_hosts,
                    smtp_code=code,
                )

        except (socket.timeout, smtplib.SMTPConnectError, TimeoutError):
            return VerificationResult(
                email=email,
                status=VerificationStatus.UNKNOWN,
                reason=VerificationReason.TIMEOUT,
                mailbox_provider=provider,
                is_role_account=is_role,
                mx_records=mx_hosts,
            )
        except Exception:
            return VerificationResult(
                email=email,
                status=VerificationStatus.UNKNOWN,
                reason=VerificationReason.CONNECTION_REFUSED,
                mailbox_provider=provider,
                is_role_account=is_role,
                mx_records=mx_hosts,
            )


class VerificationEngine(IVerificationPipeline):
    """Main verification engine composing the 4 evaluation stages."""

    def __init__(
        self,
        stages: Optional[List[IVerificationStage]] = None,
        smtp_timeout: float = 5.0,
    ):
        if stages:
            self.stages = stages
        else:
            self.stages = [
                SyntaxAndRoleStage(),
                BlocklistStage(),
                DNSStage(),
                SMTPSocketStage(timeout=smtp_timeout),
            ]

    def verify(self, email: str) -> VerificationResult:
        context: dict = {}
        for stage in self.stages:
            res = stage.evaluate(email, context=context)
            if res is not None:
                return res

        # Fallback if no stage produced a terminal result
        is_role = context.get("is_role_account", False)
        provider = context.get("mailbox_provider", MailboxProvider.OTHER)
        mx_hosts = context.get("mx_hosts", [])

        return VerificationResult(
            email=email,
            status=VerificationStatus.UNKNOWN,
            reason=VerificationReason.UNKNOWN_HOST,
            mailbox_provider=provider,
            is_role_account=is_role,
            mx_records=mx_hosts,
        )
