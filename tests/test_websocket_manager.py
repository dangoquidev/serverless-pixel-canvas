import os
import json
import pytest

from tests.conftest import MockLambdaContext
from serverless.websocket_manager.app import lambda_handler

def test_websocket_manager_connect(dynamodb_mock):
    """Test that a CONNECT event saves the connection ID to DynamoDB."""
    event = {
        "requestContext": {
            "eventType": "CONNECT",
            "connectionId": "test-conn-id-123"
        }
    }
    
    response = lambda_handler(event, MockLambdaContext())
    assert response["statusCode"] == 200
    
    table = dynamodb_mock.Table(os.environ["CONNECTIONS_TABLE_NAME"])
    
    items = table.scan()["Items"]
    assert len(items) == 1
    assert items[0]["ConnectionId"] == "test-conn-id-123"

def test_websocket_manager_disconnect(dynamodb_mock):
    """Test that a DISCONNECT event removes the connection ID from DynamoDB."""
    # 1. Arrange: Insert a record into the mock DB first
    table = dynamodb_mock.Table(os.environ["CONNECTIONS_TABLE_NAME"])
    table.put_item(Item={"ConnectionId": "test-conn-id-456"})
    
    # 2. Act: Send disconnect event
    event = {
        "requestContext": {
            "eventType": "DISCONNECT",
            "connectionId": "test-conn-id-456"
        }
    }
    response = lambda_handler(event, MockLambdaContext())
    assert response["statusCode"] == 200
    
    # 3. Assert: Verify the table is empty
    items = table.scan()["Items"]
    assert len(items) == 0

def test_websocket_manager_missing_connection_id():
    """Test that missing connectionId is rejected cleanly."""
    event = {
        "requestContext": {
            "eventType": "CONNECT"
        }
    }
    response = lambda_handler(event, MockLambdaContext())
    assert response["statusCode"] == 400
