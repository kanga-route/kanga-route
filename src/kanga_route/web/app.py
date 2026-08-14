"""Versioned HTTP API and static browser console."""

import asyncio
import json
import os
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Deque, Dict, Optional

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from kanga_route.application.single_verification import (
    CachePolicy,
    SingleVerificationError,
    SingleVerificationService,
)
from kanga_route.application.mail_advisory import MailAdvisoryService
from kanga_route.cache.dynamodb import DynamoDBCacheStore
from kanga_route.engine.verifier import VerificationEngine

STATIC_ROOT = Path(__file__).resolve().parent / "static"
MAX_REQUEST_BYTES = 1_024
MAX_ADVICE_REQUEST_BYTES = 32_768

PUBLIC_ERRORS = {
    "invalid_email": "Enter one complete email address.",
    "invalid_request": "The request was not valid.",
    "unsupported_media_type": "Send the request as JSON.",
    "request_too_large": "The request was too large.",
    "rate_limited": "Too many checks are running. Try again shortly.",
    "request_timeout": "The verification timed out. Try again later.",
    "cache_unavailable": "The verification cache is unavailable.",
    "configuration_invalid": "The appliance SMTP identity is not configured.",
    "verification_failed": "The verification could not be completed.",
}


class VerifyRequest(BaseModel):
    """Strict request envelope for one verification."""

    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=1, max_length=320)
    cache_policy: CachePolicy = CachePolicy.USE


class AdviceRequest(BaseModel):
    """Strict request envelope for cache-only recipient advice."""

    model_config = ConfigDict(extra="forbid")

    recipients: list[str] = Field(min_length=1, max_length=100)


class RequestLimiter:
    """Small in-memory per-client sliding-window limiter."""

    def __init__(self, requests_per_minute: int):
        self.requests_per_minute = max(1, requests_per_minute)
        self.requests: Dict[str, Deque[float]] = defaultdict(deque)
        self.lock = asyncio.Lock()

    async def allow(self, client_key: str) -> bool:
        now = time.monotonic()
        cutoff = now - 60.0
        async with self.lock:
            recent = self.requests[client_key]
            while recent and recent[0] <= cutoff:
                recent.popleft()
            if len(recent) >= self.requests_per_minute:
                return False
            recent.append(now)
            return True


def error_response(code: str, status_code: int) -> JSONResponse:
    """Return a stable error envelope without request data or exceptions."""
    return JSONResponse(
        {"error": {"code": code, "message": PUBLIC_ERRORS[code]}},
        status_code=status_code,
    )


async def _run_with_timeout(
    service: SingleVerificationService,
    payload: VerifyRequest,
    semaphore: asyncio.Semaphore,
    timeout_seconds: float,
):
    def release_after_completion(completed_task: asyncio.Task) -> None:
        semaphore.release()
        if not completed_task.cancelled():
            completed_task.exception()

    await semaphore.acquire()
    task = asyncio.create_task(
        asyncio.to_thread(
            service.verify,
            payload.email,
            payload.cache_policy,
        )
    )

    try:
        outcome = await asyncio.wait_for(
            asyncio.shield(task),
            timeout=timeout_seconds,
        )
    except BaseException:
        if task.done():
            semaphore.release()
        else:
            task.add_done_callback(release_after_completion)
        raise
    else:
        semaphore.release()
        return outcome


def create_app(
    service: Optional[SingleVerificationService] = None,
    advisory_service: Optional[MailAdvisoryService] = None,
    *,
    timeout_seconds: Optional[float] = None,
    max_concurrent: Optional[int] = None,
    requests_per_minute: Optional[int] = None,
    advice_requests_per_minute: Optional[int] = None,
) -> FastAPI:
    """Create the same-origin API and browser application."""
    configured_timeout = timeout_seconds or float(
        os.getenv("WEB_VERIFY_TIMEOUT_SECONDS", "45")
    )
    configured_concurrency = max_concurrent or int(
        os.getenv("WEB_MAX_CONCURRENT", "2")
    )
    configured_rate = requests_per_minute or int(
        os.getenv("WEB_REQUESTS_PER_MINUTE", "30")
    )
    configured_advice_rate = advice_requests_per_minute or int(
        os.getenv("MAIL_ADVICE_REQUESTS_PER_MINUTE", "600")
    )
    if configured_timeout <= 0:
        raise ValueError("WEB_VERIFY_TIMEOUT_SECONDS must be positive")
    if configured_concurrency <= 0:
        raise ValueError("WEB_MAX_CONCURRENT must be positive")
    if configured_rate <= 0:
        raise ValueError("WEB_REQUESTS_PER_MINUTE must be positive")
    if configured_advice_rate <= 0:
        raise ValueError("MAIL_ADVICE_REQUESTS_PER_MINUTE must be positive")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if service is None:
            cache_store = DynamoDBCacheStore()
            await asyncio.to_thread(cache_store.ensure_table_exists)
            app.state.verification_service = SingleVerificationService(
                cache_store=cache_store,
                engine=VerificationEngine(),
            )
        else:
            app.state.verification_service = service
            cache_store = getattr(service, "cache_store", None)
        app.state.advisory_service = advisory_service
        if app.state.advisory_service is None and cache_store is not None:
            app.state.advisory_service = MailAdvisoryService(cache_store)
        yield

    app = FastAPI(
        title="Kanga-Route operator console",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.state.verification_semaphore = asyncio.Semaphore(
        configured_concurrency
    )
    app.state.request_limiter = RequestLimiter(configured_rate)
    app.state.advice_request_limiter = RequestLimiter(configured_advice_rate)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; base-uri 'none'; frame-ancestors 'none'; "
            "form-action 'self'; object-src 'none'"
        )
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        return response

    @app.get("/healthz")
    async def health() -> Dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/v1/verify")
    async def verify(request: Request):
        content_type = request.headers.get("content-type", "")
        if content_type.partition(";")[0].strip().lower() != "application/json":
            return error_response("unsupported_media_type", 415)

        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                if int(content_length) > MAX_REQUEST_BYTES:
                    return error_response("request_too_large", 413)
            except ValueError:
                return error_response("invalid_request", 400)

        body = await request.body()
        if len(body) > MAX_REQUEST_BYTES:
            return error_response("request_too_large", 413)

        try:
            decoded = json.loads(body.decode("utf-8"))
            payload = VerifyRequest.model_validate(decoded)
        except (UnicodeDecodeError, json.JSONDecodeError, ValidationError):
            return error_response("invalid_request", 422)

        client_key = request.client.host if request.client else "local"
        if not await app.state.request_limiter.allow(client_key):
            return error_response("rate_limited", 429)

        try:
            outcome = await _run_with_timeout(
                app.state.verification_service,
                payload,
                app.state.verification_semaphore,
                configured_timeout,
            )
        except asyncio.TimeoutError:
            return error_response("request_timeout", 504)
        except SingleVerificationError as exc:
            status_code = 422 if exc.code == "invalid_email" else 503
            public_code = (
                exc.code
                if exc.code in PUBLIC_ERRORS
                else "verification_failed"
            )
            return error_response(public_code, status_code)
        except Exception:
            return error_response("verification_failed", 503)

        return JSONResponse(
            {
                "result": outcome.result.to_dict(),
                "cache": {"status": outcome.cache_status.value},
            }
        )

    @app.post("/api/v1/advice")
    async def advise(request: Request):
        content_type = request.headers.get("content-type", "")
        if content_type.partition(";")[0].strip().lower() != "application/json":
            return error_response("unsupported_media_type", 415)

        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                if int(content_length) > MAX_ADVICE_REQUEST_BYTES:
                    return error_response("request_too_large", 413)
            except ValueError:
                return error_response("invalid_request", 400)

        body = await request.body()
        if len(body) > MAX_ADVICE_REQUEST_BYTES:
            return error_response("request_too_large", 413)
        try:
            decoded = json.loads(body.decode("utf-8"))
            payload = AdviceRequest.model_validate(decoded)
        except (UnicodeDecodeError, json.JSONDecodeError, ValidationError):
            return error_response("invalid_request", 422)

        client_key = request.client.host if request.client else "local"
        if not await app.state.advice_request_limiter.allow(client_key):
            return error_response("rate_limited", 429)

        advisory = app.state.advisory_service
        if advisory is None:
            return JSONResponse(
                {
                    "fail_open": True,
                    "recipients": [
                        {
                            "email": email.strip().lower(),
                            "action": "allow",
                            "source": "unavailable",
                            "result": None,
                        }
                        for email in payload.recipients
                    ],
                }
            )

        try:
            outcome = await asyncio.to_thread(advisory.advise, payload.recipients)
        except Exception:
            return JSONResponse(
                {
                    "fail_open": True,
                    "recipients": [
                        {
                            "email": email.strip().lower(),
                            "action": "allow",
                            "source": "unavailable",
                            "result": None,
                        }
                        for email in payload.recipients
                    ],
                }
            )
        return JSONResponse(outcome.to_dict())

    app.mount(
        "/assets",
        StaticFiles(directory=STATIC_ROOT),
        name="assets",
    )

    @app.get("/", response_class=FileResponse)
    async def index():
        return FileResponse(STATIC_ROOT / "index.html")

    return app


def main() -> None:
    """Run the browser service inside its loopback-published container."""
    uvicorn.run(
        create_app(),
        host=os.getenv("WEB_BIND_HOST", "0.0.0.0"),
        port=int(os.getenv("WEB_PORT", "8080")),
        access_log=False,
        log_level=os.getenv("WEB_LOG_LEVEL", "info"),
        proxy_headers=False,
        server_header=False,
    )


if __name__ == "__main__":
    main()
