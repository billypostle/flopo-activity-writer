import base64

from fastapi.testclient import TestClient

from app import main


def _auth_header(username: str, password: str) -> dict[str, str]:
    token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {token}"}


def test_healthz_allows_unauthenticated_access(monkeypatch):
    monkeypatch.setattr(main, "validate_notion_configuration", lambda: (True, "Notion ready"))
    monkeypatch.setattr(main.config, "APP_AUTH_USERNAME", "charlotte")
    monkeypatch.setattr(main.config, "APP_AUTH_PASSWORD", "secret")

    with TestClient(main.app) as client:
        response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_home_requires_auth_when_credentials_configured(monkeypatch):
    monkeypatch.setattr(main, "validate_notion_configuration", lambda: (True, "Notion ready"))
    monkeypatch.setattr(main.config, "APP_AUTH_USERNAME", "charlotte")
    monkeypatch.setattr(main.config, "APP_AUTH_PASSWORD", "secret")

    with TestClient(main.app) as client:
        response = client.get("/")

    assert response.status_code == 401
    assert response.headers["www-authenticate"].startswith("Basic")


def test_protected_route_allows_valid_auth(monkeypatch):
    monkeypatch.setattr(main, "validate_notion_configuration", lambda: (True, "Notion ready"))
    monkeypatch.setattr(main.config, "APP_AUTH_USERNAME", "charlotte")
    monkeypatch.setattr(main.config, "APP_AUTH_PASSWORD", "secret")

    with TestClient(main.app) as client:
        response = client.get("/api/resources", headers=_auth_header("charlotte", "secret"))

    assert response.status_code == 200
    assert "content_fields" in response.json()


def test_removed_endpoints_return_404(monkeypatch):
    monkeypatch.setattr(main, "validate_notion_configuration", lambda: (True, "Notion ready"))
    monkeypatch.setattr(main.config, "APP_AUTH_USERNAME", "charlotte")
    monkeypatch.setattr(main.config, "APP_AUTH_PASSWORD", "secret")
    headers = _auth_header("charlotte", "secret")

    with TestClient(main.app) as client:
        save_response = client.post("/api/save-local", json={"activity_draft": {}}, headers=headers)
        combined_response = client.post(
            "/api/publish/notion-webflow-draft",
            json={"activity_draft": {}},
            headers=headers,
        )

    assert save_response.status_code == 404
    assert combined_response.status_code == 404


def test_security_headers_set(monkeypatch):
    monkeypatch.setattr(main, "validate_notion_configuration", lambda: (True, "Notion ready"))
    monkeypatch.setattr(main.config, "APP_AUTH_USERNAME", "")
    monkeypatch.setattr(main.config, "APP_AUTH_PASSWORD", "")

    with TestClient(main.app) as client:
        response = client.get("/healthz")

    assert "frame-ancestors https://flopo.co.uk https://*.flopo.co.uk" in response.headers[
        "content-security-policy"
    ]
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["x-content-type-options"] == "nosniff"
