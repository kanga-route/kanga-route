# 2. Dual-Mode DynamoDB Caching Strategy

* **Status:** Accepted

## Context
Deep SMTP handshakes are time-consuming and risk IP blacklisting if performed redundantly]. We need a fast caching layer to store verification results and timestamps.

## Decision
The Docker Compose stack will include the official `amazon/dynamodb-local` container as a sidecar, mapping its data to a persistent Docker volume. The Python engine will default to this local database. By modifying the `.env` file to remove the local endpoint variable, the container will seamlessly route to a managed AWS DynamoDB table via the host instance's IAM role.

## Consequences

### Positive
* Delivers a true out-of-the-box experience for immediate testing while providing a frictionless upgrade path to enterprise-scale persistent storage.

### Negative
* Local cache will be lost if the persistent Docker volume is accidentally pruned or the host VM is destroyed without a backup.