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
def test_broadcast_worker_parses_dynamodb_stream(mock_post, dynamodb_mock):
    """Test that the broadcast worker correctly handles DynamoDB Streams and pushes to clients."""
    
    # 1. Arrange: Insert connections into DynamoDB
    table = dynamodb_mock.Table(os.environ["CONNECTIONS_TABLE_NAME"])
    table.put_item(Item={"ConnectionId": "conn-1"})
    table.put_item(Item={"ConnectionId": "conn-2"})
    
    # Mock the API Gateway Management API (already handled via @patch decorator)
    
    # Mock a DynamoDB STREAM event payload (like adding a pixel)
    event = {
        "Records": [
            {
                "eventName": "INSERT",
                "dynamodb": {
                    "NewImage": {
                        "ChunkId": {"S": "CHUNK#0#0"},
                        "PixelId": {"S": "PIXEL#5#5"},
                        "color": {"S": "#FFFFFF"},
                        "author_id": {"S": "user1"}
                    }
                }
            }
        ]
    }
    
    # 2. Act
    response = lambda_handler(event, MockLambdaContext())
    assert response["statusCode"] == 200
    
    # 3. Assert: Verify post_to_connection was called for BOTH connections
    assert mock_post.call_count == 2
    
    # Grab the payload that was sent
    call_args = mock_post.call_args[1]
    posted_data = json.loads(call_args["Data"].decode("utf-8"))
    
    assert len(posted_data) == 1
    assert posted_data[0]["type"] == "pixel_update"
    assert posted_data[0]["data"]["PixelId"] == "PIXEL#5#5"
