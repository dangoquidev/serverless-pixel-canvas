# WebSocket Manager Function (`websocket-manager-fn`)

**Responsibility:** Maintains the state of active web clients. Saves the `connectionId` when a user connects to the WebSocket API, and deletes it when they disconnect.

**Trigger:**
* **Source:** API Gateway (WebSocket)
* **Routes:** `$connect` and `$disconnect`

**Environment Variables:**
* `CONNECTIONS_TABLE_NAME`: DynamoDB table storing active connection IDs.

**IAM Permissions Required:**
* `dynamodb:PutItem`, `dynamodb:DeleteItem` on the `websocket-connections` table.