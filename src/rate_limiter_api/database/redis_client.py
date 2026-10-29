
import redis.asyncio as redis

from rate_limiter_api.config import settings


connection_pool = redis.BlockingConnectionPool.from_url(
    settings.redis_url,
    max_connections=5,
    timeout=30,
    decode_responses=True,
)

redis_client = redis.Redis(connection_pool=connection_pool)


async def connect_to_redis() -> None:
    await redis_client.ping()
    print("Connected to Redis successfully!")


async def close_redis_connection() -> None:
    await redis_client.aclose()
