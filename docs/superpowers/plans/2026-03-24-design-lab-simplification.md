# Design Lab Simplification Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把设计实验室首页和三套方案页收缩成低认知负担的三块式结构。

**Architecture:** 保留现有后端接口和 `shared.js` 的上下文传递能力，只重写静态页面结构、渲染分组和文案。每个方案页保留独立视觉风格，但都遵守“最多三个主块”的共同约束。

**Tech Stack:** 静态 HTML、原生 JavaScript、共享 CSS、Python `pytest`

---

### Task 1: 写入约束文档

**Files:**
- Create: `docs/plans/2026-03-24-design-lab-simplification-design.md`
- Create: `docs/superpowers/plans/2026-03-24-design-lab-simplification.md`

- [ ] 记录新的信息架构和范围边界
- [ ] 明确每个方案页只保留三个主块

### Task 2: 收缩首页

**Files:**
- Modify: `host/static/design-lab/index.html`
- Modify: `host/static/design-lab/shared.js`

- [ ] 删除 rubric 和重复说明
- [ ] 保留上下文输入、一行概览、三张方案卡
- [ ] 缩短首页概览文案

### Task 3: 收缩观察台

**Files:**
- Modify: `host/static/design-lab/design-consultation.html`

- [ ] 合并“概况 + 当前轮次 + 自我修改”为“当前”
- [ ] 保留“时间线”
- [ ] 把命令、模型、stdout/stderr、工作区并入“输出”

### Task 4: 收缩控制台

**Files:**
- Modify: `host/static/design-lab/ui-ux-pro-max.html`

- [ ] 合并“状态带 + KPI + 自我修改”为“状态”
- [ ] 保留“动态”
- [ ] 保留“输出”

### Task 5: 收缩流程台

**Files:**
- Modify: `host/static/design-lab/penpot-uiux-design.html`

- [ ] 合并“阶段 + 当前上下文”为“上下文”
- [ ] 保留“时间线”
- [ ] 合并“细节面板 + 自我修改”为“细节”

### Task 6: 更新验证

**Files:**
- Modify: `tests/test_design_lab.py`

- [ ] 更新静态结构断言到新的 section id 和文案
- [ ] 运行 `pytest tests/test_design_lab.py tests/test_web_ui.py tests/test_orchestrator.py -q`
- [ ] 重启 UI 并做一次页面冒烟检查
