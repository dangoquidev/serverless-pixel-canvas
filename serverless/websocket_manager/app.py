import os
import json
import boto3
from aws_lambda_powertools import Logger, Tracer
from aws_lambda_powertools.utilities.typing import LambdaContext

logger = Logger()
tracer = Tracer()

# 2. Initialization (Cold Start Optimization)
dynamodb = boto3.resource("dynamodb")
CONNECTIONS_TABLE_NAME = os.environ.get("CONNECTIONS_TABLE_NAME")
connections_table = dynamodb.Table(CONNECTIONS_TABLE_NAME)

# --- Helper Functions ---


def handle_connect(connection_id: str) -> None:
    """Saves the new WebSocket connection to DynamoDB."""
    connections_table.put_item(Item={"ConnectionId": connection_id})


def handle_disconnect(connection_id: str) -> None:
    """Removes the disconnected WebSocket connection from DynamoDB."""
    connections_table.delete_item(Key={"ConnectionId": connection_id})


# --- Main Handler ---


@tracer.capture_lambda_handler
@logger.inject_lambda_context
def lambda_handler(event: dict, context: LambdaContext):
    """Main orchestrator for managing WebSocket connections."""
    correlation_id = context.aws_request_id

    request_context = event.get("requestContext", {})
    connection_id = request_context.get("connectionId")
    event_type = request_context.get("eventType")  # CONNECT or DISCONNECT

    if not connection_id:
        logger.warning(
            json.dumps(
                {
                    "function": "websocket_manager",
                    "message": "ConnectionId missing from request context",
                    "correlation_id": correlation_id,
                }
            )
        )
        return {"statusCode": 400, "body": "ConnectionId missing"}

    try:
        if event_type == "CONNECT":
            handle_connect(connection_id)
            logger.info(
                json.dumps(
                    {
                        "function": "websocket_manager",
                        "message": "Client connected",
                        "connection_id": connection_id,
                        "correlation_id": correlation_id,
                    }
                )
            )

        elif event_type == "DISCONNECT":
            handle_disconnect(connection_id)
            logger.info(
                json.dumps(
                    {
                        "function": "websocket_manager",
                        "message": "Client disconnected",
                        "connection_id": connection_id,
                        "correlation_id": correlation_id,
                    }
                )
            )

        else:
            logger.warning(
                json.dumps(
                    {
                        "function": "websocket_manager",
                        "message": f"Unhandled event type: {event_type}",
                        "connection_id": connection_id,
                        "correlation_id": correlation_id,
                    }
                )
            )

        # Must return 200 OK for API Gateway to accept the connection
        return {"statusCode": 200, "body": "Success"}

    except Exception as e:
        logger.error(
            json.dumps(
                {
                    "function": "websocket_manager",
                    "message": "Error managing connection",
                    "error": str(e),
                    "connection_id": connection_id,
                    "event_type": event_type,
                    "correlation_id": correlation_id,
                }
            )
        )
        # Returning 500 drops the connection gracefully
        return {"statusCode": 500, "body": "Internal Server Error"}
