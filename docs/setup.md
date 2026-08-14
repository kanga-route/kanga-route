# Kanga-Route Setup & Operations Guide

This guide takes a new Kanga-Route appliance from a clean launch to a
scheduled HubSpot verification run.

## 1. Configure HubSpot

### Create the five contact properties

In **Settings > Data Management > Properties**, select **Contact properties**
and create these properties with the exact internal names and values below.

| Label | Internal name | Type | Values |
|---|---|---|---|
| Email Verification Status | `email_verification_status` | Dropdown select | `Valid`, `Invalid`, `Catch-All`, `Unknown` |
| Email Verification Reason | `email_verification_reason` | Dropdown select | `OK`, `Syntax_Error`, `Disposable`, `No_MX`, `User_Not_Found`, `Greylisted`, `Timeout`, `Connection_Refused`, `Unknown_Host`, `DNS_Timeout`, `DNS_Error`, `SMTP_Temporary_Failure`, `SMTP_Rejected` |
| Mailbox Provider | `mailbox_provider` | Single-line text | Free text |
| Is Role Account | `is_role_account` | Single-line text | `true` or `false` |
| Last Verified | `last_verified` | Date and time picker | Datetime |

The `last_verified` property must be a HubSpot datetime property. Kanga-Route
writes Unix epoch milliseconds so it can search for stale contacts and verify
them again after the configured interval.

### Create a private app

1. Open **Settings > Integrations > Private Apps**.
2. Create a private app with `crm.objects.contacts.read` and
   `crm.objects.contacts.write`.
3. Copy its access token. Store it only in `/opt/kanga-route/.env` or a
   managed secret workflow; never commit it or bake it into an AMI.

Kanga-Route fetches contacts with no verification status; `Unknown` contacts
whose timestamp is missing or older than `UNKNOWN_RETRY_AFTER_HOURS`; and any
contact with a `last_verified` value older than `REVERIFY_AFTER_DAYS`.

## 2. Configure the SMTP identity and AWS egress

Kanga-Route stops after the SMTP `RCPT TO` check and never sends a message
body, but recipient servers still inspect the connecting IP and SMTP identity.

Before a production run:

1. Allocate an Elastic IP for the appliance.
2. Create an A record such as `verifier.example.com` pointing to that IP.
3. Configure the Elastic IP's reverse DNS/PTR to the same hostname.
4. Authorize the IP for the envelope address, such as
   `verify@example.com`, in your existing SPF record.
5. Ask AWS to remove the outbound port 25 restriction for the account, region,
   and Elastic IP.

Then configure the exact hostname and address as `SMTP_HELO_DOMAIN` and
`SMTP_MAIL_FROM`. The shipped `.invalid` values are fail-safe placeholders;
the engine refuses to run until they are replaced.

## 3. Launch the appliance

Use a private AMI candidate built from the current commit, or a later promoted
release. Pass that appliance AMI ID to the Pulumi stack:

```bash
cd infra
python -m venv venv
. venv/bin/activate
pip install -r requirements.txt
pulumi stack init dev
pulumi config set aws:region us-east-1
pulumi config set kanga-route-infra:amiId ami-0123456789abcdef0
pulumi up
```

`amiId` is required. The stack deliberately refuses to substitute a plain
Ubuntu image. SSH is disabled by default; use SSM Session Manager. If SSH is
required, set a restricted CIDR such as
`pulumi config set kanga-route-infra:sshCidr 203.0.113.10/32`.

### Configure the instance

Connect with SSM Session Manager (recommended), EC2 Instance Connect when it is
available, or restricted SSH. Start from the installed template:

```bash
sudo cp /opt/kanga-route/.env.example /opt/kanga-route/.env
sudo chmod 600 /opt/kanga-route/.env
sudoedit /opt/kanga-route/.env
```

At minimum, set:

```dotenv
HUBSPOT_ACCESS_TOKEN=pat-na1-your-private-app-token
SMTP_HELO_DOMAIN=verifier.example.com
SMTP_MAIL_FROM=verify@example.com
USE_LOCAL_DB=true
DYNAMODB_TABLE_NAME=KangaRouteCache
AWS_REGION=us-east-1
BATCH_SIZE=100
REVERIFY_AFTER_DAYS=30
CACHE_TTL_DAYS=30
UNKNOWN_RETRY_AFTER_HOURS=48
```

Do not put a HubSpot token in EC2 User Data: instance User Data is retrievable
through AWS APIs. After saving the file:

```bash
sudo systemctl restart kanga-route.service
sudo systemctl restart kanga-route-run.timer
sudo kanga-route run
```

The one-shot run exits nonzero when required configuration, DynamoDB, HubSpot,
or CRM writeback fails. A successful run writes results back to HubSpot.

### Enable the browser console

The browser-based single-address console is disabled by default. To opt in,
add the following to `/opt/kanga-route/.env` and restart the stack:

```dotenv
ENABLE_WEB_UI=true
KANGA_ROUTE_WEB_PORT=8080
```

```bash
sudo systemctl restart kanga-route.service
```

The port is published only on appliance loopback. Use SSM port forwarding and
open `http://127.0.0.1:8080/` on the operator workstation. Do not add an EC2
ingress rule or change the Compose address binding. This first console has no
authentication endpoint; any non-loopback or authenticated deployment is
blocked until the TLS/authentication design is complete.

For one verification without a browser, run:

```bash
sudo kanga-route verify person@example.com
```

See [Browser Console](browser-console.md) for the SSM command, API contract,
limits, statuses, reasons, and security behavior.

### Managed DynamoDB mode

The default local mode uses the persistent DynamoDB Local volume. To use
managed DynamoDB and the EC2 instance role instead:

```dotenv
USE_LOCAL_DB=false
DYNAMODB_ENDPOINT_URL=
DYNAMODB_TABLE_NAME=KangaRouteCache
AWS_REGION=us-east-1
```

The table is created on first use and its `ttl` attribute is enabled for
automatic expiry. Cloud appliance mode requires an attached EC2 IAM instance
role with DynamoDB table and TTL permissions. Compose deliberately does not
forward `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, or
`AWS_SESSION_TOKEN` from the host.

## 4. Operate the appliance

The Packer image enables a persistent daily systemd timer. Missed runs execute
after the next boot, and randomized delay avoids every appliance starting at
exactly midnight.

```bash
# Run immediately and wait for completion
sudo kanga-route run

# Inspect cache stack, service, timer, and next execution
kanga-route status

# Follow verification history and live logs in journald
sudo kanga-route logs

# Change to 02:00 UTC daily (systemd OnCalendar syntax)
sudo kanga-route schedule "*-*-* 02:00:00 UTC"
```

Only one verification run can execute at a time; a system-level file lock
prevents overlapping manual and timer invocations.

## 5. Interpret results safely

- `Invalid` is reserved for authoritative syntax, disposable-domain, no-mail,
  or explicit recipient-not-found evidence.
- `Catch-All` means the server accepted a randomized nonexistent recipient.
- `Unknown` covers DNS timeouts, greylisting, connection failures, ambiguous
  SMTP policy rejections, and other transient outcomes. These results are
  visible in HubSpot but never cached; the retry cooldown keeps them eligible
  later without letting the same cohort monopolize every scheduled batch.
- Multiple MX hosts are tried for transient connection failures.
