import os
import json
import pytest
import boto3
from unittest.mock import patch
from moto import mock_aws

os.environ["DISCORD_APP_ID"] = "12345"

from tests.conftest import MockLambdaContext
from serverless.discord_notifier.app import lambda_handler

@mock_aws
@patch("urllib.request.urlopen")
def test_discord_notifier_sends_webhook(mock_urlopen):
    """Test that an S3 PutObject event successfully triggers a Discord webhook."""

    # 1. Arrange: Create mock S3 bucket + object (with discord_token in metadata)
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="test-snapshots-bucket")
    s3.put_object(
        Bucket="test-snapshots-bucket",
        Key="snapshots/snapshot-12345.png",
        Body=b"fake-image",
        Metadata={"discord_token": "mocktoken123"}
    )

    event = {
        "Records": [
            {
                "s3": {
                    "bucket": {"name": "test-snapshots-bucket"},
                    "object": {"key": "snapshots/snapshot-12345.png"}
                }
            }
        ]
    }

    # 2. Act
    response = lambda_handler(event, MockLambdaContext())

    # 3. Assert
    assert response["statusCode"] == 200

    # Ensure urlopen was called exactly once (the Discord PATCH)
    assert mock_urlopen.call_count == 1

    # Inspect the payload sent to Discord via the Request object
    request_obj = mock_urlopen.call_args[0][0]
    request_body = json.loads(request_obj.data.decode("utf-8"))
    assert "content" in request_body
    assert "snapshots/snapshot-12345.png" in request_body["content"]


@mock_aws
def test_discord_notifier_missing_token_skips():
    """Test that a snapshot with no discord_token in metadata is silently skipped."""
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="test-snapshots-bucket")
    # Put object WITHOUT discord_token metadata
    s3.put_object(Bucket="test-snapshots-bucket", Key="snapshots/no-token.png", Body=b"img")

    event = {
        "Records": [
            {
                "s3": {
                    "bucket": {"name": "test-snapshots-bucket"},
                    "object": {"key": "snapshots/no-token.png"}
                }
            }
        ]
    }

    response = lambda_handler(event, MockLambdaContext())
    # Lambda should succeed but count 0 notifications
    assert response["statusCode"] == 200
    assert "0" in response["body"]
