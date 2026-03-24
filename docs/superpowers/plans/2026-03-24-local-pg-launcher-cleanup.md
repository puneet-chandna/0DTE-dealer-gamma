# Local PG Launcher Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove Docker from the local startup flow and make the launcher reflect the project’s standard local PostgreSQL setup, with clear Windows guidance when PostgreSQL is missing.

**Architecture:** Keep Linux/Git Bash/WSL as the real startup path through shell scripts and the local PostgreSQL 17 helper scripts. Simplify the Windows PowerShell launcher so it no longer tries to manage Docker and instead provides colored install guidance or WSL/Git Bash guidance when native PostgreSQL is unavailable.

**Tech Stack:** Bash, PowerShell, pytest, README docs

---

### Task 1: Update startup script coverage

**Files:**
- Modify: `backend/tests/test_startup_scripts.py`

- [ ] **Step 1: Write the failing test**

Add assertions that:
- `run_docker_db_terminal.sh` no longer exists
- `start_app.ps1` contains guidance about local PostgreSQL installation or WSL/Git Bash

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest -q tests/test_startup_scripts.py`
Expected: FAIL because the old Docker helper still exists and Windows guidance is incomplete

- [ ] **Step 3: Write minimal implementation**

Update the test file only enough to express the new expected startup contract.

- [ ] **Step 4: Run test to verify it passes after implementation**

Run: `cd backend && .venv/bin/pytest -q tests/test_startup_scripts.py`
Expected: PASS

### Task 2: Remove Docker from the launcher flow

**Files:**
- Modify: `scripts/start_app.sh`
- Delete: `scripts/run_docker_db_terminal.sh`

- [ ] **Step 1: Write the failing test**

Covered by Task 1.

- [ ] **Step 2: Run test to verify it fails**

Covered by Task 1.

- [ ] **Step 3: Write minimal implementation**

Update `start_app.sh` so:
- it only launches the local DB terminal for the standard local PG setup
- it no longer branches into Docker handling
- it treats non-local DBs as external and skips DB terminal launch cleanly

Delete the unused Docker DB helper script.

- [ ] **Step 4: Run test to verify it passes**

Run:
- `bash -n scripts/start_app.sh scripts/run_backend_dev.sh scripts/run_frontend_dev.sh scripts/run_local_db_terminal.sh`
- `cd backend && .venv/bin/pytest -q tests/test_startup_scripts.py`

Expected: PASS

### Task 3: Fix native Windows guidance

**Files:**
- Modify: `scripts/start_app.ps1`

- [ ] **Step 1: Write the failing test**

Covered by Task 1.

- [ ] **Step 2: Run test to verify it fails**

Covered by Task 1.

- [ ] **Step 3: Write minimal implementation**

Update `start_app.ps1` so:
- it no longer mentions Docker
- it prints colored guidance when local PostgreSQL is not available
- it clearly recommends WSL/Git Bash for the repo-standard local PG flow
- it can continue only when an external/reachable DB is already configured

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest -q tests/test_startup_scripts.py`
Expected: PASS

### Task 4: Update docs

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Write the failing test**

Manual-docs-only change; no automated test.

- [ ] **Step 2: Write minimal implementation**

Update README startup docs so they describe:
- local PostgreSQL as the standard
- Linux/Git Bash/WSL launcher as the recommended path
- native Windows PowerShell as a guidance-only helper when PostgreSQL is not installed

- [ ] **Step 3: Run verification**

Run:
- `bash -n scripts/start_app.sh scripts/run_backend_dev.sh scripts/run_frontend_dev.sh scripts/run_local_db_terminal.sh`
- `cd backend && .venv/bin/pytest -q tests/test_startup_scripts.py`

Expected: PASS
