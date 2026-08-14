# Optional Mail-Server Advice

Kanga-Route can advise a mail system using verification evidence already in its
cache. It is not an SMTP relay, smart host, MX server, or mandatory delivery
hop. Mail continues when Kanga-Route is stopped.

## Safety contract

The mail path is cache-only. It never starts DNS or SMTP verification. The
mapping is:

| Evidence | Advice | Default mail behavior |
|---|---|---|
| Cached `Valid` | `allow` | continue |
| Cached `Invalid` | `warn` | continue and observe |
| Cached `Catch-All` or `Unknown` | `allow` | continue |
| Cache miss | `allow` | continue |
| Cache error or unavailable service | `allow` | continue |

`POST /api/v1/advice` accepts up to 100 recipients:

```json
{"recipients":["person@example.com","other@example.net"]}
```

The response always includes `fail_open: true`. Each recipient contains
`action`, `source` (`cache`, `miss`, `unavailable`, or `local`), and cached
neutral evidence when present. Unlike `POST /api/v1/verify`, this endpoint
cannot invoke the engine.

The appliance web service remains loopback-only and unauthenticated. Do not
expose this endpoint to the public internet. A future Google Workspace or
Microsoft 365 integration should call it over a private authenticated path and
must treat timeout, non-2xx, or malformed responses as allow.

## Postfix reference integration

This is appropriate when Postfix runs on the Kanga-Route host or can reach the
policy port through a separately secured private path. In
`/opt/kanga-route/.env` set:

```dotenv
ENABLE_POSTFIX_POLICY=true
KANGA_ROUTE_POSTFIX_POLICY_PORT=10040
POSTFIX_POLICY_MODE=observe
```

Restart the appliance stack:

```bash
sudo systemctl restart kanga-route.service
sudo docker compose --project-directory /opt/kanga-route ps
```

Start with `observe`. It logs a cached-invalid observation but always returns
Postfix `DUNNO`. Add the policy service to the relevant Postfix restriction list
using a short timeout and an explicit fail-open default:

```text
check_policy_service { inet:127.0.0.1:10040, timeout=1s, default_action=DUNNO }
```

The exact restriction list depends on whether the server is checking inbound
recipients or outbound submissions. Apply it only to the intended mail flow,
then run `postfix check` and reload Postfix. The Postfix policy delegation
protocol and `default_action` behavior are documented in the
[official policy service guide](https://www.postfix.org/SMTPD_POLICY_README.html).

After observing production behavior, an operator may explicitly choose:

```dotenv
POSTFIX_POLICY_MODE=enforce-cached-invalid
```

That mode rejects only a syntactically valid recipient with cached `Invalid`
evidence. It still returns `DUNNO` for missing recipients, malformed requests,
cache misses, `Unknown`, `Catch-All`, and every error. The safer default remains
`observe`, because verification evidence can become stale and some providers
deliberately obscure recipient validity.

## Google Workspace and Microsoft 365

Do not route either provider through Kanga-Route as a connector or smart host;
that would make it an inline delivery dependency. Safe future integrations are
compose-time advisory surfaces:

- an [Outlook Smart Alerts add-in](https://learn.microsoft.com/en-us/office/dev/add-ins/outlook/onmessagesend-onappointmentsend-events)
  using a send mode that permits sending when the add-in is unavailable; and
- a user-invoked [Gmail compose add-on](https://developers.google.com/workspace/add-ons/gmail/extending-compose-ui).

Both should batch recipients into one advisory request, enforce a client-side
deadline of at most 500 ms, and allow on timeout or error. Mailbox change
notifications may later warm the verification queue asynchronously, but queue
work must never occur inside the send transaction.
