
import asyncio
import uuid

import pytest

from rate_limiter_api.services.concurrency_limiter import (
    acquire_request_slot,
    release_request_slot,
)
from rate_limiter_api.database.mongodb import database


@pytest.fixture
def unique_user_id():
    return f"concurrency_test_{uuid.uuid4().hex}"


@pytest.mark.asyncio(loop_scope="session")
async def test_concurrency_limit_blocks_extra_requests(unique_user_id):
    first = await acquire_request_slot(unique_user_id, max_concurrent=2)
    second = await acquire_request_slot(unique_user_id, max_concurrent=2)
    third = await acquire_request_slot(unique_user_id, max_concurrent=2)

    try:
        assert first is not None
        assert second is not None
        assert third is None
    finally:
        for request_id in (first, second):
            if request_id is not None:
                await release_request_slot(unique_user_id, request_id)

        await database["active_requests"].delete_one({"_id": unique_user_id})


@pytest.mark.asyncio(loop_scope="session")
async def test_releasing_slot_allows_another_request(unique_user_id):
    first = await acquire_request_slot(unique_user_id, max_concurrent=1)

    try:
        assert first is not None

        blocked = await acquire_request_slot(unique_user_id, max_concurrent=1)
        assert blocked is None

        await release_request_slot(unique_user_id, first)

        next_request = await acquire_request_slot(
            unique_user_id,
            max_concurrent=1,
        )
        assert next_request is not None

        await release_request_slot(unique_user_id, next_request)
    finally:
        await database["active_requests"].delete_one({"_id": unique_user_id})


@pytest.mark.asyncio(loop_scope="session")
async def test_users_have_independent_concurrency_limits(unique_user_id):
    other_user = f"concurrency_test_{uuid.uuid4().hex}"

    first = await acquire_request_slot(unique_user_id, max_concurrent=1)

    try:
        other = await acquire_request_slot(other_user, max_concurrent=1)

        assert first is not None
        assert other is not None

        await release_request_slot(other_user, other)
    finally:
        if first is not None:
            await release_request_slot(unique_user_id, first)

        await database["active_requests"].delete_many(
            {"_id": {"$in": [unique_user_id, other_user]}}
        )
