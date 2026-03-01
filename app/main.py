from __future__ import annotations

from pathlib import Path
import logging
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .generator import generate_activity_draft
from .markdown_writer import build_markdown, save_markdown_to_activities
from .models import (
    CombinedPublishRequest,
    CombinedPublishResponse,
    GenerateDraftRequest,
    GenerateDraftResponse,
    CombinedPublishNotionResult,
    CombinedPublishWebflowResult,
    NotionCreateDraftRequest,
    NotionCreateDraftResponse,
    SaveLocalRequest,
    SaveLocalResponse,
)
from .notion_client import create_notion_draft, validate_notion_configuration
from .resources import content_fields_from_csv, load_resources_payload
from .webflow_client import create_webflow_draft, validate_webflow_configuration

app = FastAPI(title="FloPo Activity Writer", version="0.1.0")
logger = logging.getLogger(__name__)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def _set_generation_status(message: str, *, active: bool) -> None:
    app.state.generation_status = {
        "active": active,
        "message": message,
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
    }


@app.on_event("startup")
def startup_validate_notion() -> None:
    _set_generation_status("Idle", active=False)
    ok, message = validate_notion_configuration()
    app.state.notion_ready = ok
    app.state.notion_status_message = message
    if ok:
        logger.info("Notion startup verification passed.")
    else:
        logger.warning("Notion startup verification failed: %s", message)

    webflow_ok, webflow_message = validate_webflow_configuration()
    app.state.webflow_ready = webflow_ok
    app.state.webflow_status_message = webflow_message
    if webflow_ok:
        logger.info("Webflow startup verification passed.")
    else:
        logger.warning("Webflow startup verification failed: %s", webflow_message)


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
        {"active": False, "message": "Idle", "updated_at_utc": datetime.now(timezone.utc).isoformat()},
    )


@app.post("/api/generate-draft", response_model=GenerateDraftResponse)
def post_generate_draft(payload: GenerateDraftRequest) -> GenerateDraftResponse:
    def update_status(message: str) -> None:
        _set_generation_status(message, active=True)

    _set_generation_status("Starting generation", active=True)
    try:
        content_fields = content_fields_from_csv()
        update_status("Loading content field definitions")
        draft, report, rewrites, qc_report = generate_activity_draft(
            payload, content_fields, on_status=update_status
        )
        update_status("Building markdown preview")
        markdown_preview = build_markdown(draft, content_fields)
    except Exception as exc:
        _set_generation_status(f"Generation failed: {exc}", active=False)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _set_generation_status("Generation complete", active=False)

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


@app.post("/api/save-local", response_model=SaveLocalResponse)
def post_save_local(payload: SaveLocalRequest) -> SaveLocalResponse:
    try:
        content_fields = content_fields_from_csv()
        path, slug = save_markdown_to_activities(payload.activity_draft, content_fields)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return SaveLocalResponse(saved_path=str(path), slug=slug)


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


@app.post("/api/publish/notion-webflow-draft", response_model=CombinedPublishResponse)
def post_publish_notion_webflow_draft(payload: CombinedPublishRequest) -> CombinedPublishResponse:
    if not getattr(app.state, "notion_ready", False):
        detail = getattr(app.state, "notion_status_message", "Notion is not configured.")
        raise HTTPException(status_code=400, detail=f"Notion startup verification failed: {detail}")
    if not getattr(app.state, "webflow_ready", False):
        detail = getattr(app.state, "webflow_status_message", "Webflow is not configured.")
        raise HTTPException(status_code=400, detail=f"Webflow startup verification failed: {detail}")

    notion_result = CombinedPublishNotionResult()
    webflow_result = CombinedPublishWebflowResult()

    try:
        notion_page = create_notion_draft(payload.activity_draft)
        notion_result = CombinedPublishNotionResult(
            id=str(notion_page.get("id", "")),
            url=str(notion_page.get("url", "")),
            created=True,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Notion draft creation failed: {exc}") from exc

    try:
        webflow_item = create_webflow_draft(payload.activity_draft)
        webflow_result = CombinedPublishWebflowResult(
            id=str(webflow_item.get("id", "")),
            collection_id=str(webflow_item.get("collection_id", "")),
            cms_locale_ids=list(webflow_item.get("cms_locale_ids", [])),
            is_draft=bool(webflow_item.get("is_draft", True)),
            is_archived=bool(webflow_item.get("is_archived", False)),
            created=bool(webflow_item.get("created", False)),
        )
    except Exception as exc:
        return CombinedPublishResponse(
            success=False,
            notion=notion_result,
            webflow=webflow_result,
            errors=[f"Webflow draft creation failed after Notion success: {exc}"],
        )

    return CombinedPublishResponse(
        success=True,
        notion=notion_result,
        webflow=webflow_result,
        errors=[],
    )
