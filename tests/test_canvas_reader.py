import json
import os
import pytest

from tests.conftest import MockLambdaContext
from serverless.canvas_reader.app import lambda_handler

def test_canvas_reader_returns_pixels(dynamodb_mock):
    """Test that the canvas_reader correctly queries and returns pixels for a chunk."""
    
    # 1. Arrange: Seed the mock DynamoDB table with some test data (minified schema)
    table = dynamodb_mock.Table(os.environ["CANVAS_TABLE_NAME"])
    table.put_item(Item={
        "c": "0#0",  # ChunkId
        "p": 1010,   # Pixel position
        "co": 0xFFFFFF,  # Color as integer (white)
        "u": "user1",
        "t": 1234567890
    })
    table.put_item(Item={
        "c": "0#0",
        "p": 2020,   # Another pixel
        "co": 0x000000,  # Color as integer (black)
        "u": "user2",
        "t": 1234567890
    })
    
    # 2. Act: Call the lambda handler simulating an API Gateway GET request
    event = {
        "queryStringParameters": {
            "cx": "0",
            "cy": "0"
        },
        "headers": {
            "x-correlation-id": "test-correlation-id"
        }
    }
    
    response = lambda_handler(event, MockLambdaContext())
    
    # 3. Assert: 
    assert response["statusCode"] == 200
    assert response.get("isBase64Encoded") == True
    assert "body" in response
    # Body should be base64-encoded binary data, not JSON
    # Verify it's base64 by trying to decode it
    import base64
    try:
        decoded = base64.b64decode(response["body"])
        # Binary data should have some content
        assert len(decoded) > 0
    except Exception as e:
        pytest.fail(f"Response body is not valid base64: {str(e)}")
    
def test_canvas_reader_bad_coordinates():
    """Test that providing non-integer coordinates kicks back a 400 Bad Request."""
    event = {
        "queryStringParameters": {
            "cx": "abc",  # Invalid
            "cy": "0"
        }
    }
    
    response = lambda_handler(event, MockLambdaContext())
    
    assert response["statusCode"] == 400
    body = json.loads(response["body"])
    assert "error" in body
