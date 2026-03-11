import os
import json
import pytest
import boto3
from unittest.mock import patch
from moto import mock_aws

os.environ["DISCORD_SECRET_NAME"] = "DiscordSecrets"

from tests.conftest import MockLambdaContext
from serverless.discord_notifier.app import lambda_handler


@mock_aws
@patch("serverless.discord_notifier.app.parameters.get_secret")
@patch("serverless.discord_notifier.app.requests.patch")
def test_discord_notifier_sends_webhook(mock_patch, mock_get_secret):
    """Test that an S3 PutObject event successfully triggers a Discord webhook."""
    mock_get_secret.return_value = {"AppId": "12345"}
    mock_patch.return_value.status_code = 200
    mock_patch.return_value.raise_for_status = lambda: None

    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="test-snapshots-bucket")
    s3.put_object(
        Bucket="test-snapshots-bucket",
        Key="snapshots/snapshot-12345.png",
        Body=b"fake-image",
        Metadata={"discord_token": "mocktoken123"},
    )

    event = {
        "Records": [
            {
                "s3": {
                    "bucket": {"name": "test-snapshots-bucket"},
                    "object": {"key": "snapshots/snapshot-12345.png"},
                }
            }
        ]
    }

    response = lambda_handler(event, MockLambdaContext())

    assert response["statusCode"] == 200
    assert mock_patch.call_count == 1

    call_args = mock_patch.call_args
    assert "snapshots/snapshot-12345.png" in call_args[1]["json"]["content"]


@mock_aws
@patch("serverless.discord_notifier.app.parameters.get_secret")
def test_discord_notifier_missing_token_skips(mock_get_secret):
    """Test that a snapshot with no discord_token in metadata is silently skipped."""
    mock_get_secret.return_value = {"AppId": "12345"}

    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="test-snapshots-bucket")
    s3.put_object(
        Bucket="test-snapshots-bucket",
        Key="snapshots/no-token.png",
        Body=b"img",
    )

    event = {
        "Records": [
            {
                "s3": {
                    "bucket": {"name": "test-snapshots-bucket"},
                    "object": {"key": "snapshots/no-token.png"},
                }
            }
        ]
    }

    response = lambda_handler(event, MockLambdaContext())
    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["processed"] == 0
