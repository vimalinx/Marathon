# Container Live Panel Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把容器详情页改成强状态 + AI 实时思路 + 实时轨迹的主界面。

**Architecture:** 保持现有 `/api/overview`、`/api/containers/:name`、`/api/runs/:id` 接口不变，只在静态前端内重新组织布局和轮询逻辑。使用已有 `latest_response_text`、`latest_action`、`recent_rounds`、`live_stdout_tail`、`live_stderr_tail` 组合出可观测实时流。

**Tech Stack:** 静态 HTML、原生 JavaScript、共享 CSS、Python `pytest`

---

### Task 1: 记录设计约束

**Files:**
- Create: `docs/plans/2026-03-24-container-live-panel-design.md`
- Create: `docs/superpowers/plans/2026-03-24-container-live-panel.md`

- [ ] 记录“只展示可观测流，不伪造隐藏 CoT”
- [ ] 固定详情页新的信息架构

### Task 2: 重做详情页骨架

**Files:**
- Modify: `host/static/container.html`
- Modify: `host/static/app.css`

- [ ] 增加顶部强状态区
- [ ] 新增“AI 实时思路”与“实时轨迹”容器
- [ ] 保留资源区、最近几轮、原始日志

### Task 3: 实现实时渲染

**Files:**
- Modify: `host/static/container.js`

- [ ] 渲染最新思路、当前动作和轨迹
- [ ] 把日志降级为原始辅助区
- [ ] 增加自动刷新调度

### Task 4: 补测试与验证

**Files:**
- Modify: `tests/test_web_ui.py`

- [ ] 更新容器详情页静态文案断言
- [ ] 运行 `pytest tests/test_web_ui.py tests/test_design_lab.py tests/test_orchestrator.py -q`
- [ ] 重启 UI 并检查详情页首屏内容
