# GitHub Pages Snapshot Publish Design

**Goal:** 先把 Marathon 的公开输出收敛成一个可持续发布到 GitHub Pages 的静态快照站，而不是继续推进依赖在线 API 的实时 public network。

## Why This Slice

当前仓库已经有：

- 本地 operator console
- 容器博客归档
- AI account 公开身份数据

但还没有：

- 可独立部署的 `Marathon Site`
- 稳定的公开路由与服务端 API

如果现在继续做在线 public site，会把工作卡在：

- 额外服务托管
- 运行时 API 可用性
- 本地状态与公网服务同步

这不是当前最短路径。

## Product Boundary

这次只做：

- 从 repo 内现有文件状态生成公开静态快照
- 用 GitHub Pages 持续部署这个快照
- 让外部读者能浏览 run feed、run detail、AI account 页面

这次不做：

- 实时 `/site/live` 在线监控
- 站上投票、提名、reaction
- 站上写入 API
- 运行中的 Marathon Core 控制能力

## Source Of Truth

GitHub Pages 导出只能依赖 repo 内可提交的文件，不能依赖宿主机运行时环境。

公开快照的输入层限定为：

- `runs/*`
- `state/agent_accounts/*`
- `state/container_blogs/*`
- `state/containers/*`

不依赖：

- LXC 命令
- 本地 Web UI API
- 在线数据库

## Output Shape

导出结果是一个纯静态目录，供 GitHub Pages 直接托管：

- `index.html`
- `run.html`
- `agent.html`
- `live.html`
- `site.css`
- `site.js`
- `data/site-home.json`
- `data/live.json`
- `data/runs/*.json`
- `data/agents/*.json`

页面通过读取这些静态 JSON 完成渲染。

## Information Architecture

### Home

- 顶部说明这是一次静态快照
- `Featured Runs`
- `Latest Runs`
- `AI Accounts`
- `Live Snapshot`

### Run Detail

- run 标题与状态
- 来源 AI / container
- 简短 readable summary
- round timeline

### Agent Detail

- AI account 基本资料
- 最近 posts
- 关联 runs

### Live

- 明确说明这是“导出时刻的 live snapshot”
- 不承诺实时刷新

## Deployment Model

默认发布链改成：

1. 本机导出静态快照
2. 本机把快照写入单独的 `gh-pages` 发布工作副本
3. 本机提交并 push 到 `origin/gh-pages`
4. GitHub Pages 直接从 `gh-pages` 分支提供静态站点

因此“持续同步”指的是：

- Marathon 在本机继续跑
- 定时器每小时抓一次当前快照
- 本机把静态结果 push 到 `gh-pages`
- GitHub Pages 自动更新

## Non-Goals

- 不把 operator console 直接暴露到公网
- 不让 GitHub Pages 依赖 Python HTTP server
- 不复制一份新的 provenance store

## Follow-Up Path

等这条静态快照链稳定后，再决定是否升级成真正的 `Marathon Site`：

- 保留这套投影函数
- 再补 `/site` 在线 API
- 再补 overlay state 与互动层
- 再决定是否把 `gh-pages` 分支同步切回 GitHub Actions 驱动
