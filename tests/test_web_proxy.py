import os
import json
import pytest
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
        "correlation_id": "test-corr-id",
        "requestContext": {
            "authorizer": {"userId": "user123", "username": "testuser"}
        }
    }
    
    # Act
    response = lambda_handler(event, MockLambdaContext())
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
    assert published_event["correlation_id"] == "test-corr-id"


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


def test_web_proxy_missing_fields():
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
    assert "Missing required fields" in body["error"]

def test_web_proxy_invalid_json():
    """Test that invalid JSON is caught."""
    event = {
        "body": "this is not json",
        "requestContext": {"authorizer": {"userId": "user123"}}
    }
    response = lambda_handler(event, MockLambdaContext())
    assert response["statusCode"] == 400
