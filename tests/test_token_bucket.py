
import asyncio
import time

import pytest

from rate_limiter_api.algorithms.token_bucket import check_token_bucket


@pytest.mark.asyncio(loop_scope="session")
async def test_bucket_allows_requests_up_to_capacity():
    user_id = f"bucket_test_{time.time_ns()}"

    results = [
        await check_token_bucket(
            user_id=user_id,
            capacity=5,
            refill_rate=1 / 12,
        )
        for _ in range(5)
    ]

    assert all(result["allowed"] for result in results)


@pytest.mark.asyncio(loop_scope="session")
async def test_bucket_blocks_when_empty():
    user_id = f"bucket_test_{time.time_ns()}"

    results = await asyncio.gather(
        *[
            check_token_bucket(
                user_id=user_id,
                capacity=5,
                refill_rate=1 / 12,
            )
            for _ in range(10)
        ]
    )

    allowed = sum(result["allowed"] for result in results)
    blocked = sum(not result["allowed"] for result in results)

    assert allowed == 5
    assert blocked == 5


@pytest.mark.asyncio(loop_scope="session")
async def test_different_users_have_independent_buckets():
    user_a = f"user_a_{time.time_ns()}"
    user_b = f"user_b_{time.time_ns()}"

    result_a = await check_token_bucket(
        user_id=user_a,
        capacity=1,
        refill_rate=1 / 12,
    )
    result_b = await check_token_bucket(
        user_id=user_b,
        capacity=1,
        refill_rate=1 / 12,
    )

    assert result_a["allowed"] is True
    assert result_b["allowed"] is True
