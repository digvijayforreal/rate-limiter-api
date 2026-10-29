
from datetime import datetime, timezone

from rate_limiter_api.database.mongodb import database


async def record_request(
    user_id: str,
    algorithm: str,
    allowed: bool,
) -> None:
    """Record one rate-limited request in MongoDB."""

    collection = database["request_analytics"]

    now = datetime.now(timezone.utc)

    await collection.update_one(
        {
            "user_id": user_id,
            "algorithm": algorithm,
        },
        {
            "$inc": {
                "total_requests": 1,
                "allowed_requests": 1 if allowed else 0,
                "rejected_requests": 0 if allowed else 1,
            },
            "$set": {
                "last_request_at": now,
            },
            "$setOnInsert": {
                "created_at": now,
            },
        },
        upsert=True,
    )
