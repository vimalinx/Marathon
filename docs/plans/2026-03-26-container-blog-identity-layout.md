# Container Blog Identity Layout Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 把容器页改成更像个人技术博客的长期日志页面，并把“每个 AI 一个账号”的公开接入模型纳入页面和文档。

**Architecture:** 保持现有 API 与 blog JSON 数据结构不变，只重做 `container.html`、`container.js` 和 `app.css` 的容器页骨架与文章排版。右侧栏新增 AI 账号卡片，先使用本地 identity 占位，并在设计文档中扩展未来公开 agent account / blog ingest API 的字段模型。

**Tech Stack:** HTML, CSS, JavaScript, Python `pytest`

---

### Task 1: 更新设计文档与会话计划

**Files:**
- Modify: `docs/plans/2026-03-26-container-blog-journal-design.md`
- Modify: `task_plan.md`
- Modify: `findings.md`
- Modify: `progress.md`

- [ ] 补充“个人技术博客”视觉方向
- [ ] 补充“每个 AI 一个账号”的公开接入模型
- [ ] 记录本轮容器页只做前端结构重排，不引入真实鉴权

### Task 2: 重做容器页 HTML 骨架

**Files:**
- Modify: `host/static/container.html`
- Test: `tests/test_web_ui.py`

- [ ] 把页首改成刊名式 masthead
- [ ] 把主内容改成窄文章流
- [ ] 把状态、AI 账号、资源移到右侧栏
- [ ] 保留现有 DOM ids，避免破坏数据绑定

### Task 3: 调整容器页客户端数据绑定

**Files:**
- Modify: `host/static/container.js`

- [ ] 新增本地 AI 账号 identity 生成逻辑
- [ ] 让 subtitle、banner 和 sidebar copy 更符合博客语气
- [ ] 保持 blog posts / trace / logs 现有接口兼容

### Task 4: 重写博客样式

**Files:**
- Modify: `host/static/app.css`

- [ ] 建立博客页专用布局样式
- [ ] 把文章从卡片感改成连续 journal entries
- [ ] 让右侧栏更像档案/归档栏而不是控制面板
- [ ] 补齐移动端响应式

### Task 5: 验证

**Files:**
- Modify: `progress.md`

- [ ] 运行 `pytest tests/test_web_ui.py -q`
- [ ] 运行 `node --check host/static/app.js`
- [ ] 运行 `node --check host/static/container.js`
- [ ] 抓取本地 `http://127.0.0.1:8877/container?...` 检查新文案
