"""Command-line entrypoint for the single-verification application service."""

import argparse
import json
from typing import Optional, Sequence

from kanga_route.application.single_verification import (
    CachePolicy,
    SingleVerificationError,
    SingleVerificationService,
)
from kanga_route.cache.dynamodb import CacheError, DynamoDBCacheStore
from kanga_route.engine.verifier import VerificationEngine


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Verify one address and emit the same neutral envelope as the API."""
    parser = argparse.ArgumentParser(
        description="Verify one email address without a product integration"
    )
    parser.add_argument("email", help="Email address to verify")
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Ignore a definitive cached result",
    )
    args = parser.parse_args(argv)

    try:
        cache_store = DynamoDBCacheStore()
        cache_store.ensure_table_exists()
        service = SingleVerificationService(
            cache_store=cache_store,
            engine=VerificationEngine(),
        )
        outcome = service.verify(
            args.email,
            CachePolicy.REFRESH if args.refresh else CachePolicy.USE,
        )
    except SingleVerificationError as exc:
        parser.exit(1, f"Verification failed: {exc.code}\n")
    except (CacheError, ValueError):
        parser.exit(1, "Verification failed: configuration_unavailable\n")

    print(
        json.dumps(
            {
                "result": outcome.result.to_dict(),
                "cache": {"status": outcome.cache_status.value},
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
