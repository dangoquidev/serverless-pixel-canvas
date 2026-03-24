"""
Token Bucket Rate Limiter for Pixel Canvas

The token bucket algorithm provides:
- Smooth rate limiting with burst capacity
- Better UX than strict per-minute limits
- Per-endpoint granularity
- DynamoDB-backed persistence

Algorithm:
1. Each user gets a "bucket" of tokens (20 per minute)
2. Each pixel draw costs 1 token
3. Tokens refill over time at the rate limit
4. Users can burst up to 20 pixels if they've been idle
5. Once bucket empty, requests are rejected (HTTP 429)

This is MUCH better than "sorry, wait 3 more seconds" responses.
"""

import time
import os
import boto3
import json
from decimal import Decimal
from aws_lambda_powertools import Logger

logger = Logger()

# Pull from environment - makes it testable
RATE_LIMIT_TOKENS = float(os.environ.get("RATE_LIMIT_TOKENS", "20"))  # 20 pixels/min
RATE_LIMIT_REFILL_RATE = float(os.environ.get("RATE_LIMIT_REFILL_RATE", "0.333"))  # tokens per second (20/60)
RATE_LIMIT_TABLE = os.environ.get("RATE_LIMIT_TABLE_NAME", "canvas-rate-limits")

dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))
rate_limit_table = dynamodb.Table(RATE_LIMIT_TABLE)


def get_token_bucket(user_id: str) -> dict:
    """
    Retrieve user's token bucket from DynamoDB.
    
    Returns:
        {
            'tokens': float - Current tokens available,
            'last_refill': float - Unix timestamp of last refill,
            'user_id': str
        }
    """
    try:
        response = rate_limit_table.get_item(
            Key={'UserId': user_id}
        )
        
        if 'Item' not in response:
            # First request - give them a full bucket
            logger.info(f"New user {user_id}: initializing bucket", extra={"user_id": user_id})
            return {
                'user_id': user_id,
                'tokens': RATE_LIMIT_TOKENS,
                'last_refill': time.time()
            }
        
        item = response['Item']
        return {
            'user_id': user_id,
            'tokens': float(item.get('tokens', RATE_LIMIT_TOKENS)),
            'last_refill': float(item.get('last_refill', time.time()))
        }
    except Exception as e:
        logger.error(f"Failed to get token bucket: {str(e)}", extra={"user_id": user_id})
        # On error, be lenient - grant full bucket
        return {
            'user_id': user_id,
            'tokens': RATE_LIMIT_TOKENS,
            'last_refill': time.time()
        }


def refill_tokens(bucket: dict, current_time: float) -> dict:
    """
    Add tokens based on elapsed time since last refill.
    
    Args:
        bucket: Token bucket from DynamoDB
        current_time: Unix timestamp of now
    
    Returns:
        Updated bucket with refilled tokens (capped at RATE_LIMIT_TOKENS)
    """
    elapsed = current_time - bucket['last_refill']
    
    # Tokens per second * seconds elapsed
    new_tokens = elapsed * RATE_LIMIT_REFILL_RATE
    total_tokens = min(
        bucket['tokens'] + new_tokens,
        RATE_LIMIT_TOKENS  # Cap at max
    )
    
    bucket['tokens'] = total_tokens
    bucket['last_refill'] = current_time
    
    return bucket


def save_token_bucket(bucket: dict) -> bool:
    """
    Persist updated bucket back to DynamoDB with TTL.
    
    Args:
        bucket: Updated token bucket
    
    Returns:
        True if successful, False otherwise
    """
    try:
        current_time = time.time()
        # TTL expires bucket after 24 hours of inactivity
        ttl = int(current_time) + 86400
        
        rate_limit_table.put_item(
            Item={
                'UserId': bucket['user_id'],
                'tokens': Decimal(str(round(bucket['tokens'], 4))),
                'last_refill': Decimal(str(bucket['last_refill'])),
                'updated_at': current_time,
                'ttl': ttl
            }
        )
        return True
    except Exception as e:
        logger.error(f"Failed to save token bucket: {str(e)}")
        return False


def check_rate_limit(user_id: str, cost: int = 1) -> tuple[bool, dict]:
    """
    Check if user has tokens available. Consumes tokens if yes.
    
    This is the main entry point for rate limiting.
    
    Args:
        user_id: User identifier
        cost: Tokens to consume (default 1 per pixel)
    
    Returns:
        (allowed: bool, details: dict) where:
        - allowed: True if request should proceed
        - details: {'tokens_remaining': float, 'retry_after_seconds': float, ...}
    """
    current_time = time.time()
    
    # Step 1: Get current bucket
    bucket = get_token_bucket(user_id)
    
    # Step 2: Refill tokens based on elapsed time
    bucket = refill_tokens(bucket, current_time)
    
    # Step 3: Check if we have enough
    if bucket['tokens'] >= cost:
        # Consume tokens
        bucket['tokens'] -= cost
        
        # Step 4: Persist new state
        save_token_bucket(bucket)
        
        logger.info(
            "Rate limit: ALLOWED",
            extra={
                "user_id": user_id,
                "tokens_remaining": bucket['tokens'],
                "cost": cost
            }
        )
        
        return True, {
            'tokens_remaining': bucket['tokens'],
            'limit': RATE_LIMIT_TOKENS,
            'reset_in_seconds': (RATE_LIMIT_TOKENS - bucket['tokens']) / RATE_LIMIT_REFILL_RATE
        }
    else:
        # Rate limited - calculate when they'll have a token
        tokens_needed = cost - bucket['tokens']
        seconds_to_wait = tokens_needed / RATE_LIMIT_REFILL_RATE
        
        logger.warning(
            "Rate limit: DENIED",
            extra={
                "user_id": user_id,
                "tokens_available": bucket['tokens'],
                "tokens_needed": tokens_needed,
                "retry_after_seconds": seconds_to_wait
            }
        )
        
        return False, {
            'tokens_remaining': bucket['tokens'],
            'tokens_needed': tokens_needed,
            'limit': RATE_LIMIT_TOKENS,
            'retry_after_seconds': round(seconds_to_wait, 1),
            'reset_in_seconds': RATE_LIMIT_TOKENS / RATE_LIMIT_REFILL_RATE
        }


def create_rate_limit_response(allowed: bool, details: dict) -> dict:
    """
    Create HTTP response for rate limit status.
    
    Args:
        allowed: Whether request was allowed
        details: Rate limit details from check_rate_limit()
    
    Returns:
        HTTP response dict ready for API Gateway
    """
    if allowed:
        return {
            'statusCode': 200,
            'headers': {
                'X-RateLimit-Limit': str(int(details['limit'])),
                'X-RateLimit-Remaining': str(int(details['tokens_remaining'])),
                'X-RateLimit-Reset-In': str(int(details['reset_in_seconds'])),
            },
            'body': json.dumps({'ok': True})
        }
    else:
        retry_after = details.get('retry_after_seconds', 1)
        return {
            'statusCode': 429,
            'headers': {
                'Retry-After': str(int(retry_after)),
                'X-RateLimit-Limit': str(int(details['limit'])),
                'X-RateLimit-Remaining': str(int(details['tokens_remaining'])),
                'X-RateLimit-Reset-In': str(int(details['reset_in_seconds'])),
                'Content-Type': 'application/json'
            },
            'body': json.dumps({
                'error': 'rate_limit_exceeded',
                'message': f'Rate limited. Retry after {retry_after} seconds.',
                'retry_after_seconds': retry_after,
                'limit': int(details['limit']),
                'tokens_remaining': int(details['tokens_remaining'])
            })
        }


def explain_bucket() -> str:
    """
    Debug endpoint to explain the token bucket algorithm.
    
    Returns:
        String explanation of how token bucket works
    """
    return f"""
TOKEN BUCKET RATE LIMITER
========================

Limit: {RATE_LIMIT_TOKENS} tokens per user
Refill Rate: {RATE_LIMIT_REFILL_RATE} tokens/second ({RATE_LIMIT_TOKENS} tokens/minute)

HOW IT WORKS:
1. Each user starts with {RATE_LIMIT_TOKENS} tokens
2. Each pixel costs 1 token
3. Tokens refill at {RATE_LIMIT_REFILL_RATE} per second
4. Users can burst up to {RATE_LIMIT_TOKENS} if idle
5. Once empty, HTTP 429 with Retry-After header

EXAMPLES:
- User draws 20 pixels instantly → bucket now has 0 tokens → next request blocked
- Wait 3 seconds → bucket has 1 token → next request allowed (19 remaining)
- Wait 60 seconds → bucket refilled to {RATE_LIMIT_TOKENS} tokens → burst again possible

BENEFITS OVER SIMPLE COUNTER:
✓ Allows bursts (draw 20 pixels if idle)
✓ Smoother rate limiting (tokens refill continuously)
✓ Better UX (no sudden "wait 3s" messages)
✓ Prevents abuse (can't exceed {RATE_LIMIT_TOKENS}/min sustained)

RESPONSE HEADERS (on all requests):
- X-RateLimit-Limit: {RATE_LIMIT_TOKENS}
- X-RateLimit-Remaining: tokens available now
- X-RateLimit-Reset-In: seconds until refull
- Retry-After: seconds to wait (on 429 only)
"""
