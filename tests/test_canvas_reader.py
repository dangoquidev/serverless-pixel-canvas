import json
import os
import pytest

from tests.conftest import MockLambdaContext
from serverless.canvas_reader.app import lambda_handler

def test_canvas_reader_returns_pixels(dynamodb_mock):
    """Test that the canvas_reader correctly queries and returns pixels for a chunk."""
    
    # 1. Arrange: Seed the mock DynamoDB table with some test data
    table = dynamodb_mock.Table(os.environ["CANVAS_TABLE_NAME"])
    table.put_item(Item={"ChunkId": "CHUNK#0#0", "PixelId": "PIXEL#10#10", "color": "#FFF"})
    table.put_item(Item={"ChunkId": "CHUNK#0#0", "PixelId": "PIXEL#20#20", "color": "#000"})
    
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
    
    body = json.loads(response["body"])
    assert body["chunk"] == "CHUNK#0#0"
    
    pixels = body["pixels"]
    assert len(pixels) == 2
    assert pixels[0]["color"] == "#FFF"
    
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
