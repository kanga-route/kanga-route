"""Kanga-Route composition root and batch CLI entrypoint."""

import argparse
import logging
import os
from typing import Optional, Sequence

from kanga_route.adapters import create_adapter
from kanga_route.application.batch import PipelineError, run_pipeline
from kanga_route.cache.dynamodb import CacheError, DynamoDBCacheStore
from kanga_route.configuration import validate_smtp_identity
from kanga_route.contracts import AdapterError, IVerificationAdapter
from kanga_route.engine.verifier import VerificationEngine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("kanga_route.main")


def _validate_runtime_configuration(
    adapter: Optional[IVerificationAdapter] = None,
) -> None:
    """Validate shared settings and only the selected adapter's settings."""
    database_mode = os.getenv("USE_LOCAL_DB", "true").strip().lower()
    if database_mode not in {"true", "false"}:
        raise ValueError("USE_LOCAL_DB must be either true or false")

    validate_smtp_identity()
    (adapter or create_adapter()).validate_configuration()


def _positive_batch_size(value: str) -> int:
    try:
        batch_size = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("batch size must be an integer") from exc
    if batch_size < 1:
        raise argparse.ArgumentTypeError("batch size must be greater than zero")
    return batch_size


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Kanga-Route product-neutral email verification engine"
    )
    parser.add_argument(
        "--batch-size",
        type=_positive_batch_size,
        default=os.getenv("BATCH_SIZE", "100"),
        help="Maximum records to evaluate in one run",
    )
    args = parser.parse_args(argv)

    try:
        adapter = create_adapter()
        _validate_runtime_configuration(adapter)
        processed = run_pipeline(
            adapter,
            DynamoDBCacheStore(),
            VerificationEngine(),
            batch_size=args.batch_size,
        )
    except (AdapterError, CacheError, PipelineError, ValueError) as exc:
        logger.error("Verification run failed: %s", exc)
        return 1
    except Exception:
        logger.exception("Verification run failed unexpectedly")
        return 1

    logger.info("Finished processing %s record(s).", processed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
