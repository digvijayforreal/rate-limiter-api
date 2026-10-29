import asyncio

from rate_limiter_api.database.redis_client import (
    connect_to_redis,
    close_redis_connection,
)


async def main():
    try:
        await connect_to_redis()
    finally:
        await close_redis_connection()


if __name__ == "__main__":
    asyncio.run(main())