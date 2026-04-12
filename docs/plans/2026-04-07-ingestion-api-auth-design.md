# Marathon Core Ingestion API Auth Design

**Goal**

给 `POST /api/ingest/*` 增加最小可用的服务端鉴权，避免在未来远程 writer 或多进程采集场景下仍然完全依赖“本机可信”假设。

## Scope

只保护这些入口：

- `POST /api/ingest/runs`
- `POST /api/ingest/events`
- `POST /api/ingest/round-posts`
- `POST /api/ingest/artifacts`

## Auth Model

第一版采用单 token 模型：

- 服务器环境变量：`MARATHON_INGEST_TOKEN`
- 客户端可通过以下任一方式发送：
  - `X-Marathon-Ingest-Token: <token>`
  - `Authorization: Bearer <token>`
  - request body 里的 `ingest_token`（仅为脚本兼容保留，不作为首选）

## Compatibility

为了不打断当前本地开发和测试：

- 如果 `MARATHON_INGEST_TOKEN` 未设置：继续允许匿名写入
- 如果 `MARATHON_INGEST_TOKEN` 已设置：必须校验通过

这让当前单机 `v0.x` 默认体验不变，但给服务端部署预留了开关。

## Error Behavior

未通过鉴权时：

- 返回 `403 Forbidden`
- 错误文案明确说明 ingestion token 缺失或不匹配

## Out Of Scope

- 多 token
- per-writer identity
- token rotation
- body signing
