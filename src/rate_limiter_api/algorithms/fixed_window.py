
import time

from rate_limiter_api.database.redis_client import redis_client


async def check_fixed_window(
    user_id: str,
    limit: int,
    window_seconds: int = 60,
) -> dict:
    """Atomically enforce a per-user fixed-window quota using Redis."""

    if limit < 1 or window_seconds < 1:
        raise ValueError("Limit and window must be positive")

    now = time.time()
    window_id = int(now // window_seconds)
    window_end = (window_id + 1) * window_seconds

    key = f"rate_limit:fixed:{user_id}:{window_id}"

    # Redis executes this script atomically, even when many requests
    # arrive at the same time.
    script = """
    local current = tonumber(redis.call('GET', KEYS[1]) or '0')
    local limit = tonumber(ARGV[1])
    local window_seconds = tonumber(ARGV[2])

    if current < limit then
        current = redis.call('INCR', KEYS[1])

        if current == 1 then
            redis.call('EXPIRE', KEYS[1], window_seconds)
        end

        return {1, current}
    end

    return {0, current}
    """

    result = await redis_client.eval(
        script,
        1,
        key,
        limit,
        window_seconds,
    )

    allowed = bool(result[0])
    count = int(result[1])

    return {
        "allowed": allowed,
        "limit": limit,
        "remaining": max(0, limit - count),
        "retry_after": (
            0
            if allowed
            else max(1, int(window_end - time.time() + 0.999))
        ),
    }
