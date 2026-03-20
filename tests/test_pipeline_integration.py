import json

from fastapi.testclient import TestClient

from app import main
from app.generator import generate_activity_draft
from app.markdown_writer import save_markdown_to_activities
from app.models import GenerateDraftRequest, QCReport, ValidationReport
from app.resources import content_fields_from_csv


def _mock_activity(content_fields):
    data = {field: "" for field in content_fields}
    data.update(
        {
            "Activity Title": "Sorting and counting foam snowballs by size using number cards",
            "Themes": "Winter; Sorting; Mathematical",
            "Activity Summary": "This activity gives children practical opportunities to sort and count objects. Adults support language and turn-taking through shared play.",
            "Learning Objectives": "Children practise comparing size and counting quantities with one-to-one correspondence.",
            "Observation Cues": "Adults notice counting accuracy, size language and social negotiation.",
            "Materials": "Foam balls; Number cards; Sorting bowls",
            "Step-by-Step Guidance": "Prepare sorting bowls and mixed-size foam balls. Invite children to sort by size and then match quantities with number cards.",
            "Adult Role": "Model counting language, observe first, and scaffold conflict resolution when needed.",
            "Space Required": "Floor space or low table for small groups.",
            "Time Required": "15-25 minutes.",
            "Safety Considerations": "Supervise closely, keep foam balls large enough to avoid choking hazards, and monitor movement around shared baskets.",
            "EYFS (2024) Links with Explanation": "Mathematics is supported through counting and comparing quantity. Communication and Language is supported as adults model comparative vocabulary. Personal, Social and Emotional Development is supported through turn-taking and patience.",
            "Ethos Adaptation: Montessori": "Prepare a limited tray with clearly defined sections and real baskets. The adult demonstrates once and steps back. The adult observes self-correction and independence before offering help.",
            "Ethos Adaptation: Forest School": "Take the activity outdoors and replace foam balls with natural objects. The adult supports risk-managed movement and problem-solving. The adult observes resilience and adapts prompts to the environment.",
            "Ethos Adaptation: Reggio Emilia": "Change the environment by setting an intentional sorting studio with visible collections and documentation materials. The adult documents children's mathematical reasoning, observes group collaboration, and responds by adapting layout and prompts to extend inquiry. The adult then notices how children revisit the display and supports further discussion.",
            "Ethos Adaptation: Steiner (Waldorf)": "Use natural wool balls and a gentle story-led introduction. The adult maintains steady rhythm and calm language. The adult notices emotional regulation, responds to changing attention, and adapts pacing.",
            "Preview content": "Children gather around sorting bowls while an adult kneels nearby and names bigger and smaller as they compare snowballs and count together.",
        }
    )
    return data


def test_generate_validate_and_save_pipeline(monkeypatch, tmp_path):
    fields = content_fields_from_csv()
    mock_data = _mock_activity(fields)
    monkeypatch.setattr(
        "app.generator.load_model_spec_only",
        lambda: {
            "spec_version": "1.0.0",
            "spec_text": "Use FloPo structure and writing quality standards.",
            "spec_hash": "abc",
            "fetched_at": 1.0,
            "source": "https://www.notion.so/spec",
        },
    )
    monkeypatch.setattr(
        "app.generator.load_runtime_ethos_skill_docs",
        lambda: {"Ethos Definitions.md": "runtime ethos guidance"},
    )

    def fake_openai_chat(_messages, **kwargs):
        stage = kwargs.get("stage_label", "")
        if stage == "qc editor":
            return json.dumps(
                {
                    "pass": True,
                    "spec_version": "1.0.0",
                    "issues": [],
                    "fields_to_edit": [],
                    "revised_fields": {},
                    "editor_notes": "No changes required.",
                },
                ensure_ascii=False,
            )
        return json.dumps(mock_data, ensure_ascii=False)

    monkeypatch.setattr("app.generator._openai_chat", fake_openai_chat)

    request = GenerateDraftRequest(notes="Children enjoyed sorting snowballs by size.")
    draft, report, rewrites, qc_report = generate_activity_draft(request, fields)

    assert report.passed is True
    assert rewrites == 0
    assert qc_report.applied is True
    path, _ = save_markdown_to_activities(draft, fields, output_dir=tmp_path)
    assert path.exists()


def test_generate_includes_runtime_ethos_skill_docs(monkeypatch):
    fields = content_fields_from_csv()
    mock_data = _mock_activity(fields)
    monkeypatch.setattr(
        "app.generator.load_model_spec_only",
        lambda: {
            "spec_version": "1.0.0",
            "spec_text": "authoritative model spec",
            "spec_hash": "abc",
            "fetched_at": 1.0,
            "source": "https://www.notion.so/spec",
        },
    )
    monkeypatch.setattr(
        "app.generator.load_runtime_ethos_skill_docs",
        lambda: {
            "Ethos Definitions.md": "master ethos router",
            "Montessori Ethos Skill Doc": "montessori runtime guidance",
        },
    )

    captured_system_prompts: list[str] = []

    def fake_openai_chat(messages, **kwargs):
        stage = kwargs.get("stage_label", "")
        if messages:
            captured_system_prompts.append(str(messages[0].get("content", "")))
        if stage == "qc editor":
            return json.dumps(
                {
                    "pass": True,
                    "spec_version": "1.0.0",
                    "issues": [],
                    "fields_to_edit": [],
                    "revised_fields": {},
                    "editor_notes": "No changes required.",
                },
                ensure_ascii=False,
            )
        return json.dumps(mock_data, ensure_ascii=False)

    monkeypatch.setattr("app.generator._openai_chat", fake_openai_chat)

    request = GenerateDraftRequest(notes="Children explored a winter sensory setup with adults nearby.")
    draft, report, rewrites, qc_report = generate_activity_draft(request, fields)

    assert draft["Activity Title"] == mock_data["Activity Title"]
    assert report.passed is True
    assert rewrites == 0
    assert qc_report.applied is True
    assert any("master ethos router" in prompt for prompt in captured_system_prompts)
    assert any("montessori runtime guidance" in prompt for prompt in captured_system_prompts)


def test_generate_endpoint_loads_runtime_ethos_skill_docs(monkeypatch):
    fields = content_fields_from_csv()
    mock_data = _mock_activity(fields)
    monkeypatch.setattr(
        "app.generator.load_model_spec_only",
        lambda: {
            "spec_version": "1.0.0",
            "spec_text": "authoritative model spec",
            "spec_hash": "abc",
            "fetched_at": 1.0,
            "source": "https://www.notion.so/spec",
        },
    )
    calls = {"ethos_docs": 0}
    monkeypatch.setattr(
        "app.generator.load_runtime_ethos_skill_docs",
        lambda: calls.__setitem__("ethos_docs", calls["ethos_docs"] + 1) or {"Ethos Definitions.md": "runtime ethos guidance"},
    )
    monkeypatch.setattr(main.config, "APP_AUTH_USERNAME", "")
    monkeypatch.setattr(main.config, "APP_AUTH_PASSWORD", "")

    def fake_openai_chat(_messages, **kwargs):
        stage = kwargs.get("stage_label", "")
        if stage == "qc editor":
            return json.dumps(
                {
                    "pass": True,
                    "spec_version": "1.0.0",
                    "issues": [],
                    "fields_to_edit": [],
                    "revised_fields": {},
                    "editor_notes": "No changes required.",
                },
                ensure_ascii=False,
            )
        return json.dumps(mock_data, ensure_ascii=False)

    monkeypatch.setattr("app.generator._openai_chat", fake_openai_chat)

    with TestClient(main.app) as client:
        response = client.post(
            "/api/generate-draft",
            json={"notes": "Children explored a winter sensory setup with adults nearby."},
        )

    assert response.status_code == 200
    assert calls["ethos_docs"] == 1


def test_generate_draft_endpoint_returns_qc_metadata(monkeypatch):
    mock_fields = [
        "Activity Title",
        "Activity Summary",
        "Preview content",
        "Safety Considerations",
        "EYFS (2024) Links with Explanation",
        "Ethos Adaptation: Montessori",
        "Ethos Adaptation: Forest School",
        "Ethos Adaptation: Reggio Emilia",
        "Ethos Adaptation: Steiner (Waldorf)",
    ]
    mock_draft = _mock_activity(mock_fields)
    mock_report = ValidationReport(passed=True, blocking_issues=[], warnings=[])
    mock_qc = QCReport(applied=True, passed=True, edited_fields=[], issues=[], error="")

    monkeypatch.setattr(main, "content_fields_from_csv", lambda: mock_fields)
    monkeypatch.setattr(main, "validate_notion_configuration", lambda: (True, "Notion ready"))
    monkeypatch.setattr(main.config, "APP_AUTH_USERNAME", "")
    monkeypatch.setattr(main.config, "APP_AUTH_PASSWORD", "")
    monkeypatch.setattr(
        main,
        "generate_activity_draft",
        lambda payload, content_fields, on_status=None: (mock_draft, mock_report, 0, mock_qc),
    )
    monkeypatch.setattr(main, "build_markdown", lambda draft, fields: "# Mock")

    with TestClient(main.app) as client:
        response = client.post(
            "/api/generate-draft",
            json={"notes": "Children explored a winter sorting setup with an adult nearby."},
        )

    assert response.status_code == 200
    body = response.json()
    assert "activity_draft" in body
    assert "validation_report" in body
    assert "rewrite_count" in body
    assert "markdown_preview" in body
    assert body["qc_applied"] is True
    assert body["qc_passed"] is True
    assert body["qc_edited_fields"] == []
    assert body["qc_issues"] == []
    assert body["qc_error"] == ""
