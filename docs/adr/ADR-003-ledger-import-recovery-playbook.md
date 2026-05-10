# ADR-003: Ledger Import Recovery Playbook

**状态**：Accepted (Sprint 10 / 2026-05-10)
**背景**：F28 — 账表导入各类故障场景的标准恢复步骤。

本剧本 8 个场景每条含**症状**、**诊断命令**、**恢复步骤**、**回滚预案**。
运维遇到对应症状后可 copy-paste 执行。

> **通用前置**：所有命令假设 cwd=`backend/`；PG 可用 `docker exec -it audit-postgres psql -U postgres -d audit_platform` 进入。

---

## 场景 1 — activate 中途 PG 重启 / connection reset

**症状**
- ImportJob.status 停在 `activating` 超过 5 分钟
- 日志出现 `connection to server was lost` / `SSL SYSCALL error`
- 前端进度条卡在 100% 不跳到 `completed`

**诊断命令**
```bash
# 查 job 状态
docker exec audit-postgres psql -U postgres -d audit_platform \
  -c "SELECT id, status, current_phase, started_at, last_heartbeat_at FROM import_jobs WHERE status='activating';"

# 查 dataset 是否仍 staged
docker exec audit-postgres psql -U postgres -d audit_platform \
  -c "SELECT id, status, created_at FROM ledger_datasets WHERE status='staged';"
```

**恢复步骤**
```bash
# 1. 触发 resume（10 min 自动重试或立即）
curl -X POST http://localhost:9980/api/projects/{pid}/ledger-import/jobs/{job_id}/resume \
  -H "Authorization: Bearer $TOKEN"

# 2. 观察 5 秒后 status 应切到 completed
```

**回滚**：若 resume 2 次仍失败，手动 `cleanup_dataset_rows` + `mark_failed`：
```python
from app.services.dataset_service import DatasetService
async with async_session() as db:
    await DatasetService.mark_failed(db, dataset_id)
    await db.commit()
```

---

## 场景 2 — staged dataset 孤儿（无 job 关联）

**症状**
- PG 有 `status='staged'` 的 dataset，created_at > 24h
- 对应 import_job 已是 `failed` / `canceled`

**诊断命令**
```sql
SELECT d.id, d.project_id, d.year, d.created_at
FROM ledger_datasets d
WHERE d.status = 'staged'
  AND d.created_at < NOW() - INTERVAL '24 hours'
  AND NOT EXISTS (
      SELECT 1 FROM import_jobs j
      WHERE j.dataset_id = d.id
        AND j.status IN ('running','queued','validating','writing','activating')
  );
```

**恢复步骤**：目前孤儿由 Sprint 6 `staged_orphan_cleaner` worker 自动清理（每小时）。立即触发：
```bash
python -c "
import asyncio
from app.core.database import async_session
from app.services.dataset_service import DatasetService
async def main():
    async with async_session() as db:
        await DatasetService.mark_failed(db, DATASET_ID)  # 单个孤儿
        await db.commit()
asyncio.run(main())
"
```

**回滚**：无（cleanup 后不可逆；误清理导致数据丢失请走 WAL archive 恢复）。

---

## 场景 3 — 索引膨胀（index size > 2× table size）

**症状**
- 查询变慢，`EXPLAIN ANALYZE` 显示 `Index Scan` 但 cost 异常高
- `\di+` 显示某个 `idx_tb_*_active_queries` index 体积远大于表

**诊断命令**
```sql
SELECT schemaname, tablename, indexname,
       pg_size_pretty(pg_relation_size(indexrelid)) AS index_size,
       pg_size_pretty(pg_relation_size(indrelid)) AS table_size
FROM pg_stat_user_indexes
WHERE indexname LIKE 'idx_tb_%_active_queries'
ORDER BY pg_relation_size(indexrelid) DESC;
```

**恢复步骤**
```sql
-- 逐个 REINDEX（CONCURRENTLY 不锁表）
REINDEX INDEX CONCURRENTLY idx_tb_balance_active_queries;
REINDEX INDEX CONCURRENTLY idx_tb_ledger_active_queries;
REINDEX INDEX CONCURRENTLY idx_tb_aux_balance_active_queries;
REINDEX INDEX CONCURRENTLY idx_tb_aux_ledger_active_queries;
```

**自动化**：Sprint 10 `dataset_purge_worker` 每晚 purge 完自动跑 REINDEX。

**回滚**：`REINDEX CONCURRENTLY` 失败会留下 `_ccnew` 无效索引，`DROP INDEX` 清理即可。

---

## 场景 4 — connection pool leak

**症状**
- `pg_stat_activity` 持续显示大量 `idle in transaction`
- 应用报 `QueuePool limit reached`
- 监控：pool_used / pool_max ≥ 0.95 且不下降

**诊断命令**
```sql
-- 查 idle in transaction 的 pid
SELECT pid, usename, state, state_change, query
FROM pg_stat_activity
WHERE state = 'idle in transaction'
ORDER BY state_change ASC
LIMIT 20;

-- 统计连接数
SELECT count(*) FROM pg_stat_activity WHERE datname='audit_platform';
```

**恢复步骤**
```sql
-- 杀掉 state_change 超过 10 分钟的 idle in tx 连接
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE state = 'idle in transaction'
  AND state_change < NOW() - INTERVAL '10 minutes';
```
随后重启 uvicorn 让 pool 重建：`restart start-dev.bat` / `docker restart audit-backend`。

**预防**：代码审查所有 `async with async_session() as db` 块必须 commit/rollback；`get_db` 依赖项在 FastAPI 退出时自动 close。

---

## 场景 5 — 可见性错误（B 看不到 A 激活的数据）

**症状**
- A 激活后 DB 有新 dataset + active 状态
- B 前端查报表仍看旧数据

**诊断**
```sql
-- 1. 确认有 active
SELECT id, status, activated_at FROM ledger_datasets
WHERE project_id='{pid}' AND year={yr} ORDER BY activated_at DESC;

-- 2. 确认 Tb* 新行 dataset_id 正确
SELECT COUNT(*) FROM tb_balance
WHERE project_id='{pid}' AND year={yr} AND dataset_id='{active_id}';

-- 3. 确认 outbox 已发布
SELECT id, status, published_at FROM event_outbox
WHERE event_type='LEDGER_DATASET_ACTIVATED' AND project_id='{pid}'
ORDER BY created_at DESC LIMIT 5;
```

**恢复步骤**
- **若 outbox `status=pending`**：`outbox_replay_worker` 每 30s 轮询，等 1 min 后重试；或手动触发：
  ```python
  from app.services.import_event_outbox_service import ImportEventOutboxService
  await ImportEventOutboxService.publish_one(db, outbox_id)
  ```
- **若 Tb* 行数 = 0**：staged 阶段写入失败，需 `resume_from_checkpoint` 重跑 parse_write_streaming。
- **若前端缓存**：F5 / Ctrl+Shift+R 强刷。

---

## 场景 6 — activate 前 integrity check 失败

**症状**：job.status = `integrity_check_failed`，日志 `DatasetIntegrityError: expected 1823 got 1820`

**诊断**：Tb* 物理行数 ≠ `dataset.record_summary` 记录的预期。
```sql
SELECT COUNT(*) FROM tb_balance WHERE dataset_id='{staging_id}';
SELECT record_summary FROM ledger_datasets WHERE id='{staging_id}';
```

**恢复**：删除 staged + 重跑整个 submit（不能跳过 parse_write_streaming）：
```python
await DatasetService.mark_failed(db, dataset_id)  # 会触发 cleanup_rows
# 用户重新 submit
```

**原因排查**：并发写入冲突 / 磁盘错误 / INSERT 部分失败；查 pipeline 日志 `_insert_*` 的 rowcount vs chunk size。

---

## 场景 7 — outbox event DLQ 堆积（F45）

**症状**：`event_outbox_dlq_depth` gauge > 0

**诊断**
```sql
SELECT event_type, COUNT(*), MAX(created_at)
FROM event_outbox_dlq
GROUP BY event_type
ORDER BY 2 DESC;
```

**恢复**：核查 DLQ 表后手动重投：
```python
from app.services.import_event_outbox_service import ImportEventOutboxService
# 把 DLQ 里的事件复制回 event_outbox 并清空 retry_count
```
> Sprint 7 F45 实装后提供 `POST /admin/event-dlq/replay` 端点。

---

## 场景 8 — worker 长时间未处理 queued job

**症状**：`ImportJob.status='queued'` 超过 5 min
- 用户前端 "导入中 0%" 一直不动

**诊断**
```sql
-- Queued 最早时间
SELECT MIN(created_at), COUNT(*) FROM import_jobs WHERE status='queued';

-- Worker 存活（进程内 worker：查 uvicorn 日志 "[IMPORT_WORKER] started"）
grep "IMPORT_WORKER" backend_dev.log | tail -5
```

**恢复步骤**
1. 若 uvicorn 正常但 worker 未启动：重启后端。
2. 若 worker 存活但 queue 卡住：手动触发一轮
   ```python
   from app.services.import_job_runner import ImportJobRunner
   await ImportJobRunner.run_worker_once()
   ```
3. 若多次 claim 失败：检查 `feature_flags.get("ledger_import_v2_enabled")`（true/false 决定走新旧引擎）。

**回滚**：无——不是数据变更操作。
