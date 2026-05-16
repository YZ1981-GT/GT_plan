# 事件级联健康度运维指南

**版本**：v1.0（R10 Spec C / Sprint 2.5.2）
**最后更新**：2026-05-16
**适用对象**：DevOps、合伙人、管理员

---

## 1. 端点

```
GET /api/projects/{pid}/event-cascade/health
```

- **admin / partner**：完整 schema（lag_seconds + stuck_handlers + dlq_depth + worker_status + redis_available + status）
- **普通用户**：仅 `{status, lag_seconds}` 两字段（design D3 隔离）

---

## 2. 4 个 worker 职责

| Worker | 职责 | 心跳频率 | TTL |
|--------|------|---------|-----|
| `sla_worker` | 检查工单 SLA 超时（每 15 分钟）；每 30s 写心跳 | 30s | 60s |
| `import_recover_worker` | 恢复僵尸导入任务（每 30s） | 30s | 60s |
| `outbox_replay_worker` | 重放失败的事件（基于退避算法） | 5-300s | 60s |
| `import_worker` | standalone 进程，跑 ImportJobRunner.run_forever | 1-60s | 60s |

**心跳机制**：每个 worker 主循环每轮调 `await write_heartbeat("worker_name")` 写入 Redis key `worker_heartbeat:{name}`，TTL=60s 自动过期。Redis 不可用时降级仅日志，不阻断 worker。

---

## 3. outbox + DLQ 工作机制

```
[业务代码] → ImportEventOutboxService.publish()
                      ↓
              import_event_outbox 表
                  status=pending
                      ↓
        outbox_replay_worker 主循环
        - 读 pending 事件
        - 调对应 handler
        - 成功 → status=succeeded
        - 失败 → attempts+1, status=failed
                      ↓
        attempts >= MAX_RETRY_ATTEMPTS
                      ↓
              event_outbox_dlq 表
                 死信队列保留
              （需运维手动介入）
```

---

## 4. lag/stuck/dlq 告警阈值

### 4.1 状态判定（design D2）

| 状态 | 条件 |
|------|------|
| `healthy` | lag ≤ 60s AND dlq=0 AND 全部 worker alive |
| `degraded` | lag > 60s OR dlq > 0 OR 1 个 worker miss OR Redis 不可用 |
| `critical` | lag > 300s OR worker miss > 1 |

### 4.2 用户感知

DegradedBanner.vue 三档：
- 🟢 **隐藏**：healthy
- 🟡 **服务响应较慢**：degraded
- 🔴 **部分功能暂时不可用**：critical

仅 admin/partner 可点击展开看 worker 心跳详情、outbox lag、DLQ 深度。

---

## 5. 故障排查 cookbook（7 种常见场景）

### 场景 1：lag_seconds 持续上升 > 300s

**可能原因**：
- outbox_replay_worker 没启动 / 已死
- 单个 handler 处理慢（DB 锁、外部 API 超时）
- 事件量突增

**排查步骤**：
1. `health.worker_status.outbox_replay_worker.alive` 是否为 true
2. `SELECT * FROM import_event_outbox WHERE status='processing' ORDER BY updated_at LIMIT 10` 看哪些 handler 卡住
3. 查 worker 日志 `tail -f backend/import_outbox.log`
4. 必要时手动重启 backend 服务

### 场景 2：dlq_depth > 0

**可能原因**：事件重试 N 次仍失败（N=LEDGER_IMPORT_OUTBOX_MAX_RETRY_ATTEMPTS）

**排查步骤**：
1. `SELECT * FROM event_outbox_dlq WHERE resolved_at IS NULL ORDER BY moved_to_dlq_at LIMIT 10`
2. 查 `last_error` 字段定位失败原因
3. 修复底层 bug 后，可手动 `UPDATE event_outbox_dlq SET resolved_at=now() WHERE id=...`
4. 或手动重新 publish 同样 payload 重试

### 场景 3：worker_status.X.alive=false（单个 worker miss）

**可能原因**：
- worker 任务异常崩溃
- Redis 连接断开导致心跳无法写入
- 服务刚启动还未首次写心跳（< 30s 后 alive=true）

**排查步骤**：
1. `health.worker_status.X.last_heartbeat` 看最后心跳时间
2. 距今 > 60s → worker 已死或 Redis 异常
3. 查 backend 启动日志确认 lifespan 是否启动了该 worker
4. 重启 backend

### 场景 4：critical 状态（多 worker miss）

**可能原因**：backend 整体异常 / Redis 全连接断开 / OOM

**排查步骤**：
1. 立即 `curl /health` 看后端基础健康
2. `docker logs backend` 查最近异常
3. `redis-cli ping` 确认 Redis
4. `free -h` 检查内存

### 场景 5：redis_available=false

**可能原因**：Redis 连接断开

**排查步骤**：
1. `docker ps | grep redis` 确认容器存活
2. `redis-cli ping`
3. backend 自动降级为"仅业务执行不写心跳"，业务正常但监控降级；恢复 Redis 后 60s 内 worker 心跳恢复

### 场景 6：DegradedBanner 一直显示但实际没问题

**可能原因**：sessionStorage 残留 / 浏览器缓存

**排查**：用户点 banner 关闭按钮自动 dismiss 5 分钟；或清除 sessionStorage

### 场景 7：stuck_handlers 列出某 handler 处理 > 30 分钟

**可能原因**：handler 内部 SQL 死锁 / 外部 API 永久挂起

**排查步骤**：
1. `health.stuck_handlers[*].outbox_id` 拿到事件 ID
2. `SELECT pg_stat_activity` 看是否有 hang 的 query
3. 必要时手动 `UPDATE import_event_outbox SET status='failed', last_error='stuck >30min' WHERE id=...` 让 worker 重试

---

## 6. 监控集成

### 6.1 通过 health 端点轮询（推荐）

```sh
# Prometheus 抓取
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
  https://gt-platform.com/api/projects/$PID/event-cascade/health \
  | jq -r '.status'
```

### 6.2 直接读 Redis（高频运维）

```sh
redis-cli get worker_heartbeat:sla_worker
redis-cli get worker_heartbeat:import_recover_worker
redis-cli get worker_heartbeat:outbox_replay_worker
redis-cli get worker_heartbeat:import_worker
```

### 6.3 SQL 直查（定位卡住 handler）

```sql
SELECT id, event_type, status, attempts, updated_at, EXTRACT(EPOCH FROM (now() - updated_at))/60 AS stuck_min
FROM import_event_outbox
WHERE status = 'processing' AND updated_at < now() - INTERVAL '30 minutes'
ORDER BY updated_at;
```

---

## 7. 维护原则

- **不在用户高峰期重启 backend**（worker 重启会导致心跳短暂 miss）
- **DLQ 不要长期累积**（depth > 50 应立即排查）
- **lag 持续 > 60s 应预警**（即使没到 300s critical）
- **Redis 重启后 60s 内 worker 心跳会自动恢复**，无需重启 backend

---

**关联文件**：
- `backend/app/workers/worker_helpers.py` — 心跳写入实现
- `backend/app/services/event_cascade_health_service.py` — 聚合服务
- `backend/app/routers/event_cascade_health.py` — HTTP 端点
- `audit-platform/frontend/src/components/DegradedBanner.vue` — 前端横幅

**关联 spec**：R10 Spec C / F1 + F2 + F4
