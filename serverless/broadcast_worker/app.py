import os
import boto3
from concurrent.futures import ThreadPoolExecutor, as_completed
from botocore.exceptions import ClientError
from aws_lambda_powertools import Logger, Tracer
from aws_lambda_powertools.utilities.typing import LambdaContext

from canvas_utils import int_to_rgb, CHUNK_SIZE, stream_image_to_binary

logger = Logger()
tracer = Tracer()

dynamodb = boto3.resource("dynamodb")
CONNECTIONS_TABLE_NAME = os.environ.get("CONNECTIONS_TABLE_NAME")
WSS_API_ENDPOINT = os.environ.get("WSS_API_ENDPOINT")

connections_table = dynamodb.Table(CONNECTIONS_TABLE_NAME)
apigw_client = boto3.client("apigatewaymanagementapi", endpoint_url=WSS_API_ENDPOINT)

# --- Helper Functions ---


def extract_pixels_to_binary(event: dict) -> bytearray:
    """Extracts valid records and compiles them into a single binary payload."""
    binary_payload = bytearray()
    for record in event.get("Records", []):
        if record.get("eventName") in ("INSERT", "MODIFY"):
            new_image = record.get("dynamodb", {}).get("NewImage")
            if not new_image:
                continue

            try:
                # Let the pure utility function handle the parsing!
                binary_payload.extend(stream_image_to_binary(new_image))
            except (KeyError, ValueError) as e:
                # Catch both missing keys and malformed data (like bad integers)
                logger.warning(f"Malformed stream record skipped: {str(e)}")
                continue

    return binary_payload


@tracer.capture_method
def fetch_active_connections() -> list[str]:
    """Scans DynamoDB for all active WebSocket connection IDs."""
    connection_ids = []

    response = connections_table.scan(ProjectionExpression="ConnectionId")
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


def broadcast_to_client(connection_id: str, payload: bytearray) -> str | None:
    """Sends binary data to a single WS client. Returns connection_id if stale."""
    try:
        apigw_client.post_to_connection(ConnectionId=connection_id, Data=payload)
        return None
    except ClientError as e:
        if e.response["Error"]["Code"] == "GoneException":
            return connection_id
        logger.error(f"Failed to send to {connection_id}: {str(e)}")
        return None


@tracer.capture_method
def broadcast_to_all(connection_ids: list[str], payload: bytearray) -> list[str]:
    """Broadcasts to all clients concurrently."""
    stale_connections = []
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


@tracer.capture_method
def cleanup_stale_connections(stale_connection_ids: list[str]):
    """Removes disconnected clients from DynamoDB efficiently."""
    if not stale_connection_ids:
        return

    with connections_table.batch_writer() as batch:
        for connection_id in stale_connection_ids:
            batch.delete_item(Key={"ConnectionId": connection_id})


# --- Main Handler ---


@tracer.capture_lambda_handler
@logger.inject_lambda_context(clear_state=True)
def lambda_handler(event: dict, context: LambdaContext):
    """Main orchestrator for the real-time binary WebSocket broadcast."""
    correlation_id = context.aws_request_id
    logger.append_keys(correlation_id=correlation_id, function="broadcast_worker")

    # 1. Parse Event into pure binary!
    binary_payload = extract_pixels_to_binary(event)

    if not binary_payload:
        logger.info("No valid pixel updates found in stream.")
        return {"statusCode": 200, "body": "No updates."}

    try:
        # 2. Fetch Connections
        connections = fetch_active_connections()
        if not connections:
            logger.info("No active WebSocket connections to broadcast to.")
            return {"statusCode": 200, "body": "No active connections."}

        # 3. Broadcast
        stale_connections = broadcast_to_all(connections, binary_payload)

        # 4. Cleanup
        cleanup_stale_connections(stale_connections)

        # 5. Log Success
        pixels_sent = len(binary_payload) // 7

        logger.info(
            "Broadcast complete",
            extra={
                "pixels_sent": pixels_sent,
                "bytes_sent": len(binary_payload),
                "active_clients": len(connections) - len(stale_connections),
                "stale_cleaned": len(stale_connections),
            },
        )

        return {"statusCode": 200, "body": "Broadcast complete."}

    except Exception:
        logger.exception("Critical error during broadcast workflow")
        return {"statusCode": 500, "body": "Internal server error"}
