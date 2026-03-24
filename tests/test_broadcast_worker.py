import os
import json
import pytest
import boto3
from moto import mock_aws

os.environ["WSS_API_ENDPOINT"] = "https://mock.execute-api.us-east-1.amazonaws.com/prod"

from unittest.mock import patch
from tests.conftest import MockLambdaContext
from serverless.broadcast_worker.app import lambda_handler

@patch("serverless.broadcast_worker.app.apigw_client.post_to_connection")
def test_broadcast_worker_parses_sns_sqs_messages(mock_post, dynamodb_mock):
    """Test that the broadcast worker correctly handles SNS→SQS messages and broadcasts to clients."""

    # 1. Arrange: Insert connections into DynamoDB
    table = dynamodb_mock.Table(os.environ["CONNECTIONS_TABLE_NAME"])
    table.put_item(Item={"ConnectionId": "conn-1", "LiveStatus": "ACTIVE"})
    table.put_item(Item={"ConnectionId": "conn-2", "LiveStatus": "ACTIVE"})

    # Mock the API Gateway Management API (already handled via @patch decorator)

    # Mock an SQS event containing a pixel update wrapped in SNS → SQS envelope
    event = {
        "Records": [
            {
                "body": json.dumps({
                    "Message": json.dumps({
                        "action": "pixel_update",
                        "payload": {
                            "x": 5,
                            "y": 5,
                            "color": "#FFFFFF"
                        }
                    })
                })
            }
        ]
    }

    # 2. Act
    response = lambda_handler(event, MockLambdaContext())
    assert response["statusCode"] == 200

    # 3. Assert: Verify post_to_connection was called for BOTH connections
    assert mock_post.call_count == 2

    # The broadcast_worker sends binary-encoded pixel data
    call_args = mock_post.call_args[1]
    # Data is base64-encoded binary, verify it's not empty
    assert "Data" in call_args
    assert len(call_args["Data"]) > 0
