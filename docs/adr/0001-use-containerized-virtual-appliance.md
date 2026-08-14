# 1. Implementation of a Containerized Virtual Appliance (Docker + Packer)

**Status:** Accepted
**Amended:** 2026-08-13

## Context

Kanga-Route must perform direct SMTP verification for HubSpot contacts.
Common serverless platforms restrict outbound port 25, while maintaining and
distributing a custom operating-system image would add substantial operational
overhead.

The original accepted decision anticipated packaging the appliance as AWS
AMIs, Azure VHDs, and standard ISOs, and described the result as completely
cloud- and hardware-agnostic. The MVP implementation delivers only the AWS
path, so those broader targets are not part of the currently supported scope.

## Decision

The application and optional DynamoDB Local sidecar are packaged as a Docker
Compose stack. HashiCorp Packer installs Docker, an allowlisted application
payload, and the Kanga-Route systemd units into a private AWS AMI candidate.
The systemd control plane starts the appropriate cache stack at boot and
invokes verification through a persistent daily timer.

AWS AMI is the sole supported appliance image target for the MVP. Pulumi
deploys that AMI to EC2. Azure VHDs, standard ISOs, other cloud images, and
bare-metal installations require separate implementation and an explicit
architecture decision before they become supported targets.

## Consequences

### Positive

- The containerized runtime isolates application dependencies from the host.
- The EC2 network path permits direct SMTP connections once the AWS account's
  outbound port 25 restriction is removed.
- An immutable AMI candidate makes the tested application payload reproducible
  within the supported AWS deployment path.

### Negative

- The supported appliance remains AWS-specific rather than fully cloud- or
  hardware-agnostic.
- Operators manage both a Docker runtime layer and an AMI host layer.
- Each additional image target will require its own build, boot validation,
  release process, and support commitment.

## Amendment history

The 2026-08-13 amendment narrows the original multi-cloud and ISO aspiration
to the AWS AMI implementation actually shipped by the MVP. It does not reject
future image targets; it removes them from the current product promise until
they are designed and validated.
