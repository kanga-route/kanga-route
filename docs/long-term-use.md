# Kanga-Route Long-Term Use & Operations Guide 🦘

This guide outlines operational best practices, IP reputation management, long-term database caching, log rotation, and routine maintenance for running the Kanga-Route Virtual Appliance in production.

---

## 1. IP Reputation & Warm-Up Best Practices

Because Kanga-Route performs direct TCP Port 25 SMTP socket handshakes against major mailbox providers (Google, Microsoft, Yahoo, Proton, iCloud), preserving the Elastic IP address reputation is critical.

### Key Rules for Host IP Health
1. **Maintain Valid Reverse DNS (rDNS / PTR Record):**
   - Ensure `verifier.yourdomain.com` matches the Reverse DNS setting on your AWS Elastic IP.
   - Mail servers automatically drop handshakes from IPs lacking valid PTR records.
2. **Implement Batch Rate Limiting:**
   - Do not verify more than **5,000–10,000 new emails per day** from a fresh Elastic IP.
   - Gradually warm up new Elastic IPs over 2–3 weeks if processing large CRM lists (>50,000 contacts).
3. **Handle Greylisting & 450 Responses:**
   - Some mail servers return `450` or `451` temporary greylisting errors on initial connections.
   - Kanga-Route automatically categorizes these as `Catch-All` with reason `Greylisted` so they do not trigger aggressive retries.

---

## 2. Database & Cache Maintenance (DynamoDB)

Refers to **ADR 0002**. Kanga-Route uses DynamoDB to cache verification results and prevent redundant SMTP socket handshakes.

### Maintenance Tasks
- **TTL Expiration (Default 30 Days):**
  - Cached verification results automatically expire after 30 days.
  - If your CRM contact list changes rapidly, you can adjust the TTL window in `DynamoDBCacheStore`.
- **Switching to Cloud DynamoDB (Scale Up):**
  - To transition from local sidecar (`dynamodb-local`) to a managed AWS DynamoDB table for enterprise persistence, update `/opt/kanga-route/.env`:
    ```env
    USE_LOCAL_DB=false
    # Remove DYNAMODB_ENDPOINT_URL to route directly to AWS DynamoDB
    DYNAMODB_TABLE_NAME=KangaRouteCache
    ```

---

## 3. Log Rotation & Disk Monitoring

The Kanga-Route appliance logs execution summaries to container stdout and `/var/log/kanga-route.log`.

### Log Rotation Setup (`/etc/logrotate.d/kanga-route`)
Ensure `/var/log/kanga-route.log` is rotated automatically to prevent disk space exhaustion:
```text
/var/log/kanga-route.log {
    daily
    rotate 14
    compress
    delaycompress
    missingok
    notifempty
    create 0640 root root
}
```

---

## 4. Upgrading the Appliance

When new engine updates or security patches are released:

1. **Pull Latest Code & Rebuild Containers:**
   ```bash
   cd /opt/kanga-route
   git pull origin master
   docker compose build engine
   ```
2. **Re-Bake AMI for CI/CD Pipelines:**
   Run Packer to output an updated production AMI:
   ```bash
   packer build packer/kanga-route.pkr.hcl
   ```

---

## 5. Monitoring & Health Checks

Use the built-in host CLI tool to verify system health:

```bash
# Check stack health & active cron schedule
kanga-route status

# Tail real-time execution logs
kanga-route logs
```
