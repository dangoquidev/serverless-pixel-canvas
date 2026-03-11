import os
import json
import boto3
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

# --- Constants & Enums (No more magic numbers!) ---


class InteractionType(IntEnum):
    PING = 1
    APPLICATION_COMMAND = 2
    MESSAGE_COMPONENT = 3


class ResponseType(IntEnum):
    PONG = 1
    CHANNEL_MESSAGE_WITH_SOURCE = 4
    DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE = 5


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


def verify_signature(event: dict, verify_key: VerifyKey | None) -> bool:
    """Verifies the request signature from Discord using ED25519."""
    if not verify_key:
        return False

    headers = event.get("headers", {})
    # API Gateway sometimes alters header casing
    signature = headers.get("x-signature-ed25519") or headers.get("X-Signature-Ed25519")
    timestamp = headers.get("x-signature-timestamp") or headers.get(
        "X-Signature-Timestamp"
    )
    body = event.get("body", "")

    if not signature or not timestamp:
        return False

    try:
        verify_key.verify(
            f"{timestamp}{body}".encode("utf-8"), bytes.fromhex(signature)
        )
        return True
    except BadSignatureError:
        return False


# --- Command Handlers (The "Future Proof" section) ---


def handle_async_command(command_name: str, body: dict, data: dict) -> dict:
    """Generic handler for commands that take a long time and need SNS Fan-Out."""
    event_payload = {
        "source": "discord",
        "action": command_name,
        "discord_token": body.get("token"),
        "payload": data,
    }

    sns_client.publish(TopicArn=SNS_TOPIC_ARN, Message=json.dumps(event_payload), MessageAttributes={
            "action": {"DataType": "String", "StringValue": command_name}
        })

    return {"type": ResponseType.DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE}


def handle_ping_command(command_name: str, body: dict, data: dict) -> dict:
    """Example of a future synchronous command that replies instantly."""
    return {
        "type": ResponseType.CHANNEL_MESSAGE_WITH_SOURCE,
        "data": {"content": "Pong! The canvas API is online."},
    }


# THE REGISTRY: Map command names to their handler functions
COMMAND_ROUTER = {
    "snapshot": handle_async_command,
    "ping": handle_ping_command,
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
def lambda_handler(event: dict, context: LambdaContext):
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
        logger.warning(
            "Unsupported interaction type", interaction_type=interaction_type
        )
        return create_response(400, "Unsupported interaction type")

    except json.JSONDecodeError:
        logger.error("Failed to parse request body")
        return create_response(400, "Invalid JSON body")
    except Exception as e:
        logger.exception("Internal server error")
        return create_response(500, "Internal server error")
