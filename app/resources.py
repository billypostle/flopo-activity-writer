from __future__ import annotations

import csv
import json
import re
import time
import unicodedata
from hashlib import sha256
from pathlib import Path
from typing import Any

from .config import (
    ACTIVITIES_CSV_PATH,
    CSV_INTERNAL_COLUMNS,
    ETHOS_MASTER_DOC,
    INCLUDED_SKILL_DOCS,
    LOCAL_MODEL_SPEC_DOC,
    NOTION_SKILL_DOCS_CONFIG_PATH,
    SKILL_DOCS_DIR,
    THEMES_CSV_PATH,
)


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


def _normalize_doc_lookup_key(value: str) -> str:
    text = unicodedata.normalize("NFKC", normalize_label(value)).strip()
    text = text.replace(".md", "").strip()
    text = (
        text.replace("–", "-")
        .replace("—", "-")
        .replace("−", "-")
        .replace("’", "'")
        .replace("“", '"')
        .replace("”", '"')
    )
    text = re.sub(r"\s+", " ", text)
    return text.casefold()


def _skill_doc_index() -> dict[str, Path]:
    index: dict[str, Path] = {}
    for path in SKILL_DOCS_DIR.rglob("*.md"):
        relative = path.relative_to(SKILL_DOCS_DIR)
        candidates = {
            path.name,
            path.stem,
            str(relative),
            str(relative.with_suffix("")),
        }
        for candidate in candidates:
            key = _normalize_doc_lookup_key(candidate)
            if key and key not in index:
                index[key] = path
    return index


def _resolve_local_skill_doc_path(doc_ref: str) -> Path:
    normalized = _normalize_doc_lookup_key(doc_ref)
    index = _skill_doc_index()
    if normalized in index:
        return index[normalized]
    fallback = SKILL_DOCS_DIR / doc_ref
    if fallback.suffix.lower() != ".md":
        fallback = fallback.with_suffix(".md")
    return fallback


def _wiki_link_targets(text: str) -> list[str]:
    targets: list[str] = []
    for raw_target in re.findall(r"\[\[([^\]]+)\]\]", text or ""):
        target = raw_target.split("|", 1)[0].split("#", 1)[0].strip()
        if target and target not in targets:
            targets.append(target)
    return targets


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
    return _local_skill_docs(INCLUDED_SKILL_DOCS)


def load_runtime_ethos_skill_docs() -> dict[str, str]:
    master_path = _resolve_local_skill_doc_path(ETHOS_MASTER_DOC)
    master_text = read_text(master_path).strip()
    if not master_text:
        return {}

    output: dict[str, str] = {ETHOS_MASTER_DOC: master_text}
    for target in _wiki_link_targets(master_text):
        target_path = _resolve_local_skill_doc_path(target)
        target_text = read_text(target_path).strip()
        if not target_text:
            continue
        output[target_path.stem] = target_text

    return output


def load_model_spec_only() -> dict[str, Any]:
    spec_path = _resolve_local_skill_doc_path(LOCAL_MODEL_SPEC_DOC)
    spec_text = read_text(spec_path).strip()
    if not spec_text:
        raise RuntimeError(f"Local model spec is missing or empty: {spec_path}")

    spec_hash = sha256(spec_text.encode("utf-8")).hexdigest()
    return {
        "spec_version": spec_hash[:12],
        "spec_text": spec_text,
        "spec_hash": spec_hash,
        "fetched_at": time.time(),
        "source": str(spec_path),
    }


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
