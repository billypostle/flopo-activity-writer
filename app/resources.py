from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

from .config import (
    ACTIVITIES_CSV_PATH,
    CSV_INTERNAL_COLUMNS,
    ETHOS_MASTER_DOC,
    ETHOS_SKILL_DOCS_DIR,
    INCLUDED_SKILL_DOCS,
    INCLUDED_ETHOS_SKILL_DOCS,
    NOTION_SKILL_DOCS_CONFIG_PATH,
    NOTION_SKILL_DOCS_MODE,
    SKILL_DOCS_DIR,
    THEMES_CSV_PATH,
)
from .notion_client import fetch_notion_child_page_refs, fetch_notion_page_markdown
from .spec_manager import get_model_spec


def normalize_label(value: str) -> str:
    replacements = {
        "–": "-",
        "—": "-",
        "â€“": "-",
        "â€”": "-",
        "’": "'",
        "â€™": "'",
    }
    output = value
    for old, new in replacements.items():
        output = output.replace(old, new)
    return output.strip()


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _resolve_local_skill_doc_path(filename: str) -> Path:
    candidates = [
        SKILL_DOCS_DIR / filename,
        ETHOS_SKILL_DOCS_DIR / filename,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def _local_skill_docs(doc_names: list[str] | None = None) -> dict[str, str]:
    docs: dict[str, str] = {}
    selected_docs = doc_names or INCLUDED_SKILL_DOCS
    for filename in selected_docs:
        full_path = _resolve_local_skill_doc_path(filename)
        docs[filename] = read_text(full_path) if full_path.exists() else ""
    return docs


def _load_notion_skill_doc_refs(path: Path = NOTION_SKILL_DOCS_CONFIG_PATH) -> dict[str, str]:
    payload_path = path
    if not payload_path.exists():
        example = payload_path.with_name("notion_skill_docs.example.json")
        payload_path = example if example.exists() else payload_path
    if not payload_path.exists():
        return {}

    try:
        payload = json.loads(payload_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON in {payload_path}: {exc}") from exc

    if not isinstance(payload, dict):
        raise RuntimeError(f"Expected object in {payload_path}, got {type(payload).__name__}.")

    refs = payload.get("skill_doc_pages", {})
    if not isinstance(refs, dict):
        raise RuntimeError(
            f"Expected 'skill_doc_pages' object in {payload_path}, got {type(refs).__name__}."
        )

    output: dict[str, str] = {}
    for key, value in refs.items():
        if isinstance(key, str) and isinstance(value, str):
            output[normalize_label(key)] = value.strip()
    return output


def load_skill_docs() -> dict[str, str]:
    refs = _load_notion_skill_doc_refs()
    requested_docs: list[str] = []
    seen: set[str] = set()
    for name in [*INCLUDED_SKILL_DOCS, *refs.keys()]:
        normalized = normalize_label(name)
        if normalized and normalized not in seen:
            seen.add(normalized)
            requested_docs.append(normalized)

    local_docs = _local_skill_docs(requested_docs)
    mode = (NOTION_SKILL_DOCS_MODE or "live_with_fallback").strip().lower()
    if mode not in {"local", "live", "live_with_fallback"}:
        raise RuntimeError(
            "Invalid NOTION_SKILL_DOCS_MODE. Expected one of: local, live, live_with_fallback."
        )
    if mode == "local":
        return local_docs

    output = dict(local_docs) if mode == "live_with_fallback" else {name: "" for name in requested_docs}
    errors: list[str] = []

    for filename in requested_docs:
        ref = refs.get(normalize_label(filename), "")
        if not ref:
            if mode == "live":
                errors.append(f"Missing Notion page reference for skill doc: {filename}")
            continue

        try:
            output[filename] = fetch_notion_page_markdown(ref)
        except Exception as exc:
            if mode == "live":
                errors.append(f"Failed loading {filename} from Notion: {exc}")

    if mode == "live" and errors:
        raise RuntimeError("Notion skill doc loading failed:\n- " + "\n- ".join(errors))

    return output


def _local_runtime_ethos_docs() -> dict[str, str]:
    return _local_skill_docs([ETHOS_MASTER_DOC, *INCLUDED_ETHOS_SKILL_DOCS])


def load_runtime_ethos_skill_docs() -> dict[str, str]:
    refs = _load_notion_skill_doc_refs()
    mode = (NOTION_SKILL_DOCS_MODE or "live_with_fallback").strip().lower()
    if mode not in {"local", "live", "live_with_fallback"}:
        raise RuntimeError(
            "Invalid NOTION_SKILL_DOCS_MODE. Expected one of: local, live, live_with_fallback."
        )

    local_docs = _local_runtime_ethos_docs()
    if mode == "local":
        return {name: text for name, text in local_docs.items() if text.strip()}

    output = dict(local_docs) if mode == "live_with_fallback" else {}
    master_ref = refs.get(normalize_label(ETHOS_MASTER_DOC), "")
    errors: list[str] = []

    if not master_ref:
        if mode == "live":
            raise RuntimeError(f"Missing Notion page reference for skill doc: {ETHOS_MASTER_DOC}")
        return {name: text for name, text in output.items() if text.strip()}

    try:
        master_content = fetch_notion_page_markdown(master_ref)
        if master_content.strip():
            output[ETHOS_MASTER_DOC] = master_content

        child_refs = fetch_notion_child_page_refs(master_ref)
        for title, ref in child_refs.items():
            child_content = fetch_notion_page_markdown(ref)
            if child_content.strip():
                output[normalize_label(title)] = child_content
    except Exception as exc:
        if mode == "live":
            errors.append(f"Failed loading runtime ethos skill docs from Notion: {exc}")

    if mode == "live" and errors:
        raise RuntimeError("Notion skill doc loading failed:\n- " + "\n- ".join(errors))

    return {name: text for name, text in output.items() if str(text).strip()}


def load_model_spec_only() -> dict[str, Any]:
    return get_model_spec()


def extract_csv_headers(csv_path: Path = ACTIVITIES_CSV_PATH) -> list[str]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        headers = next(reader)
    return [normalize_label(h) for h in headers]


def content_fields_from_csv(csv_path: Path = ACTIVITIES_CSV_PATH) -> list[str]:
    headers = extract_csv_headers(csv_path)
    return [h for h in headers if h not in CSV_INTERNAL_COLUMNS]


def parse_themes() -> list[str]:
    if THEMES_CSV_PATH.exists():
        output: list[str] = []
        with THEMES_CSV_PATH.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = normalize_label(row.get("Name", ""))
                if name:
                    output.append(name)
        return output

    themes_md = read_text(SKILL_DOCS_DIR / "Themes.md")
    return [
        normalize_label(line.strip("- ").strip())
        for line in themes_md.splitlines()
        if line.strip().startswith("-")
    ]


def parse_materials() -> list[str]:
    text = read_text(SKILL_DOCS_DIR / "Materials list.md")
    materials = []
    for line in text.splitlines():
        cleaned = line.strip()
        if cleaned.startswith("- [ ]"):
            materials.append(normalize_label(cleaned.replace("- [ ]", "").strip()))
    return materials


def parse_age_bands() -> list[str]:
    text = read_text(SKILL_DOCS_DIR / "Age groups & identified focus areas.md")
    bands = []
    for line in text.splitlines():
        m = re.match(r"^#\s+\*\*(.+)\*\*$", line.strip())
        if m:
            bands.append(normalize_label(m.group(1)))
    return bands


def parse_eyfs_areas() -> list[str]:
    text = read_text(SKILL_DOCS_DIR / "The EYFS seven areas of learning & development.md")
    areas = []
    for line in text.splitlines():
        m = re.match(r"^##\s+\*\*\d+\.\s+(.+)\*\*$", line.strip())
        if m:
            areas.append(normalize_label(m.group(1)))
    return areas


def load_resources_payload() -> dict[str, Any]:
    return {
        "content_fields": content_fields_from_csv(),
        "themes": parse_themes(),
        "materials": parse_materials(),
        "age_bands": parse_age_bands(),
        "eyfs_areas": parse_eyfs_areas(),
    }
