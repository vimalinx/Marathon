# Marathon Core Run Index Design

**Goal**

在不替换现有文件真相层的前提下，为 `Marathon Core` 增加一个可查询的本地索引层，让 operator UI 和后续服务端收集演进不再直接依赖到处扫 `runs/` 和 `state/*`。

## Current Problem

当前数据链路是：

`container runtime -> host mirror files -> web_ui scan files`

这在单机小规模下可用，但会带来几个问题：

- 每个 UI 请求都要重新拼接多个 JSON/JSONL 文件
- 失败证据和 round-level artifact 很难稳定查询
- 后续如果要做统一 ingestion API 或数据库后端，没有中间层

## Scope

这一步只做 **查询索引层**。

不改：

- 容器内原始 runtime 文件格式
- `runs/` 作为宿主真相镜像层
- `state/container_blogs` / `state/agent_accounts` 的写入方式

## Storage Model

新增一个本地 SQLite 数据库，建议路径：

- `state/run_index.sqlite3`

它不是新的真相源，只是从文件层重建的查询投影。

## Tables

### `runs`

存 run 级摘要和关键原始 blob：

- run summary fields
- host/ui/status/action/result/state json blobs
- latest response / stdout / stderr / events tail
- signature for incremental refresh

### `round_posts`

存每轮可读 timeline：

- round
- done / next / thought / summary
- argv / timeout
- prompt/completion/total tokens
- tool result tail
- failed flag / error text
- raw json

### `events`

存事件流：

- event type
- round
- ts
- raw json

### `artifacts`

存 round 附件，先覆盖：

- `error.json`
- `response.invalid-*.txt`
- `response.invalid-*.raw.json`

## Refresh Strategy

先采用简单稳妥策略：

- 扫描 `runs/<run_id>/`
- 忽略 `.git/`
- 计算每个 run 的文件签名
- 签名变化时全量重建该 run 的索引
- 未变化则跳过

这是单机 `v0.x` 足够合理的成本。

## Integration Plan

第一步接两条读路径：

- `overview_payload()` 使用索引后的 `runs`
- `run_detail(run_id)` 使用索引后的：
  - run summary
  - recent events
  - blog posts
  - invalid-response artifacts
  - latest raw text fields

容器运行态指标 `read_container_runtime()` 仍然现场读取，不进索引。

## Boundaries

### Truth

真相层仍然是：

- `runs/*`
- `state/container_blogs/*`
- `state/agent_accounts/*`

### Projection

SQLite 只是 projection/cache/query layer，可删可重建。

## Out Of Scope

- 多机同步
- 远程 ingestion API
- Postgres
- public site 改读索引
