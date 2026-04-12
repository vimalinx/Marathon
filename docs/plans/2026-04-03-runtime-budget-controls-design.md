# Marathon Core Runtime Budget Controls Design

**Goal**

让 `Marathon Core` 的任务启动与容器详情页具备可见、可调、可继承的运行节奏与预算控制能力，同时保证详情页始终保留明确的返回导航。

## Why

当前 `Marathon Core` 已经支持基础的 `max_rounds`、`sleep_seconds` 和单次 `max_completion_tokens`，但这些控制分散在后端参数里，前端没有完整暴露，也没有容器级默认设置与备份机制。

结果是：

- 用户进入具体案例后，返回路径不够显式
- 用户无法直接在 UI 里约束任务总时长和总 token 预算
- 同一个容器缺少可复用的默认运行配置
- 修改容器默认设置时没有留出稳定的恢复点

## Product Shape

本次改动只影响 `Marathon Core` 的 operator UI。

不改：

- `Marathon Site` 公共快照站
- LXC 网络配置编辑器
- agent account 写入协议

新增能力分成三层：

### 1. 明确返回导航

在具体容器详情页保留清晰的顶栏返回入口，而不是只依赖品牌名链接。

### 2. 任务运行预算控制

对单次任务暴露这些可调控制项：

- 最大轮次 `max_rounds`
- 轮次间隔 `sleep_seconds`
- 总运行时长上限 `max_runtime_seconds`
- 总 token 预算 `max_total_tokens`
- 单次响应 token 上限 `max_completion_tokens`

其中：

- `max_rounds` 和 `sleep_seconds` 继续保持现有语义
- `max_runtime_seconds` 和 `max_total_tokens` 为新的整次任务预算
- token 预算按模型返回的 `usage.total_tokens` 累加
- 当预算命中时，当前轮完成后停止继续开新轮，并写入 `stop_reason`

### 3. 容器级默认设置

每个容器允许保存一份本地默认 AI 设置，供：

- 在该容器上直接启动任务时复用
- 从该容器克隆新任务时继承

这份默认设置属于 host 侧元数据，不属于 run provenance。

建议覆盖的字段：

- `mode`
- `task_prompt`
- `model`
- `base_url`
- `reasoning_effort`
- `temperature`
- `top_p`
- `max_completion_tokens`
- `request_timeout_seconds`
- `max_rounds`
- `sleep_seconds`
- `max_runtime_seconds`
- `max_total_tokens`

不把 `api_key` 放进容器默认设置，继续由全局模型配置提供。

## Data Ownership

### Run-level truth

运行中的真实预算与累计消耗写进 run 日志：

- `host_run.json`
- `ui_launch.json`
- `run.json`
- `status.json`
- `events.jsonl`
- 每轮 `response_raw.json`

### Container-level defaults

容器默认设置继续放在：

- `state/containers/<container>.json`

新增字段：

- `agent_settings`

### Backups

每次修改 `agent_settings` 前，先把旧容器元数据备份到：

- `state/container_settings_backups/<container>/<timestamp>.json`

这类备份属于 host 侧运维安全层，不参与公开站投影。

## Merge Rules

运行配置解析顺序：

1. 全局 model profile
2. 容器默认设置
3. 当前请求显式字段

显式请求永远覆盖容器默认设置。

## UI Shape

### New Task Page

补充可见控件：

- 最大轮次
- 轮次间隔
- 时长上限
- 总 token 预算
- 单次响应 token 上限

如果选择了一个已有容器作为来源模板，页面应加载并展示该容器保存的默认设置。

### Container Detail Page

新增一个“运行默认设置”侧栏卡片，允许保存容器默认设置，并显示最近一次备份信息。

详情页顶栏新增明确的“总览”返回入口。

## Out Of Scope

- 编辑原始 LXC config 文件
- 对历史 run 进行预算回填修复
- 多版本备份浏览器式管理界面
- 细粒度美元成本估算
