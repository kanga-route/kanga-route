# 1. Implementation of a Containerized Virtual Appliance (Docker + Packer)

* **Status:** Accepted

## Context
We need an automated system to perform deep SMTP verification on HubSpot contacts. Serverless platforms (AWS Fargate, managed Kubernetes) hard-block outbound Port 25, preventing raw SMTP handshakes. Distributing a custom Linux OS (ISO) introduces massive maintenance overhead.

## Decision
We will adopt a hybrid architecture. The core application and database emulator will be packaged as a standard `docker-compose.yml` stack. We will use HashiCorp Packer to bake this containerized payload into cloud-native Machine Images (AWS AMIs, Azure VHDs) and standard ISOs. A systemd service will automatically execute `docker compose up -d` on boot.

## Consequences

### Positive
* Complete cloud and hardware agnosticism.
* The host OS remains pristine with zero dependency conflicts.
* Bypasses serverless Port 25 restrictions natively through the VM's network bridge.

### Negative
* Requires managing two layers of abstraction (Docker for the runtime, Packer for the host VM image).