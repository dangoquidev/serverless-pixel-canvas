import os
import json
import uuid
import boto3
from aws_lambda_powertools import Logger, Tracer
from aws_lambda_powertools.utilities.typing import LambdaContext

logger = Logger()
tracer = Tracer()

# 2. Initialization (Cold Start Optimization)
sns_client = boto3.client("sns")
SNS_TOPIC_ARN = os.environ.get("SNS_TOPIC_ARN")

# --- Helper Functions ---


def create_response(status_code: int, body: dict) -> dict:
    """Helper to format API Gateway HTTP responses with CORS headers."""
    return {
        "statusCode": status_code,
        "headers": {
            "Access-Control-Allow-Origin": "*",
            "Content-Type": "application/json",
        },
        "body": json.dumps(body),
    }


def validate_payload(body: dict) -> list:
    """Validates that all required fields are present in the request body."""
    required_fields = ["x", "y", "color", "user_id"]
    missing = [field for field in required_fields if field not in body]
    return missing


def publish_event(payload: dict, correlation_id: str) -> None:
    """Publishes the validated pixel draw event to the SNS fan-out topic."""
    pixel_event = {
        "action": "draw_pixel",
        "correlation_id": correlation_id,
        "payload": payload,
    }
    sns_client.publish(TopicArn=SNS_TOPIC_ARN, Message=json.dumps(pixel_event))


# --- Main Handler ---


@tracer.capture_lambda_handler
@logger.inject_lambda_context
def lambda_handler(event: dict, context: LambdaContext):
    """Main orchestrator for acting as a lightweight proxy for pixel draws."""
    correlation_id = event.get("correlation_id", context.aws_request_id)

    logger.info(
        json.dumps(
            {
                "function": "web_proxy",
                "message": "Processing incoming pixel draw request",
                "correlation_id": correlation_id,
            }
        )
    )

    try:
        # 1. Parse Body
        body_str = event.get("body", "{}")
        body = json.loads(body_str)

        # 2. Validation
        missing_fields = validate_payload(body)
        if missing_fields:
            logger.warning(
                json.dumps(
                    {
                        "function": "web_proxy",
                        "message": "Validation failed",
                        "missing_fields": missing_fields,
                        "correlation_id": correlation_id,
                    }
                )
            )
            return create_response(
                400, {"error": f"Missing required fields: {', '.join(missing_fields)}"}
            )

        # 3. Publish Event
        publish_event(body, correlation_id)

        logger.info(
            json.dumps(
                {
                    "function": "web_proxy",
                    "message": "Successfully published pixel event",
                    "user_id": body.get("user_id"),
                    "correlation_id": correlation_id,
                }
            )
        )

        # 4. Asynchronous Acknowledge
        return create_response(
            202,
            {
                "message": "Pixel draw request accepted",
                "correlation_id": correlation_id,
            },
        )

    except json.JSONDecodeError:
        logger.error(
            json.dumps(
                {
                    "function": "web_proxy",
                    "message": "Invalid JSON body",
                    "correlation_id": correlation_id,
                }
            )
        )
        return create_response(400, {"error": "Invalid JSON format"})

    except Exception as e:
        logger.error(
            json.dumps(
                {
                    "function": "web_proxy",
                    "message": "Internal Server Error",
                    "error": str(e),
                    "correlation_id": correlation_id,
                }
            )
        )
        return create_response(500, {"error": "Internal Server Error"})
