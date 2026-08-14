# Kanga-Route Contributor Roadmap

Kanga-Route is an open-source email-verification engine and self-hosted
appliance. HubSpot is the first supported integration, not the boundary of the
product. This roadmap breaks future development into work that can be discussed,
claimed, implemented, and reviewed independently.

The roadmap describes direction rather than release dates. Before starting an
item, open or claim its GitHub issue so contributors do not duplicate work. A
pull request should normally address one roadmap item and include its tests and
documentation.

## Product principles

- **Conservative results:** transient or ambiguous evidence remains `Unknown`;
  only explicit evidence may produce `Invalid`.
- **Product-neutral core:** verification and caching must not depend on HubSpot,
  another integration, the CLI, or the browser UI.
- **Adapters translate; the engine decides:** integrations fetch records, map
  them into shared contracts, and format results for their product. They do not
  reimplement verification policy.
- **Self-hosted and inspectable:** users control the runtime, credentials, data,
  and network identity.
- **One payload, multiple environments:** Docker is a supported delivery path
  and every VM artifact runs the same immutable container digest.
- **Secure by default:** secrets never enter source control, submitted addresses
  are not exposed unnecessarily, and authenticated browser traffic is never
  accepted over plaintext HTTP.
- **Small, testable contributions:** extension points include a fake or
  reference implementation and reusable contract tests.

## Current foundation

The current implementation provides syntax, role-address, disposable-domain,
DNS/MX, SMTP, and catch-all checks; conservative result classifications;
bounded concurrency;
local or managed DynamoDB caching; a HubSpot integration; Docker Compose,
systemd, Packer, Pulumi, SSM-first administration, and CI.

Shared evidence, targets, outcomes, orchestration, and adapter selection are
product-neutral. HubSpot is behind the stable adapter port and owns its mapping,
limits, failures, and formatting. A cache-only mail advisory service and Postfix
reference integration demonstrate that new consumers do not modify the engine.
AWS AMI is the current VM artifact. ADR 0005 defines the staged path to a
published Compose bundle, QCOW2, OVA, and cloud import formats without turning
each format into a separate application build.

## Contributor workflow

Suggested GitHub labels:

- Area: `area/core`, `area/integration`, `area/ui`, `area/security`,
  `area/operations`, `area/docs`
- Size: `size/s`, `size/m`, `size/l`
- Experience: `good first issue`, `help wanted`
- State: `needs design`, `ready`, `blocked`

Size is a guide, not a time estimate:

- **S:** isolated change with an established design.
- **M:** several files or a new tested component.
- **L:** architectural work that begins with an issue proposal or ADR.

Each item has a stable identifier for issues and pull requests, such as
`CORE-01: Introduce a product-neutral input record`.

---

## Milestone 1: Product-neutral application core

**Goal:** run the same workflow from HubSpot, another integration, the CLI, or
the browser UI without importing product-specific code.

### CORE-01 — Introduce a product-neutral input record

**Status:** Complete

**Size:** M

**Labels:** `area/core`, `help wanted`, `ready`

Replace `HubSpotContact` in shared code with a neutral model such as
`VerificationTarget`, containing an adapter-owned record ID, email address, and
optional metadata.

Acceptance criteria:

- Shared contracts and orchestration no longer import `HubSpotContact`.
- The neutral record does not name or assume a CRM.
- HubSpot maps contacts into it without losing exact-ID writeback.
- Existing behavior remains covered by unit tests.

### CORE-02 — Separate verification evidence from record identity

**Status:** Complete

**Size:** M

**Labels:** `area/core`, `needs design`

Remove `contact_id` from `VerificationResult`. Introduce an
orchestration-level type that associates an adapter record with its result
without making the engine aware of that record.

Acceptance criteria:

- `VerificationEngine.verify(email)` returns a product-neutral result.
- One result can be associated with records from different adapters.
- Cache entries contain verification evidence, not external product IDs.
- Batch and cache-hit result pairing is tested.

### CORE-03 — Move result formatting into adapters

**Status:** Complete

**Size:** S

**Labels:** `area/core`, `area/integration`, `good first issue`, `ready`

Move `VerificationResult.to_hubspot_properties()` into the HubSpot integration
and define a neutral JSON representation for CLI, API, and test use.

Acceptance criteria:

- No HubSpot method or property name remains in `models.py`.
- HubSpot still produces the same five property values.
- Timestamp conversion is covered in the HubSpot tests.
- The neutral representation has a documented deterministic schema.

### CORE-04 — Replace `ICRMClient` with an adapter contract

**Status:** Complete

**Size:** L

**Labels:** `area/core`, `area/integration`, `needs design`

**Depends on:** CORE-01, CORE-02

Define a product-neutral adapter protocol. An adapter validates its
configuration, fetches eligible targets, and writes associated results.
Capabilities must allow read-only or write-only adapters without pretending
that every product is a CRM.

Acceptance criteria:

- Shared orchestration has no HubSpot imports or HubSpot error handling.
- Common error categories retain original exceptions as diagnostic context.
- Read and write capabilities are explicit.
- HubSpot implements the contract without paging, retry, or writeback regressions.
- An ADR records the contract before implementation merges.

### CORE-05 — Add adapter selection and configuration discovery

**Status:** Complete

**Size:** M

**Labels:** `area/core`, `area/integration`, `help wanted`

**Depends on:** CORE-04

Select an installed adapter through explicit configuration instead of importing
`HubSpotClient` in the entrypoint. Start with a small registry; a third-party
plugin system is deferred until multiple adapters prove the contract.

Acceptance criteria:

- `hubspot` remains the documented default during migration.
- Unknown adapters fail before network or cache work.
- Only the selected adapter validates its secrets.
- Selection failures have tests and actionable messages.

### CORE-06 — Publish an adapter contract-test kit

**Status:** In progress

**Size:** M

**Labels:** `area/integration`, `help wanted`

**Depends on:** CORE-04

Create reusable tests for target identity, batch limits, result pairing, partial
failures, safe retries, and secret redaction.

Acceptance criteria:

- HubSpot passes the shared contract suite.
- An in-memory fake demonstrates the interface.
- Tests require no real product credentials.
- Documentation distinguishes required and optional capabilities.

**Milestone exit:** the runner, verifier, cache, and shared models contain no
HubSpot types, property names, limits, or error messages.

---

## Milestone 2: Contributor-friendly integrations

**Goal:** make a new integration primarily a mapping and API-client task, with
verification semantics supplied by the core.

### INT-01 — Make HubSpot the reference adapter

**Status:** In progress

**Size:** M

**Labels:** `area/integration`, `help wanted`

**Depends on:** CORE-03 through CORE-06

Organize HubSpot as the reference implementation, including configuration,
eligibility queries, pagination, retries, mapping, and writeback.

Acceptance criteria:

- HubSpot-specific code lives under one adapter package.
- Documentation maps common fields to HubSpot properties.
- Unit tests require no live HubSpot account.
- Maintainers have an opt-in smoke-test procedure.

### INT-02 — Add a CSV adapter

**Size:** M

**Labels:** `area/integration`, `good first issue`

**Depends on:** CORE-06, INT-01

Use CSV as the first portability proof. Read configurable ID and email columns,
then write neutral result fields to a new file without overwriting the source.

Acceptance criteria:

- Configurable columns are documented.
- Invalid rows produce row-level diagnostics.
- Ordering and source identifiers are preserved.
- Tests cover Unicode, quoted fields, duplicates, missing fields, and empty files.
- Input is never modified in place.

### INT-03 — Document integration authoring

**Size:** S

**Labels:** `area/docs`, `area/integration`, `good first issue`

**Depends on:** CORE-06, INT-01

Write a guide covering package layout, configuration, mapping, errors, contract
tests, documentation, and the pull-request checklist.

Acceptance criteria:

- The guide builds a small adapter using fake data.
- Secret-handling rules are explicit.
- It links to contract tests and the HubSpot reference adapter.
- No proprietary account is needed for the tutorial.

### INT-04 — Add adapter health and dry-run commands

**Size:** M

**Labels:** `area/integration`, `area/operations`, `help wanted`

**Depends on:** CORE-05

Validate configuration and preview eligible records without SMTP probes or
product writebacks.

Acceptance criteria:

- Checks distinguish configuration, authentication, permission, and connectivity.
- Output redacts secrets and email addresses by default.
- Neither command writes to the product.
- Exit codes are stable and documented.

### INT-05 — Select the second API-backed product

**Size:** L

**Labels:** `area/integration`, `needs design`

**Depends on:** INT-01, INT-02, INT-03

Choose from demonstrated demand. Candidates may include Salesforce, Pipedrive,
Zoho CRM, or a generic webhook, but none is committed until an issue documents
users, API constraints, authentication, tests, and maintainer interest.

Acceptance criteria:

- The proposal identifies a contributor or maintainer.
- API scopes follow least privilege.
- CI tests behavior without production credentials.
- Product support adds no product-specific branches to the engine.

**Milestone exit:** CSV plus two API-backed products use the same contract, and
new integrations do not modify verification stages.

---

## Milestone 3: Single-address verification UI

**Goal:** allow an operator to enter one email and inspect one result without
configuring or writing to a product integration.

The first UI is a self-hosted operator tool, not a public multi-tenant service.

### UI-01 — Extract a single-verification application service

**Status:** Complete

**Size:** M

**Labels:** `area/core`, `area/ui`, `help wanted`

**Depends on:** CORE-02, CORE-03

Expose one operation that validates input, applies an explicit cache policy,
runs the engine when needed, and returns a neutral result. CLI and UI use the
same service.

Acceptance criteria:

- No CRM or adapter dependency.
- Cache behavior is explicit and tested.
- CLI and UI normalize input identically.
- Errors use stable categories without secrets or stack traces.

### UI-02 — Add a versioned HTTP API

**Status:** Complete

**Size:** M

**Labels:** `area/ui`, `area/security`, `needs design`

**Depends on:** UI-01

Add `POST /api/v1/verify` for one address. Batch upload and integration
credentials remain out of scope.

Acceptance criteria:

- Malformed input returns a safe `4xx` without a network probe.
- Request size, timeout, concurrency, and rate limits exist.
- Addresses and authorization values are absent from access logs.
- Tests use a fake verifier without external networking.
- Every status and reason is documented.

### UI-03 — Build the minimal browser interface

**Status:** Complete

**Size:** M

**Labels:** `area/ui`, `help wanted`

**Depends on:** UI-02

Provide one email field, submit action, progress state, and explanations for
status, reason, provider, role account, MX, and verification time.

Acceptance criteria:

- Keyboard and screen-reader workflows work.
- No appliance or integration credentials are embedded in the page.
- `Unknown` and `Catch-All` are not presented as invalid.
- Browser tests cover success, validation, timeout, and server errors.
- No third-party analytics, fonts, scripts, or CDNs are required.

### UI-04 — Enforce TLS before authentication

**Status:** In progress

**Size:** L

**Labels:** `area/security`, `area/ui`, `needs design`

**Depends on:** UI-02

Bind to loopback or a private interface by default. Any login, token, session
cookie, or authenticated request must be accepted only through HTTPS. Plaintext
HTTP may redirect or expose a minimal health response, but never accepts
credentials or authenticated work.

The guided AWS CloudFormation deployment now supplies one concrete secure edge:
an HTTPS ALB authenticates with Cognito before forwarding through a restricted
instance security group and nginx to the loopback-only web container. The
general ADR, trusted-proxy contract, and security tests remain to be completed
before other public deployment patterns are supported.

Acceptance criteria:

- An ADR defines authentication, TLS termination, trusted proxies, certificate
  lifecycle, and recovery.
- Non-loopback exposure fails closed unless secure deployment is configured.
- Cookies, if used, are `Secure`, `HttpOnly`, and have explicit `SameSite`.
- Browser-authenticated state changes have CSRF protection.
- Forwarded-protocol headers are trusted only from configured proxies.
- Tests prove authentication cannot complete over plaintext HTTP.

### UI-05 — Package the UI with the appliance

**Size:** M

**Labels:** `area/ui`, `area/operations`, `help wanted`

**Depends on:** UI-03, UI-04

Add UI/API services with health checks, resource limits, upgrade documentation,
and an explicit opt-in exposure model.

Acceptance criteria:

- Scheduled integrations continue when UI is disabled.
- Default installation creates no public ingress.
- Health checks expose no addresses, secrets, or detailed state.
- Upgrade docs identify UI-owned persistent data.
- Compose and booted-appliance smoke tests run one fake verification.

**Milestone exit:** an operator can securely test one address in a browser
without an integration and without an authenticated plaintext endpoint.

---

## Milestone 4: Optional mail-system advice

**Goal:** let a mail system use existing evidence without making Kanga-Route a
relay, delivery hop, or availability dependency.

### MAIL-01 — Add cache-only recipient advice

**Status:** Complete

**Size:** M

**Labels:** `area/integration`, `area/core`, `area/security`

The multi-recipient application service and `POST /api/v1/advice` cannot import
or receive the live engine. Cached `Invalid` produces a warning; every miss,
ambiguous result, and failure allows mail to continue.

### MAIL-02 — Add a fail-open Postfix reference adapter

**Status:** Complete

**Size:** M

**Labels:** `area/integration`, `area/operations`

The opt-in policy service defaults to observe-only `DUNNO`. Enforcement is an
explicit operator choice and applies only to cached `Invalid` evidence. Postfix
uses a short timeout and `default_action=DUNNO` for process-level fail-open.

### MAIL-03 — Warm cache misses asynchronously

**Size:** M

**Labels:** `area/core`, `area/operations`, `needs design`

Define a bounded, deduplicated queue that may receive advisory cache misses
after the mail transaction returns. Queue failure must not alter the advisory
response, and workers must use the existing engine port.

### MAIL-04 — Add compose-time cloud-mail adapters

**Size:** L

**Labels:** `area/integration`, `area/ui`, `needs design`

Prototype Outlook Smart Alerts and a user-invoked Gmail compose add-on. Each
must batch recipients, use a sub-500-ms caller deadline, and allow send when the
add-on or Kanga-Route is unavailable. Connector/smart-host routing is excluded.

**Milestone exit:** on-premises and cloud compose surfaces can consume the same
advisory contract without live verification or a mandatory mail hop.

---

## Milestone 5: Portable delivery

**Goal:** support user-managed Docker, AWS, common on-premises hypervisors, and
other clouds from one traceable application payload.

### DIST-01 — Define the portable artifact contract

**Status:** Complete

**Size:** S

**Labels:** `area/operations`, `area/docs`, `area/security`

ADR 0005 establishes the OCI container as the canonical payload, requires
digest identity across VM formats, defines the initial artifact matrix, and
defers a bare-metal ISO until demonstrated demand.

### DIST-02 — Publish immutable OCI images and a Compose release bundle

**Size:** M

**Labels:** `area/operations`, `area/security`, `help wanted`, `ready`

Publish engine, browser, and policy-service images to GHCR from protected
release workflows. A downloadable bundle contains Compose configuration,
`.env.example`, checksums, version metadata, and an operator guide.

Acceptance criteria:

- Images are tagged by release and source commit and recorded by digest.
- Production Compose pulls digests; the development override may still build.
- A release can be installed without cloning the repository.
- No registry, cloud, product, or SMTP credential is embedded in an image.
- CI runs the existing cache, API, and Postfix smoke tests against pulled images.

### DIST-03 — Extract shared, idempotent host provisioning

**Size:** M

**Labels:** `area/operations`, `area/security`

Refactor the AMI provisioner so AWS and generic VM builders install the same
Docker runtime, control plane, Compose bundle, and pinned container digest.

Acceptance criteria:

- Running provisioning twice is safe.
- Platform-specific guest agents are isolated from the common provisioner.
- Images contain no build-time SSH key, machine ID, host key, or credential.
- AMI behavior and its smoke tests do not regress.

### DIST-04 — Build and boot-test a QCOW2 appliance

**Size:** L

**Labels:** `area/operations`, `area/security`, `needs design`

Use a pinned Ubuntu cloud image and the Packer QEMU builder to produce a QCOW2
artifact for KVM, Proxmox, OpenStack, and OCI import.

Acceptance criteria:

- DHCP and cloud-init configure a fresh identity at first boot.
- The default appliance has no public UI, enabled batch schedule, or enforced
  mail policy.
- A KVM boot test validates startup, local cache, one fake result, and shutdown.
- Checksums, provenance, and limitations accompany the artifact.

### DIST-05 — Build and boot-test an OVA appliance

**Size:** L

**Labels:** `area/operations`, `area/security`, `needs design`

Package the same provisioned payload as an OVA with VMDK for VMware and
VirtualBox. Do not fork application settings from the QCOW2 or AMI targets.

Acceptance criteria:

- VMware-compatible virtual hardware and DHCP defaults are documented.
- Import and first-boot instructions require no embedded password.
- A representative hypervisor boot test exercises the same appliance contract.
- The release manifest records the same application container digest.

### DIST-06 — Add Google Cloud raw-image import

**Size:** M

**Labels:** `area/operations`, `area/docs`, `needs design`

Produce the required `disk.raw` archive from the validated generic disk,
document import and networking, and boot-test the imported image in staging.

### DIST-07 — Add Azure fixed-VHD import

**Size:** M

**Labels:** `area/operations`, `area/docs`, `needs design`

Produce an aligned fixed VHD with the required provisioning support, document
gallery import, and boot-test a correctly classified generalized image.

### DIST-08 — Sign and inventory every release artifact

**Size:** M

**Labels:** `area/operations`, `area/security`, `help wanted`

Generate an SBOM, checksums, provenance attestations, and one machine-readable
release manifest that ties every artifact to its source and container digest.

### DIST-09 — Reassess a bootable ISO after demonstrated demand

**Size:** S

**Labels:** `area/operations`, `area/docs`, `needs design`

Do not implement an ISO from format symmetry alone. A proposal must identify a
bare-metal or air-gapped user, unattended installation requirements, supported
hardware, update and recovery behavior, test infrastructure, and an owner.

**Milestone exit:** Docker, AMI, QCOW2, and OVA releases execute the same signed
container digest and pass booted tests; GCP and Azure imports have verified paths.

---

## Milestone 6: Operational hardening

These can progress alongside feature milestones when they do not alter
unfinished core contracts.

### OPS-01 — Pin and automate dependency updates

**Size:** M

**Labels:** `area/operations`, `area/security`, `help wanted`, `ready`

- Pin Python dependencies, images, Packer plugins, and build tooling.
- Define an update cadence and compatibility checks.
- Produce a dependency inventory or SBOM for candidates.

### OPS-02 — Add booted-appliance release tests

**Size:** L

**Labels:** `area/operations`, `area/security`, `needs design`

- Boot the exact candidate in staging.
- Test configuration failure, cache startup, SSM, one fake run, and shutdown.
- Promote the tested artifact without rebuilding.

### OPS-03 — Add metrics, summaries, and alerts

**Size:** M

**Labels:** `area/operations`, `help wanted`

- Report results by status/reason, cache hits, duration, and adapter outcome.
- Never use email addresses as metric dimensions.
- Keep telemetry local and customer-controlled by default.

### OPS-04 — Document and test backup and restore

**Size:** M

**Labels:** `area/operations`, `area/docs`, `help wanted`

- Cover local and managed DynamoDB.
- Define data preserved during appliance replacement.
- Add a repeatable restore drill.

### OPS-05 — Support pre-provisioned managed DynamoDB

**Size:** S

**Labels:** `area/operations`, `area/security`, `good first issue`

- Allow deployments to disable table creation and TTL administration.
- Document the least-privilege data-plane policy.
- Test missing-table and insufficient-permission diagnostics.

---

## Maintainer-owned decisions

These require an ADR and explicit maintainer approval:

- Changes to the accepted adapter interface and any third-party plugin mechanism.
- Authentication and TLS architecture for the browser UI.
- Changes to status or reason meanings.
- New network probes or material SMTP behavior changes.
- Database migrations and compatibility guarantees.
- Multi-region public AMI replication, release signing, and long-term artifact-retention policy.
- Changes to the supported artifact matrix or cross-format release contract.

## Explicitly out of scope for now

- A hosted multi-tenant verification SaaS.
- Anonymous public access to the single-address UI.
- Browser-based bulk upload.
- Product OAuth secrets in browser storage.
- Product-specific verification logic in the core.
- Using Kanga-Route as an SMTP relay, smart host, or mandatory delivery hop.
- A bootable ISO without demonstrated users, installation requirements, test
  infrastructure, and a maintainer.
- Automatically suppressing contacts based only on `Unknown` or `Catch-All`.

## Suggested next contributor issues

1. **DIST-02:** publish immutable OCI images and the standalone Compose bundle.
2. **CORE-06:** finish and publish the reusable adapter contract-test kit.
3. **INT-01:** finish organizing HubSpot as the documented reference adapter.
4. **INT-02:** prove product portability with a CSV adapter.
5. **OPS-05:** support pre-provisioned DynamoDB.

OPS-05 is the smallest independent code change. DIST-02 is the critical path
for deployment portability; CORE-06 and INT-01 are the best starting points for
contributors preparing a new product integration.
