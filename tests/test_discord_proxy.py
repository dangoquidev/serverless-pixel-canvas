import os
import json
import pytest
from nacl.signing import SigningKey

# 1. Generate a real Ed25519 keypair for the test
private_key = SigningKey.generate()
public_key = private_key.verify_key
public_key_hex = public_key.encode().hex()

# 2. Set environment variables BEFORE importing the lambda
os.environ["DISCORD_PUBLIC_KEY"] = public_key_hex
os.environ["SNS_TOPIC_ARN"] = "arn:aws:sns:us-east-1:123456789012:test-topic"

from tests.conftest import MockLambdaContext
from serverless.discord_proxy.app import lambda_handler

def sign_request(body_str: str) -> tuple[str, str]:
    """Helper to generate a valid Discord ED25519 signature."""
    timestamp = "1234567890"  # mock timestamp
    
    # Discord signs the timestamp + body
    message = f"{timestamp}{body_str}".encode("utf-8")
    signed = private_key.sign(message)
    signature_hex = signed.signature.hex()
    
    return signature_hex, timestamp

def test_discord_proxy_valid_ping():
    """Test that validating a correct signature on a Ping (type 1) works."""
    body = {"type": 1}
    body_str = json.dumps(body)
    
    sig, ts = sign_request(body_str)
    
    event = {
        "headers": {
            "x-signature-ed25519": sig,
            "x-signature-timestamp": ts
        },
        "body": body_str
    }
    
    response = lambda_handler(event, MockLambdaContext())
    
    assert response["statusCode"] == 200
    assert json.loads(response["body"])["type"] == 1

def test_discord_proxy_invalid_signature():
    """Test that a bad signature is rejected with 401."""
    body_str = json.dumps({"type": 1})
    
    # We use a valid timestamp, but explicitly theWRONG signature
    event = {
        "headers": {
            "x-signature-ed25519": "00" * 64, # 64 bytes of zeros (invalid)
            "x-signature-timestamp": "1234567890"
        },
        "body": body_str
    }
    
    response = lambda_handler(event, MockLambdaContext())
    assert response["statusCode"] == 401

def test_discord_proxy_missing_headers():
    """Test that missing security headers causes rejection."""
    event = {
        "headers": {}, # Missing signature headers completely
        "body": '{"type": 1}'
    }
    
    response = lambda_handler(event, MockLambdaContext())
    assert response["statusCode"] == 401
