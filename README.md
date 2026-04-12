# Marathon

一个用于“零干预、自循环、本地沙盒 AI 智能体实验”的极简原型。

## Open Source Scope

如果现在以 `v0.1` 公开发布，建议把仓库主支持面理解为：

- `Marathon Core`：本地容器运行、宿主观察、nightly 路径、operator UI

下面这些区域目前更偏实验或扩展能力：

- `Marathon Site`
- `design-lab`
- GitHub Pages 快照发布链

协作与发布相关文档：

- [CONTRIBUTING.md](./CONTRIBUTING.md)
- [SECURITY.md](./SECURITY.md)
- [CODE_OF_CONDUCT.md](./CODE_OF_CONDUCT.md)
- [RELEASING.md](./RELEASING.md)
- [CHANGELOG.md](./CHANGELOG.md)

如果你要把新的 ingestion API 暴露给外部 writer 或远程 worker，建议额外设置：

```bash
export MARATHON_INGEST_TOKEN=你自己的服务端写入令牌
```

之后外部写入方需要带上：

- `X-Marathon-Ingest-Token: <token>`
或
- `Authorization: Bearer <token>`

这版采用的是：**AI 主体运行在容器内部，宿主机只负责启动、观察、镜像日志和回收容器。**

现在另外补了一套**独立的宿主机 nightly 模式**：

- LXC 模式继续保留，用来做强隔离实验。
- host nightly 模式直接在真实 Git 仓库里跑，不接 Web UI，不碰 LXC。
- 它会每晚新开一个 `marathon/nightly-YYYYMMDD-HHMMSS` 分支，按轮提交，第二天早上直接看 Git 历史。

## 当前结构

- `container/agent_loop.py`：AI 的自循环主程序，运行在容器里。
- `container/agent_tools.py`：容器内唯一工具，只负责执行一条命令。
- `prompts/minimal_system.txt`：最小提示词，也会被复制到容器内 `/opt/marathon/minimal_system.txt`。
- `host/orchestrator.py`：宿主观察器，负责启动容器内 agent、同步状态到宿主、按轮做 Git 备份。
- `host/host_nightly.py`：宿主机 nightly 模式的 Git、配置和 `systemd --user` unit helper。
- `host/host_nightly_runner.py`：单次宿主机 nightly run 入口，直接对真实仓库跑 agent。
- `host/prune_container_state.py`：清理已经销毁容器留下的 stale `state/containers/*.json`。
- `scripts/create_base_container.sh`：创建基础 LXC 容器。
- `scripts/start_run.sh`：复制 base 容器并启动一个 run。
- `scripts/run_host_nightly_once.sh`：对一个真实仓库执行一次 host nightly run。
- `scripts/setup_host_nightly.sh`：为一个真实仓库安装 `systemd --user` nightly timer。
- `scripts/prune_container_state.sh`：扫描并清理 stale 容器状态元数据。

## 设计原则

- **AI 在容器里**：不是宿主机调用模型再操纵容器，而是容器里的 agent 自己调用模型、自己执行命令、自己修改自己。
- **只给一个工具**：唯一可用外部能力就是执行一条命令。
- **零历史上下文**：每轮不会把前几轮结果回灌给模型。
- **工具源码可见**：AI 可以在容器内直接查看和修改 `/opt/marathon/agent_tools.py` 与 `/opt/marathon/agent_loop.py`。
- **宿主只围观**：宿主机会同步 `status.json`、`events.jsonl`、最近动作和输出，并在 `runs/<run_id>` 做 Git 提交。

## 模型默认配置

如果存在 `~/.config/marathon/model.env`，`start_run.sh`、宿主侧 Web UI 和 host nightly 入口都会自动读取它。

推荐把模型配置写成：

```bash
export MARATHON_BASE_URL=https://your-provider.example/v1
export MARATHON_API_KEY=你的密钥
export MARATHON_MODEL=gpt-5.4
```

显式导出的环境变量仍然优先于这个文件。

注意：

- `MARATHON_BASE_URL` 和 `MARATHON_API_KEY` 现在都视为必填
- 仓库不再内置默认 provider 地址

## Web UI

现在提供一个宿主侧 Web UI，用来管理这整套系统：

新版布局现在改成**容器优先**：

- 先选一个沙盒容器
- 再决定是启动/停止容器，还是“装上 AI 并启动”
- `run` 依然存在，但退到后台自动生成，主要只用于保存日志、轮次和宿主机镜像备份

主屏会优先显示当前沙盒对应的 AI 输出、动作、文件状态和最近轮次；复杂运维被收进抽屉。

- 创建 base 容器
- 克隆容器
- 启动 / 停止 / 销毁容器
- 从 base 容器复制出一个新沙盒并直接启动 AI
- 给任意现有容器同步 AI 文件并直接启动
- 查看当前沙盒的最新 AI 输出、最近动作、最近输出
- 对当前沙盒里的 AI 下发停止请求

启动方式：

```bash
chmod +x scripts/start_web_ui.sh scripts/stop_web_ui.sh
./scripts/start_web_ui.sh
```

默认监听：

```text
http://127.0.0.1:8765
```

说明：

- Web UI 是宿主侧面板，不在容器里运行。
- `scripts/start_web_ui.sh` 默认通过 `tmux` 常驻启动，避免被临时 shell 会话退出时一并带走。
- 如果 `8765` 端口已经被其他程序占用，启动脚本会明确报错，而不是假装启动成功。
- Web UI 和宿主 supervisor 默认用非交互 `sudo -n` 调用 LXC；如果你没有为相关命令配置免密 sudo，它会直接报错而不是卡住。
- 它有权管理 LXC 和 supervisor 进程，所以默认只应绑定在本机地址。
- 如果你通过 Web UI 启动 run，容器不会像 `scripts/start_run.sh` 那样在结束时自动销毁；你可以在 UI 里手动销毁。

## 网络说明

因为 agent 现在运行在容器内部，所以**容器必须能访问模型接口**。

- 默认 `DISABLE_NETWORK=0`，这样容器可以直接请求模型。
- 如果你设 `DISABLE_NETWORK=1`，容器会断网，这时容器内 agent 将无法继续调用模型。
- 更稳妥的做法是：保留网络，但在宿主机防火墙层只允许容器访问模型地址。

## 清理遗留容器状态

如果你之前跑过很多临时容器，`state/containers/*.json` 里可能会留下已经销毁容器的旧状态文件。

先 dry-run 看看会删什么：

```bash
./scripts/prune_container_state.sh
```

确认后再真正删除：

```bash
./scripts/prune_container_state.sh --apply
```

这个脚本默认只会处理“`/var/lib/lxc/<container_name>` 已经不存在”的状态文件。

## 快速开始

### 1. 创建基础容器

```bash
chmod +x scripts/create_base_container.sh scripts/start_run.sh
./scripts/create_base_container.sh marathon-base
```

### 2. 配置密钥

```bash
export MARATHON_BASE_URL=https://your-provider.example/v1
export MARATHON_API_KEY=你的密钥
```

### 3. 启动一个 run

```bash
./scripts/start_run.sh marathon-base
```

默认无限循环。也可以限制轮数：

```bash
export MAX_ROUNDS=100
export ROUND_SLEEP_SECONDS=1
./scripts/start_run.sh marathon-base
```

### 4. 停止 run

在宿主机：

```bash
touch runs/<run_id>/STOP
```

宿主观察器会把这个停止请求同步进容器，容器内 agent 在下一轮前停止。

## 宿主机 Nightly 模式

这是一套和 LXC 路径**分开的**宿主机自动运行模式，直接在真实项目仓库里工作。

特点：

- 每次运行前先 `git fetch origin`
- 默认从 `origin/HEAD` 解析默认分支
- 如果工作区一开始就是脏的，会先在当前分支打一个明确 checkpoint 提交
- 然后新开一个 nightly 分支继续跑
- 每轮只有真的改动了文件才提交
- 不自动 push、不自动 merge、不自动开 PR
- 到本地时间 `08:00:00` 后不再开启新一轮，当前轮跑完就停

手动跑一次：

```bash
./scripts/run_host_nightly_once.sh <repo_path>
```

安装每天自动跑：

```bash
./scripts/setup_host_nightly.sh <repo_path>
```

默认会在仓库里创建：

- 分支：`marathon/nightly-YYYYMMDD-HHMMSS`
- 项目配置：`state/host_projects/<slug>.json`
- 运行日志：`host-runs/<slug>/<run_id>/`

这个模式依赖：

- 目标目录本身就是一个正常 Git 仓库
- 仓库有可用的 `origin`
- `origin/HEAD` 能解析到默认分支
- 当前用户可用 `systemctl --user`（仅自动调度时需要）

## 容器内日志

容器内每个 run 会写到：

```text
/workspace/runtime-log/<run_id>/
```

包含：

- `run.json`
- `status.json`
- `events.jsonl`
- `latest_action.json`
- `latest_tool_result.json`
- `rounds/0001/...`

这些文件会在容器内按轮做 Git 提交。

## 宿主机镜像日志

宿主机会把关键文件镜像到：

```text
runs/<run_id>/
```

## GitHub Pages 快照发布

如果你暂时不想做在线 public site，而只想把当前仓库里的公开状态持续同步到 GitHub Pages，现在可以走静态快照发布链。

它的边界是：

- 只发布 repo 里已经存在的文件状态
- 不依赖本地 Web UI 服务在线
- 不暴露 operator console
- 适合把 `runs/`、`state/agent_accounts/` 这些公开层数据投影成一个只读站点

本地手动导出：

```bash
python3 scripts/export_github_pages.py --output-dir build/github-pages
```

导出目录里会包含：

- `index.html`
- `run.html`
- `agent.html`
- `live.html`
- `data/site-home.json`
- `data/runs/*.json`
- `data/agents/*.json`

如果只是手动导出，本地直接跑：

```bash
python3 scripts/export_github_pages.py --output-dir build/github-pages
```

如果你要让这台机器每小时自动同步一次到 GitHub Pages，用这条：

```bash
./scripts/setup_github_pages_sync.sh
```

它会安装一个 `systemd --user` timer，默认每小时执行一次：

- 导出当前静态快照
- 写入单独的 `gh-pages` 发布工作副本
- 提交快照更新
- `git push origin gh-pages`

前提条件：

- 这个仓库本身已经配置好 `origin`
- `origin` 指向 GitHub 上的目标仓库
- 你的 GitHub Pages source 配置为 `Deploy from a branch`
- 分支选择 `gh-pages`，目录选择 `/ (root)`

也就是说，Pages 的持续更新路径是：

```text
本机 Marathon 状态 -> 静态导出 -> 本机 push gh-pages -> GitHub Pages
```

## Ingestion API

现在仓库还提供了一套最小服务端写入口，写回 `runs/<run_id>/` 真相层：

- `POST /api/ingest/runs`
- `POST /api/ingest/events`
- `POST /api/ingest/round-posts`
- `POST /api/ingest/artifacts`

默认本地开发场景下，如果没有设置 `MARATHON_INGEST_TOKEN`，这些入口保持匿名可写。

如果你准备把它用于更像服务端的部署，建议设置 `MARATHON_INGEST_TOKEN` 后再开放写入口。

仓库里还保留了一个 GitHub Actions Pages workflow：

```text
.github/workflows/deploy-pages.yml
```

这个 workflow 现在只保留 `workflow_dispatch`，不再作为每小时自动同步的主路径。

默认同步这些：

- `status.json`
- `events.jsonl`
- `latest_action.json`
- `latest_tool_result.json`
- `latest_state_before.json`
- `latest_state_after.json`
- `live.stdout`
- `live.stderr`

每当检测到新一轮完成，宿主机都会在 `runs/<run_id>` 内做一次 Git 提交。

## JSON 输出格式

模型每轮只能输出：

```json
{
  "done": "完整说明这轮刚刚做了什么、观察到了什么、得出了什么结论",
  "next": "完整说明下一步准备做什么，为什么要做这个动作",
  "thought": "完整说明当前思路、判断、怀疑点、取舍，不要只写一句话",
  "argv": ["bash", "-lc", "pwd && ls -la"],
  "timeout": 30
}
```

## Release Checklist

公开发布前，至少确认：

- `python3 -m pytest -q` 全绿
- README 在一台干净机器上可复现
- 没有提交真实 API key 或本地环境文件
- 已添加正式许可证文件

## 关键边界

- AI 现在是真正在容器里跑，不是在容器外遥控容器。
- 它能直接把自己在容器里的工具和主循环改坏。
- 坏掉的是这个 run 容器；丢弃容器后可从 base 容器重新复制。
- 如果你要更强边界，建议后续再加非特权 LXC、非 root 用户和更细的网络出站限制。
