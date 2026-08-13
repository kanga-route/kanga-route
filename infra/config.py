"""Pure configuration validation helpers for the Pulumi stack.

This module deliberately has no Pulumi or AWS imports so validation can be
unit-tested without evaluating the infrastructure program.
"""

from __future__ import annotations

import ipaddress
import re
from typing import Optional


_AMI_ID_PATTERN = re.compile(r"^ami-(?:[0-9a-f]{8}|[0-9a-f]{17})$")
_ACCOUNT_ID_PATTERN = re.compile(r"^[0-9]{12}$")
_DYNAMODB_TABLE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{3,255}$")
_PARTITION_PATTERN = re.compile(r"^[a-z0-9-]+$")
_REGION_PATTERN = re.compile(r"^[a-z]{2}(?:-gov)?-[a-z]+-[0-9]+$")


DYNAMODB_TABLE_ACTIONS = (
    "dynamodb:CreateTable",
    "dynamodb:DescribeTable",
    "dynamodb:DescribeTimeToLive",
    "dynamodb:GetItem",
    "dynamodb:PutItem",
    "dynamodb:UpdateTimeToLive",
)


def validate_ami_id(value: str) -> str:
    """Validate an explicitly selected EC2 AMI identifier."""

    candidate = value.strip() if value else ""
    if not _AMI_ID_PATTERN.fullmatch(candidate):
        raise ValueError(
            "amiId must be an explicit EC2 AMI ID such as "
            "ami-0123456789abcdef0; stock Ubuntu fallback is not supported"
        )
    return candidate


def validate_ssh_cidr(value: Optional[str]) -> Optional[str]:
    """Return a canonical restricted IPv4 CIDR, or None for no SSH."""

    if value is None:
        return None

    candidate = value.strip()
    if not candidate:
        raise ValueError("sshCidr must be omitted to disable SSH or set to an IPv4 CIDR")
    if "/" not in candidate:
        raise ValueError("sshCidr must use explicit IPv4 CIDR notation")

    try:
        network = ipaddress.ip_network(candidate, strict=True)
    except ValueError as exc:
        raise ValueError("sshCidr must be a canonical IPv4 CIDR") from exc

    if not isinstance(network, ipaddress.IPv4Network):
        raise ValueError("sshCidr currently supports IPv4 CIDRs only")
    if network.prefixlen == 0:
        raise ValueError("sshCidr must never allow 0.0.0.0/0")

    return network.with_prefixlen


def validate_dynamodb_table_name(value: str) -> str:
    """Validate a DynamoDB table name using AWS naming constraints."""

    candidate = value.strip() if value else ""
    if not _DYNAMODB_TABLE_NAME_PATTERN.fullmatch(candidate):
        raise ValueError(
            "dynamodbTableName must be 3-255 characters using letters, numbers, "
            "underscore, hyphen, or period"
        )
    return candidate


def build_dynamodb_table_arn(
    *, partition: str, region: str, account_id: str, table_name: str
) -> str:
    """Build the exact table ARN used by the instance's least-privilege policy."""

    if not _PARTITION_PATTERN.fullmatch(partition):
        raise ValueError("invalid AWS partition")
    if not _REGION_PATTERN.fullmatch(region):
        raise ValueError("invalid AWS region")
    if not _ACCOUNT_ID_PATTERN.fullmatch(account_id):
        raise ValueError("AWS account ID must contain exactly 12 digits")

    validated_table_name = validate_dynamodb_table_name(table_name)
    return (
        f"arn:{partition}:dynamodb:{region}:{account_id}:"
        f"table/{validated_table_name}"
    )


def build_dynamodb_policy_document(table_arn: str) -> dict:
    """Build a table-scoped IAM policy for cache and TTL operations."""

    if not table_arn.startswith("arn:") or ":dynamodb:" not in table_arn:
        raise ValueError("table_arn must be a DynamoDB ARN")

    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": list(DYNAMODB_TABLE_ACTIONS),
                "Resource": table_arn,
            }
        ],
    }
