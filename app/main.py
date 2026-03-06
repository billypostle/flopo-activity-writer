from __future__ import annotations

import binascii
import logging
from base64 import b64decode
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from secrets import compare_digest

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .generator import generate_activity_draft
from .markdown_writer import build_markdown
from .models import (
    GenerateDraftRequest,
    GenerateDraftResponse,
    NotionCreateDraftRequest,
    NotionCreateDraftResponse,
)
from .notion_client import create_notion_draft, validate_notion_configuration
from .resources import content_fields_from_csv, load_resources_payload

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _set_generation_status(app, "Idle", active=False)
    ok, message = validate_notion_configuration()
    app.state.notion_ready = ok
    app.state.notion_status_message = message
    if ok:
        logger.info("Notion startup verification passed.")
    else:
        logger.warning("Notion startup verification failed: %s", message)
    yield


app = FastAPI(
    title="FloPo Activity Writer",
    version="0.1.0",
    lifespan=lifespan,
    docs_url=None if config.ENVIRONMENT == "production" else "/docs",
    redoc_url=None if config.ENVIRONMENT == "production" else "/redoc",
    openapi_url=None if config.ENVIRONMENT == "production" else "/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def _set_generation_status(app_obj: FastAPI, message: str, *, active: bool) -> None:
    app_obj.state.generation_status = {
        "active": active,
        "message": message,
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def _auth_error() -> JSONResponse:
    return JSONResponse(
        status_code=401,
        content={"detail": "Authentication required."},
        headers={"WWW-Authenticate": 'Basic realm="FloPo Activity Writer"'},
    )


def _is_authenticated(request: Request) -> bool:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Basic "):
        return False

    encoded = auth_header[6:].strip()
    try:
        decoded = b64decode(encoded).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError):
        return False

    if ":" not in decoded:
        return False

    username, password = decoded.split(":", 1)
    return compare_digest(username, config.APP_AUTH_USERNAME) and compare_digest(
        password, config.APP_AUTH_PASSWORD
    )


@app.middleware("http")
async def security_and_auth_middleware(request: Request, call_next):
    path = request.url.path
    is_health = path == "/healthz"
    is_preflight = request.method.upper() == "OPTIONS"

    if not is_health and not is_preflight:
        creds_configured = bool(config.APP_AUTH_USERNAME and config.APP_AUTH_PASSWORD)
        if config.ENVIRONMENT == "production" and not creds_configured:
            return JSONResponse(
                status_code=500,
                content={"detail": "APP_AUTH_USERNAME and APP_AUTH_PASSWORD must be configured."},
            )

        if creds_configured and not _is_authenticated(request):
            return _auth_error()

    response = await call_next(request)
    response.headers["Content-Security-Policy"] = config.CONTENT_SECURITY_POLICY
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


@app.get("/")
def home() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/resources")
def get_resources() -> dict:
    return load_resources_payload()


@app.get("/api/generation-status")
def get_generation_status() -> dict:
    return getattr(
        app.state,
        "generation_status",
        {
            "active": False,
            "message": "Idle",
            "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        },
    )


@app.post("/api/generate-draft", response_model=GenerateDraftResponse)
def post_generate_draft(payload: GenerateDraftRequest) -> GenerateDraftResponse:
    def update_status(message: str) -> None:
        _set_generation_status(app, message, active=True)

    _set_generation_status(app, "Starting generation", active=True)
    try:
        content_fields = content_fields_from_csv()
        update_status("Loading content field definitions")
        draft, report, rewrites, qc_report = generate_activity_draft(
            payload, content_fields, on_status=update_status
        )
        update_status("Building markdown preview")
        markdown_preview = build_markdown(draft, content_fields)
    except Exception as exc:
        _set_generation_status(app, f"Generation failed: {exc}", active=False)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _set_generation_status(app, "Generation complete", active=False)

    return GenerateDraftResponse(
        activity_draft=draft,
        validation_report=report,
        rewrite_count=rewrites,
        markdown_preview=markdown_preview,
        qc_applied=qc_report.applied,
        qc_passed=qc_report.passed,
        qc_edited_fields=qc_report.edited_fields,
        qc_issues=qc_report.issues,
        qc_error=qc_report.error,
    )


@app.post("/api/notion/create-draft", response_model=NotionCreateDraftResponse)
def post_notion_create_draft(payload: NotionCreateDraftRequest) -> NotionCreateDraftResponse:
    if not getattr(app.state, "notion_ready", False):
        detail = getattr(app.state, "notion_status_message", "Notion is not configured.")
        raise HTTPException(status_code=400, detail=f"Notion startup verification failed: {detail}")

    try:
        notion_page = create_notion_draft(payload.activity_draft)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return NotionCreateDraftResponse(
        notion_id=notion_page.get("id", ""),
        notion_url=notion_page.get("url", ""),
        draft_property="",
        draft_value=None,
    )
