import os
import json
import pytest
from moto import mock_aws
import boto3

# Setup dummy environment before import
os.environ["SNAPSHOT_BUCKET"] = "test-snapshots-bucket"

from tests.conftest import MockLambdaContext
from serverless.snapshot_worker.app import lambda_handler

def test_snapshot_worker_creates_and_uploads_image(dynamodb_mock):
    """Test that the snapshot worker can scan DynamoDB, draw a PIL image, and upload to S3."""
    
    # 1. Arrange: Create the S3 mock
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="test-snapshots-bucket")
    
    # Seed DynamoDB with some pixels
    table = dynamodb_mock.Table(os.environ["CANVAS_TABLE_NAME"])
    table.put_item(Item={"ChunkId": "CHUNK#0#0", "PixelId": "PIXEL#50#50", "color": "#FF0000"})
    table.put_item(Item={"ChunkId": "CHUNK#0#0", "PixelId": "PIXEL#60#60", "color": "#00FF00"})
    
    # Mock Event (Usually invoked via EventBridge cron or manually)
    event = {
        "Records": [
            {
                "body": json.dumps({"Message": json.dumps({"action": "snapshot", "discord_token": "mock_token"})})
            }
        ]
    }
    
    # 2. Act
    response = lambda_handler(event, MockLambdaContext())
    
    # 3. Assert
    assert response["statusCode"] == 200
    assert "Successfully generated 1 snapshots" in response["body"]
    
    # Check S3 metadata
    s3_response = s3.list_objects_v2(Bucket="test-snapshots-bucket", Prefix="snapshots/snapshot_")
    assert "Contents" in s3_response
    assert len(s3_response["Contents"]) == 1
    
    saved_key = s3_response["Contents"][0]["Key"]
    obj_meta = s3.head_object(Bucket="test-snapshots-bucket", Key=saved_key)
    assert obj_meta["ContentType"] == "image/png"
