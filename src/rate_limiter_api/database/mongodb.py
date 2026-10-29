
from pymongo import AsyncMongoClient

from rate_limiter_api.config import settings


client = AsyncMongoClient(settings.mongodb_uri)

database = client[settings.mongodb_database]


async def connect_to_mongodb() -> None:
    """Verify that MongoDB is reachable."""
    await client.admin.command("ping")
    print("Connected to MongoDB successfully!")


async def close_mongodb_connection() -> None:
    """Close the MongoDB connection."""
    await client.close()
