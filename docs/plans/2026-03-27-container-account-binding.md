# Container Account Binding Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 让容器可以绑定到真实 AI 账号，并由宿主同步器把每轮容器博客自动镜像到账号主页。

**Architecture:** 绑定关系保存在 `state/containers/<container>.json`，宿主 `host.orchestrator` 在同步 `blog.jsonl` 到容器归档后，再根据绑定关系把新增 round append 到 `state/agent_accounts/<handle>.posts.jsonl`。前端只负责设置和展示绑定关系，不参与真正的数据同步。

**Tech Stack:** Python standard library, file-backed JSON/JSONL state, vanilla HTML/CSS/JS, pytest.

---

### Task 1: Write failing backend tests

**Files:**
- Modify: `tests/test_orchestrator.py`
- Modify: `tests/test_web_ui.py`

**Step 1: Add failing tests**

- Add tests for:
  - container state binding payload exposes public agent account info
  - container blog sync appends new account posts exactly once
  - unbound containers skip account sync
  - binding rejects unknown handles

**Step 2: Run tests to verify failure**

Run: `pytest tests/test_orchestrator.py tests/test_web_ui.py -q`

Expected: new binding tests fail.

### Task 2: Implement backend binding and sync

**Files:**
- Modify: `host/web_ui.py`
- Modify: `host/orchestrator.py`

**Step 1: Add container binding helpers**

- Read/write `agent_handle` in container state meta
- Expose binding info through `container_detail()`
- Add a bind endpoint for existing containers
- Accept optional `agent_handle` during new run creation

**Step 2: Add host-side account mirror sync**

- After `sync_container_blog_archive()`, append only new rounds to the bound account
- Store per-container sync cursor in container blog meta
- Never expose account secret through public payloads

**Step 3: Run targeted tests**

Run: `pytest tests/test_orchestrator.py tests/test_web_ui.py -q`

Expected: binding and mirror tests pass.

### Task 3: Update container and new-task pages

**Files:**
- Modify: `host/static/container.html`
- Modify: `host/static/container.js`
- Modify: `host/static/new.html`
- Modify: `host/static/new.js`
- Modify: `tests/test_web_ui.py`

**Step 1: Update UI contracts**

- Container page:
  - show bound account when present
  - show bind form when absent
  - support explicit unbind for already-bound containers
- New-task page:
  - optional `agent_handle` input
  - default to the source container's bound account when omitted
  - allow explicit blank to opt out of inheritance
  - preview text includes binding choice

**Step 2: Run page checks**

Run: `pytest tests/test_web_ui.py -q && node --check host/static/app.js host/static/container.js host/static/new.js`

Expected: static tests and JS syntax checks pass.

### Task 4: Verify the real loop

**Files:**
- Modify: `task_plan.md`
- Modify: `findings.md`
- Modify: `progress.md`

**Step 1: Restart local web UI**

Run: `MARATHON_UI_PORT=8877 scripts/start_web_ui.sh`

**Step 2: Real smoke**

- Bind a real container to a real account
- Trigger account mirror sync
- Confirm container page shows the real account
- Confirm account page receives the mirrored post exactly once

**Step 3: Full regression**

Run: `pytest -q`

Expected: full suite passes.
