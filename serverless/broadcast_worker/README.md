# Broadcast Worker Function (`broadcast-worker-fn`)

**Responsibility:** Listens for database writes (pixel events) and pushes updates to all active WebSocket clients in near real-time.

For small broadcasts (≤ 5000 connections), uses ThreadPoolExecutor for concurrent sends. For large broadcasts (> 5000 connections), fans-out to SQS for horizontal scaling via multiple Lambda invocations.

Also cleans up stale or disconnected WebSocket connections automatically.

**Triggers:**
* **Primary:** DynamoDB Stream (`canvas-pixels` table) for `INSERT` or `MODIFY` operations
* **Secondary (Phase 2.9):** SQS BatchBroadcastQueue for large broadcast fan-out

**Processing Flow (Small Broadcasts ≤ 5000 connections):**
1. Receives DynamoDB stream event with pixel updates
2. Fetches all active connection IDs from `websocket-connections` table (with projection to minimize RCU)
3. Uses ThreadPoolExecutor (50 workers) to send to all clients concurrently
4. Detects stale connections (410 Gone responses) and cleans them up via DynamoDB batch write
5. Logs success metrics

**Processing Flow (Large Broadcasts > 5000 connections - Phase 2.9):**
1. Receives DynamoDB stream event with pixel updates
2. Fetches all active connection IDs
3. **Detects > 5000 connections** and fans-out to SQS:
   - Splits connections into batches of 500
   - Enqueues each batch as a separate SQS message
   - Returns immediately (orchestrator pattern)
4. `BatchBroadcastWorkerFunction` processes each batch independently:
   - Receives batch from SQS
   - Sends to 500 connections via ThreadPoolExecutor
   - Cleans up stale connections
   - Completes independently (parallel scaling)

**Environment Variables:**
* `CONNECTIONS_TABLE_NAME`: DynamoDB table storing active connection IDs
* `WSS_API_ENDPOINT`: API Gateway WebSocket callback URL
* `BATCH_BROADCAST_QUEUE_URL`: SQS queue for fan-out (Phase 2.9, optional)
* `BATCH_THRESHOLD`: When to fan-out (default 5000 connections)
* `BATCH_SIZE`: Connections per batch (default 500)

**IAM Permissions Required:**
* **DynamoDB Streams:**
  - `dynamodb:GetRecords`, `dynamodb:GetShardIterator`, `dynamodb:DescribeStream`, `dynamodb:ListStreams` on `canvas-pixels` stream
  - `dynamodb:Scan`, `dynamodb:BatchWriteItem` on `websocket-connections`
* **WebSocket API:**
  - `execute-api:ManageConnections` on the WebSocket API Gateway
* **SQS (Phase 2.9):**
  - `sqs:SendMessage` on `BatchBroadcastQueue`

**Performance Characteristics:**
* **Small Broadcasts (Direct):**
  - Typical latency: 500ms - 2s
  - Max concurrency: 50 sockets per Lambda
  - Suitable for: < 5000 connections
  
* **Large Broadcasts (SQS Fan-Out):**
  - Initial latency: 100-200ms (orchestrates batches)
  - Processing latency: 500ms - 2s per batch (parallel)
  - Total end-to-end: 1-3s for 100k connections
  - Horizontal scalability: Unlimited via SQS + Lambda concurrency

**Optimization Notes (Phase 2.8 & 2.9):**
* **Phase 2.8:** Added DynamoDB GSI `ConnectionTimestampIndex` with TTL support for efficient connection scanning
* **Phase 2.8:** Scan projection to `ConnectionId` only (minimizes data transfer)
* **Phase 2.9:** SQS fan-out pattern for unlimited connection broadcast (100k → 200 Lambda invocations vs 100k API calls)

**Monitoring:**
* **Metrics:**
  - `active_clients`: Connected sockets at broadcast time
  - `stale_cleaned`: Removed disconnected clients
  - `broadcast_duration`: Time to send to all (excluding SQS fan-out latency)
  
* **Alarms:**
  - DynamoDB scan RCU spikes (indicates large broadcaster table)
  - Lambda duration > 10s (may indicate timeout for huge broadcasts)
  - SQS queue depth (indicates batches waiting to process)
