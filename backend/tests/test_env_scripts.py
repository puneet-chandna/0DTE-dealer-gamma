from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _setup_env(tmp_path: Path, backend: str, frontend: str | None = None) -> Path:
    for directory in ("backend", "frontend"):
        target = tmp_path / directory
        target.mkdir()
        shutil.copy2(REPO_ROOT / directory / ".env.example", target / ".env.example")
    (tmp_path / "backend" / ".env").write_text(backend, encoding="utf-8")
    (tmp_path / "frontend" / ".env.local").write_text(
        frontend or "NEXT_PUBLIC_API_URL=http://localhost:8000\nNEXT_PUBLIC_WS_URL=ws://localhost:8000/ws\n",
        encoding="utf-8",
    )
    venv_bin = tmp_path / "backend" / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    (venv_bin / "python").symlink_to(sys.executable)
    return tmp_path


def _run_setup(sandbox: Path, *args: str, **overrides: str) -> subprocess.CompletedProcess[str]:
    env = {
        "PATH": "/usr/bin:/bin",
        "ODTE_REPO_ROOT": str(sandbox),
        "PYTHONPATH": os.environ.get("PYTHONPATH", ""),
        **overrides,
    }
    return subprocess.run(
        ["bash", str(REPO_ROOT / "scripts" / "setup_env.sh"), *args],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_setup_parses_dotenv_without_executing_shell_and_preserves_files(tmp_path: Path) -> None:
    marker = tmp_path / "executed"
    backend = (
        "DATABASE_URL=postgresql+asyncpg://ignored:secret@localhost:5432/old\n"
        'export DATABASE_URL = "sqlite+aiosqlite:///./quoted.db" # selected\n'
        f"CUSTOM=$(touch {marker})\n"
    )
    frontend = (
        'export NEXT_PUBLIC_API_URL = "https://api.example.test" # comment\n'
        "NEXT_PUBLIC_WS_URL='wss://api.example.test/ws'\n"
    )
    sandbox = _setup_env(tmp_path, backend, frontend)
    completed = _run_setup(sandbox)
    assert completed.returncode == 0, completed.stderr
    assert "DATABASE_URL=sqlite+aiosqlite:///./quoted.db" in completed.stdout
    assert "NEXT_PUBLIC_API_URL=https://api.example.test" in completed.stdout
    assert "NEXT_PUBLIC_WS_URL=wss://api.example.test/ws" in completed.stdout
    assert (sandbox / "backend" / ".env").read_text(encoding="utf-8") == backend
    assert (sandbox / "frontend" / ".env.local").read_text(encoding="utf-8") == frontend
    assert not marker.exists()


def test_setup_environment_database_override_has_backend_precedence(tmp_path: Path) -> None:
    original = "DATABASE_URL=mysql://ignored:secret@localhost/db\nCUSTOM=keep\n"
    sandbox = _setup_env(tmp_path, original)
    database_url = "sqlite+aiosqlite:///./override.db"
    completed = _run_setup(sandbox, DATABASE_URL=database_url)
    assert completed.returncode == 0, completed.stderr
    assert f"DATABASE_URL={database_url}" in completed.stdout
    assert (sandbox / "backend" / ".env").read_text(encoding="utf-8") == original


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("DATABASE_URL", "sqliteevil://example/db"),
        ("DATABASE_URL", "postgresql://"),
        ("DATABASE_URL", "postgresql://localhost:invalid/db"),
        ("DATABASE_URL", "sqlite+aiosqlite:///./invalid\tdatabase.db"),
        ("DATABASE_URL", "sqlite+aiosqlite:///./invalid\x01database.db"),
        ("NEXT_PUBLIC_API_URL", "ftp://localhost:8000"),
        ("NEXT_PUBLIC_API_URL", "http://"),
        ("NEXT_PUBLIC_API_URL", "http://local host:8000"),
        ("NEXT_PUBLIC_WS_URL", "https://localhost:8000/ws"),
        ("NEXT_PUBLIC_WS_URL", "ws://"),
    ],
)
def test_setup_rejects_invalid_url_schemes_and_endpoints(
    tmp_path: Path, key: str, value: str
) -> None:
    sandbox = _setup_env(tmp_path, "DATABASE_URL=sqlite+aiosqlite:///./local.db\n")
    completed = _run_setup(sandbox, **{key: value})
    assert completed.returncode != 0
    assert key in completed.stderr


def test_setup_mode_replaces_exported_url_without_touching_customization(tmp_path: Path) -> None:
    sandbox = _setup_env(
        tmp_path,
        'export DATABASE_URL = "postgresql+asyncpg://localhost:55432/db"\nCUSTOM=keep\n',
    )
    completed = _run_setup(sandbox, "--sqlite")
    assert completed.returncode == 0, completed.stderr
    text = (sandbox / "backend" / ".env").read_text(encoding="utf-8")
    assert text.count("DATABASE_URL") == 1
    assert "DATABASE_URL=sqlite+aiosqlite:///./odte_gex.db" in text
    assert "CUSTOM=keep\n" in text


def test_setup_removes_only_the_stale_root_provider_assignment(tmp_path: Path) -> None:
    sandbox = _setup_env(tmp_path, "DATABASE_URL=sqlite+aiosqlite:///./local.db\n")
    root_env = sandbox / ".env"
    root_env.write_text(
        "# POLYGON_API_KEY was replaced\n"
        "OTHER_POLYGON_API_KEY=keep\n"
        'CUSTOM="POLYGON_API_KEY"\n'
        ' export POLYGON_API_KEY = "stale"\n',
        encoding="utf-8",
    )
    completed = _run_setup(sandbox)
    assert completed.returncode == 0, completed.stderr
    assert root_env.read_text(encoding="utf-8") == (
        "# POLYGON_API_KEY was replaced\nOTHER_POLYGON_API_KEY=keep\n"
        'CUSTOM="POLYGON_API_KEY"\n'
    )


def test_setup_docker_preset_matches_compose_defaults(tmp_path: Path) -> None:
    sandbox = _setup_env(tmp_path, "DATABASE_URL=sqlite+aiosqlite:///./local.db\n")
    completed = _run_setup(sandbox, "--postgres-docker")
    assert completed.returncode == 0, completed.stderr
    assert "DATABASE_URL=postgresql+asyncpg://odte_user:odte_password@localhost:5432/odte_gex" in (
        sandbox / "backend" / ".env"
    ).read_text(encoding="utf-8")


def test_setup_accepts_quoted_sqlite_path_with_spaces(tmp_path: Path) -> None:
    database_url = "sqlite+aiosqlite:///./my database.db"
    sandbox = _setup_env(tmp_path, f'DATABASE_URL="{database_url}"\n')
    completed = _run_setup(sandbox)
    assert completed.returncode == 0, completed.stderr
    assert f"DATABASE_URL={database_url}" in completed.stdout


def test_setup_mode_replaces_all_case_variants_of_database_url(tmp_path: Path) -> None:
    sandbox = _setup_env(
        tmp_path,
        "DATABASE_URL=sqlite+aiosqlite:///./old.db\n"
        "database_url=sqlite+aiosqlite:///./override.db\n"
        "CUSTOM=keep\n",
    )
    completed = _run_setup(sandbox, "--sqlite")
    assert completed.returncode == 0, completed.stderr
    chosen = "sqlite+aiosqlite:///./odte_gex.db"
    assert f"(DATABASE_URL={chosen})" in completed.stdout
    text = (sandbox / "backend/.env").read_text(encoding="utf-8")
    assert f"DATABASE_URL={chosen}\n" in text
    assert f"database_url={chosen}\n" in text
    assert "CUSTOM=keep\n" in text
