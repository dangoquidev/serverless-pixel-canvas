# Discord Notifier Function (`discord-notifier-fn`)

**Responsibility:** Completes the snapshot workflow. [cite_start]Listens for the creation of new PNG files in the S3 bucket, retrieves the Discord interaction token from the object's metadata, and patches the deferred Discord message with the image URL[cite: 543, 544, 616].

**Trigger:**
* **Source:** Amazon S3
* **Event:** `s3:ObjectCreated:*`

**Environment Variables:**
* `DISCORD_SECRET_NAME`: Secrets Manager secret with `AppId` (required) and optionally `BotToken` (if you get 403 Forbidden from Discord API).

**IAM Permissions Required:**
* `s3:GetObject` (to read metadata) on the `SnapshotsBucket`.