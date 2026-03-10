# Web Proxy Function (`web-proxy-fn`)

[cite_start]**Responsibility:** Acts as the lightweight HTTP entry point for web clients to draw pixels[cite: 588, 611]. [cite_start]It validates the payload, assigns a correlation ID for tracing [cite: 239, 241, 359][cite_start], publishes the event to the messaging broker, and asynchronously returns a `202 Accepted`[cite: 588, 633].

**Trigger:**
* **Source:** API Gateway (REST)
* **Route:** `POST /pixels`
* **Payload Example:** `{"x": 150, "y": 200, "color": "#FF0000", "user_id": "12345"}`

**Environment Variables:**
* `SNS_TOPIC_ARN`: The ARN of the fan-out SNS topic.

**IAM Permissions Required:**
* `sns:Publish` on the `pixel-events-topic`.