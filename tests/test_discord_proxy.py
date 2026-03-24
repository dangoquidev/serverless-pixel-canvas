import json

from tests.conftest import MockLambdaContext
from serverless.discord_proxy import app as discord_proxy_app


def _event(body: dict) -> dict:
    return {
        "headers": {
            "x-signature-ed25519": "mock",
            "x-signature-timestamp": "1234567890",
        },
        "body": json.dumps(body),
    }


def test_discord_proxy_valid_ping(monkeypatch):
    monkeypatch.setattr(discord_proxy_app, "get_verify_key", lambda: object())
    monkeypatch.setattr(discord_proxy_app, "verify_signature", lambda event, verify_key: True)

    response = discord_proxy_app.lambda_handler(_event({"type": 1}), MockLambdaContext())

    assert response["statusCode"] == 200
    assert json.loads(response["body"])["type"] == 1


def test_discord_proxy_invalid_signature(monkeypatch):
    monkeypatch.setattr(discord_proxy_app, "get_verify_key", lambda: object())
    monkeypatch.setattr(discord_proxy_app, "verify_signature", lambda event, verify_key: False)

    response = discord_proxy_app.lambda_handler(_event({"type": 1}), MockLambdaContext())

    assert response["statusCode"] == 401


def test_discord_proxy_draw_command_publishes(monkeypatch):
    monkeypatch.setattr(discord_proxy_app, "get_verify_key", lambda: object())
    monkeypatch.setattr(discord_proxy_app, "verify_signature", lambda event, verify_key: True)

    calls = []

    def _publish(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(discord_proxy_app.sns_client, "publish", _publish)

    body = {
        "type": 2,
        "member": {"user": {"id": "1234"}},
        "data": {
            "name": "draw",
            "options": [
                {"name": "x", "value": 12},
                {"name": "y", "value": 34},
                {"name": "color", "value": "#00FF00"},
            ],
        },
    }

    response = discord_proxy_app.lambda_handler(_event(body), MockLambdaContext())

    assert response["statusCode"] == 200
    assert len(calls) == 1
    assert calls[0]["MessageAttributes"]["action"]["StringValue"] == "draw_pixel"


def test_discord_proxy_snapshot_keeps_legacy_payload_shape(monkeypatch):
    monkeypatch.setattr(discord_proxy_app, "get_verify_key", lambda: object())
    monkeypatch.setattr(discord_proxy_app, "verify_signature", lambda event, verify_key: True)

    calls = []

    def _publish(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(discord_proxy_app.sns_client, "publish", _publish)

    body = {
        "type": 2,
        "token": "discord_interaction_token",
        "data": {"name": "snapshot"},
    }

    response = discord_proxy_app.lambda_handler(_event(body), MockLambdaContext())

    assert response["statusCode"] == 200
    assert len(calls) == 1

    message = json.loads(calls[0]["Message"])
    assert message["action"] == "snapshot"
    assert message["discord_token"] == "discord_interaction_token"


def test_discord_proxy_clean_requires_admin(monkeypatch):
    monkeypatch.setattr(discord_proxy_app, "get_verify_key", lambda: object())
    monkeypatch.setattr(discord_proxy_app, "verify_signature", lambda event, verify_key: True)
    monkeypatch.setattr(discord_proxy_app, "get_admin_discord_ids", lambda: {"9999"})

    calls = []

    def _publish(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(discord_proxy_app.sns_client, "publish", _publish)

    body = {
        "type": 2,
        "member": {"user": {"id": "1234"}},
        "data": {"name": "clean"},
    }

    response = discord_proxy_app.lambda_handler(_event(body), MockLambdaContext())

    assert response["statusCode"] == 200
    assert len(calls) == 0


def test_discord_proxy_clean_admin_publishes(monkeypatch):
    monkeypatch.setattr(discord_proxy_app, "get_verify_key", lambda: object())
    monkeypatch.setattr(discord_proxy_app, "verify_signature", lambda event, verify_key: True)
    monkeypatch.setattr(discord_proxy_app, "get_admin_discord_ids", lambda: {"1234"})

    calls = []

    def _publish(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(discord_proxy_app.sns_client, "publish", _publish)

    body = {
        "type": 2,
        "member": {"user": {"id": "1234"}},
        "data": {"name": "clean"},
    }

    response = discord_proxy_app.lambda_handler(_event(body), MockLambdaContext())

    assert response["statusCode"] == 200
    assert len(calls) == 1
    assert calls[0]["MessageAttributes"]["action"]["StringValue"] == "clean"


def test_discord_proxy_missing_headers(monkeypatch):
    monkeypatch.setattr(discord_proxy_app, "get_verify_key", lambda: object())
    monkeypatch.setattr(discord_proxy_app, "verify_signature", lambda event, verify_key: False)

    event = {
        "headers": {},
        "body": '{"type": 1}'
    }

    response = discord_proxy_app.lambda_handler(event, MockLambdaContext())
    assert response["statusCode"] == 401
