"""Unit tests for DynamoDB Cache Store (Dual-Mode Caching)."""

import time
from unittest.mock import MagicMock
import pytest
from botocore.exceptions import ClientError

from kanga_route.cache.dynamodb import DynamoDBCacheStore
from kanga_route.models import (
    VerificationResult,
    VerificationStatus,
    VerificationReason,
    MailboxProvider,
)


def test_cache_get_miss():
    mock_table = MagicMock()
    mock_table.get_item.return_value = {}
    mock_resource = MagicMock()
    mock_resource.Table.return_value = mock_table

    store = DynamoDBCacheStore(boto3_resource=mock_resource)
    res = store.get("missing@example.com")
    assert res is None
    mock_table.get_item.assert_called_once_with(Key={"email": "missing@example.com"})


def test_cache_get_hit():
    mock_table = MagicMock()
    mock_table.get_item.return_value = {
        "Item": {
            "email": "user@example.com",
            "status": "Valid",
            "reason": "OK",
            "mailbox_provider": "Google Workspace",
            "is_role_account": False,
            "mx_records": ["aspmx.l.google.com"],
            "verified_at": "2026-08-06T00:00:00Z",
            "ttl": int(time.time()) + 3600,
        }
    }
    mock_resource = MagicMock()
    mock_resource.Table.return_value = mock_table

    store = DynamoDBCacheStore(boto3_resource=mock_resource)
    res = store.get("user@example.com")
    assert res is not None
    assert res.email == "user@example.com"
    assert res.status == VerificationStatus.VALID
    assert res.mailbox_provider == MailboxProvider.GOOGLE_WORKSPACE


def test_cache_get_expired_ttl():
    mock_table = MagicMock()
    mock_table.get_item.return_value = {
        "Item": {
            "email": "expired@example.com",
            "status": "Valid",
            "reason": "OK",
            "mailbox_provider": "Other / Self-Hosted",
            "is_role_account": False,
            "ttl": int(time.time()) - 100,  # Expired
        }
    }
    mock_resource = MagicMock()
    mock_resource.Table.return_value = mock_table

    store = DynamoDBCacheStore(boto3_resource=mock_resource)
    res = store.get("expired@example.com")
    assert res is None


def test_cache_put_success():
    mock_table = MagicMock()
    mock_resource = MagicMock()
    mock_resource.Table.return_value = mock_table

    store = DynamoDBCacheStore(boto3_resource=mock_resource)
    result = VerificationResult(
        email="test@company.com",
        status=VerificationStatus.VALID,
        reason=VerificationReason.OK,
    )
    ok = store.put(result, ttl_seconds=3600)
    assert ok is True
    mock_table.put_item.assert_called_once()


def test_ensure_table_exists_creates_table_when_missing():
    mock_table = MagicMock()
    mock_table.load.side_effect = ClientError(
        {"Error": {"Code": "ResourceNotFoundException"}}, "Load"
    )
    mock_resource = MagicMock()
    mock_resource.Table.return_value = mock_table

    store = DynamoDBCacheStore(boto3_resource=mock_resource)
    store.ensure_table_exists()
    mock_resource.create_table.assert_called_once()
