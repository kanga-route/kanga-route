"""DynamoDB cache with explicit local and managed-cloud modes (ADR 0002)."""

import logging
import os
import time
from typing import Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from kanga_route.contracts import ICacheStore
from kanga_route.models import (
    MailboxProvider,
    VerificationReason,
    VerificationResult,
    VerificationStatus,
)

logger = logging.getLogger(__name__)


class CacheError(RuntimeError):
    """Raised when the cache cannot complete a required operation."""


class DynamoDBCacheStore(ICacheStore):
    """DynamoDB verification-result cache for local or managed AWS use."""

    def __init__(
        self,
        table_name: Optional[str] = None,
        endpoint_url: Optional[str] = None,
        region_name: Optional[str] = None,
        boto3_resource=None,
        use_local: Optional[bool] = None,
        default_ttl_seconds: Optional[int] = None,
    ):
        self.table_name = (
            table_name
            or os.getenv("DYNAMODB_TABLE_NAME")
            or "KangaRouteCache"
        )
        if use_local is None:
            configured_mode = os.getenv("USE_LOCAL_DB", "true").strip().lower()
            if configured_mode not in {"true", "false"}:
                raise ValueError("USE_LOCAL_DB must be either true or false")
            self.use_local = configured_mode == "true"
        else:
            self.use_local = use_local
        self.region_name = (
            region_name or os.getenv("AWS_REGION") or "us-east-1"
        )
        self.default_ttl_seconds = (
            default_ttl_seconds
            if default_ttl_seconds is not None
            else int(os.getenv("CACHE_TTL_DAYS", "30")) * 86400
        )
        if self.default_ttl_seconds <= 0:
            raise ValueError("CACHE_TTL_DAYS must define a positive cache lifetime")

        if self.use_local:
            self.endpoint_url = (
                endpoint_url
                or os.getenv("DYNAMODB_ENDPOINT_URL")
                or "http://localhost:8000"
            )
        else:
            # Cloud mode must use the AWS endpoint and credential chain/instance role.
            self.endpoint_url = None

        if boto3_resource is not None:
            self.dynamodb = boto3_resource
        else:
            kwargs = {"region_name": self.region_name}
            if self.use_local:
                kwargs.update(
                    {
                        "endpoint_url": self.endpoint_url,
                        "aws_access_key_id": "fakeMyKeyId",
                        "aws_secret_access_key": "fakeSecretAccessKey",
                    }
                )
            self.dynamodb = boto3.resource("dynamodb", **kwargs)

        self.table = self.dynamodb.Table(self.table_name)

    def ensure_table_exists(self) -> None:
        """Create the table if needed and enable expiry on its ttl attribute."""
        try:
            self.table.load()
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") != (
                "ResourceNotFoundException"
            ):
                raise CacheError(
                    f"Unable to describe DynamoDB table {self.table_name}"
                ) from exc

            try:
                self.table = self.dynamodb.create_table(
                    TableName=self.table_name,
                    KeySchema=[
                        {"AttributeName": "email", "KeyType": "HASH"},
                    ],
                    AttributeDefinitions=[
                        {"AttributeName": "email", "AttributeType": "S"},
                    ],
                    BillingMode="PAY_PER_REQUEST",
                )
                self.table.meta.client.get_waiter("table_exists").wait(
                    TableName=self.table_name
                )
            except (BotoCoreError, ClientError) as create_exc:
                raise CacheError(
                    f"Unable to create DynamoDB table {self.table_name}"
                ) from create_exc
        except BotoCoreError as exc:
            raise CacheError(
                f"Unable to connect to DynamoDB table {self.table_name}"
            ) from exc

        self._ensure_ttl_enabled()

    def _ensure_ttl_enabled(self) -> None:
        client = self.table.meta.client
        try:
            response = client.describe_time_to_live(
                TableName=self.table_name
            )
            description = response.get("TimeToLiveDescription", {})
            status = description.get("TimeToLiveStatus")
            attribute = description.get("AttributeName")
            if status in ("ENABLED", "ENABLING") and attribute == "ttl":
                return
            client.update_time_to_live(
                TableName=self.table_name,
                TimeToLiveSpecification={
                    "Enabled": True,
                    "AttributeName": "ttl",
                },
            )
        except (AttributeError, TypeError):
            # Lightweight test doubles may not implement the TTL control plane.
            return
        except (BotoCoreError, ClientError) as exc:
            if self.use_local:
                logger.warning(
                    "DynamoDB Local did not enable server-side TTL; "
                    "expired entries will still be ignored at read time: %s",
                    exc,
                )
                return
            raise CacheError(
                f"Unable to enable TTL on DynamoDB table {self.table_name}"
            ) from exc

    def get(self, email: str) -> Optional[VerificationResult]:
        """Fetch a non-expired VerificationResult by normalized email."""
        if not email:
            return None

        email_clean = email.strip().lower()
        try:
            response = self.table.get_item(Key={"email": email_clean})
        except (BotoCoreError, ClientError) as exc:
            raise CacheError(f"Cache read failed for {email_clean}") from exc

        item = response.get("Item")
        if not item:
            return None

        ttl = item.get("ttl")
        if ttl is not None and int(ttl) <= int(time.time()):
            try:
                self.table.delete_item(Key={"email": email_clean})
            except (BotoCoreError, ClientError):
                logger.warning("Could not remove expired cache entry %s", email_clean)
            return None

        try:
            result_data = {
                "email": item["email"],
                "status": VerificationStatus(item["status"]),
                "reason": VerificationReason(item["reason"]),
                "mailbox_provider": MailboxProvider(
                    item.get(
                        "mailbox_provider",
                        MailboxProvider.OTHER.value,
                    )
                ),
                "is_role_account": bool(item.get("is_role_account", False)),
                "mx_records": item.get("mx_records", []),
                "smtp_code": item.get("smtp_code"),
            }
            if item.get("verified_at"):
                result_data["verified_at"] = item["verified_at"]
            return VerificationResult(**result_data)
        except (KeyError, TypeError, ValueError) as exc:
            raise CacheError(
                f"Cache entry for {email_clean} is invalid"
            ) from exc

    def put(
        self,
        result: VerificationResult,
        ttl_seconds: Optional[int] = None,
    ) -> bool:
        """Store a definitive verification result with a DynamoDB TTL."""
        if not result or not result.email:
            raise CacheError("Cannot cache a result without an email address")
        if result.status == VerificationStatus.UNKNOWN:
            raise CacheError("Unknown verification results must not be cached")

        effective_ttl = (
            self.default_ttl_seconds
            if ttl_seconds is None
            else ttl_seconds
        )
        if effective_ttl <= 0:
            raise CacheError("Cache TTL must be positive")

        email_clean = result.email.strip().lower()
        item = {
            "email": email_clean,
            "status": result.status.value,
            "reason": result.reason.value,
            "mailbox_provider": result.mailbox_provider.value,
            "is_role_account": result.is_role_account,
            "mx_records": result.mx_records,
            "verified_at": result.verified_at,
        }
        if result.smtp_code is not None:
            item["smtp_code"] = result.smtp_code
        if effective_ttl > 0:
            item["ttl"] = int(time.time()) + effective_ttl

        try:
            self.table.put_item(Item=item)
        except (BotoCoreError, ClientError) as exc:
            raise CacheError(f"Cache write failed for {email_clean}") from exc
        return True
