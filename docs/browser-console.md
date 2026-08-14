# Browser Console

Kanga-Route includes a browser-based operator console for verifying one email
address without reading from or writing to a product integration. The same
product-neutral application service powers the console, versioned API, and
`kanga-route verify` command.

## Exposure model

The console is disabled by default. When enabled, Docker publishes it only on
the appliance loopback interface. The application has no login, session, token,
cookie, or other authentication endpoint. Never expose port 8080 or change the
Compose binding to a public interface.

Two appliance access paths are documented:

- **Private access:** connect directly to loopback through an authenticated SSM
  port-forwarding session.
- **Public AWS access:** use the [beginner AWS deployment](aws-appliance-deployment.md),
  where an HTTPS ALB authenticates users with Cognito before forwarding through
  nginx to the loopback service. The instance accepts nginx traffic only from
  the ALB security group.

The CloudFormation path is the only supported public exposure model today. It
does not add authentication to the application itself. Do not copy only part
of that design or place another proxy in front of Kanga-Route without a
reviewed TLS, authentication, trusted-proxy, and recovery design. UI-04 remains
open for that general contract and its security tests.

Enable it in `/opt/kanga-route/.env`:

```dotenv
ENABLE_WEB_UI=true
KANGA_ROUTE_WEB_PORT=8080
WEB_VERIFY_TIMEOUT_SECONDS=45
WEB_MAX_CONCURRENT=2
WEB_REQUESTS_PER_MINUTE=30
MAIL_ADVICE_REQUESTS_PER_MINUTE=600
```

Restart the stack and start an SSM tunnel from the operator workstation:

```bash
sudo systemctl restart kanga-route.service

aws ssm start-session \
  --target i-0123456789abcdef0 \
  --document-name AWS-StartPortForwardingSession \
  --parameters '{"portNumber":["8080"],"localPortNumber":["8080"]}'
```

Then open `http://127.0.0.1:8080/` in a browser. Closing the SSM session removes
the workstation path to the console.

## API contract

`POST /api/v1/verify` accepts a strict JSON envelope:

```json
{
  "email": "person@example.com",
  "cache_policy": "use"
}
```

`cache_policy` is `use` or `refresh` and defaults to `use`. A successful
response contains the neutral result plus `cache.status`, which is `hit`,
`miss`, or `bypassed`:

```json
{
  "result": {
    "email": "person@example.com",
    "status": "Valid",
    "reason": "OK",
    "mailbox_provider": "Google Workspace",
    "is_role_account": false,
    "mx_records": ["aspmx.l.google.com"],
    "smtp_code": 250,
    "verified_at": "2026-08-13T20:00:00+00:00"
  },
  "cache": { "status": "miss" }
}
```

Statuses are `Valid`, `Invalid`, `Catch-All`, and `Unknown`. Reasons are `OK`,
`Syntax_Error`, `Disposable`, `No_MX`, `User_Not_Found`, `Greylisted`,
`Timeout`, `Connection_Refused`, `Unknown_Host`, `DNS_Timeout`, `DNS_Error`,
`SMTP_Temporary_Failure`, and `SMTP_Rejected`.

Errors use a stable envelope and never echo the submitted address or internal
exception:

```json
{
  "error": {
    "code": "invalid_email",
    "message": "Enter one complete email address."
  }
}
```

Stable codes are `invalid_email`, `invalid_request`,
`unsupported_media_type`, `request_too_large`, `rate_limited`,
`request_timeout`, `cache_unavailable`, `configuration_invalid`, and
`verification_failed`.

## Cache-only mail advice API

`POST /api/v1/advice` is a distinct multi-recipient contract for optional mail
integrations:

```json
{"recipients":["person@example.com","other@example.net"]}
```

It reads cached evidence only; it cannot invoke DNS, SMTP, or the live engine.
Its response declares `fail_open: true`, and every cache miss or cache failure
returns `allow`. Cached `Invalid` evidence returns `warn`, while `Valid`,
`Catch-All`, and `Unknown` return `allow`. See the
[mail-server integration guide](mail-server-integration.md) before connecting a
mail system. The loopback API is unauthenticated and must not be made public.

## Operational behavior

- Invalid input returns a safe `4xx` before cache, DNS, or SMTP work.
- Fresh checks require a configured SMTP identity; definitive cache hits do not.
- Requests are size-, time-, concurrency-, and rate-limited per web process.
- Uvicorn access logs are disabled so addresses never enter request logs.
- Responses use no-store caching, a same-origin content security policy, and
  frame, referrer, and content-type protections.
- The page uses no third-party analytics, fonts, scripts, or CDNs.
- The console owns no persistent data. Results use the existing verification
  cache, so disabling or upgrading the console requires no UI data migration.
