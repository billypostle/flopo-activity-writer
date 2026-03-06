from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

APP_DIR = Path(__file__).resolve().parent
PROJECT_DIR = APP_DIR.parent


def _first_existing_path(candidates: list[Path]) -> Path:
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def _looks_like_flopo_repo(path: Path) -> bool:
    return (path / "Databases").exists() and (path / "Skill docs").exists()


def _resolve_repo_root(candidates: list[Path], fallback: Path) -> Path:
    existing: list[Path] = []
    for candidate in candidates:
        if candidate.exists() and candidate not in existing:
            existing.append(candidate)

    for candidate in existing:
        if _looks_like_flopo_repo(candidate):
            return candidate

    if fallback.exists():
        return fallback
    return _first_existing_path(candidates)


explicit_repo_root = os.getenv("FLOPO_REPO_ROOT", "").strip()
repo_root_candidates: list[Path] = []
if explicit_repo_root:
    repo_root_candidates.append(Path(explicit_repo_root).expanduser())
repo_root_candidates.extend(
    [
        PROJECT_DIR.parent.parent,  # local monorepo layout
        PROJECT_DIR.parent,  # alternate local layout
        PROJECT_DIR,  # Vercel root-dir deployment
    ]
)
REPO_ROOT = _resolve_repo_root(repo_root_candidates, fallback=PROJECT_DIR)

# Always load this project's .env, regardless of process working directory.
load_dotenv(dotenv_path=PROJECT_DIR / ".env", override=True)

SKILL_DOCS_DIR = REPO_ROOT / "Skill docs"
DATABASES_DIR = REPO_ROOT / "Databases"
ACTIVITIES_OUTPUT_DIR = REPO_ROOT / "Activities"

activities_csv_candidates = [
    PROJECT_DIR / "config" / "activities_fields.csv",  # bundled for hosted deploys
    DATABASES_DIR / "FloPo - Activities - 698734a9856055bb42014e7a (1).csv",  # local monorepo
]
themes_csv_candidates = [
    PROJECT_DIR / "config" / "webflow_themes_import.csv",  # optional bundled copy
    DATABASES_DIR / "webflow_themes_import.csv",  # local monorepo
]

ACTIVITIES_CSV_PATH = _first_existing_path(activities_csv_candidates)
THEMES_CSV_PATH = _first_existing_path(themes_csv_candidates)
NOTION_FIELD_MAP_PATH = PROJECT_DIR / "config" / "notion_field_map.json"

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip().strip("\"'")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.2").strip()
OPENAI_QC_MODEL = os.getenv("OPENAI_QC_MODEL", "o3").strip()
NOTION_API_KEY = os.getenv("NOTION_API_KEY", "").strip().strip("\"'")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID", "").strip().strip("\"'")
NOTION_VERSION = os.getenv("NOTION_VERSION", "2022-06-28").strip()
NOTION_DRAFT_PROPERTY = os.getenv("NOTION_DRAFT_PROPERTY", "Draft").strip()
NOTION_SKILL_DOCS_MODE = os.getenv("NOTION_SKILL_DOCS_MODE", "live_with_fallback").strip().lower()
NOTION_SKILL_DOCS_REQUEST_TIMEOUT_SECONDS = int(
    os.getenv("NOTION_SKILL_DOCS_REQUEST_TIMEOUT_SECONDS", "30")
)
FLOPO_MODEL_SPEC_URL = os.getenv("FLOPO_MODEL_SPEC_URL", "").strip().strip("\"'")
FLOPO_MODEL_SPEC_VERSION = os.getenv("FLOPO_MODEL_SPEC_VERSION", "1.0.0").strip()
FLOPO_MODEL_SPEC_CACHE_PATH = Path(
    os.getenv("FLOPO_MODEL_SPEC_CACHE_PATH", str(PROJECT_DIR / ".cache" / "model_spec.json"))
)
FLOPO_MODEL_SPEC_REFRESH_SECONDS = int(os.getenv("FLOPO_MODEL_SPEC_REFRESH_SECONDS", "3600"))
WEBFLOW_API_TOKEN = os.getenv("WEBFLOW_API_TOKEN", "").strip().strip("\"'")
WEBFLOW_COLLECTION_ID = os.getenv("WEBFLOW_COLLECTION_ID", "").strip().strip("\"'")
WEBFLOW_CMS_LOCALE_IDS = [
    value.strip()
    for value in os.getenv("WEBFLOW_CMS_LOCALE_IDS", "").strip().strip("\"'").split(",")
    if value.strip()
]
WEBFLOW_API_BASE_URL = os.getenv("WEBFLOW_API_BASE_URL", "https://api.webflow.com").strip()
WEBFLOW_FIELD_MAP_PATH = PROJECT_DIR / "config" / "webflow_field_map.json"
NOTION_SKILL_DOCS_CONFIG_PATH = PROJECT_DIR / "config" / "notion_skill_docs.json"
MAX_REWRITE_ATTEMPTS = int(os.getenv("MAX_REWRITE_ATTEMPTS", "3"))
default_environment = "production" if os.getenv("VERCEL_ENV", "").strip().lower() == "production" else "development"
ENVIRONMENT = os.getenv("ENVIRONMENT", default_environment).strip().lower()
APP_AUTH_USERNAME = os.getenv("APP_AUTH_USERNAME", "").strip()
APP_AUTH_PASSWORD = os.getenv("APP_AUTH_PASSWORD", "").strip()
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", "https://flopo.co.uk").split(",")
    if origin.strip()
]

INCLUDED_SKILL_DOCS = [
    "Writing guide.md",
    "Activity Structure.md",
    "Themes.md",
    "Materials list.md",
    "Age groups & identified focus areas.md",
    "The EYFS seven areas of learning & development.md",
    "Ethos Definitions.md",
    "Yearly curriculum.md",
]

CSV_INTERNAL_COLUMNS = {
    "Slug",
    "Collection ID",
    "Locale ID",
    "Item ID",
    "Archived",
    "Draft",
    "Created On",
    "Updated On",
    "Published On",
    "Hero",
    "Ethos Adaptation: Montessori (image)",
    "Ethos Adaptation: Forest School (image)",
    "Ethos Adaptation: Reggio Emilia (image)",
    "Ethos Adaptation: Steiner (Waldorf) (image)",
    "Is Free?",
    "Is Included in Subscription?",
    "Linked Product",
}

ALLOWED_EMPTY_FIELDS = {
    "Age Adaptation: 0-12 months (Little Learners)",
    "Age Adaptation: 12-24 months (Early Explorers)",
    "Age Adaptation: 2 years (Budding Adventurers)",
    "Age Adaptation: 3 years (Curious Investigators)",
    "Age Adaptation: 4 years (Confident Discoverers)",
    "Linked materials",
}

BANNED_PHRASES = [
    "supports holistic development",
    "enhances engagement",
    "screen-free fun",
    "messy magic",
]

REQUIRED_ETHOS_FIELDS = [
    "Ethos Adaptation: Montessori",
    "Ethos Adaptation: Forest School",
    "Ethos Adaptation: Reggio Emilia",
    "Ethos Adaptation: Steiner (Waldorf)",
]
