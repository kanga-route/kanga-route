"""Focused tests for the Pulumi stack's pure configuration boundary."""

import ast
from pathlib import Path

import pytest

from infra.config import (
    DYNAMODB_TABLE_ACTIONS,
    build_dynamodb_policy_document,
    build_dynamodb_table_arn,
    validate_ami_id,
    validate_dynamodb_table_name,
    validate_ssh_cidr,
)


ROOT = Path(__file__).resolve().parents[1]
INFRA_MAIN = ROOT / "infra" / "__main__.py"


@pytest.mark.parametrize(
    "ami_id",
    ["ami-1234abcd", "ami-0123456789abcdef0"],
)
def test_validate_ami_id_accepts_explicit_ec2_ids(ami_id):
    assert validate_ami_id(ami_id) == ami_id


@pytest.mark.parametrize(
    "ami_id",
    ["", "ubuntu-latest", "ami-xyz", "ami-0123456789abcdef"],
)
def test_validate_ami_id_rejects_missing_or_malformed_values(ami_id):
    with pytest.raises(ValueError, match="amiId"):
        validate_ami_id(ami_id)


def test_validate_ssh_cidr_disables_ssh_when_omitted():
    assert validate_ssh_cidr(None) is None


def test_validate_ssh_cidr_accepts_restricted_ipv4_network():
    assert validate_ssh_cidr("203.0.113.10/32") == "203.0.113.10/32"


@pytest.mark.parametrize(
    "cidr",
    ["0.0.0.0/0", "203.0.113.10", "203.0.113.10/24", "::/0"],
)
def test_validate_ssh_cidr_rejects_open_or_invalid_networks(cidr):
    with pytest.raises(ValueError, match="sshCidr"):
        validate_ssh_cidr(cidr)


def test_build_dynamodb_policy_is_table_scoped_and_includes_ttl():
    table_arn = build_dynamodb_table_arn(
        partition="aws",
        region="us-east-1",
        account_id="123456789012",
        table_name="KangaRouteCache",
    )

    policy = build_dynamodb_policy_document(table_arn)
    statement = policy["Statement"][0]

    assert statement["Resource"] == (
        "arn:aws:dynamodb:us-east-1:123456789012:table/KangaRouteCache"
    )
    assert statement["Resource"] != "*"
    assert set(statement["Action"]) == set(DYNAMODB_TABLE_ACTIONS)
    assert "dynamodb:DescribeTimeToLive" in statement["Action"]
    assert "dynamodb:UpdateTimeToLive" in statement["Action"]


@pytest.mark.parametrize("table_name", ["ab", "bad/table", "x" * 256])
def test_validate_dynamodb_table_name_rejects_invalid_names(table_name):
    with pytest.raises(ValueError, match="dynamodbTableName"):
        validate_dynamodb_table_name(table_name)


def test_infrastructure_program_has_no_ami_lookup_or_user_data():
    source = INFRA_MAIN.read_text(encoding="utf-8")
    tree = ast.parse(source)

    attributes = {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }
    keyword_names = {
        keyword.arg
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        for keyword in node.keywords
    }

    assert "get_ami" not in attributes
    assert "user_data" not in keyword_names
    assert "metadata_options" in keyword_names
    assert "root_block_device" in keyword_names


def test_infrastructure_program_requires_ami_and_imdsv2():
    source = INFRA_MAIN.read_text(encoding="utf-8")

    assert 'config.require("amiId")' in source
    assert 'http_tokens="required"' in source
    assert "http_put_response_hop_limit=2" in source
    assert "encrypted=True" in source
    assert "ingress=ssh_ingress" in source
    assert "cidr_blocks=[ssh_cidr]" in source
