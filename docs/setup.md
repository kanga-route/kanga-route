# Kanga-Route Setup & Deployment Guide

This guide covers the end-to-end setup for the Kanga-Route virtual appliance, including HubSpot configuration, AWS network requirements, and CLI usage.

## Phase 1: HubSpot Configuration

Before booting the appliance, you must prepare your HubSpot CRM to receive the verification data.

1. **Create Custom Contact Properties:**
   Navigate to Settings > Properties > Contact Properties and create the following exact properties:
   * `Email Verification Status` (Internal: `email_verification_status`) - Type: Dropdown (`Valid`, `Invalid`, `Catch-All`, `Unknown`)
   * `Email Verification Reason` (Internal: `email_verification_reason`) - Type: Dropdown (`Syntax_Invalid`, `Disposable_Domain`, `DNS_No_MX`, `SMTP_User_Not_Found`, `SMTP_Greylisted`, `SMTP_Timeout`)
   * `Mailbox Provider` (Internal: `mailbox_provider`) - Type: Dropdown (`Google Workspace`, `Microsoft 365`, `Other`, `None`)
   * `Is Role Account` (Internal: `is_role_account`) - Type: Single Checkbox (Yes/No)
   * `Last Verified` (Internal: `last_verified`) - Type: Date picker

2. **Generate API Token:**
   Navigate to Settings > Integrations > Private Apps. Create an app with `crm.objects.contacts.read` and `crm.objects.contacts.write` scopes. Copy the Access Token.

---

## Phase 2: AWS Networking Prep (Crucial)

To perform real SMTP handshakes, AWS must allow outbound traffic on Port 25. 

1. **Allocate an Elastic IP:** In the AWS EC2 Console, allocate a new Elastic IP address.
2. **Set Reverse DNS (rDNS):** Create an `A` record in your DNS provider (e.g., `verifier.yourdomain.com`) pointing to your Elastic IP. In AWS, update the rDNS of the Elastic IP to match this domain.
3. **Request Port 25 Unblock:** Open an AWS Support Ticket requesting the removal of email sending limitations. Provide the Elastic IP, the rDNS record, and state you are running a B2B email hygiene appliance to prevent hard bounces.

---

## Phase 3: Appliance Initialization

Once deployed via the provided Packer/Pulumi stack (or manual EC2 launch using the Kanga-Route AMI):

1. SSH into the EC2 instance.
2. Open the configuration file: `sudo nano /etc/kanga-route/.env`
3. Populate the required variables:

HUBSPOT_ACCESS_TOKEN=pat-na1-xxxxxxxx-xxxx
USE_LOCAL_DB=true
DYNAMODB_TABLE_NAME=email-verification-cache
AWS_REGION=us-east-1
SMTP_SENDER_EMAIL=verifier@yourdomain.com

---

## Phase 4: First Run & CLI Operations

Kanga-Route ships with a global CLI tool (`kanga-route`) for easy management. Upon initial setup, you should trigger a manual run to initialize the database and perform your first sync.

**1. Trigger the First Run:**
`kanga-route run`
*This bypasses the schedule, initializes the local DynamoDB table if it is missing, pages through HubSpot, and immediately starts verifying contacts. Check your HubSpot CRM to confirm properties are updating.*

**2. Check System Status:**
`kanga-route status`
*Displays the status of the local DynamoDB service and the current cron schedule.*

**3. Update the Automated Schedule:**
`kanga-route schedule "0 2 * * *"`
*Updates the underlying OS cron job. Accepts standard cron expressions. The default recommendation is nightly at 2:00 AM server time.*

**4. View Logs (Troubleshooting):**
If you need to debug SMTP timeouts or HubSpot API limits, the CLI outputs directly to the system log:
`tail -f /var/log/kanga-route.log`