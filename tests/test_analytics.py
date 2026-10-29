
import pytest

from rate_limiter_api.database.mongodb import database
from rate_limiter_api.services.analytics import record_request


@pytest.mark.asyncio(loop_scope="session")
async def test_record_allowed_and_rejected_requests():
    user_id = "analytics_test_user"
    collection = database["request_analytics"]

    await collection.delete_many({"user_id": user_id})

    try:
        await record_request(
            user_id=user_id,
            algorithm="fixed_window",
            allowed=True,
        )
        await record_request(
            user_id=user_id,
            algorithm="fixed_window",
            allowed=False,
        )

        result = await collection.find_one(
            {
                "user_id": user_id,
                "algorithm": "fixed_window",
            }
        )

        assert result is not None
        assert result["total_requests"] == 2
        assert result["allowed_requests"] == 1
        assert result["rejected_requests"] == 1
        assert "created_at" in result
        assert "last_request_at" in result

    finally:
        await collection.delete_many({"user_id": user_id})


@pytest.mark.asyncio(loop_scope="session")
async def test_analytics_are_separated_by_algorithm():
    user_id = "analytics_algorithm_test_user"
    collection = database["request_analytics"]

    await collection.delete_many({"user_id": user_id})

    try:
        await record_request(user_id, "fixed_window", True)
        await record_request(user_id, "token_bucket", False)

        fixed = await collection.find_one(
            {"user_id": user_id, "algorithm": "fixed_window"}
        )
        bucket = await collection.find_one(
            {"user_id": user_id, "algorithm": "token_bucket"}
        )

        assert fixed["allowed_requests"] == 1
        assert bucket["rejected_requests"] == 1

    finally:
        await collection.delete_many({"user_id": user_id})
