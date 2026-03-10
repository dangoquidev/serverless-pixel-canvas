# Authentication Callback Function (`auth-fn`)

[cite_start]**Responsibility:** Handles the Discord OAuth2 authorization code flow[cite: 328, 329, 330]. [cite_start]Exchanges the code for a Discord identity, generates a secure JWT for the application, and redirects the user back to the static frontend[cite: 330, 331].

**Trigger:**
* **Source:** API Gateway (REST)
* **Route:** `GET /auth/callback`

**Environment Variables:**
* `DISCORD_CLIENT_ID` & `DISCORD_CLIENT_SECRET`: For OAuth2 exchange.
* `JWT_SECRET`: For signing the application token.
* `REDIRECT_URI`: The API Gateway callback URL.
* `FRONTEND_URL`: The S3 static website URL.

**IAM Permissions Required:**
* None specific to AWS resources (only basic Lambda execution), as it strictly talks to the external Discord API.