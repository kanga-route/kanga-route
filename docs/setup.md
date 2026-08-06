# Kanga-Route Setup & Operations Guide 🦘

This comprehensive guide details the setup process for HubSpot CRM, AWS infrastructure provisioning, connection methods (EC2 Instance Connect, SSM Session Manager, User Data, and SSH), and daily operation of the Kanga-Route appliance.

---

## Phase 1: HubSpot CRM Configuration

### 1. Create Custom Contact Properties
In your HubSpot portal, navigate to **Settings ⚙️ > Data Management > Properties > Contact Properties > Create Property**:

| Property Label | Internal Name (*Must Match Exactly*) | Field Type | Allowed Options / Values |
|---|---|---|---|
| **Email Verification Status** | `email_verification_status` | Dropdown Select | `Valid`, `Invalid`, `Catch-All`, `Unknown` |
| **Email Verification Reason** | `email_verification_reason` | Dropdown Select | `OK`, `Syntax_Error`, `Disposable`, `No_MX`, `User_Not_Found`, `Greylisted`, `Timeout`, `Connection_Refused`, `Unknown_Host` |
| **Mailbox Provider** | `mailbox_provider` | Single-line Text | Free text (e.g., `Google Workspace`, `Microsoft 365`) |
| **Is Role Account** | `is_role_account` | Single-line Text | `true` / `false` |
| **Last Verified** | `last_verified` | Single-line Text | ISO 8601 Datetime String |

### 2. Generate Private App Token
1. Navigate to **Settings ⚙️ > Integrations > Private Apps**.
2. Click **Create a private app**.
3. Under **Scopes**, grant the following permissions:
   - `crm.objects.contacts.read`
   - `crm.objects.contacts.write`
4. Save the app and copy your Access Token (`pat-na1-xxxxxxxx-xxxx...`).

---

## Phase 2: Domain DNS & AWS Egress Setup

Even though Kanga-Route **does not send actual email messages** (it terminates connections immediately after the `RCPT TO` socket handshake), recipient mail servers (Google Workspace, Microsoft 365) run automated real-time DNS security checks on connecting IP addresses.

To prevent mail servers from dropping connections or flagging socket checks as spam, you must configure the following **3 DNS records** on your domain (`yourdomain.com`):

### 1. DNS A Record (Forward Lookup)
In your domain registrar (e.g., Cloudflare, Route53, Namecheap, GoDaddy), create a DNS `A` record pointing your verifier hostname to your AWS Elastic IP:

| Record Type | Name / Host | Target Value | Description |
|---|---|---|---|
| **`A`** | `verifier` (or `verifier.yourdomain.com`) | `<YOUR_AWS_ELASTIC_IP>` | Maps domain hostname to your EC2 Elastic IP |

---

### 2. Reverse DNS / PTR Record (Forward-Confirmed Reverse DNS - FCrDNS)
Recipient mail servers verify that your Elastic IP resolves back to your domain hostname.
1. Open the [AWS EC2 Console > Elastic IPs](https://console.aws.amazon.com/ec2/v2/home#Addresses:).
2. Select your allocated Elastic IP.
3. Click **Actions > Edit reverse DNS**.
4. Enter `verifier.yourdomain.com` and click **Update**.

---

### 3. SPF Record (Sender Policy Framework TXT Record)
Authorize your AWS Elastic IP to announce `verify@yourdomain.com` during the SMTP handshake:

- **If you do NOT have an existing SPF record**:
  Create a `TXT` record on your root domain (`yourdomain.com`):
  ```text
  v=spf1 ip4:<YOUR_AWS_ELASTIC_IP> ~all
  ```
- **If you ALREADY have an SPF record** (e.g. for Google Workspace or Microsoft 365):
  Append `ip4:<YOUR_AWS_ELASTIC_IP>` into your existing record:
  ```text
  v=spf1 include:_spf.google.com ip4:<YOUR_AWS_ELASTIC_IP> ~all
  ```

---

### 4. AWS Outbound Port 25 Unblock Request
AWS blocks outbound TCP Port 25 by default on all EC2 accounts.
1. Open the AWS Support Console and navigate to **Request to remove email sending limitations**.
2. Select your AWS Region (`us-east-1`) and Elastic IP.
3. State: *"Outbound Port 25 is required for CRM email verification socket handshakes on our appliance."*

---

## Phase 3: Launch & Connection Methods

### Method 1: Zero-Touch Automated Launch via User Data (Recommended — No Terminal Needed!)

You can pass your HubSpot credentials directly during instance launch so the VM boots up 100% pre-configured and begins scheduled verification without needing to log in:

1. Click [**Launch Appliance in AWS Console 🚀**](https://console.aws.amazon.com/ec2/v2/home?region=us-east-1#LaunchInstances:amiId=ami-0621206b8c7bfc85c) (AMI ID: **`ami-0621206b8c7bfc85c`**).
2. Expand **Advanced Details** at the bottom of the launch page.
3. Paste the following script into **User Data**:
   ```bash
   #!/bin/bash
   cat << 'EOF' > /opt/kanga-route/.env
   HUBSPOT_ACCESS_TOKEN=pat-na1-your-actual-hubspot-token
   DYNAMODB_ENDPOINT_URL=http://dynamodb-local:8000
   DYNAMODB_TABLE_NAME=KangaRouteCache
   AWS_REGION=us-east-1
   AWS_ACCESS_KEY_ID=dummy
   AWS_SECRET_ACCESS_KEY=dummy
   EOF
   systemctl restart kanga-route.service
   ```
4. Click **Launch Instance**. The appliance will automatically initialize and execute its scheduled verification runs.

---

### Method 2: EC2 Instance Connect (1-Click Web Console Terminal)

No SSH key pairs, local terminal commands, or open inbound ports are required.

1. Open the [AWS EC2 Console](https://console.aws.amazon.com/ec2/).
2. Select your `Kanga-Route-Appliance` instance and click **Connect** in the top menu.
3. Choose the **EC2 Instance Connect** tab.
4. Click **Connect**. A terminal window will open directly in your web browser.
5. Update your token:
   ```bash
   sudo nano /opt/kanga-route/.env
   ```
6. Trigger a verification run:
   ```bash
   kanga-route run
   ```

---

### Method 3: AWS Systems Manager (SSM) Session Manager (Browser Terminal)

For enterprise security environments where inbound SSH Port 22 is completely closed:

1. In the AWS EC2 Console, select your `Kanga-Route-Appliance` instance.
2. Click **Connect > Session Manager > Connect**.
3. A secure browser shell will open. Switch to the `ubuntu` user:
   ```bash
   sudo su - ubuntu
   kanga-route status
   ```

---

### Method 4: Standard SSH Connection

1. Connect via terminal:
   ```bash
   ssh -i /path/to/key.pem ubuntu@<INSTANCE_ELASTIC_IP>
   ```
2. Edit configuration:
   ```bash
   sudo nano /opt/kanga-route/.env
   ```
3. Trigger sync:
   ```bash
   kanga-route run
   ```

---

## Phase 4: Host CLI Reference (`kanga-route`)

The host control plane CLI abstracts container operations:

- **`kanga-route run`**: Triggers an immediate verification execution batch against HubSpot.
- **`kanga-route status`**: Displays Docker container health and active systemd/cron schedules.
- **`kanga-route logs`**: Tails live verification engine logs (`docker compose logs -f engine`).
- **`kanga-route schedule "<cron_expr>"`**: Configures automated recurring execution (e.g., `kanga-route schedule "0 2 * * *"` for 2:00 AM UTC daily).