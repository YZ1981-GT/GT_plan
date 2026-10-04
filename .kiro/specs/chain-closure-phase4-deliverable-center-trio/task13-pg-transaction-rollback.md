# Task 13 — 真 PG 临时 schema 与事务回滚（交付证据）

> spec `chain-closure-phase4-deliverable-center-trio`，需求 7.5。
> 分支 `work/2026-10-01-i-cycle-classification-convergence`，基线 HEAD `19c65589d`。
> append-only。

## 一、交付定位

Task 13 不新增生产代码，是对 Tasks 3/4/6/8/9 已交付的迁移、约束、savepoint、文件指纹的
**真实 PostgreSQL 16 事务回滚闭环证据**：迁移/约束/savepoint/行锁/下载指纹逐项在真 PG16 验证，
并补齐本任务核心断言 ——「试跑前后 job/version/attempt/文件指纹**零痕迹**」。

全部用一次性 throwaway 数据库（`CREATE DATABASE` → 跑真实迁移/裸 DDL → 断言 →
`DROP DATABASE`），**绝不**写真实项目生产库 `audit_platform` 作通过证据（需求 7.5）。
无 PG 环境时每条用例 `skip`（如实标依赖阻断，不以 SQLite / HTTP 200 冒充）。

新测试文件：`backend/tests/test_phase4_trio_pg_transaction_rollback.py`（6 条，全部真 PG16）。

## 二、覆盖矩阵与断言

| # | 用例 | 覆盖 | 真 PG16 断言 |
|---|------|------|------|
| 1 | `test_v180_apply_then_r180_rollback_clean` | **迁移** | V180 apply 建 `export_job_attempts` 表 + job/item/version 新列；R180 回滚后表与列全部消失（apply→rollback 一条龙 + 残留清零） |
| 2 | `test_attempt_no_unique_serializes_concurrent_inserts` | **约束** | 两条独立连接并发抢同一 `(item_id, attempt_no)`，`uq_export_job_attempt_item_no` 串行化、第二条被拒；终态该 item 仅一行 |
| 3 | `test_executor_native_savepoint_rolls_back_business_keeps_trace` | **savepoint** | 真 PG `AsyncSession` 跑真实 executor，第 2 步失败：原生 `ROLLBACK TO SAVEPOINT` 撤销半成品版本，失败 attempt + item=failed 留痕存活、第 1 步成功版本存活 |
| 4 | `test_trio_chain_uses_no_row_lock_concurrency_guard_is_unique_index` | **行锁** | 现算证明三件套链源码不含 `with_for_update` / `FOR UPDATE` / `pg_advisory`；并发守卫是唯一索引（行锁对本链**不适用**，如实记录） |
| 5 | `test_download_fingerprint_verify_on_real_pg_version_row` | **下载指纹** | 真 PG 版本行记录 sha256/size，`verify_file_fingerprint` 通过；截断→size 不符 fail-closed（`file_hash_mismatch`），错哈希→失配 fail-closed |
| 6 | `test_dry_run_in_rolled_back_transaction_leaves_zero_trace` | **零痕迹（核心）** | 事务内跑完整 executor（建 job/item/attempt + 版本行），`ROLLBACK` 外层事务后用**独立连接**复查：job/version/attempt/item 计数回到试跑前（零新增）；dry-run 落盘文件清理后指纹不可再校验（`missing_file`，零残留） |

### 关于「行锁」子项的诚实结论

三件套编排链（`full_deliverables_executor` / `export_job_service` / `deliverable_service`）
**不使用行锁**。attempt append-only 的并发正确性由 V180 的
`uq_export_job_attempt_item_no` 唯一索引承载（用例 2 在真 PG 原生并发下证明）。
故「行锁」对本链判为**不适用**，用现算断言（用例 4）守护「将来有人给链路加行锁时必须
同步更新本依据与断言」，而非假装覆盖一个不存在的机制。

## 三、零痕迹断言的非恒绿证明（变异）

把用例 6 的 `await dry.rollback()` 变异为 `await dry.commit()`（即 dry-run 不回滚、
真落库）后复跑：

```
E   {'jobs': 1} != {'jobs': 0}
tests/test_phase4_trio_pg_transaction_rollback.py: AssertionError
1 failed
```

`after == baseline` 精确打红（`jobs` 从 0 变 1），证明零痕迹断言真正绑定「回滚后无残留」
而非两个空集的恒真比较。用例内 `in_tx` 断言（事务内 `jobs>=1 / items>=1 / attempts>=1`）
进一步证明 dry-run 确实跑了完整业务流程、写入了数据，而非空操作。复原后 6 passed。

## 四、运行证据（Windows / `..\.venv\Scripts\python.exe`，cwd=backend）

```
# Task 13 新测（全部真 PG16，audit-postgres 容器 Up）
tests/test_phase4_trio_pg_transaction_rollback.py
  6 passed in 3.54s
  · test_v180_apply_then_r180_rollback_clean .................. PASSED
  · test_attempt_no_unique_serializes_concurrent_inserts ...... PASSED
  · test_executor_native_savepoint_rolls_back_business_keeps_trace  PASSED
  · test_trio_chain_uses_no_row_lock_concurrency_guard_is_unique_index  PASSED
  · test_download_fingerprint_verify_on_real_pg_version_row ... PASSED
  · test_dry_run_in_rolled_back_transaction_leaves_zero_trace . PASSED

# 零痕迹变异（rollback→commit）必红：
  test_dry_run_in_rolled_back_transaction_leaves_zero_trace
  1 failed，断言命中 {'jobs': 1} != {'jobs': 0}；复原后 6 passed

# 全 phase4_trio 回归（9 文件，含本新文件）
  74 passed in 59.45s（68 既有 + 6 新）

# throwaway 库清零核验（容器内 psql）
  SELECT datname FROM pg_database WHERE datname LIKE 'phase4_t13%' …
  → 0 行（所有一次性库已 DROP，无残留）
```

> 全量 `pytest -k phase4_trio` 收集期有 7 个**无关**文件报 collection error
> （`tests/e2e/test_sign_convention_e2e.py` / `tests/playwright/...` / `test_guidance_*`
> / `test_render_config_sheet_context.py` / `test_task_event_bus_idempotency_auth.py`），
> 属 HEAD 预存、与本任务无关；显式枚举 9 个 phase4_trio 文件跑则 74 passed 全绿。

## 五、边界

- 只做真 PG16 事务回滚闭环**证据**，不新增/修改生产代码。
- 真 PG 临时库建表用裸 DDL（只建 executor 实际触碰的 7 张表、去 FK），避开
  `Base.metadata.create_all` 的全量 FK 闭包与未安装的 `vector` 扩展（本机 PG 无 pgvector）。
- 临时库用完即删（`DROP DATABASE` + 先 `pg_terminate_backend` 断连）；**未**写真实项目库
  `audit_platform` 作本任务通过证据（需求 7.5）。
- 「真实项目事务内 dry-run」（Task 14）与「真实出具写库验收」（Task 16）仍为 `[ ]*`，
  需可连接的真实项目数据 / 用户明确授权，本任务不代办。
