
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from rate_limiter_api.main import app


@pytest.fixture
def client():
    test_client = TestClient(app)
    yield test_client
    test_client.close()


def test_health_endpoint(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_data_rejects_missing_api_key(client):
    response = client.get("/api/data")

    assert response.status_code == 422


def test_data_rejects_invalid_api_key(client):
    with patch(
        "rate_limiter_api.services.auth.database"
    ) as mock_database:
        mock_database["users"].find_one = AsyncMock(return_value=None)

        response = client.get(
            "/api/data",
            headers={"X-API-Key": "invalid-test-key"},
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or inactive API key."



def test_data_rejects_when_concurrency_limit_is_reached(client):
    from unittest.mock import AsyncMock, patch

    from rate_limiter_api.services.auth import get_current_user

    app.dependency_overrides[get_current_user] = lambda: {
        "user_id": "api_concurrency_test_user",
        "role": "user",
    }

    try:
        with (
            patch("rate_limiter_api.routes.data.database") as mock_database,
            patch(
                "rate_limiter_api.routes.data.acquire_request_slot",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            mock_database["users"].find_one = AsyncMock(
                return_value={
                    "rate_limit": {
                        "algorithm": "fixed_window",
                        "limit": 10,
                        "window_seconds": 60,
                    },
                    "max_concurrent": 1,
                }
            )

            response = client.get("/api/data")

        assert response.status_code == 429
        assert response.json()["detail"] == (
            "Too many concurrent requests. Try again later."
        )
        assert response.headers["Retry-After"] == "1"

    finally:
        app.dependency_overrides.clear()


def test_analytics_rejects_invalid_admin_key(client):
    response = client.get(
        "/admin/analytics",
        headers={"X-Admin-Key": "invalid-test-key"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid admin API key."


def test_analytics_returns_totals(client):
    from unittest.mock import AsyncMock, patch

    with patch(
        "rate_limiter_api.routes.admin.settings"
    ) as mock_settings, patch(
        "rate_limiter_api.routes.admin.database"
    ) as mock_database:
        mock_settings.admin_api_key = "test-admin-key"

        mock_cursor = mock_database["request_analytics"].find.return_value
        mock_cursor.sort.return_value.to_list = AsyncMock(
            return_value=[
                {
                    "user_id": "test-user",
                    "algorithm": "fixed_window",
                    "total_requests": 5,
                    "allowed_requests": 4,
                    "rejected_requests": 1,
                }
            ]
        )

        response = client.get(
            "/admin/analytics",
            headers={"X-Admin-Key": "test-admin-key"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["totals"]["total_requests"] == 5
    assert body["totals"]["allowed_requests"] == 4
    assert body["totals"]["rejected_requests"] == 1


def test_config_updates_user_rate_limit(client):
    with (
        patch("rate_limiter_api.routes.admin.settings") as mock_settings,
        patch("rate_limiter_api.routes.admin.database") as mock_database,
    ):
        mock_settings.admin_api_key = "test-admin-key"

        mock_database["users"].find_one = AsyncMock(
            return_value={"user_id": "test-user"}
        )
        mock_database["users"].update_one = AsyncMock()

        response = client.post(
            "/api/config",
            headers={"X-Admin-Key": "test-admin-key"},
            json={
                "user_id": "test-user",
                "algorithm": "token_bucket",
                "limit": 5,
                "window_seconds": 30,
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == "test-user"
    assert body["rate_limit"] == {
        "algorithm": "token_bucket",
        "limit": 5,
        "window_seconds": 30,
    }

    mock_database["users"].update_one.assert_awaited_once_with(
        {"user_id": "test-user"},
        {
            "$set": {
                "rate_limit": {
                    "algorithm": "token_bucket",
                    "limit": 5,
                    "window_seconds": 30,
                }
            }
        },
    )


def test_config_rejects_invalid_admin_key(client):
    with patch(
        "rate_limiter_api.routes.admin.settings"
    ) as mock_settings:
        mock_settings.admin_api_key = "correct-admin-key"

        response = client.post(
            "/api/config",
            headers={"X-Admin-Key": "wrong-admin-key"},
            json={
                "user_id": "test-user",
                "algorithm": "fixed_window",
                "limit": 10,
                "window_seconds": 60,
            },
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid admin API key."


def test_config_rejects_unknown_user(client):
    with (
        patch("rate_limiter_api.routes.admin.settings") as mock_settings,
        patch("rate_limiter_api.routes.admin.database") as mock_database,
    ):
        mock_settings.admin_api_key = "test-admin-key"
        mock_database["users"].find_one = AsyncMock(return_value=None)

        response = client.post(
            "/api/config",
            headers={"X-Admin-Key": "test-admin-key"},
            json={
                "user_id": "unknown-user",
                "algorithm": "fixed_window",
                "limit": 10,
                "window_seconds": 60,
            },
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "User not found."


def test_data_includes_rate_limit_headers(client):
    from rate_limiter_api.services.auth import get_current_user

    app.dependency_overrides[get_current_user] = lambda: {
        "user_id": "header-test-user",
        "role": "user",
    }

    try:
        with (
            patch("rate_limiter_api.routes.data.database") as mock_database,
            patch(
                "rate_limiter_api.routes.data.acquire_request_slot",
                new_callable=AsyncMock,
                return_value="test-request-id",
            ),
            patch(
                "rate_limiter_api.routes.data.release_request_slot",
                new_callable=AsyncMock,
            ),
            patch(
                "rate_limiter_api.routes.data.check_rate_limit",
                new_callable=AsyncMock,
                return_value={
                    "allowed": True,
                    "limit": 10,
                    "remaining": 7,
                    "retry_after": 0,
                },
            ),
            patch(
                "rate_limiter_api.routes.data.record_request",
                new_callable=AsyncMock,
            ),
        ):
            mock_database["users"].find_one = AsyncMock(
                return_value={
                    "rate_limit": {
                        "algorithm": "fixed_window",
                        "limit": 10,
                        "window_seconds": 60,
                    },
                    "max_concurrent": 2,
                }
            )

            response = client.get("/api/data")

        assert response.status_code == 200
        assert response.headers["X-RateLimit-Limit"] == "10"
        assert response.headers["X-RateLimit-Remaining"] == "7"

    finally:
        app.dependency_overrides.clear()


def test_data_rate_limit_exceeded_returns_headers(client):
    from rate_limiter_api.services.auth import get_current_user

    app.dependency_overrides[get_current_user] = lambda: {
        "user_id": "blocked-test-user",
        "role": "user",
    }

    try:
        with (
            patch("rate_limiter_api.routes.data.database") as mock_database,
            patch(
                "rate_limiter_api.routes.data.acquire_request_slot",
                new_callable=AsyncMock,
                return_value="test-request-id",
            ),
            patch(
                "rate_limiter_api.routes.data.release_request_slot",
                new_callable=AsyncMock,
            ),
            patch(
                "rate_limiter_api.routes.data.check_rate_limit",
                new_callable=AsyncMock,
                return_value={
                    "allowed": False,
                    "limit": 10,
                    "remaining": 0,
                    "retry_after": 12,
                },
            ),
            patch(
                "rate_limiter_api.routes.data.record_request",
                new_callable=AsyncMock,
            ),
        ):
            mock_database["users"].find_one = AsyncMock(
                return_value={
                    "rate_limit": {
                        "algorithm": "fixed_window",
                        "limit": 10,
                        "window_seconds": 60,
                    },
                    "max_concurrent": 2,
                }
            )

            response = client.get("/api/data")

        assert response.status_code == 429
        assert response.headers["X-RateLimit-Limit"] == "10"
        assert response.headers["X-RateLimit-Remaining"] == "0"
        assert response.headers["Retry-After"] == "12"

    finally:
        app.dependency_overrides.clear()
