# Canvas Reader Function (`canvas-reader-fn`)

**Responsibility:** Serves the initial canvas state to the web frontend upon loading. [cite_start]Queries DynamoDB for a specific chunk of pixels[cite: 189, 190, 191].

**Trigger:**
* **Source:** API Gateway (REST)
* **Route:** `GET /canvas`
* **Query Parameters:** `cx` (chunk X) and `cy` (chunk Y).

**Environment Variables:**
* `CANVAS_TABLE_NAME`: DynamoDB table for pixel chunks.

**IAM Permissions Required:**
* `dynamodb:Query` on the `canvas-pixels` table.