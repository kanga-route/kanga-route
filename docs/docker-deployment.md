# Run Kanga-Route on a User-Managed Docker Host

This is a supported deployment shape for operators who want Kanga-Route on
their own Linux host, on premises, or in a cloud that does not yet have a
published appliance image. Today it builds from a repository checkout. DIST-02
on the [roadmap](roadmap.md#dist-02--publish-immutable-oci-images-and-a-compose-release-bundle)
will replace that requirement with published images and a downloadable bundle.

The operator owns the host, patching, scheduling, backups, TLS exposure, and
SMTP network identity. Kanga-Route owns the same application contracts and
result semantics used by the AMI.

## Network requirements

Verification opens outbound TCP connections to recipient MX servers on port
25. It does not require inbound port 25 and does not receive or relay message
bodies.

Docker bridge networking is supported and normally preferred. The recipient
sees the public address of the Docker host or its upstream NAT gateway. Do not
switch to host networking merely to run SMTP probes.

Before real verification, the operator must provide:

- outbound TCP 25 from the host or NAT gateway;
- a stable public source address;
- PTR and forward DNS that agree with that address;
- an `SMTP_HELO_DOMAIN` resolving to that address; and
- an `SMTP_MAIL_FROM` at a domain the operator controls, with an appropriate
  SPF policy.

Cloud providers and ISPs may block TCP 25 or control reverse DNS separately.
Resolve those restrictions with the network owner; containers cannot bypass
them.

## Install and configure

Install a current Docker Engine with the Compose plugin, then clone a reviewed
release or commit:

```bash
git clone https://github.com/kanga-route/kanga-route.git
cd kanga-route
cp .env.example .env
chmod 600 .env
```

Edit `.env`. For a self-contained host, keep:

```dotenv
USE_LOCAL_DB=true
DYNAMODB_TABLE_NAME=KangaRouteCache
```

Replace both `.invalid` SMTP identity placeholders before performing a live
probe. Add product credentials only for the adapter selected by
`KANGA_ROUTE_ADAPTER`.

Validate and build the exact checkout:

```bash
docker compose config --quiet
docker compose build
docker compose up -d --wait dynamodb-local
```

The Compose project deliberately does not forward static AWS credentials from
the host. Managed DynamoDB requires an explicitly designed workload-identity
path for the chosen environment. DynamoDB Local is the portable default.

## Run verification

Verify one address without a product adapter:

```bash
docker compose run --rm --no-deps engine \
  kanga-route-verify person@example.com
```

Run one configured adapter batch:

```bash
docker compose run --rm --no-deps engine
```

Docker-only installations do not receive the AMI systemd timer automatically.
Use the host scheduler or container orchestrator to invoke that one-shot batch.
Prevent overlapping runs, retain exit status, and send logs to the operator's
normal logging system.

## Optional services

Start the loopback-only browser console:

```bash
docker compose --profile ui up -d --wait web
```

Start the loopback-only, cache-only Postfix policy service:

```bash
docker compose --profile mail-policy up -d --wait postfix-policy
```

Both published host ports bind to `127.0.0.1` by default. Do not change the
browser binding to a public interface without the documented HTTPS protection.
Keep Postfix configured with a short policy timeout and
`default_action=DUNNO`; see [optional mail-server advice](mail-server-integration.md).

## Operate and upgrade

Inspect health and logs with:

```bash
docker compose --profile ui --profile mail-policy ps
docker compose logs --since=1h web postfix-policy dynamodb-local
```

Back up the named DynamoDB Local volume before replacing the host. To upgrade
the current source-built installation, review the target commit, rebuild, and
recreate only the enabled services. Never overwrite `.env` with the example
file. The future Compose release bundle will document digest-pinned upgrades.
