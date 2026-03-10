# Brutalist Serverless Pixel Canvas Frontend

This is a highly-optimized, "Brutalist" themed frontend for the Serverless Pixel Canvas. It uses Svelte (compiled via Vite) and raw HTML5 Canvas to handle immense loads of real-time incoming WebSocket pixel data with zero Virtual DOM overhead.

## Architecture
- **Framework:** Svelte & Vite
- **Data Stores:** Native Svelte Stores (`authStore`, `wsStore`, `canvasStore`)
- **Graphics:** HTML5 `<canvas>` (managed completely out of the Svelte reactivity loop)
- **Styling:** Raw CSS variables, `app.css`

## Setup & Deployment

1. **Install Dependencies:**
   ```bash
   npm install
   ```

2. **Configure Environment Variables:**
   Before running locally or building for production, you must link the frontend to your AWS backend.

   Create a `.env` file in this `frontend/` directory (next to this README):
   ```env
   VITE_API_URL=https://<API_GATEWAY_ID>.execute-api.<REGION>.amazonaws.com/Prod
   VITE_WSS_URL=wss://<WEBSOCKET_API_ID>.execute-api.<REGION>.amazonaws.com/production
   ```
   *Note: You can find these exact URLs in the AWS CloudFormation/SAM Outputs tab after running `sam deploy` on the backend.*

3. **Run Locally:**
   ```bash
   npm run dev
   ```
   This will start a local Hot-Module Replacement server at `http://localhost:5173`. Make sure your backend APIs (API Gateway) have CORS configured if you are testing locally against production endpoints.

4. **Build for Production (S3/CloudFront):**
   ```bash
   npm run build
   ```
   This will generate a `dist/` folder containing the static HTML, optimized JS chunks, and minified CSS.

   To deploy, sync the contents of the `dist/` directory directly to your AWS S3 `FrontendBucket`:
   ```bash
   aws s3 sync dist/ s3://<YOUR_FRONTEND_BUCKET_NAME>
   ```
   Amazon CloudFront will automatically serve the new files using the S3 bucket as an origin.
