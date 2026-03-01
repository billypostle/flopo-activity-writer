import json

from app.generator import _run_qc_editor_pass
from app.validators import validate_draft


def _base_draft():
    return {
        "Activity Title": "Exploring winter textures in a small world sensory tray",
        "Themes": "Winter; Small world play",
        "Activity Summary": "This activity invites children to explore winter textures in open-ended play. Adults support language and shared attention without over-directing.",
        "Learning Objectives": "Children may notice texture, temperature and changes as they manipulate materials.",
        "Observation Cues": "Adults notice language, turn-taking and repeated choices.",
        "Linked materials": "",
        "Materials": "Builders tuff tray; Cotton wool; Ice cubes; Small world animals",
        "Step-by-Step Guidance": "Prepare a tray and offer a small set of winter-themed resources. Invite child-led exploration while observing and supporting.",
        "Adult Role": "Stay nearby, model simple language, and scaffold conflict resolution only when needed.",
        "Age Adaptation: 0-12 months (Little Learners)": "",
        "Age Adaptation: 12-24 months (Early Explorers)": "Offer fewer materials and simple language prompts.",
        "Age Adaptation: 2 years (Budding Adventurers)": "Add opportunities for symbolic play and short shared turns.",
        "Age Adaptation: 3 years (Curious Investigators)": "Invite predictions and comparison language during play.",
        "Age Adaptation: 4 years (Confident Discoverers)": "Encourage collaborative planning and reflection.",
        "Space Required": "A clear floor area around a low tray.",
        "Time Required": "20-30 minutes.",
        "Safety Considerations": "Supervise closely. Check loose parts for choking risk. Monitor wet surfaces to reduce slipping hazards.",
        "EYFS (2024) Links with Explanation": "Communication and Language is supported as adults model vocabulary. Physical Development is supported through grasping and scooping. Understanding the World is supported through sensory exploration of winter materials.",
        "Ethos Adaptation: Montessori": "Prepare a calm, ordered tray with limited materials and clear boundaries. The adult offers quiet observation and only models once. The adult notices concentration and responds by preserving uninterrupted work cycles.",
        "Ethos Adaptation: Forest School": "Move the activity outdoors using natural resources. The adult supports risk-managed exploration and adapts to weather changes. The adult observes resilience, problem-solving and collaboration in the outdoor space.",
        "Ethos Adaptation: Reggio Emilia": "Rearrange the environment with an intentional invitation table near natural light and visible documentation space. The adult documents language and collaboration, then responds with follow-up provocations. The adult observes group meaning-making and adjusts materials accordingly.",
        "Ethos Adaptation: Steiner (Waldorf)": "Use natural fibres and muted colours with a gentle rhythm. The adult models calm language and pacing. The adult notices emotional state, responds to fluctuations in engagement, and adapts tempo to support regulation.",
        "Preview content": "Children run their hands through cotton wool and pause when ice cubes slide across the tray. An adult crouches nearby, naming rough, smooth and cold as children compare what they feel.",
    }


def test_qc_pass_true_returns_unchanged_draft(monkeypatch):
    draft = _base_draft()
    fields = list(draft.keys())
    report = validate_draft(draft, fields)

    monkeypatch.setattr(
        "app.generator._openai_chat",
        lambda *_args, **_kwargs: json.dumps(
            {
                "pass": True,
                "spec_version": "1.0.0",
                "issues": [],
                "fields_to_edit": [],
                "revised_fields": {},
                "editor_notes": "No changes required.",
            }
        ),
    )

    updated, qc_report = _run_qc_editor_pass(
        draft, {"spec_version": "1.0.0", "spec_text": "x"}, fields, report
    )

    assert updated == draft
    assert qc_report.applied is True
    assert qc_report.passed is True
    assert qc_report.edited_fields == []


def test_qc_targeted_edit_updates_only_flagged_fields(monkeypatch):
    draft = _base_draft()
    draft["Preview content"] = (
        "A brief excerpt showing children exploring shapes. "
        "The preview hints at open-ended dialogue while withholding the full steps."
    )
    fields = list(draft.keys())
    report = validate_draft(draft, fields)

    new_preview = (
        "Children press snowflake cutters into damp dough while an adult sits beside them, "
        "naming edges and counting points as they compare each shape."
    )
    monkeypatch.setattr(
        "app.generator._openai_chat",
        lambda *_args, **_kwargs: json.dumps(
            {
                "pass": False,
                "spec_version": "1.0.0",
                "issues": [
                    {
                        "severity": "blocker",
                        "section": "Preview content",
                        "rule": "Preview must avoid meta-language",
                        "evidence": "The preview hints at open-ended dialogue...",
                        "fix": "Replace with in-scene excerpt only.",
                    }
                ],
                "fields_to_edit": ["Preview content"],
                "revised_fields": {"Preview content": new_preview},
                "editor_notes": "Updated scene detail.",
            }
        ),
    )

    updated, qc_report = _run_qc_editor_pass(
        draft, {"spec_version": "1.0.0", "spec_text": "x"}, fields, report
    )

    assert updated["Preview content"] == new_preview
    assert updated["Activity Title"] == draft["Activity Title"]
    assert qc_report.applied is True
    assert "Preview content" in qc_report.edited_fields


def test_qc_invalid_field_names_are_ignored(monkeypatch):
    draft = _base_draft()
    fields = list(draft.keys())
    report = validate_draft(draft, fields)

    monkeypatch.setattr(
        "app.generator._openai_chat",
        lambda *_args, **_kwargs: json.dumps(
            {
                "pass": False,
                "spec_version": "1.0.0",
                "issues": [
                    {
                        "severity": "minor",
                        "section": "Not A Real Field",
                        "rule": "Field must be in allowed list",
                        "evidence": "Not A Real Field",
                        "fix": "Remove unsupported field.",
                    }
                ],
                "fields_to_edit": ["Not A Real Field"],
                "revised_fields": {"Not A Real Field": "value"},
                "editor_notes": "Ignored invalid field.",
            }
        ),
    )

    updated, qc_report = _run_qc_editor_pass(
        draft, {"spec_version": "1.0.0", "spec_text": "x"}, fields, report
    )

    assert updated == draft
    assert qc_report.applied is True
    assert qc_report.edited_fields == []


def test_qc_malformed_json_fail_open(monkeypatch):
    draft = _base_draft()
    fields = list(draft.keys())
    report = validate_draft(draft, fields)

    monkeypatch.setattr("app.generator._openai_chat", lambda *_args, **_kwargs: "not json")

    updated, qc_report = _run_qc_editor_pass(
        draft, {"spec_version": "1.0.0", "spec_text": "x"}, fields, report
    )

    assert updated == draft
    assert qc_report.applied is False
    assert qc_report.error


def test_qc_edits_discarded_when_validation_gets_worse(monkeypatch):
    draft = _base_draft()
    fields = list(draft.keys())
    report = validate_draft(draft, fields)

    monkeypatch.setattr(
        "app.generator._openai_chat",
        lambda *_args, **_kwargs: json.dumps(
            {
                "pass": True,
                "spec_version": "1.0.0",
                "issues": [],
                "fields_to_edit": ["Preview content"],
                "revised_fields": {"Preview content": "Brief preview excerpt with full steps."},
                "editor_notes": "Changed preview wording.",
            }
        ),
    )

    updated, qc_report = _run_qc_editor_pass(
        draft, {"spec_version": "1.0.0", "spec_text": "x"}, fields, report
    )

    assert updated == draft
    assert qc_report.applied is True
    assert qc_report.passed is False
    assert any("discarded" in issue.lower() for issue in qc_report.issues)
