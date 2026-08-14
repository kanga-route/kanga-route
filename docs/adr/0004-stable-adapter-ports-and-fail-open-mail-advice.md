# ADR 0004: Stable Adapter Ports and Fail-Open Mail Advice

**Status:** Accepted

## Context

Kanga-Route began with a HubSpot-shaped orchestration contract. The verification
result was already product-neutral, but the runner still knew HubSpot method
names, limits, errors, and configuration. Adding another product would therefore
have required editing shared orchestration and risked changing the engine.

Mail-system integration adds a second concern. A DNS or SMTP verification can
take seconds and can fail for reasons unrelated to mail delivery. Putting that
work inline in an SMTP transaction would make Kanga-Route a delivery dependency.

## Decision

The dependency direction is fixed:

```text
product adapter ----> adapter port ----> neutral target/outcome models
                                      \
batch application ----> engine port ----> verification result
                 \
                  ----> cache port

mail adapter ----> cache-only advisory service ----> cache port
```

`IVerificationAdapter` is the only batch-integration seam. It exposes:

- a stable configuration `name`;
- explicit read/write capabilities and a hard batch limit;
- configuration validation before I/O;
- `fetch_targets(limit)` returning only `VerificationTarget` values; and
- `write_outcomes(outcomes)` accepting only `VerificationOutcome` values.

An adapter owns credentials, eligibility rules, paging, retries, product record
IDs, API objects, limits, errors, and writeback formatting. It translates its
errors to `AdapterError` while retaining the original exception as `__cause__`.
The explicit registry is the only place that discovers an adapter. Only the
selected adapter validates its secrets.

The verification engine accepts an address and returns `VerificationResult`.
It must not import an adapter, product client, web layer, mail layer, or
composition root. A new service or adapter must not add a branch, parameter,
metadata field, or product name to the engine. Engine changes are reserved for
verification evidence, protocols, and classification semantics.

Mail integrations use `MailAdvisoryService`. Its constructor accepts a cache
port and deliberately cannot accept the verification engine. It performs no
DNS, SMTP, queue, or product I/O. Cached `Invalid` evidence produces `warn`;
`Valid`, `Catch-All`, and `Unknown` produce `allow`. A miss or any cache failure
also produces `allow`. The response declares `fail_open: true`.

Postfix is the first reference mail adapter. Its default `observe` mode always
returns `DUNNO`. The opt-in `enforce-cached-invalid` mode rejects only cached
`Invalid` evidence. Postfix must configure a short timeout and
`default_action=DUNNO`, so a stopped policy process does not interrupt mail.

## Consequences

- HubSpot behavior remains behind a wrapper without changing its API client.
- New batch products require an adapter, registry entry, contract tests, and
  documentation; they require no engine edit.
- Mail advice can be stale by the cache TTL. It is advisory, not proof of
  deliverability at send time.
- Cache misses do not initiate verification. A future asynchronous queue may
  warm misses, but it must remain outside the message transaction.
- Read-only or write-only capabilities can be declared, although the current
  scheduled batch runner intentionally requires both.
- Dependency tests fail if product code is imported into the engine.
