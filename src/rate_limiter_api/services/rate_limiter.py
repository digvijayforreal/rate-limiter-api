
from rate_limiter_api.algorithms.fixed_window import check_fixed_window
from rate_limiter_api.algorithms.token_bucket import check_token_bucket


async def check_rate_limit(
    user_id: str,
    algorithm: str = "fixed_window",
    limit: int = 10,
    window_seconds: int = 60,
) -> dict:
    """Select and execute the requested rate-limiting algorithm."""

    if algorithm == "fixed_window":
        return await check_fixed_window(
            user_id=user_id,
            limit=limit,
            window_seconds=window_seconds,
        )

    if algorithm == "token_bucket":
        return await check_token_bucket(
            user_id=user_id,
            capacity=limit,
            refill_rate=1 / window_seconds,
        )

    raise ValueError(
        "Unsupported algorithm. Use 'fixed_window' or 'token_bucket'."
    )
