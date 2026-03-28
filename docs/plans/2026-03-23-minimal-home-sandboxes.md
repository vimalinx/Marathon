# Minimal Home And Sandboxes Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把主页改成极简实验主屏，并新增独立沙盒页承载沙盒列表。

**Architecture:** 保留现有 API 和数据获取方式，前端通过两张静态页面消费同一组 `/api/overview`、`/api/containers/:name`、`/api/runs/:id` 接口。主页收缩到“当前实验”，沙盒页承载容器列表和进入动作。

**Tech Stack:** Python `http.server` Web UI, plain HTML/CSS/JavaScript, unittest/pytest existing test suite.

---

## Chunk 1: Static Routing

### Task 1: Add standalone sandboxes page route

**Files:**
- Modify: `host/web_ui.py`
- Test: `tests/test_design_lab.py`

- [ ] **Step 1: Add `/sandboxes` and `/sandboxes.html` to static asset resolution**
- [ ] **Step 2: Add a test that requests `/sandboxes` and receives the sandboxes page**
- [ ] **Step 3: Run the focused route tests**

Run: `pytest tests/test_design_lab.py -q`

## Chunk 2: Simplify Home

### Task 2: Replace dark multi-panel home layout with minimal light layout

**Files:**
- Modify: `host/static/index.html`

- [ ] **Step 1: Replace dark theme tokens with light neutral tokens**
- [ ] **Step 2: Remove sidebar container list from the home page**
- [ ] **Step 3: Reduce the home information architecture to current experiment, actions, and latest output**
- [ ] **Step 4: Keep existing task/freeplay actions wired to current APIs**
- [ ] **Step 5: Add visible navigation link to the sandboxes page**

## Chunk 3: Add Sandboxes Page

### Task 3: Create standalone sandboxes page

**Files:**
- Create: `host/static/sandboxes.html`

- [ ] **Step 1: Create a minimal light-themed sandboxes page**
- [ ] **Step 2: Load `/api/overview` and render containers as a readable list**
- [ ] **Step 3: Show simple per-container summary: state, latest run, memory**
- [ ] **Step 4: Add “进入主页” action that opens `/?container=<name>`**

## Chunk 4: Home/Sandbox Coordination

### Task 4: Make the home page accept a selected container cleanly

**Files:**
- Modify: `host/static/index.html`

- [ ] **Step 1: Read `container` from the URL query string**
- [ ] **Step 2: Prefer the query-selected container when loading home data**
- [ ] **Step 3: Keep fallback behavior when no query parameter is present**

## Chunk 5: Verify Copy And Presence

### Task 5: Add lightweight content tests for the simplified UI

**Files:**
- Modify: `tests/test_web_ui.py`

- [ ] **Step 1: Add assertions for homepage copy indicating minimal experiment view**
- [ ] **Step 2: Add assertions that the homepage contains the sandboxes navigation**
- [ ] **Step 3: Add assertions that `sandboxes.html` exists and includes expected copy**
- [ ] **Step 4: Run focused UI tests**

Run: `pytest tests/test_web_ui.py tests/test_design_lab.py -q`

## Chunk 6: Final Verification

### Task 6: Run final verification for the shipped slice

**Files:**
- Modify: `README.md` (only if homepage description is visibly stale after implementation)

- [ ] **Step 1: Run Python syntax check**

Run: `python3 -m py_compile host/web_ui.py`

- [ ] **Step 2: Run focused tests**

Run: `pytest tests/test_web_ui.py tests/test_design_lab.py -q`

- [ ] **Step 3: Smoke-check the served pages**

Run:

```bash
python3 -m host.web_ui --host 127.0.0.1 --port 8765
curl -s http://127.0.0.1:8765/ | head
curl -s http://127.0.0.1:8765/sandboxes | head
```
