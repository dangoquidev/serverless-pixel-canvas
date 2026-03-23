import os
import json
import uuid
import boto3
from aws_lambda_powertools import Logger, Tracer
from aws_lambda_powertools.utilities.typing import LambdaContext

# Import the centralized decoder
from canvas_utils import decode_db_item

logger = Logger()
tracer = Tracer()

dynamodb = boto3.resource("dynamodb")
s3 = boto3.client("s3")

CANVAS_TABLE_NAME = os.environ.get("CANVAS_TABLE_NAME")
SNAPSHOT_BUCKET = os.environ.get("SNAPSHOT_BUCKET")
canvas_table = dynamodb.Table(CANVAS_TABLE_NAME)

CANVAS_WIDTH = 1000
CANVAS_HEIGHT = 1000


def generate_snapshot_image(
    pixels: list, file_path: str, canvas_width: int, canvas_height: int
) -> None:
    try:
        from PIL import Image
    except ImportError:
        raise RuntimeError("Pillow (PIL) is required to generate snapshots.")

    img = Image.new("RGB", (canvas_width, canvas_height), color="white")
    pixels_data = img.load()

    for pixel in pixels:
        try:
            # Clean and centralized logic!
            global_x, global_y, _, _, _, _, r, g, b = decode_db_item(pixel)

            if 0 <= global_x < canvas_width and 0 <= global_y < canvas_height:
                pixels_data[global_x, global_y] = (r, g, b)

        except Exception as e:
            logger.warning(f"Skipped invalid pixel during snapshot: {e}")
            continue

    img.save(file_path)


@tracer.capture_method
def fetch_all_pixels() -> list:
    pixels = []
    scan_kwargs = {"ProjectionExpression": "c, p, co"}

    response = canvas_table.scan(**scan_kwargs)
    pixels.extend(response.get("Items", []))

    while "LastEvaluatedKey" in response:
        scan_kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
        response = canvas_table.scan(**scan_kwargs)
        pixels.extend(response.get("Items", []))

    return pixels


@tracer.capture_method
def upload_snapshot_to_s3(file_path: str, request_id: str, discord_token: str) -> str:
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

            pixels = fetch_all_pixels()
            file_path = f"/tmp/canvas_snapshot_{uuid.uuid4().hex[:8]}.png"
            generate_snapshot_image(pixels, file_path, CANVAS_WIDTH, CANVAS_HEIGHT)

            object_key = upload_snapshot_to_s3(file_path, correlation_id, discord_token)

            if os.path.exists(file_path):
                os.remove(file_path)

            logger.info(
                "Snapshot generated",
                extra={"object_key": object_key, "pixels_count": len(pixels)},
            )
            processed_count += 1

        except Exception:
            logger.exception("Error generating snapshot")
            raise

    return {
        "statusCode": 200,
        "body": f"Successfully generated {processed_count} snapshots",
    }
