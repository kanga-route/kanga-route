# ADR 0005: Portable Distribution from One Container Payload

**Status:** Accepted

## Context

Kanga-Route currently has two usable delivery paths: operators can build and
run the Docker Compose project themselves, or maintainers can bake that project
into an AWS AMI. The application is not intrinsically tied to AWS, but the only
released virtual-machine image is an AMI.

On-premises operators and users of other cloud providers should not have to
reimplement the appliance. A bootable ISO appears universal, but it creates an
installer product with disk partitioning, hardware discovery, interactive and
unattended installation, upgrade, recovery, and broad driver-support duties.
Most virtualized environments instead consume an existing virtual disk or an
appliance archive.

Publishing several independently built application variants would create a
larger risk: Docker, AMI, on-premises, and cloud-specific behavior could drift.

## Decision

The versioned OCI container image is the canonical application payload. Every
virtual-machine appliance must run the same container digest and Compose
contract. A release manifest associates the source commit, container digest,
host-image artifact, checksum, SBOM, signature or attestation, build run, and
boot-test result.

Delivery support is organized as follows:

| Artifact | Intended environment | Direction |
|---|---|---|
| OCI images plus Compose bundle | User-managed Linux and container hosts | Primary |
| AWS AMI | AWS EC2 | Primary and currently implemented |
| QCOW2 | KVM, Proxmox, OpenStack, and OCI import | Next appliance target |
| OVA with VMDK | VMware and VirtualBox | Next on-premises target |
| `disk.raw` archive | Google Cloud image import | Derived after QCOW2 |
| Fixed VHD | Azure and Hyper-V | Derived after QCOW2 |
| Bootable ISO | Bare metal and specialized air-gapped installs | Deferred pending demand |

Docker remains a supported operator path, not merely an internal AMI build
step. Users may run the Compose stack or its individual images and own the host,
scheduler, TLS exposure, public/NAT address, outbound TCP 25 access, and SMTP
identity. Docker bridge networking is the default; host networking is not a
product requirement.

All VM targets share one idempotent host-provisioning implementation. Builders
may supply platform-specific metadata or guest agents, but they may not fork
application configuration or rebuild application code differently. Images
contain no product credentials, cloud account identifiers, SSH host keys,
machine identifiers, or configured customer network identity.

A generic VM image must:

- obtain network configuration through DHCP without a fixed MAC or IP;
- support first-boot configuration through cloud-init and a documented console
  recovery path;
- default to DynamoDB Local unless the operator selects another supported
  cache mode;
- keep batch schedules, browser exposure, and mail policy enforcement disabled
  until explicitly configured;
- retain the loopback-only browser and policy-service defaults; and
- pass a booted-artifact test before publication.

Artifact conversion is not considered validation. QCOW2, OVA, raw, VHD, and
AMI outputs each require a representative boot test. Documentation must label
an artifact experimental until its boot test and installation guide exist.

## Consequences

### Positive

- Container, AWS, on-premises, and future cloud users receive identical
  application code.
- QCOW2 and OVA cover the common virtualized environments without maintaining
  an operating-system installer.
- Operators retain a direct Docker deployment when they prefer to manage SMTP
  networking and scheduling themselves.
- Digests and a release manifest make cross-format provenance reviewable.

### Negative

- Each VM format still needs build infrastructure, boot tests, documentation,
  vulnerability maintenance, and a support owner.
- Platform guest agents and image-import constraints cannot be made completely
  uniform.
- The current AMI bakery builds the container locally; moving it to a published
  digest requires a staged migration so private candidates remain reproducible.

## Deferred ISO decision

An ISO will be reconsidered only when an issue identifies a real bare-metal or
air-gapped user, unattended-install requirements, supported hardware or
hypervisors, update and recovery expectations, a test environment, and a
maintainer. Until then, an ISO is not a promised release artifact.
