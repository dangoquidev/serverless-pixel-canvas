# Broadcast Worker Function (`broadcast-worker-fn`)

[cite_start]**Responsibility:** Listens for successful database writes and pushes the new pixel data to all active web clients in near real-time[cite: 208, 209]. Also cleans up stale or disconnected WebSocket connections.

**Trigger:**
* **Source:** DynamoDB Stream (`canvas-pixels` table)
* **Event:** `INSERT` or `MODIFY` operations.

**Environment Variables:**
* `CONNECTIONS_TABLE_NAME`: DynamoDB table storing active connection IDs.
* `WSS_API_ENDPOINT`: The API Gateway WebSocket callback URL.

**IAM Permissions Required:**
* `dynamodb:GetRecords`, `dynamodb:GetShardIterator`, `dynamodb:DescribeStream`, `dynamodb:ListStreams` on `canvas-pixels` stream.
* `dynamodb:Scan`, `dynamodb:BatchWriteItem` on `websocket-connections`.
* `execute-api:ManageConnections` on the WebSocket API Gateway.