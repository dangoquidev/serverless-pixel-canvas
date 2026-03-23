import os
import json
import boto3
import re
from enum import IntEnum
from nacl.signing import VerifyKey
from nacl.exceptions import BadSignatureError
from aws_lambda_powertools import Logger, Tracer
from aws_lambda_powertools.utilities import parameters
from aws_lambda_powertools.utilities.typing import LambdaContext

logger = Logger()
tracer = Tracer()

sns_client = boto3.client("sns")
SNS_TOPIC_ARN = os.environ.get("SNS_TOPIC_ARN")
APP_SECRET_NAME = os.environ.get("APP_SECRET_NAME", "AppSecrets")

# --- Constants & Enums (No more magic numbers!) ---

class InteractionType(IntEnum):
    PING = 1
    APPLICATION_COMMAND = 2
    MESSAGE_COMPONENT = 3

class ResponseType(IntEnum):
    PONG = 1
    CHANNEL_MESSAGE_WITH_SOURCE = 4
    DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE = 5


CANVAS_SIZE = 1000
HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


# --- Authentication & Signatures ---

def get_verify_key() -> VerifyKey | None:
    """Fetches Discord PublicKey and builds VerifyKey (cached 5 min by Powertools)."""
    try:
        discord_secrets = parameters.get_secret(
            os.environ["DISCORD_SECRET_NAME"], transform="json"
        )
        public_key_hex = discord_secrets.get("PublicKey", "")
        return VerifyKey(bytes.fromhex(public_key_hex)) if public_key_hex else None
    except Exception:
        logger.exception("Failed to load or parse DISCORD PublicKey")
        return None


def get_admin_discord_ids() -> set[str]:
    """Fetches Discord admin IDs from AppSecrets.DiscordAdminIds."""
    try:
        app_secrets = parameters.get_secret(APP_SECRET_NAME, transform="json")
        raw_ids = app_secrets.get("DiscordAdminIds", [])

        if isinstance(raw_ids, str):
            return {admin_id.strip() for admin_id in raw_ids.split(",") if admin_id.strip()}

        if isinstance(raw_ids, list):
            return {str(admin_id).strip() for admin_id in raw_ids if str(admin_id).strip()}

        return set()
    except Exception:
        logger.exception("Failed to load DiscordAdminIds from AppSecrets")
        return set()

def verify_signature(event: dict, verify_key: VerifyKey | None) -> bool:
    """Verifies the request signature from Discord using ED25519."""
    if not verify_key:
        return False

    headers = event.get("headers", {})
    # API Gateway sometimes alters header casing
    signature = headers.get("x-signature-ed25519") or headers.get("X-Signature-Ed25519")
    timestamp = headers.get("x-signature-timestamp") or headers.get("X-Signature-Timestamp")
    body = event.get("body", "")

    if not signature or not timestamp:
        return False

    try:
        verify_key.verify(f"{timestamp}{body}".encode("utf-8"), bytes.fromhex(signature))
        return True
    except BadSignatureError:
        return False


def get_discord_user_id(body: dict) -> str | None:
    member = body.get("member", {}) or {}
    member_user = member.get("user", {}) or {}
    user = body.get("user", {}) or {}
    user_id = member_user.get("id") or user.get("id")
    return str(user_id) if user_id else None


def extract_command_options(data: dict) -> dict:
    options = data.get("options", []) or []
    return {option.get("name"): option.get("value") for option in options if option.get("name")}


def publish_event(action: str, payload: dict) -> None:
    event_payload = {
        "source": "discord",
        "action": action,
        "payload": payload,
    }

    sns_client.publish(
        TopicArn=SNS_TOPIC_ARN,
        Message=json.dumps(event_payload),
        MessageAttributes={
            "action": {
                "DataType": "String",
                "StringValue": action,
            }
        },
    )


# --- Command Handlers (The "Future Proof" section) ---

def handle_async_command(command_name: str, body: dict, data: dict) -> dict:
    """Generic handler for commands that take a long time and need SNS Fan-Out."""
    event_payload = {
        "source": "discord",
        "action": command_name,
        "discord_token": body.get("token"),
        "payload": data,
    }

    sns_client.publish(
        TopicArn=SNS_TOPIC_ARN,
        Message=json.dumps(event_payload),
        MessageAttributes={
            "action": {
                "DataType": "String",
                "StringValue": command_name,
            }
        },
    )

    return {"type": ResponseType.DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE}


def handle_ping_command(command_name: str, body: dict, data: dict) -> dict:
    """Example of a future synchronous command that replies instantly."""
    return {
        "type": ResponseType.CHANNEL_MESSAGE_WITH_SOURCE,
        "data": {"content": "Pong! The canvas API is online."}
    }


def handle_draw_command(command_name: str, body: dict, data: dict) -> dict:
    """Allows drawing a single pixel from Discord with validated options."""
    user_id = get_discord_user_id(body)
    if not user_id:
        return {
            "type": ResponseType.CHANNEL_MESSAGE_WITH_SOURCE,
            "data": {"content": "Missing Discord user context.", "flags": 64},
        }

    options = extract_command_options(data)

    try:
        x = int(options.get("x"))
        y = int(options.get("y"))
    except (ValueError, TypeError):
        return {
            "type": ResponseType.CHANNEL_MESSAGE_WITH_SOURCE,
            "data": {"content": "x and y must be integers.", "flags": 64},
        }

    color = str(options.get("color", "")).strip()

    if not (0 <= x < CANVAS_SIZE and 0 <= y < CANVAS_SIZE):
        return {
            "type": ResponseType.CHANNEL_MESSAGE_WITH_SOURCE,
            "data": {"content": "Coordinates must be between 0 and 999.", "flags": 64},
        }

    if not HEX_COLOR_RE.match(color):
        return {
            "type": ResponseType.CHANNEL_MESSAGE_WITH_SOURCE,
            "data": {"content": "color must match #RRGGBB.", "flags": 64},
        }

    publish_event(
        action="draw_pixel",
        payload={
            "user_id": user_id,
            "x": x,
            "y": y,
            "color": color,
            "source": "discord",
        },
    )

    return {
        "type": ResponseType.CHANNEL_MESSAGE_WITH_SOURCE,
        "data": {"content": f"Pixel queued: ({x}, {y}) {color}", "flags": 64},
    }


def handle_clean_command(command_name: str, body: dict, data: dict) -> dict:
    """Queues a full-canvas clean operation, restricted to configured Discord admins."""
    user_id = get_discord_user_id(body)
    if not user_id:
        return {
            "type": ResponseType.CHANNEL_MESSAGE_WITH_SOURCE,
            "data": {"content": "Missing Discord user context.", "flags": 64},
        }

    admin_ids = get_admin_discord_ids()
    if user_id not in admin_ids:
        logger.warning("Unauthorized clean attempt", discord_user_id=user_id)
        return {
            "type": ResponseType.CHANNEL_MESSAGE_WITH_SOURCE,
            "data": {"content": "You are not allowed to use /clean.", "flags": 64},
        }

    publish_event(
        action="clean",
        payload={
            "requested_by": user_id,
            "source": "discord",
        },
    )

    return {
        "type": ResponseType.CHANNEL_MESSAGE_WITH_SOURCE,
        "data": {"content": "Canvas clean queued.", "flags": 64},
    }


# THE REGISTRY: Map command names to their handler functions
COMMAND_ROUTER = {
    "snapshot": handle_async_command,
    "ping": handle_ping_command,
    "draw": handle_draw_command,
    "clean": handle_clean_command,
}


# --- Main Handler ---

def create_response(status_code: int, body: dict | str) -> dict:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": body if isinstance(body, str) else json.dumps(body),
    }

@tracer.capture_lambda_handler
@logger.inject_lambda_context(clear_state=True)
def lambda_handler(event: dict, context: LambdaContext) -> dict:
    logger.append_keys(correlation_id=context.aws_request_id, function="discord_proxy")

    verify_key = get_verify_key()

    if not verify_signature(event, verify_key):
        logger.warning("Invalid request signature")
        return create_response(401, "Invalid request signature")

    try:
        body = json.loads(event.get("body", "{}"))
        interaction_type = body.get("type")

        # 1. Handle Ping
        if interaction_type == InteractionType.PING:
            logger.info("Received Ping interaction")
            return create_response(200, {"type": ResponseType.PONG})

        # 2. Handle Slash Commands
        if interaction_type == InteractionType.APPLICATION_COMMAND:
            data = body.get("data", {})
            command_name = data.get("name")

            logger.info("Received slash command", command=command_name)

            handler = COMMAND_ROUTER.get(command_name)

            if handler:
                response_payload = handler(command_name, body, data)
                return create_response(200, response_payload)
            else:
                logger.warning("Unknown command received", command=command_name)
                return create_response(400, "Unknown command")

        # 3. Handle Unknown Interactions
        logger.warning("Unsupported interaction type", interaction_type=interaction_type)
        return create_response(400, "Unsupported interaction type")

    except json.JSONDecodeError:
        logger.error("Failed to parse request body")
        return create_response(400, "Invalid JSON body")
    except BadSignatureError as e:
        logger.warning("Signature verification failed", extra={"error": str(e)})
        return create_response(401, "Invalid signature")
    except ValueError as e:
        logger.warning("Invalid request format", extra={"error": str(e)})
        return create_response(400, "Invalid request format")
    except Exception as e:
        logger.exception("Unexpected server error", extra={"error": str(e)})
        return create_response(500, "Internal server error")
