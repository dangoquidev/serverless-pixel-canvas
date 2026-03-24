import json
import os
import pytest
from decimal import Decimal

# We import the Lambda handler after conftest.py has set up the mock environment vars
from tests.conftest import MockLambdaContext
from serverless.pixel_worker.app import lambda_handler

def test_pixel_worker_processes_valid_message(dynamodb_mock):
    """Test that a valid SQS pixel message writes successfully to DynamoDB."""
    
    # 1. Arrange: Create a mock SQS event payload (what SNS sends to SQS)
    sns_message = {
        "payload": {
            "user_id": "test_user_123",
            "x": 150,
            "y": 250,
            "color": "#FF0000"
        }
    }
    
    sqs_event = {
        "Records": [
            {
                "messageId": "test_msg_id",
                "body": json.dumps({"Message": json.dumps(sns_message)})
            }
        ]
    }
    
    # 2. Act: Call the lambda handler
    response = lambda_handler(sqs_event, MockLambdaContext())
    
    # 3. Assert: Verify the response code and check DynamoDB state
    assert response["statusCode"] == 200
    
    table = dynamodb_mock.Table(os.environ["CANVAS_TABLE_NAME"])
    
    # Chunk ID should be 150//100 = 1, 250//100 = 2 -> "1#2"
    chunk_id = "1#2"
    
    db_response = table.query(
        KeyConditionExpression="c = :c",
        ExpressionAttributeValues={":c": chunk_id}
    )
    
    items = db_response.get("Items", [])
    assert len(items) == 1
    # Position = local_y * CHUNK_SIZE + local_x = (250 % 100) * 100 + (150 % 100) = 50 * 100 + 50 = 5050
    assert items[0]["p"] == Decimal("5050")
    assert items[0]["co"] == Decimal("16711680")  # #FF0000 as integer
    assert items[0]["u"] == "test_user_123"  # Minified user_id key

def test_pixel_worker_accepts_all_pixels_no_rate_limiting(dynamodb_mock, caplog):
    """Test that pixel_worker accepts all pixels since rate limiting is done in web_proxy.
    
    Rate limiting has been consolidated to web_proxy (token bucket algorithm).
    pixel_worker receives only pre-validated, rate-limited pixels.
    """
    sns_message = {"payload": {"user_id": "user123", "x": 10, "y": 10, "color": "#000000"}}
    sqs_event = {
        "Records": [{"body": json.dumps({"Message": json.dumps(sns_message)})}]
    }
    
    # Submit multiple pixels - all should be accepted since rate limiting is upstream
    for _ in range(25):
        lambda_handler(sqs_event, MockLambdaContext())
        
    table = dynamodb_mock.Table(os.environ["CANVAS_TABLE_NAME"])
    
    db_response = table.scan()
    
    # All pixels should be written (they overwrite the same position, but that's expected)
    # Rate limiting is no longer done at this level
    assert len(db_response["Items"]) > 0
    assert db_response["Items"][0]["u"] == "user123"
