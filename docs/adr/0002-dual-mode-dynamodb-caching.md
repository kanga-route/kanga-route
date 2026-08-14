# 2. Dual-Mode DynamoDB Caching Strategy

**Status:** Accepted
**Amended:** 2026-08-13

## Context

Deep SMTP handshakes are time-consuming and can harm sender reputation when
repeated unnecessarily. Kanga-Route needs a cache for definitive verification
results, with a local mode for an immediately usable appliance and a managed
mode for AWS-operated persistence.

The original accepted text selected managed DynamoDB by removing a local
endpoint setting. That implicit behavior was ambiguous: an empty or misspelled
setting could unintentionally change where data was stored.

## Decision

Cache mode is selected explicitly with `USE_LOCAL_DB`:

- `USE_LOCAL_DB=true` is the default. Docker Compose starts DynamoDB Local,
  stores its data in a persistent Docker volume, and supplies the local
  endpoint plus non-secret request-signing values to the engine.
- `USE_LOCAL_DB=false` selects managed DynamoDB. The engine ignores any local
  endpoint, uses the standard AWS endpoint, and obtains credentials from the
  AWS SDK credential chain. On the supported EC2 appliance, authorization is
  provided by the attached IAM instance role; Compose does not forward static
  AWS credentials from the host.
- Any value other than `true` or `false` is a configuration error. Removing or
  blanking `DYNAMODB_ENDPOINT_URL` does not select cloud mode.

Both modes use the configured `DYNAMODB_TABLE_NAME`. Entries have a DynamoDB
TTL, and expired entries are ignored at read time. Only definitive results are
cached; `Unknown` results are written to HubSpot for visibility but deliberately
remain eligible for a later verification attempt.

## Consequences

### Positive

- Local mode works without managed AWS database credentials and survives
  container restarts through its named volume.
- Cloud mode uses short-lived IAM credentials instead of baked or forwarded
  static keys.
- Explicit mode selection fails closed instead of silently routing to an
  unintended database.

### Negative

- Local cache data is lost if its Docker volume is pruned or its instance is
  destroyed without a backup.
- Managed mode depends on correct EC2 IAM permissions for table and TTL
  operations.
- Operators must preserve the explicit mode setting when moving an appliance
  between local and managed storage.

## Amendment history

The 2026-08-13 amendment supersedes endpoint-removal as a mode switch. The
dual-mode decision remains accepted, but `USE_LOCAL_DB=false` is now the only
supported way to select managed DynamoDB.
