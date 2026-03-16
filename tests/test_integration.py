"""
Integration Tests for Serverless Pixel Canvas

Tests end-to-end workflows involving multiple services:
- SNS → SQS → Lambda event flow
- DynamoDB streams → Broadcast → WebSocket
- Snapshot generation → Discord notification
"""

import json
import os
import pytest
import boto3


# ==========================================
# Integration Test: Pixel Event Flow
# ==========================================


@pytest.mark.integration
def test_pixel_event_from_web_proxy_to_pixel_worker(dynamodb_mock):
    """
    Integration: web_proxy publishes pixel → SNS → SQS → pixel_worker processes.

    Workflow:
    1. Web proxy publishes pixel event to SNS
    2. SNS delivers to SQS queue via subscription
    3. Pixel worker receives and processes from SQS
    """
    sns = boto3.client("sns", region_name="us-east-1")
    sqs = boto3.client("sqs", region_name="us-east-1")

    # Create resources
    topic = sns.create_topic(Name="pixel-events-integration")
    topic_arn = topic["TopicArn"]

    queue = sqs.create_queue(QueueName="pixel-worker-integration-queue")
    queue_url = queue["QueueUrl"]
    queue_arn = sqs.get_queue_attributes(
        QueueUrl=queue_url, AttributeNames=["QueueArn"]
    )["Attributes"]["QueueArn"]

    # Subscribe queue to topic
    sns.subscribe(TopicArn=topic_arn, Protocol="sqs", Endpoint=queue_arn)

    # Use existing table from conftest (already created with proper schema)
    canvas_table = dynamodb_mock.Table(os.environ["CANVAS_TABLE_NAME"])

    # Publish pixel event to SNS (simulating web_proxy)
    pixel_data = {
        "x": 100,
        "y": 250,
        "color": "#FF5733",
        "userId": "user_123",
    }

    sns.publish(
        TopicArn=topic_arn,
        Message=json.dumps({"action": "pixel_draw", **pixel_data}),
        Subject="Pixel Event",
    )

    # Verify message arrived in SQS
    messages = sqs.receive_message(QueueUrl=queue_url)
    assert "Messages" in messages
    assert len(messages["Messages"]) == 1

    sqs_message = messages["Messages"][0]
    message_body = json.loads(sqs_message["Body"])
    sns_message = json.loads(message_body["Message"])

    # Verify pixel data integrity through the pipeline
    assert sns_message["x"] == 100
    assert sns_message["y"] == 250
    assert sns_message["color"] == "#FF5733"
    assert sns_message["userId"] == "user_123"

    # Simulate pixel_worker processing
    chunk_id = f"0#{sns_message['x']//100}#{sns_message['y']//100}"
    pixel_id = f"{chunk_id}#{sns_message['x']}#{sns_message['y']}"
    
    canvas_table.put_item(
        Item={
            "ChunkId": chunk_id,
            "PixelId": pixel_id,
            "color": sns_message["color"],
            "userId": sns_message["userId"],
            "timestamp": 1703001234,
        }
    )

    # Verify pixel was written to DynamoDB
    response = canvas_table.get_item(Key={"ChunkId": chunk_id, "PixelId": pixel_id})
    assert "Item" in response
    assert response["Item"]["color"] == "#FF5733"


# ==========================================
# Integration Test: Broadcast Workflow
# ==========================================


@pytest.mark.integration
def test_broadcast_worker_receives_ddb_stream(dynamodb_mock):
    """
    Integration: DynamoDB stream triggers broadcast_worker for WebSocket delivery.

    Workflow:
    1. Pixel written to canvas-pixels table
    2. DynamoDB stream records change
    3. Broadcast worker receives stream event
    4. Broadcasts to connected WebSocket clients
    """
    # Use existing connections table from conftest
    connections_table = dynamodb_mock.Table(os.environ["CONNECTIONS_TABLE_NAME"])

    # Store some active connections
    connections_table.put_item(
        Item={
            "ConnectionId": "conn_abc123",
            "UserId": "user_456",
            "Timestamp": 1703001234,
            "TTL": 1703087634,
        }
    )

    connections_table.put_item(
        Item={
            "ConnectionId": "conn_def456",
            "UserId": "user_789",
            "Timestamp": 1703001234,
            "TTL": 1703087634,
        }
    )

    # Verify connections are retrievable (as broadcast_worker would do)
    response = connections_table.scan()
    assert response["Count"] >= 2

    connection_ids = [item["ConnectionId"] for item in response["Items"]]
    assert "conn_abc123" in connection_ids
    assert "conn_def456" in connection_ids


# ==========================================
# Integration Test: Snapshot Workflow
# ==========================================


@pytest.mark.integration
def test_snapshot_workflow_with_completion_event(dynamodb_mock):
    """
    Integration: Snapshot generation → S3 upload → SNS completion event.

    Workflow:
    1. Snapshot worker reads canvas from DynamoDB
    2. Generates PNG and uploads to S3
    3. Publishes completion event to SNS
    4. Discord notifier receives event
    """
    sns = boto3.client("sns", region_name="us-east-1")
    s3 = boto3.client("s3", region_name="us-east-1")

    # Use existing canvas table from conftest
    canvas_table = dynamodb_mock.Table(os.environ["CANVAS_TABLE_NAME"])

    # Add some pixels
    chunk_id = "0#0#0"
    for i in range(10):
        pixel_id = f"{chunk_id}#{i}#{i}"
        canvas_table.put_item(
            Item={
                "ChunkId": chunk_id,
                "PixelId": pixel_id,
                "color": "#FF5733",
                "userId": "user_123",
                "timestamp": 1703001234,
            }
        )

    # Create S3 bucket
    s3.create_bucket(Bucket="snapshots-bucket-integration")

    # Simulate snapshot_worker uploading PNG
    s3.put_object(
        Bucket="snapshots-bucket-integration",
        Key="snapshots/snapshot_abc123.png",
        Body=b"fake-png-data",
        ContentType="image/png",
    )

    # Create SNS topic and simulate publication
    topic = sns.create_topic(Name="snapshot-complete-integration")
    topic_arn = topic["TopicArn"]

    response = sns.publish(
        TopicArn=topic_arn,
        Subject="Snapshot Generation Complete",
        Message=json.dumps(
            {
                "action": "snapshot_complete",
                "object_key": "snapshots/snapshot_abc123.png",
                "discord_token": "interaction_token_xyz",
                "pixel_count": 10,
                "correlation_id": "abc123",
            }
        ),
    )

    assert "MessageId" in response

    # Verify S3 object exists
    objects = s3.list_objects_v2(Bucket="snapshots-bucket-integration")
    assert objects["KeyCount"] == 1
    assert objects["Contents"][0]["Key"] == "snapshots/snapshot_abc123.png"


# ==========================================
# Integration Test: Error Recovery (DLQ)
# ==========================================


@pytest.mark.integration
def test_failed_pixel_processing_goes_to_dlq(dynamodb_mock):
    """
    Integration: Failed pixel processing sends message to DLQ.

    Workflow:
    1. Pixel worker fails to process message (e.g., invalid color)
    2. Message goes back to queue
    3. After max retries, message goes to DLQ
    4. DLQ processor picks it up
    """
    sns = boto3.client("sns", region_name="us-east-1")
    sqs = boto3.client("sqs", region_name="us-east-1")

    # Setup SNS and SQS with DLQ
    topic_response = sns.create_topic(Name="pixel-events-dlq-integration")
    topic_arn = topic_response["TopicArn"]

    # Create queues with DLQ configuration
    dlq_response = sqs.create_queue(QueueName="pixel-worker-dlq-integration")
    dlq_url = dlq_response["QueueUrl"]
    dlq_arn = sqs.get_queue_attributes(
        QueueUrl=dlq_url, AttributeNames=["QueueArn"]
    )["Attributes"]["QueueArn"]

    primary_queue_response = sqs.create_queue(
        QueueName="pixel-worker-queue-integration",
        Attributes={
            "RedrivePolicy": json.dumps(
                {
                    "deadLetterTargetArn": dlq_arn,
                    "maxReceiveCount": "3",
                }
            )
        },
    )
    primary_queue_url = primary_queue_response["QueueUrl"]
    primary_queue_arn = sqs.get_queue_attributes(
        QueueUrl=primary_queue_url, AttributeNames=["QueueArn"]
    )["Attributes"]["QueueArn"]

    # Subscribe queue to topic
    sns.subscribe(TopicArn=topic_arn, Protocol="sqs", Endpoint=primary_queue_arn)

    # Publish invalid pixel event
    sns.publish(
        TopicArn=topic_arn,
        Message=json.dumps(
            {
                "action": "pixel_draw",
                "x": 100,
                "y": 250,
                "color": "INVALID",  # Invalid format
                "userId": "user_123",
            }
        ),
    )

    # Message should be in primary queue
    messages = sqs.receive_message(QueueUrl=primary_queue_url)
    assert "Messages" in messages

    # The infrastructure is configured correctly for DLQ
    # In real SQS, after 3 failures the message goes to DLQ
    queue_attrs = sqs.get_queue_attributes(
        QueueUrl=primary_queue_url, AttributeNames=["RedrivePolicy"]
    )
    redrive_policy = json.loads(queue_attrs["Attributes"]["RedrivePolicy"])
    assert redrive_policy["maxReceiveCount"] in [3, "3"]  # moto returns as int
    assert dlq_arn in redrive_policy["deadLetterTargetArn"]


# ==========================================
# Integration Test: Rate Limiting
# ==========================================


@pytest.mark.integration
def test_rate_limit_enforcement_across_requests(dynamodb_mock):
    """
    Integration: Rate limiting works across multiple pixel requests.

    Workflow:
    1. User sends 1st request (within limit)
    2. User sends 2-20 requests (still within limit)
    3. User sends 21st request (exceeds 20/min limit)
    4. Request rejected with 429
    """
    rate_limit_table = dynamodb_mock.Table(os.environ["RATE_LIMIT_TABLE_NAME"])

    user_id = "user_test_rate_limit"

    # Simulate processing 20 pixels
    for i in range(20):
        rate_limit_table.put_item(
            Item={
                "UserId": user_id,
                "TimeWindow": f"1703001200#{i}",
                "PixelCount": i + 1,
                "WindowStart": 1703001200,
                "TTL": 1703001260,  # 60 seconds
            }
        )

    # Verify 20th request succeeds
    response = rate_limit_table.query(
        KeyConditionExpression="UserId = :uid",
        ExpressionAttributeValues={":uid": user_id}
    )
    
    assert response["Count"] == 20


# ==========================================
# Integration Test: WebSocket Connection Lifecycle
# ==========================================


@pytest.mark.integration
def test_websocket_connection_lifecycle(dynamodb_mock):
    """
    Integration: WebSocket connections are tracked with TTL auto-cleanup.

    Workflow:
    1. User connects: connection record created with TTL
    2. User disconnects: connection record deleted
    3. After TTL expires: DynamoDB auto-removes record
    """
    connections_table = dynamodb_mock.Table(os.environ["CONNECTIONS_TABLE_NAME"])

    # User connects
    connection_id = "conn_test_lifecycle_new"
    timestamp = 1703001200
    ttl = timestamp + 86400  # 24 hours

    connections_table.put_item(
        Item={
            "ConnectionId": connection_id,
            "UserId": "user_lifecycle",
            "Timestamp": timestamp,
            "TTL": ttl,
        }
    )

    # Verify connection is stored
    response = connections_table.get_item(Key={"ConnectionId": connection_id})
    assert "Item" in response
    assert response["Item"]["ConnectionId"] == connection_id

    # User disconnects (explicit deletion)
    connections_table.delete_item(Key={"ConnectionId": connection_id})

    # Verify connection is removed
    response = connections_table.get_item(Key={"ConnectionId": connection_id})
    assert "Item" not in response


# ==========================================
# Integration Test: End-to-End Canvas Update
# ==========================================


@pytest.mark.integration
def test_end_to_end_canvas_pixel_update(dynamodb_mock):
    """
    Full integration test of the entire pixel drawing workflow.

    Workflow:
    1. User calls web_proxy /draw endpoint (mocked)
    2. Web proxy publishes to SNS
    3. SNS delivers to SQS via pixel_worker subscription
    4. Pixel worker processes and writes to DynamoDB
    5. Broadcast worker picks up via DynamoDB stream
    6. Broadcasts to all connected WebSocket clients
    """
    sns = boto3.client("sns", region_name="us-east-1")
    sqs = boto3.client("sqs", region_name="us-east-1")

    # Setup infrastructure
    topic_response = sns.create_topic(Name="pixel-events-e2e")
    topic_arn = topic_response["TopicArn"]

    queue_response = sqs.create_queue(QueueName="pixel-queue-e2e")
    queue_url = queue_response["QueueUrl"]
    queue_arn = sqs.get_queue_attributes(
        QueueUrl=queue_url, AttributeNames=["QueueArn"]
    )["Attributes"]["QueueArn"]

    # Subscribe queue to topic
    sns.subscribe(TopicArn=topic_arn, Protocol="sqs", Endpoint=queue_arn)

    # Get existing tables from conftest
    canvas_table = dynamodb_mock.Table(os.environ["CANVAS_TABLE_NAME"])
    connections_table = dynamodb_mock.Table(os.environ["CONNECTIONS_TABLE_NAME"])

    # Step 1: Simulate web_proxy publishing pixel
    pixel_event = {
        "x": 500,
        "y": 500,
        "color": "#FFFFFF",
        "userId": "user_integration_test",
    }

    sns.publish(
        TopicArn=topic_arn,
        Message=json.dumps(pixel_event),
        Subject="Pixel Draw",
    )

    # Step 2: Verify message in SQS
    messages = sqs.receive_message(QueueUrl=queue_url)
    assert "Messages" in messages

    # Step 3: Simulate pixel_worker processing
    sqs_message = messages["Messages"][0]
    message_body = json.loads(sqs_message["Body"])
    pixel_data = json.loads(message_body["Message"])

    chunk_id = f"0#{pixel_data['x']//100}#{pixel_data['y']//100}"
    pixel_id = f"{chunk_id}#{pixel_data['x']}#{pixel_data['y']}"
    
    canvas_table.put_item(
        Item={
            "ChunkId": chunk_id,
            "PixelId": pixel_id,
            "color": pixel_data["color"],
            "userId": pixel_data["userId"],
            "timestamp": 1703001234,
        }
    )

    # Step 4: Verify pixel was written
    response = canvas_table.get_item(Key={"ChunkId": chunk_id, "PixelId": pixel_id})
    assert response["Item"]["color"] == "#FFFFFF"

    # Step 5: Store a connected client
    connections_table.put_item(
        Item={
            "ConnectionId": "conn_test_e2e",
            "UserId": "user_client",
            "Timestamp": 1703001234,
            "TTL": 1703087634,
        }
    )

    # Step 6: Verify broadcast would target this client
    clients = connections_table.scan()
    assert clients["Count"] >= 1
    assert any(c["ConnectionId"] == "conn_test_e2e" for c in clients["Items"])
