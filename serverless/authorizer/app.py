import os
import uuid
import jwt
from aws_lambda_powertools import Logger, Tracer
from aws_lambda_powertools.utilities import parameters
from aws_lambda_powertools.utilities.typing import LambdaContext

logger = Logger()
tracer = Tracer()


def get_jwt_secret() -> str:
    """Fetches JWT secret from Secrets Manager (cached 5 min by Powertools)."""
    app_secrets = parameters.get_secret(
        os.environ["APP_SECRET_NAME"], transform="json"
    )
    return app_secrets.get("JwtSecret", "")


# --- Helper Functions ---


def generate_policy(principal_id: str, effect: str, resource: str) -> dict:
    """Generates the IAM policy expected by API Gateway Custom Authorizers."""
    auth_response = {"principalId": principal_id}
    if effect and resource:
        policy_document = {
            "Version": "2012-10-17",
            "Statement": [
                {"Action": "execute-api:Invoke", "Effect": effect, "Resource": resource}
            ],
        }
        auth_response["policyDocument"] = policy_document
    return auth_response


def extract_token(event: dict) -> str:
    """Safely extracts and formats the Bearer token from the API Gateway event."""
    token = event.get("authorizationToken", "")
    if token.lower().startswith("bearer "):
        return token.split(" ", 1)[-1].strip()
    return token.strip()


# --- Main Handler ---


@tracer.capture_lambda_handler
@logger.inject_lambda_context
def lambda_handler(event: dict, context: LambdaContext):
    correlation_id = str(uuid.uuid4())
    method_arn = event.get("methodArn", "")

    # 1. Extract Token
    token = extract_token(event)

    if not token:
        logger.warning(
            "Missing authorization token", extra={"correlation_id": correlation_id}
        )
        return generate_policy("unauthorized", "Deny", method_arn)

    # 2. Verify and Decode JWT
    jwt_secret = get_jwt_secret()
    try:
        decoded_payload = jwt.decode(token, jwt_secret, algorithms=["HS256"])
        user_id = decoded_payload.get("sub")

        # Ensure the token actually contains the identity we need
        if not user_id:
            raise jwt.InvalidTokenError("Token missing 'sub' claim")

        logger.info(
            "User successfully authorized",
            extra={"user_id": user_id, "correlation_id": correlation_id},
        )

        # Token is valid: Allow access to the API resource
        return generate_policy(user_id, "Allow", method_arn)

    except jwt.ExpiredSignatureError:
        logger.warning("Token expired", extra={"correlation_id": correlation_id})
        return generate_policy("unauthorized", "Deny", method_arn)

    except jwt.InvalidTokenError as e:
        logger.warning(
            "Invalid token", extra={"error": str(e), "correlation_id": correlation_id}
        )
        return generate_policy("unauthorized", "Deny", method_arn)

    except Exception as e:
        logger.exception(
            "Internal authorization error", extra={"correlation_id": correlation_id}
        )
        return generate_policy("unauthorized", "Deny", method_arn)
