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
canvas_table = dynamodb.Table(os.environ.get("CANVAS_TABLE_NAME"))

class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return int(obj) if obj % 1 == 0 else float(obj)
        return super(DecimalEncoder, self).default(obj)

# --- Helper Functions ---

def build_api_response(status_code: int, body_dict: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {
            "Access-Control-Allow-Origin": "*",
            "Content-Type": "application/json",
            "Cache-Control": "public, max-age=5"
        },
        "body": json.dumps(body_dict, cls=DecimalEncoder),
    }

@tracer.capture_method
def fetch_chunk_pixels(chunk_id: str) -> list:
    """Fetches pixels with a ProjectionExpression to reduce RCU usage."""
    pixels = []

    query_params = {
        "KeyConditionExpression": Key("ChunkId").eq(chunk_id),
        "ProjectionExpression": "PixelId, color"
    }

    response = canvas_table.query(**query_params)
    pixels.extend(response.get("Items", []))

    while "LastEvaluatedKey" in response:
        query_params["ExclusiveStartKey"] = response["LastEvaluatedKey"]
        response = canvas_table.query(**query_params)
        pixels.extend(response.get("Items", []))

    return pixels

# --- Main Handler ---

@tracer.capture_lambda_handler
@logger.inject_lambda_context
def lambda_handler(event: dict, context: LambdaContext) -> dict:

    query_params = event.get("queryStringParameters") or {}
    try:
        cx = int(query_params.get("cx", 0))
        cy = int(query_params.get("cy", 0))
    except (ValueError, TypeError):
        return build_api_response(400, {"error": "cx and cy must be integers"})

    chunk_id = f"CHUNK#{cx}#{cy}"

    try:
        pixels = fetch_chunk_pixels(chunk_id)

        logger.info("Chunk loaded", chunk_id=chunk_id, count=len(pixels))

        return build_api_response(200, {
            "chunk": chunk_id,
            "pixels": pixels,
            "request_id": context.aws_request_id
        })

    except Exception:
        logger.exception("DynamoDB Query Failed")
        return build_api_response(500, {"error": "Internal server error"})
