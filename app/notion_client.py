from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import requests

from .config import (
    NOTION_API_KEY,
    NOTION_DATA_SOURCE_ID,
    NOTION_DATABASE_ID,
    NOTION_FIELD_MAP_PATH,
    NOTION_SKILL_DOCS_REQUEST_TIMEOUT_SECONDS,
    NOTION_VERSION,
)
from .resources import normalize_theme_list

NOTION_BASE_URL = "https://api.notion.com/v1"
MIN_DATA_SOURCE_NOTION_VERSION = "2025-09-03"


def _load_field_map(path: Path = NOTION_FIELD_MAP_PATH) -> dict[str, Any]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    example = path.with_name("notion_field_map.example.json")
    if example.exists():
        return json.loads(example.read_text(encoding="utf-8"))
    return {"title_property": "Activity Title", "field_property_map": {}}


def _effective_notion_version(*, require_data_sources: bool = False) -> str:
    if require_data_sources and NOTION_VERSION < MIN_DATA_SOURCE_NOTION_VERSION:
        return MIN_DATA_SOURCE_NOTION_VERSION
    return NOTION_VERSION


def _headers(*, require_data_sources: bool = False) -> dict[str, str]:
    if not NOTION_API_KEY:
        raise RuntimeError("NOTION_API_KEY is missing.")
    return {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": _effective_notion_version(require_data_sources=require_data_sources),
        "Content-Type": "application/json",
    }


def _format_notion_error(response: requests.Response) -> str:
    code = "unknown_error"
    message = response.text
    try:
        body = response.json()
        code = str(body.get("code", code))
        message = str(body.get("message", message))
    except ValueError:
        pass
    return f"Notion API {response.status_code} ({code}): {message}"


def _request_notion_json(url: str, timeout: int = 30) -> dict[str, Any]:
    response = requests.get(url, headers=_headers(), timeout=timeout)
    if response.status_code >= 400:
        raise RuntimeError(_format_notion_error(response))
    return response.json()


def _request_notion_json_with_headers(
    url: str,
    *,
    headers: dict[str, str],
    timeout: int = 30,
) -> dict[str, Any]:
    response = requests.get(url, headers=headers, timeout=timeout)
    if response.status_code >= 400:
        raise RuntimeError(_format_notion_error(response))
    return response.json()


def _parse_notion_page_id(page_ref: str) -> str:
    raw = (page_ref or "").strip()
    if not raw:
        raise RuntimeError("Notion page reference is empty.")

    # Accept full URL, bare 32-char ID, or canonical UUID.
    match = re.search(r"([0-9a-fA-F]{32})", raw)
    if match:
        compact = match.group(1).lower()
        return (
            f"{compact[0:8]}-{compact[8:12]}-{compact[12:16]}-"
            f"{compact[16:20]}-{compact[20:32]}"
        )

    uuid_match = re.search(
        r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})",
        raw,
    )
    if uuid_match:
        return uuid_match.group(1).lower()

    raise RuntimeError(f"Could not parse a Notion page ID from: {page_ref}")


def _fetch_block_children(block_id: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    cursor: str | None = None

    while True:
        url = f"{NOTION_BASE_URL}/blocks/{block_id}/children?page_size=100"
        if cursor:
            url = f"{url}&start_cursor={cursor}"
        payload = _request_notion_json(url, timeout=NOTION_SKILL_DOCS_REQUEST_TIMEOUT_SECONDS)
        items.extend(payload.get("results", []))
        if not payload.get("has_more"):
            break
        cursor = payload.get("next_cursor")
        if not cursor:
            break

    return items


def _collect_child_page_refs(blocks: list[dict[str, Any]]) -> dict[str, str]:
    refs: dict[str, str] = {}
    for block in blocks:
        block_type = str(block.get("type", ""))
        payload = block.get(block_type, {}) if isinstance(block.get(block_type), dict) else {}
        if block_type == "child_page":
            title = str(payload.get("title", "")).strip()
            block_id = str(block.get("id", "")).strip()
            if title and block_id and title not in refs:
                refs[title] = block_id

        if block.get("has_children"):
            child_id = str(block.get("id", "")).strip()
            if child_id:
                nested_blocks = _fetch_block_children(child_id)
                refs.update(_collect_child_page_refs(nested_blocks))

    return refs


def _extract_plain_text_from_rich_text(rich_text: list[dict[str, Any]]) -> str:
    return "".join(str(item.get("plain_text", "")) for item in rich_text).strip()


def _render_block_lines(block: dict[str, Any], depth: int = 0) -> list[str]:
    block_type = str(block.get("type", ""))
    payload = block.get(block_type, {}) if isinstance(block.get(block_type), dict) else {}
    rich_text = payload.get("rich_text", []) if isinstance(payload, dict) else []
    text = _extract_plain_text_from_rich_text(rich_text) if isinstance(rich_text, list) else ""

    indent = "  " * depth
    lines: list[str] = []

    if block_type == "heading_1":
        lines.append(f"{indent}# {text}".rstrip())
    elif block_type == "heading_2":
        lines.append(f"{indent}## {text}".rstrip())
    elif block_type == "heading_3":
        lines.append(f"{indent}### {text}".rstrip())
    elif block_type == "bulleted_list_item":
        lines.append(f"{indent}- {text}".rstrip())
    elif block_type == "numbered_list_item":
        lines.append(f"{indent}1. {text}".rstrip())
    elif block_type == "to_do":
        checked = bool(payload.get("checked", False))
        marker = "x" if checked else " "
        lines.append(f"{indent}- [{marker}] {text}".rstrip())
    elif block_type == "quote":
        lines.append(f"{indent}> {text}".rstrip())
    elif block_type == "callout":
        lines.append(f"{indent}> {text}".rstrip())
    elif block_type == "code":
        language = str(payload.get("language", "")).strip()
        if language:
            lines.append(f"{indent}```{language}")
        else:
            lines.append(f"{indent}```")
        if text:
            lines.append(f"{indent}{text}")
        lines.append(f"{indent}```")
    elif block_type == "divider":
        lines.append(f"{indent}---")
    elif block_type == "table_of_contents":
        lines.append(f"{indent}[Table of contents]")
    elif block_type == "image":
        lines.append(f"{indent}[Image]")
    elif block_type == "video":
        lines.append(f"{indent}[Video]")
    elif block_type == "embed":
        lines.append(f"{indent}[Embed]")
    elif block_type == "bookmark":
        lines.append(f"{indent}[Bookmark]")
    elif block_type == "file":
        lines.append(f"{indent}[File]")
    elif block_type == "child_page":
        title = str(payload.get("title", "")).strip()
        lines.append(f"{indent}# {title}".rstrip())
    elif block_type == "paragraph":
        lines.append(f"{indent}{text}".rstrip())
    elif text:
        lines.append(f"{indent}{text}".rstrip())

    if block.get("has_children"):
        children = _fetch_block_children(str(block.get("id", "")))
        for child in children:
            lines.extend(_render_block_lines(child, depth=depth + 1))

    return [line for line in lines if line.strip()]


def fetch_notion_page_markdown(page_ref: str) -> str:
    page_id = _parse_notion_page_id(page_ref)
    _request_notion_json(
        f"{NOTION_BASE_URL}/pages/{page_id}",
        timeout=NOTION_SKILL_DOCS_REQUEST_TIMEOUT_SECONDS,
    )
    root_blocks = _fetch_block_children(page_id)
    lines: list[str] = []
    for block in root_blocks:
        lines.extend(_render_block_lines(block))
    return "\n".join(lines).strip()


def fetch_notion_child_page_refs(page_ref: str) -> dict[str, str]:
    page_id = _parse_notion_page_id(page_ref)
    _request_notion_json(
        f"{NOTION_BASE_URL}/pages/{page_id}",
        timeout=NOTION_SKILL_DOCS_REQUEST_TIMEOUT_SECONDS,
    )
    root_blocks = _fetch_block_children(page_id)
    return _collect_child_page_refs(root_blocks)


def validate_notion_configuration() -> tuple[bool, str]:
    if not NOTION_API_KEY:
        return False, "NOTION_API_KEY is missing."
    if not NOTION_DATA_SOURCE_ID and not NOTION_DATABASE_ID:
        return False, "Set NOTION_DATA_SOURCE_ID or NOTION_DATABASE_ID."

    try:
        parent_type, parent_id, _ = _resolve_parent_target()
    except (RuntimeError, requests.RequestException) as exc:
        return False, f"Notion validation request failed: {exc}"
    return True, f"Notion configuration verified via {parent_type}: {parent_id}"


def _resolve_database_data_source(database_id: str) -> tuple[str, str | None]:
    response = requests.get(
        f"{NOTION_BASE_URL}/databases/{database_id}",
        headers=_headers(require_data_sources=True),
        timeout=30,
    )
    if response.status_code >= 400:
        raise RuntimeError(_format_notion_error(response))
    body = response.json()
    data_sources = body.get("data_sources", [])
    if not data_sources:
        raise RuntimeError(
            "The configured Notion database was found, but it has no data sources. "
            "Set NOTION_DATA_SOURCE_ID directly."
        )
    if len(data_sources) > 1:
        options = ", ".join(
            f"{item.get('name') or '<unnamed>'} ({item.get('id') or '<missing id>'})"
            for item in data_sources
        )
        raise RuntimeError(
            "The configured Notion database has multiple data sources. "
            f"Set NOTION_DATA_SOURCE_ID to one of: {options}"
        )
    data_source = data_sources[0]
    return str(data_source.get("id") or "").strip(), str(data_source.get("name") or "").strip() or None


def _resolve_parent_target() -> tuple[str, str, dict[str, Any]]:
    if NOTION_DATA_SOURCE_ID:
        body = _request_notion_json_with_headers(
            f"{NOTION_BASE_URL}/data_sources/{NOTION_DATA_SOURCE_ID}",
            headers=_headers(require_data_sources=True),
            timeout=30,
        )
        return "data_source_id", str(body.get("id") or NOTION_DATA_SOURCE_ID), body

    if not NOTION_DATABASE_ID:
        raise RuntimeError("Set NOTION_DATA_SOURCE_ID or NOTION_DATABASE_ID.")

    data_source_headers = _headers(require_data_sources=True)
    data_source_url = f"{NOTION_BASE_URL}/data_sources/{NOTION_DATABASE_ID}"
    data_source_response = requests.get(data_source_url, headers=data_source_headers, timeout=30)
    if data_source_response.status_code < 400:
        body = data_source_response.json()
        return "data_source_id", str(body.get("id") or NOTION_DATABASE_ID), body

    try:
        resolved_id, _ = _resolve_database_data_source(NOTION_DATABASE_ID)
    except RuntimeError as database_error:
        raise RuntimeError(
            f"{database_error} "
            f"The configured NOTION_DATABASE_ID ({NOTION_DATABASE_ID}) is not currently usable."
        ) from database_error

    body = _request_notion_json_with_headers(
        f"{NOTION_BASE_URL}/data_sources/{resolved_id}",
        headers=data_source_headers,
        timeout=30,
    )
    return "data_source_id", str(body.get("id") or resolved_id), body


def _database_properties() -> dict[str, dict[str, Any]]:
    _, _, body = _resolve_parent_target()
    return body.get("properties", {})


def _rich_text_chunks(text: str, size: int = 1800) -> list[dict[str, Any]]:
    if not text:
        return []
    chunks = [text[i : i + size] for i in range(0, len(text), size)]
    return [{"type": "text", "text": {"content": c}} for c in chunks]


def _property_payload_for_value(property_type: str, value: str) -> dict[str, Any] | None:
    clean = (value or "").strip()
    if property_type == "rich_text":
        return {"rich_text": _rich_text_chunks(clean)}
    if property_type == "title":
        return {"title": [{"type": "text", "text": {"content": clean or "Untitled Activity"}}]}
    if property_type == "multi_select":
        names = [t.strip() for t in clean.split(";") if t.strip()]
        return {"multi_select": [{"name": n} for n in names]}
    if property_type == "select":
        return {"select": {"name": clean}} if clean else None
    if property_type == "checkbox":
        lowered = clean.lower()
        return {"checkbox": lowered in {"1", "true", "yes", "y", "on"}}
    if property_type == "url":
        return {"url": clean}
    if property_type == "email":
        return {"email": clean}
    if property_type == "phone_number":
        return {"phone_number": clean}
    if property_type == "number":
        if not clean:
            return {"number": None}
        try:
            return {"number": float(clean)}
        except ValueError:
            return None
    return None


def _to_notion_properties(
    draft: dict[str, str],
    field_map: dict[str, Any],
    db_properties: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    title_property = field_map.get("title_property", "Activity Title")
    themes_property = field_map.get("themes_property", "Themes")
    field_property_map = field_map.get("field_property_map", {})

    properties: dict[str, Any] = {}

    title_entry = db_properties.get(title_property)
    if not title_entry or title_entry.get("type") != "title":
        title_property = next(
            (name for name, prop in db_properties.items() if prop.get("type") == "title"),
            title_property,
        )
        title_entry = db_properties.get(title_property)
    if title_entry and title_entry.get("type") == "title":
        title_value = draft.get("Activity Title", "")
        properties[title_property] = {
            "title": [{"type": "text", "text": {"content": title_value or "Untitled Activity"}}]
        }

    themes_raw = normalize_theme_list(draft.get("Themes", ""))
    themes_entry = db_properties.get(themes_property)
    if themes_raw and themes_entry:
        themes_payload = _property_payload_for_value(themes_entry.get("type", ""), themes_raw)
        if themes_payload is not None:
            properties[themes_property] = themes_payload

    for draft_field, notion_property in field_property_map.items():
        value = draft.get(draft_field, "")
        if draft_field == "Themes" or draft_field == "Activity Title":
            continue
        notion_entry = db_properties.get(notion_property)
        if not notion_entry:
            continue
        payload = _property_payload_for_value(notion_entry.get("type", ""), value)
        if payload is not None:
            properties[notion_property] = payload
    return properties


def create_notion_draft(draft: dict[str, str]) -> dict[str, Any]:
    if not NOTION_DATA_SOURCE_ID and not NOTION_DATABASE_ID:
        raise RuntimeError("Set NOTION_DATA_SOURCE_ID or NOTION_DATABASE_ID.")

    field_map = _load_field_map()
    db_properties = _database_properties()
    properties = _to_notion_properties(draft, field_map, db_properties)
    parent_type, parent_id, _ = _resolve_parent_target()
    payload = {
        "parent": {parent_type: parent_id},
        "properties": properties,
    }
    response = requests.post(
        f"{NOTION_BASE_URL}/pages",
        headers=_headers(require_data_sources=True),
        json=payload,
        timeout=60,
    )
    if response.status_code >= 400:
        raise RuntimeError(_format_notion_error(response))
    return response.json()
