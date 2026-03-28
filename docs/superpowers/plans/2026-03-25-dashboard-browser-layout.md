# Dashboard Browser Layout Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把首页改成顶部筛选、当前重点横排卡片、最近活跃网格的浏览器式布局。

**Architecture:** 复用现有 `/api/overview` 数据，在前端按筛选和优先级切出“当前重点”和“最近活跃”两个集合。HTML 只提供容器骨架，卡片与筛选状态全部由 `dashboard.js` 驱动，样式沿用现有浅色系统并新增首页专用卡片布局。

**Tech Stack:** 静态 HTML、原生 JavaScript、共享 CSS、Python `pytest`

---

### Task 1: 写入设计与计划

**Files:**
- Create: `docs/plans/2026-03-25-dashboard-browser-layout-design.md`
- Create: `docs/superpowers/plans/2026-03-25-dashboard-browser-layout.md`

- [ ] 固定新的首页信息架构
- [ ] 固定筛选与卡片分组规则

### Task 2: 重构首页骨架与样式

**Files:**
- Modify: `host/static/index.html`
- Modify: `host/static/app.css`

- [ ] 增加顶部筛选栏
- [ ] 增加“当前重点”横排容器
- [ ] 增加“最近活跃”网格容器
- [ ] 新增重点卡和简卡样式

### Task 3: 重构首页脚本

**Files:**
- Modify: `host/static/dashboard.js`

- [ ] 实现筛选状态管理
- [ ] 渲染重点卡片
- [ ] 渲染最近活跃网格
- [ ] 加入自动刷新

### Task 4: 验证

**Files:**
- Modify: `tests/test_web_ui.py`

- [ ] 更新首页静态结构断言
- [ ] 运行 `pytest tests/test_web_ui.py tests/test_design_lab.py tests/test_orchestrator.py -q`
- [ ] 重启 UI 并检查首页关键内容
