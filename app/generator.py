from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable

import requests

from .config import ALLOWED_EMPTY_FIELDS, MAX_REWRITE_ATTEMPTS, OPENAI_API_KEY, OPENAI_MODEL, OPENAI_QC_MODEL
from .models import GenerateDraftRequest, QCReport, ValidationReport
from .resources import load_model_spec_only, load_runtime_ethos_skill_docs, normalize_label, parse_themes
from .validators import validate_draft

OPENAI_URL = "https://api.openai.com/v1/chat/completions"
logger = logging.getLogger(__name__)


def _extract_json(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        text = text.rsplit("```", 1)[0]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start : end + 1])
        raise


def _openai_chat(
    messages: list[dict[str, Any]],
    on_status: Callable[[str], None] | None = None,
    stage_label: str = "generation",
    model: str | None = None,
) -> str:
    def update_status(message: str) -> None:
        if on_status:
            on_status(message)

    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is missing.")

    selected_model = model or OPENAI_MODEL
    base_payload = {
        "model": selected_model,
        "messages": messages,
    }
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    # Some models/accounts reject response_format=json_object on chat completions.
    # Try strict JSON first, then fall back to plain text response parsing.
    payload_attempts = [
        {**base_payload, "temperature": 0.2, "response_format": {"type": "json_object"}},
        {**base_payload, "response_format": {"type": "json_object"}},
        {**base_payload, "temperature": 0.2},
        base_payload,
    ]

    last_error: str | None = None
    last_status_code = 0
    for index, payload in enumerate(payload_attempts, start=1):
        payload_with_stream = {**payload, "stream": True}
        update_status(f"OpenAI {stage_label}: request attempt {index}/{len(payload_attempts)}")
        try:
            with requests.post(
                OPENAI_URL,
                headers=headers,
                json=payload_with_stream,
                timeout=120,
                stream=True,
            ) as response:
                last_status_code = response.status_code
                if response.ok:
                    parts: list[str] = []
                    chars_received = 0
                    next_status_chars = 220
                    last_progress_status_at = 0.0
                    update_status(f"OpenAI {stage_label}: streaming response")
                    for raw_line in response.iter_lines(decode_unicode=True):
                        if not raw_line:
                            continue
                        line = raw_line.strip()
                        if not line.startswith("data:"):
                            continue
                        data_str = line[5:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue
                        delta = (chunk.get("choices") or [{}])[0].get("delta", {})
                        token_text = delta.get("content")
                        if token_text:
                            parts.append(token_text)
                            chars_received += len(token_text)
                            if chars_received >= next_status_chars:
                                now = time.monotonic()
                                if now - last_progress_status_at >= 3.0:
                                    update_status(
                                        f"OpenAI {stage_label}: {chars_received} chars received"
                                    )
                                    last_progress_status_at = now
                                next_status_chars = chars_received + 220

                    content = "".join(parts).strip()
                    if content:
                        update_status(
                            f"OpenAI {stage_label}: stream complete ({len(content)} chars)"
                        )
                        return content
                    last_error = "OpenAI stream completed without content."
                else:
                    last_error = response.text
                # Retry only for request-shape issues, not auth/quota/server failures.
                if response.status_code != 400:
                    break
        except requests.RequestException as exc:
            last_error = str(exc)
            break

    raise RuntimeError(
        f"OpenAI request failed ({last_status_code}). "
        f"Model={selected_model}. Response: {last_error or '<empty>'}"
    )


def _field_schema_prompt(content_fields: list[str]) -> str:
    structure = {field: "string" for field in content_fields}
    return json.dumps(structure, indent=2)


def _estimate_tokens(messages: list[dict[str, Any]]) -> int:
    total_chars = 0
    for message in messages:
        content = str(message.get("content", ""))
        total_chars += len(content)
    return max(1, total_chars // 4)


def _ethos_skill_docs_prompt(ethos_skill_docs: dict[str, str]) -> str:
    sections: list[str] = []
    for name, text in ethos_skill_docs.items():
        clean = str(text or "").strip()
        if clean:
            sections.append(f"## {name}\n{clean}")
    if not sections:
        return ""
    return (
        "Runtime ethos skill docs (prefer these Notion-backed docs for ethos adaptation "
        "content; local files are fallback only):\n"
        + "\n\n".join(sections)
    )


def _approved_themes_prompt() -> str:
    themes = parse_themes()
    if not themes:
        return ""
    return (
        "Approved Webflow CMS themes for the Themes field (use exact names only; separate multiple themes with semicolons, never commas):\n"
        + "\n".join(f"- {theme}" for theme in themes)
    )


def _system_prompt(
    model_spec: dict[str, Any],
    content_fields: list[str],
    ethos_skill_docs: dict[str, str],
) -> str:
    spec_version = str(model_spec.get("spec_version", "")).strip()
    spec_text = str(model_spec.get("spec_text", "")).strip()
    if not spec_version or not spec_text:
        raise RuntimeError("Model spec is incomplete. Expected spec_version and non-empty spec_text.")
    ethos_docs_text = _ethos_skill_docs_prompt(ethos_skill_docs)
    ethos_section = f"\n\n{ethos_docs_text}" if ethos_docs_text else ""
    themes_text = _approved_themes_prompt()
    themes_section = f"\n\n{themes_text}" if themes_text else ""
    return (
        "You are a specialist FloPo activity writer. "
        "Generate content that strictly follows the Model Spec. "
        "Return strict JSON object only with exactly these keys and no extras:\n"
        f"{_field_schema_prompt(content_fields)}\n\n"
        "Constraints:\n"
        "- Keep plain text only (no HTML).\n"
        "- Keep the exact field names.\n"
        "- Do not leave required fields blank except optional age adaptation fields.\n"
        "- Title must be long-tail sentence case and descriptive.\n"
        "- Summary should be 2-5 sentences and primarily non-procedural.\n"
        "- Preview content must be useful but intentionally incomplete.\n"
        "- Preview content must read like a real in-activity excerpt, not commentary.\n"
        "- Preview content must not use meta words such as: preview, excerpt, hint, withhold, full steps.\n"
        "- Preview content must not discuss what is withheld/revealed/disclosed.\n"
        "- Preview content must include explicit actors (children and/or adults) doing something.\n"
        "- Preview content should include concrete child/adult/material details.\n"
        "- Themes must be separated with semicolons (`Theme; Theme`), never commas.\n"
        "- Ethos adaptations must be concrete and deep.\n\n"
        "Conflict resolution policy:\n"
        "- If any other instruction conflicts, the Model Spec wins.\n\n"
        f"spec_version: {spec_version}\n\n"
        "Model Spec (authoritative ruleset):\n"
        f"{spec_text}"
        f"{themes_section}"
        f"{ethos_section}"
    )


def _user_prompt(request: GenerateDraftRequest, model_spec: dict[str, Any]) -> str:
    spec_version = str(model_spec.get("spec_version", "")).strip()
    return (
        f"spec_version: {spec_version}\n\n"
        "Source notes:\n"
        f"{request.notes}\n\n"
        "Use only the notes, Model Spec and approved Webflow CMS theme list to infer all content fields, including themes, age adaptations, materials, and contextual framing."
    )


def _rewrite_prompt(
    draft: dict[str, str],
    issues: list[str],
    content_fields: list[str],
    model_spec: dict[str, Any],
    ethos_skill_docs: dict[str, str],
) -> str:
    spec_version = str(model_spec.get("spec_version", "")).strip()
    spec_text = str(model_spec.get("spec_text", "")).strip()
    ethos_docs_text = _ethos_skill_docs_prompt(ethos_skill_docs)
    ethos_section = f"\n\n{ethos_docs_text}" if ethos_docs_text else ""
    themes_text = _approved_themes_prompt()
    themes_section = f"\n\n{themes_text}" if themes_text else ""
    return (
        "Rewrite the activity JSON to resolve only the blocking issues below while preserving all fields.\n"
        f"Issues:\n- " + "\n- ".join(issues) + "\n\n"
        "Important rewrite rules:\n"
        "- Preserve all keys exactly.\n"
        "- Only edit fields implicated by the blocking issues.\n"
        "- For Preview content, write an in-activity snippet only; no meta wording about previews/excerpts.\n"
        "- For Themes, use only exact approved Webflow CMS theme names.\n"
        "- For Themes, separate multiple values with semicolons (`Theme; Theme`), never commas.\n"
        "- Keep Preview content useful but incomplete without describing what is withheld/revealed/disclosed.\n"
        "- Include explicit scene actors (children/adults) and concrete materials/actions.\n\n"
        f"spec_version: {spec_version}\n\n"
        "Model Spec (authoritative ruleset):\n"
        f"{spec_text}"
        f"{themes_section}"
        f"{ethos_section}\n\n"
        "Return strict JSON only with exactly these keys:\n"
        f"{_field_schema_prompt(content_fields)}\n\n"
        "Current draft JSON:\n"
        f"{json.dumps(draft, ensure_ascii=False)}"
    )


def _qc_system_prompt(
    model_spec: dict[str, Any],
    content_fields: list[str],
    ethos_skill_docs: dict[str, str],
) -> str:
    spec_version = str(model_spec.get("spec_version", "")).strip()
    spec_text = str(model_spec.get("spec_text", "")).strip()
    ethos_docs_text = _ethos_skill_docs_prompt(ethos_skill_docs)
    ethos_section = f"\n\n{ethos_docs_text}" if ethos_docs_text else ""
    themes_text = _approved_themes_prompt()
    themes_section = f"\n\n{themes_text}" if themes_text else ""
    return (
        "You are FloPo QC Editor, a strict validating editor. "
        "Your task is to review the provided draft against the Model Spec and output only targeted fixes.\n\n"
        "Rules:\n"
        "- The Model Spec is the only authoritative writing ruleset.\n"
        "- Do not rewrite the whole draft unless every field fails.\n"
        "- Edit only fields that fail the spec.\n"
        "- Preserve field names exactly.\n"
        "- Keep plain text only. No HTML.\n"
        "- Keep child/adult realism, concrete context, and age-aware safety detail.\n"
        "- Themes must use only exact approved Webflow CMS theme names.\n"
        "- Themes must separate multiple values with semicolons (`Theme; Theme`), never commas.\n"
        "- Do not introduce meta commentary about preview in Preview content.\n"
        "- revised_fields keys must be a subset of fields_to_edit.\n"
        "- Never include fields outside the allowed field list.\n\n"
        "Return strict JSON only with this exact shape:\n"
        "{\n"
        '  "pass": boolean,\n'
        '  "spec_version": "1.0.0",\n'
        '  "issues": [\n'
        "    {\n"
        '      "severity": "blocker|major|minor",\n'
        '      "section": "Field Name",\n'
        '      "rule": "Rule text",\n'
        '      "evidence": "Quoted failing text",\n'
        '      "fix": "Required correction summary"\n'
        "    }\n"
        "  ],\n"
        '  "fields_to_edit": ["Field Name"],\n'
        '  "revised_fields": {"Field Name": "Rewritten content"},\n'
        '  "editor_notes": "short note"\n'
        "}\n\n"
        f"spec_version: {spec_version}\n\n"
        "Model Spec (authoritative ruleset):\n"
        f"{spec_text}"
        f"{themes_section}"
        f"{ethos_section}\n\n"
        "Allowed fields:\n"
        f"{json.dumps(content_fields, ensure_ascii=False)}"
    )


def _qc_user_prompt(draft: dict[str, str], content_fields: list[str], model_spec: dict[str, Any]) -> str:
    spec_version = str(model_spec.get("spec_version", "")).strip()
    return (
        f"spec_version: {spec_version}\n\n"
        "Allowed fields:\n"
        f"{json.dumps(content_fields, ensure_ascii=False)}\n\n"
        "Current draft JSON:\n"
        f"{json.dumps(draft, ensure_ascii=False)}\n\n"
        "Evaluate this draft against the Model Spec.\n"
        "If acceptable, set pass=true and return empty fields_to_edit/revised_fields.\n"
        "If not acceptable, list issues and provide corrected text only for failing fields."
    )


def _normalize_field_keys(draft: dict[str, Any], content_fields: list[str]) -> dict[str, str]:
    draft_norm = {
        normalize_label(str(k)): (v if isinstance(v, str) else str(v or ""))
        for k, v in draft.items()
    }
    output: dict[str, str] = {}
    for field in content_fields:
        f = normalize_label(field)
        output[f] = draft_norm.get(f, "")
    return output


def _run_qc_editor_pass(
    draft: dict[str, str],
    model_spec: dict[str, Any],
    ethos_skill_docs: dict[str, str],
    content_fields: list[str],
    pre_qc_report: ValidationReport,
    on_status: Callable[[str], None] | None = None,
) -> tuple[dict[str, str], QCReport]:
    def update_status(message: str) -> None:
        if on_status:
            on_status(message)

    qc_system = _qc_system_prompt(model_spec, content_fields, ethos_skill_docs)
    qc_user = _qc_user_prompt(draft, content_fields, model_spec)
    logger.info(
        "Estimated prompt tokens (qc editor): %s",
        _estimate_tokens(
            [
                {"role": "system", "content": qc_system},
                {"role": "user", "content": qc_user},
            ]
        ),
    )

    try:
        raw = _openai_chat(
            [
                {"role": "system", "content": qc_system},
                {"role": "user", "content": qc_user},
            ],
            on_status=update_status,
            stage_label="qc editor",
            model=OPENAI_QC_MODEL,
        )
        payload = _extract_json(raw)
    except Exception as exc:
        return draft, QCReport(
            applied=False,
            passed=False,
            edited_fields=[],
            issues=[],
            error=f"QC pass fail-open: {exc}",
        )

    if not isinstance(payload, dict):
        return draft, QCReport(
            applied=False,
            passed=False,
            edited_fields=[],
            issues=[],
            error="QC pass fail-open: response was not a JSON object.",
        )

    try:
        pass_value = payload["pass"]
        spec_version_value = str(payload["spec_version"])
        issues_raw = payload["issues"]
        fields_to_edit_raw = payload["fields_to_edit"]
        revised_fields_raw = payload["revised_fields"]
        editor_notes = payload["editor_notes"]
        if not isinstance(pass_value, bool):
            raise ValueError("QC pass must be boolean.")
        if not isinstance(issues_raw, list) or not isinstance(fields_to_edit_raw, list):
            raise ValueError("QC issues/fields_to_edit must be arrays.")
        if not isinstance(revised_fields_raw, dict):
            raise ValueError("QC revised_fields must be an object.")
        if not isinstance(editor_notes, str):
            raise ValueError("QC editor_notes must be a string.")
        if not spec_version_value:
            raise ValueError("QC spec_version must be non-empty.")
    except (KeyError, ValueError, TypeError) as exc:
        return draft, QCReport(
            applied=False,
            passed=False,
            edited_fields=[],
            issues=[],
            error=f"QC pass fail-open: invalid QC response schema ({exc}).",
        )

    issues: list[str] = []
    for item in issues_raw:
        if not isinstance(item, dict):
            continue
        severity = str(item.get("severity", "")).strip().lower()
        section = str(item.get("section", "")).strip()
        rule = str(item.get("rule", "")).strip()
        evidence = str(item.get("evidence", "")).strip()
        fix = str(item.get("fix", "")).strip()
        if not (severity and section and rule and evidence and fix):
            continue
        issues.append(f"{severity.upper()} | {section} | {rule} | Evidence: {evidence} | Fix: {fix}")
    expected_spec_version = str(model_spec.get("spec_version", "")).strip()
    if spec_version_value != expected_spec_version:
        issues.append(
            f"QC response spec_version mismatch (got {spec_version_value}, expected {expected_spec_version})."
        )
    allowed = {normalize_label(f) for f in content_fields}
    fields_to_edit = {
        normalize_label(str(field).strip())
        for field in fields_to_edit_raw
        if normalize_label(str(field).strip()) in allowed
    }
    revised_fields: dict[str, str] = {}
    for key, value in revised_fields_raw.items():
        field = normalize_label(str(key))
        if field in allowed and isinstance(value, str):
            revised_fields[field] = value

    editable = [field for field in content_fields if field in fields_to_edit]
    edited_fields: list[str] = []
    merged = dict(draft)
    for field in editable:
        if field not in revised_fields:
            continue
        next_value = revised_fields[field]
        if field not in ALLOWED_EMPTY_FIELDS and not next_value.strip():
            continue
        if merged.get(field, "") != next_value:
            merged[field] = next_value
            edited_fields.append(field)

    if set(revised_fields.keys()) - fields_to_edit:
        issues.append("QC response included revised_fields outside fields_to_edit; ignored extras.")

    merged_report = validate_draft(merged, content_fields)
    if len(merged_report.blocking_issues) > len(pre_qc_report.blocking_issues):
        issues.append("QC edits were discarded because they increased blocking issues.")
        return draft, QCReport(
            applied=True,
            passed=False,
            edited_fields=[],
            issues=issues,
            error="",
        )

    return merged, QCReport(
        applied=True,
        passed=pass_value and merged_report.passed,
        edited_fields=edited_fields,
        issues=issues,
        error="",
    )


def generate_activity_draft(
    request: GenerateDraftRequest,
    content_fields: list[str],
    on_status: Callable[[str], None] | None = None,
) -> tuple[dict[str, str], ValidationReport, int, QCReport]:
    def update_status(message: str) -> None:
        if on_status:
            on_status(message)

    update_status("Loading model spec")
    model_spec = load_model_spec_only()
    update_status(f"Model spec ready (v{model_spec.get('spec_version', '')})")
    update_status("Loading runtime ethos skill docs")
    ethos_skill_docs = load_runtime_ethos_skill_docs()
    update_status("Preparing content fields")
    content_fields = [normalize_label(f) for f in content_fields]

    update_status("Building prompts")
    system_prompt = _system_prompt(model_spec, content_fields, ethos_skill_docs)
    user_prompt = _user_prompt(request, model_spec)
    initial_messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    logger.info(
        "Estimated prompt tokens (initial draft): %s",
        _estimate_tokens(initial_messages),
    )

    update_status("Generating initial draft with OpenAI")
    raw = _openai_chat(initial_messages, on_status=update_status, stage_label="initial draft")
    update_status("Parsing draft response")
    draft = _normalize_field_keys(_extract_json(raw), content_fields)
    update_status("Validating initial draft")
    report = validate_draft(draft, content_fields)

    rewrite_count = 0
    while not report.passed and rewrite_count < MAX_REWRITE_ATTEMPTS:
        rewrite_count += 1
        update_status(f"Rewriting draft (attempt {rewrite_count}/{MAX_REWRITE_ATTEMPTS})")
        rewrite_user = _rewrite_prompt(
            draft, report.blocking_issues, content_fields, model_spec, ethos_skill_docs
        )
        rewrite_messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": rewrite_user},
        ]
        logger.info(
            "Estimated prompt tokens (rewrite %s): %s",
            rewrite_count,
            _estimate_tokens(rewrite_messages),
        )
        rewritten_raw = _openai_chat(
            rewrite_messages,
            on_status=update_status,
            stage_label=f"rewrite {rewrite_count}",
        )
        draft = _normalize_field_keys(_extract_json(rewritten_raw), content_fields)
        update_status(f"Validating rewrite attempt {rewrite_count}")
        report = validate_draft(draft, content_fields)

    update_status("Running QC editor pass")
    draft, qc_report = _run_qc_editor_pass(
        draft,
        model_spec,
        ethos_skill_docs,
        content_fields,
        report,
        on_status=update_status,
    )
    if qc_report.applied:
        update_status("QC merge accepted")
    else:
        update_status("QC skipped/fail-open")

    report = validate_draft(draft, content_fields)
    update_status("Finalizing generation result")
    return draft, report, rewrite_count, qc_report
