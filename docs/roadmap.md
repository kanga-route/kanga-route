# Kanga-Route Development Roadmap 🗺️

## Phase 1: Core Engine & Verification Pipeline (v1.0.0 — Completed)
* 4-layer verification sequence (Syntax Regex, 150+ Disposable Blocklist, DNS MX Provider Fingerprinting, STARTTLS SMTP Socket Handshake)
* Random dummy address Catch-All detection (`nxdomain_test_<uuid>@domain.com`)
* Provider-based `asyncio.Semaphore` rate limiting (max 5 connections per provider)
* Dual-Mode DynamoDB caching with 30-day automatic TTL expiration
* Granular HubSpot CRM API v3 property writebacks
* **Milestone:** v1.0.0 production engine released

---

## Phase 2: Virtual Appliance & Infrastructure Bakery (v1.0.0 — Completed)
* `docker-compose.yml` sidecar orchestration (`verifier-engine` + `dynamodb-local`)
* Host OS `/usr/local/bin/kanga-route` control plane CLI wrapper
* `systemd/kanga-route.service` automatic boot orchestration
* Automated HashiCorp Packer AMI bakery (`packer/kanga-route.pkr.hcl`) with public launch permissions
* Pulumi Infrastructure-as-Code stack (`infra/`) for automated VPC, Security Group, and Elastic IP provisioning
* **Milestone:** Public AMI `ami-0621206b8c7bfc85c` live in `us-east-1`

---

## Phase 3: CI/CD & Gated Release Management (v1.0.0 — Completed)
* Automated Pull Request CI pipeline (`.github/workflows/pull-request.yml`) executing `pytest` test suite, Packer template validation, and Pulumi syntax checks
* Automated SemVer versioning workflow (`.github/workflows/auto-version.yml`)
* Cost-optimized manual release promotion workflow (`.github/workflows/packer-build.yml`) with candidate manifest artifact uploads
* **Milestone:** Release gating and candidate artifact management active

---

## Phase 4: Domain Firmographics & Team Alerts (v1.1.0 — Planned)
* **Domain & Tech Stack Enrichment**: Automatically extract MX provider, SSL issuer, and tech stack signatures (Google Workspace, Microsoft 365, Shopify) from target contact email domains.
* **Team Slack/Teams Webhooks**: Real-time channel alerts (`#sales-ops`) for daily verification digests and sequence risk warnings.

---

## Phase 5: Past Champion / Job Changer Detector (v1.2.0 — Planned)
* **Job Change Tracking (Opt-In Feature)**: When a previously engaged contact's email returns `User_Not_Found` during routine verification runs, the engine checks for domain change triggers or updated contact handles.
* **HubSpot Task Generation**: Automatically creates a high-priority task for the account owner: *"⚡ Prospect Job Change Alert: Past champion has left their previous company!"*
* **Opt-In Configuration**: Enabled via `.env` setting `FEATURE_JOB_CHANGER_DETECTOR=true`.
