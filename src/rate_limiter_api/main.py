
from contextlib import asynccontextmanager

from fastapi import FastAPI

from rate_limiter_api.database.mongodb import (
    connect_to_mongodb,
    close_mongodb_connection,
    database,
)
from rate_limiter_api.database.redis_client import (
    connect_to_redis,
    close_redis_connection,
)
from rate_limiter_api.routes.data import router as data_router
from rate_limiter_api.routes.admin import (
    router as admin_router,
    config_router,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_to_mongodb()
    await connect_to_redis()

    try:
        users_collection = database["users"]

        await users_collection.create_index(
            "user_id",
            unique=True,
        )

        await users_collection.create_index(
            "api_key_hash",
            unique=True,
        )

        yield

    finally:
        await close_redis_connection()
        await close_mongodb_connection()


app = FastAPI(
    title="Rate Limiter API",
    lifespan=lifespan,
)

app.include_router(data_router)
app.include_router(admin_router)
app.include_router(config_router)


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
