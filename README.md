![Kanga-Route Banner](banner.png)

# Kanga-Route 🦘

<p align="center">
  <a href="https://github.com/shereford"><img src="https://img.shields.io/badge/author-@shereford-blue.svg?logo=github" alt="Author"></a>
  <a href="https://github.com/kanga-route/kanga-route/blob/master/LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.9+-blue.svg" alt="Python"></a>
  <a href="https://www.docker.com/"><img src="https://img.shields.io/badge/docker-ready-2496ED.svg" alt="Docker"></a>
  <a href="https://aws.amazon.com/"><img src="https://img.shields.io/badge/AWS-AMI%20Public-FF9900.svg" alt="AWS AMI"></a>
  <a href="https://github.com/kanga-route/kanga-route/actions"><img src="https://img.shields.io/badge/tests-20%20passed-success.svg" alt="Tests"></a>
</p>

> 💎 **Zero SaaS fees. Zero hard bounces.**  
> Kanga-Route bridges the gap between sales operations and email deliverability. By running deep, 4-layer email verification (STARTTLS, Catch-All dummy checks, async provider throttling) on an isolated cloud appliance, it eliminates recurring SaaS subscription fees while protecting your domain score and keeping your HubSpot CRM operating cleanly.

---

## 🚀 Appliance Release Registry & AMI Catalog

Launch pre-built Kanga-Route virtual appliances directly into your AWS account:

| Version | Release Date | Status | AWS Region | AMI ID | Quick Launch |
|---|---|---|---|---|---|
| **`v1.0.0`** | `2026-08-06` | **Latest (Stable)** | `us-east-1` (N. Virginia) | **`ami-0621206b8c7bfc85c`** | [**Launch v1.0.0 Appliance 🚀**](https://console.aws.amazon.com/ec2/v2/home?region=us-east-1#LaunchInstances:amiId=ami-0621206b8c7bfc85c) |

> 💡 **Release Status Legend**:
> - **`Latest (Stable)`**: Newest validated production AMI build.
> - **`Archived`**: Previous historical AMI builds retained for reference.

### 📌 Programmatic Version Pinning (AWS CLI & Terraform)

For DevOps automation where hardcoding static AMI IDs is undesirable, query the public Kanga-Route registry (`603773569022`) dynamically by version tag:

```bash
# Query public AMI ID for version v1.0.0 via AWS CLI
aws ec2 describe-images \
  --owners 603773569022 \
  --filters "Name=tag:Application,Values=Kanga-Route" "Name=tag:Version,Values=1.0.0" \
  --query 'Images[0].ImageId' --output text
```

```hcl
# Dynamic Version Pinning in Terraform
data "aws_ami" "kanga_route" {
  most_recent = true
  owners      = ["603773569022"]

  filter {
    name   = "tag:Application"
    values = ["Kanga-Route"]
  }

  filter {
    name   = "tag:Version"
    values = ["1.0.0"] # Pin exact version tag
  }
}
```

> [!IMPORTANT]
> **Prerequisites**: Configure 5 custom contact properties in HubSpot and submit the AWS Port 25 unblock request before running production verifications. See the complete [Setup & Operations Guide](docs/setup.md).

---

## 🎯 Sales Operations & HubSpot CRM Impact

Kanga-Route protects company sender scores by preventing deliverability drops below HubSpot’s **5% hard bounce suspension threshold**. It automatically writes back 5 granular contact properties to trigger automated CRM workflows (such as un-enrolling contacts from Sales Sequences and assigning tasks to reps).

👉 **[Read the full HubSpot User Story & Sales Workflow Guide](docs/hubspot-user-story.md)**

---

## 📐 System Architecture

Kanga-Route runs as a containerized appliance (`verifier-engine` + `dynamodb-local`) orchestrated by systemd on a Packer-built Ubuntu VM with an isolated host CLI control plane.

👉 **[View the complete System Architecture Topology & Diagrams](docs/architecture.md)**

---

## ⚡ Feature Highlights

- **4-Layer Verification Sequence**: Syntax & Role check, 150+ Disposable Domain Blocklist, DNS MX Provider Fingerprinting, and direct TCP Port 25 SMTP Socket Handshake with STARTTLS and random dummy Catch-All detection.
- **Async Concurrency & Provider Throttling**: Provider-based `asyncio.Semaphore` rate-limiting (max 5 concurrent connections to Google/Outlook MX hosts) to prevent IP blacklisting.
- **Dual-Mode Cache Persistence**: Toggle seamlessly between local sidecar (`dynamodb-local`) and managed AWS Cloud DynamoDB with 30-day automatic TTL expiration.
- **Granular CRM Intelligence**: Pushes `email_verification_status`, `email_verification_reason`, `mailbox_provider`, `is_role_account`, and `last_verified` to HubSpot contacts.
- **Host OS Control Plane CLI**: Simple host wrapper (`kanga-route run`, `status`, `logs`, `schedule`).

---

## 📚 Documentation Index

For detailed step-by-step installation guides, architecture specifications, and operational best practices, refer to the dedicated documentation guides:

| Guide | Description | Link |
|---|---|---|
| 📜 **Changelog** | Version history, release milestones, and feature updates | [**CHANGELOG.md**](CHANGELOG.md) |
| 📖 **Setup & Operations Guide** | Step-by-step HubSpot setup, DNS records (A, PTR, SPF), AWS Console / Pulumi deployment, and connection methods | [**docs/setup.md**](docs/setup.md) |
| 🎯 **HubSpot User Story & Sales Workflow** | Deliverability protection, sequence un-enrollment workflows, and sales analytics | [**docs/hubspot-user-story.md**](docs/hubspot-user-story.md) |
| 📐 **Architecture Overview** | System layout, topology diagram, container stack, and host control plane | [**docs/architecture.md**](docs/architecture.md) |
| 🛡️ **Long-Term Use Advice** | IP reputation management, rate limiting, log rotation, and DynamoDB scaling | [**docs/long-term-use.md**](docs/long-term-use.md) |
| 🗺️ **Roadmap** | Multi-phase development milestones and feature releases | [**docs/roadmap.md**](docs/roadmap.md) |
| 📋 **ADR 0001** | Containerized Virtual Appliance (Docker + Packer) | [**docs/adr/0001-use-containerized-virtual-appliance.md**](docs/adr/0001-use-containerized-virtual-appliance.md) |
| 📋 **ADR 0002** | Dual-Mode DynamoDB Caching Strategy | [**docs/adr/0002-dual-mode-dynamodb-caching.md**](docs/adr/0002-dual-mode-dynamodb-caching.md) |
| 📋 **ADR 0003** | Granular CRM Intelligence Writebacks | [**docs/adr/0003-hubspot-granular-writebacks.md**](docs/adr/0003-hubspot-granular-writebacks.md) |

---

## 📁 Project Directory Structure

```text
kanga-route/
├── banner.png                     # Kanga-Route header banner
├── README.md                      # Primary documentation guide
├── Dockerfile                     # Python engine container image build
├── docker-compose.yml             # Local engine + dynamodb-local container stack
├── pyproject.toml                 # Package configuration
├── requirements.txt               # Dependencies
├── .env.example                   # Environment configuration template
│
├── bin/
│   └── kanga-route                # Host OS CLI wrapper script
├── systemd/
│   └── kanga-route.service        # Systemd unit file for VM boot orchestration
├── src/
│   └── kanga_route/               # Engine source code (verifier, cache, crm, main)
├── tests/                         # Automated test suite (20 tests passing)
├── packer/                        # AMI image bakery (kanga-route.pkr.hcl)
├── infra/                         # Pulumi Infrastructure-as-Code stack
└── docs/                          # Dedicated setup, user story, architecture & ADR guides
```

---

## 👤 Author & Maintainer

Designed and maintained by [@shereford](https://github.com/shereford). Feedback, issues, and pull requests are welcome!
