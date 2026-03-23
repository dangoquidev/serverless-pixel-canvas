import json
import os
import pytest

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
    
    # Chunk ID should be 150//100 = 1, 250//100 = 2
    chunk_id = "CHUNK#1#2"
    
    db_response = table.query(
        KeyConditionExpression="ChunkId = :c",
        ExpressionAttributeValues={":c": chunk_id}
    )
    
    items = db_response.get("Items", [])
    assert len(items) == 1
    assert items[0]["PixelId"] == "PIXEL#150#250"
    assert items[0]["color"] == "#FF0000"
    assert items[0]["author_id"] == "test_user_123"

def test_pixel_worker_enforces_rate_limit(dynamodb_mock, caplog):
    """Test that submitting more than 20 requests per minute rejects the pixels."""
    sns_message = {"payload": {"user_id": "spammer", "x": 10, "y": 10, "color": "#000000"}}
    sqs_event = {
        "Records": [{"body": json.dumps({"Message": json.dumps(sns_message)})}]
    }
    
    # We loop 25 times. The first 20 should succeed, the last 5 should hit the rate limit constraint
    for _ in range(25):
        lambda_handler(sqs_event, MockLambdaContext())
        
    table = dynamodb_mock.Table(os.environ["CANVAS_TABLE_NAME"])
    
    db_response = table.scan()
    
    # Even though we sent 25 messages, exactly 20 should be saved due to 
    # the DynamoDB `attribute_not_exists(draw_count) OR draw_count < :limit` rule
    # Note: Because the mock runs fast, they will overwrite the same PIXEL#10#10 
    # but the rate limit table will have count = 20.
    rate_table = dynamodb_mock.Table(os.environ["RATE_LIMIT_TABLE_NAME"])
    rate_items = rate_table.scan()["Items"]
    
    assert len(rate_items) == 1
    assert rate_items[0]["draw_count"] == 20
