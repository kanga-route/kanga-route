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

## Phase 3: Deployment
1. Use the provided Pulumi stack (or your preferred IaC) to deploy the Kanga-Route AMI to an EC2 instance (`t3.micro` or `t4g.micro`)
2. Ensure the Security Group allows outbound TCP Port 25 (SMTP), Port 53 (DNS), and Port 443 (HTTPS)
3. SSH into the newly provisioned instance
4. Open `/opt/kanga-route/.env` and insert your HubSpot Private App Token

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