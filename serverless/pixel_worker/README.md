# Pixel Worker Function (`pixel-worker-fn`)

**Responsibility:** The core engine. [cite_start]Consumes batches of pixel draw requests from the queue [cite: 214, 224][cite_start], enforces user rate limits [cite: 614, 643][cite_start], calculates the target canvas chunk, and persists the pixel data (color, author, timestamp) to the database[cite: 614, 639, 642].

**Trigger:**
* **Source:** Amazon SQS
* **Batch Size:** Up to 10 messages.

**Environment Variables:**
* `CANVAS_TABLE_NAME`: DynamoDB table for pixel chunks.
* `RATE_LIMIT_TABLE_NAME`: DynamoDB table for rate limiting.

**IAM Permissions Required:**
* `dynamodb:PutItem`, `dynamodb:UpdateItem` on `canvas-pixels` and `rate-limits` tables.
* `sqs:ReceiveMessage`, `sqs:DeleteMessage`, `sqs:GetQueueAttributes` on `PixelWorkerQueue`.