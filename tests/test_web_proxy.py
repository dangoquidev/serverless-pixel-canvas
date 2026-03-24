import os
import json
import pytest
from unittest.mock import patch
from moto import mock_aws
import boto3

# We need to set dummy environment and create the SNS topic before testing
os.environ["SNS_TOPIC_ARN"] = "arn:aws:sns:us-east-1:123456789012:test-pixel-events-topic"

from tests.conftest import MockLambdaContext
from serverless.web_proxy.app import lambda_handler

@mock_aws
def test_web_proxy_valid_payload():
    """Test that a valid REST payload successfully publishes to SNS."""
    
    # Arrange: We need to create the actual dummy SNS topic in moto
    sns = boto3.client("sns", region_name="us-east-1")
    sns.create_topic(Name="test-pixel-events-topic")
    
    # Subscribe an SQS queue so we can intercept and read the published message
    sqs = boto3.client("sqs", region_name="us-east-1")
    queue = sqs.create_queue(QueueName="test-queue")
    queue_url = queue["QueueUrl"]
    queue_arn = sqs.get_queue_attributes(QueueUrl=queue_url, AttributeNames=["QueueArn"])["Attributes"]["QueueArn"]
    sns.subscribe(TopicArn=os.environ["SNS_TOPIC_ARN"], Protocol="sqs", Endpoint=queue_arn)
    
    payload = {
        "x": 500,
        "y": 500,
        "color": "#000000"
    }
    
    event = {
        "body": json.dumps(payload),
        "requestContext": {
            "authorizer": {"userId": "user123", "username": "testuser"}
        }
    }
    
    # Act
    ctx = MockLambdaContext()
    response = lambda_handler(event, ctx)
    assert response["statusCode"] == 202
    
    # Assert
    # Read the message that was actually pushed by SNS into our mock SQS
    messages = sqs.receive_message(QueueUrl=queue_url, MaxNumberOfMessages=1)
    
    assert "Messages" in messages
    msg_body = json.loads(messages["Messages"][0]["Body"])
    published_event = json.loads(msg_body["Message"])
    
    assert published_event["action"] == "draw_pixel"
    assert published_event["payload"]["x"] == 500
    assert published_event["payload"]["user_id"] == "user123"
    # Correlation ID comes from Lambda context, not client
    assert published_event["correlation_id"] == ctx.aws_request_id


def test_web_proxy_missing_authorizer():
    """Test that missing user_id in authorizer context returns 401."""
    event = {
        "body": json.dumps({"x": 0, "y": 0, "color": "#000"}),
        "requestContext": {}
    }
    response = lambda_handler(event, MockLambdaContext())
    assert response["statusCode"] == 401
    body = json.loads(response["body"])
    assert "Unauthorized" in body["error"]


def test_web_proxy_missing_fields(caplog):
    """Test that missing required fields in the payload returns a 400 Bad Request."""
    payload = {
        "x": 500,
        # missing y, color
    }
    event = {
        "body": json.dumps(payload),
        "requestContext": {"authorizer": {"userId": "user123"}}
    }
    
    response = lambda_handler(event, MockLambdaContext())
    assert response["statusCode"] == 400
    body = json.loads(response["body"])
    assert "Missing" in body["error"]

def test_web_proxy_invalid_json():
    """Test that invalid JSON is caught."""
    event = {
        "body": "this is not json",
        "requestContext": {"authorizer": {"userId": "user123"}}
    }
    response = lambda_handler(event, MockLambdaContext())
    assert response["statusCode"] == 400


def test_web_proxy_out_of_bounds_coordinates():
    """Test that coordinates outside 0-999 range are rejected."""
    event = {
        "body": json.dumps({
            "x": 1500,  # Out of bounds
            "y": 250,
            "color": "#FF0000"
        }),
        "requestContext": {"authorizer": {"userId": "user123"}}
    }
    
    response = lambda_handler(event, MockLambdaContext())
    
    assert response["statusCode"] == 400
    body = json.loads(response["body"])
    assert "out of bounds" in body["error"].lower()


def test_web_proxy_invalid_coordinate_type():
    """Test that non-integer coordinates are rejected."""
    event = {
        "body": json.dumps({
            "x": "150",  # String instead of int
            "y": 250,
            "color": "#FF0000"
        }),
        "requestContext": {"authorizer": {"userId": "user123"}}
    }
    
    response = lambda_handler(event, MockLambdaContext())
    
    assert response["statusCode"] == 400
    body = json.loads(response["body"])
    assert "integer" in body["error"].lower()


@mock_aws
def test_web_proxy_sns_publish_failure():
    """Test that SNS publish failures result in 500 error."""
    # Create SNS topic but will mock the client to fail
    sns = boto3.client("sns", region_name="us-east-1")
    sns.create_topic(Name="test-pixel-events-topic")
    
    with patch("serverless.web_proxy.app.sns_client.publish") as mock_publish:
        mock_publish.side_effect = Exception("SNS service unavailable")
        
        event = {
            "body": json.dumps({
                "x": 100,
                "y": 100,
                "color": "#FF0000"
            }),
            "requestContext": {"authorizer": {"userId": "user123"}}
        }
        
        response = lambda_handler(event, MockLambdaContext())
        
        assert response["statusCode"] == 500
        body = json.loads(response["body"])
        assert "Internal server error" in body["error"]


def test_web_proxy_cors_headers_present():
    """Test that CORS headers are included in all responses."""
    event = {
        "body": json.dumps({
            "x": 100,
            "y": 100,
            "color": "#FF0000"
        }),
        "requestContext": {}  # Missing authorizer
    }
    
    response = lambda_handler(event, MockLambdaContext())
    
    # Check CORS headers on error response
    assert response["headers"]["Access-Control-Allow-Origin"] == "*"
    assert "Content-Type" in response["headers"]
    assert response["headers"]["Access-Control-Allow-Methods"] == "POST,OPTIONS"


def test_web_proxy_edge_boundary_coordinates():
    """Test that edge coordinates (0 and 999) are accepted."""
    with patch("serverless.web_proxy.app.sns_client.publish") as mock_publish:
        mock_publish.return_value = {"MessageId": "test-msg"}
        
        # Test 0,0 (bottom-left)
        event = {
            "body": json.dumps({
                "x": 0,
                "y": 0,
                "color": "#000000"
            }),
            "requestContext": {"authorizer": {"userId": "user123"}}
        }
        
        response = lambda_handler(event, MockLambdaContext())
        assert response["statusCode"] == 202
        
        # Test 999,999 (top-right)
        event["body"] = json.dumps({
            "x": 999,
            "y": 999,
            "color": "#FFFFFF"
        })
        
        response = lambda_handler(event, MockLambdaContext())
        assert response["statusCode"] == 202


def test_web_proxy_uses_authorizer_userid_not_client():
    """Test that user_id comes from authorizer context, not client payload."""
    with patch("serverless.web_proxy.app.sns_client.publish") as mock_publish:
        mock_publish.return_value = {"MessageId": "test-msg"}
        
        event = {
            "body": json.dumps({
                "x": 100,
                "y": 100,
                "color": "#FF0000",
                "user_id": "hacker-trying-to-spoof"  # Client tries to spoof user_id
            }),
            "requestContext": {"authorizer": {"userId": "legitimate-user123"}}
        }
        
        response = lambda_handler(event, MockLambdaContext())
        assert response["statusCode"] == 202
        
        # Verify the actual user_id used is from authorizer, not client
        call_kwargs = mock_publish.call_args[1]
        message = json.loads(call_kwargs["Message"])
        assert message["payload"]["user_id"] == "legitimate-user123"
        assert message["payload"]["user_id"] != "hacker-trying-to-spoof"


def test_web_proxy_invalid_color_format(caplog):
    """Test that invalid color hex format is rejected."""
    invalid_colors = [
        "#GG0000",  # Invalid hex char
        "#FFFF",    # Too short
        "FF0000",   # Missing #
        "#ff00",    # Too short with valid chars
        "#FF00000", # Too long
        "red",      # Color name instead of hex
    ]
    
    for invalid_color in invalid_colors:
        event = {
            "body": json.dumps({
                "x": 100,
                "y": 100,
                "color": invalid_color
            }),
            "requestContext": {"authorizer": {"userId": "user123"}}
        }
        
        response = lambda_handler(event, MockLambdaContext())
        assert response["statusCode"] == 400, f"Should reject color: {invalid_color}"
        body = json.loads(response["body"])
        assert "hex format" in body["error"].lower()


def test_web_proxy_valid_color_formats():
    """Test that valid color hex formats are accepted."""
    valid_colors = [
        "#000000",  # Black
        "#FFFFFF",  # White
        "#FF0000",  # Red
        "#00ff00",  # Green (lowercase)
        "#0000fF",  # Blue (mixed case)
    ]
    
    with patch("serverless.web_proxy.app.sns_client.publish") as mock_publish:
        mock_publish.return_value = {"MessageId": "test-msg"}
        
        for valid_color in valid_colors:
            event = {
                "body": json.dumps({
                    "x": 100,
                    "y": 100,
                    "color": valid_color
                }),
                "requestContext": {"authorizer": {"userId": "user123"}}
            }
            
            response = lambda_handler(event, MockLambdaContext())
            assert response["statusCode"] == 202, f"Should accept color: {valid_color}"
