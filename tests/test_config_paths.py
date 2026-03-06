from pathlib import Path

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

