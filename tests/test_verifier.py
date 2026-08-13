"""Unit tests for Kanga-Route models, 4-layer verification engine, and async rate limiting."""

import asyncio
import socket
import threading
import time
from unittest.mock import MagicMock, patch

import dns.exception
import dns.resolver
import pytest

from kanga_route.models import (
    VerificationResult,
    VerificationStatus,
    VerificationReason,
    MailboxProvider,
)
from kanga_route.engine.verifier import (
    SyntaxAndRoleStage,
    BlocklistStage,
    DNSStage,
    SMTPSocketStage,
    VerificationEngine,
    AsyncVerificationEngine,
)


def test_verification_result_to_dict_is_json_compatible():
    result = VerificationResult(
        email="admin@company.com",
        status=VerificationStatus.VALID,
        reason=VerificationReason.OK,
        mailbox_provider=MailboxProvider.GOOGLE_WORKSPACE,
        is_role_account=True,
        mx_records=["aspmx.l.google.com"],
        verified_at="2026-08-06T00:00:00Z",
    )

    assert result.to_dict() == {
        "email": "admin@company.com",
        "status": "Valid",
        "reason": "OK",
        "mailbox_provider": "Google Workspace",
        "is_role_account": True,
        "mx_records": ["aspmx.l.google.com"],
        "smtp_code": None,
        "verified_at": "2026-08-06T00:00:00Z",
    }


def test_syntax_stage_invalid():
    stage = SyntaxAndRoleStage()
    res = stage.evaluate("not-an-email")
    assert res is not None
    assert res.status == VerificationStatus.INVALID
    assert res.reason == VerificationReason.SYNTAX_ERROR

    res_empty = stage.evaluate("")
    assert res_empty is not None
    assert res_empty.status == VerificationStatus.INVALID


def test_syntax_stage_valid_and_role():
    stage = SyntaxAndRoleStage()
    ctx = {}
    res = stage.evaluate("support@mycompany.com", context=ctx)
    assert res is None  # Stage passes to next layer
    assert ctx.get("is_role_account") is True

    ctx_personal = {}
    res2 = stage.evaluate("john.doe@mycompany.com", context=ctx_personal)
    assert res2 is None
    assert ctx_personal.get("is_role_account") is False


def test_blocklist_stage():
    stage = BlocklistStage()
    ctx = {"is_role_account": False}
    res = stage.evaluate("test@mailinator.com", context=ctx)
    assert res is not None
    assert res.status == VerificationStatus.INVALID
    assert res.reason == VerificationReason.DISPOSABLE

    res_pass = stage.evaluate("test@realcompany.com", context=ctx)
    assert res_pass is None


@pytest.mark.parametrize("domain", ["fmail.co.uk", "list.ru", "netcourrier.com"])
def test_blocklist_does_not_reject_legitimate_mailbox_domains(domain):
    result = BlocklistStage().evaluate(
        f"user@{domain}", context={"is_role_account": False}
    )

    assert result is None

def test_dns_stage_fingerprinting():
    mock_resolver = MagicMock()

    # Mock Google Workspace MX
    google_mx = MagicMock()
    google_mx.preference = 10
    google_mx.exchange = "aspmx.l.google.com."
    mock_resolver.resolve.return_value = [google_mx]

    stage = DNSStage(resolver=mock_resolver)
    ctx = {}
    res = stage.evaluate("user@domain.com", context=ctx)
    assert res is None
    assert ctx["mailbox_provider"] == MailboxProvider.GOOGLE_WORKSPACE
    assert "aspmx.l.google.com" in ctx["mx_hosts"]


def test_dns_stage_authoritative_no_mx_and_no_a_is_invalid():
    mock_resolver = MagicMock()
    mock_resolver.resolve.side_effect = [
        dns.resolver.NoAnswer(),
        dns.resolver.NXDOMAIN(),
    ]

    stage = DNSStage(resolver=mock_resolver)
    ctx = {"is_role_account": False}
    res = stage.evaluate("user@invalid-domain-xyz.com", context=ctx)

    assert res is not None
    assert res.status == VerificationStatus.INVALID
    assert res.reason == VerificationReason.NO_MX
    assert mock_resolver.resolve.call_args_list == [
        (("invalid-domain-xyz.com", "MX"),),
        (("invalid-domain-xyz.com", "A"),),
    ]


def test_dns_stage_authoritative_nxdomain_is_invalid_without_fallback():
    mock_resolver = MagicMock()
    mock_resolver.resolve.side_effect = dns.resolver.NXDOMAIN()

    result = DNSStage(resolver=mock_resolver).evaluate(
        "user@does-not-exist.example",
        context={"is_role_account": False},
    )

    assert result is not None
    assert result.status == VerificationStatus.INVALID
    assert result.reason == VerificationReason.NO_MX
    mock_resolver.resolve.assert_called_once_with("does-not-exist.example", "MX")


def test_dns_stage_transient_a_fallback_failure_is_unknown():
    mock_resolver = MagicMock()
    mock_resolver.resolve.side_effect = [
        dns.resolver.NoAnswer(),
        dns.exception.Timeout(),
        dns.resolver.NoAnswer(),
    ]

    result = DNSStage(resolver=mock_resolver).evaluate(
        "user@address-fallback.example",
        context={"is_role_account": False},
    )

    assert result is not None
    assert result.status == VerificationStatus.UNKNOWN
    assert result.reason == VerificationReason.DNS_TIMEOUT
    assert mock_resolver.resolve.call_args_list == [
        (("address-fallback.example", "MX"),),
        (("address-fallback.example", "A"),),
        (("address-fallback.example", "AAAA"),),
    ]


def test_dns_stage_accepts_aaaa_only_implicit_mx_domain():
    mock_resolver = MagicMock()
    mock_resolver.resolve.side_effect = [
        dns.resolver.NoAnswer(),
        dns.resolver.NoAnswer(),
        [MagicMock()],
    ]
    context = {"is_role_account": False}

    result = DNSStage(resolver=mock_resolver).evaluate(
        "user@ipv6-mail.example", context=context
    )

    assert result is None
    assert context["mx_hosts"] == ["ipv6-mail.example"]
    assert mock_resolver.resolve.call_args_list == [
        (("ipv6-mail.example", "MX"),),
        (("ipv6-mail.example", "A"),),
        (("ipv6-mail.example", "AAAA"),),
    ]


@pytest.mark.parametrize(
    ("dns_error", "expected_reason"),
    [
        (dns.exception.Timeout(), VerificationReason.DNS_TIMEOUT),
        (dns.resolver.NoNameservers(), VerificationReason.DNS_ERROR),
    ],
)
def test_dns_stage_transient_failure_is_unknown(dns_error, expected_reason):
    mock_resolver = MagicMock()
    mock_resolver.resolve.side_effect = dns_error

    result = DNSStage(resolver=mock_resolver).evaluate(
        "user@temporarily-unavailable.com",
        context={"is_role_account": False},
    )

    assert result is not None
    assert result.status == VerificationStatus.UNKNOWN
    assert result.reason == expected_reason
    mock_resolver.resolve.assert_called_once_with(
        "temporarily-unavailable.com", "MX"
    )


def test_smtp_stage_defaults_use_reserved_invalid_domains():
    with patch("kanga_route.engine.verifier.os.getenv", return_value=None):
        stage = SMTPSocketStage()

    assert stage.helo_domain == "verifier.kanga-route.invalid"
    assert stage.from_email == "verify@kanga-route.invalid"


@patch("smtplib.SMTP")
def test_smtp_stage_valid_with_starttls_and_catchall_check(mock_smtp_cls):
    mock_smtp = MagicMock()
    mock_smtp_cls.return_value = mock_smtp
    mock_smtp.connect.return_value = (220, b"Banner")
    mock_smtp.has_extn.return_value = True
    mock_smtp.mail.return_value = (250, b"OK")
    # Return 550 for dummy check (not catch-all), 250 for real email
    mock_smtp.rcpt.side_effect = [(550, b"User unknown"), (250, b"OK")]

    stage = SMTPSocketStage(
        helo_domain="verifier.kanga-route.com",
        from_email="verify@kanga-route.com",
        check_catch_all=True,
    )
    ctx = {
        "mx_hosts": ["mail.company.com"],
        "mailbox_provider": MailboxProvider.OTHER,
        "is_role_account": False,
    }

    res = stage.evaluate("user@company.com", context=ctx)
    assert res is not None
    assert res.status == VerificationStatus.VALID
    assert res.reason == VerificationReason.OK
    assert res.smtp_code == 250
    mock_smtp.starttls.assert_called_once()


@patch("smtplib.SMTP")
def test_smtp_stage_catch_all_detected(mock_smtp_cls):
    mock_smtp = MagicMock()
    mock_smtp_cls.return_value = mock_smtp
    mock_smtp.connect.return_value = (220, b"Banner")
    mock_smtp.has_extn.return_value = False
    mock_smtp.mail.return_value = (250, b"OK")
    # Return 250 for dummy check -> Catch-All
    mock_smtp.rcpt.return_value = (250, b"OK")

    stage = SMTPSocketStage(check_catch_all=True)
    ctx = {
        "mx_hosts": ["mail.catchall-domain.com"],
        "mailbox_provider": MailboxProvider.OTHER,
        "is_role_account": False,
    }

    res = stage.evaluate("randomuser@catchall-domain.com", context=ctx)
    assert res is not None
    assert res.status == VerificationStatus.CATCH_ALL
    assert res.reason == VerificationReason.OK


@patch("smtplib.SMTP")
def test_smtp_stage_user_not_found(mock_smtp_cls):
    mock_smtp = MagicMock()
    mock_smtp_cls.return_value = mock_smtp
    mock_smtp.connect.return_value = (220, b"Banner")
    mock_smtp.has_extn.return_value = False
    mock_smtp.mail.return_value = (250, b"OK")
    # Return 550 for dummy check, 550 for real email
    mock_smtp.rcpt.side_effect = [(550, b"User unknown"), (550, b"User unknown")]

    stage = SMTPSocketStage(check_catch_all=True)
    ctx = {
        "mx_hosts": ["mail.company.com"],
        "mailbox_provider": MailboxProvider.OTHER,
        "is_role_account": False,
    }

    res = stage.evaluate("nonexistent@company.com", context=ctx)
    assert res is not None
    assert res.status == VerificationStatus.INVALID
    assert res.reason == VerificationReason.USER_NOT_FOUND
    assert res.smtp_code == 550


@patch("smtplib.SMTP")
def test_smtp_stage_tries_next_mx_after_connection_timeout(mock_smtp_cls):
    first_smtp = MagicMock()
    first_smtp.connect.side_effect = socket.timeout("primary timed out")
    second_smtp = MagicMock()
    second_smtp.connect.return_value = (220, b"Banner")
    second_smtp.has_extn.return_value = False
    second_smtp.mail.return_value = (250, b"OK")
    second_smtp.rcpt.return_value = (250, b"OK")
    mock_smtp_cls.side_effect = [first_smtp, second_smtp]

    result = SMTPSocketStage(check_catch_all=False).evaluate(
        "user@company.com",
        context={
            "mx_hosts": ["mx1.company.com", "mx2.company.com"],
            "mailbox_provider": MailboxProvider.OTHER,
            "is_role_account": False,
        },
    )

    assert result is not None
    assert result.status == VerificationStatus.VALID
    assert first_smtp.connect.call_args.args == ("mx1.company.com", 25)
    assert second_smtp.connect.call_args.args == ("mx2.company.com", 25)
    first_smtp.close.assert_called_once()
    second_smtp.quit.assert_called_once()
    second_smtp.close.assert_called_once()


@patch("smtplib.SMTP")
def test_smtp_stage_tries_next_mx_after_transient_mail_response(mock_smtp_cls):
    first_smtp = MagicMock()
    first_smtp.connect.return_value = (220, b"Banner")
    first_smtp.has_extn.return_value = False
    first_smtp.mail.return_value = (451, b"Try again later")
    second_smtp = MagicMock()
    second_smtp.connect.return_value = (220, b"Banner")
    second_smtp.has_extn.return_value = False
    second_smtp.mail.return_value = (250, b"OK")
    second_smtp.rcpt.return_value = (250, b"OK")
    mock_smtp_cls.side_effect = [first_smtp, second_smtp]

    result = SMTPSocketStage(check_catch_all=False).evaluate(
        "user@company.com",
        context={
            "mx_hosts": ["mx1.company.com", "mx2.company.com"],
            "mailbox_provider": MailboxProvider.OTHER,
            "is_role_account": False,
        },
    )

    assert result is not None
    assert result.status == VerificationStatus.VALID
    first_smtp.rcpt.assert_not_called()
    first_smtp.quit.assert_called_once()
    first_smtp.close.assert_called_once()
    second_smtp.rcpt.assert_called_once_with("user@company.com")
    second_smtp.quit.assert_called_once()
    second_smtp.close.assert_called_once()


@patch("smtplib.SMTP")
def test_smtp_stage_tries_next_mx_after_transient_recipient_response(
    mock_smtp_cls,
):
    first_smtp = MagicMock()
    first_smtp.connect.return_value = (220, b"Banner")
    first_smtp.has_extn.return_value = False
    first_smtp.mail.return_value = (250, b"OK")
    first_smtp.rcpt.return_value = (451, b"Try again later")
    second_smtp = MagicMock()
    second_smtp.connect.return_value = (220, b"Banner")
    second_smtp.has_extn.return_value = False
    second_smtp.mail.return_value = (250, b"OK")
    second_smtp.rcpt.return_value = (250, b"OK")
    mock_smtp_cls.side_effect = [first_smtp, second_smtp]

    result = SMTPSocketStage(check_catch_all=False).evaluate(
        "user@company.com",
        context={
            "mx_hosts": ["mx1.company.com", "mx2.company.com"],
            "mailbox_provider": MailboxProvider.OTHER,
            "is_role_account": False,
        },
    )

    assert result is not None
    assert result.status == VerificationStatus.VALID
    first_smtp.quit.assert_called_once()
    first_smtp.close.assert_called_once()
    second_smtp.quit.assert_called_once()
    second_smtp.close.assert_called_once()


@patch("smtplib.SMTP")
def test_smtp_stage_ambiguous_5xx_is_unknown(mock_smtp_cls):
    mock_smtp = MagicMock()
    mock_smtp_cls.return_value = mock_smtp
    mock_smtp.connect.return_value = (220, b"Banner")
    mock_smtp.has_extn.return_value = False
    mock_smtp.mail.return_value = (250, b"OK")
    mock_smtp.rcpt.return_value = (550, b"Rejected by policy")

    result = SMTPSocketStage(check_catch_all=False).evaluate(
        "user@company.com",
        context={
            "mx_hosts": ["mail.company.com"],
            "mailbox_provider": MailboxProvider.OTHER,
            "is_role_account": False,
        },
    )

    assert result is not None
    assert result.status == VerificationStatus.UNKNOWN
    assert result.reason == VerificationReason.SMTP_REJECTED
    assert result.smtp_code == 550
    mock_smtp.quit.assert_called_once()
    mock_smtp.close.assert_called_once()


def test_async_verification_engine():
    mock_engine = MagicMock(spec=VerificationEngine)
    mock_engine.verify.return_value = VerificationResult(
        email="test@domain.com",
        status=VerificationStatus.VALID,
        reason=VerificationReason.OK,
    )

    async_engine = AsyncVerificationEngine(sync_engine=mock_engine, max_concurrent_per_provider=2)
    results = asyncio.run(async_engine.verify_batch_async(["test1@domain.com", "test2@domain.com"]))

    assert len(results) == 2
    assert results[0].status == VerificationStatus.VALID
    assert mock_engine.verify.call_count == 2


class _ConcurrencyTrackingEngine:
    def __init__(self):
        self._lock = threading.Lock()
        self.active = 0
        self.peak_active = 0

    def verify(self, email):
        with self._lock:
            self.active += 1
            self.peak_active = max(self.peak_active, self.active)
        try:
            time.sleep(0.05)
            return VerificationResult(
                email=email,
                status=VerificationStatus.VALID,
                reason=VerificationReason.OK,
            )
        finally:
            with self._lock:
                self.active -= 1


def test_async_verification_engine_enforces_global_cap_across_domains():
    tracking_engine = _ConcurrencyTrackingEngine()
    async_engine = AsyncVerificationEngine(
        sync_engine=tracking_engine,
        max_concurrent_per_provider=6,
        max_concurrent=2,
    )
    emails = [f"user@domain-{index}.example" for index in range(6)]

    results = asyncio.run(async_engine.verify_batch_async(emails))

    assert len(results) == 6
    assert tracking_engine.peak_active == 2
