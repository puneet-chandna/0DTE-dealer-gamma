# Stop App Launcher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one-command stop scripts that shut down frontend, backend, and the local PostgreSQL database safely in the correct order.

**Architecture:** Persist lightweight PID files for the long-running frontend and backend processes when they are launched in their helper shells. Add stop scripts that read those PID files, send graceful signals, wait for processes to exit, and stop Postgres last using `pg_ctl` so the database stays consistent.

**Tech Stack:** Bash, PowerShell, pytest, README docs

---

### Task 1: Add failing startup/stop script coverage

**Files:**
- Modify: `backend/tests/test_startup_scripts.py`

- [ ] **Step 1: Write the failing test**

Add expectations for:
- `scripts/stop_app.sh`
- `scripts/stop_app.ps1`
- Linux stop script bash syntax validity

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest -q tests/test_startup_scripts.py`
Expected: FAIL because the stop scripts do not exist yet.

- [ ] **Step 3: Write minimal implementation**

Update the test file only.

- [ ] **Step 4: Run test to verify it passes after implementation**

Run: `cd backend && .venv/bin/pytest -q tests/test_startup_scripts.py`
Expected: PASS after implementation is complete.

### Task 2: Persist runtime state for running services

**Files:**
- Modify: `scripts/run_backend_dev.sh`
- Modify: `scripts/run_frontend_dev.sh`

- [ ] **Step 1: Write the failing test**

Covered by Task 1.

- [ ] **Step 2: Run test to verify it fails**

Covered by Task 1.

- [ ] **Step 3: Write minimal implementation**

Have the backend and frontend helper scripts:
- create a shared runtime directory
- write their child process PID files
- clean those PID files on exit

- [ ] **Step 4: Run verification**

Run bash syntax checks on the updated scripts.

### Task 3: Add Linux and Windows stop launchers

**Files:**
- Create: `scripts/stop_app.sh`
- Create: `scripts/stop_app.ps1`
- Modify: `scripts/stop_local_postgres.sh`

- [ ] **Step 1: Write the failing test**

Covered by Task 1.

- [ ] **Step 2: Run test to verify it fails**

Covered by Task 1.

- [ ] **Step 3: Write minimal implementation**

Implement stop scripts that:
- stop frontend first
- stop backend second
- stop local PostgreSQL last
- tolerate already-stopped services
- print clear status messages

Also harden `stop_local_postgres.sh` so it exits cleanly if the DB is already down.

- [ ] **Step 4: Run verification**

Run:
- `bash -n scripts/stop_app.sh scripts/stop_local_postgres.sh scripts/run_backend_dev.sh scripts/run_frontend_dev.sh`
- `cd backend && .venv/bin/pytest -q tests/test_startup_scripts.py`

### Task 4: Document the stop flow

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Write the failing test**

Manual-docs-only change; no automated test.

- [ ] **Step 2: Write minimal implementation**

Document the stop commands and explain that the DB is shut down last for safety.

- [ ] **Step 3: Run final verification**

Run:
- `bash -n scripts/start_app.sh scripts/stop_app.sh scripts/run_backend_dev.sh scripts/run_frontend_dev.sh scripts/run_local_db_terminal.sh scripts/setup_local_postgres.sh scripts/start_local_postgres.sh scripts/stop_local_postgres.sh`
- `cd backend && .venv/bin/pytest -q tests/test_startup_scripts.py`
