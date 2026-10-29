
import hashlib
import secrets

from fastapi import Header, HTTPException

from rate_limiter_api.database.mongodb import database


def hash_api_key(api_key: str) -> str:
    """Hash an API key before storing it in MongoDB."""
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


async def get_current_user(
    x_api_key: str = Header(..., alias="X-API-Key"),
) -> dict:
    """Validate an API key and return its associated user."""

    if not x_api_key.strip():
        raise HTTPException(
            status_code=401,
            detail="API key is required.",
        )

    key_hash = hash_api_key(x_api_key)

    user = await database["users"].find_one(
        {
            "api_key_hash": key_hash,
            "active": True,
        }
    )

    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid or inactive API key.",
        )

    return {
        "user_id": user["user_id"],
        "role": user.get("role", "user"),
    }


def generate_api_key() -> str:
    """Generate a cryptographically secure API key."""
    return secrets.token_urlsafe(32)
