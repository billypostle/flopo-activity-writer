from pathlib import Path

from app import resources


def test_load_skill_docs_reads_local_files(monkeypatch, tmp_path: Path):
    (tmp_path / "Writing guide.md").write_text("local guide content", encoding="utf-8")

    monkeypatch.setattr(resources, "INCLUDED_SKILL_DOCS", ["Writing guide.md"])
    monkeypatch.setattr(resources, "SKILL_DOCS_DIR", tmp_path)

    docs = resources.load_skill_docs()

    assert docs["Writing guide.md"] == "local guide content"


def test_load_runtime_ethos_skill_docs_uses_router_links(monkeypatch, tmp_path: Path):
    skill_docs = tmp_path / "Skill docs"
    ethos_dir = skill_docs / "Ethos Skills"
    ethos_dir.mkdir(parents=True)

    (skill_docs / "Ethos Definitions.md").write_text(
        "# Ethos Definitions\n\n"
        "Use [[Writing guide]] and [[Montessori Ethos Adaptation - Model Skill Reference]].\n",
        encoding="utf-8",
    )
    (skill_docs / "Writing guide.md").write_text("writing guide content", encoding="utf-8")
    (ethos_dir / "Montessori Ethos Adaptation - Model Skill Reference.md").write_text(
        "montessori content",
        encoding="utf-8",
    )

    monkeypatch.setattr(resources, "SKILL_DOCS_DIR", skill_docs)

    docs = resources.load_runtime_ethos_skill_docs()

    assert docs["Ethos Definitions.md"].startswith("# Ethos Definitions")
    assert docs["Writing guide"] == "writing guide content"
    assert docs["Montessori Ethos Adaptation - Model Skill Reference"] == "montessori content"


def test_load_runtime_ethos_skill_docs_ignores_missing_router_targets(monkeypatch, tmp_path: Path):
    skill_docs = tmp_path / "Skill docs"
    skill_docs.mkdir(parents=True)
    (skill_docs / "Ethos Definitions.md").write_text(
        "# Ethos Definitions\n\nUse [[Missing doc]] only.\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(resources, "SKILL_DOCS_DIR", skill_docs)

    docs = resources.load_runtime_ethos_skill_docs()

    assert list(docs.keys()) == ["Ethos Definitions.md"]


def test_load_model_spec_only_reads_local_spec(monkeypatch, tmp_path: Path):
    skill_docs = tmp_path / "Skill docs"
    skill_docs.mkdir(parents=True)
    (skill_docs / "flo_po_model_facing_activity_spec_v_1.md").write_text(
        "local model spec",
        encoding="utf-8",
    )

    monkeypatch.setattr(resources, "SKILL_DOCS_DIR", skill_docs)
    monkeypatch.setattr(resources, "LOCAL_MODEL_SPEC_DOC", "flo_po_model_facing_activity_spec_v_1.md")

    spec = resources.load_model_spec_only()

    assert spec["spec_text"] == "local model spec"
    assert spec["source"].endswith("flo_po_model_facing_activity_spec_v_1.md")
