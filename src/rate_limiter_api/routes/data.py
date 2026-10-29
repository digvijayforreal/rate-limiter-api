import time

from rate_limiter_api.database.redis_client import redis_client


from fastapi import APIRouter, Depends, HTTPException, Response

from rate_limiter_api.database.mongodb import database
from rate_limiter_api.services.auth import get_current_user
from rate_limiter_api.services.concurrency_limiter import (
    acquire_request_slot,
    release_request_slot,
)
from rate_limiter_api.services.rate_limiter import check_rate_limit
from rate_limiter_api.services.analytics import record_request
router = APIRouter(prefix="/api", tags=["Rate Limited API"])


@router.get("/data")
async def get_data(
    response: Response,
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user["user_id"]

    user = await database["users"].find_one(
        {"user_id": user_id},
        {"rate_limit": 1, "max_concurrent": 1, "_id": 0},
    )

    if user is None:
        raise HTTPException(status_code=401, detail="User not found.")

    config = user.get(
        "rate_limit",
        {
            "algorithm": "fixed_window",
            "limit": 10,
            "window_seconds": 60,
        },
    )

    max_concurrent = user.get("max_concurrent", 2)

    request_id = await acquire_request_slot(
        user_id=user_id,
        max_concurrent=max_concurrent,
    )

    if request_id is None:
        raise HTTPException(
            status_code=429,
            detail="Too many concurrent requests. Try again later.",
            headers={"Retry-After": "1"},
        )

    try:
        result = await check_rate_limit(
            user_id=user_id,
            algorithm=config["algorithm"],
            limit=config["limit"],
            window_seconds=config["window_seconds"],
        )

        await record_request(
            user_id=user_id,
            algorithm=config["algorithm"],
            allowed=result["allowed"],
        )

        response.headers["X-RateLimit-Limit"] = str(result["limit"])
        response.headers["X-RateLimit-Remaining"] = str(result["remaining"])

        if not result["allowed"]:
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded. Try again later.",
                headers={
                    "X-RateLimit-Limit": str(result["limit"]),
                    "X-RateLimit-Remaining": str(result["remaining"]),
                    "Retry-After": str(result["retry_after"]),
                },
            )

        return {
            "message": "Request allowed",
            "user_id": user_id,
            "algorithm": config["algorithm"],
            "data": {"example": "This is protected API data."},
            "rate_limit": result,
        }
    finally:
        await release_request_slot(user_id, request_id)


@router.get("/status")
async def get_rate_limit_status(
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user["user_id"]

    user = await database["users"].find_one(
        {"user_id": user_id},
        {"rate_limit": 1, "_id": 0},
    )

    if user is None:
        raise HTTPException(
            status_code=404,
            detail="User not found.",
        )

    config = user.get(
        "rate_limit",
        {
            "algorithm": "fixed_window",
            "limit": 10,
            "window_seconds": 60,
        },
    )

    algorithm = config["algorithm"]
    limit = config["limit"]
    window_seconds = config["window_seconds"]
    now = time.time()

    if algorithm == "fixed_window":
        window_id = int(now // window_seconds)
        key = f"rate_limit:fixed:{user_id}:{window_id}"

        count = int(await redis_client.get(key) or 0)
        remaining = max(0, limit - count)

        retry_after = (
            max(1, int((window_id + 1) * window_seconds - now + 0.999))
            if remaining == 0
            else 0
        )

    elif algorithm == "token_bucket":
        key = f"rate_limit:bucket:{user_id}"

        values = await redis_client.hmget(
            key,
            "tokens",
            "updated_at",
        )

        if values[0] is None or values[1] is None:
            tokens = float(limit)
        else:
            tokens = min(
                float(limit),
                float(values[0])
                + max(0, now - float(values[1])) / window_seconds,
            )

        remaining = int(tokens)
        retry_after = (
            max(1, int((1 - tokens) * window_seconds + 0.999))
            if tokens < 1
            else 0
        )

    else:
        raise HTTPException(
            status_code=500,
            detail="Unsupported rate-limit algorithm.",
        )

    return {
        "user_id": user_id,
        "algorithm": algorithm,
        "limit": limit,
        "remaining_requests": remaining,
        "retry_after": retry_after,
    }