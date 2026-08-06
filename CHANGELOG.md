# Changelog 📜

All notable changes to the Kanga-Route Virtual Appliance project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## 📐 Semantic Versioning Policy (`MAJOR.MINOR.PATCH`)

This project strictly adheres to `MAJOR.MINOR.PATCH` versioning rules:

- **MAJOR (`1.x.x` → `2.0.0`)**: Incompatible API, database schema, or breaking environment variable changes.
  - Changes to HubSpot custom contact property internal names.
  - Breaking changes to `/opt/kanga-route/.env` keys or database schemas requiring manual data migration.
  - Architectural shifts replacing Docker Compose or DynamoDB data contracts.

- **MINOR (`1.0.x` → `1.1.0`)**: Backward-compatible new features, CRM connectors, or performance enhancements.
  - Adding new verification layers (e.g., SPF/DKIM verification, webhooks, Slack/Teams alerts).
  - Adding new CRM connectors (e.g., Salesforce, Marketo, ActiveCampaign).
  - Performance improvements, dynamic blocklist fetching, or new container capabilities.
  - Infrastructure expansions (e.g., Terraform support, ARM64 `t4g` AMIs).

- **PATCH (`1.0.0` → `1.0.1`)**: Backward-compatible bug fixes, security patches, blocklist updates, and documentation.
  - Bug fixes for edge-case SMTP timeouts, regex parsing, or DNS resolution logic.
  - Updates to the static disposable domain blocklist or MX provider regex patterns.
  - Documentation updates (`README.md`, setup guides) and CI/CD workflow fixes.

---

## [1.0.0] - 2026-08-06

### Added
- **4-Layer Verification Engine**: Syntax Regex & Role Account detection, 150+ Disposable Domain Blocklist, DNS MX resolution & provider fingerprinting, and direct TCP Port 25 SMTP socket handshakes.
- **Production SMTP Security**: STARTTLS encryption, random dummy address Catch-All detection (`nxdomain_test_<uuid>@domain.com`), and public domain configuration (`SMTP_HELO_DOMAIN`, `SMTP_MAIL_FROM`).
- **Async Concurrency & Provider Throttling**: Provider-based `asyncio.Semaphore` rate limiting (max 5 concurrent connections to Google/Outlook MX hosts) to prevent IP blacklisting.
- **Dual-Mode Cache Persistence**: Dual-mode DynamoDB caching (`dynamodb-local` sidecar vs AWS Cloud DynamoDB) with 30-day automatic TTL expiration.
- **Granular HubSpot CRM Writebacks**: Pushes `email_verification_status`, `email_verification_reason`, `mailbox_provider`, `is_role_account`, and `last_verified` to HubSpot contacts.
- **Host OS Control Plane CLI**: Baked `/usr/local/bin/kanga-route` wrapper (`run`, `status`, `logs`, `schedule`) and `systemd/kanga-route.service` boot orchestration.
- **Packer Appliance Bakery & Public AMI**: Automated Packer template (`packer/kanga-route.pkr.hcl`) generating public AMIs in `us-east-1` (`ami-0621206b8c7bfc85c`).
- **Pulumi IaC Stack**: Fully automated Infrastructure-as-Code stack (`infra/__main__.py`) provisioning VPC, Subnet, Security Group, IAM Role with SSM/DynamoDB policies, Elastic IP, and EC2 instance.
- **CI/CD & Release Gating**: GitHub Actions workflows for PR validation (`pull-request.yml`), candidate AMI manifest artifact uploads, and release promotion (`packer-build.yml`).
