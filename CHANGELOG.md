# Changelog 📜

All notable changes to the Kanga-Route Virtual Appliance project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
