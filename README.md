# Kanga-Route 🦘

> **Zero SaaS fees. Zero hard bounces.**  
> A containerized virtual appliance that routes HubSpot CRM contacts through a deep, 4-layer email verification engine and caches results in DynamoDB.

---

## Table of Contents

- [Overview \& Problem Statement](#overview--problem-statement)
- [System Architecture](#system-architecture)
- [Full Functionality Overview](#full-functionality-overview)
  - [1. 4-Layer Verification Engine](#1-4-layer-verification-engine)
  - [2. Granular CRM Intelligence Writebacks](#2-granular-crm-intelligence-writebacks)
  - [3. Dual-Mode Caching Strategy](#3-dual-mode-caching-strategy)
  - [4. Host OS Control Plane CLI](#4-host-os-control-plane-cli)
  - [5. Automated Image Bakery (Packer)](#5-automated-image-bakery-packer)
  - [6. Cloud Infrastructure (Pulumi)](#6-cloud-infrastructure-pulumi)
- [Prerequisites](#prerequisites)
- [Step-by-Step Guide for Junior Cloud Engineers](#step-by-step-guide-for-junior-cloud-engineers)
  - [Part 1: Local Setup \& Testing](#part-1-local-setup--testing)
  - [Part 2: Using the `kanga-route` Host CLI](#part-2-using-the-kanga-route-host-cli)
  - [Part 3: Baking the AMI Image with Packer](#part-3-baking-the-ami-image-with-packer)
  - [Part 4: Deploying to AWS with Pulumi](#part-4-deploying-to-aws-with-pulumi)
  - [Part 5: Production AWS Networking Requirements](#part-5-production-aws-networking-requirements)
- [Troubleshooting Guide](#troubleshooting-guide)
- [Project Directory Structure](#project-directory-structure)

---

## Overview & Problem Statement

### The Problem
Traditional SaaS email verification services charge recurring subscription fees and per-lookup pricing. When engineers attempt to build self-hosted verification workers using modern serverless platforms (AWS Lambda, Fargate, managed Kubernetes), they hit a hard wall: **cloud providers strictly block outbound TCP Port 25**, preventing raw SMTP socket handshakes.

### The Solution
**Kanga-Route** is designed as a **Containerized Virtual Appliance** running on an EC2 instance. The application logic is fully containerized with Docker Compose, while HashiCorp Packer bakes the stack into pre-configured Amazon Machine Images (AMIs). Running on an EC2 virtual machine bypasses serverless Port 25 restrictions natively through the host VM's network bridge.

---

## System Architecture

```mermaid
graph TD
    subgraph HubSpot CRM
        HS[HubSpot Contacts API v3]
    end

    subgraph Host VM / EC2 Instance (Kanga-Route Appliance)
        CLI[kanga-route CLI Wrapper] -->|Trigger Run| Compose[Docker Compose Stack]
        Systemd[systemd: kanga-route.service] -->|Auto-start on boot| Compose

        subgraph Docker Compose Container Stack
            Engine[verifier-engine Container]
            CacheDB[(dynamodb-local Container)]
        end
    end

    subgraph External Network / Internet
        DNS[Public DNS Resolvers]
        MX[Recipient Mail Servers (Port 25)]
    end

    Engine -->|1. Fetch Unverified Contacts| HS
    Engine -->|2. Check Cache| CacheDB
    Engine -->|3. Query MX Records| DNS
    Engine -->|4. Direct SMTP Handshake| MX
    Engine -->|5. Store Result| CacheDB
    Engine -->|6. Batch Writeback Properties| HS
```

---

## Full Functionality Overview

### 1. 4-Layer Verification Engine
Every email address passes through a sequential, 4-stage evaluation pipeline to ensure high accuracy while minimizing external network connections:

1. **Layer 1: Syntax & Role Account Detection**
   - Validates RFC 5322 email syntax using regular expressions.
   - Flags role-based administrative accounts (`admin@`, `info@`, `support@`, `sales@`, `billing@`, etc.).
2. **Layer 2: Disposable Domain Blocklist Check**
   - Screens domain names against known temporary/disposable email providers (`mailinator.com`, `10minutemail.com`, `tempmail.com`, etc.).
3. **Layer 3: DNS MX Lookup & Mailbox Provider Fingerprinting**
   - Queries public DNS for active `MX` (Mail Exchange) records (with fallback to `A` records).
   - Identifies and fingerprints major email service providers (Google Workspace, Microsoft 365, Proton Mail, Yahoo, iCloud, etc.).
4. **Layer 4: Direct SMTP Socket Handshake**
   - Opens a direct TCP socket connection to the primary recipient mail server on Port 25.
   - Executes standard SMTP commands (`EHLO`/`HELO`, `MAIL FROM`, `RCPT TO`) to verify mailbox existence without sending actual email messages.

### 2. Granular CRM Intelligence Writebacks
Refers to **ADR 0003**. Rather than returning a binary "Valid/Invalid" flag, Kanga-Route pushes rich operational intelligence back to custom HubSpot contact properties:

| HubSpot Property Internal Name | Type | Allowed / Sample Values | Description |
|---|---|---|---|
| `email_verification_status` | Enumeration | `Valid`, `Invalid`, `Catch-All`, `Unknown` | Primary verification outcome |
| `email_verification_reason` | Enumeration | `OK`, `Syntax_Error`, `Disposable`, `No_MX`, `User_Not_Found`, `Greylisted`, `Timeout`, `Connection_Refused`, `Unknown_Host` | Specific failure or success rationale |
| `mailbox_provider` | String | `Google Workspace`, `Microsoft 365`, `Proton Mail`, `Yahoo Mail`, `iCloud Mail`, `Other / Self-Hosted` | Provider identified via MX record fingerprinting |
| `is_role_account` | String / Bool | `true`, `false` | Indicates if address belongs to a role account |
| `last_verified` | String / Datetime | `2026-08-06T00:00:00Z` | ISO 8601 UTC timestamp of execution |

### 3. Dual-Mode Caching Strategy
Refers to **ADR 0002**. Deep SMTP verification handshakes are network-intensive. Kanga-Route caches verification results to prevent redundant connections on static contacts, saving bandwidth and protecting your host IP reputation:

- **Local Mode (Default):** Runs an official `amazon/dynamodb-local` sidecar container in Docker Compose, storing cached items in a persistent Docker volume (`dynamodb-data`).
- **Cloud Mode:** Set `USE_LOCAL_DB=false` (or remove `DYNAMODB_ENDPOINT_URL`) to seamlessly route cache reads and writes to a managed AWS DynamoDB table via the host EC2 instance's IAM role.
- **Automatic TTL:** Items automatically expire after 30 days (configurable).

### 4. Host OS Control Plane CLI
A native Bash CLI tool (`/usr/local/bin/kanga-route`) is baked directly into the appliance image. It abstracts Docker commands so junior cloud engineers and RevOps administrators do not need to manage raw container syntax:

- `kanga-route run`: Triggers an immediate one-off verification container run.
- `kanga-route status`: Checks container health and active cron schedules.
- `kanga-route logs`: Tails live engine container logs.
- `kanga-route schedule "<cron_expr>"`: Updates the host OS cron schedule automatically.

### 5. Automated Image Bakery (Packer)
Refers to **ADR 0001**. Uses HashiCorp Packer (`packer/kanga-route.pkr.hcl`) and a shell provisioner (`packer/scripts/provision.sh`) to bake Docker, Docker Compose, systemd unit files, pre-pulled images, and the host CLI into an Amazon Machine Image (AMI). A GitHub Actions workflow (`.github/workflows/packer-build.yml`) automates AMI builds on release.

### 6. Cloud Infrastructure (Pulumi)
A complete Infrastructure-as-Code stack written in Python (`infra/__main__.py`) provisions all required AWS resources:
- Dedicated VPC, Public Subnet, Internet Gateway, and Route Table.
- Security Group configured with outbound egress rules for TCP Port 25 (SMTP), Port 53 (DNS), Port 443 (HTTPS), and Port 80.
- IAM Role and Instance Profile granting DynamoDB permissions.
- Elastic IP (EIP) attached to the EC2 instance for static public IP addressing and Reverse DNS (rDNS).

---

## Prerequisites

Before starting, ensure your local workstation or administrative environment has the following tools installed:

1. **Docker Desktop / Docker Engine** (v20.10+) & **Docker Compose** (v2.0+)
2. **Python** (v3.9 or higher)
3. **Git**
4. **AWS CLI** & **HashiCorp Packer** (optional, required only for AMI baking)
5. **Pulumi CLI** (optional, required only for AWS cloud infrastructure deployment)

---

## Step-by-Step Guide for Junior Cloud Engineers

### Part 1: Local Setup & Testing

#### Step 1: Clone the Repository
```bash
git clone https://github.com/kanga-route/kanga-route.git
cd kanga-route
```

#### Step 2: Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Open `.env` in your text editor:
```env
HUBSPOT_ACCESS_TOKEN=pat-na1-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
DYNAMODB_ENDPOINT_URL=http://dynamodb-local:8000
DYNAMODB_TABLE_NAME=KangaRouteCache
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=dummy
AWS_SECRET_ACCESS_KEY=dummy
```
> **Note:** For local testing without a live HubSpot portal, leave `HUBSPOT_ACCESS_TOKEN` as the placeholder value.

#### Step 3: Set up Python Virtual Environment & Install Dependencies
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

#### Step 4: Run the Unit Test Suite
Verify that all unit tests pass cleanly:
```bash
PYTHONPATH=src .venv/bin/pytest
```
Expected output:
```text
============================== 20 passed in 0.13s ==============================
```

#### Step 5: Spin Up the Local DynamoDB Database
Start the local DynamoDB sidecar container in detached mode:
```bash
docker compose up -d dynamodb-local
```
Verify the container is running:
```bash
docker compose ps
```

#### Step 6: Run the Verification Engine Container
Trigger the containerized verifier engine:
```bash
docker compose run --rm engine
```
You will see output similar to:
```text
2026-08-06 06:05:25,919 [INFO] kanga_route.main: Starting Kanga-Route batch verification run (limit=100)...
```

---

### Part 2: Using the `kanga-route` Host CLI

On a provisioned appliance (or locally), use the wrapper script in `./bin/kanga-route`:

1. **Run a Manual Verification Batch:**
   ```bash
   ./bin/kanga-route run
   ```

2. **Check System & Container Status:**
   ```bash
   ./bin/kanga-route status
   ```

3. **Tail Container Logs:**
   ```bash
   ./bin/kanga-route logs
   ```

4. **Update Automated Cron Schedule:**
   To run verification automatically every night at 2:00 AM UTC:
   ```bash
   ./bin/kanga-route schedule "0 2 * * *"
   ```

---

### Part 3: Baking the AMI Image with Packer

When preparing a production machine image for AWS deployment:

1. **Initialize Packer Plugins:**
   ```bash
   packer init packer/kanga-route.pkr.hcl
   ```

2. **Validate the Packer Template:**
   ```bash
   packer validate packer/kanga-route.pkr.hcl
   ```

3. **Build the AMI Image:**
   ```bash
   packer build -var "aws_region=us-east-1" packer/kanga-route.pkr.hcl
   ```
   *Packer will output the newly registered AMI ID (e.g. `ami-0123456789abcdef0`).*

---

### Part 4: Deploying to AWS with Pulumi

To provision the full cloud infrastructure on AWS:

1. **Navigate to the `infra` Directory:**
   ```bash
   cd infra
   ```

2. **Install Infrastructure Dependencies:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Select or Create a Pulumi Stack:**
   ```bash
   pulumi stack init dev
   ```

4. **Set Configuration Variables:**
   ```bash
   pulumi config set aws:region us-east-1
   pulumi config set kanga-route-infra:instanceType t3.micro
   # Optional: set pre-baked AMI ID from Packer
   pulumi config set kanga-route-infra:amiId ami-0123456789abcdef0
   ```

5. **Deploy the Appliance Infrastructure:**
   ```bash
   pulumi up
   ```
   *Pulumi will output the assigned Elastic IP and EC2 Instance ID.*

---

### Part 5: Production AWS Networking Requirements

> [!IMPORTANT]
> Major email providers (Gmail, Outlook, Yahoo) enforce strict anti-spam requirements on mail servers connecting via Port 25. Complete these two mandatory AWS configuration steps prior to production verification:

1. **Submit AWS Port 25 Unblock Request:**
   - AWS blocks outbound Port 25 by default on all EC2 instances.
   - Open the AWS Support Console and navigate to **Request to remove email sending limitations**.
   - Provide your Elastic IP and explain that the instance performs outbound SMTP verification for your CRM contacts.

2. **Configure Reverse DNS (rDNS / PTR Record):**
   - Create a DNS `A` record in your DNS provider (e.g., Cloudflare, Route53) pointing `verifier.yourdomain.com` to your Elastic IP.
   - In the AWS EC2 Console under **Elastic IPs**, select your Elastic IP and edit **Reverse DNS (PTR record)** to match `verifier.yourdomain.com`.

---

## Troubleshooting Guide

### Issue 1: `401 Unauthorized` from HubSpot API
- **Cause:** `HUBSPOT_ACCESS_TOKEN` is missing or invalid in `.env`.
- **Fix:** Navigate to **HubSpot > Settings > Integrations > Private Apps**, create an app granting `crm.objects.contacts.read` and `crm.objects.contacts.write` scopes, and update `.env`.

### Issue 2: `Unable to locate credentials` when starting DynamoDB
- **Cause:** `boto3` requires dummy credentials when connecting to `dynamodb-local`.
- **Fix:** Ensure `AWS_ACCESS_KEY_ID=dummy` and `AWS_SECRET_ACCESS_KEY=dummy` are present in your `.env` file or environment.

### Issue 3: SMTP Handshake Timeouts (`reason: Timeout`)
- **Cause:** Outbound Port 25 is blocked by your local ISP or cloud provider network security group.
- **Fix:** Ensure you are running on an unblocked network or an AWS EC2 instance with approved Port 25 egress.

---

## Project Directory Structure

```text
kanga-route/
├── README.md                      # Primary documentation guide
├── Dockerfile                     # Python engine container image build
├── docker-compose.yml             # Local engine + dynamodb-local container stack
├── pyproject.toml                 # Package configuration
├── requirements.txt               # Dependencies (boto3, requests, dnspython, pydantic, pytest)
├── .env.example                   # Environment configuration template
│
├── bin/
│   └── kanga-route                # Host OS CLI wrapper script
│
├── systemd/
│   └── kanga-route.service        # Systemd unit file for VM boot orchestration
│
├── src/
│   └── kanga_route/
│       ├── __init__.py
│       ├── models.py              # Granular domain models and enums (ADR 0003)
│       ├── contracts.py           # Strict component interfaces (IVerificationPipeline, ICacheStore, ICRMClient)
│       ├── main.py                # Pipeline CLI runner entrypoint
│       ├── cache/
│       │   ├── __init__.py
│       │   └── dynamodb.py        # Dual-mode DynamoDBCacheStore implementation (ADR 0002)
│       ├── crm/
│       │   ├── __init__.py
│       │   └── hubspot.py         # HubSpot Contacts API v3 client
│       └── engine/
│           ├── __init__.py
│           └── verifier.py        # 4-layer verification engine implementation
│
├── tests/                         # Automated test suite (20 tests)
│   ├── test_verifier.py
│   ├── test_cache.py
│   ├── test_hubspot.py
│   └── test_main.py
│
├── packer/                        # AMI image bakery (ADR 0001)
│   ├── kanga-route.pkr.hcl
│   └── scripts/
│       └── provision.sh
│
├── infra/                         # Pulumi Infrastructure-as-Code stack
│   ├── Pulumi.yaml
│   ├── Pulumi.dev.yaml
│   ├── requirements.txt
│   └── __main__.py
│
└── docs/                          # Architecture guides & ADR records
    ├── architecture.md
    ├── roadmap.md
    ├── setup.md
    └── adr/
        ├── 0001-use-containerized-virtual-appliance.md
        ├── 0002-dual-mode-dynamodb-caching.md
        └── 0003-hubspot-granular-writebacks.md
```
