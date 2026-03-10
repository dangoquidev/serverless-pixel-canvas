# API Gateway Custom Authorizer (`authorizer-fn`)

[cite_start]**Responsibility:** Secures the REST API by intercepting requests[cite: 341, 439, 686]. [cite_start]Decodes and validates the JWT provided by the frontend [cite: 797] and returns an IAM policy allowing or denying the execution of the requested API endpoint.

**Trigger:**
* **Source:** API Gateway (Custom Lambda Authorizer)
* **Target Route:** `POST /pixels`

**Environment Variables:**
* `JWT_SECRET`: For validating the token signature.

**IAM Permissions Required:**
* None specific (only basic Lambda execution). API Gateway requires `lambda:InvokeFunction` permission to trigger this authorizer.