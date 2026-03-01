import json

from app import webflow_client


class _DummyResponse:
    def __init__(self, status_code=200, json_body=None, text=""):
        self.status_code = status_code
        self._json_body = json_body if json_body is not None else {}
        self.text = text

    def json(self):
        return self._json_body


def test_load_field_map_falls_back_to_example(tmp_path):
    primary = tmp_path / "webflow_field_map.json"
    example = tmp_path / "webflow_field_map.example.json"
    example.write_text(
        json.dumps({"name_field_slug": "name", "slug_field_slug": "slug", "field_slug_map": {}}),
        encoding="utf-8",
    )

    loaded = webflow_client._load_field_map(primary)
    assert loaded["name_field_slug"] == "name"
    assert loaded["slug_field_slug"] == "slug"


def test_slugify_handles_spaces_symbols_and_empty():
    assert webflow_client._slugify("Sorting & Counting Snowballs!") == "sorting-counting-snowballs"
    assert webflow_client._slugify("") == "untitled-activity"


def test_resolve_collection_and_locales_reads_csv_defaults(monkeypatch, tmp_path):
    csv_path = tmp_path / "activities.csv"
    csv_path.write_text(
        "Activity Title,Collection ID,Locale ID\nDemo,coll_123,loc_456\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(webflow_client, "WEBFLOW_COLLECTION_ID", "")
    monkeypatch.setattr(webflow_client, "WEBFLOW_CMS_LOCALE_IDS", [])

    collection_id, locale_ids = webflow_client._resolve_collection_and_locales(csv_path)
    assert collection_id == "coll_123"
    assert locale_ids == ["loc_456"]


def test_format_webflow_error_uses_code_and_message():
    response = _DummyResponse(
        status_code=400,
        json_body={"code": "validation_error", "message": "Invalid field value"},
    )
    message = webflow_client._format_webflow_error(response)
    assert "Webflow API 400" in message
    assert "validation_error" in message
    assert "Invalid field value" in message


def test_create_webflow_draft_builds_expected_payload(monkeypatch):
    captured = {}

    def fake_post(url, headers, json, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout
        return _DummyResponse(
            status_code=200,
            json_body={"items": [{"id": "wf_item_1"}]},
        )

    monkeypatch.setattr(webflow_client, "WEBFLOW_API_TOKEN", "token_123")
    monkeypatch.setattr(webflow_client, "WEBFLOW_API_BASE_URL", "https://api.webflow.com")
    monkeypatch.setattr(webflow_client, "_resolve_collection_and_locales", lambda: ("coll_123", ["loc_456"]))
    monkeypatch.setattr(
        webflow_client,
        "_load_field_map",
        lambda: {
            "name_field_slug": "name",
            "slug_field_slug": "slug",
            "field_slug_map": {"Activity Summary": "activity-summary"},
            "allow_empty_fields": [],
        },
    )
    monkeypatch.setattr(webflow_client.requests, "post", fake_post)

    result = webflow_client.create_webflow_draft(
        {
            "Activity Title": "Sorting and counting foam snowballs by size",
            "Activity Summary": "Children sort objects by size and count.",
        }
    )

    assert captured["url"] == "https://api.webflow.com/v2/collections/coll_123/items/bulk"
    assert captured["json"]["isDraft"] is True
    assert captured["json"]["isArchived"] is False
    assert captured["json"]["cmsLocaleIds"] == ["loc_456"]
    assert captured["json"]["fieldData"]["name"] == "Sorting and counting foam snowballs by size"
    assert captured["json"]["fieldData"]["slug"] == "sorting-and-counting-foam-snowballs-by-size"
    assert captured["json"]["fieldData"]["activity-summary"] == "Children sort objects by size and count."
    assert result["id"] == "wf_item_1"
