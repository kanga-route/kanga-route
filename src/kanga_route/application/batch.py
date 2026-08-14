"""Product-neutral batch verification orchestration."""

import asyncio
import logging
import time
from typing import List, Optional

from kanga_route.cache.dynamodb import CacheError, DynamoDBCacheStore
from kanga_route.contracts import (
    ICacheStore,
    IVerificationAdapter,
    IVerificationPipeline,
)
from kanga_route.engine.verifier import AsyncVerificationEngine
from kanga_route.models import VerificationOutcome, VerificationStatus

logger = logging.getLogger(__name__)


class PipelineError(RuntimeError):
    """Raised when a required pipeline step cannot be completed safely."""


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
    adapter: IVerificationAdapter,
    cache_store: ICacheStore,
    engine: IVerificationPipeline,
    batch_size: int = 100,
    cache_ready_attempts: int = 5,
    cache_ready_delay_seconds: float = 1.0,
) -> int:
    """Execute one neutral read/verify/write batch."""
    if batch_size <= 0:
        raise ValueError("batch_size must be greater than zero")
    capabilities = adapter.capabilities
    if not capabilities.can_read_targets or not capabilities.can_write_outcomes:
        raise PipelineError(
            f"Adapter {adapter.name!r} does not support batch read/write"
        )
    if batch_size > capabilities.max_batch_size:
        raise ValueError(
            f"batch_size cannot exceed adapter limit "
            f"{capabilities.max_batch_size:,}"
        )

    logger.info(
        "Starting Kanga-Route batch verification run "
        "(adapter=%s, limit=%s)...",
        adapter.name,
        batch_size,
    )
    _ensure_cache_ready(
        cache_store,
        attempts=cache_ready_attempts,
        delay_seconds=cache_ready_delay_seconds,
    )

    targets = adapter.fetch_targets(limit=batch_size)
    if not targets:
        logger.info("No records currently require verification.")
        return 0

    logger.info("Retrieved %s record(s) to evaluate.", len(targets))
    outcomes: List[VerificationOutcome] = []
    targets_to_verify = []
    cache_hits = 0

    for target in targets:
        try:
            cached_result = cache_store.get(target.email)
        except Exception as exc:
            raise PipelineError(
                f"Cache lookup failed for {target.email}"
            ) from exc

        if (
            cached_result is not None
            and cached_result.status != VerificationStatus.UNKNOWN
        ):
            cache_hits += 1
            outcomes.append(
                VerificationOutcome(target=target, result=cached_result)
            )
        else:
            targets_to_verify.append(target)

    if targets_to_verify:
        async_engine = AsyncVerificationEngine(sync_engine=engine)
        emails = [target.email for target in targets_to_verify]
        verified_results = asyncio.run(async_engine.verify_batch_async(emails))

        if len(verified_results) != len(targets_to_verify):
            raise PipelineError("Verification engine returned an incomplete batch")

        for target, result in zip(targets_to_verify, verified_results):
            if result.status != VerificationStatus.UNKNOWN:
                try:
                    cached = cache_store.put(result)
                except Exception as exc:
                    raise PipelineError(
                        f"Cache write failed for {result.email}"
                    ) from exc
                if cached is False:
                    raise PipelineError(f"Cache rejected result for {result.email}")
            outcomes.append(VerificationOutcome(target=target, result=result))

    logger.info(
        "Evaluation complete. Cache hits: %s, engine verifications: %s.",
        cache_hits,
        len(targets_to_verify),
    )

    try:
        success = adapter.write_outcomes(outcomes)
    except Exception as exc:
        raise PipelineError(
            f"Adapter {adapter.name!r} outcome write failed"
        ) from exc
    if not success:
        raise PipelineError(f"Adapter {adapter.name!r} outcome write was incomplete")
    logger.info(
        "Successfully wrote %s outcome(s) through adapter %s.",
        len(outcomes),
        adapter.name,
    )
    return len(outcomes)
