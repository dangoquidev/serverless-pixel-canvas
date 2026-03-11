import os
import json
import uuid
import boto3
from aws_lambda_powertools import Logger, Tracer
from aws_lambda_powertools.utilities.typing import LambdaContext

from canvas_utils import CHUNK_SIZE, int_to_rgb

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


def generate_snapshot_image(
    pixels: list, file_path: str, canvas_width: int, canvas_height: int
) -> None:
    """Renders the minified pixel data into a PNG image. (Requires PIL)"""
    try:
        from PIL import Image
    except ImportError:
        raise RuntimeError("Pillow (PIL) is required to generate snapshots.")

    img = Image.new("RGB", (canvas_width, canvas_height), color="white")
    pixels_data = img.load()

    for pixel in pixels:
        try:
            # Reconstruct Chunk X and Y from "5#5"
            cx_str, cy_str = pixel["c"].split("#")
            cx, cy = int(cx_str), int(cy_str)

            # Reconstruct Local X and Y from 0-9999
            p = int(pixel["p"])
            local_x = p % CHUNK_SIZE
            local_y = p // CHUNK_SIZE

            # Calculate Global Canvas Coordinates
            global_x = (cx * CHUNK_SIZE) + local_x
            global_y = (cy * CHUNK_SIZE) + local_y

            if 0 <= global_x < canvas_width and 0 <= global_y < canvas_height:
                rgb = int_to_rgb(int(pixel["co"]))
                pixels_data[global_x, global_y] = rgb

        except Exception:
            continue

    img.save(file_path)


@tracer.capture_method
def fetch_all_pixels() -> list:
    """Scans the entire canvas table to retrieve only the required minified pixel data."""
    pixels = []

    scan_kwargs = {"ProjectionExpression": "c, p, co"}

    response = canvas_table.scan(**scan_kwargs)
    pixels.extend(response.get("Items", []))

    # Handle pagination in case the table is large
    while "LastEvaluatedKey" in response:
        scan_kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
        response = canvas_table.scan(**scan_kwargs)
        pixels.extend(response.get("Items", []))

    return pixels


@tracer.capture_method
def upload_snapshot_to_s3(file_path: str, request_id: str, discord_token: str) -> str:
    """Uploads the generated image to S3 with Discord interaction token in metadata."""
    object_key = f"snapshots/snapshot_{request_id}.png"

    extra_args = {"ContentType": "image/png"}
    if discord_token:
        extra_args["Metadata"] = {"discord_token": discord_token}

    s3.upload_file(file_path, SNAPSHOT_BUCKET, object_key, ExtraArgs=extra_args)
    return object_key


# --- Main Handler ---


@tracer.capture_lambda_handler
@logger.inject_lambda_context(clear_state=True)
def lambda_handler(event: dict, context: LambdaContext):
    """Main orchestrator for generating canvas snapshots."""
    correlation_id = context.aws_request_id
    logger.append_keys(correlation_id=correlation_id, function="snapshot_worker")

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

            logger.info("Starting snapshot generation")

            # 1. Read DB
            pixels = fetch_all_pixels()

            # 2. Compose Image using the Utility Layer
            file_path = f"/tmp/canvas_snapshot_{uuid.uuid4().hex[:8]}.png"
            generate_snapshot_image(pixels, file_path, CANVAS_WIDTH, CANVAS_HEIGHT)

            # 3. Upload to S3
            object_key = upload_snapshot_to_s3(file_path, correlation_id, discord_token)

            # Clean up local file
            if os.path.exists(file_path):
                os.remove(file_path)

            logger.info(
                "Snapshot generated and uploaded successfully",
                extra={"object_key": object_key, "pixels_count": len(pixels)},
            )

            processed_count += 1

        except Exception:
            # We use logger.exception to automatically print the full traceback
            logger.exception("Error generating snapshot")
            raise

    return {
        "statusCode": 200,
        "body": f"Successfully generated {processed_count} snapshots",
    }
