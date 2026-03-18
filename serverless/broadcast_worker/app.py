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
sqs = boto3.client("sqs")
CONNECTIONS_TABLE_NAME = os.environ.get("CONNECTIONS_TABLE_NAME")
WSS_API_ENDPOINT = os.environ.get("WSS_API_ENDPOINT")
BATCH_BROADCAST_QUEUE_URL = os.environ.get("BATCH_BROADCAST_QUEUE_URL")
# Threshold for splitting into batches (higher = fewer invocations, more per-Lambda work)
BATCH_THRESHOLD = int(os.environ.get("BATCH_THRESHOLD", "5000"))
BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "500"))

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
    """Fetches all active WebSocket connection IDs efficiently.
    
    With TTL enabled on the connections table, stale entries are automatically removed,
    so we only need to fetch remaining entries. Uses scan with projection to minimize data transfer.
    """
    connection_ids = []
    response = connections_table.scan(
        ProjectionExpression="ConnectionId",
        # Limit scan to reduce RCU consumption in busy scenarios
    )

    # Extract just the string IDs
    connection_ids.extend([item["ConnectionId"] for item in response.get("Items", [])])

    # Handle pagination if table has many connections
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
    """Broadcasts to all clients using SQS fan-out for large connection counts.
    
    For small broadcasts, uses ThreadPoolExecutor directly.
    For large broadcasts, splits into batches and fans-out via SQS to prevent
    single Lambda timeout/memory issues and enable horizontal scaling.
    """
    
    # Small broadcasts: direct ThreadPoolExecutor approach
    if len(connection_ids) <= BATCH_THRESHOLD:
        return _broadcast_direct(connection_ids, payload)
    
    # Large broadcasts: fan-out via SQS
    logger.info(
        json.dumps(
            {
                "message": "Using SQS fan-out for large broadcast",
                "total_connections": len(connection_ids),
                "num_batches": (len(connection_ids) + BATCH_SIZE - 1) // BATCH_SIZE,
                "batch_size": BATCH_SIZE,
            }
        )
    )
    return _broadcast_fan_out_sqs(connection_ids, payload)


def _broadcast_direct(connection_ids: list[str], payload: bytes) -> list[str]:
    """Direct broadcast using ThreadPoolExecutor for small connection counts."""
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


def _broadcast_fan_out_sqs(connection_ids: list[str], payload: bytes) -> list[str]:
    """Fan-out broadcast via SQS for large connection counts.
    
    Splits connections into batches and queues each batch to SQS,
    allowing parallel processing by multiple Lambda invocations.
    """
    if not BATCH_BROADCAST_QUEUE_URL:
        logger.warning("BATCH_BROADCAST_QUEUE_URL not configured, falling back to direct")
        return _broadcast_direct(connection_ids, payload)
    
    # Split connections into batches
    batches = [
        connection_ids[i : i + BATCH_SIZE]
        for i in range(0, len(connection_ids), BATCH_SIZE)
    ]
    
    # Send batch tasks to SQS
    try:
        for idx, batch in enumerate(batches):
            sqs.send_message(
                QueueUrl=BATCH_BROADCAST_QUEUE_URL,
                MessageBody=json.dumps(
                    {
                        "connections": batch,
                        "payload": payload.decode("utf-8"),
                        "batch_index": idx,
                        "total_batches": len(batches),
                    }
                ),
            )
        logger.info(
            json.dumps(
                {
                    "message": "Enqueued broadcast batches",
                    "num_batches": len(batches),
                    "queue_url": BATCH_BROADCAST_QUEUE_URL,
                }
            )
        )
        return []  # Stale connections handled by batch processors
    except ClientError as e:
        logger.error(
            json.dumps({
                "message": "Failed to enqueue batches, falling back to direct",
                "error": str(e),
            })
        )
        return _broadcast_direct(connection_ids, payload)


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
def handle_batch_broadcast(event: dict, context: LambdaContext):
    """Handles a single batch broadcast from SQS fanout.
    
    Invoked by SQS for each batch of connections when broadcasts exceed threshold.
    Processes the connection batch and reports stale connections back.
    """
    correlation_id = context.aws_request_id
    
    try:
        # Parse SQS message
        body = event.get("Records", [{}])[0].get("body", "{}")
        batch_data = json.loads(body)
        
        connections = batch_data.get("connections", [])
        payload_str = batch_data.get("payload", "")
        batch_idx = batch_data.get("batch_index", 0)
        total_batches = batch_data.get("total_batches", 1)
        
        if not connections:
            return {"statusCode": 200, "body": "No connections in batch"}
        
        # Convert payload back to bytes
        payload = payload_str.encode("utf-8") if isinstance(payload_str, str) else payload_str
        
        # Broadcast to this batch
        stale_connections = _broadcast_direct(connections, payload)
        
        # Cleanup stale connections
        cleanup_stale_connections(stale_connections)
        
        logger.info(
            json.dumps(
                {
                    "function": "broadcast_worker.batch",
                    "correlation_id": correlation_id,
                    "batch_index": batch_idx,
                    "total_batches": total_batches,
                    "connections_in_batch": len(connections),
                    "stale_cleaned": len(stale_connections),
                }
            )
        )
        
        return {"statusCode": 200, "body": f"Batch {batch_idx}/{total_batches} complete"}
        
    except Exception as e:
        logger.error(
            json.dumps(
                {
                    "function": "broadcast_worker.batch",
                    "message": "Error processing batch broadcast",
                    "error": str(e),
                    "correlation_id": correlation_id,
                }
            )
        )
        return {"statusCode": 500, "body": "Batch processing failed"}


@tracer.capture_lambda_handler
@logger.inject_lambda_context
def lambda_handler(event: dict, context: LambdaContext) -> dict:
    """Main orchestrator for real-time WebSocket broadcasts.
    
    For broadcasts to <= 5000 connections: Direct ThreadPoolExecutor approach
    For broadcasts to > 5000 connections: SQS fan-out to batch processors
    
    This ensures we stay within Lambda limits and enable horizontal scaling.
    """
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

        # 3. Broadcast (with auto fan-out for large broadcasts)
        stale_connections = broadcast_to_all(connections, message_payload)

        # 4. Cleanup (direct broadcasts only; fan-out batches handle their own)
        if stale_connections:
            cleanup_stale_connections(stale_connections)

        # 5. Log Success
        logger.info(
            json.dumps(
                {
                    "function": "broadcast_worker",
                    "message": "Broadcast complete",
                    "correlation_id": correlation_id,
                    "pixels_sent": len(pixels_to_broadcast),
                    "active_clients": len(connections),
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
