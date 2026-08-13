# Kanga-Route Development Roadmap

## MVP: self-hosted HubSpot verification appliance — release candidate

- Four-stage verification: syntax/role, disposable domains, DNS/MX, and SMTP.
- Conservative classifications: transient DNS/SMTP failures stay `Unknown`;
  explicit evidence is required for `Invalid`.
- Cross-domain concurrency limiting and MX failover.
- HubSpot paging, retries, granular writebacks, and scheduled re-verification.
- Local or managed DynamoDB caching with TTL.
- Clean-checkout Docker Compose configuration and non-root engine container.
- Daily systemd timer, journald logs, manual CLI, and overlap protection.
- Private-only Packer candidates and an allowlisted AMI payload.
- Pulumi VPC/EC2 deployment that requires an appliance AMI, defaults to SSM,
  enforces IMDSv2, and encrypts the root disk.
- Pull-request tests for Python behavior, Compose, Docker, shell, and Packer.

## Next: operational hardening

- Pin container images and dependency versions with an automated update policy.
- Add a booted-AMI staging smoke test and automate promotion of that exact
  candidate without rebuilding it; promotion remains a manual release step.
- Add metrics, alerting, and a documented backup/restore drill.
- Scope managed DynamoDB access to a pre-provisioned table where deployments
  need stricter separation of duties.

## Later: product expansion

- Maintain the disposable-domain list from a reviewed upstream source.
- Add CRM connectors only after HubSpot operations are stable.
- Add notification integrations and aggregate reporting.
- Evaluate additional image targets only when there is user demand; the current
  supported appliance target is AWS AMI.
