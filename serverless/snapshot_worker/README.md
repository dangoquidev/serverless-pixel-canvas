# Snapshot Worker Function (`snapshot-worker-fn`)

[cite_start]**Responsibility:** Generates a full image of the canvas[cite: 616, 628]. [cite_start]Reads the entire database state, uses Pillow to draw a PNG image, and uploads it to an S3 bucket with the original Discord interaction token as metadata[cite: 542].

**Trigger:**
* **Source:** Amazon SQS
* **Event:** `snapshot` command routed from SNS.

**Environment Variables:**
* `CANVAS_TABLE_NAME`: DynamoDB table for pixel chunks.
* `SNAPSHOT_BUCKET`: S3 bucket to store the generated PNGs.

**IAM Permissions Required:**
* `dynamodb:Scan` on the `canvas-pixels` table.
* `s3:PutObject` on the `SnapshotsBucket`.
* `sqs:ReceiveMessage`, `sqs:DeleteMessage`, `sqs:GetQueueAttributes` on `SnapshotWorkerQueue`.