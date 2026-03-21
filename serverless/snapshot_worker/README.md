# Snapshot Worker Function (`snapshot-worker-fn`)

**Responsibility:** Generates a full PNG image of the canvas at a point in time.

Reads the entire DynamoDB canvas state, uses Pillow to render a PNG image, uploads it to S3, and publishes a completion event to SNS (containing metadata like discord_token) so that downstream processors (discord_notifier) don't need to make expensive S3 head_object calls.

**Trigger:**
* **Source:** Amazon SQS
* **Event:** `snapshot` action routed from SNS → SnapshotWorkerQueue.

**Processing Flow:**
1. Receives SQS message containing SNS event with `snapshot` action
2. Scans entire `canvas-pixels` DynamoDB table
3. Renders pixels to PNG using Pillow (using hex color codes)
4. Uploads PNG to S3 with presigned URL (1 day expiration)
5. **Publishes completion event to SNS** containing:
   - `object_key`: S3 key for the snapshot
   - `discord_token`: Interaction token (for discord_notifier)
   - `pixel_count`: Total pixels rendered
   - `correlation_id`: For tracing

**Environment Variables:**
* `CANVAS_TABLE_NAME`: DynamoDB table for pixel chunks.
* `SNAPSHOT_BUCKET`: S3 bucket to store the generated PNGs.
* `SNAPSHOT_COMPLETE_TOPIC`: SNS topic ARN for completion events (new in Phase 2.10).

**IAM Permissions Required:**
* `dynamodb:Scan` on the `canvas-pixels` table.
* `s3:PutObject` on the `SnapshotsBucket`.
* `sqs:ReceiveMessage`, `sqs:DeleteMessage`, `sqs:GetQueueAttributes` on `SnapshotWorkerQueue`.
* `sns:Publish` on the `SNAPSHOT_COMPLETE_TOPIC` (new in Phase 2.10).

**Performance Characteristics:**
* **Typical Duration:** 5-15 seconds (depending on pixel count and image size)
* **Memory:** 512 MB (configured in template.yaml)
* **DynamoDB Cost:** One scan operation (~RCU depends on table size)
* **S3 Cost:** One PutObject operation

**Optimization Notes (Phase 2.10):**
Previously, discord_notifier had to call S3 `head_object` to retrieve the discord_token from object metadata. Now, the token is published directly via SNS event, avoiding that API call and improving latency for the Discord notification workflow.
