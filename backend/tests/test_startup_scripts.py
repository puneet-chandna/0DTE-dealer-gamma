from __future__ import annotations

import shutil
import signal
import subprocess
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"


def test_cross_platform_startup_scripts_exist() -> None:
    expected_scripts = [
        "start_app.sh",
        "stop_app.sh",
        "start_app.ps1",
        "stop_app.ps1",
        "cleanup_runtime_state.sh",
        "run_backend_dev.sh",
        "run_frontend_dev.sh",
        "run_local_db_terminal.sh",
        "dev.sh",
        "setup_env.sh",
    ]

    for script_name in expected_scripts:
        script_path = SCRIPTS_DIR / script_name
        assert script_path.exists(), f"Missing startup helper script: {script_path}"

    assert not (SCRIPTS_DIR / "run_docker_db_terminal.sh").exists()


def test_linux_startup_script_is_valid_bash() -> None:
    completed = subprocess.run(
        [
            "bash",
            "-n",
            str(SCRIPTS_DIR / "start_app.sh"),
            str(SCRIPTS_DIR / "stop_app.sh"),
            str(SCRIPTS_DIR / "dev.sh"),
            str(SCRIPTS_DIR / "setup_env.sh"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr


def test_windows_startup_script_guides_users_to_local_postgres_or_wsl() -> None:
    windows_script = (SCRIPTS_DIR / "start_app.ps1").read_text(encoding="utf-8")

    assert "Docker" not in windows_script
    assert "WSL" in windows_script
    assert "Git Bash" in windows_script
    assert "PostgreSQL" in windows_script
    assert "Write-Host" in windows_script


def test_runtime_cleanup_script_removes_stale_pid_files(tmp_path: Path) -> None:
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    stale_pid_file = runtime_dir / "frontend.pid"
    stale_pid_file.write_text("999999\n", encoding="utf-8")

    completed = subprocess.run(
        ["bash", str(SCRIPTS_DIR / "cleanup_runtime_state.sh")],
        check=False,
        capture_output=True,
        text=True,
        env={
            "PATH": str(Path("/usr/bin")) + ":" + str(Path("/bin")),
            "ODTE_RUNTIME_DIR": str(runtime_dir),
        },
    )

    assert completed.returncode == 0, completed.stderr
    assert not stale_pid_file.exists()


def test_start_local_postgres_requires_initialized_cluster(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    data_dir = tmp_path / "data"
    socket_dir = tmp_path / "run"
    log_file = tmp_path / "logs" / "postgres.log"
    bin_dir.mkdir()
    data_dir.mkdir()
    pg_ctl = bin_dir / "pg_ctl"
    pg_ctl.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    pg_ctl.chmod(0o755)

    completed = subprocess.run(
        ["bash", str(SCRIPTS_DIR / "start_local_postgres.sh")],
        check=False,
        capture_output=True,
        text=True,
        env={
            "PATH": "/usr/bin:/bin",
            "PG_BIN_DIR": str(bin_dir),
            "PGDATA_DIR": str(data_dir),
            "PGSOCKET_DIR": str(socket_dir),
            "PGLOG_FILE": str(log_file),
            "PGPORT": "55432",
        },
    )

    assert completed.returncode != 0
    assert "not initialized" in completed.stderr


def test_start_local_postgres_does_not_restart_running_server(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    data_dir = tmp_path / "data"
    socket_dir = tmp_path / "run"
    log_file = tmp_path / "logs" / "postgres.log"
    marker_file = tmp_path / "start_called"

    bin_dir.mkdir()
    data_dir.mkdir()
    (data_dir / "PG_VERSION").write_text("17\n", encoding="utf-8")
    pg_ctl = bin_dir / "pg_ctl"
    pg_ctl.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "if [[ \"$3\" == \"status\" ]]; then\n"
        "  exit 0\n"
        "fi\n"
        f"printf 'started' > {marker_file}\n"
        "exit 0\n",
        encoding="utf-8",
    )
    pg_ctl.chmod(0o755)

    completed = subprocess.run(
        ["bash", str(SCRIPTS_DIR / "start_local_postgres.sh")],
        check=False,
        capture_output=True,
        text=True,
        env={
            "PATH": "/usr/bin:/bin",
            "PG_BIN_DIR": str(bin_dir),
            "PGDATA_DIR": str(data_dir),
            "PGSOCKET_DIR": str(socket_dir),
            "PGLOG_FILE": str(log_file),
            "PGPORT": "55432",
        },
    )

    assert completed.returncode == 0, completed.stderr
    assert "already running" in completed.stdout
    assert not marker_file.exists()


def test_start_local_postgres_creates_log_directory_before_start(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    data_dir = tmp_path / "data"
    socket_dir = tmp_path / "run"
    log_file = tmp_path / "logs" / "nested" / "postgres.log"
    marker_file = tmp_path / "start_called"

    bin_dir.mkdir()
    data_dir.mkdir()
    (data_dir / "PG_VERSION").write_text("17\n", encoding="utf-8")
    pg_ctl = bin_dir / "pg_ctl"
    pg_ctl.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "if [[ \"$3\" == \"status\" ]]; then\n"
        "  exit 3\n"
        "fi\n"
        "log_file=''\n"
        "while (($#)); do\n"
        "  if [[ \"$1\" == \"-l\" ]]; then\n"
        "    log_file=\"$2\"\n"
        "    shift 2\n"
        "    continue\n"
        "  fi\n"
        "  shift\n"
        "done\n"
        "[[ -d \"$(dirname \"$log_file\")\" ]]\n"
        f"printf 'started' > {marker_file}\n"
        "exit 0\n",
        encoding="utf-8",
    )
    pg_ctl.chmod(0o755)

    completed = subprocess.run(
        ["bash", str(SCRIPTS_DIR / "start_local_postgres.sh")],
        check=False,
        capture_output=True,
        text=True,
        env={
            "PATH": "/usr/bin:/bin",
            "PG_BIN_DIR": str(bin_dir),
            "PGDATA_DIR": str(data_dir),
            "PGSOCKET_DIR": str(socket_dir),
            "PGLOG_FILE": str(log_file),
            "PGPORT": "55432",
        },
    )

    assert completed.returncode == 0, completed.stderr
    assert marker_file.exists()


def test_dev_runner_is_single_process_without_terminal_dependency() -> None:
    dev_script = (SCRIPTS_DIR / "dev.sh").read_text(encoding="utf-8")

    for terminal_launcher in (
        "gnome-terminal",
        "x-terminal-emulator",
        "konsole",
        "xfce4-terminal",
        "detect_terminal",
        "launch_terminal",
    ):
        assert terminal_launcher not in dev_script

    assert "dev.pid" in dev_script
    assert "dev.log" in dev_script
    assert "trap" in dev_script and "INT" in dev_script and "TERM" in dev_script
    assert "sqlite" in dev_script


def test_sqlite_url_detection_covers_sqlalchemy_driver_urls() -> None:
    # Regression guard: the default URL is `sqlite+aiosqlite:///...`, which
    # does NOT match the glob `sqlite:*` (the `+` follows `sqlite` directly).
    for script_name in ("dev.sh", "start_app.sh", "setup_env.sh"):
        script_text = (SCRIPTS_DIR / script_name).read_text(encoding="utf-8")
        assert "== sqlite*" in script_text
        assert "== sqlite:*" not in script_text


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _sandbox_env(sandbox: Path, stub_bin: Path) -> dict[str, str]:
    return {
        "PATH": str(stub_bin),
        "HOME": str(sandbox),
        "ODTE_REPO_ROOT": str(sandbox),
        "ODTE_BACKEND_VENV_BIN": str(sandbox / "backend" / ".venv" / "bin"),
        "ODTE_RUNTIME_DIR": str(sandbox / ".local-run"),
        "ODTE_DEV_SKIP_WAIT": "1",
    }


def test_dev_runner_starts_and_stops_without_terminal_binaries(tmp_path: Path) -> None:
    sandbox = tmp_path / "odte-dev-stub-sandbox"
    stub_bin = sandbox / "stub-bin"
    venv_bin = sandbox / "backend" / ".venv" / "bin"
    frontend_dir = sandbox / "frontend"
    stub_bin.mkdir(parents=True)
    venv_bin.mkdir(parents=True)
    frontend_dir.mkdir(parents=True)

    (sandbox / "scripts").mkdir()
    shutil.copy2(SCRIPTS_DIR / "dev.sh", sandbox / "scripts" / "dev.sh")
    (sandbox / "backend" / ".env").write_text(
        "DATABASE_URL=sqlite+aiosqlite:///./odte_gex.db\n", encoding="utf-8"
    )
    (frontend_dir / "package.json").write_text('{"name": "frontend"}\n', encoding="utf-8")

    _write_executable(
        venv_bin / "alembic",
        "#!/usr/bin/env bash\necho 'stub alembic upgrade head'\nexit 0\n",
    )
    _write_executable(venv_bin / "python", "#!/usr/bin/env bash\nexit 0\n")
    _write_executable(
        venv_bin / "uvicorn",
        "#!/usr/bin/env bash\n"
        "trap 'exit 0' TERM INT\n"
        "echo 'stub uvicorn ready'\n"
        "sleep 300 &\n"
        'wait "$!"\n',
    )
    _write_executable(
        stub_bin / "pnpm",
        "#!/usr/bin/env bash\n"
        "trap 'exit 0' TERM INT\n"
        "echo 'stub pnpm ready'\n"
        "sleep 300 &\n"
        'wait "$!"\n',
    )

    # Closed-world PATH: symlink only the tools dev.sh needs, proving the
    # runner works with no terminal emulator (or any other extra) on PATH.
    for tool in ("bash", "python3", "awk", "sed", "mkdir", "rm", "sleep", "pgrep", "pkill"):
        source = shutil.which(tool)
        assert source is not None, f"test prerequisite missing: {tool}"
        target = stub_bin / tool
        if not target.exists():
            target.symlink_to(source)

    env = _sandbox_env(sandbox, stub_bin)

    for terminal_binary in (
        "gnome-terminal",
        "x-terminal-emulator",
        "konsole",
        "xfce4-terminal",
        "tmux",
    ):
        assert shutil.which(terminal_binary, path=env["PATH"]) is None
    assert Path(shutil.which("pnpm", path=env["PATH"]) or "").parent == stub_bin

    proc = subprocess.Popen(
        ["bash", str(sandbox / "scripts" / "dev.sh")],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
    )
    try:
        pid_file = sandbox / ".local-run" / "dev.pid"
        log_file = sandbox / ".local-run" / "dev.log"

        deadline = time.time() + 20
        while time.time() < deadline:
            if (
                pid_file.exists()
                and log_file.exists()
                and "[backend]" in log_file.read_text(encoding="utf-8", errors="replace")
                and "[frontend]" in log_file.read_text(encoding="utf-8", errors="replace")
            ):
                break
            if proc.poll() is not None:
                break
            time.sleep(0.2)

        assert proc.poll() is None, f"dev runner exited early with {proc.returncode}"
        assert pid_file.exists(), "dev runner did not write a single dev.pid file"
        log_text = log_file.read_text(encoding="utf-8", errors="replace")
        assert "[backend]" in log_text
        assert "[frontend]" in log_text

        proc.send_signal(signal.SIGINT)
        proc.wait(timeout=25)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=10)

    assert not pid_file.exists(), "dev runner did not clean up dev.pid on shutdown"

    deadline = time.time() + 10
    while time.time() < deadline:
        leftover = subprocess.run(
            ["pgrep", "-f", "odte-dev-stub-sandbox"],
            check=False,
            capture_output=True,
            text=True,
            env={"PATH": "/usr/bin:/bin"},
        )
        # pgrep exits 1 when nothing matches; filter out zombie entries conservatively
        # by also requiring a live /proc state check below.
        if leftover.returncode != 0:
            break
        time.sleep(0.5)

    leftover = subprocess.run(
        ["pgrep", "-f", "odte-dev-stub-sandbox"],
        check=False,
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin"},
    )
    live_pids = []
    for candidate in leftover.stdout.split():
        try:
            state = (Path(f"/proc/{candidate}/stat").read_text().split()[2])
        except (FileNotFoundError, IndexError):
            continue
        if state != "Z":
            live_pids.append(candidate)
    assert not live_pids, f"orphaned dev stub processes remain: {live_pids}"


def _make_setup_env_sandbox(tmp_path: Path) -> Path:
    sandbox = tmp_path / "setup-env-sandbox"
    (sandbox / "backend").mkdir(parents=True)
    (sandbox / "frontend").mkdir(parents=True)
    shutil.copy2(REPO_ROOT / "backend" / ".env.example", sandbox / "backend" / ".env.example")
    shutil.copy2(REPO_ROOT / "frontend" / ".env.example", sandbox / "frontend" / ".env.example")
    (sandbox / ".env").write_text(
        "# Data Providers\nPOLYGON_API_KEY=stale-placeholder\n", encoding="utf-8"
    )
    return sandbox


def _run_setup_env(sandbox: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(sandbox),
        "ODTE_REPO_ROOT": str(sandbox),
    }
    return subprocess.run(
        ["bash", str(SCRIPTS_DIR / "setup_env.sh"), *args],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


def test_setup_env_creates_and_preserves_env_files(tmp_path: Path) -> None:
    sandbox = _make_setup_env_sandbox(tmp_path)

    first = _run_setup_env(sandbox, "--sqlite")
    assert first.returncode == 0, first.stderr
    backend_env = sandbox / "backend" / ".env"
    frontend_env = sandbox / "frontend" / ".env.local"
    assert backend_env.exists()
    assert frontend_env.exists()
    assert "DATABASE_URL=sqlite+aiosqlite:///./odte_gex.db" in backend_env.read_text(
        encoding="utf-8"
    )

    # Idempotent: a rerun must not clobber local customizations.
    with backend_env.open("a", encoding="utf-8") as handle:
        handle.write("MY_LOCAL_TWEAK=keep-me\n")
    second = _run_setup_env(sandbox, "--sqlite")
    assert second.returncode == 0, second.stderr
    rerun_text = backend_env.read_text(encoding="utf-8")
    assert "MY_LOCAL_TWEAK=keep-me" in rerun_text
    assert "already exists, leaving it untouched" in second.stdout

    # No flag: an explicitly chosen Postgres URL is left alone, only validated.
    backend_text = backend_env.read_text(encoding="utf-8")
    backend_text = "\n".join(
        line
        for line in backend_text.splitlines()
        if not line.startswith("DATABASE_URL=")
        and not line.startswith("MY_LOCAL_TWEAK=")
    )
    backend_env.write_text(
        backend_text
        + "\nDATABASE_URL=postgresql+asyncpg://odte_user:odte_password@127.0.0.1:55432/odte_gex\n",
        encoding="utf-8",
    )
    third = _run_setup_env(sandbox)
    assert third.returncode == 0, third.stderr
    assert (
        "DATABASE_URL=postgresql+asyncpg://odte_user:odte_password@127.0.0.1:55432/odte_gex"
        in backend_env.read_text(encoding="utf-8")
    )

    # Stale provider key is scrubbed from the root .env.
    assert "POLYGON_API_KEY" not in (sandbox / ".env").read_text(encoding="utf-8")


def test_setup_env_mode_flag_sets_postgres_url(tmp_path: Path) -> None:
    sandbox = _make_setup_env_sandbox(tmp_path)

    completed = _run_setup_env(sandbox, "--postgres-local")
    assert completed.returncode == 0, completed.stderr
    assert "DATABASE_URL=postgresql+asyncpg://odte_user:odte_password@127.0.0.1:55432/odte_gex" in (
        sandbox / "backend" / ".env"
    ).read_text(encoding="utf-8")


def test_setup_env_fails_fast_on_missing_values(tmp_path: Path) -> None:
    sandbox = _make_setup_env_sandbox(tmp_path)

    completed = _run_setup_env(sandbox, "--sqlite")
    assert completed.returncode == 0, completed.stderr

    frontend_env = sandbox / "frontend" / ".env.local"
    broken = "\n".join(
        line
        for line in frontend_env.read_text(encoding="utf-8").splitlines()
        if not line.startswith("NEXT_PUBLIC_WS_URL=")
    )
    frontend_env.write_text(broken + "\n", encoding="utf-8")

    failed = _run_setup_env(sandbox)
    assert failed.returncode != 0
    assert "NEXT_PUBLIC_WS_URL" in failed.stderr

    unknown = _run_setup_env(sandbox, "--bogus")
    assert unknown.returncode != 0
