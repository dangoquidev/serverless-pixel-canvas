import os
import json
from decimal import Decimal
import boto3
from boto3.dynamodb.conditions import Key
from aws_lambda_powertools import Logger, Tracer
from aws_lambda_powertools.utilities.typing import LambdaContext

logger = Logger()
tracer = Tracer()

dynamodb = boto3.resource("dynamodb")
CANVAS_TABLE_NAME = os.environ.get("CANVAS_TABLE_NAME")
canvas_table = dynamodb.Table(CANVAS_TABLE_NAME)


class DecimalEncoder(json.JSONEncoder):
    """Helper to convert DynamoDB Decimals to standard numbers for JSON serialization."""

    def default(self, obj):
        if isinstance(obj, Decimal):
            return int(obj) if obj % 1 == 0 else float(obj)
        return super(DecimalEncoder, self).default(obj)


# --- Helper Functions ---


def extract_coordinates(event: dict) -> tuple[int, int]:
    """Extracts and validates chunk coordinates from the API Gateway event."""
    query_params = event.get("queryStringParameters") or {}
    cx_raw = query_params.get("cx", "0")
    cy_raw = query_params.get("cy", "0")

    # This will naturally raise a ValueError if they aren't integers, which we catch later
    return int(cx_raw), int(cy_raw)


def fetch_chunk_pixels(chunk_id: str) -> list:
    """Fetches all pixels for a given chunk, automatically handling DynamoDB pagination."""
    pixels = []

    response = canvas_table.query(KeyConditionExpression=Key("ChunkId").eq(chunk_id))
    pixels.extend(response.get("Items", []))

    while "LastEvaluatedKey" in response:
        response = canvas_table.query(
            KeyConditionExpression=Key("ChunkId").eq(chunk_id),
            ExclusiveStartKey=response["LastEvaluatedKey"],
        )
        pixels.extend(response.get("Items", []))

    return pixels


def build_api_response(status_code: int, body_dict: dict) -> dict:
    """Standardizes the API Gateway response format."""
    return {
        "statusCode": status_code,
        "headers": {
            "Access-Control-Allow-Origin": "*",
            "Content-Type": "application/json",
        },
        "body": json.dumps(body_dict, cls=DecimalEncoder),
    }


# --- Main Handler ---


@tracer.capture_lambda_handler
@logger.inject_lambda_context
def lambda_handler(event: dict, context: LambdaContext):
    """Main orchestrator for the GET /canvas endpoint."""
    correlation_id = context.aws_request_id

    # 1. Parse & Validate
    try:
        cx, cy = extract_coordinates(event)
    except ValueError:
        logger.warning(
            json.dumps(
                {
                    "message": "Invalid coordinates provided",
                    "correlation_id": correlation_id,
                }
            )
        )
        return build_api_response(400, {"error": "cx and cy must be valid integers"})

    chunk_id = f"CHUNK#{cx}#{cy}"

    # 2. Fetch Data & Respond
    try:
        pixels = fetch_chunk_pixels(chunk_id)

        logger.info(
            json.dumps(
                {
                    "function": "canvas_reader",
                    "message": f"Successfully loaded chunk {chunk_id}",
                    "pixel_count": len(pixels),
                    "correlation_id": correlation_id,
                }
            )
        )

        return build_api_response(200, {"chunk": chunk_id, "pixels": pixels})

    except Exception as e:
        logger.error(
            json.dumps(
                {
                    "function": "canvas_reader",
                    "message": "Failed to read from DynamoDB",
                    "error": str(e),
                    "correlation_id": correlation_id,
                }
            )
        )
        return build_api_response(500, {"error": "Failed to load canvas"})
