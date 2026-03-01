from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

import requests

from .config import (
    ACTIVITIES_CSV_PATH,
    WEBFLOW_API_BASE_URL,
    WEBFLOW_API_TOKEN,
    WEBFLOW_CMS_LOCALE_IDS,
    WEBFLOW_COLLECTION_ID,
    WEBFLOW_FIELD_MAP_PATH,
)


def _load_field_map(path: Path = WEBFLOW_FIELD_MAP_PATH) -> dict[str, Any]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    example = path.with_name("webflow_field_map.example.json")
    if example.exists():
        return json.loads(example.read_text(encoding="utf-8"))
    return {
        "name_field_slug": "name",
        "slug_field_slug": "slug",
        "field_slug_map": {},
        "allow_empty_fields": [],
    }


def _headers() -> dict[str, str]:
    if not WEBFLOW_API_TOKEN:
        raise RuntimeError("WEBFLOW_API_TOKEN is missing.")
    return {
        "Authorization": f"Bearer {WEBFLOW_API_TOKEN}",
        "Content-Type": "application/json",
    }


def _format_webflow_error(response: requests.Response) -> str:
    code = "unknown_error"
    message = response.text
    try:
        body = response.json()
        code = str(body.get("code", code))
        message = str(body.get("message", message))
    except ValueError:
        pass
    return f"Webflow API {response.status_code} ({code}): {message}"


def _slugify(value: str) -> str:
    lowered = (value or "").strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    return slug or "untitled-activity"


def _resolve_collection_and_locales(csv_path: Path = ACTIVITIES_CSV_PATH) -> tuple[str, list[str]]:
    collection_id = WEBFLOW_COLLECTION_ID
    locale_ids = list(WEBFLOW_CMS_LOCALE_IDS)

    if collection_id and locale_ids:
        return collection_id, locale_ids

    if not csv_path.exists():
        return collection_id, locale_ids

    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        first_row = next(reader, {})

    csv_collection_id = (first_row.get("Collection ID", "") or "").strip()
    csv_locale_id = (first_row.get("Locale ID", "") or "").strip()

    if not collection_id and csv_collection_id:
        collection_id = csv_collection_id
    if not locale_ids and csv_locale_id:
        locale_ids = [csv_locale_id]
    return collection_id, locale_ids


def validate_webflow_configuration() -> tuple[bool, str]:
    if not WEBFLOW_API_TOKEN:
        return False, "WEBFLOW_API_TOKEN is missing."

    collection_id, locale_ids = _resolve_collection_and_locales()
    if not collection_id:
        return False, (
            "WEBFLOW_COLLECTION_ID is missing and no CSV default Collection ID could be derived."
        )
    if not locale_ids:
        return False, (
            "WEBFLOW_CMS_LOCALE_IDS is missing and no CSV default Locale ID could be derived."
        )

    try:
        response = requests.get(
            f"{WEBFLOW_API_BASE_URL}/v2/collections/{collection_id}",
            headers=_headers(),
            timeout=30,
        )
    except requests.RequestException as exc:
        return False, f"Webflow validation request failed: {exc}"

    if response.status_code >= 400:
        return False, _format_webflow_error(response)

    return True, "Webflow configuration verified."


def _build_webflow_field_data(draft: dict[str, str], field_map: dict[str, Any]) -> dict[str, Any]:
    name_field_slug = str(field_map.get("name_field_slug", "name")).strip()
    slug_field_slug = str(field_map.get("slug_field_slug", "slug")).strip()
    field_slug_map = field_map.get("field_slug_map", {})
    allow_empty_fields = set(field_map.get("allow_empty_fields", []))

    if not name_field_slug or not slug_field_slug:
        raise RuntimeError("Webflow map must include non-empty name_field_slug and slug_field_slug.")
    if not isinstance(field_slug_map, dict):
        raise RuntimeError("Webflow map field_slug_map must be an object.")

    title = (draft.get("Activity Title", "") or "").strip() or "Untitled Activity"
    field_data: dict[str, Any] = {
        name_field_slug: title,
        slug_field_slug: _slugify(title),
    }

    for draft_field, webflow_slug in field_slug_map.items():
        slug = (webflow_slug or "").strip()
        if not slug:
            continue
        value = (draft.get(draft_field, "") or "").strip()
        if value or slug in allow_empty_fields:
            field_data[slug] = value
    return field_data


def create_webflow_draft(draft: dict[str, str]) -> dict[str, Any]:
    collection_id, locale_ids = _resolve_collection_and_locales()
    if not collection_id:
        raise RuntimeError(
            "Missing Webflow collection target. Set WEBFLOW_COLLECTION_ID or CSV Collection ID."
        )
    if not locale_ids:
        raise RuntimeError(
            "Missing Webflow locale target. Set WEBFLOW_CMS_LOCALE_IDS or CSV Locale ID."
        )

    field_map = _load_field_map()
    field_data = _build_webflow_field_data(draft, field_map)
    payload = {
        "isDraft": True,
        "isArchived": False,
        "cmsLocaleIds": locale_ids,
        "fieldData": field_data,
    }
    response = requests.post(
        f"{WEBFLOW_API_BASE_URL}/v2/collections/{collection_id}/items/bulk",
        headers=_headers(),
        json=payload,
        timeout=60,
    )
    if response.status_code >= 400:
        raise RuntimeError(_format_webflow_error(response))

    body = response.json()
    created_item: dict[str, Any] = {}
    if isinstance(body.get("items"), list) and body["items"]:
        created_item = body["items"][0]
    elif isinstance(body.get("stagedItems"), list) and body["stagedItems"]:
        created_item = body["stagedItems"][0]

    item_id = str(
        created_item.get("id")
        or created_item.get("itemId")
        or body.get("id")
        or body.get("itemId")
        or ""
    )

    return {
        "id": item_id,
        "collection_id": collection_id,
        "cms_locale_ids": locale_ids,
        "is_draft": True,
        "is_archived": False,
        "created": True,
    }
