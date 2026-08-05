# Kanga-Route System Architecture

Kanga-Route is a self-hosted, virtual appliance designed to perform deep SMTP email verification for HubSpot contacts. By running as a standalone Amazon Machine Image (AMI) rather than a serverless container, it bypasses standard cloud restrictions on outbound TCP Port 25, allowing for raw socket mail server handshakes without third-party SaaS APIs.

## High-Level Workflow

1. **Trigger:** The appliance is awakened by a local `systemd` cron timer or a manual CLI command.
2. **Ingest:** The Python engine pages through the HubSpot CRM API, fetching contacts modified since the last run.
3. **Cache Check:** Contacts are checked against the DynamoDB cache. If recently verified (e.g., within 30 days), the network verification is skipped to conserve bandwidth and protect IP reputation.
4. **Verification:** Unknown or expired emails are passed through the 4-Layer Verification Engine.
5. **Write-Back:** The engine batches the results and updates custom properties on the HubSpot contact records.

---

## The 4-Layer Verification Engine

To fail fast and save compute, the verification engine processes emails sequentially through four layers. If a layer fails, the check terminates immediately.

1. **Syntax & Role Parsing:** Validates string format against RFC-5322 and flags common role-based accounts (e.g., `admin@`, `sales@`).
2. **Disposable Domain Blocklist:** Cross-references the domain against a local JSON list of known throwaway/disposable providers.
3. **DNS & MX Lookup:** Queries the domain's nameservers to ensure a valid Mail Exchange (MX) record exists. Identifies the underlying mailbox provider (e.g., Google Workspace, Microsoft 365).
4. **Raw SMTP Handshake:** Opens a direct TCP Socket on Port 25 to the target MX server. Issues `HELO`, `MAIL FROM`, and `RCPT TO` commands to verify mailbox existence, logging exact SMTP response codes, and issuing `QUIT` before data transmission.

---

## State Management (Bring-Your-Own-Database)

Kanga-Route utilizes a dual-mode caching system built on DynamoDB to prevent redundant verification.

* **Local Mode (Default):** The OS runs `amazon/dynamodb-local` via Java as a persistent background service. The cache is stored locally on the VM's disk. This allows for instant deployment with zero external dependencies.
* **Cloud Mode:** Controlled via the `USE_LOCAL_DB=false` environment variable. The appliance bypasses the local service and inherits the EC2 IAM profile to communicate with a dedicated, persistent AWS DynamoDB table for enterprise scaling.

---

## Infrastructure Footprint

When deployed to production (e.g., via Pulumi), the AWS footprint consists of:
* **Compute:** 1x `t4g.micro` or `t3.micro` EC2 Instance.
* **Network:** 1x Elastic IP (EIP) with a configured Reverse DNS (PTR) record.
* **Security:** Security Group allowing outbound TCP 25 (SMTP), 53 (DNS), and 443 (HTTPS).
* **IAM:** Instance Profile with permissions scoped strictly to the DynamoDB cache table (if Cloud Mode is enabled).