
import time
import uuid

from rate_limiter_api.database.redis_client import redis_client


async def acquire_request_slot(
    user_id: str,
    max_concurrent: int = 2,
    lease_seconds: int = 300,
) -> str | None:
    """Atomically reserve a concurrency slot in Redis."""

    if max_concurrent < 1:
        raise ValueError("max_concurrent must be positive")

    if lease_seconds < 1:
        raise ValueError("lease_seconds must be positive")

    request_id = str(uuid.uuid4())
    key = f"concurrency:active:{user_id}"
    now_ms = int(time.time() * 1000)
    expires_at_ms = now_ms + lease_seconds * 1000

    script = """
    local key = KEYS[1]
    local now_ms = tonumber(ARGV[1])
    local expires_at_ms = tonumber(ARGV[2])
    local max_concurrent = tonumber(ARGV[3])
    local request_id = ARGV[4]

    -- Remove expired requests left behind by crashed requests.
    redis.call('ZREMRANGEBYSCORE', key, '-inf', now_ms)

    local active_count = redis.call('ZCARD', key)

    if active_count >= max_concurrent then
        return 0
    end

    redis.call('ZADD', key, expires_at_ms, request_id)

    -- Keep the Redis key only as long as it has active requests.
    redis.call('PEXPIRE', key, expires_at_ms - now_ms)

    return 1
    """

    acquired = await redis_client.eval(
        script,
        1,
        key,
        now_ms,
        expires_at_ms,
        max_concurrent,
        request_id,
    )

    if acquired:
        return request_id

    return None


async def release_request_slot(
    user_id: str,
    request_id: str,
) -> None:
    """Release a previously reserved concurrency slot."""

    key = f"concurrency:active:{user_id}"

    await redis_client.zrem(key, request_id)
