# Kanga-Route Development Roadmap

## Phase 1: The Engine (Python & Dockerfile)
* Draft the `requirements.txt` (`boto3`, `requests`, `dnspython`)
* Build the 4-layer verification script (Regex, Blocklist, DNS, SMTP Socket)
* Build the DynamoDB cache connector with the local/cloud toggle logic
* Write the Dockerfile to containerize the Python engine
* **Milestone:** The engine runs successfully on a local workstation using `docker run`

---

## Phase 2: The Orchestration (Docker Compose & Bash)
* Write the `docker-compose.yml` defining the engine and the `dynamodb-local` sidecar
* Write the `kanga-route` bash CLI wrapper to abstract Docker commands for the end-user
* Write the systemd service files to handle auto-starting the containers on boot
* **Milestone:** `docker compose up -d` brings the entire system online locally

---

## Phase 3: The Bakery (Packer)
* Write the `.hcl` Packer template targeting multiple builders (AWS AMI, ISO, etc.)
* Configure provisioners to install Docker, copy the compose stack, and enable the systemd services
* **Milestone:** GitHub Actions successfully builds the Docker-in-AMI image and registers it

---

## Phase 4: The Infrastructure (Pulumi)
* Write the Pulumi stack to provision the VPC, EC2 instance, Elastic IP, and Security Groups
* Define the IAM Instance Profile for optional AWS DynamoDB routing
* **Milestone:** `pulumi up` deploys the production-ready appliance to AWS
