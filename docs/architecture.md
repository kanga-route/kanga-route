# Kanga-Route Architecture

Kanga-Route is a self-hosted AWS appliance that verifies HubSpot contact email
addresses without sending message bodies.

```mermaid
flowchart TD
    Timer["systemd daily timer"] --> Batch["batch orchestration + file lock"]
    CLI["kanga-route run"] --> Batch
    SingleCLI["kanga-route verify"] --> Single["single-verification service"]
    Browser["browser via SSM tunnel"] --> Web["loopback-published web container"]
    Web --> Single
    Batch --> Engine["verification engine"]
    Single --> Engine
    Batch --> HubSpot["HubSpot Contacts API"]
    Engine --> DNS["DNS resolvers"]
    Engine --> MX["Recipient MX servers: TCP 25"]
    Batch --> Cache{"Cache mode"}
    Single --> Cache
    Cache --> Local["DynamoDB Local volume"]
    Cache --> Cloud["Managed DynamoDB"]
```

## Verification flow

The engine pages unverified contacts, cooldown-eligible `Unknown` contacts,
and results older than `REVERIFY_AFTER_DAYS`. Syntax and disposable-domain
failures terminate early.
Authoritative DNS absence can produce `Invalid / No_MX`; transient DNS
failures produce `Unknown`. SMTP checks try MX hosts in priority order,
perform opportunistic STARTTLS, test a randomized recipient for catch-all
behavior, and require explicit recipient-not-found evidence before producing
`Invalid / User_Not_Found`.

A global asynchronous semaphore caps concurrent probes across different
customer domains. Unknown results are written back for visibility but not
cached. Definitive results use DynamoDB TTL.

## Product-neutral result contract

The verifier emits a JSON-compatible object through
`VerificationResult.to_dict()`. Its stable fields are `email`, `status`,
`reason`, `mailbox_provider`, `is_role_account`, `mx_records`, `smtp_code`, and
`verified_at`. Enum fields use their documented string values,
`verified_at` remains an ISO-8601 string, and optional fields are represented as
JSON `null`.

`VerificationTarget` carries an adapter-owned `record_id`, an email address, and
optional metadata. `VerificationOutcome` associates a target with its result at
the orchestration boundary and rejects mismatched email addresses. External
record identity is never embedded in verification evidence or cache entries.

Integration adapters own all product-specific formatting. For example, the
HubSpot adapter maps the neutral status and reason to custom property names,
renders booleans as lowercase strings, and converts `verified_at` to Unix epoch
milliseconds. This keeps the verification engine reusable by future CRM,
spreadsheet, webhook, and file adapters.

## Single-address browser boundary

The browser console, `POST /api/v1/verify`, and single-address CLI use one
application service for normalization, cache policy, configuration validation,
and verification. The API accepts only a bounded JSON envelope, uses stable
sanitized errors, and runs blocking verification work behind explicit timeout,
concurrency, and rate limits. Uvicorn access logging is disabled.

The web container is opt-in and published as `127.0.0.1:8080` on the appliance.
It contains no authentication mechanism and is intended only for SSM port
forwarding. Non-loopback exposure remains blocked on the UI-04 TLS/auth design.

## Host control plane

Packer installs Docker, an allowlisted application payload, three systemd
units, and the `kanga-route` command. The stack unit starts DynamoDB Local only
when local mode is selected and starts the loopback browser container only when
explicitly enabled. A persistent timer invokes a oneshot run service daily;
journald retains output, and `flock` prevents overlap.

## AWS deployment

Pulumi creates the VPC, public subnet, egress rules, IAM instance profile,
Elastic IP, and EC2 instance. It requires a Kanga-Route AMI ID rather than
falling back to Ubuntu, requires IMDSv2, encrypts the root disk, and exposes no
SSH ingress unless a restricted CIDR is explicitly configured. SSM Session
Manager is the default administration path.

Outbound port 25 still requires AWS account approval, and operators must align
the appliance Elastic IP with forward DNS, reverse DNS, and the configured SMTP
identity.
