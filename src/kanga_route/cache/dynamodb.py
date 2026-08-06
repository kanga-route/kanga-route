"""DynamoDB implementation of ICacheStore with dual-mode support (ADR 0002).

Supports local sidecar container (dynamodb-local) or AWS cloud DynamoDB.
"""

import os
import time
from typing import Optional
import boto3
from botocore.exceptions import ClientError

from kanga_route.contracts import ICacheStore
from kanga_route.models import (
    VerificationResult,
    VerificationStatus,
    VerificationReason,
    MailboxProvider,
)


class DynamoDBCacheStore(ICacheStore):
    """Dual-mode DynamoDB verification result cache store."""

    def __init__(
        self,
        table_name: Optional[str] = None,
        endpoint_url: Optional[str] = None,
        region_name: Optional[str] = None,
        boto3_resource=None,
    ):
        self.table_name = (
            table_name
            or os.getenv("DYNAMODB_TABLE_NAME")
            or "KangaRouteCache"
        )
        self.endpoint_url = (
            endpoint_url
            if endpoint_url is not None
            else os.getenv("DYNAMODB_ENDPOINT_URL")
        )
        self.region_name = (
            region_name or os.getenv("AWS_REGION") or "us-east-1"
        )

        if boto3_resource:
            self.dynamodb = boto3_resource
        else:
            kwargs = {"region_name": self.region_name}
            if self.endpoint_url:
                kwargs["endpoint_url"] = self.endpoint_url
            self.dynamodb = boto3.resource("dynamodb", **kwargs)

        self.table = self.dynamodb.Table(self.table_name)

    def ensure_table_exists(self) -> None:
        """Helper to create table if running against a fresh local/cloud instance."""
        try:
            self.table.load()
        except ClientError as e:
            if e.response["Error"]["Code"] == "ResourceNotFoundException":
                self.dynamodb.create_table(
                    TableName=self.table_name,
                    KeySchema=[
                        {"AttributeName": "email", "KeyType": "HASH"},
                    ],
                    AttributeDefinitions=[
                        {"AttributeName": "email", "AttributeType": "S"},
                    ],
                    BillingMode="PAY_PER_REQUEST",
                )
                # Wait until table exists
                self.table.meta.client.get_waiter("table_exists").wait(
                    TableName=self.table_name
                )
            else:
                raise e

    def get(self, email: str) -> Optional[VerificationResult]:
        """Fetch cached VerificationResult by email address."""
        if not email:
            return None

        email_clean = email.strip().lower()
        try:
            response = self.table.get_item(Key={"email": email_clean})
            item = response.get("Item")
            if not item:
                return None

            # Check TTL if present
            ttl = item.get("ttl")
            if ttl and int(ttl) < int(time.time()):
                return None

            return VerificationResult(
                email=item["email"],
                status=VerificationStatus(item["status"]),
                reason=VerificationReason(item["reason"]),
                mailbox_provider=MailboxProvider(
                    item.get("mailbox_provider", MailboxProvider.OTHER.value)
                ),
                is_role_account=bool(item.get("is_role_account", False)),
                mx_records=item.get("mx_records", []),
                verified_at=item.get("verified_at", ""),
            )
        except ClientError:
            return None

    def put(
        self, result: VerificationResult, ttl_seconds: Optional[int] = 86400 * 30
    ) -> bool:
        """Store VerificationResult in DynamoDB with optional TTL (default 30 days)."""
        if not result or not result.email:
            return False

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

        if ttl_seconds:
            item["ttl"] = int(time.time()) + ttl_seconds

        try:
            self.table.put_item(Item=item)
            return True
        except ClientError:
            return False
