from __future__ import annotations

from fastapi.testclient import TestClient

from hawakhata.app import create_app
from hawakhata.config import Settings
from hawakhata.core.errors import UpstreamUnavailableError
from hawakhata.core.middleware import SECURITY_HEADERS


def test_healthz_ok(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_meta_reports_versions_and_fixture_mode_without_keys(client: TestClient) -> None:
    data = client.get("/api/v1/meta").json()["data"]
    assert data["data_mode"] == "fixture"
    assert data["llm_mode"] == "deterministic"
    assert data["prompt_version"] == "v1.0"


def test_every_response_has_security_headers_and_request_id(client: TestClient) -> None:
    response = client.get("/healthz")
    for header, value in SECURITY_HEADERS.items():
        assert response.headers[header] == value
    assert "unsafe-inline" not in response.headers["Content-Security-Policy"]
    assert len(response.headers["X-Request-ID"]) >= 8


def test_hsts_only_over_https(client: TestClient) -> None:
    assert "Strict-Transport-Security" not in client.get("/healthz").headers
    https = client.get("/healthz", headers={"x-forwarded-proto": "https"})
    assert https.headers["Strict-Transport-Security"].startswith("max-age=")


def test_valid_incoming_request_id_is_propagated(client: TestClient) -> None:
    response = client.get("/healthz", headers={"x-request-id": "abc12345XYZ"})
    assert response.headers["X-Request-ID"] == "abc12345XYZ"


def test_unknown_route_uses_error_contract(client: TestClient) -> None:
    body = client.get("/api/v1/nope").json()
    assert body["error"]["code"] == "NOT_FOUND"
    assert body["error"]["request_id"]


def test_oversized_body_rejected_with_413(client: TestClient) -> None:
    response = client.post("/api/v1/meta", content=b"x" * 4096)
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"


def test_rate_limit_returns_429_with_retry_after(client: TestClient) -> None:
    statuses = [client.get("/api/v1/meta").status_code for _ in range(7)]
    assert statuses[-1] == 429
    limited = client.get("/api/v1/meta")
    assert limited.json()["error"]["code"] == "RATE_LIMITED"
    assert int(limited.headers["Retry-After"]) >= 1


def test_app_errors_and_unexpected_errors_follow_contract(settings: Settings) -> None:
    app = create_app(settings)

    @app.get("/api/v1/_boom_app")
    async def boom_app() -> None:
        raise UpstreamUnavailableError("Air data is temporarily unavailable.")

    @app.get("/api/v1/_boom")
    async def boom() -> None:
        raise RuntimeError("secret internal detail")

    with TestClient(app, raise_server_exceptions=False) as test_client:
        app_error = test_client.get("/api/v1/_boom_app")
        assert app_error.status_code == 503
        assert app_error.json()["error"]["retryable"] is True
        unexpected = test_client.get("/api/v1/_boom")
        assert unexpected.status_code == 500
        assert "secret internal detail" not in unexpected.text


def test_validation_errors_follow_contract(settings: Settings) -> None:
    app = create_app(settings)

    @app.get("/api/v1/_needs_int")
    async def needs_int(value: int) -> dict[str, int]:
        return {"value": value}

    with TestClient(app) as test_client:
        response = test_client.get("/api/v1/_needs_int", params={"value": "x"})
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_docs_hidden_in_prod() -> None:
    prod = create_app(Settings(_env_file=None, app_env="prod"))
    with TestClient(prod) as test_client:
        assert test_client.get("/api/docs").status_code == 404
