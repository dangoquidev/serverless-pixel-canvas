import os
import json
import uuid
import boto3
from PIL import Image
from aws_lambda_powertools import Logger, Tracer
from aws_lambda_powertools.utilities.typing import LambdaContext

logger = Logger()
tracer = Tracer()

# 2. Initialization (Cold Start Optimization)
dynamodb = boto3.resource("dynamodb")
s3 = boto3.client("s3")

CANVAS_TABLE_NAME = os.environ.get("CANVAS_TABLE_NAME")
SNAPSHOT_BUCKET = os.environ.get("SNAPSHOT_BUCKET")
canvas_table = dynamodb.Table(CANVAS_TABLE_NAME)

CANVAS_WIDTH = 1000
CANVAS_HEIGHT = 1000

# --- Helper Functions ---


def hex_to_rgb(hex_color: str) -> tuple:
    """Converts a hex color string to an RGB tuple."""
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))


def fetch_all_pixels() -> list:
    """Scans the entire canvas table to retrieve all pixels."""
    pixels = []
    response = canvas_table.scan()
    pixels.extend(response.get("Items", []))

    # Handle pagination in case the table is large
    while "LastEvaluatedKey" in response:
        response = canvas_table.scan(ExclusiveStartKey=response["LastEvaluatedKey"])
        pixels.extend(response.get("Items", []))

    return pixels


def generate_image(pixels: list, file_path: str) -> None:
    """Renders the pixel data into a PNG image and saves it to the local filesystem."""
    img = Image.new("RGB", (CANVAS_WIDTH, CANVAS_HEIGHT), color="white")
    pixels_data = img.load()

    for pixel in pixels:
        try:
            _, x_str, y_str = pixel["PixelId"].split("#")
            x, y = int(x_str), int(y_str)

            if 0 <= x < CANVAS_WIDTH and 0 <= y < CANVAS_HEIGHT:
                color = pixel.get("color", "#000000")
                pixels_data[x, y] = hex_to_rgb(color)
        except Exception as e:
            logger.warning(f"Failed to process pixel {pixel.get('PixelId')}: {str(e)}")
            continue

    img.save(file_path)


def upload_snapshot_to_s3(file_path: str, request_id: str, discord_token: str) -> str:
    """Uploads the generated image to S3 with Discord interaction token in metadata."""
    object_key = f"snapshots/snapshot_{request_id}.png"

    extra_args = {"ContentType": "image/png"}
    if discord_token:
        # discord_notifier needs this to patch the deferred Discord message
        extra_args["Metadata"] = {"discord_token": discord_token}

    s3.upload_file(
        file_path,
        SNAPSHOT_BUCKET,
        object_key,
        ExtraArgs=extra_args,
    )
    return object_key


# --- Main Handler ---


@tracer.capture_lambda_handler
@logger.inject_lambda_context
def lambda_handler(event: dict, context: LambdaContext):
    """Main orchestrator for generating canvas snapshots."""
    correlation_id = context.aws_request_id

    records = event.get("Records", [])
    if not records:
        return {"statusCode": 200, "body": "No records to process"}

    processed_count = 0

    for record in records:
        try:
            sqs_body = json.loads(record.get("body", "{}"))
            sns_message = json.loads(sqs_body.get("Message", "{}"))

            if sns_message.get("action") != "snapshot":
                continue

            discord_token = sns_message.get("discord_token")

            logger.info(
                json.dumps(
                    {
                        "function": "snapshot_worker",
                        "message": "Starting snapshot generation",
                        "correlation_id": correlation_id,
                    }
                )
            )

            # 1. Read DB
            pixels = fetch_all_pixels()

            # 2. Compose Image
            file_path = f"/tmp/canvas_snapshot_{uuid.uuid4().hex[:8]}.png"
            generate_image(pixels, file_path)

            # 3. Upload to S3
            object_key = upload_snapshot_to_s3(
                file_path, context.aws_request_id, discord_token
            )

            # Clean up local file
            if os.path.exists(file_path):
                os.remove(file_path)

            logger.info(
                json.dumps(
                    {
                        "function": "snapshot_worker",
                        "message": "Snapshot generated and uploaded successfully",
                        "object_key": object_key,
                        "pixels_count": len(pixels),
                        "correlation_id": correlation_id,
                    }
                )
            )

            processed_count += 1

        except Exception as e:
            logger.error(
                json.dumps(
                    {
                        "function": "snapshot_worker",
                        "message": "Error generating snapshot",
                        "error": str(e),
                        "correlation_id": correlation_id,
                    }
                )
            )
            raise e

    return {
        "statusCode": 200,
        "body": f"Successfully generated {processed_count} snapshots",
    }
