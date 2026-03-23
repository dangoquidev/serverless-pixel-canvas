import os
import json
import boto3
from aws_lambda_powertools import Logger, Tracer
from aws_lambda_powertools.utilities.typing import LambdaContext
from aws_lambda_powertools.logging import correlation_paths

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

        return True, ""
    except Exception:
        return False, "Invalid payload format"


# --- Main Handler ---


@tracer.capture_lambda_handler
@logger.inject_lambda_context(correlation_id_path=correlation_paths.API_GATEWAY_REST)
def lambda_handler(event: dict, context: LambdaContext):
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
            logger.warning(
                "Validation failed", extra={"error": error_msg, "payload": body}
            )
            return create_response(400, {"error": error_msg})

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
            },
        )

        logger.info("Pixel event published", user_id=user_id, x=body["x"], y=body["y"])

        # 5. Return 202 Accepted (Standard for async processing)
        return create_response(
            202, {"message": "Accepted", "request_id": context.aws_request_id}
        )

    except json.JSONDecodeError:
        return create_response(400, {"error": "Invalid JSON"})
    except Exception as e:
        logger.exception("Unexpected worker failure")
        return create_response(500, {"error": "Internal server error"})
