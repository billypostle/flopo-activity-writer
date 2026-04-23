from __future__ import annotations

from typing import Any

import pytest

from app import notion_client


class DummyResponse:
    def __init__(self, status_code: int, body: dict[str, Any]) -> None:
        self.status_code = status_code
        self._body = body
        self.text = str(body)

    def json(self) -> dict[str, Any]:
        return self._body


def test_resolve_parent_target_prefers_explicit_data_source(monkeypatch) -> None:
    monkeypatch.setattr(notion_client, "NOTION_API_KEY", "secret")
    monkeypatch.setattr(notion_client, "NOTION_DATA_SOURCE_ID", "data-source-123")
    monkeypatch.setattr(notion_client, "NOTION_DATABASE_ID", "")

    def fake_get(url: str, *, headers: dict[str, str], timeout: int) -> DummyResponse:
        assert url.endswith("/data_sources/data-source-123")
        assert headers["Notion-Version"] >= notion_client.MIN_DATA_SOURCE_NOTION_VERSION
        return DummyResponse(200, {"id": "data-source-123", "properties": {"Title": {"type": "title"}}})

    monkeypatch.setattr(notion_client.requests, "get", fake_get)

    parent_type, parent_id, body = notion_client._resolve_parent_target()

    assert parent_type == "data_source_id"
    assert parent_id == "data-source-123"
    assert body["properties"]["Title"]["type"] == "title"


def test_resolve_parent_target_accepts_data_source_in_database_id(monkeypatch) -> None:
    monkeypatch.setattr(notion_client, "NOTION_API_KEY", "secret")
    monkeypatch.setattr(notion_client, "NOTION_DATA_SOURCE_ID", "")
    monkeypatch.setattr(notion_client, "NOTION_DATABASE_ID", "data-source-via-legacy-var")

    def fake_get(url: str, *, headers: dict[str, str], timeout: int) -> DummyResponse:
        if url.endswith("/data_sources/data-source-via-legacy-var"):
            return DummyResponse(200, {"id": "data-source-via-legacy-var", "properties": {}})
        raise AssertionError(f"unexpected url: {url}")

    monkeypatch.setattr(notion_client.requests, "get", fake_get)

    parent_type, parent_id, _ = notion_client._resolve_parent_target()

    assert parent_type == "data_source_id"
    assert parent_id == "data-source-via-legacy-var"


def test_resolve_parent_target_resolves_single_child_data_source(monkeypatch) -> None:
    monkeypatch.setattr(notion_client, "NOTION_API_KEY", "secret")
    monkeypatch.setattr(notion_client, "NOTION_DATA_SOURCE_ID", "")
    monkeypatch.setattr(notion_client, "NOTION_DATABASE_ID", "database-123")

    def fake_get(url: str, *, headers: dict[str, str], timeout: int) -> DummyResponse:
        if url.endswith("/data_sources/database-123"):
            return DummyResponse(404, {"code": "object_not_found", "message": "missing"})
        if url.endswith("/databases/database-123"):
            return DummyResponse(
                200,
                {
                    "data_sources": [
                        {"id": "child-data-source-1", "name": "Full Activities"},
                    ]
                },
            )
        if url.endswith("/data_sources/child-data-source-1"):
            return DummyResponse(200, {"id": "child-data-source-1", "properties": {"Title": {"type": "title"}}})
        raise AssertionError(f"unexpected url: {url}")

    monkeypatch.setattr(notion_client.requests, "get", fake_get)

    parent_type, parent_id, body = notion_client._resolve_parent_target()

    assert parent_type == "data_source_id"
    assert parent_id == "child-data-source-1"
    assert body["properties"]["Title"]["type"] == "title"


def test_resolve_parent_target_rejects_multiple_child_data_sources(monkeypatch) -> None:
    monkeypatch.setattr(notion_client, "NOTION_API_KEY", "secret")
    monkeypatch.setattr(notion_client, "NOTION_DATA_SOURCE_ID", "")
    monkeypatch.setattr(notion_client, "NOTION_DATABASE_ID", "database-123")

    def fake_get(url: str, *, headers: dict[str, str], timeout: int) -> DummyResponse:
        if url.endswith("/data_sources/database-123"):
            return DummyResponse(404, {"code": "object_not_found", "message": "missing"})
        if url.endswith("/databases/database-123"):
            return DummyResponse(
                200,
                {
                    "data_sources": [
                        {"id": "ds-1", "name": "Full Activities"},
                        {"id": "ds-2", "name": "Archive"},
                    ]
                },
            )
        raise AssertionError(f"unexpected url: {url}")

    monkeypatch.setattr(notion_client.requests, "get", fake_get)

    with pytest.raises(RuntimeError, match="multiple data sources"):
        notion_client._resolve_parent_target()


def test_create_notion_draft_posts_to_resolved_data_source(monkeypatch) -> None:
    monkeypatch.setattr(notion_client, "NOTION_API_KEY", "secret")
    monkeypatch.setattr(notion_client, "NOTION_DATA_SOURCE_ID", "child-data-source-1")
    monkeypatch.setattr(notion_client, "NOTION_DATABASE_ID", "")
    monkeypatch.setattr(
        notion_client,
        "_load_field_map",
        lambda path=None: {"title_property": "Name", "field_property_map": {}},
    )
    monkeypatch.setattr(
        notion_client,
        "_resolve_parent_target",
        lambda: ("data_source_id", "child-data-source-1", {"properties": {"Name": {"type": "title"}}}),
    )

    def fake_post(url: str, *, headers: dict[str, str], json: dict[str, Any], timeout: int) -> DummyResponse:
        assert url.endswith("/pages")
        assert json["parent"] == {"data_source_id": "child-data-source-1"}
        assert "Name" in json["properties"]
        return DummyResponse(200, {"id": "page-123", "url": "https://notion.so/page-123"})

    monkeypatch.setattr(notion_client.requests, "post", fake_post)

    created = notion_client.create_notion_draft({"Activity Title": "Test activity"})

    assert created["id"] == "page-123"
