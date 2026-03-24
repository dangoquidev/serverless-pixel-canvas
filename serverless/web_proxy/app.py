import os
import json
import re
import boto3
import sys
sys.path.insert(0, '/opt/python')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from aws_lambda_powertools import Logger, Tracer
from aws_lambda_powertools.utilities.typing import LambdaContext
from aws_lambda_powertools.logging import correlation_paths

# Import token bucket rate limiter
try:
    from shared_modules.token_bucket import check_rate_limit, create_rate_limit_response
except ImportError:
    # Fallback: rate limiting disabled if import fails
    def check_rate_limit(user_id: str, cost: int = 1) -> tuple:
        return True, {}
    def create_rate_limit_response(allowed: bool, details: dict) -> dict:
        return {}

# 1. Initialization
logger = Logger()
tracer = Tracer()
sns_client = boto3.client("sns")

SNS_TOPIC_ARN = os.environ.get("SNS_TOPIC_ARN")

# --- Helper Functions ---

def create_response(status_code: int, body: dict) -> dict:
    """Standardized response helper with CORS."""
    return {
        "statusCode": status_code,
        "headers": {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,Authorization",
            "Access-Control-Allow-Methods": "POST,OPTIONS",
            "Content-Type": "application/json",
        },
        "body": json.dumps(body),
    }

def validate_pixel(body: dict) -> tuple[bool, str]:
    """Strict validation of pixel data types and values."""
    try:
        x, y = body.get("x"), body.get("y")
        color = body.get("color")

        if None in (x, y, color):
            return False, "Missing x, y, or color"

        if not (isinstance(x, int) and isinstance(y, int)):
            return False, "Coordinates must be integers"

        if not (0 <= x < 1000 and 0 <= y < 1000):
            return False, "Coordinates out of bounds (0-999)"

        # Validate color is valid hex format (#RRGGBB)
        if not re.match(r"^#[0-9A-Fa-f]{6}$", color):
            return False, "Color must be valid hex format (#RRGGBB)"

        return True, ""
    except Exception:
        return False, "Invalid payload format"

# --- Main Handler ---

@tracer.capture_lambda_handler
@logger.inject_lambda_context(correlation_id_path=correlation_paths.API_GATEWAY_REST)
def lambda_handler(event: dict, context: LambdaContext) -> dict:
    """
    Lightweight proxy that validates pixel draws and fouts them to SNS.
    """
    # 1. Extract Authorizer Context (The "Shuttle")
    auth_ctx = event.get("requestContext", {}).get("authorizer", {})
    user_id = auth_ctx.get("userId")

    if not user_id:
        logger.error("Unauthorized access attempt: No userId in context")
        return create_response(401, {"error": "Unauthorized"})

    try:
        # 2. Parse and Validate
        body = json.loads(event.get("body", "{}"))
        is_valid, error_msg = validate_pixel(body)

        if not is_valid:
            logger.warning("Validation failed", extra={"error": error_msg, "payload": body})
            return create_response(400, {"error": error_msg})

        # 2.5. Check Rate Limit using Token Bucket
        allowed, rate_limit_details = check_rate_limit(user_id, cost=1)
        if not allowed:
            logger.info("Rate limit exceeded", extra={"user_id": user_id, **rate_limit_details})
            
            # Return 429 with rate limit info in headers
            response = create_response(429, {
                "error": "rate_limit_exceeded",
                "message": f"Rate limited. Retry after {rate_limit_details.get('retry_after_seconds', 1)} seconds.",
                "retry_after_seconds": rate_limit_details.get('retry_after_seconds', 1),
            })
            response["headers"]["Retry-After"] = str(int(rate_limit_details.get('retry_after_seconds', 1)))
            response["headers"]["X-RateLimit-Limit"] = str(int(rate_limit_details.get('limit', 20)))
            response["headers"]["X-RateLimit-Remaining"] = str(int(rate_limit_details.get('tokens_remaining', 0)))
            return response

        # 3. Enrich Payload (Never trust the client-provided user_id)
        pixel_event = {
            "action": "draw_pixel",
            "correlation_id": context.aws_request_id,
            "payload": {
                "user_id": user_id,
                "x": body["x"],
                "y": body["y"],
                "color": body["color"],
            },
        }

        sns_client.publish(
            TopicArn=SNS_TOPIC_ARN,
            Message=json.dumps(pixel_event),
            MessageAttributes={
                "action": {"DataType": "String", "StringValue": "draw_pixel"}
            }
        )

        logger.info("Pixel event published", user_id=user_id, x=body["x"], y=body["y"])

        # 5. Return 202 Accepted (Standard for async processing)
        response = create_response(202, {
            "message": "Accepted",
            "request_id": context.aws_request_id
        })
        
        # Add rate limit headers to successful response too
        response["headers"]["X-RateLimit-Limit"] = str(int(rate_limit_details.get('limit', 20)))
        response["headers"]["X-RateLimit-Remaining"] = str(int(rate_limit_details.get('tokens_remaining', 0)))
        response["headers"]["X-RateLimit-Reset-In"] = str(int(rate_limit_details.get('reset_in_seconds', 0)))
        
        return response

    except json.JSONDecodeError:
        return create_response(400, {"error": "Invalid JSON"})
    except Exception as e:
        logger.exception("Unexpected worker failure")
        return create_response(500, {"error": "Internal server error"})
