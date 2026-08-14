![Kanga-Route Banner](banner.png)

# Kanga-Route

Kanga-Route is an open-source, self-hosted email-verification appliance. It
combines syntax, disposable-domain, DNS/MX, and cautious SMTP evidence into a
product-neutral result without sending an email message body. Ambiguous and
transient evidence remains `Unknown`; an address becomes `Invalid` only when
the verifier receives explicit evidence.

Use the same engine from the browser console, versioned HTTP API, CLI, batch
integration, or optional mail-server advice service. Standalone verification
does not require a CRM account. HubSpot is the first reference integration,
not a boundary of the product, and new adapters translate their own records
without changing verification behavior.

## Delivery model

Kanga-Route follows a **one payload, multiple environments** model. The OCI
container is the canonical application payload; supported and planned
appliances wrap the same application contract instead of creating separate
product variants. Today the container is built from a reviewed checkout;
publishing digest-pinned images and a versioned Compose bundle is the next
distribution milestone.

| Deployment | Intended use | Current status | Start here |
|---|---|---|---|
| Docker Compose | User-managed Linux, on-premises, or any cloud | Supported today from a reviewed repository checkout | [Docker deployment](docs/docker-deployment.md) |
| AWS AMI | Managed appliance on EC2 | Implemented; verify the catalog entry is `shared` or `public` before deployment | [AWS deployment](docs/aws-appliance-deployment.md) |
| QCOW2 and OVA | KVM, Proxmox, OpenStack, VMware, and VirtualBox | Planned and must be boot-tested independently | [Portable-delivery roadmap](docs/roadmap.md#milestone-5-portable-delivery) |
| Google Cloud raw image and Azure fixed VHD | Provider-native VM imports | Planned after the generic VM artifacts | [ADR 0005](docs/adr/0005-portable-distribution-from-one-container-payload.md) |
| Bootable ISO | Bare metal or specialized air-gapped installation | Deferred until a real user and support owner establish requirements | [Deferred ISO decision](docs/adr/0005-portable-distribution-from-one-container-payload.md#deferred-iso-decision) |

Docker operators own host patching, scheduling, backups, TLS exposure,
outbound TCP 25 access, public/NAT addressing, and SMTP network identity. The
AWS appliance provides the host control plane around the same application.
Every published format must retain conservative result semantics and pass its
own boot test.

## Documentation by audience

### Evaluators and new users

- [Architecture](docs/architecture.md) — understand the engine, application
  boundaries, cache, and appliance control plane.
- [Browser console](docs/browser-console.md) — review the single-address UI and
  versioned API behavior.
- [HubSpot user story](docs/hubspot-user-story.md) — see how the reference batch
  integration fits a sales workflow.
- [Contributor roadmap](docs/roadmap.md) — see what exists today and what is
  planned next.

### Deployers and operators

- [Beginner AWS deployment](docs/aws-appliance-deployment.md) — build the
  network and appliance from CloudFormation with guided DNS and AWS steps.
- [CloudFormation template](cloudformation/kanga-route-appliance.yaml) — create
  the documented AWS resources in a selected region.
- [User-managed Docker deployment](docs/docker-deployment.md) — operate on
  premises or in another cloud while owning the host and SMTP networking.
- [Setup and operations](docs/setup.md) — configure SMTP identity, caching,
  schedules, HubSpot, and result handling.
- [Browser console](docs/browser-console.md) — expose the unauthenticated UI
  only through the documented TLS or private-access boundary.
- [Optional mail-server advice](docs/mail-server-integration.md) — consume
  cached evidence without making Kanga-Route a mail-flow dependency.
- [Long-term operations](docs/long-term-use.md) — manage reputation, cache
  lifecycle, logs, schedules, and upgrades.
- [AMI catalog](docs/ami-catalog.md) — check the exact regional image and its
  `candidate`, `shared`, or `public` availability.

### Integration authors and contributors

- [Contributor guide](docs/contributing.md) — prepare a development environment
  and run the same validation used by pull requests.
- [Integration authoring contract](docs/integration-authoring.md) — implement an
  adapter without coupling a product to the verification engine.
- [Contributor roadmap](docs/roadmap.md) — claim a bounded piece of planned
  work and follow its acceptance criteria.
- [Architecture](docs/architecture.md) — understand the dependency seams that
  architecture tests enforce.

### Release maintainers and architects

- [AMI build and publication](docs/ami-release-workflow.md) — build, test,
  approve, promote, and record one exact AMI.
- [AMI catalog](docs/ami-catalog.md) — review the generated regional release
  inventory.
- [Architecture decisions](docs/adr/) — read the durable decisions governing
  packaging, caching, integration writebacks, adapter seams, mail advice, and
  portable delivery.

## Repository layout

```text
.
├── .github/
│   ├── ISSUE_TEMPLATE/       # Structured bug and feature requests
│   └── workflows/            # Pull-request CI and reusable AMI delivery
├── bin/kanga-route           # Appliance operator control command
├── browser-tests/            # Playwright browser interaction tests
├── cloudformation/           # Guided standalone AWS deployment stack
├── docs/                     # Audience guides
│   └── adr/                  # Architecture decisions
├── infra/                    # Pulumi AWS infrastructure implementation
├── packer/                   # AMI template and host provisioning
├── scripts/                  # AMI catalog and release automation
├── src/kanga_route/
│   ├── adapters/             # Product adapters and explicit registry
│   ├── application/          # Batch, single-address, CLI, and advice services
│   ├── cache/                # Local or managed DynamoDB persistence
│   ├── crm/                  # Product transport clients used by adapters
│   ├── engine/               # Product-neutral verification logic
│   ├── mail/                 # Optional Postfix policy integration
│   └── web/                  # Browser console and versioned HTTP API
├── systemd/                  # Appliance service and scheduling units
├── tests/                    # Unit, boundary, infrastructure, and release tests
├── Dockerfile
├── docker-compose.yml
└── pyproject.toml
```

## Safety

Email probing is inherently probabilistic. Do not suppress a contact merely
because it is `Unknown` or `Catch-All`. Run only from infrastructure and
domains you control, respect provider policies, keep batch sizes conservative,
and monitor IP reputation.

Kanga-Route is MIT licensed, authored by
[@shereford](https://github.com/shereford), and maintained by
[Dekglas LLC](https://dekglas.com), with `@shereford` continuing as an
additional maintainer.
