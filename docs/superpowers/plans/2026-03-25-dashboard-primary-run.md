# Dashboard Primary Run Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把总览页改成“顶部主运行大卡 + 下方其他容器简卡”的结构。

**Architecture:** 复用现有 `/api/overview` 数据，不增加后端接口。用前端排序逻辑选出一个主运行容器，把它渲染成大卡，其余容器按简卡渲染，并增加自动刷新调度。

**Tech Stack:** 静态 HTML、原生 JavaScript、共享 CSS、Python `pytest`

---

### Task 1: 写入设计与计划

**Files:**
- Create: `docs/plans/2026-03-25-dashboard-primary-run-design.md`
- Create: `docs/superpowers/plans/2026-03-25-dashboard-primary-run.md`

- [ ] 固定首页新的信息架构
- [ ] 记录主运行选择规则

### Task 2: 重构首页骨架与样式

**Files:**
- Modify: `host/static/index.html`
- Modify: `host/static/app.css`

- [ ] 增加主运行区容器
- [ ] 调整“整体情况”和“其他容器”顺序
- [ ] 为主运行卡和简卡补样式

### Task 3: 重构首页脚本

**Files:**
- Modify: `host/static/dashboard.js`

- [ ] 选出主运行容器
- [ ] 渲染主运行大卡
- [ ] 渲染其余容器简卡
- [ ] 增加自动刷新

### Task 4: 验证

**Files:**
- Modify: `tests/test_web_ui.py`

- [ ] 更新首页静态结构断言
- [ ] 运行 `pytest tests/test_web_ui.py tests/test_design_lab.py tests/test_orchestrator.py -q`
- [ ] 重启 UI 并检查首页关键文案
