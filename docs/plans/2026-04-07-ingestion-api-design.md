# Marathon Core Ingestion API Design

**Goal**

在保留当前文件真相层的前提下，为 `Marathon Core` 提供一个最小可用的 host-side ingestion API，让外部 worker、nightly runner 或未来远程 agent 不必依赖本地文件扫描才能把运行事实写进系统。

## Scope

第一版只做 4 类写入：

- run metadata / status
- events
- round posts
- artifacts

所有写入都落回：

- `runs/<run_id>/...`

也就是：

- API 是写入口
- 文件树仍然是事实层
- SQLite index 继续作为查询投影层

## Endpoints

### `POST /api/ingest/runs`

用途：

- 初始化或更新 run 级文件

写入目标：

- `run.json`
- `host_run.json`
- `ui_launch.json`
- `status.json`
- `launch.json`（可选）

### `POST /api/ingest/events`

用途：

- 追加事件流

写入目标：

- `events.jsonl`

### `POST /api/ingest/round-posts`

用途：

- 追加 round-level readable timeline

写入目标：

- `blog.jsonl`
- `latest_round.json`
- `latest_action.json`

### `POST /api/ingest/artifacts`

用途：

- 写入任意已允许的 top-level 或 round-level artifact

第一版允许：

- top-level:
  - `latest_response.txt`
  - `latest_tool_result.json`
  - `latest_state_before.json`
  - `latest_state_after.json`
  - `live.stdout`
  - `live.stderr`
  - `supervisor.stdout`
  - `supervisor.stderr`
- round-level:
  - `request.json`
  - `response.txt`
  - `response_raw.json`
  - `action.json`
  - `tool_result.json`
  - `state_before.json`
  - `state_after.json`
  - `error.json`
  - `response.invalid-*.txt`
  - `response.invalid-*.raw.json`

## Safety Rules

- `run_id` 必须通过现有 `require_name`
- round-level artifact 的 round 必须是正整数
- 只允许写白名单文件名，避免路径逃逸
- `json` artifact 必须是对象或数组，不接受任意字符串伪装 JSON

## UI Boundary

第一版 ingestion API 不一定在 UI 上直接暴露按钮。

先作为：

- server-to-server 写入口
- future worker / nightly / external runtime 入口

## Out Of Scope

- Auth
- Multi-tenant quotas
- Remote upload streaming
- DB-first ingestion
