import os
import jwt
from datetime import datetime, timedelta, timezone

# Set dummy secret before importing lambda
os.environ["JWT_SECRET"] = "super-secret-test-key"

from tests.conftest import MockLambdaContext
from serverless.authorizer.app import lambda_handler

def test_authorizer_valid_token():
    """Test that a valid JWT token returns an Allow IAM policy."""
    # 1. Arrange
    valid_payload = {
        "sub": "user_123",
        "username": "testuser",
        "exp": datetime.now(timezone.utc) + timedelta(hours=1)
    }
    token = jwt.encode(valid_payload, os.environ["JWT_SECRET"], algorithm="HS256")
    
    event = {
        "authorizationToken": f"Bearer {token}",
        "methodArn": "arn:aws:execute-api:us-east-1:123456789012:api-id/prod/GET/canvas"
    }

    # 2. Act
    response = lambda_handler(event, MockLambdaContext())

    # 3. Assert
    assert response["principalId"] == "user_123"
    assert response["policyDocument"]["Statement"][0]["Effect"] == "Allow"
    assert response["policyDocument"]["Statement"][0]["Resource"] == event["methodArn"]

def test_authorizer_missing_token():
    """Test that missing token returns a Deny policy."""
    event = {
        "authorizationToken": "",
        "methodArn": "arn:aws:execute-api:us-east-1:123:api/dev/GET/x"
    }
    response = lambda_handler(event, MockLambdaContext())
    assert response["principalId"] == "unauthorized"
    assert response["policyDocument"]["Statement"][0]["Effect"] == "Deny"

def test_authorizer_expired_token():
    """Test that an expired token is explicitly rejected with Deny."""
    expired_payload = {
        "sub": "user_123",
        "exp": datetime.now(timezone.utc) - timedelta(hours=1) # Already expired
    }
    token = jwt.encode(expired_payload, os.environ["JWT_SECRET"], algorithm="HS256")
    
    event = {
        "authorizationToken": str(token),
        "methodArn": "arn:aws:execute-api"
    }
    
    response = lambda_handler(event, MockLambdaContext())
    assert response["principalId"] == "unauthorized"
    assert response["policyDocument"]["Statement"][0]["Effect"] == "Deny"

def test_authorizer_invalid_signature():
    """Test that a token signed with the wrong secret is denied."""
    payload = {"sub": "hacker"}
    bad_token = jwt.encode(payload, "wrong-secret", algorithm="HS256")
    
    event = {"authorizationToken": str(bad_token), "methodArn": "test"}
    response = lambda_handler(event, MockLambdaContext())
    assert response["policyDocument"]["Statement"][0]["Effect"] == "Deny"
