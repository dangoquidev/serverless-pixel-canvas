import json
import os
import time

import boto3
import requests
from aws_lambda_powertools import Logger, Tracer
from aws_lambda_powertools.utilities import parameters
from aws_lambda_powertools.utilities.typing import LambdaContext

logger = Logger()
tracer = Tracer()

s3 = boto3.client("s3")
sqs = boto3.client("sqs")

DISCORD_SECRET_NAME = os.environ.get("DISCORD_SECRET_NAME", "DiscordSecrets")
DISCORD_API_BASE = "https://discord.com/api/v10"
EXPIRATION_TIME = 1 * 24 * 60 * 60  # 1 day
DISCORD_NOTIFIER_DLQ_URL = os.environ.get("DISCORD_NOTIFIER_DLQ_URL")

# Circuit breaker: retry configuration
MAX_RETRIES = 3
INITIAL_BACKOFF_SECONDS = 1  # Start with 1 second
MAX_BACKOFF_SECONDS = 32  # Cap at 32 seconds


# --- Helper Functions ---

def get_discord_secrets() -> dict:
    """Fetches Discord secrets from Secrets Manager (cached by Powertools)."""
    return parameters.get_secret(DISCORD_SECRET_NAME, transform="json")


def get_discord_token_from_metadata(bucket_name: str, object_key: str) -> str | None:
    """Retrieves the Discord interaction token from S3 object metadata."""
    response = s3.head_object(Bucket=bucket_name, Key=object_key)
    return response.get("Metadata", {}).get("discord_token")


def patch_deferred_message(
    application_id: str,
    interaction_token: str,
    content: str,
) -> None:
    """
    Edits the original deferred interaction response with the snapshot URL.
    Implements exponential backoff retry for transient failures (5xx, timeouts).
    Raises HTTPError for permanent failures (4xx).
    """
    url = f"{DISCORD_API_BASE}/webhooks/{application_id}/{interaction_token}/messages/@original"
    payload = {"content": content}
    headers = {"Content-Type": "application/json"}

    last_exception = None
    
    for attempt in range(MAX_RETRIES + 1):
        try:
            response = requests.patch(url, json=payload, headers=headers, timeout=10)
            
            # 4xx errors are permanent failures, don't retry
            if 400 <= response.status_code < 500:
                logger.error(
                    json.dumps({
                        "message": "Discord API permanent failure (4xx)",
                        "status_code": response.status_code,
                        "response": response.text,
                        "url": url,
                    })
                )
                response.raise_for_status()
                return
            
            # 5xx and other errors are retryable
            if response.status_code >= 400:
                logger.warning(
                    json.dumps({
                        "message": "Discord API transient failure (5xx)",
                        "status_code": response.status_code,
                        "attempt": attempt + 1,
                        "max_retries": MAX_RETRIES,
                    })
                )
                # Will retry if attempts remain
                if attempt < MAX_RETRIES:
                    backoff = min(INITIAL_BACKOFF_SECONDS * (2 ** attempt), MAX_BACKOFF_SECONDS)
                    time.sleep(backoff)
                    last_exception = response
                    continue
                else:
                    response.raise_for_status()
            
            # Success (2xx/3xx)
            logger.info("Discord API call successful")
            return
            
        except (requests.Timeout, requests.ConnectionError) as e:
            # Transient network issues, retry with backoff
            logger.warning(
                json.dumps({
                    "message": "Discord API transient failure (network)",
                    "error": str(e),
                    "attempt": attempt + 1,
                    "max_retries": MAX_RETRIES,
                })
            )
            last_exception = e
            
            if attempt < MAX_RETRIES:
                backoff = min(INITIAL_BACKOFF_SECONDS * (2 ** attempt), MAX_BACKOFF_SECONDS)
                time.sleep(backoff)
            else:
                raise
        except requests.HTTPError:
            raise  # Re-raise after logging
    
    # All retries exhausted
    if last_exception:
        raise last_exception


def send_to_dlq(record: dict, error: str, correlation_id: str):
    """
    Publishes failed records to DLQ for later retry or manual investigation.
    """
    if not DISCORD_NOTIFIER_DLQ_URL:
        logger.warning("DISCORD_NOTIFIER_DLQ_URL not configured, cannot send to DLQ")
        return
    
    try:
        sqs.send_message(
            QueueUrl=DISCORD_NOTIFIER_DLQ_URL,
            MessageBody=json.dumps({
                "original_record": record,
                "error": error,
                "correlation_id": correlation_id,
                "timestamp": int(time.time()),
            }),
        )
        logger.info(
            json.dumps({
                "message": "Failed record sent to DLQ",
                "correlation_id": correlation_id,
                "queue_url": DISCORD_NOTIFIER_DLQ_URL,
            })
        )
    except Exception as e:
        logger.error(
            json.dumps({
                "message": "Failed to send record to DLQ",
                "error": str(e),
                "correlation_id": correlation_id,
            })
        )
    """
    Processes a single S3 ObjectCreated record. Returns True if successful.
    """
    bucket_name = record["s3"]["bucket"]["name"]
    object_key = record["s3"]["object"]["key"]

    discord_token = get_discord_token_from_metadata(bucket_name, object_key)
    if not discord_token:
        logger.warning(
            "No discord_token in S3 metadata, skipping",
            extra={"object_key": object_key},
        )
        return False

    application_id = secrets.get("AppId", "")

    if not application_id:
        logger.error("AppId missing from DiscordSecrets")
        raise ValueError("AppId required in DiscordSecrets")

    image_url = s3.generate_presigned_url(
        ClientMethod='get_object',
        Params={
            'Bucket': bucket_name,
            'Key': object_key
        },
        ExpiresIn=EXPIRATION_TIME
    )

    content = f"Here is the current canvas snapshot! {image_url}"

    patch_deferred_message(
        application_id=application_id,
        interaction_token=discord_token,
        content=content
    )

    logger.info("Successfully notified Discord", extra={"object_key": object_key})
    return True


# --- Main Handler ---

@tracer.capture_lambda_handler
@logger.inject_lambda_context(clear_state=True)
def lambda_handler(event: dict, context: LambdaContext) -> dict:
    """Notifies Discord after a snapshot is uploaded to S3."""
    correlation_id = context.aws_request_id
    logger.append_keys(correlation_id=correlation_id, function="discord_notifier")

    records = event.get("Records", [])
    if not records:
        logger.info("No S3 records to process")
        return {"statusCode": 200, "body": "No records to process"}

    secrets = get_discord_secrets()
    processed_count = 0

    for record in records:
        object_key = record.get("s3", {}).get("object", {}).get("key", "unknown")
        try:
            if process_s3_record(record, secrets, correlation_id):
                processed_count += 1
        except requests.HTTPError as e:
            logger.error(
                json.dumps({
                    "message": "Discord API request failed permanently",
                    "object_key": object_key,
                    "status_code": e.response.status_code if e.response else None,
                    "correlation_id": correlation_id,
                })
            )
            # Send to DLQ for later retry
            send_to_dlq(record, f"HTTPError: {str(e)}", correlation_id)
        except (requests.Timeout, requests.ConnectionError) as e:
            logger.error(
                json.dumps({
                    "message": "Discord API connection failed after retries",
                    "object_key": object_key,
                    "error": str(e),
                    "correlation_id": correlation_id,
                })
            )
            # Send to DLQ for later retry
            send_to_dlq(record, f"Network Error: {str(e)}", correlation_id)
        except Exception as e:
            logger.exception(
                json.dumps({
                    "message": "Failed to process S3 record",
                    "object_key": object_key,
                    "error": str(e),
                    "correlation_id": correlation_id,
                })
            )
            # Send to DLQ for later investigation
            send_to_dlq(record, f"Exception: {str(e)}", correlation_id)

    return {
        "statusCode": 200,
        "body": json.dumps({"processed": processed_count}),
    }
