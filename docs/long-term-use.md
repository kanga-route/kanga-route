# Long-Term Operations

## IP reputation

Keep the configured `SMTP_HELO_DOMAIN`, forward A record, Elastic IP PTR
record, and `SMTP_MAIL_FROM`/SPF identity aligned. AWS must allow outbound
port 25. Start with conservative batches and increase them only after observing
recipient-server behavior.

Kanga-Route limits total concurrent probes and retries transient failures.
Greylisting and ambiguous policy rejections are `Unknown`, not `Invalid`.
Unknown results are not cached. `UNKNOWN_RETRY_AFTER_HOURS` defaults to 48,
preventing the same oldest transient cohort from consuming every daily batch
while preserving later retries.

## Cache lifecycle

`CACHE_TTL_DAYS` controls definitive-result cache lifetime and defaults to 30.
Kanga-Route enables DynamoDB TTL on the `ttl` attribute. It also rejects stale
entries at read time because DynamoDB deletion is asynchronous.

`REVERIFY_AFTER_DAYS` controls when contacts with an old
`last_verified` datetime become eligible again. Keep it aligned with, or
longer than, the cache TTL so a stale HubSpot contact is not immediately served
the same cached result.

For managed DynamoDB, set `USE_LOCAL_DB=false`, leave
`DYNAMODB_ENDPOINT_URL` and static AWS credentials empty, and grant the EC2
instance role access to the configured table.

## Logs and schedules

Runs are oneshot systemd services, and logs remain in journald even though the
engine container is removed afterward:

```bash
kanga-route status
sudo kanga-route logs
sudo kanga-route schedule "*-*-* 02:00:00 UTC"
```

Configure journald retention according to the host's disk and compliance
requirements. A file lock prevents overlapping scheduled and manual runs.

## Upgrades

Treat an AMI as immutable. The bakery only builds private candidates. Launch
the candidate in a staging account, complete a configuration and HubSpot smoke
test, and then promote that exact AMI—without rebuilding it—through a separate
manual AWS release operation before broader sharing or production rollout.
Automating exact-candidate promotion is post-MVP work. The workflow does not
rewrite release documentation or publish builds automatically.
