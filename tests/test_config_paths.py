import tempfile
from pathlib import Path

from app import config
from app.config import _resolve_repo_root, _resolve_skill_docs_dir


def test_resolve_repo_root_prefers_flopo_layout(tmp_path: Path) -> None:
    generic = tmp_path / "generic"
    generic.mkdir()

    repo = tmp_path / "repo"
    (repo / "Databases").mkdir(parents=True)
    (repo / "Skill docs").mkdir(parents=True)

    fallback = tmp_path / "fallback"
    fallback.mkdir()

    resolved = _resolve_repo_root([generic, repo, fallback], fallback=fallback)
    assert resolved == repo


def test_resolve_repo_root_accepts_documentation_skill_docs_layout(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "Databases").mkdir(parents=True)
    (repo / "Documentation" / "FloPo" / "Skill docs").mkdir(parents=True)

    fallback = tmp_path / "fallback"
    fallback.mkdir()

    resolved = _resolve_repo_root([repo, fallback], fallback=fallback)
    assert resolved == repo


def test_resolve_repo_root_falls_back_to_project_dir(tmp_path: Path) -> None:
    generic = tmp_path / "generic"
    generic.mkdir()

    fallback = tmp_path / "project_dir"
    fallback.mkdir()

    resolved = _resolve_repo_root([generic], fallback=fallback)
    assert resolved == fallback


def test_resolve_model_spec_cache_path_uses_tmp_on_vercel(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(config, "PROJECT_DIR", Path("C:/vercel/path0"))
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("FLOPO_MODEL_SPEC_CACHE_PATH", ".cache/model_spec.json")

    resolved = config._resolve_model_spec_cache_path()
    assert resolved == Path(tempfile.gettempdir()) / "model_spec.json"


def test_parse_allowed_origins_normalizes_and_deduplicates() -> None:
    parsed = config._parse_allowed_origins(
        "https://flopo.co.uk, https://flopo-stage.webflow.io/writer, https://flopo-stage.webflow.io"
    )
    assert parsed == ["https://flopo.co.uk", "https://flopo-stage.webflow.io"]


def test_resolve_skill_docs_dir_falls_back_to_bundled_docs(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    bundled = tmp_path / "project" / "config" / "skill_docs"
    bundled.mkdir(parents=True)

    monkeypatch.setattr(config, "BUNDLED_SKILL_DOCS_DIR", bundled)

    resolved = _resolve_skill_docs_dir(repo_root)
    assert resolved == bundled
