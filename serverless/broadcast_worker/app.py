import json
import os
import boto3
from concurrent.futures import ThreadPoolExecutor, as_completed
from botocore.exceptions import ClientError
from boto3.dynamodb.types import TypeDeserializer
from aws_lambda_powertools import Logger, Tracer
from aws_lambda_powertools.utilities.typing import LambdaContext

logger = Logger()
tracer = Tracer()

# 2. Initialization (Cold Start Optimization)
dynamodb = boto3.resource("dynamodb")
CONNECTIONS_TABLE_NAME = os.environ.get("CONNECTIONS_TABLE_NAME")
WSS_API_ENDPOINT = os.environ.get("WSS_API_ENDPOINT")

connections_table = dynamodb.Table(CONNECTIONS_TABLE_NAME)
apigw_client = boto3.client("apigatewaymanagementapi", endpoint_url=WSS_API_ENDPOINT)
deserializer = TypeDeserializer()

# --- Helper Functions ---


def deserialize_dynamodb_item(item: dict) -> dict:
    """Converts DynamoDB stream format to standard Python dicts."""
    return {k: deserializer.deserialize(v) for k, v in item.items()}


def extract_pixels_from_event(event: dict) -> list[dict]:
    """Extracts and formats new/modified pixels from the DynamoDB Stream event."""
    pixels = []
    for record in event.get("Records", []):
        if record.get("eventName") in ("INSERT", "MODIFY"):
            dynamodb_image = record.get("dynamodb", {}).get("NewImage")
            if dynamodb_image:
                pixels.append(
                    {
                        "type": "pixel_update",
                        "data": deserialize_dynamodb_item(dynamodb_image),
                    }
                )
    return pixels


def fetch_active_connections() -> list[str]:
    """Scans DynamoDB for all active WebSocket connection IDs, handling pagination."""
    connection_ids = []
    response = connections_table.scan(ProjectionExpression="ConnectionId")

    # Extract just the string IDs to make downstream processing cleaner
    connection_ids.extend([item["ConnectionId"] for item in response.get("Items", [])])

    while "LastEvaluatedKey" in response:
        response = connections_table.scan(
            ProjectionExpression="ConnectionId",
            ExclusiveStartKey=response["LastEvaluatedKey"],
        )
        connection_ids.extend(
            [item["ConnectionId"] for item in response.get("Items", [])]
        )

    return connection_ids


def broadcast_to_client(connection_id: str, payload: bytes) -> str | None:
    """Sends data to a single WS client. Returns the connection_id if stale (410 Gone)."""
    try:
        apigw_client.post_to_connection(ConnectionId=connection_id, Data=payload)
        return None
    except ClientError as e:
        if e.response["Error"]["Code"] == "GoneException":
            return connection_id
        logger.error(
            json.dumps(
                {"error": f"Failed to send to {connection_id}", "details": str(e)}
            )
        )
        return None


def broadcast_to_all(connection_ids: list[str], payload: bytes) -> list[str]:
    """Broadcasts to all clients concurrently. Returns a list of stale connection IDs."""
    stale_connections = []
    # Use ThreadPoolExecutor for concurrent network I/O
    with ThreadPoolExecutor(max_workers=50) as executor:
        futures = [
            executor.submit(broadcast_to_client, conn_id, payload)
            for conn_id in connection_ids
        ]
        for future in as_completed(futures):
            stale_id = future.result()
            if stale_id:
                stale_connections.append(stale_id)

    return stale_connections


def cleanup_stale_connections(stale_connection_ids: list[str]):
    """Removes disconnected clients from DynamoDB."""
    if not stale_connection_ids:
        return

    with connections_table.batch_writer() as batch:
        for connection_id in stale_connection_ids:
            batch.delete_item(Key={"ConnectionId": connection_id})


# --- Main Handler ---


@tracer.capture_lambda_handler
@logger.inject_lambda_context
def lambda_handler(event: dict, context: LambdaContext):
    """Main orchestrator for the real-time WebSocket broadcast."""
    correlation_id = context.aws_request_id

    # 1. Parse Event
    pixels_to_broadcast = extract_pixels_from_event(event)
    if not pixels_to_broadcast:
        return {"statusCode": 200, "body": "No updates."}

    message_payload = json.dumps(pixels_to_broadcast).encode("utf-8")

    try:
        # 2. Fetch Connections
        connections = fetch_active_connections()
        if not connections:
            return {"statusCode": 200, "body": "No active connections."}

        # 3. Broadcast
        stale_connections = broadcast_to_all(connections, message_payload)

        # 4. Cleanup
        cleanup_stale_connections(stale_connections)

        # 5. Log Success
        logger.info(
            json.dumps(
                {
                    "function": "broadcast_worker",
                    "message": "Broadcast complete",
                    "correlation_id": correlation_id,
                    "pixels_sent": len(pixels_to_broadcast),
                    "active_clients": len(connections) - len(stale_connections),
                    "stale_cleaned": len(stale_connections),
                }
            )
        )

        return {"statusCode": 200, "body": "Broadcast complete."}

    except Exception as e:
        logger.error(
            json.dumps(
                {
                    "function": "broadcast_worker",
                    "message": "Critical error during broadcast workflow",
                    "error": str(e),
                    "correlation_id": correlation_id,
                }
            )
        )
        return {"statusCode": 500, "body": "Internal server error"}
