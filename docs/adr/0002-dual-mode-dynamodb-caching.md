# 2. Dual-Mode DynamoDB Caching (Local & Cloud)

**Date:** 2026-08-05
**Status:** Accepted

**Context:**
Verifying an entire CRM database daily wastes compute and risks IP blacklisting. We must cache verification results (e.g., for 30-90 days) so only new or modified emails are checked. However, requiring users to provision an external cloud database just to test the tool creates too much friction.

**Decision:**
The appliance will use a "BYODB" (Bring Your Own Database) toggle pattern based on Amazon DynamoDB.
1. **Default (Local Mode):** The OS will run `dynamodb-local` (via Java) as a persistent `systemd` background service. The Python engine will default to this local endpoint.
2. **Production (Cloud Mode):** By setting `USE_LOCAL_DB=false`, the engine will bypass the local service and natively inherit the EC2 IAM role to communicate with a dedicated AWS DynamoDB table.

**Consequences:**
* **Positive:** Time-to-first-value is under 15 minutes. Engineers can boot the image and run it immediately without external cloud dependencies.
* **Positive:** Scales seamlessly to production infrastructure without changing the Python codebase.