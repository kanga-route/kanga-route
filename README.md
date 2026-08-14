![Kanga-Route Banner](banner.png)

# Kanga-Route

Kanga-Route is a self-hosted appliance for conservative email verification.
Its verification engine accepts an email address and returns product-neutral
evidence through a browser UI, HTTP API, CLI, or integration adapter. The core
does not require a CRM account and is designed to support products beyond any
single vendor.

HubSpot is the first shipped batch integration, not the boundary of the tool.
Its adapter pages contacts, sends their addresses through the same verification
engine, and writes five granular properties back to the original records.
Additional adapters can translate their own records and result formats without
adding product-specific behavior to the verification stages.

It does not send email message bodies.

## Delivery model

Docker is a supported deployment path and the canonical application payload.
Operators may run the Compose project directly and manage outbound TCP 25,
public/NAT addressing, PTR and forward DNS, SMTP identity, scheduling, and UI
exposure themselves. The AWS AMI packages that same containerized application
with a host control plane.

QCOW2 and OVA appliances, followed by Google Cloud raw-image and Azure fixed-VHD
imports, are planned as separately boot-tested release targets. A bootable ISO
is deferred until a bare-metal or air-gapped user establishes its installation,
hardware, update, recovery, and support requirements. See
[ADR 0005](docs/adr/0005-portable-distribution-from-one-container-payload.md)
and the [portable-delivery roadmap](docs/roadmap.md#milestone-5-portable-delivery).
Operators choosing the current source-built path should follow the
[user-managed Docker guide](docs/docker-deployment.md).

## MVP capabilities

- Conservative four-stage verification with catch-all detection, STARTTLS,
  multiple-MX failover, and a global concurrency cap.
- Safe classifications: transient DNS, SMTP, and policy failures stay
  `Unknown`; explicit evidence is required for `Invalid`.
- Product-neutral verification targets, outcomes, and JSON result envelopes.
- A stable adapter port and explicit registry that keep product authentication,
  limits, errors, and formatting outside shared orchestration and the engine.
- Single-address verification through the browser console, versioned API, or
  CLI without reading from or writing to a product integration.
- A HubSpot reference adapter with paging, bounded API retry, cooldown-aware
  re-verification, and exact contact-ID writebacks.
- DynamoDB Local for a zero-infrastructure cache, or managed DynamoDB through
  the EC2 instance role; both use a 30-day default TTL.
- A daily persistent systemd timer, manual `kanga-route` control plane,
  journald logs, and overlap protection.
- An opt-in browser console and versioned API for one address, published only
  on appliance loopback for SSM port forwarding.
- Cache-only, multi-recipient mail advice plus an opt-in fail-open Postfix
  reference policy service; neither performs live verification in a mail flow.
- A controlled AMI delivery pipeline that bakes one private candidate, promotes
  that exact image through an approval gate, and records it in a regional AMI
  catalog.

## Integration status

Kanga-Route separates verification from product-specific transport and
formatting. The current release supports:

- **Standalone verification:** one address at a time through the browser UI,
  `POST /api/v1/verify`, or `kanga-route-verify`.
- **HubSpot batch verification:** the first full read/write adapter and the
  reference implementation for future integrations.
- **Contributor extension points:** the neutral adapter port and registry are in
  place; the [roadmap](docs/roadmap.md) tracks CSV support, completion of the
  contract-test kit, and selection of the next API-backed product.
- **Optional mail advice:** `POST /api/v1/advice` and the Postfix reference
  service read cached evidence only and fail open on misses or failures.

An integration owns authentication, record retrieval, field mapping, and
writeback formatting. It should not change syntax, disposable-domain, DNS, SMTP,
cache, or classification behavior in the shared engine.

## Quick start

Start with the [AMI catalog](docs/ami-catalog.md). It shows the current image ID
for each region and whether that image is a private candidate, account-shared,
or public. Do not treat a `candidate` entry as an end-user release.

Maintainers run the `Build and Deploy Kanga-Route AMI` workflow from `master`.
It bakes a private candidate, exposes the exact AMI ID for smoke testing,
promotes the same image without rebuilding it, and updates the catalog. Shared
and public promotion pass through the protected `ami-publication` environment.
See the [AMI release workflow guide](docs/ami-release-workflow.md).

The bakery authenticates to AWS through GitHub Actions OIDC. Configure the
repository variable `AWS_AMI_BUILDER_ROLE_ARN` with the ARN of a dedicated
builder role. Its trust policy must restrict the audience to
`sts.amazonaws.com` and the subject to this repository's `master` branch.
Newer GitHub repositories use an immutable subject shaped like
`repo:OWNER@OWNER_ID/REPOSITORY@REPOSITORY_ID:ref:refs/heads/master`.
Retrieve the repository's current OIDC subject configuration through GitHub's
Actions OIDC API instead of committing concrete AWS account IDs, role ARNs,
owner IDs, or repository IDs. Do not configure long-lived AWS access-key
secrets for the workflow. The build verifies its caller identity before Packer
creates any resources.

The previously listed public AMI predates this MVP work. It is intentionally
not advertised as an MVP release image; use a candidate built from the current
commit.

Before the first real SMTP verification you must:

1. allocate an Elastic IP and align A, PTR, SPF, HELO, and envelope-from values;
2. obtain AWS outbound port 25 approval;
3. copy `.env.example` to `.env`, store it with mode `0600`, and replace
   the fail-safe `.invalid` SMTP placeholders; and
4. test one address through the CLI, browser UI, or versioned API.

To enable the current HubSpot batch integration, also create the five exact
contact properties, configure a private-app token, and start with a manual
smoke run using `sudo kanga-route run` before enabling its schedule.

Follow [the setup and operations guide](docs/setup.md) for exact property types,
Pulumi configuration, cache modes, schedules, and result semantics.

For a guided deployment into a new AWS account, use the
[beginner AWS appliance deployment guide](docs/aws-appliance-deployment.md) and
its companion
[CloudFormation template](cloudformation/kanga-route-appliance.yaml). The stack
creates a dedicated VPC with configurable CIDRs and a Cognito-protected HTTPS
path to the browser UI.

## Local development

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install --editable ".[dev]"
python -m pytest

docker compose config --quiet
docker compose build engine
docker compose run --rm --no-deps engine kanga-route-engine --help
docker compose up -d --wait dynamodb-local
docker compose --profile ui up -d --wait web
# Open http://127.0.0.1:8080/

docker run --rm --network host \
  --volume "$PWD:/workspace" \
  --workdir /workspace/browser-tests \
  mcr.microsoft.com/playwright:v1.62.1-noble@sha256:dcc5531e97840b9b5e794f2814476b21571c5124a3fca2267d73041f56e7580e \
  /bin/bash -lc 'npm ci && npm test'
```

A clean checkout does not require a secret `.env` merely to validate or build
the Compose project. A real SMTP probe requires a configured public SMTP
identity. The scheduled HubSpot integration additionally requires its private
app token; standalone verification does not.

## Documentation

- [Setup and operations](docs/setup.md)
- [AMI catalog](docs/ami-catalog.md)
- [AMI build and publication](docs/ami-release-workflow.md)
- [Beginner AWS and CloudFormation deployment](docs/aws-appliance-deployment.md)
- [Architecture](docs/architecture.md)
- [Browser console](docs/browser-console.md)
- [User-managed Docker deployment](docs/docker-deployment.md)
- [Integration authoring contract](docs/integration-authoring.md)
- [Optional mail-server advice](docs/mail-server-integration.md)
- [HubSpot user story and workflows](docs/hubspot-user-story.md)
- [Long-term operations](docs/long-term-use.md)
- [Roadmap](docs/roadmap.md)
- [ADR 0001: Containerized appliance](docs/adr/0001-use-containerized-virtual-appliance.md)
- [ADR 0002: Dual-mode DynamoDB cache](docs/adr/0002-dual-mode-dynamodb-caching.md)
- [ADR 0003: HubSpot writebacks](docs/adr/0003-hubspot-granular-writebacks.md)
- [ADR 0004: Stable adapter ports and fail-open mail advice](docs/adr/0004-stable-adapter-ports-and-fail-open-mail-advice.md)
- [ADR 0005: Portable distribution from one container payload](docs/adr/0005-portable-distribution-from-one-container-payload.md)

## Repository layout

```text
.
├── .env.example
├── Dockerfile
├── docker-compose.yml
├── bin/kanga-route
├── systemd/
├── src/kanga_route/
├── tests/
├── packer/
├── infra/
├── cloudformation/
└── docs/
```

## Safety notes

Email probing is inherently probabilistic. Do not suppress a contact merely
because it is `Unknown` or `Catch-All`. Run only from infrastructure and
domains you control, respect provider policies, keep batch sizes conservative,
and monitor IP reputation.

Kanga-Route is MIT licensed, authored by
[@shereford](https://github.com/shereford), and maintained by
[Dekglas LLC](https://dekglas.com), with `@shereford` continuing as an
additional maintainer.
