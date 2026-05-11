# ADR-006: SSE vs 轮询 — 导入进度追踪

**Status**: Accepted (保持现状)
**Date**: 2026-05-11

## Context

ThreeColumnLayout.vue 同时维护：
- SSE 连接（`/events/stream`）— 接收所有项目事件（DATASET_ACTIVATED 等）
- 5s 轮询（`/active-job`）— 专门查导入进度

两者功能部分重叠。

## Decision

**保持双通道**，各司其职：
- SSE：推送业务事件（activate/rollback/stale），触发视图自动刷新
- 轮询：查询导入进度（phase/percent/message），驱动顶栏进度指示器

## Rationale

1. SSE 可能断连（网络抖动/代理超时），轮询作为兜底更可靠
2. 导入进度需要精确百分比（每 5%/10k 行更新），SSE 事件粒度太粗
3. 轮询只在有活跃 job 时才有意义（idle 时 5s 一次开销可忽略）
4. 未来如需去重：让 SSE 推送 IMPORT_PROGRESS 事件，前端收到后跳过下一次轮询

## Consequences

- 短期无需改动，当前架构满足需求
- 长期如 SSE 稳定性提升，可考虑用 SSE 替代轮询（减少 1 个 HTTP 请求/5s）
