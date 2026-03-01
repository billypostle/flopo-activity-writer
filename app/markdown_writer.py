from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .config import ACTIVITIES_OUTPUT_DIR


def slugify(text: str) -> str:
    slug = text.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"\s+", "-", slug)
    slug = re.sub(r"-{2,}", "-", slug)
    return slug.strip("-")


def build_markdown(draft: dict[str, str], ordered_fields: Iterable[str]) -> str:
    now = datetime.now(timezone.utc).isoformat()
    title = draft.get("Activity Title", "untitled activity")
    lines = [
        "---",
        f"title: {title}",
        f"generated_at_utc: {now}",
        "---",
        "",
    ]
    for field in ordered_fields:
        lines.append(f"## {field}")
        lines.append("")
        lines.append((draft.get(field, "") or "").strip())
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def save_markdown_to_activities(
    draft: dict[str, str],
    ordered_fields: Iterable[str],
    output_dir: Path = ACTIVITIES_OUTPUT_DIR,
) -> tuple[Path, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    title = draft.get("Activity Title", "untitled activity")
    slug = slugify(title) or "untitled-activity"
    destination = output_dir / f"{slug}.md"
    markdown = build_markdown(draft, ordered_fields)
    destination.write_text(markdown, encoding="utf-8")
    return destination, slug

