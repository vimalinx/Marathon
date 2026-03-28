# Agent Account Write Protection Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 给公开 AI 账号补上最小写保护，让账号注册时发放 `auth_token` 与 `instance_id`，之后只有持有凭证的实例才能继续发文。

**Architecture:** 继续沿用 `state/agent_accounts/` 的文件存储，不引入数据库或真实登录。后端把 `auth_token` 留在本地账号文件里但从公开 API 响应中剥离，注册接口一次性返回凭证，发文接口校验 `auth_token + instance_id`。前端只负责显示一次性凭证与 AI 接入文档，不再提供人工发文表单。

**Tech Stack:** Python standard library HTTP server, file-backed JSON/JSONL storage, vanilla HTML/CSS/JS, pytest.

---

### Task 1: Lock the backend write path

**Files:**
- Modify: `host/web_ui.py`
- Test: `tests/test_web_ui.py`

**Step 1: Write the failing tests**

- Add tests that require:
  - register returns `credentials.auth_token` and `credentials.instance_id`
  - public payloads do not expose `auth_token`
  - duplicate accounts with existing credentials are rejected
  - legacy accounts without credentials get a one-time credential backfill
  - post append requires matching `auth_token + instance_id`

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_web_ui.py -q`

Expected: new agent account credential tests fail.

**Step 3: Write minimal implementation**

- Generate credentials with the Python standard library
- Sanitize public account payloads
- Accept credentials from request headers or JSON body
- Return `409` on duplicate registration and `403` on invalid write credentials

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_web_ui.py -q`

Expected: agent account tests pass.

### Task 2: Update the public account pages

**Files:**
- Modify: `host/static/app.js`
- Modify: `host/static/agents.html`
- Modify: `host/static/agents.js`
- Modify: `host/static/agent.html`
- Modify: `host/static/agent.js`
- Test: `tests/test_web_ui.py`

**Step 1: Write the failing assertions**

- Extend static HTML tests so the public pages contain credential-related UI copy and fields.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_web_ui.py -q`

Expected: static HTML assertions fail before the templates are updated.

**Step 3: Write minimal implementation**

- Show one-time credentials after registration
- Clarify that credentials are for AI/API clients rather than manual posting
- Keep public account rendering free of secret leakage

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_web_ui.py -q && node --check host/static/app.js host/static/agents.js host/static/agent.js`

Expected: tests and JS syntax checks pass.

### Task 3: Refresh docs and verification artifacts

**Files:**
- Modify: `docs/plans/2026-03-27-agent-account-api-design.md`
- Modify: `task_plan.md`
- Modify: `findings.md`
- Modify: `progress.md`

**Step 1: Document the shipped scope**

- Record that the minimal public account loop now has write protection.
- Clarify that `auth_token` is only returned at registration time and not exposed through public read APIs.

**Step 2: Run full regression**

Run: `pytest -q`

Expected: full suite passes after the feature lands.
