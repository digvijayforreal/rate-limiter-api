
from typing import Literal

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError

from rate_limiter_api.config import settings
from rate_limiter_api.database.mongodb import database
from rate_limiter_api.services.auth import generate_api_key, hash_api_key


router = APIRouter(prefix="/admin", tags=["Admin"])
config_router = APIRouter(prefix="/api", tags=["Rate Limit Configuration"])


class RateLimitConfig(BaseModel):
    user_id: str = Field(min_length=1, max_length=100)
    algorithm: Literal["fixed_window", "token_bucket"] = "fixed_window"
    limit: int = Field(default=10, ge=1, le=10000)
    window_seconds: int = Field(default=60, ge=1, le=86400)


@config_router.post("/config")
async def configure_rate_limit(
    config: RateLimitConfig,
    x_admin_key: str = Header(..., alias="X-Admin-Key"),
):
    """Configure a user's rate limit. Admin access is required."""

    if x_admin_key != settings.admin_api_key:
        raise HTTPException(
            status_code=401,
            detail="Invalid admin API key.",
        )

    user_id = config.user_id.strip()

    if not user_id:
        raise HTTPException(
            status_code=422,
            detail="User ID cannot be empty.",
        )

    user = await database["users"].find_one({"user_id": user_id})

    if user is None:
        raise HTTPException(
            status_code=404,
            detail="User not found.",
        )

    configuration = {
        "algorithm": config.algorithm,
        "limit": config.limit,
        "window_seconds": config.window_seconds,
    }

    await database["users"].update_one(
        {"user_id": user_id},
        {"$set": {"rate_limit": configuration}},
    )

    return {
        "message": "Rate limit configuration updated.",
        "user_id": user_id,
        "rate_limit": configuration,
    }


@router.post("/users", status_code=201)
async def create_user(
    user_id: str,
    x_admin_key: str = Header(..., alias="X-Admin-Key"),
):
    """Create a user and issue an API key."""

    if x_admin_key != settings.admin_api_key:
        raise HTTPException(
            status_code=401,
            detail="Invalid admin API key.",
        )

    user_id = user_id.strip()

    if not user_id:
        raise HTTPException(
            status_code=400,
            detail="User ID cannot be empty.",
        )

    api_key = generate_api_key()

    user_document = {
        "user_id": user_id,
        "api_key_hash": hash_api_key(api_key),
        "active": True,
        "role": "user",
        "rate_limit": {
            "algorithm": "fixed_window",
            "limit": 10,
            "window_seconds": 60,
        },
    }

    try:
        await database["users"].insert_one(user_document)
    except DuplicateKeyError:
        raise HTTPException(
            status_code=409,
            detail="User ID already exists.",
        )

    return {
        "message": "User created successfully.",
        "user_id": user_id,
        "api_key": api_key,
        "warning": "Save this API key now. It will not be returned again.",
    }


@router.put("/users/{user_id}/rate-limit")
async def update_user_rate_limit(
    user_id: str,
    algorithm: Literal["fixed_window", "token_bucket"] = Query(
        default="fixed_window"
    ),
    limit: int = Query(default=10, ge=1, le=10000),
    window_seconds: int = Query(default=60, ge=1, le=86400),
    x_admin_key: str = Header(..., alias="X-Admin-Key"),
):
    """Update a user's rate-limit configuration. Admin access is required."""

    if x_admin_key != settings.admin_api_key:
        raise HTTPException(
            status_code=401,
            detail="Invalid admin API key.",
        )

    user = await database["users"].find_one({"user_id": user_id})

    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")

    configuration = {
        "algorithm": algorithm,
        "limit": limit,
        "window_seconds": window_seconds,
    }

    await database["users"].update_one(
        {"user_id": user_id},
        {"$set": {"rate_limit": configuration}},
    )

    return {
        "message": "Rate limit configuration updated.",
        "user_id": user_id,
        "rate_limit": configuration,
    }


@router.get("/analytics")
async def get_request_analytics(
    user_id: str | None = Query(default=None),
    x_admin_key: str = Header(..., alias="X-Admin-Key"),
):
    """Return request analytics. Admin access is required."""

    if x_admin_key != settings.admin_api_key:
        raise HTTPException(
            status_code=401,
            detail="Invalid admin API key.",
        )

    collection = database["request_analytics"]

    query = {}
    if user_id:
        query["user_id"] = user_id

    cursor = collection.find(query, {"_id": 0}).sort(
        "last_request_at", -1
    )

    records = await cursor.to_list(length=1000)

    totals = {
        "total_requests": sum(
            record.get("total_requests", 0) for record in records
        ),
        "allowed_requests": sum(
            record.get("allowed_requests", 0) for record in records
        ),
        "rejected_requests": sum(
            record.get("rejected_requests", 0) for record in records
        ),
    }

    return {
        "count": len(records),
        "totals": totals,
        "analytics": records,
    }
