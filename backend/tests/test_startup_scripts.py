from __future__ import annotations

import subprocess
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
