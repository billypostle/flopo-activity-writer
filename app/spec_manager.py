from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any

from .config import (
    FLOPO_MODEL_SPEC_CACHE_PATH,
    FLOPO_MODEL_SPEC_REFRESH_SECONDS,
    FLOPO_MODEL_SPEC_URL,
    FLOPO_MODEL_SPEC_VERSION,
)
from .notion_client import fetch_notion_page_markdown

logger = logging.getLogger(__name__)


def hash_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def load_cached_spec(path: Path | None = None) -> dict[str, Any] | None:
    cache_path = path or FLOPO_MODEL_SPEC_CACHE_PATH
    if not cache_path.exists():
        return None
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    required = {"spec_version", "spec_text", "spec_hash", "fetched_at", "source"}
    if not required.issubset(payload.keys()):
        return None
    return payload


def save_cached_spec(payload: dict[str, Any], path: Path | None = None) -> None:
    cache_path = path or FLOPO_MODEL_SPEC_CACHE_PATH
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _is_cache_fresh(payload: dict[str, Any], refresh_seconds: int) -> bool:
    fetched_at = payload.get("fetched_at")
    if not isinstance(fetched_at, (float, int)):
        return False
    return (time.time() - float(fetched_at)) < max(refresh_seconds, 0)


def get_model_spec() -> dict[str, Any]:
    spec_url = FLOPO_MODEL_SPEC_URL.strip()
    if not spec_url:
        raise RuntimeError("FLOPO_MODEL_SPEC_URL is missing.")
    if not FLOPO_MODEL_SPEC_VERSION.strip():
        raise RuntimeError("FLOPO_MODEL_SPEC_VERSION is missing.")

    refresh_seconds = FLOPO_MODEL_SPEC_REFRESH_SECONDS
    cached = load_cached_spec()
    if cached and _is_cache_fresh(cached, refresh_seconds):
        return cached

    spec_text = fetch_notion_page_markdown(spec_url)
    spec_hash = hash_text(spec_text)
    fetched_at = time.time()
    payload = {
        "spec_version": FLOPO_MODEL_SPEC_VERSION,
        "spec_text": spec_text,
        "spec_hash": spec_hash,
        "fetched_at": fetched_at,
        "source": spec_url,
    }

    if cached and cached.get("spec_hash") != spec_hash:
        logger.warning(
            "Model spec content changed; bump FLOPO_MODEL_SPEC_VERSION (semver) after review."
        )

    save_cached_spec(payload)
    return payload
