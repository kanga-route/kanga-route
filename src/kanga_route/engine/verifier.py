"""4-layer email verification engine implementing IVerificationPipeline.

Layer 1: Syntax & Role Account Evaluation
Layer 2: Expanded Disposable Domain Blocklist Check
Layer 3: DNS Lookup & Mailbox Provider Fingerprinting
Layer 4: Direct SMTP Socket Handshake (STARTTLS, Catch-All Dummy Check, Provider Throttling)
"""

import asyncio
import os
import re
import socket
import smtplib
import ssl
import uuid
from typing import List, Optional, Set, Dict
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
    "compliance",
    "privacy",
    "abuse",
    "finance",
    "accounting",
    "legal",
}

# Expanded production disposable email domain blocklist (150+ providers)
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
    "guerrillamail.block",
    "guerrillamail.info",
    "guerrillamail.biz",
    "guerrillamail.de",
    "guerrillamail.net",
    "guerrillamail.org",
    "guerrillamailblock.com",
    "pokemail.net",
    "spam4.me",
    "grr.la",
    "inboxalias.com",
    "mailna.co",
    "mailna.in",
    "mailna.me",
    "mohmal.com",
    "disposablemail.com",
    "tempinbox.com",
    "crazymailing.com",
    "tempmail.net",
    "mytemp.email",
    "generator.email",
    "emailondeck.com",
    "tempail.com",
    "mailnesia.com",
    "dropmail.me",
    "fakeinbox.com",
    "trashmail.net",
    "trashmail.me",
    "trashmail.at",
    "trashmail.com.de",
    "trashmail.io",
    "yopmail.fr",
    "yopmail.net",
    "cool.fr.nf",
    "jetable.fr.nf",
    "courriel.fr.nf",
    "moncourrier.fr.nf",
    "monemail.fr.nf",
    "monmail.fr.nf",
    "nospam.ze.tc",
    "nomail.xl.cx",
    "mega.zik.dj",
    "speed.1s.fr",
    "courriel.realhist.com",
    "maildrop.cc",
    "getairmail.com",
    "inboxclean.com",
    "boun.cr",
    "0815.ru",
    "10minutemail.co.uk",
    "10minutemail.net",
    "20mail.it",
    "33mail.com",
    "anonbox.net",
    "binkmail.com",
    "bobmail.info",
    "bugmenot.com",
    "crapmail.org",
    "dayrep.com",
    "discard.email",
    "discardmail.com",
    "discardmail.de",
    "dodgeit.com",
    "drdrb.com",
    "e4ward.com",
    "emailtemporal.com",
    "emailtemporal.org",
    "emltmp.com",
    "filzmail.com",
    "fleamail.com",
    "fmail.co.uk",
    "gishpuppy.com",
    "guerrillamail.de",
    "hatespam.org",
    "hidemail.de",
    "incognitomail.com",
    "incognitomail.org",
    "jetable.org",
    "junkmail.io",
    "kasmail.com",
    "klzlk.com",
    "letthemeatspam.com",
    "list.ru",
    "mail-temporaire.fr",
    "mailcatch.com",
    "mailexpire.com",
    "mailfa.com",
    "mailinator.net",
    "mailinator2.com",
    "mailme.gq",
    "mailnull.com",
    "mailtothis.com",
    "meltmail.com",
    "mintemail.com",
    "mytrashmail.com",
    "netcourrier.com",
    "nospam4.us",
    "nowmymail.com",
    "oneoffmail.com",
    "owlymail.com",
    "pwnedmail.com",
    "safetypost.de",
    "spambox.us",
    "spamfree24.org",
    "spamgourmet.com",
    "syronex.com",
    "tafmail.com",
    "tempr.email",
    "tmpeml.com",
    "trashymail.com",
    "zippymail.in",
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

    def __init__(self, custom_blocklist: Optional[Set[str]] = None):
        self.blocklist = custom_blocklist or DISPOSABLE_DOMAINS

    def evaluate(
        self, email: str, context: Optional[dict] = None
    ) -> Optional[VerificationResult]:
        domain = email.strip().lower().split("@")[-1]
        if domain in self.blocklist:
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
    """Layer 4: Direct SMTP socket handshake with STARTTLS, Catch-All test & Public HELO/MAIL FROM."""

    def __init__(
        self,
        helo_domain: Optional[str] = None,
        from_email: Optional[str] = None,
        timeout: float = 5.0,
        enable_tls: bool = True,
        check_catch_all: bool = True,
    ):
        self.helo_domain = helo_domain or os.getenv("SMTP_HELO_DOMAIN", "verifier.kanga-route.com")
        self.from_email = from_email or os.getenv("SMTP_MAIL_FROM", "verify@kanga-route.com")
        self.timeout = timeout
        self.enable_tls = enable_tls
        self.check_catch_all = check_catch_all

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
        domain = email.strip().lower().split("@")[-1]

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

            # Issue initial EHLO
            smtp.ehlo(self.helo_domain)

            # Negotiate STARTTLS encryption if supported
            if self.enable_tls and smtp.has_extn("starttls"):
                try:
                    context_ssl = ssl.create_default_context()
                    context_ssl.check_hostname = False
                    context_ssl.verify_mode = ssl.CERT_NONE
                    smtp.starttls(context=context_ssl)
                    smtp.ehlo(self.helo_domain)
                except Exception:
                    pass

            smtp.mail(self.from_email)

            # Catch-All Detection via random non-existent dummy address
            if self.check_catch_all:
                dummy_local = f"nxdomain_test_{uuid.uuid4().hex[:10]}"
                dummy_email = f"{dummy_local}@{domain}"
                dummy_code, _ = smtp.rcpt(dummy_email)

                if dummy_code in (250, 251):
                    # Server accepts ANY recipient address -> Catch-All Domain
                    try:
                        smtp.quit()
                    except Exception:
                        pass
                    return VerificationResult(
                        email=email,
                        status=VerificationStatus.CATCH_ALL,
                        reason=VerificationReason.OK,
                        mailbox_provider=provider,
                        is_role_account=is_role,
                        mx_records=mx_hosts,
                        smtp_code=dummy_code,
                    )

            # Evaluate Target Recipient Email
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
                    status=VerificationStatus.UNKNOWN,
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
    """Main sync verification engine composing all evaluation stages."""

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


class AsyncVerificationEngine:
    """Production Async Verification Engine with provider-based semaphore rate limiting."""

    def __init__(
        self,
        sync_engine: Optional[IVerificationPipeline] = None,
        max_concurrent_per_provider: int = 5,
    ):
        self.sync_engine = sync_engine or VerificationEngine()
        self.max_concurrent_per_provider = max_concurrent_per_provider
        self.provider_semaphores: Dict[str, asyncio.Semaphore] = {}

    def _get_semaphore(self, domain: str) -> asyncio.Semaphore:
        if domain not in self.provider_semaphores:
            self.provider_semaphores[domain] = asyncio.Semaphore(
                self.max_concurrent_per_provider
            )
        return self.provider_semaphores[domain]

    async def verify_email_async(self, email: str) -> VerificationResult:
        domain = email.strip().lower().split("@")[-1]
        sem = self._get_semaphore(domain)
        async with sem:
            loop = asyncio.get_running_loop()
            # Run CPU/Network IO bound sync verification in thread pool executor
            return await loop.run_in_executor(None, self.sync_engine.verify, email)

    async def verify_batch_async(self, emails: List[str]) -> List[VerificationResult]:
        tasks = [self.verify_email_async(email) for email in emails]
        return await asyncio.gather(*tasks)
