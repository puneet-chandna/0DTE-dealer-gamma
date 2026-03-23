# Repository License and Policy Docs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a noncommercial source-available license, supporting policy documents, and a corrected top-level README that accurately describes the repository's licensing and current setup.

**Architecture:** Keep the official license text isolated in `LICENSE`, express ownership and notice requirements in `NOTICE`, place policy guidance in focused Markdown docs, and update the root README to link the policy docs while staying aligned with the current repository state. Keep all legal language consistent with the approved design spec and avoid changing application code.

**Tech Stack:** Markdown, Git, GitHub repository conventions, PolyForm Noncommercial 1.0.0

---

### Task 1: Add Public License and Commercial-Use Docs

**Files:**
- Create: `LICENSE`
- Create: `NOTICE`
- Create: `COMMERCIAL-LICENSING.md`
- Reference: `docs/superpowers/specs/2026-03-23-repo-license-policy-design.md`

- [ ] **Step 1: Add the official PolyForm text to `LICENSE`**

Copy the official `PolyForm Noncommercial 1.0.0` license text into `LICENSE` without editing it.

Source: `https://polyformproject.org/licenses/noncommercial/1.0.0/`

Expected result:
- `LICENSE` exists at the repo root
- the title says `PolyForm Noncommercial License 1.0.0`
- the text is preserved exactly as published

- [ ] **Step 2: Create `NOTICE` with ownership and downstream notice text**

Write `NOTICE` with content equivalent to:

```txt
0DTE Dealer Gamma Exposure (GEX) Monitor

Copyright (c) 2026 Puneet Chandna and Gunjana Sahoo

This project is licensed under the PolyForm Noncommercial License 1.0.0.
See the LICENSE file for the full license text.

Required Notice: Copyright (c) 2026 Puneet Chandna and Gunjana Sahoo.
Commercial use requires a separate written license from the copyright holders.
```

- [ ] **Step 3: Create `COMMERCIAL-LICENSING.md`**

Write a repository policy document that covers:

- the repo is available for noncommercial use under `PolyForm Noncommercial 1.0.0`
- no commercial rights are granted by the public repo license
- examples of uses that require separate written permission:
  - monetized products or services
  - paid consulting or support centered on the software
  - resale, sublicensing, or bundled commercial distribution
  - internal business use tied to commercial operations or revenue generation
  - commercial derivatives or hosted offerings
- uncertain use cases should be treated as unlicensed until approved in writing
- contact email: `puneetchandna21@gmail.com`

- [ ] **Step 4: Verify the new legal docs are present and consistent**

Run:

```bash
test -f LICENSE
test -f NOTICE
test -f COMMERCIAL-LICENSING.md
rg -n "PolyForm Noncommercial|puneetchandna21@gmail.com|Commercial use requires" LICENSE NOTICE COMMERCIAL-LICENSING.md
```

Expected:
- all `test -f` commands exit `0`
- `rg` finds the expected license/contact language

- [ ] **Step 5: Commit**

```bash
git add LICENSE NOTICE COMMERCIAL-LICENSING.md
git commit -m "docs: add noncommercial license and commercial use policy"
```

### Task 2: Add Contributor, Security, and Support Docs

**Files:**
- Create: `CONTRIBUTING.md`
- Create: `SECURITY.md`
- Create: `SUPPORT.md`
- Reference: `docs/superpowers/specs/2026-03-23-repo-license-policy-design.md`

- [ ] **Step 1: Create `CONTRIBUTING.md`**

Write a contributing guide that includes:

- issues and pull requests are welcome
- contributions must be original or properly attributed
- by submitting a contribution, the contributor agrees it is provided under the repository's license terms
- no separate CLA is required
- contributors should avoid adding third-party code that conflicts with the repo's license model
- contributors should run relevant tests and keep documentation updated when behavior or setup changes

Include a short workflow section with:

```txt
1. Open an issue for significant changes.
2. Fork the repository and create a focused branch.
3. Run the relevant tests before submitting.
4. Submit a pull request with a clear summary.
```

- [ ] **Step 2: Create `SECURITY.md`**

Write a security policy that includes:

- request private disclosure first
- send reports to `puneetchandna21@gmail.com`
- include affected area, reproduction steps, impact, and proof-of-concept if available
- do not open a public issue for unpatched vulnerabilities
- response target should be modest, for example "we will try to acknowledge reports within 5 business days"

- [ ] **Step 3: Create `SUPPORT.md`**

Write a support-routing document that explains:

- general usage questions: GitHub issues or discussions if enabled
- bug reports: repository issues
- security reports: `puneetchandna21@gmail.com`
- commercial licensing: `puneetchandna21@gmail.com`
- maintainers may not be able to provide free private support for all requests

- [ ] **Step 4: Verify contributor/support docs**

Run:

```bash
test -f CONTRIBUTING.md
test -f SECURITY.md
test -f SUPPORT.md
rg -n "puneetchandna21@gmail.com|CLA|license terms|security" CONTRIBUTING.md SECURITY.md SUPPORT.md
```

Expected:
- all files exist
- `CLA` appears only in the "no separate CLA is required" context
- email/contact routing is present

- [ ] **Step 5: Commit**

```bash
git add CONTRIBUTING.md SECURITY.md SUPPORT.md
git commit -m "docs: add repository contribution and support policies"
```

### Task 3: Refresh and Rename the Root README

**Files:**
- Move: `Readme.md` -> `README.md`
- Modify: `README.md`
- Reference: `frontend/package.json`
- Reference: `backend/.env.example`
- Reference: `frontend/.env.example`
- Reference: `.env.example`
- Reference: `docs/API.md`
- Reference: `docs/ARCHITECTURE.md`
- Reference: `docs/DEPLOYMENT.md`
- Reference: `docs/PROVIDER_INTEGRATION_PLAN.md`

- [ ] **Step 1: Rename the root README to the conventional filename**

Run:

```bash
git mv Readme.md README.md
```

Expected:
- `README.md` exists
- `Readme.md` no longer exists in git tracking

- [ ] **Step 2: Preserve the corrected table of contents and update section structure**

Edit `README.md` so the table of contents points to actual GitHub heading anchors, and add links for new policy documents where appropriate.

Minimum sections to include:

- `Features`
- `Tech Stack`
- `Project Structure`
- `Quick Start`
- `Key Concepts`
- `Tests`
- `Documentation`
- `Deployment`
- `Architecture Rules`
- `License and Commercial Use`
- `Contributing`
- `Security`

- [ ] **Step 3: Correct factual mismatches in the README**

Update the content so it reflects the current repo:

- replace outdated `Polygon.io` wording with current provider-oriented wording
- clarify which env templates users should copy:
  - `backend/.env.example` -> `backend/.env`
  - `frontend/.env.example` -> `frontend/.env.local`
  - optionally mention the top-level `.env.example` only if it remains intentionally supported
- align the frontend test command with the package script:

```bash
cd frontend && pnpm test:run
```

- keep the earlier table-of-contents anchor fix intact

- [ ] **Step 4: Add licensing and policy visibility to the README**

Add a concise section describing:

- the project is `source-available`
- the public license is `PolyForm Noncommercial 1.0.0`
- personal, educational, research, and other noncommercial use are allowed under the license
- commercial use requires separate written permission
- policy docs to link:
  - `LICENSE`
  - `NOTICE`
  - `COMMERCIAL-LICENSING.md`
  - `CONTRIBUTING.md`
  - `SECURITY.md`
  - `SUPPORT.md`

- [ ] **Step 5: Verify README structure and links**

Run:

```bash
test -f README.md
test ! -f Readme.md
rg -n "^## |^- \\[" README.md
rg -n "PolyForm Noncommercial|source-available|COMMERCIAL-LICENSING|CONTRIBUTING|SECURITY|SUPPORT" README.md
```

Expected:
- renamed file is in place
- section headings and table-of-contents entries are visible
- the new license/policy links appear in the README

- [ ] **Step 6: Commit**

```bash
git add README.md
git commit -m "docs: refresh README for licensing and current setup"
```

### Task 4: Final Documentation Consistency Pass

**Files:**
- Verify: `LICENSE`
- Verify: `NOTICE`
- Verify: `COMMERCIAL-LICENSING.md`
- Verify: `CONTRIBUTING.md`
- Verify: `SECURITY.md`
- Verify: `SUPPORT.md`
- Verify: `README.md`
- Reference: `docs/superpowers/specs/2026-03-23-repo-license-policy-design.md`

- [ ] **Step 1: Check file inventory against the spec**

Run:

```bash
for f in LICENSE NOTICE COMMERCIAL-LICENSING.md CONTRIBUTING.md SECURITY.md SUPPORT.md README.md; do
  test -f "$f"
done
```

Expected:
- all files exist and the loop exits successfully

- [ ] **Step 2: Check for forbidden terminology and outdated claims**

Run:

```bash
rg -n "MIT|open source" README.md LICENSE NOTICE COMMERCIAL-LICENSING.md CONTRIBUTING.md SECURITY.md SUPPORT.md
```

Expected:
- no incorrect `MIT` references remain
- any `open source` hits should be reviewed and removed unless explicitly contrasted with `source-available`

- [ ] **Step 3: Check markdown and whitespace hygiene**

Run:

```bash
git diff --check
```

Expected:
- no trailing-whitespace or malformed-patch warnings

- [ ] **Step 4: Review the final diff against the spec**

Run:

```bash
git diff -- README.md LICENSE NOTICE COMMERCIAL-LICENSING.md CONTRIBUTING.md SECURITY.md SUPPORT.md
```

Expected:
- only documentation and policy files changed
- the wording aligns with the approved spec

- [ ] **Step 5: Commit only if the consistency pass changed files**

```bash
git status --short
# If Task 4 caused follow-up edits:
git add README.md LICENSE NOTICE COMMERCIAL-LICENSING.md CONTRIBUTING.md SECURITY.md SUPPORT.md
git commit -m "docs: finalize repository license and policy docs"
```

Expected:
- if Task 4 required wording fixes, those fixes are committed
- if Task 4 made no changes, skip the commit and note that no additional commit was needed
