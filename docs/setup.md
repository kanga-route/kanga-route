# Kanga-Route Setup & Operations Guide

## Phase 1: HubSpot Configuration
1. Create the necessary custom contact properties in HubSpot:
   * **Email Verification Status**
   * **Email Verification Reason**
   * **Mailbox Provider**
   * **Is Role Account**
   * **Last Verified** 
2. Navigate to **Settings > Integrations > Private Apps**
3. Create a new app granting `crm.objects.contacts.read` and `crm.objects.contacts.write` scopes
4. Save the Access Token

---

## Phase 2: AWS Networking & Security
1. Allocate an **Elastic IP** in the AWS EC2 Console
2. Create an **A record** in your DNS provider pointing to the Elastic IP (e.g., `verifier.yourdomain.com`)
3. Update the **Reverse DNS (rDNS)** on the Elastic IP in AWS to match your new A record
4. Submit the *Request to remove email sending limitations* form in the AWS Support Console to unblock outbound TCP Port 25

---

## Phase 3: Deployment Options

### Option A: AWS Web Console Deployment (No IaC Required)
1. **Bake the AMI Image with Packer:**
   ```bash
   packer init packer/kanga-route.pkr.hcl
   packer build packer/kanga-route.pkr.hcl
   ```
2. **Launch from AWS EC2 Console:**
   * Open the AWS Console and navigate to **EC2 > AMIs > Owned by me**
   * Select `Kanga-Route-Appliance` and click **Launch instance from AMI**
   * Select instance type `t3.micro` or `t4g.micro`
   * Select an SSH key pair
   * Create a Security Group allowing SSH (Port 22) and outbound Port 25 (SMTP), Port 53 (DNS), Port 443 (HTTPS), and Port 80
3. **Attach Elastic IP & Configure Token:**
   * Associate your allocated Elastic IP with the new instance
   * SSH into the instance: `ssh ubuntu@<ELASTIC_IP>`
   * Edit `/opt/kanga-route/.env` and insert your `HUBSPOT_ACCESS_TOKEN`

### Option B: Automated Pulumi IaC Deployment
1. Navigate to `infra/` and run `pulumi stack init dev`
2. Configure stack variables: `pulumi config set kanga-route-infra:amiId <YOUR_AMI_ID>`
3. Run `pulumi up` to provision VPC, Subnet, Security Group, Elastic IP, and EC2 instance automatically.

---

## Phase 4: Operations & CLI
Kanga-Route ships with a global CLI tool that acts as a wrapper for the underlying Docker containers.

**Run a Manual Sync:** 
```bash 
kanga-route run
  ```
  (Executes a one-off Docker container run to immediately process HubSpot contacts).

** Check Status: **
```bash
kanga-route status
```
*(Displays if the DynamoDB container is healthy and shows the current cron schedule)*

** View Logs: **
```bash
kanga-route logs
```
*(Tails the Docker Compose logs for debugging SMTP timeouts or API limits)*

** Update Schedule: **
```bash
kanga-route schedule "0 2 * * *"
```
*(Updates the host OS cron job to trigger the Docker run automatically)*