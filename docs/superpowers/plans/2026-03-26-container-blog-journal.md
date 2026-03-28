# Container Blog Journal Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 Marathon 改成“每个容器一个长期博客”的实验系统，AI 每轮输出完整的 done / next / thought，并把这些内容持久化成容器级 JSONL，再默认展示到网页上。

**Architecture:** 容器内 `agent_loop` 直接产出完整 round post 与 run 级 `blog.jsonl`；宿主 `host.orchestrator` 在同步时把 run 级博客增量归并到 `state/container_blogs/<container>.jsonl`；`host.web_ui` 聚合容器博客并暴露 API；静态前端改成默认消费博客内容而不是摘要字段。

**Tech Stack:** Python 标准库、原生 HTML/CSS/JavaScript、`pytest`

---

### Task 1: 写入设计与计划

**Files:**
- Create: `docs/plans/2026-03-26-container-blog-journal-design.md`
- Create: `docs/superpowers/plans/2026-03-26-container-blog-journal.md`
- Modify: `task_plan.md`
- Modify: `findings.md`
- Modify: `progress.md`

- [ ] 固定“每容器单独博客”的产品边界
- [ ] 固定新动作协议与 blog post 结构
- [ ] 记录运行链路改造点

### Task 2: 重构容器内动作协议与 round 日志

**Files:**
- Modify: `prompts/minimal_system.txt`
- Modify: `container/agent_loop.py`
- Test: `tests/test_agent_loop.py`

- [ ] 更新系统提示词，要求模型输出 `done` / `next` / `thought`
- [ ] 新增动作校验与机器摘要派生
- [ ] 调整 `recent_rounds`、`latest_round.json`、`events.jsonl`、`blog.jsonl`
- [ ] 更新单测断言

### Task 3: 重构宿主同步与容器博客归档

**Files:**
- Modify: `host/orchestrator.py`
- Modify: `host/web_ui.py`
- Test: `tests/test_web_ui.py`

- [ ] 同步 run 级 `blog.jsonl`
- [ ] 增加 `state/container_blogs/` 容器级持久化归档
- [ ] 在 overview/container detail 中聚合最近博客内容
- [ ] 增加容器博客 API
- [ ] 更新后端测试

### Task 4: 重做前端博客视图

**Files:**
- Modify: `host/static/app.js`
- Modify: `host/static/app.css`
- Modify: `host/static/container.html`
- Modify: `host/static/container.js`
- Modify: `host/static/dashboard.js`
- Modify: `host/static/sandboxes.js`
- Test: `tests/test_web_ui.py`

- [ ] 把容器详情页主区域改成博客流
- [ ] 首页卡片改为显示最近博客内容
- [ ] 容器列表改为显示最近博客片段
- [ ] 保留运行状态与原始日志，但不再以摘要视图为主

### Task 5: 验证

**Files:**
- Modify: `progress.md`

- [ ] 运行 `pytest tests/test_agent_loop.py tests/test_web_ui.py -q`
- [ ] 运行 `pytest -q`
- [ ] 启动 `python3 -m host.web_ui --host 127.0.0.1 --port 8877`
- [ ] 抽查 `/api/overview` 与 `/api/containers/<name>` 返回结构

### Task 6: 记录后续多实例云同步方案

**Files:**
- Modify: `docs/plans/2026-03-26-container-blog-journal-design.md`
- Modify: `docs/superpowers/plans/2026-03-26-container-blog-journal.md`

- [ ] 说明本地 `state/container_blogs/*.jsonl` 仍是 source of truth
- [ ] 说明按小时增量同步与本地 cursor 的思路
- [ ] 说明未来要补一份给 AI 直接读取的云同步 `.md` 协议文档
