import os
import json
import base64
import boto3
from boto3.dynamodb.conditions import Key
from aws_lambda_powertools import Logger, Tracer
from aws_lambda_powertools.utilities.typing import LambdaContext

# IMPORT FROM YOUR BRAND NEW LAYER!
from canvas_utils import build_binary_array

logger = Logger()
tracer = Tracer()

dynamodb = boto3.resource("dynamodb")
canvas_table = dynamodb.Table(os.environ.get("CANVAS_TABLE_NAME"))

# --- Helper Functions ---


def build_error_response(status_code: int, message: str) -> dict:
    """Helper for returning standard JSON errors."""
    return {
        "statusCode": status_code,
        "headers": {
            "Access-Control-Allow-Origin": "*",
            "Content-Type": "application/json",
        },
        "body": json.dumps({"error": message}),
    }


def build_success_response(binary_array: bytearray) -> dict:
    """Helper for returning standard binary responses."""
    return {
        "statusCode": 200,
        "headers": {
            "Access-Control-Allow-Origin": "*",
            "Content-Type": "application/octet-stream",
            "Cache-Control": "public, max-age=5",
        },
        "isBase64Encoded": True,
        "body": base64.b64encode(binary_array).decode("utf-8"),
    }


@tracer.capture_method
def fetch_chunk_minified(cx: int, cy: int) -> list:
    """Fetches minified pixels, reducing RCU usage and memory by over 60%."""
    items = []
    chunk_id = f"{cx}#{cy}"

    query_params = {
        "KeyConditionExpression": Key("c").eq(chunk_id),
        "ProjectionExpression": "p, co",
    }

    response = canvas_table.query(**query_params)
    items.extend(response.get("Items", []))

    while "LastEvaluatedKey" in response:
        query_params["ExclusiveStartKey"] = response["LastEvaluatedKey"]
        response = canvas_table.query(**query_params)
        items.extend(response.get("Items", []))

    return items


# --- Main Handler ---


@tracer.capture_lambda_handler
@logger.inject_lambda_context(clear_state=True)
def lambda_handler(event: dict, context: LambdaContext):
    logger.append_keys(correlation_id=context.aws_request_id)

    query_params = event.get("queryStringParameters") or {}
    try:
        cx = int(query_params.get("cx", 0))
        cy = int(query_params.get("cy", 0))
    except (ValueError, TypeError):
        return build_error_response(400, "cx and cy must be integers")

    try:
        items = fetch_chunk_minified(cx, cy)
        logger.info("Chunk loaded", chunk_x=cx, chunk_y=cy, count=len(items))

        binary_array = build_binary_array(items)

        return build_success_response(binary_array)

    except Exception:
        logger.exception("DynamoDB Query Failed")
        return build_error_response(500, "Internal server error")
