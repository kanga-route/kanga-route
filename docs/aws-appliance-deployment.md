# Deploy Kanga-Route in a new AWS environment

> **Please do not skim this guide. Budget about 45–75 minutes for the hands-on
> setup.** Kanga-Route ties together an AMI, a region, VPC address ranges, DNS,
> TLS, an Elastic IP, and an SMTP identity. A plausible-looking value entered in
> the wrong field—or doing the DNS steps out of order—can leave you with a stack
> that is easier to delete and recreate than repair. Read each step completely,
> collect the values in the worksheet, and then click **Next**. DNS propagation,
> certificate validation, and AWS's outbound-port-25 review can add waiting time
> beyond the 45–75 minute setup window.

This guide deploys the companion
[`cloudformation/kanga-route-appliance.yaml`](../cloudformation/kanga-route-appliance.yaml)
template. It assumes you are relatively new to AWS and explains each value you
must provide.

## What the stack builds

The template creates:

- a dedicated VPC with a configurable private IPv4 CIDR;
- two public subnets in different Availability Zones, an internet gateway, and
  routing;
- one EC2 instance from the Kanga-Route AMI, one Elastic IP, and encrypted root
  storage;
- an EC2 role for browser-based administration through Systems Manager Session
  Manager—no SSH key or inbound SSH rule;
- the local DynamoDB cache and browser UI already included in the appliance;
- Nginx on the appliance as a private reverse proxy to the loopback-only UI;
- an internet-facing Application Load Balancer (ALB), HTTPS certificate, and
  Route 53 UI record;
- a Cognito user pool, hosted sign-in page, mandatory TOTP MFA, and one invited
  administrator; and
- security groups that keep the EC2 instance closed by default.

The template deliberately does **not** create the final inbound rule from the
ALB to the appliance. That one security-group change is the activation switch
for the public UI. Until you make it, the instance has no inbound rules.

The stack does not register a domain, approve outbound SMTP for your account,
or create reverse DNS. Those are account-level or registrar operations and are
covered below.

## Before you begin

### Expected cost

This is not a free-tier-only deployment. It creates billable resources,
including an EC2 instance, public IPv4 address, Application Load Balancer,
EBS volume, Route 53 hosted zone/domain, and potentially Cognito usage. Review
the current AWS pricing for the region you choose and delete the stack when you
finish testing.

### Permissions

Sign in to the AWS account that will own the appliance. The identity creating
the stack must be allowed to create CloudFormation, EC2, Elastic Load Balancing,
IAM, Route 53, ACM, Cognito, and Systems Manager resources. For a short-lived
test in your own account, an administrator identity is the simplest route. In a
managed company account, ask the AWS administrator to deploy the stack or
provide a CloudFormation execution role with those permissions.

The deployment creates an IAM role, so CloudFormation will ask you to
acknowledge **I acknowledge that AWS CloudFormation might create IAM
resources**.

### Region: choose it before creating the stack

An AWS region is the geographic AWS location that owns the AMI, EC2 instance,
VPC, load balancer, certificate, and Cognito pool. CloudFormation cannot accept
a parameter that moves a stack to another region.

1. In the AWS console, look at the region selector in the upper-right corner.
2. Choose the region that contains the Kanga-Route AMI—for example,
   **US East (N. Virginia) us-east-1**.
3. Leave the console in this region throughout the deployment.

If you change regions later, you will see a different set of AMIs, VPCs,
instances, certificates, and stacks. The template displays the selected region
as a stack output so you can verify it afterward.

## Step 1: obtain or register a domain

A real domain is required for the public HTTPS UI and for credible direct SMTP
verification. A placeholder such as `example.com` or a name ending in
`.invalid` is suitable only for local smoke tests; it cannot provide public
TLS, forward DNS, or matching reverse DNS.

If you already own a domain and have its public Route 53 hosted zone, continue
to the next section.

To register a new domain in Route 53:

1. In the AWS console search bar, enter **Route 53**, then open it.
2. In the left navigation choose **Registered domains**.
3. Choose **Register domains** and search for an available name.
4. Select a name, choose a registration duration, enter accurate registrant
   contact details, enable automatic renewal if desired, and complete payment.
5. Confirm any verification email AWS sends. An unverified registrant email can
   suspend the domain.
6. Open **Route 53 → Hosted zones** and verify that a **Public hosted zone** now
   exists for the domain.

Domain registration is deliberately outside CloudFormation: registering a
domain is a purchase and establishes ownership/contact records that should not
be hidden inside an infrastructure stack.

If the domain is registered elsewhere, either delegate it to a Route 53 public
hosted zone by updating the registrar's name servers or move its DNS hosting to
Route 53 before continuing. The template's automatic certificate validation
requires the public hosted zone to be in the same AWS account as this stack.

## Step 2: fill in the deployment worksheet

Write down the following values before opening CloudFormation. The example
values use the fictional `example.com`; replace every one with your own value.

| Stack field | What it means | Where to find or choose it | Example |
| --- | --- | --- | --- |
| **Region** | AWS location for the entire stack. It is selected in the console, not entered into the template. | Console region selector, upper right. It must contain the AMI. | `us-east-1` |
| **Kanga-Route AMI ID** | Machine image used to launch the appliance. AMI IDs are region-specific. | **EC2 → AMIs**. Change **Owned by me** to the appropriate ownership filter, select the tested Kanga-Route image, and copy **AMI ID** from Details. | `ami-0123456789abcdef0` |
| **Instance type** | CPU and memory assigned to the appliance. | Choose from the template list. Start with `t3.micro`; use `t3.small` or `t3.medium` for larger workloads. | `t3.micro` |
| **VPC IPv4 CIDR** | Private address space for the new isolated network. | Choose an unused RFC 1918 range. The default is normally safe for a standalone deployment. | `10.42.0.0/16` |
| **Public subnet 1 CIDR** | Slice of the VPC used by the appliance and one ALB node. | Use a non-overlapping subnet fully inside the VPC range. | `10.42.1.0/24` |
| **Public subnet 2 CIDR** | Second VPC slice used by the ALB in another Availability Zone. | Use a different non-overlapping subnet fully inside the VPC range. | `10.42.2.0/24` |
| **Browsers allowed to reach the load balancer** | Source IPv4 CIDR for the ALB's ports 80 and 443. This does not expose the instance. | For only your current network, search the web for “what is my IP” and append `/32`. For any internet user to reach the Cognito sign-in page, use `0.0.0.0/0`. | `203.0.113.10/32` |
| **Route 53 public hosted zone ID** | Identifier of the DNS zone that contains the UI hostname. This is not the domain name. | **Route 53 → Hosted zones → your domain**. Copy **Hosted zone ID** from **Hosted zone details**. | `Z0123456789EXAMPLE` |
| **Browser UI hostname** | Public HTTPS name users will open. It must be inside the selected hosted zone and not already be used by another record. | Choose a new lowercase subdomain. | `route.example.com` |
| **Cognito domain prefix** | Unique label for the AWS-hosted login endpoint. It is not your UI hostname and must be globally unique within the region. | Choose 3–63 lowercase letters, digits, or hyphens. Add your organization and a random suffix if the name is taken. | `acme-kanga-route-7f3a` |
| **Initial UI administrator email** | Address that receives the temporary Cognito password. | Use an inbox you can access now. | `engineer@example.com` |
| **SMTP HELO hostname** | Public name the verifier announces to receiving mail servers. | Choose a second new lowercase hostname under your domain. Do not reuse the UI hostname. | `verifier.example.com` |
| **SMTP MAIL FROM address** | Envelope sender identity used during SMTP probes; Kanga-Route does not send a message body. | Choose an address at a domain you control. A mailbox password is not needed. | `verify@example.com` |

### CIDR rules in plain language

CIDR values describe IP address ranges. Keep the defaults unless the new VPC
will later connect to another network that already uses `10.42.0.0/16`.

If you change them:

- use a private range beginning with `10.`, `172.16` through `172.31`, or
  `192.168`;
- put both subnet ranges inside the VPC range;
- do not let the two subnet ranges overlap; and
- do not reuse ranges from a network you plan to connect through peering, a VPN,
  or Transit Gateway.

For example, VPC `10.90.0.0/16` with subnets `10.90.1.0/24` and
`10.90.2.0/24` is valid. If CloudFormation reports that a subnet is not within
the VPC or overlaps another subnet, delete the failed stack and correct the
worksheet before retrying.

## Step 3: create the CloudFormation stack

1. Download
   [`cloudformation/kanga-route-appliance.yaml`](../cloudformation/kanga-route-appliance.yaml)
   from this repository to your computer.
2. Confirm the AWS console still shows the worksheet's **Region** in the upper
   right.
3. Search for **CloudFormation** and open it.
4. Choose **Stacks**, then **Create stack → With new resources (standard)**.
5. Under **Prerequisite – Prepare template**, select **Choose an existing
   template**.
6. Under **Specify template**, select **Upload a template file**, choose the
   downloaded YAML file, and choose **Next**.
7. For **Stack name**, enter `kanga-route` or another short name using letters,
   numbers, and hyphens.
8. Enter every parameter from the worksheet. Stop and re-check the AMI, hosted
   zone, UI hostname, administrator email, and all three CIDRs before choosing
   **Next**.
9. On **Configure stack options**, keep the defaults unless your organization
   requires tags or a specific IAM execution role. Choose **Next**.
10. Review the parameters. Under **Capabilities**, check **I acknowledge that
    AWS CloudFormation might create IAM resources**.
11. Choose **Submit**.
12. Stay on the **Events** tab until the stack reaches `CREATE_COMPLETE`. A
    normal deployment can take 10–20 minutes. The certificate step may wait
    longer if the hosted zone and UI hostname do not match.

Do not add the final security-group rule while the stack is still creating.
CloudFormation intentionally reports the ALB target as unhealthy until the
activation step near the end of this guide.

### If creation fails

Select the first resource with `CREATE_FAILED` on the **Events** tab and read
its **Status reason**. Common causes are:

- the AMI ID exists in a different region or was not shared with this account;
- the selected hosted zone does not contain the UI hostname;
- the Cognito domain prefix is already taken;
- the subnet CIDRs overlap or are outside the VPC CIDR; or
- an organization policy blocks one of the requested resources.

Fix the worksheet value. If CloudFormation rolled the stack back, choose
**Delete** and wait for `DELETE_COMPLETE` before creating it again. Reusing the
same stack name while deletion is still running will fail.

## Step 4: save the stack outputs

After `CREATE_COMPLETE`, open the stack's **Outputs** tab and save these values:

- `DeploymentRegion`
- `ApplianceInstanceId`
- `ApplianceElasticIpAddress`
- `ApplianceSecurityGroupId`
- `LoadBalancerSecurityGroupId`
- `UiUrl`
- `CognitoUserPoolId`
- `SessionManagerCommand`
- `PrivateUiTunnelCommand`

These are generated values, not secret credentials. Do not publish operational
details such as your public IP, user-pool ID, or instance ID unless necessary.

## Step 5: create the SMTP forward-DNS record

The appliance needs its SMTP hostname to resolve to its stable Elastic IP.

1. Open **Route 53 → Hosted zones → your domain**.
2. Choose **Create record**.
3. For **Record name**, enter only the label portion of your SMTP HELO hostname.
   For `verifier.example.com` in the `example.com` zone, enter `verifier`.
4. Set **Record type** to **A – Routes traffic to an IPv4 address**.
5. Leave **Alias** off.
6. In **Value**, paste `ApplianceElasticIpAddress` from the stack Outputs.
7. Leave TTL at `300` and choose **Create records**.

Do not create this record for the UI hostname; the stack already created that
record as an alias to the ALB.

## Step 6: request outbound port 25 and matching reverse DNS

AWS blocks public outbound TCP port 25 from EC2 by default. Direct SMTP
verification cannot work until AWS removes that block for this account and
region.

Use AWS's **Request to remove email sending limitations** form. In the request:

- select the exact `DeploymentRegion` from the Outputs;
- provide the Elastic IP from `ApplianceElasticIpAddress`;
- explain that Kanga-Route performs low-volume recipient verification handshakes
  and does not transmit email message bodies; and
- request reverse DNS (PTR) for the Elastic IP, pointing to the exact
  `SmtpHeloDomain` entered in the stack.

The A record from Step 5 must already resolve to the Elastic IP before AWS can
approve matching reverse DNS. Approval time is controlled by AWS and is not
part of the 45–75 minute hands-on estimate.

After approval, verify **EC2 → Elastic IP addresses → select the appliance
address** shows the intended reverse DNS name. Forward and reverse values must
match:

```text
verifier.example.com  A    203.0.113.25
203.0.113.25          PTR  verifier.example.com
```

The addresses above are documentation examples only.

### Publish SPF carefully

Publish an SPF TXT policy for the domain used by `SmtpMailFrom`. If the domain
already has an SPF record, update that record with someone who manages your
mail DNS—never publish two separate `v=spf1` records at one name. A simple
dedicated-domain policy can authorize the appliance Elastic IP, but the exact
record depends on the rest of your organization's mail senders.

## Step 7: connect without SSH and verify the appliance

The stack creates no SSH key and no inbound port 22 rule. Use Session Manager:

1. Open **EC2 → Instances** in the stack region.
2. Select the instance whose ID matches `ApplianceInstanceId`.
3. Choose **Connect → Session Manager → Connect**.
4. If the Session Manager button is not immediately enabled, wait five minutes
   for the agent and IAM role to register, then refresh.

In the browser shell run:

```bash
sudo systemctl status kanga-route.service --no-pager
sudo systemctl status nginx.service --no-pager
sudo docker compose --project-directory /opt/kanga-route ps
curl --fail --silent http://127.0.0.1:8080/healthz
```

The last command should return a successful health response. The scheduled
HubSpot timer is disabled by the stack so it cannot run before you add a real
HubSpot token.

For logs:

```bash
sudo journalctl -u kanga-route.service --no-pager -n 100
```

## Step 8: privately test the browser UI first

This step validates the application before you make the public UI reachable.
It requires the AWS CLI and the Session Manager plugin on your computer.

1. In CloudFormation Outputs, copy `PrivateUiTunnelCommand`.
2. Run it in a terminal authenticated to the deployment account.
3. Leave that terminal running.
4. Open `http://localhost:8080/` in your browser.
5. Enter a single test email address and confirm the page returns a structured
   result.
6. Press `Ctrl+C` in the terminal to close the tunnel.

The local tunnel is intentionally HTTP because traffic stays inside the
authenticated Systems Manager session. The public route created later is
always HTTPS and always authenticated by Cognito.

SMTP results will remain incomplete or `Unknown` while AWS blocks port 25 or
before the A/PTR identity is correct. That is expected; it does not mean the UI
is broken.

## Step 9: optionally configure scheduled HubSpot processing

The one-address browser test does not require HubSpot. To enable HubSpot batch
processing, first follow [Setup and operations](setup.md) to create the exact
HubSpot properties and private app.

Then open a Session Manager shell and edit the root-owned environment file:

```bash
sudoedit /opt/kanga-route/.env
```

Set `HUBSPOT_ACCESS_TOKEN` to the private-app token and adjust batch/schedule
settings as described in the operations guide. Never place the token in a
CloudFormation parameter, stack output, command history, issue, or log.

After validating a manual run, enable the schedule:

```bash
sudo kanga-route run
sudo systemctl enable --now kanga-route-run.timer
sudo systemctl list-timers kanga-route-run.timer
```

## Final step: make the Cognito-protected UI public

At this point CloudFormation has already built the VPC, HTTPS certificate, DNS
record, load balancer, Cognito login, MFA requirement, reverse proxy, and both
security groups. Your only activation action is to let the ALB reach port 80 on
the appliance.

1. Open **EC2 → Security Groups** in `DeploymentRegion`.
2. Search for the exact `ApplianceSecurityGroupId` from stack Outputs and select
   it.
3. Open **Inbound rules → Edit inbound rules → Add rule**.
4. Set **Type** to **Custom TCP**.
5. Set **Port range** to `80`.
6. For **Source**, choose **Custom**, then paste or select the exact
   `LoadBalancerSecurityGroupId` from stack Outputs.
7. For **Description**, enter `HTTPS ALB reverse proxy only`.
8. Confirm the source starts with `sg-`. If it says `0.0.0.0/0`, a public IP, or
   a CIDR, stop and correct it.
9. Choose **Save rules**.

Never open port `8080` on the instance, never open instance port `80` to
`0.0.0.0/0`, and never add port `22`. Only the load balancer security group
should be able to reach instance port 80.

Wait one to three minutes, then:

1. Open **EC2 → Target Groups**, select the stack's target group, and confirm
   the appliance target becomes **Healthy**.
2. Open `UiUrl` from the stack Outputs. Use the hostname, not the raw ALB DNS
   name or Elastic IP.
3. Cognito will prompt the initial administrator to use the temporary password
   sent to `AdminEmail`, choose a permanent password, and enroll a TOTP
   authenticator.
4. After sign-in, test one email address again.

There is no application-authentication path outside TLS: port 80 on the ALB
only redirects to HTTPS, Cognito authentication occurs on the HTTPS listener,
and the appliance's port 8080 remains bound to loopback.

To take the public UI offline without deleting the appliance, delete only the
TCP 80 inbound rule you just added to `ApplianceSecurityGroupId`.

## Final validation checklist

- [ ] The CloudFormation stack is `CREATE_COMPLETE` in the intended region.
- [ ] The instance has one Elastic IP and no public inbound rules except TCP 80
      sourced from the ALB security group.
- [ ] The UI hostname opens with a valid HTTPS certificate and redirects to
      Cognito before showing the application.
- [ ] The administrator enrolled TOTP MFA.
- [ ] The SMTP HELO A record resolves to the appliance Elastic IP.
- [ ] The Elastic IP PTR record resolves back to the same HELO hostname.
- [ ] AWS approved outbound port 25 in this account and region.
- [ ] SPF is correct and there is only one SPF record at the relevant name.
- [ ] A single-address browser test works.
- [ ] If HubSpot is enabled, a manual run succeeds before the timer is enabled.

## Troubleshooting

### The stack is waiting on the certificate

Confirm `UiDomainName` is inside the Route 53 public zone selected by
`HostedZoneId`, and that both belong to this AWS account. Do not manually edit
the validation record CloudFormation creates. Certificate issuance and DNS
propagation can take time.

### The UI shows 503 or the target is unhealthy

Confirm the final appliance inbound rule is TCP 80 with
`LoadBalancerSecurityGroupId`—not a CIDR—as its source. Then use Session Manager
to check the `kanga-route` and `nginx` services and curl `/healthz` as shown in
Step 7.

### Cognito says the domain prefix is unavailable

The prefix is globally unique within an AWS region. Delete the failed stack,
add a short random suffix to `CognitoDomainPrefix`, and deploy again.

### Session Manager is unavailable

Confirm you are viewing the correct region and instance, the instance is
running, the attached IAM role includes `AmazonSSMManagedInstanceCore`, and the
instance can reach HTTPS through its public route and Elastic IP. Wait several
minutes after first boot.

### SMTP checks time out

Confirm AWS approved outbound port 25 for the exact account and region, the
instance security group still permits outbound TCP 25, and A/PTR records match.
Some receiving servers intentionally defer or block verification probes, so an
`Unknown` result can still be correct behavior.

## Delete the test environment safely

If AWS configured reverse DNS for the Elastic IP, remove that reverse-DNS
association first in **EC2 → Elastic IP addresses** or through the AWS support
process. An Elastic IP with reverse DNS can fail to release and block stack
deletion.

Then open **CloudFormation → Stacks**, select the stack, and choose **Delete**.
Wait for `DELETE_COMPLETE` and verify the EC2 instance, load balancer, Elastic
IP, and VPC are gone.

Deleting the stack does not delete the source AMI or its snapshots, your
registered domain, or unrelated DNS records. Delete those separately only if
you are certain they are no longer needed.

## AWS references

- [Registering a new domain with Route 53](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/domain-register.html)
- [CloudFormation ACM DNS validation](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-certificatemanager-certificate.html)
- [Authenticate ALB users with Cognito](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/listener-authenticate-users.html)
- [Connect to an instance with Session Manager](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-sessions-start.html)
- [EC2 port 25 restriction](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-resource-limits.html)
- [Elastic IP reverse DNS](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/Using_Elastic_Addressing_Reverse_DNS.html)
