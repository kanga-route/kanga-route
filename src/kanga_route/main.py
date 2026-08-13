"""Kanga-Route verification pipeline and CLI entrypoint."""

import argparse
import asyncio
import logging
import os
import time
from typing import List, Optional, Sequence

from kanga_route.cache.dynamodb import CacheError, DynamoDBCacheStore
from kanga_route.contracts import ICacheStore, ICRMClient, IVerificationPipeline
from kanga_route.crm.hubspot import HubSpotClient, HubSpotError
from kanga_route.engine.verifier import AsyncVerificationEngine, VerificationEngine
from kanga_route.models import VerificationResult, VerificationStatus

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("kanga_route.main")


class PipelineError(RuntimeError):
    """Raised when a required pipeline step cannot be completed safely."""


def _validate_runtime_configuration() -> None:
    """Fail before touching external services when required identity is absent."""
    if not os.getenv("HUBSPOT_ACCESS_TOKEN", "").strip():
        raise ValueError("HUBSPOT_ACCESS_TOKEN is required")

    database_mode = os.getenv("USE_LOCAL_DB", "true").strip().lower()
    if database_mode not in {"true", "false"}:
        raise ValueError("USE_LOCAL_DB must be either true or false")

    helo_domain = os.getenv(
        "SMTP_HELO_DOMAIN", "verifier.example.invalid"
    ).strip().lower().rstrip(".")
    from_email = os.getenv(
        "SMTP_MAIL_FROM", "verify@example.invalid"
    ).strip().lower()
    from_local, separator, from_domain = from_email.rpartition("@")
    if (
        not helo_domain
        or helo_domain.endswith(".invalid")
        or "." not in helo_domain
        or any(character.isspace() for character in helo_domain)
    ):
        raise ValueError(
            "SMTP_HELO_DOMAIN must be a configured public hostname"
        )
    if (
        separator != "@"
        or from_email.count("@") != 1
        or not from_local
        or not from_domain
        or "." not in from_domain
        or from_domain.endswith(".invalid")
        or any(character.isspace() for character in from_email)
    ):
        raise ValueError(
            "SMTP_MAIL_FROM must be a configured sender address"
        )


def _ensure_cache_ready(
    cache_store: ICacheStore,
    attempts: int = 5,
    delay_seconds: float = 1.0,
) -> None:
    if not isinstance(cache_store, DynamoDBCacheStore):
        return

    last_error: Optional[BaseException] = None
    for attempt in range(max(1, attempts)):
        try:
            cache_store.ensure_table_exists()
            return
        except CacheError as exc:
            last_error = exc
            if attempt + 1 < max(1, attempts):
                time.sleep(max(0.0, delay_seconds))

    raise PipelineError("DynamoDB cache is not ready") from last_error


def run_pipeline(
    crm_client: ICRMClient,
    cache_store: ICacheStore,
    engine: IVerificationPipeline,
    batch_size: int = 100,
    cache_ready_attempts: int = 5,
    cache_ready_delay_seconds: float = 1.0,
) -> int:
    """Execute one verification batch or raise on an incomplete run."""
    if batch_size <= 0:
        raise ValueError("batch_size must be greater than zero")
    if batch_size > 10_000:
        raise ValueError("batch_size cannot exceed HubSpot's 10,000-result search cap")

    logger.info(
        "Starting Kanga-Route batch verification run (limit=%s)...",
        batch_size,
    )
    _ensure_cache_ready(
        cache_store,
        attempts=cache_ready_attempts,
        delay_seconds=cache_ready_delay_seconds,
    )

    contacts = crm_client.fetch_unverified_contacts(limit=batch_size)
    if not contacts:
        logger.info("No contacts currently require verification.")
        return 0

    logger.info("Retrieved %s contact(s) to evaluate.", len(contacts))
    results: List[VerificationResult] = []
    contacts_to_verify = []
    cache_hits = 0

    for contact in contacts:
        try:
            cached_result = cache_store.get(contact.email)
        except Exception as exc:
            raise PipelineError(
                f"Cache lookup failed for {contact.email}"
            ) from exc

        if (
            cached_result is not None
            and cached_result.status != VerificationStatus.UNKNOWN
        ):
            cache_hits += 1
            cached_result.contact_id = contact.id
            results.append(cached_result)
        else:
            contacts_to_verify.append(contact)

    if contacts_to_verify:
        async_engine = AsyncVerificationEngine(sync_engine=engine)
        emails = [contact.email for contact in contacts_to_verify]
        verified_results = asyncio.run(
            async_engine.verify_batch_async(emails)
        )

        if len(verified_results) != len(contacts_to_verify):
            raise PipelineError("Verification engine returned an incomplete batch")

        for contact, result in zip(contacts_to_verify, verified_results):
            result.contact_id = contact.id
            if result.status != VerificationStatus.UNKNOWN:
                try:
                    cached = cache_store.put(result)
                except Exception as exc:
                    raise PipelineError(
                        f"Cache write failed for {result.email}"
                    ) from exc
                if cached is False:
                    raise PipelineError(
                        f"Cache rejected result for {result.email}"
                    )
            results.append(result)

    logger.info(
        "Evaluation complete. Cache hits: %s, engine verifications: %s.",
        cache_hits,
        len(contacts_to_verify),
    )

    if results:
        try:
            success = crm_client.batch_update_verification_results(results)
        except Exception as exc:
            raise PipelineError("HubSpot batch writeback failed") from exc
        if not success:
            raise PipelineError("HubSpot batch writeback was incomplete")
        logger.info("Successfully updated %s contact(s) in HubSpot.", len(results))

    return len(results)


def _positive_batch_size(value: str) -> int:
    try:
        batch_size = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("batch size must be an integer") from exc
    if not 1 <= batch_size <= 10_000:
        raise argparse.ArgumentTypeError(
            "batch size must be between 1 and 10,000"
        )
    return batch_size


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Kanga-Route HubSpot email verification engine"
    )
    parser.add_argument(
        "--batch-size",
        type=_positive_batch_size,
        default=os.getenv("BATCH_SIZE", "100"),
        help="Maximum contacts to evaluate in one run (1-10,000)",
    )
    args = parser.parse_args(argv)

    try:
        _validate_runtime_configuration()
        processed = run_pipeline(
            HubSpotClient(),
            DynamoDBCacheStore(),
            VerificationEngine(),
            batch_size=args.batch_size,
        )
    except (CacheError, HubSpotError, PipelineError, ValueError) as exc:
        logger.error("Verification run failed: %s", exc)
        return 1
    except Exception:
        logger.exception("Verification run failed unexpectedly")
        return 1

    logger.info("Finished processing %s contact(s).", processed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
