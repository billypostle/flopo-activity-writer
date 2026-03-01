from __future__ import annotations

import re
from typing import Iterable

from .config import ALLOWED_EMPTY_FIELDS, BANNED_PHRASES, REQUIRED_ETHOS_FIELDS
from .models import ValidationReport
from .resources import normalize_label


def _non_empty(value: str | None) -> bool:
    return bool((value or "").strip())


def _sentence_count(text: str) -> int:
    return len([s for s in re.split(r"[.!?]+", text) if s.strip()])


def _contains_step_leakage(text: str) -> bool:
    leakage_terms = [
        r"\bstep\b",
        r"\bstep-by-step\b",
        r"\bprepare\b",
        r"\bset up\b",
        r"\barrange\b",
        r"\bplace\b",
        r"\bintroduce\b",
        r"\bmodel\b",
    ]
    sequencing_terms = [
        r"\bfirst\b",
        r"\bthen\b",
        r"\bafter\b",
        r"\bnext\b",
        r"\bfinally\b",
    ]
    lower = text.lower()
    leakage_hits = sum(1 for term in leakage_terms if re.search(term, lower))
    sequencing_hits = sum(1 for term in sequencing_terms if re.search(term, lower))
    return leakage_hits >= 2 or (leakage_hits >= 1 and sequencing_hits >= 1) or sequencing_hits >= 3


def validate_title(title: str) -> list[str]:
    issues = []
    t = title.strip()
    if not t:
        return ["Activity title is empty."]
    if "?" in t or "!" in t:
        issues.append("Activity title must not contain question or exclamation marks.")
    if len(t.split()) < 4:
        issues.append("Activity title is too short; use a clear long-tail descriptive format.")
    if t[0].islower():
        issues.append("Activity title should begin with sentence case capitalization.")
    return issues


def validate_section_completeness(
    draft: dict[str, str], expected_fields: Iterable[str]
) -> list[str]:
    issues = []
    for raw_field in expected_fields:
        field = normalize_label(raw_field)
        if field in ALLOWED_EMPTY_FIELDS:
            continue
        if not _non_empty(draft.get(field, "")):
            issues.append(f"Missing required field content: {field}")
    return issues


def validate_summary_and_preview(draft: dict[str, str]) -> list[str]:
    issues = []
    summary = draft.get("Activity Summary", "")
    preview = draft.get("Preview content", "")

    if not _non_empty(summary):
        issues.append("Activity Summary is required.")
    else:
        sentence_total = _sentence_count(summary)
        if sentence_total < 2 or sentence_total > 5:
            issues.append("Activity Summary must be 2-5 sentences.")

    if not _non_empty(preview):
        issues.append("Preview content is required.")
    return issues


def validate_preview_quality(draft: dict[str, str]) -> list[str]:
    issues = []
    preview = draft.get("Preview content", "")
    if not _non_empty(preview):
        return issues

    lower = preview.lower()
    meta_patterns = [
        r"\bpreview\b",
        r"\bpreview content\b",
        r"\bexcerpt\b",
        r"\bhints?\b",
        r"\bteases?\b",
        r"\boverview\b",
        r"\bwithhold(?:ing)?\b",
        r"\bwithout\s+(?:revealing|disclosing)\b",
        r"\bdisclos(?:e|ing)\b",
        r"\breveal(?:ing)?\b",
        r"\bfull steps?\b",
        r"\bfull instructional steps?\b",
        r"\binstructional steps?\b",
        r"\bfull activity\b",
        r"\bcomplete guide\b",
        r"\bin this section\b",
        r"\bthis is a brief preview\b",
        r"\bthe preview\b",
    ]
    matched = [p for p in meta_patterns if re.search(p, lower)]
    if matched:
        issues.append(
            "Preview content uses meta-language; write an in-activity excerpt, not commentary about the preview."
        )

    concrete_patterns = [
        r"\bchild(?:ren)?\b",
        r"\bbaby|babies|toddler(?:s)?\b",
        r"\badult(?:s)?\b",
        r"\bpractitioner(?:s)?\b",
        r"\bmaterial(?:s)?\b",
        r"\bcount(?:ing)?\b",
        r"\bsort(?:ing)?\b",
        r"\bexplor(?:e|ing|ation)\b",
        r"\btray\b",
        r"\bbasket\b",
        r"\btable\b",
        r"\bfloor\b",
    ]
    concrete_hits = sum(1 for p in concrete_patterns if re.search(p, lower))
    if concrete_hits < 2:
        issues.append(
            "Preview content is too abstract; include concrete child/adult/material actions from the activity scene."
        )

    actor_patterns = [
        r"\bchild(?:ren)?\b",
        r"\bbaby|babies|toddler(?:s)?\b",
        r"\badult(?:s)?\b",
        r"\bpractitioner(?:s)?\b",
    ]
    if not any(re.search(p, lower) for p in actor_patterns):
        issues.append(
            "Preview content must include explicit scene actors (children and/or adults), not generic activity description."
        )

    numbered_steps = len(re.findall(r"(?:^|\n)\s*\d+\.\s+", preview))
    imperative_verbs = [
        r"\bprepare\b",
        r"\bset up\b",
        r"\bintroduce\b",
        r"\bplace\b",
        r"\barrange\b",
        r"\bgather\b",
        r"\binvite\b",
    ]
    imperative_hits = sum(1 for p in imperative_verbs if re.search(p, lower))
    if numbered_steps >= 2 or imperative_hits >= 3:
        issues.append(
            "Preview content appears to give away procedural flow (major): reduce numbered steps/imperatives."
        )

    return issues


def validate_section_order(draft: dict[str, str], expected_fields: Iterable[str]) -> list[str]:
    expected = [normalize_label(field) for field in expected_fields]
    expected_set = set(expected)
    observed = [normalize_label(key) for key in draft.keys() if normalize_label(key) in expected_set]
    if observed != expected:
        return ["Section order mismatch: draft keys must match the canonical CSV field order exactly."]
    return []


def validate_summary_and_preview_warnings(draft: dict[str, str]) -> list[str]:
    warnings = []
    summary = draft.get("Activity Summary", "")
    preview = draft.get("Preview content", "")
    if _non_empty(summary) and _contains_step_leakage(summary):
        warnings.append("Activity Summary may include setup/procedural detail.")
    if _non_empty(preview) and _contains_step_leakage(preview):
        warnings.append("Preview content may reveal too much setup/procedural detail.")
    return warnings


def _ethos_has_three_decisions(text: str) -> bool:
    verbs = [
        "arrange",
        "prepare",
        "offer",
        "position",
        "observe",
        "notice",
        "respond",
        "shift",
        "model",
        "adapt",
        "document",
        "support",
    ]
    lower = text.lower()
    count = sum(1 for v in verbs if v in lower)
    return count >= 3


def validate_ethos_depth(draft: dict[str, str]) -> list[str]:
    issues = []
    for field in REQUIRED_ETHOS_FIELDS:
        value = draft.get(field, "")
        if not _non_empty(value):
            issues.append(f"{field} is required.")
            continue
        if _sentence_count(value) < 3:
            issues.append(f"{field} is too shallow; provide fuller adaptation detail.")
        if not _ethos_has_three_decisions(value):
            issues.append(f"{field} must include at least three distinct adult decisions.")

    reggio = draft.get("Ethos Adaptation: Reggio Emilia", "").lower()
    reggio_env_terms = ["environment", "space", "layout", "display", "materials", "studio"]
    if reggio and not any(term in reggio for term in reggio_env_terms):
        issues.append("Reggio Emilia adaptation must include an explicit physical environment change.")
    return issues


def validate_eyfs_and_safety(draft: dict[str, str]) -> list[str]:
    issues = []
    eyfs = draft.get("EYFS (2024) Links with Explanation", "")
    safety = draft.get("Safety Considerations", "")
    eyfs_terms = [
        "communication and language",
        "physical development",
        "personal, social and emotional",
        "literacy",
        "mathematics",
        "understanding the world",
        "expressive arts and design",
    ]
    if len(eyfs.strip()) < 80:
        issues.append("EYFS links are too short; include clear explanation.")
    elif not any(term in eyfs.lower() for term in eyfs_terms):
        issues.append("EYFS links must name at least one specific EYFS area.")

    if len(safety.strip()) < 40:
        issues.append("Safety Considerations are too brief; provide explicit age-aware detail.")
    safety_terms = ["supervis", "choking", "risk", "safe", "hazard"]
    if safety and not any(term in safety.lower() for term in safety_terms):
        issues.append("Safety Considerations should include concrete supervision/hazard language.")
    return issues


def validate_style(draft: dict[str, str], expected_fields: Iterable[str]) -> list[str]:
    issues = []
    text_blob = "\n".join(draft.get(field, "") for field in expected_fields)
    lower = text_blob.lower()

    for phrase in BANNED_PHRASES:
        if phrase in lower:
            issues.append(f"Banned phrase used: {phrase}")

    passive_matches = re.findall(r"\b(is|are|was|were|be|been|being)\s+\w+(?:ed|en)\b", lower)
    if len(passive_matches) > 14:
        issues.append("Draft likely overuses passive voice.")
    return issues


def validate_draft(draft: dict[str, str], expected_fields: Iterable[str]) -> ValidationReport:
    fields = [normalize_label(f) for f in expected_fields]
    normalized_draft = {normalize_label(k): v for k, v in draft.items()}

    blocking_issues: list[str] = []
    warnings: list[str] = []

    blocking_issues.extend(validate_title(normalized_draft.get("Activity Title", "")))
    blocking_issues.extend(validate_section_completeness(normalized_draft, fields))
    blocking_issues.extend(validate_section_order(draft, fields))
    blocking_issues.extend(validate_summary_and_preview(normalized_draft))
    blocking_issues.extend(validate_preview_quality(normalized_draft))
    blocking_issues.extend(validate_ethos_depth(normalized_draft))
    blocking_issues.extend(validate_eyfs_and_safety(normalized_draft))
    warnings.extend(validate_summary_and_preview_warnings(normalized_draft))
    warnings.extend(validate_style(normalized_draft, fields))

    return ValidationReport(
        passed=len(blocking_issues) == 0,
        blocking_issues=blocking_issues,
        warnings=warnings,
    )
