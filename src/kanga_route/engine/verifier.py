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
import dns.exception
import dns.resolver

from kanga_route.contracts import IVerificationPipeline, IVerificationStage
from kanga_route.email_address import EMAIL_REGEX
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

# Built-in disposable-domain list. Additions require evidence because matches
# are terminal verification failures.
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
            sorted_answers = sorted(answers, key=lambda record: record.preference)
            exchanges = [str(record.exchange) for record in sorted_answers]

            # A single null MX (RFC 7505) explicitly says that the domain does
            # not accept email, even if it also has an address record.
            if exchanges == ["."]:
                return self._no_mx_result(email, context)

            mx_hosts = [exchange.rstrip(".") for exchange in exchanges if exchange != "."]
        except dns.resolver.NXDOMAIN:
            # NXDOMAIN authoritatively proves that the recipient domain itself
            # does not exist; an address-record fallback cannot change that.
            return self._no_mx_result(email, context)
        except dns.resolver.NoAnswer:
            # RFC 5321 permits an A-record fallback when the domain exists but
            # publishes no MX record.
            mx_hosts = self._resolve_address_fallback(email, domain, context)
            if isinstance(mx_hosts, VerificationResult):
                return mx_hosts
        except dns.exception.Timeout:
            return self._dns_failure_result(email, context, VerificationReason.DNS_TIMEOUT)
        except dns.resolver.NoNameservers:
            return self._dns_failure_result(email, context, VerificationReason.DNS_ERROR)
        except Exception:
            # SERVFAIL, resolver transport errors, and other indeterminate
            # failures must never be interpreted as proof that a domain is bad.
            return self._dns_failure_result(email, context, VerificationReason.DNS_ERROR)

        if not mx_hosts:
            mx_hosts = self._resolve_address_fallback(email, domain, context)
            if isinstance(mx_hosts, VerificationResult):
                return mx_hosts

        provider = self._fingerprint_provider(mx_hosts)

        if context is not None:
            context["mx_hosts"] = mx_hosts
            context["mailbox_provider"] = provider

        return None

    def _resolve_address_fallback(
        self, email: str, domain: str, context: Optional[dict]
    ):
        transient_reason = None
        for record_type in ("A", "AAAA"):
            try:
                answers = self.resolver.resolve(domain, record_type)
            except dns.resolver.NXDOMAIN:
                return self._no_mx_result(email, context)
            except dns.resolver.NoAnswer:
                continue
            except dns.exception.Timeout:
                transient_reason = transient_reason or VerificationReason.DNS_TIMEOUT
                continue
            except dns.resolver.NoNameservers:
                transient_reason = VerificationReason.DNS_ERROR
                continue
            except Exception:
                transient_reason = VerificationReason.DNS_ERROR
                continue

            if answers:
                # RFC 5321 implicit MX uses the domain itself. Either address
                # family is sufficient; the SMTP client resolves the host.
                return [domain]

        if transient_reason is not None:
            return self._dns_failure_result(email, context, transient_reason)
        return self._no_mx_result(email, context)

    @staticmethod
    def _no_mx_result(email: str, context: Optional[dict]) -> VerificationResult:
        return VerificationResult(
            email=email,
            status=VerificationStatus.INVALID,
            reason=VerificationReason.NO_MX,
            is_role_account=(
                context.get("is_role_account", False) if context else False
            ),
        )

    @staticmethod
    def _dns_failure_result(
        email: str, context: Optional[dict], reason: VerificationReason
    ) -> VerificationResult:
        return VerificationResult(
            email=email,
            status=VerificationStatus.UNKNOWN,
            reason=reason,
            is_role_account=(
                context.get("is_role_account", False) if context else False
            ),
        )

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
    """Layer 4: Direct SMTP handshake with TLS and catch-all detection."""

    _RECIPIENT_NOT_FOUND_PATTERNS = (
        re.compile(r"\b5\.1\.1\b", re.IGNORECASE),
        re.compile(
            r"\b(?:user|recipient|mailbox)\s+(?:is\s+)?"
            r"(?:unknown|not found|does not exist)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\bno such (?:user|recipient|mailbox|account|address)\b",
            re.IGNORECASE,
        ),
        re.compile(r"\binvalid recipient\b", re.IGNORECASE),
        re.compile(
            r"\baccount\b.{0,80}\bdoes not exist\b",
            re.IGNORECASE,
        ),
    )

    def __init__(
        self,
        helo_domain: Optional[str] = None,
        from_email: Optional[str] = None,
        timeout: float = 5.0,
        enable_tls: bool = True,
        check_catch_all: bool = True,
    ):
        self.helo_domain = (
            helo_domain
            or os.getenv("SMTP_HELO_DOMAIN")
            or "verifier.kanga-route.invalid"
        )
        self.from_email = (
            from_email
            or os.getenv("SMTP_MAIL_FROM")
            or f"verify@{self.helo_domain.replace('verifier.', '')}"
        )
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
            return self._result(
                email,
                VerificationStatus.INVALID,
                VerificationReason.NO_MX,
                provider,
                is_role,
                mx_hosts,
            )

        domain = email.strip().lower().split("@")[-1]
        last_failure = self._result(
            email,
            VerificationStatus.UNKNOWN,
            VerificationReason.CONNECTION_REFUSED,
            provider,
            is_role,
            mx_hosts,
        )

        for mx_host in mx_hosts:
            smtp = None
            connected = False
            try:
                smtp = smtplib.SMTP(timeout=self.timeout)
                code, _ = smtp.connect(mx_host, 25)

                if code not in (220, 250):
                    reason = (
                        self._temporary_reason(code)
                        if 400 <= code < 500
                        else VerificationReason.SMTP_REJECTED
                    )
                    last_failure = self._result(
                        email,
                        VerificationStatus.UNKNOWN,
                        reason,
                        provider,
                        is_role,
                        mx_hosts,
                        code,
                    )
                    # A connection-level refusal says nothing about the target
                    # mailbox; another MX may still be healthy.
                    continue

                connected = True
                smtp.ehlo(self.helo_domain)

                if self.enable_tls and smtp.has_extn("starttls"):
                    try:
                        context_ssl = ssl.create_default_context()
                        context_ssl.check_hostname = False
                        context_ssl.verify_mode = ssl.CERT_NONE
                        smtp.starttls(context=context_ssl)
                        smtp.ehlo(self.helo_domain)
                    except Exception:
                        # Preserve opportunistic STARTTLS behavior: servers with
                        # a broken TLS extension can still answer the probe.
                        pass

                mail_code, _ = smtp.mail(self.from_email)
                if 400 <= mail_code < 500:
                    last_failure = self._result(
                        email,
                        VerificationStatus.UNKNOWN,
                        self._temporary_reason(mail_code),
                        provider,
                        is_role,
                        mx_hosts,
                        mail_code,
                    )
                    continue
                if not 200 <= mail_code < 300:
                    return self._result(
                        email,
                        VerificationStatus.UNKNOWN,
                        VerificationReason.SMTP_REJECTED,
                        provider,
                        is_role,
                        mx_hosts,
                        mail_code,
                    )

                if self.check_catch_all:
                    dummy_local = f"nxdomain_test_{uuid.uuid4().hex[:10]}"
                    dummy_email = f"{dummy_local}@{domain}"
                    dummy_code, _ = smtp.rcpt(dummy_email)

                    if dummy_code in (250, 251):
                        return self._result(
                            email,
                            VerificationStatus.CATCH_ALL,
                            VerificationReason.OK,
                            provider,
                            is_role,
                            mx_hosts,
                            dummy_code,
                        )
                    if 400 <= dummy_code < 500:
                        last_failure = self._result(
                            email,
                            VerificationStatus.UNKNOWN,
                            self._temporary_reason(dummy_code),
                            provider,
                            is_role,
                            mx_hosts,
                            dummy_code,
                        )
                        continue

                code, response = smtp.rcpt(email)

                if code in (250, 251):
                    return self._result(
                        email,
                        VerificationStatus.VALID,
                        VerificationReason.OK,
                        provider,
                        is_role,
                        mx_hosts,
                        code,
                    )
                if 400 <= code < 500:
                    last_failure = self._result(
                        email,
                        VerificationStatus.UNKNOWN,
                        self._temporary_reason(code),
                        provider,
                        is_role,
                        mx_hosts,
                        code,
                    )
                    continue
                if self._is_explicit_recipient_not_found(code, response):
                    return self._result(
                        email,
                        VerificationStatus.INVALID,
                        VerificationReason.USER_NOT_FOUND,
                        provider,
                        is_role,
                        mx_hosts,
                        code,
                    )
                if 500 <= code < 600:
                    # A bare/generic 5xx can represent policy, authentication,
                    # reputation, or relay restrictions. It is not proof that
                    # the recipient does not exist.
                    return self._result(
                        email,
                        VerificationStatus.UNKNOWN,
                        VerificationReason.SMTP_REJECTED,
                        provider,
                        is_role,
                        mx_hosts,
                        code,
                    )
                return self._result(
                    email,
                    VerificationStatus.UNKNOWN,
                    VerificationReason.UNKNOWN_HOST,
                    provider,
                    is_role,
                    mx_hosts,
                    code,
                )
            except (socket.timeout, TimeoutError):
                last_failure = self._result(
                    email,
                    VerificationStatus.UNKNOWN,
                    VerificationReason.TIMEOUT,
                    provider,
                    is_role,
                    mx_hosts,
                )
            except smtplib.SMTPResponseException as exc:
                reason = (
                    self._temporary_reason(exc.smtp_code)
                    if 400 <= exc.smtp_code < 500
                    else VerificationReason.SMTP_REJECTED
                )
                last_failure = self._result(
                    email,
                    VerificationStatus.UNKNOWN,
                    reason,
                    provider,
                    is_role,
                    mx_hosts,
                    exc.smtp_code,
                )
            except (smtplib.SMTPException, OSError):
                last_failure = self._result(
                    email,
                    VerificationStatus.UNKNOWN,
                    VerificationReason.CONNECTION_REFUSED,
                    provider,
                    is_role,
                    mx_hosts,
                )
            except Exception:
                last_failure = self._result(
                    email,
                    VerificationStatus.UNKNOWN,
                    VerificationReason.CONNECTION_REFUSED,
                    provider,
                    is_role,
                    mx_hosts,
                )
            finally:
                self._close_smtp(smtp, connected)

        return last_failure

    @classmethod
    def _is_explicit_recipient_not_found(cls, code: int, response) -> bool:
        if not 500 <= code < 600:
            return False
        if isinstance(response, bytes):
            message = response.decode("utf-8", errors="replace")
        else:
            message = str(response)
        return any(pattern.search(message) for pattern in cls._RECIPIENT_NOT_FOUND_PATTERNS)

    @staticmethod
    def _temporary_reason(code: int) -> VerificationReason:
        if code in (450, 451, 452):
            return VerificationReason.GREYLISTED
        return VerificationReason.SMTP_TEMPORARY_FAILURE

    @staticmethod
    def _close_smtp(smtp, connected: bool) -> None:
        if smtp is None:
            return
        if connected:
            try:
                smtp.quit()
            except Exception:
                pass
        try:
            smtp.close()
        except Exception:
            pass

    @staticmethod
    def _result(
        email: str,
        status: VerificationStatus,
        reason: VerificationReason,
        provider: MailboxProvider,
        is_role: bool,
        mx_hosts: List[str],
        smtp_code: Optional[int] = None,
    ) -> VerificationResult:
        return VerificationResult(
            email=email,
            status=status,
            reason=reason,
            mailbox_provider=provider,
            is_role_account=is_role,
            mx_records=mx_hosts,
            smtp_code=smtp_code,
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
    """Async verifier with per-domain and process-wide concurrency limits."""

    def __init__(
        self,
        sync_engine: Optional[IVerificationPipeline] = None,
        max_concurrent_per_provider: int = 5,
        max_concurrent: Optional[int] = None,
    ):
        if max_concurrent_per_provider < 1:
            raise ValueError("max_concurrent_per_provider must be at least 1")
        global_limit = (
            max_concurrent_per_provider
            if max_concurrent is None
            else max_concurrent
        )
        if global_limit < 1:
            raise ValueError("max_concurrent must be at least 1")

        self.sync_engine = sync_engine or VerificationEngine()
        self.max_concurrent_per_provider = max_concurrent_per_provider
        self.max_concurrent = global_limit
        self.provider_semaphores: Dict[str, asyncio.Semaphore] = {}
        self.global_semaphore = asyncio.Semaphore(global_limit)

    def _get_semaphore(self, domain: str) -> asyncio.Semaphore:
        if domain not in self.provider_semaphores:
            self.provider_semaphores[domain] = asyncio.Semaphore(
                self.max_concurrent_per_provider
            )
        return self.provider_semaphores[domain]

    async def verify_email_async(self, email: str) -> VerificationResult:
        domain = email.strip().lower().split("@")[-1]
        domain_semaphore = self._get_semaphore(domain)
        async with self.global_semaphore:
            async with domain_semaphore:
                loop = asyncio.get_running_loop()
                return await loop.run_in_executor(
                    None, self.sync_engine.verify, email
                )

    async def verify_batch_async(self, emails: List[str]) -> List[VerificationResult]:
        tasks = [self.verify_email_async(email) for email in emails]
        return await asyncio.gather(*tasks)
