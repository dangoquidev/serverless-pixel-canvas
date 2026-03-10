import json
import os
import boto3
from aws_lambda_powertools import Logger, Tracer
from aws_lambda_powertools.utilities.typing import LambdaContext

logger = Logger()
tracer = Tracer()

# 2. Initialization
sqs = boto3.client("sqs")
PIXEL_WORKER_QUEUE_URL = os.environ.get("PIXEL_WORKER_QUEUE_URL")

# --- Helper Functions ---


def redrive_message(message_body: str) -> bool:
    """Attempts to push a failed message back onto the main PixelWorkerQueue."""
    if not PIXEL_WORKER_QUEUE_URL:
        logger.error("PIXEL_WORKER_QUEUE_URL environment variable is missing!")
        return False

    try:
        # Re-queue the original SNS payload
        sqs.send_message(QueueUrl=PIXEL_WORKER_QUEUE_URL, MessageBody=message_body)
        return True
    except Exception as e:
        logger.error(f"Failed to redrive message: {str(e)}")
        return False


# --- Main Handler ---


@tracer.capture_lambda_handler
@logger.inject_lambda_context
def lambda_handler(event: dict, context: LambdaContext):
    """Processes messages that failed to be handled by the Pixel Worker and landed in the DLQ."""
    correlation_id = context.aws_request_id

    records = event.get("Records", [])
    if not records:
        return {"statusCode": 200, "body": "No records in DLQ batch"}

    logger.info(
        json.dumps(
            {
                "function": "dlq_processor",
                "message": f"Processing {len(records)} messages from the DLQ",
                "correlation_id": correlation_id,
            }
        )
    )

    success_count = 0
    fail_count = 0

    for record in records:
        message_id = record.get("messageId")
        message_body = record.get("body", "{}")

        # TODO: inspect the error attribute traces, have logic whether to DROP or REDRIVE the message.
        # Log it and attempt a redrive.

        try:
            # Try to extract the payload to see what failed
            sqs_body = json.loads(message_body)
            sns_message = json.loads(sqs_body.get("Message", "{}"))
            payload = sns_message.get("payload", {})
            user_id = payload.get("user_id", "Unknown")

            logger.warning(
                json.dumps(
                    {
                        "function": "dlq_processor",
                        "message": f"Analyzing failed message for user {user_id}",
                        "sqs_message_id": message_id,
                        "payload": payload,
                        "correlation_id": correlation_id,
                    }
                )
            )

            # Optionally: implement conditional redrive logic here
            # e.g. "if retries < MAX_RETRIES: redrive_message()"

            if redrive_message(message_body):
                success_count += 1
                logger.info(
                    json.dumps(
                        {
                            "function": "dlq_processor",
                            "message": f"Successfully redrove message {message_id}",
                            "correlation_id": correlation_id,
                        }
                    )
                )
            else:
                fail_count += 1

        except json.JSONDecodeError:
            logger.error(
                json.dumps(
                    {
                        "function": "dlq_processor",
                        "message": f"Unparseable message in DLQ: {message_id}",
                        "body_content": message_body[:200],  # Log first 200 chars
                        "correlation_id": correlation_id,
                    }
                )
            )
            fail_count += 1
            # Messages that can't be parsed are ignored (deleted from DLQ automatically by Lambda integration)

    return {
        "statusCode": 200,
        "body": f"Processed DLQ: {success_count} redriven, {fail_count} failed",
    }
