import json
import os
import boto3
import pytest
from moto import mock_aws

os.environ["PIXEL_WORKER_QUEUE_URL"] = "https://sqs.us-east-1.amazonaws.com/123456789012/test-pixel-worker-queue"

from tests.conftest import MockLambdaContext
from serverless.dlq_processor.app import lambda_handler

@mock_aws
def test_dlq_processor_redrives_message():
    """Test that the DLQ processor successfully redrives messages back to the main queue."""
    sqs = boto3.client("sqs", region_name="us-east-1")
    
    # 1. Arrange: Create the queue we are asserting messages get put into
    queue = sqs.create_queue(QueueName="test-pixel-worker-queue")
    os.environ["PIXEL_WORKER_QUEUE_URL"] = queue["QueueUrl"]
    
    # Simulate an SQS DLQ event payload
    sns_payload = {"payload": {"user_id": "dlq-user", "x": 0, "y": 0, "color": "#000"}}
    sqs_body = {"Message": json.dumps(sns_payload)}
    
    event = {
        "Records": [
            {
                "messageId": "failed-msg-123",
                "body": json.dumps(sqs_body)
            }
        ]
    }
    
    # 2. Act
    response = lambda_handler(event, MockLambdaContext())
    assert response["statusCode"] == 200
    assert "1 redriven" in response["body"]
    
    # 3. Assert: The message should now be in the main queue
    messages = sqs.receive_message(QueueUrl=queue["QueueUrl"])
    assert "Messages" in messages
    
    redriven_body = messages["Messages"][0]["Body"]
    assert json.loads(redriven_body)["Message"] == json.dumps(sns_payload)

@mock_aws
def test_dlq_processor_bad_json():
    """Test that DLQ processor ignores garbage JSON."""
    event = {
        "Records": [
            {
                "messageId": "bad-msg-1",
                "body": "this is not json"
            }
        ]
    }
    
    response = lambda_handler(event, MockLambdaContext())
    assert response["statusCode"] == 200
    assert "1 failed" in response["body"]
