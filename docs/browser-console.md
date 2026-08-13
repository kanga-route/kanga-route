# Browser Console

Kanga-Route includes a browser-based operator console for verifying one email
address without reading from or writing to a product integration. The same
product-neutral application service powers the console, versioned API, and
`kanga-route verify` command.

## Exposure model

The console is disabled by default. When enabled, Docker publishes it only on
the appliance loopback interface. It has no login, session, token, cookie, or
other authentication endpoint. Reach it through an SSM port-forwarding session;
do not add EC2 ingress or change the Compose binding to a public interface.

This loopback-only HTTP mode does not authorize future network exposure. Any
authenticated or non-loopback browser deployment requires the UI-04 TLS and
authentication ADR first.

Enable it in `/opt/kanga-route/.env`:

```dotenv
ENABLE_WEB_UI=true
KANGA_ROUTE_WEB_PORT=8080
WEB_VERIFY_TIMEOUT_SECONDS=45
WEB_MAX_CONCURRENT=2
WEB_REQUESTS_PER_MINUTE=30
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
