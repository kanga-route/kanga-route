"""CLI entrypoint for Kanga-Route verification engine.

Orchestrates CRM contact fetching -> Cache lookup -> Async Verification Engine execution -> Cache storage -> CRM batch writeback.
"""

import sys
import logging
import argparse
import asyncio
from typing import Optional, List

from kanga_route.crm.hubspot import HubSpotClient
from kanga_route.cache.dynamodb import DynamoDBCacheStore
from kanga_route.engine.verifier import VerificationEngine, AsyncVerificationEngine
from kanga_route.contracts import ICRMClient, ICacheStore, IVerificationPipeline
from kanga_route.models import VerificationResult

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("kanga_route.main")


def run_pipeline(
    crm_client: ICRMClient,
    cache_store: ICacheStore,
    engine: IVerificationPipeline,
    batch_size: int = 100,
) -> int:
    """Executes a single batch verification run across components."""
    logger.info(f"Starting Kanga-Route batch verification run (limit={batch_size})...")

    # 1. Ensure cache store is initialized
    if isinstance(cache_store, DynamoDBCacheStore):
        try:
            cache_store.ensure_table_exists()
        except Exception as e:
            logger.warning(f"Could not verify/create DynamoDB table: {e}")

    # 2. Fetch contacts from CRM
    contacts = crm_client.fetch_unverified_contacts(limit=batch_size)
    if not contacts:
        logger.info("No unverified contacts found. Processing complete.")
        return 0

    logger.info(f"Retrieved {len(contacts)} contact(s) to evaluate.")
    results: List[VerificationResult] = []

    # 3. Process each contact with cache lookup & async engine execution
    cache_hits = 0
    cache_misses = 0
    contacts_to_verify = []

    for contact in contacts:
        email = contact.email
        if not email:
            continue

        cached_result = cache_store.get(email)
        if cached_result:
            cache_hits += 1
            cached_result.contact_id = contact.id
            results.append(cached_result)
        else:
            cache_misses += 1
            contacts_to_verify.append(contact)

    if contacts_to_verify:
        async_engine = AsyncVerificationEngine(sync_engine=engine)
        emails = [c.email for c in contacts_to_verify]
        
        async def _run_async_verifications():
            return await async_engine.verify_batch_async(emails)

        verified_results = asyncio.run(_run_async_verifications())

        for contact, res in zip(contacts_to_verify, verified_results):
            res.contact_id = contact.id
            cache_store.put(res)
            results.append(res)

    logger.info(
        f"Evaluation complete. Cache hits: {cache_hits}, Engine verifications: {cache_misses}."
    )

    # 4. Batch update CRM writebacks
    if results:
        success = crm_client.batch_update_verification_results(results)
        if success:
            logger.info(f"Successfully updated {len(results)} contact(s) in CRM.")
        else:
            logger.error("Failed to perform complete batch writeback to CRM.")

    return len(results)


def main():
    parser = argparse.ArgumentParser(
        description="Kanga-Route Containerized Verification Engine CLI"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Maximum number of contacts to evaluate in one run",
    )
    args = parser.parse_args()

    crm = HubSpotClient()
    cache = DynamoDBCacheStore()
    engine = VerificationEngine()

    processed = run_pipeline(crm, cache, engine, batch_size=args.batch_size)
    logger.info(f"Finished processing {processed} contacts.")
    sys.exit(0)


if __name__ == "__main__":
    main()
