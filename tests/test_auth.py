import os
import json
import pytest
import responses
import jwt

# Set dummy environment variables BEFORE importing lambda
os.environ["DISCORD_CLIENT_ID"] = "test-client-id"
os.environ["DISCORD_CLIENT_SECRET"] = "test-client-secret"
os.environ["REDIRECT_URI"] = "https://example.com/callback"
os.environ["JWT_SECRET"] = "test-jwt-secret"
os.environ["FRONTEND_URL"] = "https://frontend.example.com"

from tests.conftest import MockLambdaContext
from serverless.auth.app import lambda_handler

@responses.activate
def test_auth_success_redirect():
    """Test that providing a valid OAuth code successfully queries Discord and returns a signed JWT."""
    
    # 1. Arrange Mocks: Mock the /token API response
    responses.add(
        responses.POST,
        "https://discord.com/api/oauth2/token",
        json={"access_token": "mock-discord-access-token"},
        status=200
    )
    
    # Mock the /@me API response
    responses.add(
        responses.GET,
        "https://discord.com/api/users/@me",
        json={"id": "999888777", "username": "TestUser"},
        status=200
    )
    
    event = {
        "queryStringParameters": {"code": "valid-oauth-code"}
    }
    
    # 2. Act
    response = lambda_handler(event, MockLambdaContext())
    
    # 3. Assert
    assert response["statusCode"] == 302
    
    # Ensure it's redirecting back to our frontend
    location = response["headers"]["Location"]
    assert location.startswith("https://frontend.example.com#token=")
    
    # Extract the generated JWT and verify its contents
    token = location.split("#token=")[1]
    from serverless.auth.app import JWT_SECRET as APP_JWT_SECRET
    decoded = jwt.decode(token, APP_JWT_SECRET, algorithms=["HS256"])
    
    assert decoded["sub"] == "999888777"
    assert decoded["username"] == "TestUser"

@responses.activate
def test_auth_discord_api_failure():
    """Test that if Discord's API fails (e.g., bad code), the user is redirected gracefully."""
    
    responses.add(
        responses.POST,
        "https://discord.com/api/oauth2/token",
        json={"error": "invalid_grant"},
        status=400 # Discord returns 400 for bad codes
    )
    
    event = {
        "queryStringParameters": {"code": "bad-oauth-code"}
    }
    
    response = lambda_handler(event, MockLambdaContext())
    
    assert response["statusCode"] == 302
    assert response["headers"]["Location"] == "https://frontend.example.com#error=discord_api_failure"

def test_auth_missing_code():
    """Test that hitting the endpoint without a code redirects away."""
    event = {"queryStringParameters": {}}
    
    response = lambda_handler(event, MockLambdaContext())
    
    assert response["statusCode"] == 302
    assert "error=missing_code" in response["headers"]["Location"]
