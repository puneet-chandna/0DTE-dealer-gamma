"""Exercise runner cleanup with real processes and disposable command stubs."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def _executable(path: Path, body: str) -> None:
    path.write_text("#!/usr/bin/env bash\n" + body + "\n", encoding="utf-8")
    path.chmod(0o755)


@pytest.fixture
def runner(tmp_path: Path):
    venv_bin = tmp_path / "backend/.venv/bin"
    stub_bin = tmp_path / "bin"
    for directory in (venv_bin, stub_bin, tmp_path / "frontend", tmp_path / "scripts"):
        directory.mkdir(parents=True)
    (tmp_path / "backend/.env").write_text("DATABASE_URL=sqlite+aiosqlite:///./test.db\n")
    (tmp_path / "frontend/package.json").write_text("{}\n")
    for script in ("dev.sh", "read_env.py"):
        if (SCRIPTS / script).exists():
            shutil.copy2(SCRIPTS / script, tmp_path / "scripts" / script)
    (venv_bin / "python").symlink_to(sys.executable)
    _executable(venv_bin / "alembic", "exit 0")
    _executable(venv_bin / "uvicorn", "sleep 300")
    _executable(stub_bin / "pnpm", "sleep 300")
    env = dict(
        PATH=f"{stub_bin}:/usr/bin:/bin",
        HOME=str(tmp_path),
        PYTHONPATH=os.environ.get("PYTHONPATH", ""),
        ODTE_REPO_ROOT=str(tmp_path),
        ODTE_BACKEND_VENV_BIN=str(venv_bin),
        ODTE_DEV_SKIP_WAIT="1",
    )
    env.pop("DATABASE_URL", None)
    processes = []

    def start():
        proc = subprocess.Popen(
            ["bash", str(tmp_path / "scripts/dev.sh")],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        processes.append(proc)
        return proc

    yield tmp_path, env, start

    for proc in processes:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait(timeout=5)
    for marker in tmp_path.glob("*.pid"):
        try:
            os.kill(int(marker.read_text()), signal.SIGKILL)
        except ProcessLookupError:
            pass


def _wait_for_file(path: Path, proc: subprocess.Popen) -> None:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if path.exists():
            return
        assert proc.poll() is None, proc.communicate()[0]
        time.sleep(0.05)
    pytest.fail(f"runner did not create {path.name}")


def _is_alive(pid: int) -> bool:
    try:
        return Path(f"/proc/{pid}/stat").read_text().split()[2] != "Z"
    except FileNotFoundError:
        return False


def test_migration_failure_removes_pid_file(runner):
    root, _, start = runner
    _executable(root / "backend/.venv/bin/alembic", "exit 17")
    proc = start()
    proc.wait(timeout=10)
    assert proc.returncode == 17
    assert not (root / ".local-run/dev.pid").exists()


@pytest.mark.parametrize("service_exit", [False, True], ids=["interrupt", "parent-exits"])
def test_shutdown_kills_descendant_that_ignores_term(runner, service_exit):
    root, _, start = runner
    child = root / "child.py"
    marker = root / "child.pid"
    child.write_text(
        "import os, pathlib, signal, time\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        f"pathlib.Path({str(marker)!r}).write_text(str(os.getpid()))\n"
        "while True: time.sleep(1)\n"
    )
    end = "sleep 0.5; exit 7" if service_exit else 'wait "$!"'
    _executable(root / "backend/.venv/bin/uvicorn", f"python3 {child} &\n{end}")
    proc = start()
    _wait_for_file(marker, proc)
    child_pid = int(marker.read_text())
    if not service_exit:
        proc.send_signal(signal.SIGINT)
    proc.wait(timeout=10)
    assert proc.returncode == (7 if service_exit else 130)
    assert not _is_alive(child_pid)
    assert not (root / ".local-run/dev.pid").exists()


def test_failed_readiness_stops_services(runner):
    root, env, start = runner
    env.update(ODTE_DEV_SKIP_WAIT="0", ODTE_DEV_BACKEND_WAIT_SECS="0")
    proc = start()
    try:
        proc.wait(timeout=8)
    except subprocess.TimeoutExpired:
        pytest.fail("runner kept running after its backend readiness deadline")
    assert proc.returncode != 0
    assert not (root / ".local-run/dev.pid").exists()


def test_term_during_readiness_is_prompt_and_cleans_up(runner):
    root, env, start = runner
    env.update(ODTE_DEV_SKIP_WAIT="0", ODTE_DEV_BACKEND_WAIT_SECS="30")
    proc = start()
    log = root / ".local-run/dev.log"
    deadline = time.monotonic() + 10
    while not log.exists() or "Waiting for backend http" not in log.read_text():
        assert proc.poll() is None
        assert time.monotonic() < deadline
        time.sleep(0.05)
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=8)
    except subprocess.TimeoutExpired:
        pytest.fail("TERM was deferred until the HTTP readiness deadline")
    assert proc.returncode == 143
    assert not (root / ".local-run/dev.pid").exists()


@pytest.mark.parametrize(("stop_signal", "exit_code"), [(signal.SIGINT, 130), (signal.SIGTERM, 143)])
def test_repeated_signal_does_not_abort_cleanup(runner, stop_signal, exit_code):
    root, _, start = runner
    child = root / "child.py"
    marker = root / "child.pid"
    child.write_text(
        "import os, pathlib, signal, time\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        f"pathlib.Path({str(marker)!r}).write_text(str(os.getpid()))\n"
        "while True: time.sleep(1)\n"
    )
    _executable(root / "backend/.venv/bin/uvicorn", f'python3 {child} &\nwait "$!"')
    proc = start()
    _wait_for_file(marker, proc)
    proc.send_signal(stop_signal)
    log = root / ".local-run/dev.log"
    deadline = time.monotonic() + 5
    while "shutting down" not in log.read_text():
        assert time.monotonic() < deadline
        time.sleep(0.05)
    proc.send_signal(stop_signal)
    proc.wait(timeout=8)
    assert proc.returncode == exit_code
    assert not _is_alive(int(marker.read_text()))
    assert not (root / ".local-run/dev.pid").exists()
