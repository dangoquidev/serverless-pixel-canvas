# Discord Notifier Function (`discord-notifier-fn`)

**Responsibility:** Completes the snapshot workflow by notifying Discord when a snapshot is ready.

Listens for snapshot completion events, generates a presigned S3 URL, and patches the deferred Discord interaction message (slash command response) with the canvas snapshot URL. Implements exponential backoff retry logic for transient failures and DLQ fallback for persistent failures.

**Trigger:**
* **Source:** Amazon S3
* **Event:** `s3:ObjectCreated:*` (receives snapshot PNG uploads)

**Processing Flow:**
1. Receives S3 ObjectCreated event for new PNG snapshot
2. Generates presigned URL (valid for 1 day)
3. Calls Discord API to edit the deferred interaction message
4. On transient failure (5xx, timeout): Retries with exponential backoff (1s, 2s, 4s, 8s, 16s max)
5. On permanent failure (4xx, all retries exhausted): Sends message to DLQ for manual review

**Environment Variables:**
* `DISCORD_SECRET_NAME`: AWS Secrets Manager secret with:
  - `AppId` (required): Discord application ID
  - `ClientSecret` (optional): For additional validation
* `DISCORD_NOTIFIER_DLQ_URL`: SQS queue URL for failed notification attempts (new in Phase 2.11)

**IAM Permissions Required:**
* `s3:GetObject` on the `SnapshotsBucket` (to read presigned URLs)
* `s3:GetObjectMetadata` on the `SnapshotsBucket`
* `secretsmanager:GetSecretValue` on the `DiscordSecrets` secret
* `sqs:SendMessage` on the `DISCORD_NOTIFIER_DLQ_URL` (new in Phase 2.11)

**Error Handling (Phase 2.11 - Circuit Breaker):**
* **Temporary Failures (Transient):**
  - 5xx HTTP errors from Discord API
  - Network timeouts/connection errors
  - **Action:** Retry with exponential backoff (max 3 retries, 32 second cap)
  
* **Permanent Failures (4xx HTTP):**
  - 400 Bad Request (invalid token format)
  - 401 Unauthorized (invalid bot permissions)
  - 404 Not Found (interaction already expired)
  - **Action:** Log error and send to DLQ (no retry)

* **All Retries Exhausted:**
  - **Action:** Send to DLQ for manual investigation/retry
  - DLQ message includes: original record, error details, correlation_id, timestamp

**Performance Characteristics:**
* **Typical Duration:** 2-5 seconds (plus potential retry backoff)
* **Memory:** 256 MB
* **API Calls:** 1 Discord API call (with up to 4 total attempts if transient failures occur)
* **S3 Operations:** 1 read for presigned URL generation

**Optimization Notes:**
* **Phase 2.10:** Originally retrieved discord_token from S3 object metadata (expensive head_object call). Now receives token directly from SNS event published by snapshot_worker.
* **Phase 2.11:** Added exponential backoff retry to handle transient Discord API failures. DLQ provides a safety net for persistent failures without losing data.

**Monitoring:**
* CloudWatch Logs: Check for "Discord API transient failure" warnings or "permanent failure" errors
* DLQ Queue Depth: Monitor for backed-up messages indicating persistent Discord outages
* Correlation IDs: Use for end-to-end tracing of snapshot requests through snapshot_worker → discord_notifier
