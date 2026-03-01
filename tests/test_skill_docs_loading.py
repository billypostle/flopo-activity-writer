from pathlib import Path

from app import resources


def test_load_skill_docs_local_mode_reads_local_files(monkeypatch, tmp_path: Path):
    doc_name = "Writing guide.md"
    doc_path = tmp_path / doc_name
    doc_path.write_text("local guide content", encoding="utf-8")

    monkeypatch.setattr(resources, "INCLUDED_SKILL_DOCS", [doc_name])
    monkeypatch.setattr(resources, "SKILL_DOCS_DIR", tmp_path)
    monkeypatch.setattr(resources, "NOTION_SKILL_DOCS_MODE", "local")

    docs = resources.load_skill_docs()
    assert docs[doc_name] == "local guide content"


def test_load_skill_docs_live_mode_uses_notion(monkeypatch):
    doc_name = "Writing guide.md"
    monkeypatch.setattr(resources, "INCLUDED_SKILL_DOCS", [doc_name])
    monkeypatch.setattr(resources, "NOTION_SKILL_DOCS_MODE", "live")
    monkeypatch.setattr(resources, "_local_skill_docs", lambda _doc_names=None: {doc_name: "stale local"})
    monkeypatch.setattr(
        resources,
        "_load_notion_skill_doc_refs",
        lambda: {doc_name: "https://www.notion.so/example-2f759bb91e6880bbb0dadc8cf7da77c1"},
    )
    monkeypatch.setattr(resources, "fetch_notion_page_markdown", lambda _ref: "fresh live content")

    docs = resources.load_skill_docs()
    assert docs[doc_name] == "fresh live content"


def test_load_skill_docs_live_with_fallback_uses_local_when_notion_fails(monkeypatch):
    doc_name = "Writing guide.md"
    monkeypatch.setattr(resources, "INCLUDED_SKILL_DOCS", [doc_name])
    monkeypatch.setattr(resources, "NOTION_SKILL_DOCS_MODE", "live_with_fallback")
    monkeypatch.setattr(
        resources,
        "_local_skill_docs",
        lambda _doc_names=None: {doc_name: "local fallback"},
    )
    monkeypatch.setattr(
        resources,
        "_load_notion_skill_doc_refs",
        lambda: {doc_name: "https://www.notion.so/example-2f759bb91e6880bbb0dadc8cf7da77c1"},
    )

    def _raise(_ref: str) -> str:
        raise RuntimeError("network error")

    monkeypatch.setattr(resources, "fetch_notion_page_markdown", _raise)

    docs = resources.load_skill_docs()
    assert docs[doc_name] == "local fallback"


def test_load_notion_skill_doc_refs_accepts_utf8_bom(tmp_path: Path):
    config_path = tmp_path / "notion_skill_docs.json"
    config_path.write_text(
        '{"skill_doc_pages":{"Writing guide.md":"https://www.notion.so/example"}}',
        encoding="utf-8-sig",
    )

    refs = resources._load_notion_skill_doc_refs(config_path)
    assert refs["Writing guide.md"] == "https://www.notion.so/example"


def test_load_skill_docs_includes_extra_docs_from_notion_config(monkeypatch):
    included = ["Writing guide.md"]
    extra_doc = "Extra relevant doc.md"
    monkeypatch.setattr(resources, "INCLUDED_SKILL_DOCS", included)
    monkeypatch.setattr(resources, "NOTION_SKILL_DOCS_MODE", "live")
    monkeypatch.setattr(resources, "_local_skill_docs", lambda _doc_names=None: {})
    monkeypatch.setattr(
        resources,
        "_load_notion_skill_doc_refs",
        lambda: {
            "Writing guide.md": "https://www.notion.so/guide",
            extra_doc: "https://www.notion.so/extra",
        },
    )

    fetched: dict[str, str] = {}

    def _fetch(ref: str) -> str:
        fetched[ref] = ref
        return f"content::{ref}"

    monkeypatch.setattr(resources, "fetch_notion_page_markdown", _fetch)

    docs = resources.load_skill_docs()

    assert "Writing guide.md" in docs
    assert extra_doc in docs
    assert docs[extra_doc] == "content::https://www.notion.so/extra"
