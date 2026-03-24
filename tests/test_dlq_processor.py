import json
import os
import boto3
import pytest
from unittest.mock import patch
from moto import mock_aws

os.environ["PIXEL_WORKER_QUEUE_URL"] = "https://sqs.us-east-1.amazonaws.com/123456789012/test-pixel-worker-queue"

from tests.conftest import MockLambdaContext
from serverless.dlq_processor.app import lambda_handler

@mock_aws
def test_dlq_processor_redrives_single_message():
    """Test that the DLQ processor successfully redrives messages back to the main queue."""
    sqs = boto3.client("sqs", region_name="us-east-1")
    
    # 1. Arrange: Create the queue we are asserting messages get put into
    queue = sqs.create_queue(QueueName="test-pixel-worker-queue")
    os.environ["PIXEL_WORKER_QUEUE_URL"] = queue["QueueUrl"]
    
    # Simulate an SQS DLQ event payload
    sns_payload = {"payload": {"user_id": "dlq-user", "x": 0, "y": 0, "color": "#000000"}}
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
def test_dlq_processor_redrives_batch_messages():
    """Test that DLQ processor redrives multiple messages in a batch."""
    sqs = boto3.client("sqs", region_name="us-east-1")
    
    queue = sqs.create_queue(QueueName="test-pixel-worker-queue")
    os.environ["PIXEL_WORKER_QUEUE_URL"] = queue["QueueUrl"]
    
    event = {
        "Records": []
    }
    
    # Create 3 valid messages
    for i in range(3):
        sns_payload = {"payload": {"user_id": f"user-{i}", "x": i, "y": i, "color": "#000000"}}
        sqs_body = {"Message": json.dumps(sns_payload)}
        event["Records"].append({
            "messageId": f"msg-{i}",
            "body": json.dumps(sqs_body)
        })
    
    # Act
    response = lambda_handler(event, MockLambdaContext())
    assert response["statusCode"] == 200
    assert "3 redriven" in response["body"]
    
    # Assert
    messages = sqs.receive_message(QueueUrl=queue["QueueUrl"], MaxNumberOfMessages=10)
    assert len(messages["Messages"]) == 3


def test_dlq_processor_malformed_json():
    """Test that DLQ processor handles and logs unparseable JSON gracefully."""
    event = {
        "Records": [
            {
                "messageId": "bad-msg-1",
                "body": "this is not json"
            }
        ]
    }
    
    # Should not crash, just log the error
    response = lambda_handler(event, MockLambdaContext())
    assert response["statusCode"] == 200
    assert "0 redriven, 1 failed" in response["body"]


@mock_aws
def test_dlq_processor_mixed_valid_and_invalid():
    """Test DLQ processor with mix of valid and invalid messages."""
    sqs = boto3.client("sqs", region_name="us-east-1")
    queue = sqs.create_queue(QueueName="test-pixel-worker-queue")
    os.environ["PIXEL_WORKER_QUEUE_URL"] = queue["QueueUrl"]
    
    # Create a batch with 2 valid and 1 invalid
    sns_payload = {"payload": {"user_id": "user-1", "x": 0, "y": 0, "color": "#000"}}
    sqs_body = {"Message": json.dumps(sns_payload)}
    
    event = {
        "Records": [
            {
                "messageId": "msg-1",
                "body": json.dumps(sqs_body)
            },
            {
                "messageId": "bad-msg",
                "body": "invalid json"
            },
            {
                "messageId": "msg-2",
                "body": json.dumps(sqs_body)
            }
        ]
    }
    
    response = lambda_handler(event, MockLambdaContext())
    assert response["statusCode"] == 200
    assert "2 redriven" in response["body"]
    assert "1 failed" in response["body"]
    
    # Verify only valid messages made it to the queue
    messages = sqs.receive_message(QueueUrl=queue["QueueUrl"], MaxNumberOfMessages=10)
    assert len(messages["Messages"]) == 2


@mock_aws
def test_dlq_processor_empty_records():
    """Test DLQ processor with empty Records list."""
    event = {"Records": []}
    
    response = lambda_handler(event, MockLambdaContext())
    assert response["statusCode"] == 200
    assert "No records" in response["body"]


@mock_aws
def test_dlq_processor_sqs_send_failure():
    """Test DLQ processor when SQS send_message fails."""
    with patch("serverless.dlq_processor.app.sqs.send_message") as mock_send:
        mock_send.side_effect = Exception("SQS service unavailable")
        
        sns_payload = {"payload": {"user_id": "user-1", "x": 0, "y": 0, "color": "#000000"}}
        sqs_body = {"Message": json.dumps(sns_payload)}
        
        event = {
            "Records": [
                {
                    "messageId": "msg-1",
                    "body": json.dumps(sqs_body)
                }
            ]
        }
        
        response = lambda_handler(event, MockLambdaContext())
        assert response["statusCode"] == 200
        # Message should be counted as failed
        assert "0 redriven, 1 failed" in response["body"]


@mock_aws
def test_dlq_processor_partial_json_structure():
    """Test DLQ processor with partially valid JSON structure."""
    event = {
        "Records": [
            {
                "messageId": "partial-msg",
                "body": json.dumps({"Message": "not a json string"})  # Message should be a JSON string
            }
        ]
    }
    
    response = lambda_handler(event, MockLambdaContext())
    # Should handle gracefully
    assert response["statusCode"] == 200


@mock_aws
def test_dlq_processor_missing_queue_url():
    """Test DLQ processor when PIXEL_WORKER_QUEUE_URL is not properly set (None)."""
    # Patch the module-level PIXEL_WORKER_QUEUE_URL to None
    with patch("serverless.dlq_processor.app.PIXEL_WORKER_QUEUE_URL", None):
        sns_payload = {"payload": {"user_id": "user-1", "x": 0, "y": 0, "color": "#000000"}}
        sqs_body = {"Message": json.dumps(sns_payload)}
        
        event = {
            "Records": [
                {
                    "messageId": "msg-1",
                    "body": json.dumps(sqs_body)
                }
            ]
        }
        
        response = lambda_handler(event, MockLambdaContext())
        assert response["statusCode"] == 200
        # Message should be counted as failed due to missing URL
        assert "0 redriven, 1 failed" in response["body"]


@mock_aws
def test_dlq_processor_extracts_user_id_for_logging():
    """Test that DLQ processor correctly extracts user_id from nested payload for logging."""
    sqs = boto3.client("sqs", region_name="us-east-1")
    queue = sqs.create_queue(QueueName="test-pixel-worker-queue")
    os.environ["PIXEL_WORKER_QUEUE_URL"] = queue["QueueUrl"]
    
    sns_payload = {
        "payload": {
            "user_id": "test-user-12345",
            "x": 100,
            "y": 200,
            "color": "#FF0000"
        }
    }
    sqs_body = {"Message": json.dumps(sns_payload)}
    
    event = {
        "Records": [
            {
                "messageId": "msg-1",
                "body": json.dumps(sqs_body)
            }
        ]
    }
    
    # Should process without error and log user info
    response = lambda_handler(event, MockLambdaContext())
    assert response["statusCode"] == 200
    assert "1 redriven" in response["body"]
