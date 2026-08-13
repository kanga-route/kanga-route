"""HTTP and static-browser contract tests for the operator console."""

import time

from fastapi.testclient import TestClient

from kanga_route.application.single_verification import (
    CacheStatus,
    SingleVerificationError,
    SingleVerificationOutcome,
)
from kanga_route.models import (
    MailboxProvider,
    VerificationReason,
    VerificationResult,
    VerificationStatus,
)
from kanga_route.web.app import create_app


class StubService:
    def __init__(self, outcome=None, error=None, delay=0):
        self.calls = []
        self.delay = delay
        self.error = error
        self.outcome = outcome or _outcome()

    def verify(self, email, cache_policy):
        self.calls.append((email, cache_policy.value))
        if self.delay:
            time.sleep(self.delay)
        if self.error:
            raise self.error
        return self.outcome


def _outcome(status=VerificationStatus.VALID):
    return SingleVerificationOutcome(
        result=VerificationResult(
            email="person@example.com",
            status=status,
            reason=(
                VerificationReason.OK
                if status == VerificationStatus.VALID
                else VerificationReason.TIMEOUT
            ),
            mailbox_provider=MailboxProvider.GOOGLE_WORKSPACE,
            is_role_account=False,
            mx_records=["aspmx.l.google.com"],
            smtp_code=250 if status == VerificationStatus.VALID else None,
            verified_at="2026-08-13T20:00:00+00:00",
        ),
        cache_status=CacheStatus.MISS,
    )


def _client(service, **kwargs):
    return TestClient(create_app(service=service, **kwargs))


def test_browser_shell_is_self_contained_and_accessible():
    with _client(StubService()) as client:
        response = client.get("/")
        script = client.get("/assets/app.js")
        styles = client.get("/assets/app.css")

    assert response.status_code == 200
    assert "Single-address verification" in response.text
    assert 'class="skip-link"' in response.text
    assert 'aria-live="polite"' in response.text
    assert "Unknown</strong> and <strong>Catch-All" in response.text
    assert "https://" not in response.text
    assert script.status_code == 200
    assert "textContent" in script.text
    assert styles.status_code == 200
    assert "prefers-reduced-motion" in styles.text


def test_responses_include_closed_security_and_cache_headers():
    with _client(StubService()) as client:
        response = client.get("/")

    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert "default-src 'self'" in response.headers["content-security-policy"]


def test_versioned_api_returns_neutral_result_envelope():
    service = StubService()
    with _client(service) as client:
        response = client.post(
            "/api/v1/verify",
            json={"email": "Person@Example.com", "cache_policy": "refresh"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "result": {
            "email": "person@example.com",
            "status": "Valid",
            "reason": "OK",
            "mailbox_provider": "Google Workspace",
            "is_role_account": False,
            "mx_records": ["aspmx.l.google.com"],
            "smtp_code": 250,
            "verified_at": "2026-08-13T20:00:00+00:00",
        },
        "cache": {"status": "miss"},
    }
    assert service.calls == [("Person@Example.com", "refresh")]


def test_malformed_envelopes_never_reach_verifier():
    service = StubService()
    with _client(service) as client:
        responses = [
            client.post("/api/v1/verify", content="not-json"),
            client.post(
                "/api/v1/verify",
                json={"email": "person@example.com", "extra": True},
            ),
            client.post(
                "/api/v1/verify",
                content=b"x" * 1_025,
                headers={"content-type": "application/json"},
            ),
        ]

    assert [response.status_code for response in responses] == [415, 422, 413]
    assert service.calls == []


def test_invalid_email_is_safe_4xx_without_exception_detail():
    canary = "ADDRESS_CANARY"
    service = StubService(
        error=SingleVerificationError("invalid_email")
    )
    with _client(service) as client:
        response = client.post(
            "/api/v1/verify",
            json={"email": "not-an-email"},
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_email"
    assert canary not in response.text


def test_service_failures_are_sanitized():
    service = StubService(
        error=SingleVerificationError("verification_failed")
    )
    with _client(service) as client:
        response = client.post(
            "/api/v1/verify",
            json={"email": "person@example.com"},
        )

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "verification_failed",
            "message": "The verification could not be completed.",
        }
    }
    assert "person@example.com" not in response.text


def test_timeout_and_rate_limit_are_bounded():
    slow_service = StubService(delay=0.05)
    with _client(slow_service, timeout_seconds=0.01) as client:
        timeout_response = client.post(
            "/api/v1/verify",
            json={"email": "person@example.com"},
        )

    limited_service = StubService()
    with _client(limited_service, requests_per_minute=1) as client:
        first = client.post(
            "/api/v1/verify",
            json={"email": "person@example.com"},
        )
        second = client.post(
            "/api/v1/verify",
            json={"email": "person@example.com"},
        )

    assert timeout_response.status_code == 504
    assert timeout_response.json()["error"]["code"] == "request_timeout"
    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["error"]["code"] == "rate_limited"


def test_health_response_exposes_no_runtime_detail():
    with _client(StubService()) as client:
        response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
