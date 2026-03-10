import os
import pytest
import boto3
from unittest.mock import MagicMock
from moto import mock_aws
from aws_lambda_powertools.utilities.typing import LambdaContext

# Set dummy environment variables BEFORE importing your Lambda apps
os.environ["AWS_ACCESS_KEY_ID"] = "testing"
os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
os.environ["AWS_SECURITY_TOKEN"] = "testing"
os.environ["AWS_SESSION_TOKEN"] = "testing"
os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
os.environ["CANVAS_TABLE_NAME"] = "test-canvas-pixels"
os.environ["RATE_LIMIT_TABLE_NAME"] = "test-rate-limits"
os.environ["CONNECTIONS_TABLE_NAME"] = "test-websocket-connections"
os.environ["AWS_XRAY_CONTEXT_MISSING"] = "LOG_ERROR"

# START MOTO GLOBALLY so module-level boto3.client() calls map to Moto,
# which fixes cold-start initialization testing issues.
mock = mock_aws()
mock.start()


class MockLambdaContext:
    """A minimal mock of the AWS Lambda LambdaContext object."""
    function_name = "test-function"
    function_version = "$LATEST"
    invoked_function_arn = "arn:aws:lambda:us-east-1:123456789012:function:test-function"
    memory_limit_in_mb = 128
    aws_request_id = "test-aws-request-id-00000"
    log_group_name = "/aws/lambda/test-function"
    log_stream_name = "2024/01/01/[$LATEST]teststream"
    remaining_time_in_millis = 30000

@pytest.fixture(scope="function", autouse=True)
def dynamodb_mock():
    """Start moto mock for dynamoDB and yield a clean resource."""
    dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
    
    # Create the tables that our Lambdas expect
    dynamodb.create_table(
        TableName=os.environ["CANVAS_TABLE_NAME"],
        KeySchema=[
            {"AttributeName": "ChunkId", "KeyType": "HASH"},
            {"AttributeName": "PixelId", "KeyType": "RANGE"}
        ],
        AttributeDefinitions=[
            {"AttributeName": "ChunkId", "AttributeType": "S"},
            {"AttributeName": "PixelId", "AttributeType": "S"}
        ],
        BillingMode="PAY_PER_REQUEST"
    )
    
    dynamodb.create_table(
        TableName=os.environ["RATE_LIMIT_TABLE_NAME"],
        KeySchema=[
            {"AttributeName": "UserId", "KeyType": "HASH"},
            {"AttributeName": "TimeWindow", "KeyType": "RANGE"}
        ],
        AttributeDefinitions=[
            {"AttributeName": "UserId", "AttributeType": "S"},
            {"AttributeName": "TimeWindow", "AttributeType": "S"}
        ],
        BillingMode="PAY_PER_REQUEST"
    )

    dynamodb.create_table(
        TableName=os.environ["CONNECTIONS_TABLE_NAME"],
        KeySchema=[
            {"AttributeName": "ConnectionId", "KeyType": "HASH"}
        ],
        AttributeDefinitions=[
            {"AttributeName": "ConnectionId", "AttributeType": "S"}
        ],
        BillingMode="PAY_PER_REQUEST"
    )

    yield dynamodb
    
    # Teardown
    dynamodb.Table(os.environ["CANVAS_TABLE_NAME"]).delete()
    dynamodb.Table(os.environ["RATE_LIMIT_TABLE_NAME"]).delete()
    dynamodb.Table(os.environ["CONNECTIONS_TABLE_NAME"]).delete()


@pytest.fixture
def ctx():
    """Shared MockLambdaContext fixture for all tests."""
    return MockLambdaContext()
