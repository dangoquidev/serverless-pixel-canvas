import os
import requests
import jwt
from datetime import datetime, timedelta, timezone
from aws_lambda_powertools import Logger, Tracer
from aws_lambda_powertools.utilities import parameters
from aws_lambda_powertools.utilities.typing import LambdaContext

logger = Logger()
tracer = Tracer()

FRONTEND_URL = os.environ.get("FRONTEND_URL")


def get_discord_secrets() -> dict:
    """Fetches Discord secrets from Secrets Manager (cached 5 min by Powertools)."""
    return parameters.get_secret(os.environ["DISCORD_SECRET_NAME"], transform="json")


def get_jwt_secret() -> str:
    """Fetches JWT secret from Secrets Manager (cached 5 min by Powertools)."""
    app_secrets = parameters.get_secret(os.environ["APP_SECRET_NAME"], transform="json")
    return app_secrets.get("JwtSecret", "")


# --- Helper Functions ---


def get_callback_redirect_uri(event: dict) -> str:
    """Builds the redirect_uri for Discord OAuth (must match in both auth and token exchange)."""
    rc = event.get("requestContext", {})
    domain = rc.get("domainName")
    stage = rc.get("stage")
    if not domain or not stage:
        raise ValueError("Missing requestContext for redirect_uri")
    return f"https://{domain}/{stage}/auth/callback"


def exchange_code_for_token(
    code: str, redirect_uri: str, client_id: str, client_secret: str
) -> str:
    """Exchanges the OAuth2 authorization code for a Discord access token."""
    token_url = "https://discord.com/api/oauth2/token"
    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    response = requests.post(token_url, data=data, headers=headers, timeout=5)
    response.raise_for_status()

    return response.json().get("access_token")


def fetch_discord_profile(access_token: str) -> dict:
    """Fetches the user's basic profile from Discord."""
    user_url = "https://discord.com/api/users/@me"
    headers = {"Authorization": f"Bearer {access_token}"}

    response = requests.get(user_url, headers=headers, timeout=5)
    response.raise_for_status()

    return response.json()


def generate_app_jwt(discord_user: dict, jwt_secret: str) -> str:
    """Generates a secure JWT for the web application."""
    jwt_payload = {
        "sub": discord_user.get("id"),
        "username": discord_user.get("username"),
        "exp": datetime.now(timezone.utc) + timedelta(hours=24),
    }
    return jwt.encode(jwt_payload, jwt_secret, algorithm="HS256")


def build_redirect_response(url_hash: str) -> dict:
    """Builds a 302 Redirect response (full-page nav; CORS not needed)."""
    return {
        "statusCode": 302,
        "headers": {"Location": f"{FRONTEND_URL}#{url_hash}"},
    }


def build_discord_redirect_response(event: dict, client_id: str) -> dict:
    """Redirects user to Discord OAuth (full-page nav; use location.href, not fetch)."""
    redirect_uri = get_callback_redirect_uri(event)
    scope = "identify"
    discord_auth_url = (
        f"https://discord.com/api/oauth2/authorize"
        f"?client_id={client_id}"
        f"&redirect_uri={redirect_uri}"
        f"&response_type=code"
        f"&scope={scope}"
    )
    return {
        "statusCode": 302,
        "headers": {"Location": discord_auth_url},
    }


# --- Main Handler ---


@tracer.capture_lambda_handler
@logger.inject_lambda_context
def lambda_handler(event: dict, context: LambdaContext):
    query_params = event.get("queryStringParameters") or {}
    code = query_params.get("code")

    discord_secrets = get_discord_secrets()
    jwt_secret = get_jwt_secret()
    client_id = discord_secrets.get("ClientId", "")
    client_secret = discord_secrets.get("ClientSecret", "")

    if not code:
        logger.info("Login initiation — redirecting to Discord OAuth")
        return build_discord_redirect_response(event, client_id)

    try:
        # 1. Use same redirect_uri as Discord auth (must match exactly)
        redirect_uri = get_callback_redirect_uri(event)

        # 2. Complete the OAuth2 handshake
        access_token = exchange_code_for_token(
            code, redirect_uri, client_id, client_secret
        )

        # 3. Retrieve user identity
        user_data = fetch_discord_profile(access_token)

        # 4. Issue application credentials
        app_token = generate_app_jwt(user_data, jwt_secret)

        logger.info("Authentication successful", extra={"user_id": user_data.get("id")})
        return build_redirect_response(f"token={app_token}")

    except requests.exceptions.RequestException as e:
        logger.error("Discord API communication failure", extra={"error": str(e)})
        return build_redirect_response("error=discord_api_failure")
    except ValueError:
        return build_redirect_response("error=internal_configuration_error")
    except Exception:
        logger.exception("Uncaught authentication error")
        return build_redirect_response("error=internal_error")
