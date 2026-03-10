# DLQ Processor Function (`dlq-processor-fn`)

**Responsibility:** Monitors the Dead Letter Queue (DLQ) for pixel drawing events that failed to process. It catches the failed payload, logs the issue for analysis, and attempts to re-drive (re-queue) the message back to the primary SQS queue.

**Trigger:**
* **Source:** Amazon SQS
* **Queue:** `PixelWorkerDLQ`

**Environment Variables:**
* `PIXEL_WORKER_QUEUE_URL`: The destination URL to re-drive messages.

**IAM Permissions Required:**
* `sqs:SendMessage` on the `PixelWorkerQueue`.
* `sqs:ReceiveMessage`, `sqs:DeleteMessage`, `sqs:GetQueueAttributes` on `PixelWorkerDLQ` (Managed automatically by SAM).
