from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class GenerateDraftRequest(BaseModel):
    notes: str = Field(min_length=10)


class ValidationReport(BaseModel):
    passed: bool
    blocking_issues: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class QCReport(BaseModel):
    applied: bool
    passed: bool
    edited_fields: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    error: str = ""


class GenerateDraftResponse(BaseModel):
    activity_draft: dict[str, str]
    validation_report: ValidationReport
    rewrite_count: int
    markdown_preview: str
    qc_applied: bool
    qc_passed: bool
    qc_edited_fields: list[str] = Field(default_factory=list)
    qc_issues: list[str] = Field(default_factory=list)
    qc_error: str = ""


class SaveLocalRequest(BaseModel):
    activity_draft: dict[str, str]


class SaveLocalResponse(BaseModel):
    saved_path: str
    slug: str


class NotionCreateDraftRequest(BaseModel):
    activity_draft: dict[str, str]


class NotionCreateDraftResponse(BaseModel):
    notion_id: str
    notion_url: str
    draft_property: str
    draft_value: Any


class CombinedPublishRequest(BaseModel):
    activity_draft: dict[str, str]


class CombinedPublishNotionResult(BaseModel):
    id: str = ""
    url: str = ""
    created: bool = False


class CombinedPublishWebflowResult(BaseModel):
    id: str = ""
    collection_id: str = ""
    cms_locale_ids: list[str] = Field(default_factory=list)
    is_draft: bool = True
    is_archived: bool = False
    created: bool = False


class CombinedPublishResponse(BaseModel):
    success: bool
    notion: CombinedPublishNotionResult
    webflow: CombinedPublishWebflowResult
    errors: list[str] = Field(default_factory=list)
