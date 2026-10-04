# Task 3 快照与 schema/ORM 三层一致（交付证据）

> spec: `chain-closure-phase4-deliverable-center-trio` / 任务 3。append-only。
> 基线：HEAD `19c65589d`，分支 `work/2026-10-01-i-cycle-classification-convergence`。
> 需求：1.5, 2.4, 3.2, 7.5。

## 一、现算最高迁移号（不信基线文档，live 重算）

- 磁盘 `backend/migrations` 现算最高 **V179**；真 PG `schema_version` `MAX(version)=179`（两处一致）。
- `MigrationRunner.scan_migrations()` 现算 count=180、max=180，**无重复版本号 RuntimeError**
  （同号检测通过）。新增迁移从 **V180** 起，无撞号。

## 二、交付物

- 迁移：`backend/migrations/V180__deliverable_trio_attempt_and_snapshot.sql` +
  `R180__rollback_deliverable_trio_attempt_and_snapshot.sql`（配对，全 DDL `IF NOT EXISTS` /
  `IF EXISTS` 幂等）。
- ORM：`backend/app/models/phase13_models.py`
  - 新增 `ExportJobAttempt` 模型（append-only 尝试历史表 `export_job_attempts`）；
  - `ExportJobItem` 新增 `step_key / sequence / snapshot_id / version_id / file_path /
    file_size / file_sha256 / attempt_count / last_attempt_id`；
  - `WordExportTaskVersion` 新增 `file_sha256 / snapshot_id`（显式命名列，历史 `file_hash` 保留）；
  - `ExportJob` 新增 `snapshot_id / trio_total(默认3) / trio_succeeded(默认0) / readiness /
    started_at / finished_at`。
- 共享快照：`backend/app/services/deliverable_trio_snapshot.py`（新增）
  - `build_digest(content)`：对规范化 JSON 取 sha256，**计算前剔除生成时间键
    （generated_at/captured_at/…）与以 `abs_path` 结尾的绝对路径键** ⇒ 同输入同 digest；
  - `DeliverableTrioSnapshot.bind_items_to_snapshot(job_id, snapshot_id)`：把同一 digest 写进
    job 与三件套三项 item 的 `snapshot_id`；
  - `verify_trio_shares_snapshot(job_id)`：复核三项绑定同一非空 snapshot_id（跨快照 fail-closed）。
- 单源收敛：`deliverable_readiness_service._build_snapshot` 改为复用 `build_digest`
  （readiness 与 executor/retry 路径同一 digest 口径）。

## 三、三层一致（DB 迁移 + ORM Mapped[] + service）

- DB：V180 在真 PG 上建表/加列（见下 PG 证据）。
- ORM：`ExportJobAttempt.__table__.columns` 17 列、item/job/version 新列均存在
  （`python -c` 实证打印全部命中）。
- service：`DeliverableReadinessService` 与 `DeliverableTrioSnapshot` 用同一 `build_digest`，
  三项 item 经 `bind_items_to_snapshot` 引用同一 snapshot_id。

## 四、测试与证据

测试文件：`backend/tests/test_phase4_trio_snapshot_schema.py`（新增，12 用例）。
命令：`..\.venv\Scripts\python.exe -m pytest tests/test_phase4_trio_snapshot_schema.py -q`
（cwd=backend）。结果：**12 passed**。

### A 组 SQLite 真 ORM + 纯函数

- `ExportJobAttempt` 可建行、item/job 新列可读写；
- digest 不含生成时间（两个不同 `generated_at` → 同 digest）；
- digest 不含绝对路径（`file_abs_path` / `report_abs_path` → 同 digest）；
- 同输入同 digest（幂等）；
- 三件套三项 `bind` 后共享同一 snapshot_id，`verify` 为 True。

### B 组 真 PG16（无 PG 环境自动 skip；本机 `audit-postgres` 可连）

- `test_v180_applies_twice_idempotent`：真实 V180 SQL 在一次性库应用**两次**，第二次不报错、
  列集合与第一次一致；关键新列（job/item/version）确实落到真 PG `information_schema`。
- `test_v180_attempt_no_unique_constraint`：同 item 的 `attempt_no` 重复插入被
  `uq_export_job_attempt_item_no` 拒绝（append-only 不可覆盖）。
- `test_v180_step_key_unique_per_job`：同 job 的 `step_key` 重复插入被 `uq_export_job_item_step` 拒绝。
- `test_r180_rollback_removes_table_and_columns`：R180 回滚后 `export_job_attempts` 表与 V180
  新增列全部消失；R180 二次执行幂等不报错。

## 五、变异证明（三类，均已验证）

1. **改快照业务输入 → digest 必变**：`test_mutating_business_input_changes_digest` —
   改 `tb_hash` 后 `build_digest` 结果不同（否则 digest 没真正绑定源数据）。
2. **让一项换 snapshot → 一致性判定必 False**：`test_one_item_different_snapshot_fails_verify` —
   篡改 `disclosure_notes` item 的 snapshot_id 后 `verify_trio_shares_snapshot` 返回 False
   （跨快照混用被拦截）。
3. **迁移漏列 → schema 断言必红**：一次性探针（`_phase4_mut_probe.py`，用完即删）从 V180 删去
   `export_job_items_v2.file_sha256` 的 ADD 行后在真 PG 应用，`{step_key,sequence,snapshot_id,
   file_sha256} <= cols` 断言变 False（输出 `RESULT: RED(good: 漏列被捕获)`）。

## 六、回归与归因

- `tests/test_phase4_readiness_gates.py`（Task 2）+ `test_migration_runner_rollback.py` +
  `test_migration_runner.py`：**77 passed**（readiness 改用 `build_digest` 无回归）。
- phase13 ORM 重负载抽样（deliverable_center p0/p1/p2 + package_pbt + batch_brief）：
  55 passed / 1 failed。唯一失败 `test_onlyoffice_disabled_without_secret` 经 `git stash`
  在**干净 HEAD** 复跑**同样失败** ⇒ HEAD 预存环境依赖红（本机设了 ONLYOFFICE 密钥），
  **非本任务引入**。

## 七、与基线红的关系（边界说明）

- `test_phase4_trio_baseline_red.py` RED-2 两条（retry attempt / 保留失败原因）此前以
  **`ImportError: cannot import name 'ExportJobAttempt'`** 失败；本任务让该模型可导入后，
  失败形态变为「attempt 表为空 / 原因未找到」—— 即 **schema 层已就绪，行为层属 Task 7/8**
  （`retry_failed` 真正新增 attempt 与保留历史）。本任务**未**触碰 `retry_failed` /
  `render_and_store` / `TRIO_STEPS`（分别属 Task 8 / Task 4 / Task 5），不越界伪绿。
- 仍为预期红：RED-1（render_and_store fail-closed，Task 4）、RED-3（TRIO_STEPS 常量，Task 5）、
  RED-2 行为层（Task 7/8）。

## 八、范围说明

- 本任务只做 schema/ORM/快照三层一致与迁移幂等/约束/回滚；不改 executor 顺序、retry 行为、
  render_and_store、路由与前端。
- 无 PG-only 风险 SQL 进 SQLite 路径（PG 专用 DDL 只在 B 组真 PG 临时库执行；A 组走 ORM）。
- 一次性变异探针已删除（`_` 前缀，用完即删）。
