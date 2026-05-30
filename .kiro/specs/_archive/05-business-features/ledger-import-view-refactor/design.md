# Design — Ledger Import View Refactor

## 架构决策

### D1 改造方式：filter abstraction（不建 view）

**不建 SQL VIEW 的原因**：
- PG VIEW 对复杂查询优化（subquery flattening）一般 OK，但写路径（pipeline/
  writer）必须绕过 view 直接写物理表，需要维护两套访问路径
- 把所有 ORM 查询改指向 view 需要新建 4 个 View-mapped ORM 模型（大改动）
- 改造 raw SQL 更复杂（要手动改每处 `FROM tb_*` 为 `FROM v_tb_*`）

**选择用 `dataset_query.get_active_filter` 作为查询抽象**：
- 已有（不需要新建）
- 调用点显式（代码审查容易）
- SQL 优化器能把 `WHERE dataset_id IN (SELECT id FROM ... WHERE status='active')`
  子查询 flatten 为 hash join（实测）
- 可以按需在 caller 缓存 active_dataset_id 避免重复查询

### D2 写入路径改为 `is_deleted=False`

**不改 model default value 的原因**：
- model 层默认仍保留 `is_deleted=True`（兼容测试 fixture 代码）
- 只改 `pipeline._insert` 的调用参数：`bulk_write_staged(..., is_deleted=False)`
- 其他写入路径（workpaper_service/adjustment_service 等）不受影响

### D3 activate 改造

**方案**：删除 `_set_dataset_visibility` 的 2 个调用点（activate 内部），
保留方法签名作 no-op。

```python
# 改前（127s）
async def activate(...):
    ...
    UPDATE ledger_datasets SET status='superseded' WHERE status='active' ...  # 1 row
    await _set_dataset_visibility(previous, is_deleted=True)   # UPDATE 200 万行
    UPDATE ledger_datasets (dataset.status='active')           # 1 row
    await _set_dataset_visibility(new, is_deleted=False)       # UPDATE 200 万行
    INSERT activation_records
    INSERT outbox event

# 改后（<1s）
async def activate(...):
    ...
    UPDATE ledger_datasets SET status='superseded' WHERE status='active' ...  # 1 row
    # ❌ 删除 _set_dataset_visibility(previous)
    UPDATE ledger_datasets (dataset.status='active')           # 1 row
    # ❌ 删除 _set_dataset_visibility(new)
    INSERT activation_records
    INSERT outbox event
```

### D4 rollback 同样改造

改前：
```python
current.status = rolled_back
_set_dataset_visibility(current, True)       # UPDATE
previous.status = active
_set_dataset_visibility(previous, False)     # UPDATE
```
改后：只改 metadata，不 UPDATE 物理行。

### D5 `_set_dataset_visibility` 改为 no-op + 废弃标记

```python
async def _set_dataset_visibility(db, *, project_id, year, dataset_id, is_deleted):
    """[DEPRECATED B'] 不再对 4 张 Tb* 表做 UPDATE。

    保留方法签名是为了兼容可能的外部调用；实际架构下，数据可见性
    完全由 ledger_datasets.status 控制，物理行 is_deleted 恒为 false。
    """
    logger.warning(
        "_set_dataset_visibility called but is no-op under B' architecture "
        "(dataset=%s, is_deleted=%s)",
        dataset_id, is_deleted,
    )
    # no-op
```

## 业务查询改造清单（按文件）

### 一、ORM 查询改造（15 个 service + 2 个 router，共 ~40 处）

所有 `WHERE TbX.is_deleted == False` 替换为 `WHERE await get_active_filter(db, TbX.__table__, pid, year)`。

**改造模板 A**（where 条件列表形式）：
```python
# 改前
.where(
    TbLedger.project_id == project_id,
    TbLedger.year == year,
    TbLedger.is_deleted == False,
    TbLedger.account_code == account_code,
)

# 改后
from app.services.dataset_query import get_active_filter
.where(
    await get_active_filter(db, TbLedger.__table__, project_id, year),
    TbLedger.account_code == account_code,
)
```

**改造模板 B**（conditions list 形式）：
```python
# 改前
conditions = [TbLedger.project_id == project_id, TbLedger.is_deleted == sa.false()]
if year:
    conditions.append(TbLedger.year == year)

# 改后：year 可选时需要预处理
if year:
    conditions = [await get_active_filter(db, TbLedger.__table__, project_id, year)]
else:
    # year=None 场景：查所有年度的 active data
    # 用 dataset_id IN (active datasets of project) 子查询
    from app.models.dataset_models import LedgerDataset, DatasetStatus
    active_ds_subq = (
        sa.select(LedgerDataset.id)
        .where(
            LedgerDataset.project_id == project_id,
            LedgerDataset.status == DatasetStatus.active,
        )
    )
    conditions = [
        TbLedger.project_id == project_id,
        TbLedger.dataset_id.in_(active_ds_subq),
    ]
```

**files 清单**（每个文件改造点数）：
- `workpaper_fill_service.py`（3 处）
- `wp_ai_service.py`（1 处）
- `wp_chat_service.py`（1 处）
- `sampling_enhanced_service.py`（3 处）
- `report_trace_service.py`（1 处）
- `ocr_service_v2.py`（1 处）
- `note_data_extractor.py`（6 处）
- `mapping_service.py`（2 处，其中 1 处已部分迁移）
- `import_service.py`（2 处）
- `import_intelligence.py`（~10 处统计查询）
- `formula_engine.py`（1 处）
- `data_fetch_custom.py`（1 处）
- `aging_analysis_service.py`（2 处）
- `routers/report_trace.py`（2 处）
- `data_validation_engine.py`（1 处）

### 二、raw SQL 改造（6 处）

**改造模板**：
```sql
-- 改前
SELECT ... FROM tb_ledger
WHERE project_id = :pid AND year = :yr AND is_deleted = false

-- 改后
SELECT ... FROM tb_ledger l
WHERE l.project_id = :pid AND l.year = :yr
  AND EXISTS (
    SELECT 1 FROM ledger_datasets d
    WHERE d.id = l.dataset_id AND d.status = 'active'
  )
```

**files 清单**：
- `metabase_service.py`：4 个 SQL 模板（ledger 汇总 / 科目明细 / 凭证查询 / aux 余额）
- `data_lifecycle_service.py`：4 UNION ALL 统计（balance/aux_balance/ledger/aux_ledger 行数）
- `smart_import_engine.py:rebuild_aux_balance_summary`：已有 dataset_id 参数，但 SQL 里还
  有 `is_deleted = false` 要去掉
- `import_intelligence.py`：多处凭证平衡检查 / 月份分布统计
- `consistency_replay_engine.py`：tb_balance vs trial_balance 汇总对比
- `data_validation_engine.py`：closing_balance > 1000000000 异常扫描
- `ledger_data_service.py:list_distinct_periods`：序时账已有期间查询

### 三、特殊情况

**不改**：
- `recycle_bin.py` — 回收站语义使用 is_deleted=true 标记软删，保留
- `cleanup_dataset_rows` — 按 dataset_id 物理 DELETE，无 is_deleted 语义
- `apply_incremental` overwrite 模式 — 按 dataset_id + period 物理 DELETE

**需要查验**：
- `validator.py` 里的 raw SQL（计算 sum_debit/sum_credit） — 按 dataset_id
  过滤，不需要 is_deleted

## 性能优化

### O1 单请求缓存 active_dataset_id

`get_active_filter` 内部每次都查 `ledger_datasets` 找 active id。如果一个请求
多次调用（如统计接口查 ledger + balance + aux），会触发 N+1 查询。

**方案**：新增 `get_filter_with_dataset_id(table, pid, year, dataset_id)` 同步
版本，caller 先查一次 dataset_id 再复用。

已在 requirements.md F1 提到。重点改造密集查询的接口：
- `import_intelligence.py` 的 `/stats` 端点（~10 次查询）
- `workpaper_fill_service.py` 的底稿填充（多次查 ledger / aux_balance）

### O2 partial index 充分利用

已建的索引：
```sql
idx_tb_*_active_queries (project_id, year, dataset_id) WHERE is_deleted = false
```

B' 架构下 is_deleted 恒 false，这个索引仍然覆盖所有 active 数据；
`get_active_filter` 查询 `WHERE project_id=X AND year=Y AND dataset_id=Z` 直接命中。

### O3 EXPLAIN ANALYZE 验证

关键查询（YG2101 级别 130 万行 aux_ledger）改造前后跑 EXPLAIN ANALYZE 对比，
确保：
- 走 idx_*_active_queries 而非 seq scan
- execution time < 旧版本 1.2×（允许轻微回归）

## 迁移步骤

### Sprint 1 — 工具 + activate + 写入（核心改造，风险可控）

**Task 1.1** 强化 `dataset_query.py`（+ 新增同步版本接口）
**Task 1.2** 改 `DatasetService.activate` → 去掉 `_set_dataset_visibility` 调用
**Task 1.3** 改 `DatasetService.rollback` → 去掉 `_set_dataset_visibility` 调用
**Task 1.4** 改 `DatasetService._set_dataset_visibility` → no-op + 废弃警告
**Task 1.5** 改 `pipeline._insert` → `is_deleted=False`
**Task 1.6** YG4001-30 smoke 验证（此时业务查询未迁移，但 staged 不会泄露
（因为 dataset.status 还是 staged））

**检查点**：YG4001-30 smoke 通过后才进 Sprint 2。

### Sprint 2 — ORM 查询迁移（40+ 处）

按文件分组改造（每个文件独立可测）：
- Task 2.1 `workpaper_fill_service.py` / `wp_ai_service.py` / `wp_chat_service.py`
- Task 2.2 `sampling_enhanced_service.py` / `report_trace_service.py` / `ocr_service_v2.py`
- Task 2.3 `note_data_extractor.py` / `mapping_service.py` / `import_service.py`
- Task 2.4 `import_intelligence.py`（量大 / 单独一任务）
- Task 2.5 `formula_engine.py` / `data_fetch_custom.py` / `aging_analysis_service.py`
- Task 2.6 `routers/report_trace.py` / `data_validation_engine.py`

**每个任务完成后**：
1. 跑对应模块的 pytest
2. grep 确认该文件无剩余 `TbX.is_deleted == False`
3. `git diff` 人工审查

### Sprint 3 — raw SQL 改造 + E2E 验证

**Task 3.1** `metabase_service.py` 4 SQL 改 EXISTS 子查询
**Task 3.2** `data_lifecycle_service.py` UNION ALL 统计
**Task 3.3** `smart_import_engine.py:rebuild_aux_balance_summary` 去 is_deleted
**Task 3.4** `import_intelligence.py` raw SQL
**Task 3.5** `consistency_replay_engine.py` + `data_validation_engine.py` +
  `ledger_data_service.py:list_distinct_periods`
**Task 3.6** `validator.py` raw SQL 审查（可能不需改）
**Task 3.7** CI grep 卡点加入 `TbX.is_deleted == False` 防回归
**Task 3.8** YG2101 E2E 实测 + perf 日志对比
**Task 3.9** rollback 集成测试
**Task 3.10** 文档 + memory 归档

## 风险 + 缓解

### 风险 1：漏改查询 → 前端看到旧数据

**缓解**：
- grep 改造前后都 `TbX.is_deleted == False` 命中数（期望 40 → 0）
- CI 加 grep 卡点（下次有人加新查询会失败）
- 兜底：`get_active_filter` 在 dataset 不可达时 fallback 到 `is_deleted=false`
  （老数据仍可见）

### 风险 2：activate 失败时数据不一致

当前：activate 失败 → 4 张 Tb* 表部分 UPDATE 部分未 UPDATE，可能数据混乱
B' 后：activate 只改 2 行 metadata，失败就回滚这 2 行，物理数据不动

**缓解**：B' 其实更安全。写测试覆盖 activate 异常场景。

### 风险 3：rollback 语义变化

改造前：rollback 时 UPDATE 让旧版本的 is_deleted=true、新版本 is_deleted=false
改造后：rollback 只改 status，物理数据不动

**问题**：rollback 后原 current（状态 rolled_back）的数据在业务查询中
自然不可见（因为 status != active），但物理行仍在表里。需要确认没有
任何查询会把 rolled_back 的数据当作 active 显示。

**缓解**：所有业务查询走 get_active_filter（靠 `status='active'`）即可。
grep 审查 + 集成测试验证。

### 风险 4：并发导入场景

项目 A 的 staged dataset 和项目 B 的 active dataset 同时写 Tb* 表。
- 改造前：靠 `is_deleted` 隔离
- 改造后：靠 `dataset_id` 隔离，两个 dataset 不同所以数据不会串

**缓解**：测试场景新增并发导入集成测试。

### 风险 5：历史数据（未迁移前的 dataset_id=NULL 行）

PG 里可能存在 dataset_id = NULL 的老数据（迁移前的行）。
- 改造前：靠 is_deleted=false 能看到
- 改造后：靠 dataset_id 过滤，dataset_id=NULL 的数据永远看不到

**缓解**：
1. 先用 migration 脚本把 NULL dataset_id 回填为"历史 dataset"
2. 或者 `get_active_filter` 兜底分支用 is_deleted=false 继续兼容
（当前 design 采用第 2 种）

## 成功指标

- YG2101 activate: 127s → <1s
- YG2101 total: 400s → 270s
- grep `TbX.is_deleted\s*==` 命中数: 40+ → 0
- pytest 全绿
- 3 个 E2E 脚本全通过

---

## 第二轮架构决策（D6-D22，对齐 requirements §2.D - §2.K + §3.6/3.7）

> 原 D1-D5 只覆盖 F1/F2/F12 核心改造；本轮追加决策覆盖 F13-F53 共 35 条新需求。

### D6 大文档健壮性（F13-F17）

#### D6.1 ProgressCallback 频率保证（F13）

**数据结构**：
```python
@dataclass
class ProgressState:
    total_rows_est: int           # detect 阶段估算
    rows_processed: int = 0       # 已处理行数
    last_pct_reported: int = -1   # 上次广播的百分比
    last_rows_reported: int = 0   # 上次广播时的行数
    last_report_at: datetime      # 上次广播时间戳

async def _maybe_report_progress(state, cb):
    pct = int(state.rows_processed * 100 / state.total_rows_est)
    rows_delta = state.rows_processed - state.last_rows_reported
    pct_delta = pct - state.last_pct_reported
    # 任一条件触发：5% 或 10k 行（取先达到）
    if pct_delta >= 5 or rows_delta >= 10_000:
        await cb(pct, build_progress_msg(state))
        state.last_pct_reported = pct
        state.last_rows_reported = state.rows_processed
        state.last_report_at = datetime.now(UTC)
```

**前端卡住判定放宽**：
- `ThreeColumnLayout.vue` 的 `pollImportQueue` heartbeat 检测阈值 10s → 30s
- 超 60s 无更新才标红"已卡住"

#### D6.2 checkpoint + resume（F14）

**`ImportJob.current_phase` 枚举扩展**：
```
queued → detecting → validating → writing → parse_write_streaming_done
→ activation_gate → activation_gate_done → activating → activate_dataset_done → completed
```

`ImportJobRunner.resume_from_checkpoint(job_id)` 路由表：
| current_phase | 恢复动作 |
|--------------|---------|
| `parse_write_streaming_done` | 从 activation_gate 开始重跑 |
| `activation_gate_done` | 从 activate_dataset 开始重跑（1s 内完成） |
| `writing` 中途 | cleanup staged → 从头重跑 |
| `activating` | resume activate_dataset（metadata 切换幂等） |

**活性**：resume 前先检查 `dataset_id` 是否仍为 staged；若已被清理则降级为"重新上传"。

#### D6.3 cancel 清理保证（F15）

**cancel_check 回调改造**：
```python
# pipeline.py
async def _handle_cancel(dataset_id, artifacts):
    """cancel 时的完整清理链。"""
    try:
        await DatasetService.cleanup_dataset_rows(dataset_id)
    except Exception as e:
        logger.error("cleanup_dataset_rows failed: %s", e)
    for art in artifacts:
        try:
            await ImportArtifactService.mark_consumed(art.id)
            if art.storage_uri.startswith("local://"):
                Path(art.storage_uri.removeprefix("local://")).unlink(missing_ok=True)
        except Exception as e:
            logger.error("artifact cleanup failed: %s", e)
```

`recover_jobs` 兜底：扫 `status=canceled AND dataset_id IS NOT NULL` 的 job，补清。

#### D6.4 Prometheus 埋点（F16）

**新文件** `backend/app/services/ledger_import/metrics.py`：
```python
from prometheus_client import Counter, Histogram, Gauge

IMPORT_DURATION = Histogram(
    "ledger_import_duration_seconds",
    "Import phase duration",
    ["phase"],
    buckets=[1, 5, 15, 30, 60, 180, 300, 600, 1800, 3600],
)
IMPORT_JOBS_TOTAL = Counter(
    "ledger_import_jobs_total",
    "Import job state transitions",
    ["status"],
)
DATASET_COUNT = Gauge(
    "ledger_dataset_count",
    "Current dataset count by project and status",
    ["project_id", "status"],
)
EVENT_DLQ_DEPTH = Gauge(
    "event_outbox_dlq_depth",
    "DLQ depth for failed event broadcasts",
)
HEALTH_STATUS = Gauge(
    "ledger_import_health_status",
    "0=healthy 1=degraded 2=unhealthy",
)
```

`/metrics` 端点挂在 `backend/app/main.py`（复用现有 app，无需独立 port）。

#### D6.5 耗时预估（F17）

**新文件** `backend/app/services/ledger_import/duration_estimator.py`：
```python
def estimate_duration_seconds(total_rows: int) -> int:
    """基于 9 家样本实测的 P50 吞吐。"""
    if total_rows < 10_000:
        return 15
    if total_rows < 100_000:
        return int(30 + total_rows / 3_000)    # ~3k rows/s
    if total_rows < 500_000:
        return int(90 + total_rows / 5_000)    # ~5k rows/s
    return int(180 + total_rows / 4_500)       # ~4.5k rows/s, 含 activate
```

### D7 运维与灰度（F18-F19）

#### D7.1 Day 7 迁移 SQL（F18）

**文件** `backend/alembic/versions/view_refactor_cleanup_old_deleted_20260517.py`：
```python
def upgrade():
    # 批量 UPDATE 分块避免锁表
    op.execute("""
        DO $$
        DECLARE batch_size INT := 100_000;
        DECLARE affected INT;
        BEGIN
          LOOP
            UPDATE tb_balance SET is_deleted = false
            WHERE ctid IN (
              SELECT ctid FROM tb_balance
              WHERE is_deleted = true
                AND dataset_id IN (SELECT id FROM ledger_datasets WHERE status='active')
              LIMIT batch_size
            );
            GET DIAGNOSTICS affected = ROW_COUNT;
            EXIT WHEN affected = 0;
            PERFORM pg_sleep(1);  -- 让出 I/O
          END LOOP;
        END $$;
    """)
    # 其他 3 张表同理
```

**原则**：分块 + 小睡，避免单次 UPDATE 锁表 10 分钟。

#### D7.2 feature flag 结构（F19）

**`feature_flags.py` 新增**：
```python
_DEFAULT_FLAGS = {
    ...,
    "ledger_import_view_refactor_enabled": False,  # 默认关保守
}
```

**接入点**：
- `DatasetService.activate` 第一行 `if await is_flag_enabled(project_id, "ledger_import_view_refactor_enabled"):`
- `get_active_filter` 签名新增 `enable_view_refactor: bool` 参数

### D8 云协同（F20-F25）

#### D8.1 WebSocket 广播架构（F20）

**事件流**：
```
DatasetService.activate (txn commit)
 └→ INSERT event_outbox (event_type=DATASET_ACTIVATED)
      └→ outbox_replay_worker (轮询 pending events)
           └→ WebSocketBroadcastService.push_to_project(project_id, event)
                └→ 向 /ws/project/{pid}/events 所有在线 client 推送
                     └→ 前端 useProjectEvents 触发 store 刷新
```

**payload schema**：
```json
{
  "event_type": "DATASET_ACTIVATED",
  "project_id": "uuid",
  "year": 2025,
  "dataset_id": "uuid",
  "activated_by": "uuid",
  "activated_at": "2026-05-10T14:20:00Z",
  "row_counts": {"tb_balance": 1823, "tb_ledger": 22716, ...}
}
```

#### D8.2 锁透明（F21）

**`ImportQueueService.get_lock_info()` 返回结构**：
```python
class LockInfo(BaseModel):
    holder_user_id: UUID
    holder_name: str                 # JOIN users 查
    job_id: UUID
    current_phase: str               # 映射 ImportJob.current_phase → 中文
    progress_pct: int
    rows_processed: int
    total_rows_est: int
    estimated_remaining_seconds: int # 基于 _last_report_at 和平均吞吐计算
    acquired_at: datetime
```

前端 `ImportButton.vue` 改造：
```html
<el-tooltip placement="top">
  <template #content>
    <div v-if="lockInfo">
      <b>{{ lockInfo.holder_name }} 正在导入</b><br>
      阶段：{{ lockInfo.current_phase_cn }} ({{ lockInfo.progress_pct }}%)<br>
      预计剩余：{{ formatDuration(lockInfo.estimated_remaining_seconds) }}
    </div>
  </template>
  <el-button disabled>导入账套</el-button>
</el-tooltip>
```

#### D8.3 接管机制（F22）

**`ImportJob.created_by` 字段迁移**：
- 保留 `created_by UUID` 作为原始创建者
- 新增 `creator_chain JSONB DEFAULT '[]'` 记录接管链路：
  ```json
  [
    {"user_id": "A", "action": "create", "at": "..."},
    {"user_id": "B", "action": "takeover", "at": "...", "reason": "A 网络掉线"}
  ]
  ```

**接管 API**：`POST /api/projects/{pid}/ledger-import/jobs/{jid}/takeover`
- 权限：PM / admin / partner
- 前置检查：`last_heartbeat > NOW() - 5 min`
- 动作：更新 `creator_chain` + 触发 `resume_from_checkpoint`

#### D8.4 rollback 走锁（F23）

`DatasetService.rollback` 加装饰器：
```python
async def rollback(db, project_id, year, ...):
    async with ImportQueueService.acquire_lock(project_id, action="rollback"):
        ...  # 原 rollback 逻辑
```

和 `activate` 共享同一把锁（同 project 同时只能一个操作）。

#### D8.5 只读旁观（F24）

`GET /jobs/{job_id}` 权限检查改为：
```python
def check_job_read_access(job, current_user, db):
    if current_user.role in ("admin", "partner"):
        return  # 全通
    # 项目组任一成员可读
    assignment = db.query(ProjectAssignment).filter_by(
        project_id=job.project_id, user_id=current_user.id
    ).first()
    if not assignment:
        raise HTTPException(403)
```

写操作（cancel/retry/takeover）单独检查 `require_role("pm","admin","partner")`。

### D9 数据正确性（F26-F29）

#### D9.1 孤儿扫描任务（F26）

**新 worker 模块** `backend/app/workers/staged_orphan_cleaner.py`：
```python
async def run(stop_event):
    while not stop_event.is_set():
        await _scan_and_clean()
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=3600)  # 1h
        except asyncio.TimeoutError:
            pass

async def _scan_and_clean():
    orphans = await db.execute("""
        SELECT d.id FROM ledger_datasets d
        WHERE d.status = 'staged'
          AND d.created_at < NOW() - INTERVAL '24 hours'
          AND NOT EXISTS (
            SELECT 1 FROM import_jobs j
            WHERE j.dataset_id = d.id
              AND j.status IN ('running','queued','validating','writing','activating')
          )
    """).fetchall()
    for o in orphans:
        await DatasetService.cleanup_dataset_rows(o.id)
        await DatasetService.mark_superseded(o.id, reason="orphan_cleanup")
```

注册到 `main.py` 的 lifespan `_start_workers` 中。

#### D9.2 integrity check（F27）

`DatasetService.activate` 事务内新增：
```python
for table_name in ("tb_balance", "tb_ledger", "tb_aux_balance", "tb_aux_ledger"):
    actual = await db.scalar(
        select(func.count()).select_from(text(table_name))
        .where(text("dataset_id = :did")),
        {"did": dataset_id},
    )
    expected = dataset.record_summary.get(table_name, 0)
    if actual != expected:
        raise DatasetIntegrityError(
            f"{table_name}: expected {expected} got {actual}"
        )
```

**失败处理**：抛 `DatasetIntegrityError` → 事务回滚 → `ImportJob.status='integrity_check_failed'` + 告警 event。

### D10 UX 补强（F31-F32）

#### D10.1 错误码 hint 映射（F32）

**新文件** `backend/app/services/ledger_import/error_hints.py`：
- Pydantic model `ErrorHint {title, description, suggestions: list[str], severity}`
- 模块级字典 `ERROR_HINTS: dict[str, ErrorHint]` 31 条
- `/diagnostics` 端点响应 `findings` 数组每条 enriched：`{...原 finding, hint: ERROR_HINTS.get(code)}`

**CI 一致性检查**：`test_all_error_codes_have_hints.py` 遍历 `errors.py` 的 `ErrorCode` 枚举断言 hint 全覆盖。

### D11 安全与健壮性（F40-F46）

#### D11.1 上传文件安全（F40）

**架构**：上传端点加装饰器 `@validate_upload_safety`：
```python
async def validate_upload_safety(file: UploadFile):
    # 1. 大小上限（前 content-length header 验，避免读完）
    if file.size > MAX_SIZE_BY_TYPE[file.content_type]:
        raise HTTPException(413, "文件超出大小上限")

    # 2. 读前 8KB 做 magic number 检查
    head = await file.read(8192)
    await file.seek(0)
    mime = magic.from_buffer(head, mime=True)
    if mime not in ALLOWED_MIMES:
        raise HTTPException(415, f"不支持的文件类型: {mime}")

    # 3. xlsx 额外检查宏 + zip bomb
    if mime.endswith("spreadsheetml.sheet"):
        with ZipFile(BytesIO(head)) as z:
            if any(n == "xl/vbaProject.bin" for n in z.namelist()):
                raise HTTPException(415, "禁止含宏的 Excel 文件")
            total_uncompressed = sum(zi.file_size for zi in z.infolist())
            if total_uncompressed > file.size * 100:
                raise HTTPException(413, "可疑的高压缩比文件（zip bomb）")

    # 4. 审计日志
    await audit_log.log("upload_accepted", {"filename": file.filename, "mime": mime, ...})
```

#### D11.2 tenant_id 预留（F41）

**Alembic 迁移** `view_refactor_tenant_id_20260518.py`：
```python
def upgrade():
    for table in ("tb_balance", "tb_ledger", "tb_aux_balance", "tb_aux_ledger", "ledger_datasets"):
        op.add_column(table, sa.Column(
            "tenant_id", sa.String(64), nullable=False, server_default="default"
        ))
        op.create_index(f"idx_{table}_tenant_project_year",
                        table, ["tenant_id", "project_id", "year"])
```

`get_active_filter` 签名扩展（强制 current_user）：
```python
async def get_active_filter(
    db, table, project_id, year, current_user: User
) -> ColumnElement:
    # 校验权限
    await verify_project_access(db, current_user.id, project_id)
    # 返回 filter（当前 tenant_id 恒 'default'）
    return and_(
        table.c.tenant_id == current_user.tenant_id,
        table.c.project_id == project_id,
        table.c.year == year,
        ...
    )
```

**破坏性变更**：40+ 调用点要同步加 `current_user` 参数 → **纳入 Sprint 1 查询迁移任务一并处理**，不单独 Sprint。

#### D11.3 事件广播 outbox 可靠性（F45）

**现有 `event_outbox_replay_worker` 已有重试逻辑**（3 次后失败）；本轮扩展：
- 失败 3 次后移入 `event_outbox_dlq` 表（新建）
- DLQ 非空时 `/metrics` 的 `event_outbox_dlq_depth` 报警
- 运维页面 `/admin/event-dlq` 展示 DLQ 内容 + 手动重投按钮

#### D11.4 rollback 下游联动（F46）

`DatasetService.rollback` 事务内新增：
```python
await db.execute(insert(EventOutbox).values(
    event_type="DATASET_ROLLED_BACK",
    payload={"project_id": pid, "year": yr,
             "old_dataset_id": str(current.id),
             "new_active_dataset_id": str(previous.id)},
    status="pending",
))
```

`event_handlers.py` 新增订阅：
```python
@on_event("DATASET_ROLLED_BACK")
async def _mark_downstream_stale(db, payload):
    pid, yr = payload["project_id"], payload["year"]
    # 找所有引用该 project+year 的 Workpaper / AuditReport / DisclosureNote
    # 但 bound_dataset_id 不变（F50 保护），只标 is_stale=True 提示刷新
    await db.execute(update(WorkingPaper).where(
        WorkingPaper.project_id == pid,
        extract("year", WorkingPaper.created_at) == yr,
        WorkingPaper.source_type == "ledger",
    ).values(is_stale=True))
    ...  # AuditReport / DisclosureNote 同理
```

### D12 数据校验透明化（F47-F49）

#### D12.1 ValidationFinding.explanation 扩展（F47）

**Pydantic 继承结构**：
```python
class ExplanationBase(BaseModel):
    formula: str
    formula_cn: str
    inputs: dict
    computed: dict
    hint: str

class BalanceMismatchExplanation(ExplanationBase):
    diff_breakdown: list[DiffBreakdownItem]

class UnbalancedExplanation(ExplanationBase):
    sample_voucher_ids: list[str]

class YearOutOfRangeExplanation(ExplanationBase):
    year_bounds: tuple[str, str]  # (2025-01-01, 2025-12-31)
    out_of_range_samples: list[dict]

class ValidationFinding(BaseModel):
    ...
    explanation: ExplanationBase | None = None
```

**validator.py 改造重点**：`validate_l3_cross_table` 的 `BALANCE_LEDGER_MISMATCH` 生成位置把 `opening/sum_debit/sum_credit/diff/tolerance` 都包进 explanation（当前只写 message 字符串丢弃了中间值）。

#### D12.2 VALIDATION_RULES_CATALOG（F48）

**新文件** `backend/app/services/ledger_import/validation_rules_catalog.py`：
```python
VALIDATION_RULES_CATALOG: list[ValidationRuleDoc] = [
    ValidationRuleDoc(
        code="L3_BALANCE_LEDGER_MISMATCH",
        level="L3",
        severity="blocking",
        title_cn="余额表 vs 序时账累计一致性校对",
        formula="closing_balance = opening_balance + sum(debit) - sum(credit)",
        formula_cn="期末余额 = 期初余额 + 借方累计 - 贷方累计",
        tolerance_formula="min(1 + max_magnitude × 0.00001, 100)",
        tolerance_cn="基础 1 元 + 最大金额 × 0.001%，上限 100 元",
        scope_cn="按 account_code 逐科目检查",
        why_cn="确保余额表和序时账一致，发现漏记凭证/金额错误",
        example={
            "inputs": {"opening": 100_000, "debit": 50_000, "credit": 30_000},
            "expected": 120_000,
            "pass": "actual ∈ [119999, 120001]",
            "fail": "actual = 130_000 → diff=10_000 > tolerance=1",
        },
        can_force=True,
    ),
    ...  # 共 31 条
]
```

**单一真源约束**：每个 finding 的 `code` 必须在 catalog 中，CI 双向一致性检查。

#### D12.3 drill_down 字段（F49）

`ValidationFinding.location` 扩展：
```python
class DrillDown(BaseModel):
    target: Literal["tb_ledger", "tb_balance", "tb_aux_ledger", "tb_aux_balance"]
    filter: dict                 # 过滤条件 {account_code: "1002", year: 2025}
    expected_count: int | None   # 预期行数
    sample_ids: list[str]        # 前 3 条行 ID

class FindingLocation(BaseModel):
    file: str | None
    sheet: str | None
    row: int | None
    column: str | None
    drill_down: DrillDown | None = None
```

前端 `DiagnosticPanel.vue` 加按钮"查看明细 (458 行)" → 打开 `LedgerPenetration.vue` 侧边抽屉。

### D13 业务闭环与合规（F50-F53）

#### D13.1 下游对象快照绑定（F50）—— 最关键合规改造

**Alembic 迁移** `view_refactor_dataset_binding_20260519.py`：
```python
for table in ("working_papers", "audit_reports", "disclosure_notes", "unadjusted_misstatements"):
    op.add_column(table, sa.Column("bound_dataset_id", UUID, nullable=True))
    op.add_column(table, sa.Column("dataset_bound_at", TIMESTAMP(timezone=True), nullable=True))
    op.create_foreign_key(f"fk_{table}_bound_dataset",
                          table, "ledger_datasets",
                          ["bound_dataset_id"], ["id"],
                          ondelete="RESTRICT")  # ← 绑定即保护
```

**绑定时机**：
```python
# workpaper_service.py 生成底稿时
async def generate_workpaper(project_id, year, ...):
    active_ds = await get_active_dataset_id(project_id, year)
    wp = WorkingPaper(
        project_id=project_id,
        year=year,
        bound_dataset_id=active_ds,
        dataset_bound_at=datetime.now(UTC),
        ...
    )

# audit_report_service.py 状态转 final 时
async def transition_to_final(report_id, user):
    report = await get(report_id)
    if report.status != "eqcr_approved":
        raise ...
    active_ds = await get_active_dataset_id(report.project_id, report.year)
    report.status = "final"
    report.bound_dataset_id = active_ds  # 锁定
    report.dataset_bound_at = datetime.now(UTC)
```

**查询扩展**：
```python
async def get_active_filter(
    db, table, project_id, year, current_user,
    force_dataset_id: UUID | None = None,  # ← 新参数
):
    if force_dataset_id:
        # 下游对象已绑定，强制查该 dataset（忽略 status）
        return and_(
            table.c.dataset_id == force_dataset_id,
            ...
        )
    # 原逻辑：按 status='active' 查
    ...
```

**rollback 保护**：
```python
async def rollback(db, project_id, year, ...):
    current_active = await get_active_dataset_id(project_id, year)
    # 查所有 final / eqcr_approved 状态的下游
    bound_reports = await db.execute(select(AuditReport).where(
        AuditReport.bound_dataset_id == current_active,
        AuditReport.status.in_(("final", "eqcr_approved")),
    )).scalars().all()
    if bound_reports:
        raise HTTPException(409, {
            "error": "signed_reports_bound",
            "message": f"无法回滚：{len(bound_reports)} 份已签字报表引用此数据集",
            "reports": [{"id": r.id, "name": r.name} for r in bound_reports],
        })
    ...  # 原 rollback 逻辑
```

#### D13.2 全局并发限流（F51）

**新文件** `backend/app/services/ledger_import/global_concurrency.py`：
```python
import redis.asyncio as redis

class GlobalImportConcurrency:
    KEY = "ledger_import:active_count"
    MAX = int(os.getenv("LEDGER_IMPORT_MAX_CONCURRENT", "3"))

    async def try_acquire(self, job_id: UUID) -> bool:
        """返回 True 立即可跑，False 入队列。"""
        r = await get_redis()
        count = await r.incr(self.KEY)
        if count > self.MAX:
            await r.decr(self.KEY)
            return False
        await r.expire(self.KEY, 7200)  # 兜底 TTL
        return True

    async def release(self):
        await (await get_redis()).decr(self.KEY)

    async def queue_position(self, job_id: UUID) -> int:
        """返回排队位置（前面还有几个）。"""
        queued = await db.execute(select(func.count()).select_from(ImportJob).where(
            ImportJob.status == "queued",
            ImportJob.created_at < self_job.created_at,
        ))
        return queued.scalar()
```

**内存降级**：pipeline 启动时读 `psutil.virtual_memory().percent`，>80% 时：
- `ENABLE_CALAMINE = False`（回退 openpyxl）
- `CHUNK_SIZE = 10_000`（降半）
- 日志打警告 `memory_pressure_downgrade`

#### D13.3 列映射历史复用（F52）

**`ImportColumnMappingHistory` 扩展字段**：
```python
class ImportColumnMappingHistory(Base):
    __tablename__ = "import_column_mapping_history"
    id: Mapped[UUID]
    project_id: Mapped[UUID]
    file_fingerprint: Mapped[str]  # sha1(sheet_name + header[:20] + software)
    software_hint: Mapped[str | None]
    mapping: Mapped[dict]           # {"voucher_no": "凭证号", ...}
    confirmed_by: Mapped[UUID]
    confirmed_at: Mapped[datetime]
    override_parent_id: Mapped[UUID | None]  # 覆盖历史链
```

**detect 阶段应用**：
```python
async def detect_with_history_reuse(sheet_detection, project_id):
    fp = sha1(sheet_detection.sheet_name + "|".join(sheet_detection.header_cells[:20]))
    history = await db.execute(select(ImportColumnMappingHistory).where(
        ImportColumnMappingHistory.project_id == project_id,
        ImportColumnMappingHistory.file_fingerprint == fp,
        ImportColumnMappingHistory.created_at > datetime.now() - timedelta(days=30),
    ).order_by(desc("created_at")).limit(1))
    if match := history.scalar_one_or_none():
        # 应用到 sheet_detection.columns
        for col in sheet_detection.columns:
            if col.standard_field in match.mapping:
                col.auto_applied_from_history = True
                col.history_mapping_id = match.id
                col.confirmed_by = match.confirmed_by
                col.confirmed_at = match.confirmed_at
```

#### D13.4 retention_class 策略（F53）

**`ImportArtifact` 新字段**：
```python
retention_class: Mapped[Literal["transient", "archived", "legal_hold"]] = \
    mapped_column(String(20), default="transient")
retention_expires_at: Mapped[datetime | None]
```

**自动决策**（activate 事务内）：
```python
def compute_retention_class(dataset, db) -> str:
    # 1. legal_hold 手动标记优先
    if dataset.legal_hold_flag:
        return "legal_hold"
    # 2. 有 final 签字报表绑定 → archived
    bound_finals = db.scalar(select(func.count()).select_from(AuditReport).where(
        AuditReport.bound_dataset_id == dataset.id,
        AuditReport.status == "final",
    ))
    if bound_finals > 0:
        return "archived"
    return "transient"

def compute_expires_at(retention_class: str) -> datetime | None:
    now = datetime.now(UTC)
    if retention_class == "transient":
        return now + timedelta(days=90)
    if retention_class == "archived":
        return now + timedelta(days=365 * 10)  # 10 年
    return None  # legal_hold 永不过期
```

**purge 任务（F3 扩展）**：
```python
async def purge_old_datasets(project_id, keep_count=3):
    # 找可删的 superseded
    candidates = await db.execute(select(LedgerDataset).where(
        LedgerDataset.project_id == project_id,
        LedgerDataset.status == "superseded",
        # 排除被下游绑定的
        ~LedgerDataset.id.in_(select(AuditReport.bound_dataset_id).where(
            AuditReport.bound_dataset_id.isnot(None)
        )),
        ~LedgerDataset.id.in_(select(WorkingPaper.bound_dataset_id).where(
            WorkingPaper.bound_dataset_id.isnot(None)
        )),
        # transient 类别才在此轮删
        LedgerDataset.id.in_(select(ImportArtifact.dataset_id).where(
            ImportArtifact.retention_class == "transient"
        )),
    ).order_by(desc("activated_at"))).scalars().all()
    # 保留最新 N 个
    for d in candidates[keep_count:]:
        await DatasetService.purge(d.id)
```

## 风险补充

### 风险 6：F50 rollback 被 final 报表"死锁"
**场景**：一旦有 final 报表，对应 dataset 再也不能 rollback。如果该 dataset 数据确实错了怎么办？

**缓解**：
- admin 角色提供 `POST /datasets/{id}/force-unbind` 接口（需双人授权）
- 解绑会自动 `AuditReport.status: final → review`（撤销签字），审计日志记录完整链路
- 这是"合规例外"机制，正常流程不应触发

### 风险 7：F51 并发限流配置过严
**场景**：默认 3 并发对大型事务所太少（10+ 项目同时审计）

**缓解**：
- feature flag `LEDGER_IMPORT_MAX_CONCURRENT` 运维可调
- 监控 `ledger_import_concurrent_jobs` gauge，持续排队超 10 个告警

### 风险 8：F52 fingerprint 碰撞
**场景**：不同客户的 sheet 可能有相同 header 结构

**缓解**：fingerprint 加入 `project_id` 作为第一层过滤；跨项目复用必须用户显式点"应用其他项目 mapping"。

---

## 文档同步清单

- `docs/adr/ADR-002-ledger-view-refactor.md`：F1/F18/F19 架构 + 迁移时间表
- `docs/adr/ADR-003-ledger-import-recovery-playbook.md`：F28 恢复剧本
- `docs/adr/ADR-004-ledger-activate-isolation.md`：F29 事务隔离
- `docs/LEDGER_IMPORT_V2_ARCHITECTURE.md`：新增"可见性架构"章节 + "下游绑定"章节

---

## 第三轮补齐（D23-D31，堵一致性审查发现的缺口）

### D23 purge 基础任务（F3）

**新 worker 模块** `backend/app/workers/dataset_purge_worker.py`：
```python
async def run(stop_event):
    """每晚 03:00 跑 purge。"""
    while not stop_event.is_set():
        now = datetime.now(UTC)
        next_run = now.replace(hour=3, minute=0, second=0) + timedelta(days=1 if now.hour >= 3 else 0)
        sleep_seconds = (next_run - now).total_seconds()
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=sleep_seconds)
        except asyncio.TimeoutError:
            await _run_purge_cycle()

async def _run_purge_cycle():
    projects = await db.execute(select(Project.id)).all()
    for pid, in projects:
        try:
            await DatasetService.purge_old_datasets(pid, keep_count=3)
        except Exception as e:
            logger.error("purge failed for project %s: %s", pid, e)
    # REINDEX CONCURRENTLY 避免阻塞
    for idx in ("idx_tb_balance_active_queries", "idx_tb_ledger_active_queries",
                "idx_tb_aux_balance_active_queries", "idx_tb_aux_ledger_active_queries"):
        await db.execute(text(f"REINDEX INDEX CONCURRENTLY {idx}"))
```

**DatasetService.purge_old_datasets 新方法**：按 F53 规则（排除下游绑定 + retention_class 过滤 + 保留 N 个 superseded）。

### D24 F4 审计轨迹（字段扩展 + 历史端点）

**`ActivationRecord` 扩展字段**（Alembic 迁移 `view_refactor_activation_record_20260523.py`）：
```python
op.add_column("activation_records", sa.Column("ip_address", sa.String(64), nullable=True))
op.add_column("activation_records", sa.Column("duration_ms", sa.Integer, nullable=True))
op.add_column("activation_records", sa.Column("before_row_counts", JSONB, nullable=True))
op.add_column("activation_records", sa.Column("after_row_counts", JSONB, nullable=True))
op.add_column("activation_records", sa.Column("reason", sa.Text, nullable=True))  # F31 提供
op.add_column("activation_records", sa.Column("action", sa.String(20), nullable=False, server_default="activate"))  # activate/rollback/force_unbind/orphan_cleanup
```

**新端点** `GET /api/projects/{pid}/ledger-import/datasets/history`：
- 返回 `[{dataset_id, status, activated_at, activated_by, row_counts, records: [ActivationRecord...]}]`
- 按 activated_at DESC 排序，支持 year 过滤

### D25 F5 跨年度同项目支持

**天然支持**（B' 架构顺带解决）：
- `get_active_filter` 按 `(project_id, year, dataset.status='active')` 过滤
- 同 project 不同 year 的 dataset 互不影响
- activate 2025 时 `WHERE status='active' AND project_id=X AND year=2025` → 只切同 year，2024 不受影响

**唯一需改**：`DatasetService.activate` 的 `mark_previous_superseded` 查询必须带 year 约束（审查发现风险点）：
```python
# 改前（可能误切其他年度）
UPDATE ledger_datasets SET status='superseded'
WHERE project_id=:pid AND status='active'  # ← 缺 year 条件

# 改后
UPDATE ledger_datasets SET status='superseded'
WHERE project_id=:pid AND year=:year AND status='active'
```

**验证**：`test_multi_year_coexist.py` 集成测试覆盖。

### D26 识别引擎强化（F6-F11）—— 本轮最大缺口

#### D26.1 文件名元信息利用（F6）

**detector.py 新函数**：
```python
_FILENAME_KEYWORDS = {
    "balance": ["科目余额表", "余额表", "试算平衡", "TB"],
    "ledger": ["序时账", "凭证明细", "总账", "GL", "账簿"],
    "aux_balance": ["辅助余额", "核算项目余额"],
    "aux_ledger": ["辅助明细", "核算项目明细"],
}
_FILENAME_PERIOD_PATTERNS = [
    r"(\d{2,4})[年\.\-年](\d{1,2})月?",   # 24年10月 / 24.10
    r"(\d{4})(\d{2})",                    # 202410
]

def _extract_filename_hints(file_name: str) -> dict:
    """从文件名提取 table_type 倾向和期间信息。"""
    hint = {"table_type_bias": {}, "period": None}
    for tt, keywords in _FILENAME_KEYWORDS.items():
        for kw in keywords:
            if kw in file_name:
                hint["table_type_bias"][tt] = 20  # +20 置信度
    for pat in _FILENAME_PERIOD_PATTERNS:
        if m := re.search(pat, file_name):
            y, mth = m.groups()
            if len(y) == 2:
                y = "20" + y
            hint["period"] = int(mth)
            hint["year"] = int(y)
            break
    return hint
```

**应用点**：`_detect_xlsx_from_path` 在 sheet 内容置信度 <60 时按 `filename_hint.table_type_bias` 加分。

#### D26.2 方括号 + 组合表头（F7）

**detector.py 新函数**：
```python
_BRACKET_RE = re.compile(r"\[([^\]]+)\]")
_COMPOUND_SEP = re.compile(r"[#/·・]")

def _normalize_header(cell_str: str) -> tuple[str, list[str]]:
    """归一化表头：剥方括号壳 + 拆组合字段。
    
    Returns (primary_name, compound_fields)。
    '[凭证号码]#[日期]' → ('凭证号码', ['凭证号码', '日期'])
    '[日期]' → ('日期', [])
    '凭证号码' → ('凭证号码', [])
    """
    # 剥括号
    stripped = _BRACKET_RE.sub(lambda m: m.group(1), cell_str)
    # 拆组合
    if parts := _COMPOUND_SEP.split(stripped):
        if len(parts) > 1:
            return parts[0].strip(), [p.strip() for p in parts]
    return stripped.strip(), []
```

**应用点**：`_detect_header_row` 对每个单元格先过一遍 `_normalize_header`，拆出的 compound_fields 保存到 `detection_evidence["compound_headers"]`，identifier 侧对每个子字段独立查别名。

#### D26.3 表类型鲁棒性（F8）

**identifier.py 改造**：
- `sheet1` / `列表数据` / `sheet` / `工作表` 等通用名改为**中性评分**（不加不减），当前可能-10
- 同 workbook 多余额表区分：detect 阶段对每个被识为 balance 的 sheet 查其列里是否含 `aux_type` 别名 → 有则降级为 `aux_balance`
- 新增 `_classify_balance_variant(columns)`：
  ```python
  def _classify_balance_variant(columns: list[ColumnDetection]) -> str:
      """如果余额表含 aux_type/aux_code 列，返回 'aux_balance' 否则 'balance'。"""
      aux_indicators = {"aux_type", "aux_code", "aux_name"}
      for c in columns:
          if c.standard_field in aux_indicators and c.confidence >= 70:
              return "aux_balance"
      return "balance"
  ```

#### D26.4 多 sheet unknown 透明化（F9）

**SheetDetection 字段扩展**：
```python
class SheetDetection(BaseModel):
    ...
    warnings: list[SheetWarning]  # 已有字段
    skip_reason: str | None = None  # 新增：unknown 时填写中文原因

class SheetWarning(BaseModel):
    code: Literal["SKIPPED_UNKNOWN", "LOW_CONFIDENCE", ...]
    message_cn: str
    severity: Literal["info", "warning"]
```

**detect 阶段决策逻辑**：
```python
if identified.table_type == "unknown":
    if sheet.row_count < 10:
        skip_reason = f"行数太少 ({sheet.row_count} 行)"
    elif not sheet.header_cells:
        skip_reason = "无法识别表头"
    else:
        skip_reason = f"列内容不符合任何已知表类型（最高置信度 {max_conf}）"
    detection.skip_reason = skip_reason
    detection.warnings.append(SheetWarning(
        code="SKIPPED_UNKNOWN", message_cn=skip_reason, severity="info"
    ))
```

**前端 `DetectionPreview.vue` 扩展**：unknown sheet 显示灰色卡片 + skip_reason badge。

#### D26.5 CSV 大文件保障（F10）

**`iter_csv_rows_from_path` 已实现流式读**（Sprint 6 Part 1 已在），本轮只需验证：
- 编码探测只读前 64KB
- 解析用 `csv.reader` 按行迭代，不 `.readlines()` 全量加载
- chunk 写入时 chunk_size=1000 行

**新增 `test_large_csv_smoke.py`**：合成 100MB CSV（500k 行）→ 断言 detect <5s / parse 峰值内存 <200MB（用 `tracemalloc` 或 `psutil.Process().memory_info().rss`）。

#### D26.6 9 家样本 header 快照测试（F11）

**新文件** `backend/tests/fixtures/header_snapshots.json`：
```json
{
  "YG36_四川物流.xlsx": {
    "科目余额表": {"data_start_row": 4, "header_cells": ["科目编码", "科目名称", "年初余额", ...]},
    "序时账":     {"data_start_row": 2, "header_cells": ["凭证日期", "凭证号", "摘要", ...]}
  },
  "陕西华氏-余额表-2024.xlsx": {...},
  ...  # 9 家全部
}
```

**参数化测试** `test_9_samples_header_detection.py`：
```python
@pytest.mark.parametrize("file_name,sheet_name,expected", load_snapshots())
def test_header_detection_snapshot(file_name, sheet_name, expected):
    path = SAMPLES_DIR / file_name
    if not path.exists():
        pytest.skip(f"真实样本 {file_name} 不存在")
    detection = detect_file_from_path(path)
    sheet = next(s for s in detection.sheets if s.sheet_name == sheet_name)
    assert sheet.data_start_row == expected["data_start_row"]
    assert sheet.header_cells[:8] == expected["header_cells"][:8]
```

### D27 F28 恢复剧本 ADR-003 细则

**文件结构** `docs/adr/ADR-003-ledger-import-recovery-playbook.md`：
```
# ADR-003 导入故障恢复剧本

## 目录
1. activate 中 PG 重启
2. staged 孤儿累积
3. 索引膨胀
4. connection leak
5. 诡异可见性错误
6. DLQ 非空 / 事件广播失败
7. integrity_check_failed
8. 灰度 flag 回滚

## 场景 1：activate 中 PG 重启

### 症状
- job.status = 'activating' 持续超 5 分钟
- pg_stat_activity 无相关 query

### 诊断命令
...具体 SQL
### 恢复步骤
1. `python -c "from app.services.import_job_runner import resume_from_checkpoint; ..."`
2. 等待 1 秒 activate 完成
3. 验证：`SELECT status FROM ledger_datasets WHERE id = 'xxx'`
### 回滚
若 resume 失败：手动把 job.status 改 failed + 通知用户重新上传
```

每个场景必须有：症状、诊断命令（可 copy-paste）、恢复步骤、回滚步骤。

### D28 F29 事务隔离 ADR-004 细则

**文件** `docs/adr/ADR-004-ledger-activate-isolation.md`：
- **决策**：`DatasetService.activate` 使用 `REPEATABLE READ` 隔离级别
- **依据**：
  - 并发 activate 同 project+year 可能双 active（race condition）
  - `REPEATABLE READ` 下第二个事务看到第一个事务开始时的快照，`WHERE status='active'` 仍返回旧 active，UPDATE 时 PG 检测到冲突抛 `40001 SerializationFailure`
  - Python 侧 `@retry_on_serialization_failure` 装饰器自动重试
- **幂等键**：`(project_id, year, dataset_id)` 二次 activate（同 dataset）直接返回成功，不抛错
- **代码**：
  ```python
  async def activate(...):
      async with db.begin() as tx:
          await db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
          ...
  ```

### D29 F31 激活意图确认（前端设计）

**组件** `DatasetActivationButton.vue`：
```html
<el-button @click="onClickActivate" type="primary">激活</el-button>
```
```ts
async function onClickActivate() {
  const { value: reason } = await ElMessageBox.prompt(
    `即将激活数据集：${dataset.name}\n影响：所有项目组成员立即看到新数据\n旧版本：${oldVersion} 将标记为 superseded\n\n激活理由（可选）：`,
    '确认激活',
    { inputPlaceholder: '说明激活原因（如：修正期末余额错误）', inputRequired: false }
  )
  await eqcrApi.activateDataset({ dataset_id, reason })
}
```

### D30 F42 零行/异常规模拦截

**detect 阶段规则**：
```python
async def check_scale_warnings(detection, project_id, db):
    total_rows = detection.total_rows_estimate
    warnings = []
    
    # 零行拦截
    if total_rows < 10:
        warnings.append({"code": "EMPTY_LEDGER_WARNING", "severity": "warning",
                         "message": f"数据量过少（{total_rows} 行）"})
    
    # 规模异常：对比历史均值
    history_mean = await db.scalar(select(func.avg(LedgerDataset.total_rows)).where(
        LedgerDataset.project_id == project_id,
        LedgerDataset.status == "active",
    ))
    if history_mean and history_mean > 0:
        ratio = total_rows / history_mean
        if ratio < 0.1 or ratio > 10:
            warnings.append({"code": "SUSPICIOUS_DATASET_SIZE", "severity": "warning",
                            "message": f"规模异常：当前 {total_rows} vs 历史均值 {int(history_mean)} ({ratio:.1f}×)"})
    return warnings
```

**submit 门控**：`ImportJob.force_submit: bool`，值为 False 时有 `EMPTY_LEDGER_WARNING` / `SUSPICIOUS_DATASET_SIZE` 的 submit 返回 400 + 要求用户前端点"强制继续"后 `force_submit=True` 重发。

### D31 F43 健康端点细则

**端点实现** `backend/app/routers/health.py`：
```python
@router.get("/api/health/ledger-import")
async def ledger_import_health():
    pool_used = db_engine.pool.checkedout()
    pool_max = db_engine.pool.size() + db_engine.pool.overflow()
    
    active_workers = len([w for w in registered_workers if w.is_alive()])
    expected_workers = len(registered_workers)
    
    p95 = IMPORT_DURATION.labels(phase="total")._sum.get() / max(IMPORT_DURATION.labels(phase="total")._count.get(), 1)  # 简化
    
    queue_depth = await db.scalar(select(func.count()).where(ImportJob.status == "queued"))
    last_activate = await db.scalar(select(func.max(ActivationRecord.created_at)))
    
    status = "healthy"
    if active_workers < expected_workers:
        status = "unhealthy"
    elif pool_used / pool_max > 0.8 or p95 > 600:
        status = "degraded"
    
    HEALTH_STATUS.set({"healthy": 0, "degraded": 1, "unhealthy": 2}[status])
    
    return {
        "status": status,
        "queue_depth": queue_depth,
        "active_workers": active_workers,
        "expected_workers": expected_workers,
        "p95_duration_seconds": p95,
        "pg_connection_pool_used": pool_used,
        "pg_connection_pool_max": pool_max,
        "last_successful_activate_at": last_activate,
    }
```

Kubernetes probe：
```yaml
livenessProbe:
  httpGet:
    path: /api/health/ledger-import
    port: 9980
  periodSeconds: 30
  failureThreshold: 3  # 3 次 unhealthy 才重启
```

### D32 F44 graceful shutdown 细则

**`ImportJobRunner` 新增 signal handler**：
```python
class ImportJobRunner:
    _stop_event: asyncio.Event
    
    def __init__(self):
        self._stop_event = asyncio.Event()
        signal.signal(signal.SIGTERM, self._on_sigterm)
    
    def _on_sigterm(self, signum, frame):
        logger.warning("SIGTERM received, initiating graceful shutdown")
        self._stop_event.set()
    
    async def _execute_v2(self, job_id):
        async def _cancel_check():
            if self._stop_event.is_set():
                raise InterruptedError("worker shutting down")
            return False
        ...
        try:
            await execute_pipeline(..., cancel_check=_cancel_check)
        except InterruptedError:
            await ImportJobService.transition(job_id, "interrupted",
                                              current_phase="graceful_shutdown")
            raise  # 让外层重启机制看到
```

**超时保护**：main.py lifespan 关闭阶段 `asyncio.wait_for(runner.wait_idle(), timeout=30)`，超时 `SIGKILL`。

**`recover_jobs` 扩展**：`interrupted` 状态 job 启动时自动调 `resume_from_checkpoint`（F14）。
