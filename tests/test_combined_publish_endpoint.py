from fastapi.testclient import TestClient

from app import main


def _make_client(monkeypatch, notion_ready=True, webflow_ready=True):
    monkeypatch.setattr(
        main,
        "validate_notion_configuration",
        lambda: (notion_ready, "Notion ready" if notion_ready else "Notion not ready"),
    )
    monkeypatch.setattr(
        main,
        "validate_webflow_configuration",
        lambda: (webflow_ready, "Webflow ready" if webflow_ready else "Webflow not ready"),
    )
    return TestClient(main.app)


def test_combined_publish_success(monkeypatch):
    monkeypatch.setattr(main, "create_notion_draft", lambda draft: {"id": "notion_1", "url": "https://notion.page/1"})
    monkeypatch.setattr(
        main,
        "create_webflow_draft",
        lambda draft: {
            "id": "wf_1",
            "collection_id": "coll_1",
            "cms_locale_ids": ["loc_1"],
            "is_draft": True,
            "is_archived": False,
            "created": True,
        },
    )

    with _make_client(monkeypatch, notion_ready=True, webflow_ready=True) as client:
        response = client.post(
            "/api/publish/notion-webflow-draft",
            json={"activity_draft": {"Activity Title": "Demo Activity"}},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["notion"]["created"] is True
    assert body["notion"]["id"] == "notion_1"
    assert body["webflow"]["created"] is True
    assert body["webflow"]["id"] == "wf_1"
    assert body["errors"] == []


def test_combined_publish_partial_failure_returns_notion_details(monkeypatch):
    monkeypatch.setattr(main, "create_notion_draft", lambda draft: {"id": "notion_2", "url": "https://notion.page/2"})

    def raise_webflow_error(_draft):
        raise RuntimeError("Webflow API 400 (validation_error): Invalid field value")

    monkeypatch.setattr(main, "create_webflow_draft", raise_webflow_error)

    with _make_client(monkeypatch, notion_ready=True, webflow_ready=True) as client:
        response = client.post(
            "/api/publish/notion-webflow-draft",
            json={"activity_draft": {"Activity Title": "Demo Activity"}},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["notion"]["created"] is True
    assert body["notion"]["url"] == "https://notion.page/2"
    assert body["webflow"]["created"] is False
    assert body["errors"]
    assert "Webflow draft creation failed after Notion success" in body["errors"][0]


def test_combined_publish_readiness_failure(monkeypatch):
    with _make_client(monkeypatch, notion_ready=True, webflow_ready=False) as client:
        response = client.post(
            "/api/publish/notion-webflow-draft",
            json={"activity_draft": {"Activity Title": "Demo Activity"}},
        )

    assert response.status_code == 400
    assert "Webflow startup verification failed" in response.json()["detail"]
