
import time

from rate_limiter_api.database.redis_client import redis_client


async def check_token_bucket(
    user_id: str,
    capacity: int = 5,
    refill_rate: float = 1 / 12,
) -> dict:
    """Atomically check and consume tokens using Redis."""

    if capacity < 1 or refill_rate <= 0:
        raise ValueError("Capacity and refill rate must be positive")

    now = time.time()
    key = f"rate_limit:bucket:{user_id}"

    # Redis executes the refill, check, and consumption atomically.
    script = """
    local capacity = tonumber(ARGV[1])
    local refill_rate = tonumber(ARGV[2])
    local now = tonumber(ARGV[3])

    local values = redis.call('HMGET', KEYS[1], 'tokens', 'updated_at')
    local tokens = tonumber(values[1])
    local updated_at = tonumber(values[2])

    if tokens == nil then
        tokens = capacity
        updated_at = now
    else
        local elapsed = math.max(0, now - updated_at)
        tokens = math.min(capacity, tokens + elapsed * refill_rate)
    end

    local allowed = 0

    if tokens >= 1 then
        tokens = tokens - 1
        allowed = 1
    end

    redis.call(
        'HSET',
        KEYS[1],
        'tokens', tokens,
        'updated_at', now
    )

    -- Expire inactive bucket state after enough time to refill fully.
    local ttl = math.max(1, math.ceil(capacity / refill_rate))
    redis.call('EXPIRE', KEYS[1], ttl)

    return {allowed, tokens}
    """

    result = await redis_client.eval(
        script,
        1,
        key,
        capacity,
        refill_rate,
        now,
    )

    allowed = bool(result[0])
    remaining = float(result[1])

    retry_after = 0
    if not allowed:
        retry_after = max(
            1,
            int((1 - remaining) / refill_rate + 0.999),
        )

    return {
        "allowed": allowed,
        "limit": capacity,
        "remaining": int(remaining),
        "retry_after": retry_after,
    }
