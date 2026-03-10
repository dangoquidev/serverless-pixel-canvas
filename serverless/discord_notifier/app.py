import json
import os
import urllib.request
import boto3
from aws_lambda_powertools import Logger, Tracer
from aws_lambda_powertools.utilities import parameters
from aws_lambda_powertools.utilities.typing import LambdaContext

logger = Logger()
tracer = Tracer()

s3 = boto3.client("s3")


# --- Helper Functions ---


def get_discord_token_from_metadata(bucket_name: str, object_key: str) -> str | None:
    """Fetches object metadata from S3 to retrieve the Discord interaction token."""
    response = s3.head_object(Bucket=bucket_name, Key=object_key)
    metadata = response.get("Metadata", {})
    return metadata.get("discord_token")


def notify_discord(
    discord_token: str, image_url: str, application_id: str
) -> None:
    """Updates the original Discord interaction message with the generated image URL."""
    discord_url = f"https://discord.com/api/v10/webhooks/{application_id}/{discord_token}/messages/@original"
    payload = {"content": f"Here is the current canvas snapshot! {image_url}"}

    req = urllib.request.Request(
        discord_url,
        data=json.dumps(payload).encode("utf-8"),
        method="PATCH",
        headers={"Content-Type": "application/json"},
    )
    urllib.request.urlopen(req, timeout=5)


# --- Main Handler ---


@tracer.capture_lambda_handler
@logger.inject_lambda_context
def lambda_handler(event: dict, context: LambdaContext):
    """Main orchestrator for notifying Discord after snapshot creation."""
    correlation_id = context.aws_request_id

    discord_secrets = parameters.get_secret(
        os.environ["DISCORD_SECRET_NAME"], transform="json"
    )
    application_id = discord_secrets.get("AppId", "")

    records = event.get("Records", [])
    if not records:
        return {"statusCode": 200, "body": "No records to process"}

    processed_count = 0

    for record in records:
        object_key = "unknown"
        try:
            bucket_name = record["s3"]["bucket"]["name"]
            object_key = record["s3"]["object"]["key"]

            # 1. Fetch metadata
            discord_token = get_discord_token_from_metadata(bucket_name, object_key)
            if not discord_token:
                logger.warning(
                    json.dumps(
                        {
                            "function": "discord_notifier",
                            "message": f"No discord_token found in metadata for {object_key}. Skipping.",
                            "correlation_id": correlation_id,
                            "object_key": object_key,
                        }
                    )
                )
                continue

            # 2. Construct S3 URL
            image_url = f"https://{bucket_name}.s3.amazonaws.com/{object_key}"

            # 3. Notify Discord
            notify_discord(discord_token, image_url, application_id)

            logger.info(
                json.dumps(
                    {
                        "function": "discord_notifier",
                        "message": "Successfully notified Discord",
                        "correlation_id": correlation_id,
                        "object_key": object_key,
                    }
                )
            )

            processed_count += 1

        except Exception as e:
            logger.error(
                json.dumps(
                    {
                        "function": "discord_notifier",
                        "message": f"Failed to process record for {object_key}",
                        "error": str(e),
                        "correlation_id": correlation_id,
                        "object_key": object_key,
                    }
                )
            )

    return {
        "statusCode": 200,
        "body": f"Notification sent for {processed_count} records",
    }
