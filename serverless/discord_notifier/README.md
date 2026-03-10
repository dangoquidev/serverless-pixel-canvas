# Discord Notifier Function (`discord-notifier-fn`)

**Responsibility:** Completes the snapshot workflow. [cite_start]Listens for the creation of new PNG files in the S3 bucket, retrieves the Discord interaction token from the object's metadata, and patches the deferred Discord message with the image URL[cite: 543, 544, 616].

**Trigger:**
* **Source:** Amazon S3
* **Event:** `s3:ObjectCreated:*`

**Environment Variables:**
* `DISCORD_APP_ID`: Used to construct the Discord API webhook URL.

**IAM Permissions Required:**
* `s3:GetObject` (to read metadata) on the `SnapshotsBucket`.