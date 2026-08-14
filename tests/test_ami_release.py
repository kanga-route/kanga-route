import json
from pathlib import Path

import pytest

from scripts.ami_release import extract_ami, record_release, render_catalog


REPOSITORY = Path(__file__).parents[1]


def test_extract_ami_returns_exact_region_candidate(tmp_path: Path) -> None:
    manifest = tmp_path / "packer-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "builds": [
                    {
                        "artifact_id": "us-east-1:ami-0123456789abcdef0",
                        "builder_type": "amazon-ebs",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    assert extract_ami(manifest, "us-east-1") == "ami-0123456789abcdef0"


def test_extract_ami_rejects_ambiguous_manifest(tmp_path: Path) -> None:
    manifest = tmp_path / "packer-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "builds": [
                    {"artifact_id": "us-east-1:ami-0123456789abcdef0"},
                    {"artifact_id": "us-east-1:ami-0fedcba9876543210"},
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="exactly one AMI"):
        extract_ami(manifest, "us-east-1")


def test_record_release_replaces_region_and_renders_document(tmp_path: Path) -> None:
    catalog = tmp_path / "ami-catalog.json"
    document = tmp_path / "ami-catalog.md"
    catalog.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "images": [
                    {
                        "region": "us-east-1",
                        "ami_id": "ami-0123456789abcdef0",
                        "visibility": "candidate",
                        "source_sha": "a" * 40,
                        "build_run_url": "https://github.com/example/project/actions/runs/1",
                        "published_at": "2026-08-13T00:00:00Z",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    record_release(
        catalog,
        document,
        ami_id="ami-0fedcba9876543210",
        region="us-east-1",
        visibility="public",
        source_sha="b" * 40,
        build_run_url="https://github.com/example/project/actions/runs/2",
        published_at="2026-08-14T00:00:00Z",
    )

    data = json.loads(catalog.read_text(encoding="utf-8"))
    assert len(data["images"]) == 1
    assert data["images"][0]["ami_id"] == "ami-0fedcba9876543210"
    rendered = document.read_text(encoding="utf-8")
    assert "`ami-0fedcba9876543210`" in rendered
    assert "| public |" in rendered
    assert "ami-0123456789abcdef0" not in rendered


def test_checked_in_catalog_document_is_current() -> None:
    catalog = json.loads(
        (REPOSITORY / "docs/ami-catalog.json").read_text(encoding="utf-8")
    )
    document = (REPOSITORY / "docs/ami-catalog.md").read_text(encoding="utf-8")

    assert document == render_catalog(catalog)


def test_packer_payload_allowlist_contains_every_runtime_python_module() -> None:
    """Prevent a valid-but-unbootable AMI when a package file is added."""
    template = (REPOSITORY / "packer/kanga-route.pkr.hcl").read_text(
        encoding="utf-8"
    )
    missing = [
        path.relative_to(REPOSITORY).as_posix()
        for path in sorted((REPOSITORY / "src/kanga_route").rglob("*.py"))
        if path.relative_to(REPOSITORY).as_posix() not in template
    ]

    assert missing == []
