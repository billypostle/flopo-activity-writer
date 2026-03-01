import json
from pathlib import Path

from app import spec_manager


def test_get_model_spec_uses_fresh_cache(monkeypatch, tmp_path: Path):
    cache_path = tmp_path / "model_spec.json"
    cached = {
        "spec_version": "1.0.0",
        "spec_text": "cached spec",
        "spec_hash": "abc",
        "fetched_at": 9999999999.0,
        "source": "https://www.notion.so/spec",
    }
    cache_path.write_text(json.dumps(cached), encoding="utf-8")

    monkeypatch.setattr(spec_manager, "FLOPO_MODEL_SPEC_URL", "https://www.notion.so/spec")
    monkeypatch.setattr(spec_manager, "FLOPO_MODEL_SPEC_VERSION", "1.0.0")
    monkeypatch.setattr(spec_manager, "FLOPO_MODEL_SPEC_CACHE_PATH", cache_path)
    monkeypatch.setattr(spec_manager, "FLOPO_MODEL_SPEC_REFRESH_SECONDS", 3600)
    monkeypatch.setattr(
        spec_manager,
        "fetch_notion_page_markdown",
        lambda _ref: (_ for _ in ()).throw(RuntimeError("should not fetch")),
    )

    payload = spec_manager.get_model_spec()
    assert payload["spec_text"] == "cached spec"


def test_get_model_spec_fetches_and_caches_when_missing(monkeypatch, tmp_path: Path):
    cache_path = tmp_path / "model_spec.json"
    source_url = "https://www.notion.so/spec"

    monkeypatch.setattr(spec_manager, "FLOPO_MODEL_SPEC_URL", source_url)
    monkeypatch.setattr(spec_manager, "FLOPO_MODEL_SPEC_VERSION", "1.0.0")
    monkeypatch.setattr(spec_manager, "FLOPO_MODEL_SPEC_CACHE_PATH", cache_path)
    monkeypatch.setattr(spec_manager, "FLOPO_MODEL_SPEC_REFRESH_SECONDS", 3600)
    monkeypatch.setattr(spec_manager, "fetch_notion_page_markdown", lambda _ref: "fresh spec")

    payload = spec_manager.get_model_spec()
    assert payload["spec_version"] == "1.0.0"
    assert payload["source"] == source_url
    assert payload["spec_text"] == "fresh spec"
    assert cache_path.exists()


def test_get_model_spec_warns_on_hash_drift(monkeypatch, tmp_path: Path, caplog):
    cache_path = tmp_path / "model_spec.json"
    source_url = "https://www.notion.so/spec"
    cached = {
        "spec_version": "1.0.0",
        "spec_text": "old spec",
        "spec_hash": spec_manager.hash_text("old spec"),
        "fetched_at": 0.0,
        "source": source_url,
    }
    spec_manager.save_cached_spec(cached, path=cache_path)

    monkeypatch.setattr(spec_manager, "FLOPO_MODEL_SPEC_URL", source_url)
    monkeypatch.setattr(spec_manager, "FLOPO_MODEL_SPEC_VERSION", "1.0.0")
    monkeypatch.setattr(spec_manager, "FLOPO_MODEL_SPEC_CACHE_PATH", cache_path)
    monkeypatch.setattr(spec_manager, "FLOPO_MODEL_SPEC_REFRESH_SECONDS", 0)
    monkeypatch.setattr(spec_manager, "fetch_notion_page_markdown", lambda _ref: "new spec")

    payload = spec_manager.get_model_spec()
    assert payload["spec_hash"] == spec_manager.hash_text("new spec")
    assert "Model spec content changed; bump FLOPO_MODEL_SPEC_VERSION" in caplog.text
