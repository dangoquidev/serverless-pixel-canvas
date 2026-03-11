import os
import json
import boto3
from boto3.dynamodb.conditions import Key
from concurrent.futures import ThreadPoolExecutor, as_completed
from botocore.exceptions import ClientError
from aws_lambda_powertools import Logger, Tracer
from aws_lambda_powertools.utilities.typing import LambdaContext
from canvas_utils import pixel_to_binary

logger = Logger()
tracer = Tracer()

# --- Cold Start: SDK Initialization ---
dynamodb = boto3.resource("dynamodb")
CONNECTIONS_TABLE_NAME = os.environ.get("CONNECTIONS_TABLE_NAME")
WSS_API_ENDPOINT = os.environ.get("WSS_API_ENDPOINT")

connections_table = dynamodb.Table(CONNECTIONS_TABLE_NAME)
apigw_client = boto3.client("apigatewaymanagementapi", endpoint_url=WSS_API_ENDPOINT)

# --- Helper Functions ---


def _parse_sqs_record(record: dict) -> dict:
    """Unwraps the SQS → SNS envelope and returns the inner pixel payload."""
    try:
        sqs_body = json.loads(record.get("body", "{}"))
        sns_message = json.loads(sqs_body.get("Message", "{}"))
        return sns_message.get("payload", {})
    except Exception:
        return {}


def extract_pixels_to_binary(event: dict) -> bytearray:
    """Extracts payloads from SQS records and compiles them into a binary batch."""
    binary_payload = bytearray()

    for record in event.get("Records", []):
        payload = _parse_sqs_record(record)

        # Validate payload has the required fields
        if (
            not payload
            or "x" not in payload
            or "y" not in payload
            or "color" not in payload
        ):
            logger.warning(
                "Invalid or missing payload in record", extra={"record": record}
            )
            continue

        try:
            pixel_bytes = pixel_to_binary(
                x=int(payload["x"]), y=int(payload["y"]), color=payload["color"]
            )
            binary_payload.extend(pixel_bytes)
        except Exception as e:
            logger.warning(
                "Failed to encode pixel to binary",
                extra={"payload": payload, "error": str(e)},
            )

    return binary_payload


@tracer.capture_method
def fetch_active_connections() -> list[str]:
    """Queries DynamoDB GSI for all active WebSocket connection IDs."""
    connection_ids = []

    response = connections_table.query(
        IndexName="LiveStatusIndex",
        KeyConditionExpression=Key("LiveStatus").eq("ACTIVE"),
        ProjectionExpression="ConnectionId",
    )
    connection_ids.extend([item["ConnectionId"] for item in response.get("Items", [])])

    while "LastEvaluatedKey" in response:
        response = connections_table.query(
            IndexName="LiveStatusIndex",
            KeyConditionExpression=Key("LiveStatus").eq("ACTIVE"),
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
    """Removes disconnected clients from DynamoDB."""
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
    logger.append_keys(
        correlation_id=context.aws_request_id, function="broadcast_worker"
    )

    binary_payload = extract_pixels_to_binary(event)

    if not binary_payload:
        logger.info("No valid pixel updates found in batch.")
        return {"statusCode": 200, "body": "No updates."}

    try:
        connections = fetch_active_connections()
        if not connections:
            logger.info("No active WebSocket connections to broadcast to.")
            return {"statusCode": 200, "body": "No active connections."}

        stale_connections = broadcast_to_all(connections, binary_payload)

        cleanup_stale_connections(stale_connections)

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

    except Exception as e:
        logger.exception(
            "Critical error during broadcast workflow", extra={"error": str(e)}
        )
        raise
