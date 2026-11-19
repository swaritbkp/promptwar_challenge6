from __future__ import annotations

from fastapi.testclient import TestClient

from hawakhata.core.middleware import SECURITY_HEADERS


def test_healthz_ok(client: TestClient) -> None:
    resp = client.get("/healthz")
    assert resp.status_code == 200 and resp.json() == {"status": "ok"}


def test_meta_reports_versions_and_fixture_mode_without_keys(client: TestClient) -> None:
    data = client.get("/api/v1/meta").json()["data"]
    assert (
        data["data_mode"] == "fixture"
        and data["llm_mode"] == "deterministic"
        and data["prompt_version"] == "v1.0"
    )


def test_every_response_has_security_headers_and_request_id(client: TestClient) -> None:
    resp = client.get("/healthz")
    for header, value in SECURITY_HEADERS.items():
        assert resp.headers[header] == value
    assert "unsafe-inline" not in resp.headers["Content-Security-Policy"]
    assert len(resp.headers["X-Request-ID"]) >= 8


def test_hsts_only_over_https(client: TestClient) -> None:
    assert "Strict-Transport-Security" not in client.get("/healthz").headers
    https = client.get("/healthz", headers={"x-forwarded-proto": "https"})
    assert https.headers["Strict-Transport-Security"].startswith("max-age=")


def test_valid_incoming_request_id_is_propagated(client: TestClient) -> None:
    resp = client.get("/healthz", headers={"x-request-id": "abc12345XYZ"})
    assert resp.headers["X-Request-ID"] == "abc12345XYZ"


def test_unknown_route_uses_error_contract(client: TestClient) -> None:
    body = client.get("/api/v1/nope").json()
    assert body["error"]["code"] == "NOT_FOUND" and body["error"]["request_id"]


def test_oversized_body_rejected_with_413(client: TestClient) -> None:
    resp = client.post("/api/v1/meta", content=b"x" * 4096)
    assert resp.status_code == 413 and resp.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"


def test_rate_limit_returns_429_with_retry_after(client: TestClient) -> None:
    assert [client.get("/api/v1/meta").status_code for _ in range(7)][-1] == 429
    lim = client.get("/api/v1/meta")
    assert lim.json()["error"]["code"] == "RATE_LIMITED" and int(lim.headers["Retry-After"]) >= 1
