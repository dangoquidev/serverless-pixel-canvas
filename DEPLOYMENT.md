# Serverless Pixel Canvas Deployment Guide

This guide details the steps required to deploy the fully Serverless Pixel Canvas architecture to your AWS account.

The project is split into two deployment phases:
1. **Backend Infrastructure (AWS SAM):** Databases, Event bus, SQS queues, API Gateways, and Lambda workers.
2. **Frontend Application (Svelte):** The static web UI served securely by CloudFront from an S3 Object bucket.

---

## Prerequisites

Before starting, ensure you have the following installed on your machine:
- [AWS CLI](https://aws.amazon.com/cli/) configured with `aws configure` (requires Administrator or power-user IAM credentials).
- [AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/serverless-sam-cli-install.html) (`sam`).
- [Node.js & npm](https://nodejs.org/en/) (for the frontend).
- Python 3.12 (for Lambda local testing).

---

## Phase 1: Configuring Secrets in AWS

The backend Lambda functions rely on specific secrets to authenticate your JSON Web Tokens and interface with the Discord API. These must be created in **AWS Secrets Manager** *before* you deploy the SAM template, or the deployment will fail.

1. **Create the Discord Secrets:**
   You must create a Discord Application in the [Discord Developer Portal](https://discord.com/developers/applications).
   Run the following AWS CLI command to store the secrets:
   ```bash
   aws secretsmanager create-secret \
     --name DiscordSecrets \
     --secret-string '{"ClientId":"YOUR_CLIENT_ID","ClientSecret":"YOUR_CLIENT_SECRET","PublicKey":"YOUR_DISCORD_PUBLIC_KEY","AppId":"YOUR_DISCORD_APP_ID"}'
   ```

2. **Create the Application Secrets:**
   Generate a random, strong secret string to sign the JWTs for your web application.
   ```bash
   aws secretsmanager create-secret \
     --name AppSecrets \
     --secret-string '{"JwtSecret":"YOUR_SUPER_LONG_RANDOM_SECRET_KEY"}'
   ```

---

## Phase 2: Deploying the Backend (AWS SAM)

Once the secrets are in place, you can deploy the `template.yaml` defining your entire infrastructure.

1. **Navigate to the project root:**
   ```bash
   cd /path/to/cloudNative
   ```

2. **Build the Serverless Application:**
   This command tells SAM to bundle all the Python code inside the `serverless/` directory and install the dependencies found in each `requirements.txt`.
   ```bash
   sam build
   ```

3. **Deploy to AWS:**
   Run the guided deployment. It will walk you through setting up stack names and regions.
   ```bash
   sam deploy --guided
   ```
   **During the prompts:**
   - Stack Name: `pixel-canvas-stack` (or similar)
   - AWS Region: e.g., `us-east-1`
   - Allow SAM CLI IAM role creation: `Y`
   - Disable rollback (optional): `Y`
   - *Save arguments to configuration file:* `Y`

4. **Capture the Outputs!**
   When the deployment finishes, the SAM CLI will print several Outputs to your terminal. **Copy these down**, as you will need them for the frontend:
   - `FrontendWebsiteURL`: e.g., `https://dxxxxxxxxxx.cloudfront.net`
   - `RestApiURL`: e.g., `https://xxxxx.execute-api.us-east-1.amazonaws.com/Prod`
   - `WebSocketURL`: e.g., `wss://xxxxx.execute-api.us-east-1.amazonaws.com/production`

---

## Phase 3: Post-Deployment Configs

### 1. Configure Discord OAuth Redirect URI
Now that you have your `RestApiURL` and `FrontendWebsiteURL`, you must inform Discord where to send users after they log in.
- Go back to the Discord Developer Portal -> OAuth2 -> General.
- Add exactly this Redirect URI:
  `<RestApiURL>/auth/callback` (e.g., `https://xxxxx.execute-api.us-east-1.amazonaws.com/Prod/auth/callback`)

### 2. Configure Discord Interaction Endpoint
To allow Discord to send `/draw` commands to your `discord_proxy` Lambda:
- Go to Discord Developer Portal -> General Information.
- Set the **Interactions Endpoint URL** to:
  `<RestApiURL>/discord/interactions`

### 3. Configure CORS for Production
**IMPORTANT:** The backend API currently defaults to allowing requests from ANY origin (`*`). This is convenient for development but **NOT SECURE FOR PRODUCTION**.

Before deploying to production, re-deploy the stack with a restricted CORS origin:
```bash
sam deploy \
  --parameter-overrides AllowedOrigin="'https://your-frontend-domain.com'" \
  --stack-name pixel-canvas-stack \
  --region us-east-1
```

**For local development** with the default CloudFront domain:
```bash
# After initial deployment, capture your FrontendWebsiteURL (e.g., https://dXXXXX.cloudfront.net)
sam deploy \
  --parameter-overrides AllowedOrigin="'https://dXXXXX.cloudfront.net'" \
  --stack-name pixel-canvas-stack \
  --region us-east-1
```

**Multi-origin CORS:** If you need to support multiple origins (e.g., dev, staging, production), you can:
- Deploy with a custom Lambda authorizer that validates origins in code
- Or maintain separate stacks for each environment

---

## Phase 4: Deploying the Frontend (Svelte)

Now that the backend is live, you must configure the static Svelte application to point to the correct live URLs, build the static files, and upload them to the S3 bucket that CloudFront monitors.

1. **Navigate to the frontend directory:**
   ```bash
   cd frontend
   ```

2. **Install frontend dependencies:**
   ```bash
   npm install
   ```

3. **Configure Environment Variables:**
   Create a `.env` file inside the `frontend/` directory with the URLs you copied from the SAM Outputs:
   ```env
   VITE_API_URL=https://xxxxx.execute-api.us-east-1.amazonaws.com/Prod
   VITE_WSS_URL=wss://xxxxx.execute-api.us-east-1.amazonaws.com/production
   ```

4. **Build the SPA:**
   This command compiles Svelte into static, highly-optimized HTML/JS/CSS inside the `dist/` directory.
   ```bash
   npm run build
   ```

5. **Upload to S3:**
   Find the exact name of your frontend S3 bucket. You can find this in the AWS Console (S3 service) or by looking closely at the SAM deployment logs. It usually starts with `pixel-canvas-stack-frontendbucket-xxxxxx`.
   
   Sync the built files to the bucket:
   ```bash
   aws s3 sync dist/ s3://YOUR_FRONTEND_BUCKET_NAME --delete
   ```

**You are done!** 
Visit the `FrontendWebsiteURL` (your CloudFront URL) in your browser. You should see the Brutalist Svelte canvas UI, be able to log in via Discord, draw pixels, and instantly see the real-time WebSocket broadcast reflections.
