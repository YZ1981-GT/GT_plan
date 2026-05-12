# ADR-004: Ledger Activate Transaction Isolation

**状态**：Accepted (Sprint 10 / 2026-05-10)
**背景**：F29 — `DatasetService.activate` 的事务隔离级别、幂等语义与并发一致性。

## 背景与动机

B' 架构下 `DatasetService.activate` 仅修改 metadata（UPDATE 2 行 `ledger_datasets`），
不再 UPDATE 百万级 Tb* 物理行，所以事务本身非常短（<1s）。
但下列并发场景仍需保证正确：

1. **同 project + 同 year 并发 activate 两个 staged**
   - 典型：PM 和 审计助理 A 几乎同时点 "激活"（中间只差 100ms）
   - 错误结果：两个 dataset 都变成 `active`（违反"同 project+year 只有一个 active"约束）
   - 正确结果：后到的事务看到旧 active 已是 superseded，拒绝或覆盖，但不应出现双 active

2. **activate 与 rollback 并发**
   - 典型：A 激活 V2 同时 B 发现问题要 rollback V1
   - 需要互斥（已由 F23 Sprint 5.14 的 `ImportQueueService.acquire_action_lock` 解决）

3. **Resume from checkpoint 导致的重复 activate**
   - `ImportJobRunner.resume_from_checkpoint` 重跑 activate 阶段
   - 若 dataset 已经 `active`，应幂等返回成功而非报错

## 决策

### 决策 1：PG 事务隔离级别 = REPEATABLE READ

**原因**：默认 `READ COMMITTED` 下并发事务可能看到不一致的 `status` 值（某事务 commit 后另一事务再次读取会看到新值）。
REPEATABLE READ 保证事务内读取一致性，并且 PG 的 REPEATABLE READ 实际是
Snapshot Isolation，不会出现 phantom read。

**代价**：并发更新同一行时抛 `SerializationFailure` (40001)。需配套重试机制。

**实施**（Sprint 10.38，延后）：
```python
async with db.begin() as txn:
    await db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
    # activate 逻辑
```
SQLite 无等价语义，测试场景下跳过此 SET。

### 决策 2：幂等键 (project_id, year, dataset_id)

**规则**：同一 `(project_id, year, dataset_id)` 二次 activate 直接返回成功。
`DatasetService.activate` 入口检查：
```python
if dataset.status == DatasetStatus.active:
    return dataset  # 幂等返回
if dataset.status != DatasetStatus.staged:
    raise ValueError(...)  # 非法状态
```

**已落地**：Sprint 10.39（已 commit）。

### 决策 3：重试装饰器 `@retry_on_serialization_failure`

**规则**：activate / rollback 装饰后，最多重试 3 次（首次 + 3 次重试），
指数退避（50ms → 100ms → 200ms → 400ms）+ ±50% 抖动。
仅对 SQLSTATE 40001 / 40P01 重试，其他异常直接冒泡。

**已落地**：Sprint 10.37 `backend/app/services/retry_utils.py`。

**使用方式**（延后在 activate 外层加装饰器）：
```python
@retry_on_serialization_failure(max_retries=3, initial_delay_ms=50)
async def activate_with_retry(db, dataset_id, ...):
    async with db.begin():
        await db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
        return await DatasetService.activate(db, dataset_id, ...)
```

### 决策 4：项目级锁作为强保证

即使事务隔离有不完美，`F23 / Sprint 5.14` 的
`ImportQueueService.acquire_action_lock(project_id, action="activate"/"rollback")`
是更粗粒度的互斥保证：同 project 同时只有一个 activate/rollback/import 操作。

**组合使用**：
- 锁：粗粒度（项目级），10 min 超时，防长期占用
- 事务隔离：细粒度（行级），只在锁释放瞬间的小窗口起作用

## 考虑过但未采用

### 乐观并发：版本号字段 (UPDATE ... WHERE version = X)

**否决原因**：需要 `LedgerDataset.version INTEGER DEFAULT 0` 字段 + 全部更新都带 `WHERE version = old_version RETURNING version+1`；改动面大。REPEATABLE READ + 重试在当前量级足够。

### 行级悲观锁：SELECT ... FOR UPDATE

**否决原因**：阻塞其他事务，容易死锁。现有 `ImportQueueService` 内存级 lock 已经承担悲观锁职责，DB 再锁一层是重复。

## 边界 case 测试清单

已覆盖（在 `tests/integration/test_dataset_purge_basic.py` / `test_multi_year_coexist.py`）：
- ✅ 同 project 跨 year 双 activate（不互相污染）
- ✅ 同 project 同 year 二次 activate 新 staged（旧 active → superseded）
- ✅ 同 dataset 二次 activate（幂等返回）

待补（PG-only，需真实 PG 环境）：
- 并发 activate 两个不同 staged → 无双 active
- activate 事务中 PG 重启 → activate 失败回滚，staged 未变

## 参考

- PG 文档：https://www.postgresql.org/docs/current/transaction-iso.html
- SQLAlchemy: `Connection.execution_options(isolation_level="REPEATABLE READ")`
- `asyncpg.exceptions.SerializationError` 对应 SQLSTATE 40001
