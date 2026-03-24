import os
import json
import re
import boto3
from boto3.session import Config
from aws_lambda_powertools import Logger, Tracer
from aws_lambda_powertools.utilities.typing import LambdaContext

from canvas_utils import build_pixel_item

logger = Logger()
tracer = Tracer()

# --- Cold Start: SDK Initialization ---
boto_config = Config(
    retries={"max_attempts": 3, "mode": "standard"}, max_pool_connections=50
)

dynamodb = boto3.resource("dynamodb", config=boto_config)
canvas_table = dynamodb.Table(os.environ.get("CANVAS_TABLE_NAME"))

# --- Helper Functions ---


def _parse_sqs_record(record: dict) -> dict:
    """Unwraps the SQS → SNS envelope and returns the full message."""
    sqs_body = json.loads(record.get("body", "{}"))
    return json.loads(sqs_body.get("Message", "{}"))


def _is_valid_payload(payload: dict) -> bool:
    """Returns True only if all required pixel fields are present and valid."""
    if not (payload.get("user_id") and "x" in payload and "y" in payload and "color" in payload):
        return False
    
    # Validate color is valid hex format (#RRGGBB)
    color = payload.get("color")
    if not re.match(r"^#[0-9A-Fa-f]{6}$", color):
        logger.warning("Invalid color hex format", extra={"color": color})
        return False
    
    return True


# NOTE: Rate limiting moved to web_proxy (token bucket algorithm)
# pixel_worker receives pre-validated pixels, no need to duplicate rate limiting here


def save_pixel(x: int, y: int, color: str, user_id: str) -> None:
    """Persists the formatted minified pixel to DynamoDB."""
    pixel_item = build_pixel_item(x, y, color, user_id)

    canvas_table.put_item(Item=pixel_item)


def clear_canvas() -> int:
    """Deletes all pixels from the canvas table. Returns number of deleted items."""
    deleted_count = 0
    scan_params = {
        "ProjectionExpression": "c, p",
    }

    response = canvas_table.scan(**scan_params)

    while True:
        items = response.get("Items", [])

        if items:
            with canvas_table.batch_writer() as batch:
                for item in items:
                    batch.delete_item(Key={"c": item["c"], "p": item["p"]})
                    deleted_count += 1

        if "LastEvaluatedKey" not in response:
            break

        response = canvas_table.scan(
            **scan_params,
            ExclusiveStartKey=response["LastEvaluatedKey"],
        )

    return deleted_count


def _process_record(record: dict, correlation_id: str) -> bool:
    """Processes a single SQS record. Returns True on success, False on skip."""
    message = _parse_sqs_record(record)
    action = message.get("action")

    if action == "clean":
        deleted_count = clear_canvas()
        logger.info(
            "Canvas cleaned",
            extra={
                "deleted_count": deleted_count,
                "correlation_id": correlation_id,
            },
        )
        return True

    payload = message.get("payload", {})

    if not _is_valid_payload(payload):
        logger.warning(
            "Missing required fields in payload",
            extra={"payload": payload, "correlation_id": correlation_id},
        )
        return False

    user_id = payload["user_id"]
    x = int(payload["x"])
    y = int(payload["y"])
    color = payload["color"]

    # Rate limiting is handled by web_proxy (token bucket) before SNS publish
    # pixel_worker receives pre-validated, rate-limited pixels only

    save_pixel(x, y, color, user_id)

    logger.info(
        "Pixel drawn successfully",
        extra={
            "user_id": user_id,
            "x": x,
            "y": y,
            "color": color,
            "correlation_id": correlation_id,
        },
    )
    return True


# --- Main Handler ---


@tracer.capture_lambda_handler
@logger.inject_lambda_context
def lambda_handler(event: dict, context: LambdaContext) -> dict:
    """Processes pixel draw events arriving via SQS from the SNS fanout."""
    records = event.get("Records", [])
    if not records:
        return {"statusCode": 200, "body": "No records to process"}

    processed_count = 0

    for record in records:
        try:
            if _process_record(record, context.aws_request_id):
                processed_count += 1
        except Exception as e:
            logger.exception(
                "Unrecoverable error processing record",
                extra={"error": str(e), "correlation_id": context.aws_request_id},
            )
            raise  # Let SQS handle the retry / DLQ routing

    return {
        "statusCode": 200,
        "body": f"Batch processed successfully: {processed_count}/{len(records)} handled",
    }
