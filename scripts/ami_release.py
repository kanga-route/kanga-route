#!/usr/bin/env python3
"""Extract Packer AMIs and maintain the human-readable AMI catalog."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

AMI_PATTERN = re.compile(r"ami-[0-9a-f]{17}")
REGION_PATTERN = re.compile(r"[a-z]{2}(?:-gov)?-[a-z]+-\d")
SHA_PATTERN = re.compile(r"[0-9a-f]{40}")
VISIBILITIES = {"candidate", "shared", "public"}


def extract_ami(manifest_path: Path, region: str) -> str:
    """Return the one AMI produced for ``region`` by a Packer manifest."""
    _require_region(region)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    candidates: list[str] = []
    for build in manifest.get("builds", []):
        artifact_id = build.get("artifact_id", "")
        artifact_region, separator, ami_id = artifact_id.partition(":")
        if separator and artifact_region == region and AMI_PATTERN.fullmatch(ami_id):
            candidates.append(ami_id)
    if len(candidates) != 1:
        raise ValueError(
            f"expected exactly one AMI for {region}, found {len(candidates)}"
        )
    return candidates[0]


def record_release(
    catalog_path: Path,
    document_path: Path,
    *,
    ami_id: str,
    region: str,
    visibility: str,
    source_sha: str,
    build_run_url: str,
    published_at: str,
) -> None:
    """Replace the current catalog entry for a region and render Markdown."""
    _validate_release(
        ami_id=ami_id,
        region=region,
        visibility=visibility,
        source_sha=source_sha,
        build_run_url=build_run_url,
        published_at=published_at,
    )
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    if catalog.get("schema_version") != 1 or not isinstance(
        catalog.get("images"), list
    ):
        raise ValueError("unsupported AMI catalog schema")

    release = {
        "region": region,
        "ami_id": ami_id,
        "visibility": visibility,
        "source_sha": source_sha,
        "build_run_url": build_run_url,
        "published_at": published_at,
    }
    images = [image for image in catalog["images"] if image.get("region") != region]
    images.append(release)
    catalog["images"] = sorted(images, key=lambda image: image["region"])

    catalog_path.write_text(
        json.dumps(catalog, indent=2, sort_keys=False) + "\n", encoding="utf-8"
    )
    document_path.write_text(render_catalog(catalog), encoding="utf-8")


def render_catalog(catalog: dict[str, Any]) -> str:
    """Render catalog JSON as the public Markdown release index."""
    rows = []
    for image in catalog["images"]:
        short_sha = image["source_sha"][:12]
        rows.append(
            "| `{region}` | `{ami_id}` | {visibility} | "
            "[`{short_sha}`]({run_url}) | `{published_at}` |".format(
                region=image["region"],
                ami_id=image["ami_id"],
                visibility=image["visibility"],
                short_sha=short_sha,
                run_url=image["build_run_url"],
                published_at=image["published_at"],
            )
        )
    table = "\n".join(rows) if rows else "| _None yet_ | — | — | — | — |"
    return f"""# Kanga-Route AMI catalog

This page shows the newest Kanga-Route appliance image recorded for each AWS
region. AMI IDs are region-specific. Check **Availability** before using one:

- **public** images can be launched by any AWS account;
- **shared** images can be launched only by explicitly approved AWS accounts;
- **candidate** images remain private to the build account for smoke testing.

| AWS region | AMI ID | Availability | Source build | Recorded at (UTC) |
| --- | --- | --- | --- | --- |
{table}

The `Build and Deploy Kanga-Route AMI` workflow generates this table from
[`ami-catalog.json`](ami-catalog.json). Do not edit either catalog file by hand.
The workflow builds one private candidate, reports its exact ID for staging,
then promotes that same image only after the `ami-publication` environment is
approved. It never rebuilds between testing and publication.

Use a **public** entry directly in the
[AWS appliance deployment guide](aws-appliance-deployment.md). To use a
**shared** entry, first confirm that its owner granted your AWS account launch
permission. A **candidate** entry is not an end-user release.
"""


def _validate_release(**release: str) -> None:
    if not AMI_PATTERN.fullmatch(release["ami_id"]):
        raise ValueError("invalid AMI ID")
    _require_region(release["region"])
    if release["visibility"] not in VISIBILITIES:
        raise ValueError("invalid visibility")
    if not SHA_PATTERN.fullmatch(release["source_sha"]):
        raise ValueError("source SHA must contain 40 lowercase hexadecimal characters")
    parsed_url = urlparse(release["build_run_url"])
    if parsed_url.scheme != "https" or parsed_url.netloc != "github.com":
        raise ValueError("build run URL must be an HTTPS github.com URL")
    timestamp = release["published_at"]
    if not timestamp.endswith("Z"):
        raise ValueError("published_at must be a UTC timestamp ending in Z")
    datetime.fromisoformat(timestamp.removesuffix("Z") + "+00:00")


def _require_region(region: str) -> None:
    if not REGION_PATTERN.fullmatch(region):
        raise ValueError(f"invalid AWS region: {region}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    extract = subparsers.add_parser("extract")
    extract.add_argument("--manifest", type=Path, required=True)
    extract.add_argument("--region", required=True)

    record = subparsers.add_parser("record")
    record.add_argument("--catalog", type=Path, required=True)
    record.add_argument("--document", type=Path, required=True)
    record.add_argument("--ami-id", required=True)
    record.add_argument("--region", required=True)
    record.add_argument("--visibility", choices=sorted(VISIBILITIES), required=True)
    record.add_argument("--source-sha", required=True)
    record.add_argument("--build-run-url", required=True)
    record.add_argument("--published-at", required=True)
    return parser


def main() -> None:
    args = _parser().parse_args()
    if args.command == "extract":
        print(extract_ami(args.manifest, args.region))
        return
    record_release(
        args.catalog,
        args.document,
        ami_id=args.ami_id,
        region=args.region,
        visibility=args.visibility,
        source_sha=args.source_sha,
        build_run_url=args.build_run_url,
        published_at=args.published_at,
    )


if __name__ == "__main__":
    main()
