"""Legacy launcher checks without starting terminals or database services."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def _executable(path: Path, body: str) -> None:
    path.write_text("#!/usr/bin/env bash\n" + body + "\n", encoding="utf-8")
    path.chmod(0o755)


@pytest.fixture
def launcher(tmp_path: Path):
    scripts = tmp_path / "scripts"
    venv_bin = tmp_path / "backend/.venv/bin"
    stub_bin = tmp_path / "bin"
    for directory in (scripts, venv_bin, stub_bin, tmp_path / "frontend"):
        directory.mkdir(parents=True)
    for name in ("start_app.sh", "read_env.py"):
        shutil.copy2(SCRIPTS / name, scripts / name)
    (venv_bin / "python").symlink_to(sys.executable)
    _executable(venv_bin / "uvicorn", "exit 0")
    _executable(
        venv_bin / "alembic",
        'echo migration >> "$STARTUP_TRACE"\nexit "${STARTUP_MIGRATION_STATUS:-0}"',
    )
    _executable(scripts / "cleanup_runtime_state.sh", 'echo cleanup >> "$STARTUP_TRACE"')
    _executable(stub_bin / "pnpm", "exit 0")
    _executable(stub_bin / "gnome-terminal", 'printf "terminal %s\\n" "$*" >> "$STARTUP_TRACE"')
    _executable(
        stub_bin / "python3",
        'if [[ "$1" == "-" && "$2" != *://* ]]; then\n'
        '  printf "wait %s:%s\\n" "$2" "$3" >> "$STARTUP_TRACE"\n'
        "  exit 0\n"
        "fi\n"
        'exec /usr/bin/python3 "$@"',
    )
    env = {
        "PATH": f"{stub_bin}:/usr/bin:/bin",
        "PYTHONPATH": os.environ.get("PYTHONPATH", ""),
        "STARTUP_TRACE": str(tmp_path / "startup.trace"),
    }

    def run(backend_env: str, **overrides: str):
        (tmp_path / "backend/.env").write_text(backend_env, encoding="utf-8")
        return subprocess.run(
            ["bash", str(scripts / "start_app.sh")],
            env={**env, **overrides},
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )

    yield tmp_path, run


def test_legacy_bash_reads_quoted_dotenv_sqlite_without_database_terminal(launcher) -> None:
    root, run = launcher
    database_url = "sqlite+aiosqlite:///./my database.db"
    completed = run(f'export DATABASE_URL = "{database_url}" # local\n')
    assert completed.returncode == 0, completed.stderr
    assert database_url in completed.stdout
    trace = (root / "startup.trace").read_text(encoding="utf-8")
    assert "wait " not in trace
    assert "ODTE DB" not in trace
    assert trace.count("terminal ") == 2
    assert "migration" in trace


def test_legacy_bash_environment_database_url_overrides_dotenv(launcher) -> None:
    root, run = launcher
    database_url = "sqlite+aiosqlite:///./override.db"
    completed = run(
        "DATABASE_URL=postgresql+asyncpg://localhost:55432/ignored\n",
        DATABASE_URL=database_url,
    )
    assert completed.returncode == 0, completed.stderr
    assert database_url in completed.stdout
    trace = (root / "startup.trace").read_text(encoding="utf-8")
    assert "wait " not in trace
    assert "ODTE DB" not in trace


@pytest.mark.parametrize(
    ("host", "port", "local"),
    [("127.0.0.1", 55432, True), ("remote.example.test", 5432, False)],
)
def test_legacy_bash_preserves_quoted_postgres_paths(launcher, host, port, local) -> None:
    root, run = launcher
    completed = run(f'DATABASE_URL="postgresql+asyncpg://{host}:{port}/test"\n')
    assert completed.returncode == 0, completed.stderr
    trace = (root / "startup.trace").read_text(encoding="utf-8")
    assert f"wait {host}:{port}" in trace
    assert ("ODTE DB" in trace) is local
    assert "migration" in trace
    assert trace.count("terminal ") == (3 if local else 2)


def test_legacy_bash_rejects_unsupported_database_scheme(launcher) -> None:
    root, run = launcher
    completed = run("DATABASE_URL=mysql://localhost/test\n")
    assert completed.returncode != 0
    assert "DATABASE_URL" in completed.stderr
    trace = (root / "startup.trace").read_text(encoding="utf-8")
    assert "migration" not in trace
    assert "terminal " not in trace


def test_legacy_bash_does_not_launch_services_after_migration_failure(launcher) -> None:
    root, run = launcher
    completed = run(
        "DATABASE_URL=sqlite+aiosqlite:///./local.db\n", STARTUP_MIGRATION_STATUS="17"
    )
    assert completed.returncode == 17
    trace = (root / "startup.trace").read_text(encoding="utf-8")
    assert "migration" in trace
    assert "terminal " not in trace
