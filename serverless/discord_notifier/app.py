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

DISCORD_SECRET_NAME = os.environ.get("DISCORD_SECRET_NAME", "DiscordSecrets")
DISCORD_API_BASE = "https://discord.com/api/v10"
EXPIRATION_TIME = 1 * 24 * 60 * 60 # 1 days


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
    """
    url = f"{DISCORD_API_BASE}/webhooks/{application_id}/{interaction_token}/messages/@original"
    payload = {"content": content}
    headers = {"Content-Type": "application/json"}

    response = requests.patch(url, json=payload, headers=headers, timeout=10)

    if response.status_code >= 400:
        logger.error(f"Discord API Error: {response.status_code} - {response.text}")

    response.raise_for_status()


def process_s3_record(record: dict, secrets: dict, correlation_id: str) -> bool:
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
                "Discord API request failed",
                extra={
                    "object_key": object_key,
                    "status_code": e.response.status_code if e.response else None,
                },
            )
            raise
        except Exception as e:
            logger.exception("Failed to process S3 record", extra={"object_key": object_key})
            raise

    return {
        "statusCode": 200,
        "body": json.dumps({"processed": processed_count}),
    }