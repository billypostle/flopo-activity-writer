import tempfile
from pathlib import Path

from app import config
from app.config import _resolve_repo_root


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
