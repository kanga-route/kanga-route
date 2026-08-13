"""Unit tests for dual-mode DynamoDB caching."""

import time
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from kanga_route.cache.dynamodb import CacheError, DynamoDBCacheStore
from kanga_route.models import (
    MailboxProvider,
    VerificationReason,
    VerificationResult,
    VerificationStatus,
)


def _store_with_table(table):
    resource = MagicMock()
    resource.Table.return_value = table
    return DynamoDBCacheStore(boto3_resource=resource), resource


def test_cache_get_miss():
    table = MagicMock()
    table.get_item.return_value = {}
    store, _ = _store_with_table(table)

    assert store.get(" Missing@Example.com ") is None
    table.get_item.assert_called_once_with(
        Key={"email": "missing@example.com"}
    )


def test_cache_get_hit_preserves_result_metadata():
    table = MagicMock()
    table.get_item.return_value = {
        "Item": {
            "email": "user@example.com",
            "status": "Valid",
            "reason": "OK",
            "mailbox_provider": "Google Workspace",
            "is_role_account": False,
            "mx_records": ["aspmx.l.google.com"],
            "smtp_code": 250,
            "verified_at": "2026-08-06T00:00:00Z",
            "ttl": int(time.time()) + 3600,
        }
    }
    store, _ = _store_with_table(table)

    result = store.get("user@example.com")

    assert result is not None
    assert result.status == VerificationStatus.VALID
    assert result.mailbox_provider == MailboxProvider.GOOGLE_WORKSPACE
    assert result.smtp_code == 250


def test_cache_get_expired_ttl_removes_item():
    table = MagicMock()
    table.get_item.return_value = {
        "Item": {
            "email": "expired@example.com",
            "status": "Valid",
            "reason": "OK",
            "ttl": int(time.time()) - 100,
        }
    }
    store, _ = _store_with_table(table)

    assert store.get("expired@example.com") is None
    table.delete_item.assert_called_once_with(
        Key={"email": "expired@example.com"}
    )


def test_cache_get_surfaces_dynamodb_error():
    table = MagicMock()
    table.get_item.side_effect = ClientError(
        {"Error": {"Code": "InternalServerError"}},
        "GetItem",
    )
    store, _ = _store_with_table(table)

    with pytest.raises(CacheError, match="Cache read failed"):
        store.get("user@example.com")


def test_cache_put_success_adds_ttl():
    table = MagicMock()
    store, _ = _store_with_table(table)
    result = VerificationResult(
        email="Test@Company.com",
        status=VerificationStatus.VALID,
        reason=VerificationReason.OK,
        smtp_code=250,
    )

    assert store.put(result, ttl_seconds=3600) is True

    item = table.put_item.call_args.kwargs["Item"]
    assert item["email"] == "test@company.com"
    assert item["smtp_code"] == 250
    assert item["ttl"] > int(time.time())


def test_cache_refuses_unknown_results():
    table = MagicMock()
    store, _ = _store_with_table(table)
    result = VerificationResult(
        email="retry@company.com",
        status=VerificationStatus.UNKNOWN,
        reason=VerificationReason.TIMEOUT,
    )

    with pytest.raises(CacheError, match="must not be cached"):
        store.put(result)


def test_local_mode_uses_local_endpoint_and_signing_credentials(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "must-not-be-used")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "must-not-be-used")

    with patch("kanga_route.cache.dynamodb.boto3.resource") as resource:
        DynamoDBCacheStore(
            use_local=True,
            endpoint_url="http://dynamodb:8000",
        )

    kwargs = resource.call_args.kwargs
    assert kwargs["endpoint_url"] == "http://dynamodb:8000"
    assert kwargs["aws_access_key_id"] == "fakeMyKeyId"
    assert kwargs["aws_secret_access_key"] == "fakeSecretAccessKey"


def test_cache_rejects_ambiguous_database_mode(monkeypatch):
    monkeypatch.setenv("USE_LOCAL_DB", "tru")

    with pytest.raises(ValueError, match="USE_LOCAL_DB"):
        DynamoDBCacheStore(boto3_resource=MagicMock())


def test_cloud_mode_ignores_endpoint_and_uses_aws_credential_chain():
    with patch("kanga_route.cache.dynamodb.boto3.resource") as resource:
        store = DynamoDBCacheStore(
            use_local=False,
            endpoint_url="http://must-not-be-used:8000",
        )

    kwargs = resource.call_args.kwargs
    assert store.endpoint_url is None
    assert "endpoint_url" not in kwargs
    assert "aws_access_key_id" not in kwargs
    assert "aws_secret_access_key" not in kwargs


def test_ensure_table_exists_creates_table_and_enables_ttl():
    original_table = MagicMock()
    original_table.load.side_effect = ClientError(
        {"Error": {"Code": "ResourceNotFoundException"}},
        "Load",
    )
    created_table = MagicMock()
    created_table.meta.client.describe_time_to_live.return_value = {
        "TimeToLiveDescription": {"TimeToLiveStatus": "DISABLED"}
    }
    resource = MagicMock()
    resource.Table.return_value = original_table
    resource.create_table.return_value = created_table
    store = DynamoDBCacheStore(boto3_resource=resource)

    store.ensure_table_exists()

    resource.create_table.assert_called_once()
    created_table.meta.client.update_time_to_live.assert_called_once_with(
        TableName="KangaRouteCache",
        TimeToLiveSpecification={
            "Enabled": True,
            "AttributeName": "ttl",
        },
    )


def test_cloud_ttl_enable_failure_is_explicit():
    table = MagicMock()
    table.meta.client.describe_time_to_live.side_effect = ClientError(
        {"Error": {"Code": "AccessDeniedException"}},
        "DescribeTimeToLive",
    )
    store, _ = _store_with_table(table)
    store.use_local = False

    with pytest.raises(CacheError, match="enable TTL"):
        store.ensure_table_exists()


def test_cache_requires_positive_default_ttl():
    with pytest.raises(ValueError, match="positive cache lifetime"):
        DynamoDBCacheStore(boto3_resource=MagicMock(), default_ttl_seconds=0)
