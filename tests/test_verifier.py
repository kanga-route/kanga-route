"""Unit tests for Kanga-Route models, 4-layer verification engine, and async rate limiting."""

import asyncio
from unittest.mock import MagicMock, patch
import pytest

from kanga_route.models import (
    VerificationResult,
    VerificationStatus,
    VerificationReason,
    MailboxProvider,
    HubSpotContact,
)
from kanga_route.engine.verifier import (
    SyntaxAndRoleStage,
    BlocklistStage,
    DNSStage,
    SMTPSocketStage,
    VerificationEngine,
    AsyncVerificationEngine,
)


def test_verification_result_to_hubspot_properties():
    result = VerificationResult(
        email="admin@company.com",
        status=VerificationStatus.VALID,
        reason=VerificationReason.OK,
        mailbox_provider=MailboxProvider.GOOGLE_WORKSPACE,
        is_role_account=True,
        mx_records=["aspmx.l.google.com"],
        verified_at="2026-08-06T00:00:00Z",
    )
    props = result.to_hubspot_properties()
    assert props["email_verification_status"] == "Valid"
    assert props["email_verification_reason"] == "OK"
    assert props["mailbox_provider"] == "Google Workspace"
    assert props["is_role_account"] == "true"
    assert props["last_verified"] == "2026-08-06T00:00:00Z"


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


def test_dns_stage_no_mx():
    mock_resolver = MagicMock()
    mock_resolver.resolve.side_effect = Exception("No MX record")

    stage = DNSStage(resolver=mock_resolver)
    ctx = {"is_role_account": False}
    res = stage.evaluate("user@invalid-domain-xyz.com", context=ctx)
    assert res is not None
    assert res.status == VerificationStatus.INVALID
    assert res.reason == VerificationReason.NO_MX


@patch("smtplib.SMTP")
def test_smtp_stage_valid_with_starttls_and_catchall_check(mock_smtp_cls):
    mock_smtp = MagicMock()
    mock_smtp_cls.return_value = mock_smtp
    mock_smtp.connect.return_value = (220, b"Banner")
    mock_smtp.has_extn.return_value = True
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
