# Discord Proxy Function (`discord-proxy-fn`)

[cite_start]**Responsibility:** Handles incoming Discord slash commands[cite: 630]. [cite_start]It mathematically verifies the ED25519 signature from Discord, publishes the command to the messaging broker, and asynchronously responds with a deferred "Thinking..." state[cite: 633].

**Trigger:**
* **Source:** API Gateway (REST)
* **Route:** `POST /discord/interactions`
* **Payload:** Discord Interaction Object (Type 1 Ping or Type 2 Application Command).

**Environment Variables:**
* `SNS_TOPIC_ARN`: The ARN of the fan-out SNS topic.
* `DISCORD_SECRET_NAME`: Secret name that contains Discord keys (including `PublicKey`).
* `APP_SECRET_NAME`: Secret that contains `DiscordAdminIds` for `/clean` authorization.

**Supported Commands:**
* `/snapshot`: Generates a canvas snapshot asynchronously.
* `/ping`: Health check command with immediate response.
* `/draw x y color`: Queues one pixel draw event (`color` must be `#RRGGBB`).
* `/clean`: Admin-only full canvas clean (Discord IDs from `AppSecrets.DiscordAdminIds`).

**IAM Permissions Required:**
* `sns:Publish` on the `pixel-events-topic`.
* `secretsmanager:GetSecretValue` for `DiscordSecrets-*` and `AppSecrets-*`.
