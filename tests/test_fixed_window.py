
import asyncio
import time

import pytest

from rate_limiter_api.algorithms.fixed_window import check_fixed_window


@pytest.mark.asyncio
async def test_concurrent_requests_respect_limit():
    user_id = f"concurrency_test_{time.time_ns()}"
    limit = 10

    results = await asyncio.gather(
        *[
            check_fixed_window(
                user_id=user_id,
                limit=limit,
                window_seconds=60,
            )
            for _ in range(100)
        ]
    )

    allowed = sum(result["allowed"] for result in results)
    blocked = sum(not result["allowed"] for result in results)

    assert allowed == 10
    assert blocked == 90
