import os
import json
import boto3
from nacl.signing import VerifyKey
from nacl.exceptions import BadSignatureError
from aws_lambda_powertools import Logger, Tracer
from aws_lambda_powertools.utilities import parameters
from aws_lambda_powertools.utilities.typing import LambdaContext

logger = Logger()
tracer = Tracer()

sns_client = boto3.client("sns")
SNS_TOPIC_ARN = os.environ.get("SNS_TOPIC_ARN")


def get_verify_key():
    """Fetches Discord PublicKey and builds VerifyKey (cached 5 min by Powertools)."""
    discord_secrets = parameters.get_secret(
        os.environ["DISCORD_SECRET_NAME"], transform="json"
    )
    public_key_hex = discord_secrets.get("PublicKey", "")
    if not public_key_hex:
        return None
    try:
        return VerifyKey(bytes.fromhex(public_key_hex))
    except (ValueError, TypeError):
        logger.warning("DISCORD PublicKey is invalid")
        return None


# --- Helper Functions ---


def create_response(status_code: int, body: dict | str) -> dict:
    """Helper to format API Gateway HTTP responses."""
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": body if isinstance(body, str) else json.dumps(body),
    }


def verify_signature(event: dict, verify_key) -> bool:
    """Verifies the request signature from Discord using ED25519."""
    if not verify_key:
        return False

    headers = event.get("headers", {})
    # API Gateway might lower-case headers
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
    except Exception as e:
        logger.error(f"Signature verification error: {str(e)}")
        return False


# --- Main Handler ---


@tracer.capture_lambda_handler
@logger.inject_lambda_context
def lambda_handler(event: dict, context: LambdaContext):
    """Main orchestrator for the Discord interaction proxy."""
    correlation_id = context.aws_request_id

    verify_key = get_verify_key()

    if not verify_signature(event, verify_key):
        logger.warning(
            json.dumps(
                {
                    "function": "discord_proxy",
                    "message": "Invalid request signature",
                    "correlation_id": correlation_id,
                }
            )
        )
        return create_response(401, "Invalid request signature")

    try:
        body = json.loads(event.get("body", "{}"))
        interaction_type = body.get("type")

        # 2. Handle Ping (Type 1)
        if interaction_type == 1:
            logger.info(
                json.dumps(
                    {
                        "function": "discord_proxy",
                        "message": "Received Ping interaction",
                        "correlation_id": correlation_id,
                    }
                )
            )
            return create_response(200, {"type": 1})

        # 3. Handle Slash Commands (Type 2)
        if interaction_type == 2:
            data = body.get("data", {})
            command_name = data.get("name")

            logger.info(
                json.dumps(
                    {
                        "function": "discord_proxy",
                        "message": f"Received slash command: {command_name}",
                        "command": command_name,
                        "correlation_id": correlation_id,
                    }
                )
            )

            # Construct SNS payload
            event_payload = {
                "source": "discord",
                "action": command_name,
                "discord_token": body.get("token"),
                "payload": data,
            }

            # Publish to SNS Fan-Out Topic
            sns_client.publish(
                TopicArn=SNS_TOPIC_ARN, Message=json.dumps(event_payload)
            )

            # 4. Asynchronous Acknowledge (Deferred)
            return create_response(200, {"type": 5})

        # Unsupported interaction type
        logger.warning(
            json.dumps(
                {
                    "function": "discord_proxy",
                    "message": f"Unsupported interaction type: {interaction_type}",
                    "correlation_id": correlation_id,
                }
            )
        )
        return create_response(400, "Unsupported interaction type")

    except json.JSONDecodeError:
        logger.error(
            json.dumps(
                {
                    "function": "discord_proxy",
                    "message": "Failed to parse request body",
                    "correlation_id": correlation_id,
                }
            )
        )
        return create_response(400, "Invalid JSON body")
    except Exception as e:
        logger.error(
            json.dumps(
                {
                    "function": "discord_proxy",
                    "message": "Internal server error",
                    "error": str(e),
                    "correlation_id": correlation_id,
                }
            )
        )
        return create_response(500, "Internal server error")
