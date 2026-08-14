![Kanga-Route Banner](banner.png)

# Kanga-Route

Kanga-Route is a self-hosted AWS appliance that verifies HubSpot contact email
addresses before sales outreach. It pages contacts from HubSpot, applies
syntax/disposable-domain/DNS/SMTP checks, caches definitive outcomes, and
writes five granular properties back to the original contacts.

It does not send email message bodies.

## MVP capabilities

- Conservative four-stage verification with catch-all detection, STARTTLS,
  multiple-MX failover, and a global concurrency cap.
- Safe classifications: transient DNS, SMTP, and policy failures stay
  `Unknown`; explicit evidence is required for `Invalid`.
- HubSpot paging, bounded API retry, cooldown-aware re-verification, and
  exact contact-ID writebacks.
- DynamoDB Local for a zero-infrastructure cache, or managed DynamoDB through
  the EC2 instance role; both use a 30-day default TTL.
- A daily persistent systemd timer, manual `kanga-route` control plane,
  journald logs, and overlap protection.
- An opt-in browser console and versioned API for one address, published only
  on appliance loopback for SSM port forwarding.
- A private-candidate-only Packer AMI workflow and Pulumi infrastructure that
  requires an appliance AMI and defaults to SSM-only administration.

## Quick start

AMI builds are always private candidates. Run the manual Packer workflow
from the commit you intend to release, boot and smoke-test the resulting AMI,
and deploy that exact candidate privately after it passes staging. Public
sharing is a separate manual release operation for now; automating promotion of
the exact staged candidate, without rebuilding it, is post-MVP work.

The bakery authenticates to AWS through GitHub Actions OIDC. Configure the
repository variable `AWS_AMI_BUILDER_ROLE_ARN` with the ARN of a dedicated
builder role. Its trust policy must restrict the GitHub subject to
`repo:kanga-route@313547928/kanga-route@1324385265:ref:refs/heads/master`
and the audience to `sts.amazonaws.com`. GitHub uses this repository's
immutable owner and repository IDs in OIDC subjects. Confirm the current prefix
with `gh api repos/kanga-route/kanga-route/actions/oidc/customization/sub`
before creating or changing the AWS trust policy. Do not configure long-lived
AWS access-key secrets for the workflow. The build verifies its caller identity
before Packer creates any resources.

The previously listed public AMI predates this MVP work. It is intentionally
not advertised as an MVP release image; use a candidate built from the current
commit.

Before the first production run you must:

1. create the five exact HubSpot contact properties and a private app;
2. allocate an Elastic IP and align A, PTR, SPF, HELO, and envelope-from values;
3. obtain AWS outbound port 25 approval;
4. copy `.env.example` to `.env`, store it with mode `0600`, and replace
   the fail-safe `.invalid` SMTP placeholders; and
5. start a manual smoke run with `sudo kanga-route run`.

Follow [the setup and operations guide](docs/setup.md) for exact property types,
Pulumi configuration, cache modes, schedules, and result semantics.

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
the Compose project. A real verification run intentionally fails until the
HubSpot token and public SMTP identity are configured.

## Documentation

- [Setup and operations](docs/setup.md)
- [Architecture](docs/architecture.md)
- [Browser console](docs/browser-console.md)
- [HubSpot user story and workflows](docs/hubspot-user-story.md)
- [Long-term operations](docs/long-term-use.md)
- [Roadmap](docs/roadmap.md)
- [ADR 0001: Containerized appliance](docs/adr/0001-use-containerized-virtual-appliance.md)
- [ADR 0002: Dual-mode DynamoDB cache](docs/adr/0002-dual-mode-dynamodb-caching.md)
- [ADR 0003: HubSpot writebacks](docs/adr/0003-hubspot-granular-writebacks.md)

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
└── docs/
```

## Safety notes

Email probing is inherently probabilistic. Do not suppress a contact merely
because it is `Unknown` or `Catch-All`. Run only from infrastructure and
domains you control, respect provider policies, keep batch sizes conservative,
and monitor IP reputation.

Kanga-Route is MIT licensed and maintained by
[@shereford](https://github.com/shereford).
