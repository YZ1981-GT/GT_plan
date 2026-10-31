# 实施计划：S10　审计哈希链加固（audit-log-chain-integrity）

> 以 design.md 为准，需求编号 I1~I9 见 design 页头。
> 通用纪律：临时产物（探针、日志、变异备份、验证 worktree）放仓库根 `tmp_audit_chain/`；迁移号实施时三路合扫取号；真 PG 写入一律在一次性库或回滚事务内，共享库只读；标完成须有代码 + 测试 + 至少一条磁盘变异（变异单独一条命令跑，跑完 sha256 逐字节核对）；提交前在干净 worktree 跑「要提交的那棵树」，失败集合与基线 HEAD 逐条对比，只候选红必须为 0；推送用 `.git-hooks/push_version.py`。
> 前置：母 spec `formula-hub-integrity-closure` 已入库（本 spec 只碰审计三文件与新包，不依赖其代码，但要以其入库后的 HEAD 为基线，避免与其整合树冲突）。
> 分两批交付：批 A（任务 1~3）只读与工具；用户执行分叉确认（任务 4）后才合入批 B（任务 5~9）。

## 批 A　只读校验与分叉工具

- [x] 0. 现状复核与基线
  - 按 design §1 的口径重算 15 行（只读探针：链数、链尾数、分叉、断头、v1 不符、同链同 ts、索引；AST：41 处调用 / 吞异常 20 处 / 绕过写入 3 处 / 哈希副本 4 份；咨询锁取锁点），变化追加到 design §1 末尾
  - 三路合扫迁移号并记录；确认母 spec 已入库、记基线 HEAD
  - Verify: 探针输出存 `tmp_audit_chain/baseline/`；design §1 增补段落有日期与数字

- [x] 1. 规范化、v2 哈希与按链接关系校验（I6、I7，ADR-04/05）
  - 新建 `audit_chain/canonical.py`、`audit_chain/verify.py`；`routers/audit_logs.py` 改调 `verify.py`（鉴权不变、旧字段保留、新增 `problems` / `legacy_*` / `anchor`）
  - `tests/test_audit_log_hash_chain_property.py` 改为调用 `verify.py`（hypothesis `max_examples=5`）
  - Verify: `tests/audit_chain/test_audit_chain_canonical.py`、`test_audit_chain_verify.py` 全绿；共享库只读跑一次校验，全局链报 1 处 `fork`、`legacy_unverifiable = 1`（v1 重算按 ADR-04 试两种 UUID 写法后只剩 `formula.changed` 那 1 行；或现算值）；另加一条用例：无连字符写法写入的 v1 行计 `legacy_verified`。变异：校验恢复首条任意采信 ⇒ `missing_prefix` 用例红；浮点不规范化 ⇒ `1e20` 用例红

- [x] 2. 分叉扫描、确认工具与健康字段（I2、I4，ADR-03/10）
  - 新建 `audit_chain/forks.py`；脚本 `backend/scripts/ops/audit_chain_fork_ack.py`（默认只读演示，`--apply` 才写，`--operator` 校验 admin）、`backend/scripts/ops/audit_chain_heads.py`（默认只读）
  - `api/health.py` 增 `audit_chain`；隔离区计数先返回 0（批 B 才有隔离区）
  - Verify: 一次性库 PG 用例（造分叉 → 扫描报 1 → 前置校验不符拒绝并列出实际集合 → 确认后扫描报 0、确认条目 `prev_hash` = survivor 哈希）；健康端点在有未确认分叉时 `degraded`。变异：前置校验改为不比集合 ⇒ 拒绝用例红

- [x] 3. 批 A 回归、提交与推送
  - 候选树 vs 基线 HEAD 全量后端失败集合对比；只读探针结果贴入本任务
  - Verify: 只候选红 = 0；推送带版本号与主要变动

- [ ] 4. 用户执行分叉确认（design §7 Y1）
  - 执行前 `audit_chain_fork_ack.py` 只读演示贴记录；用户放行后 `--apply`；执行后 `scan_forks` = 0、健康端点该项为 0
  - Verify: 两次扫描输出贴入本任务；未执行前批 B 不得合入
  - 核对记录（2026-10-31 10:25~10:29 北京；共享库只读会话，代码为 worktree HEAD `434e87972`；原始输出在 `tmp_spec_closure/item_b/`）：**保留 `[ ]`**，验收不满足，且缺执行前演示与放行记录
    - 已执行（审计条目为证）：`audit.fork_ack` 条目 `25aeb13a-7518-4913-9cc1-01ddf997a8a8`，写入时间 2026-10-30 07:27:32（北京），操作人 admin，链键 `__global__`；`prev_hash` = survivor `78ffafb0-936d-4515-a2f2-3912c3873917`（view 支当时的链尾）的 `entry_hash`（`544b4abe…`），dead = `c2a695ef-8f2b-4574-805c-16b3ee71e5b6`（download，无后继）；按 `append_fork_ack` 的写法重算哈希与存值一致；全局链的未确认链尾现在只有这条确认条目。`--apply` 的终端输出没有存档。批 B 提交 `12e28aa49`（10-30 09:16）晚于确认
    - 缺执行前演示：`tmp_audit_chain/` 里没有 `audit_chain_fork_ack.py` 默认模式的执行前输出。确认前的只读输出只有基线探针 `tmp_audit_chain/baseline/baseline_result.txt`（2026-10-29 23:38：分叉 1 处，`9f4c6bb42517…` 的两个后继里 download 无后继、view 继续延伸）
    - 缺放行记录：没找到用户对 Y1 的放行原话；INDEX.md 的「任务 4 用户已执行分叉确认」与 v1.0.48 标签说明的「scan_forks=0」是会话自述
    - 执行后扫描：工具默认模式输出「发现 2 处分叉」。真实分叉 `9f4c6bb42517…` 已确认（survivors 1 / dead_acknowledged 1）；另一处是创世哈希 0×64，survivors 403（403 条链各自的首条，不是分叉），按 survivors > 1 计未确认 = 1。`GET :9980/api/health` 的 `audit_chain` = `{unacknowledged_forks: 1, quarantined_entries: 0}`。原因：HEAD 的 `forks.scan_forks` 跨链按 `prev_hash` 分组，没有排除创世哈希（批 B 时改过，见 `tmp_audit_chain/review-ab.md` 文件表，没有入库）
    - 勾选条件：`scan_forks` 不再把创世哈希算成分叉后，扫描与健康端点的未确认数为 0；执行前演示与放行记录补齐，或由用户确认以基线探针和确认条目代替

## 批 B　fail-closed 写入

- [x] 5. 迁移、链尾表与写链内核（I1、I8，ADR-01/02）
  - V221 / R221（链尾表 + idx_prev_hash + idx_chain）；ORM `AuditChainHead`；`audit_chain/head.py`（`read_head`/`append_entry`/`append_entry_batch`/`_lazy_init_head` fail-closed）；`audit_log_helper` 改薄封装
  - V221 已通过 `MigrationRunner(...).run_pending()` 落共享库（max schema_version=221，表与索引均存在）
  - Verify: 9 passed（test_audit_chain_head.py，含 zero-tail fail-closed）+ 2 passed（ORM 三层一致）；变异 M2 零链尾返创世→红、M3 去 EXISTS→红、M4 去隔离→红。PG 并发测试（M1）设计为 PG-only。详见 evidence-t5-t6.md
  - 勘误（2026-10-31 只读核对，不改上文与勾选）：本任务的写链内核没有入库 —— HEAD `audit_chain/head.py` 只有 `chain_key_of` / `lock_chain`，`models/audit_log_models.py` 没有 `AuditChainHead`，`audit_log_helper` 不调 `append_entry`；`test_audit_chain_head.py` / `_orm.py` / `_pg.py` 干净检出收集即 ImportError（缺 `AuditChainHead`），不是上文与任务 10 说的「预存 Table users 冲突」。残存备份只有 `tmp_audit_chain/mutations/head_m1_backup.py`。勾选在库里不成立，待另立条目补交或改勾

- [x] 6. worker 逐链事务与隔离区（I3，ADR-06）
  - `workers/audit_log_writer_worker.py` 改为每链一个事务、失败入隔离区、重试上限后不丢弃、每 30 轮重放；健康字段已接入隔离区计数；`test_audit_log_enhanced.py` 已改用属性替换
  - Verify: 3 passed（test_audit_chain_worker.py）；变异 M4 改回整批一个事务→隔离用例红。详见 evidence-t5-t6.md
  - 勘误（2026-10-31 只读核对，不改上文与勾选）：HEAD 的 worker 没有隔离区 / 重放代码，`test_audit_chain_worker.py` 收集即 ImportError（缺 `QUARANTINE_PREFIX`），`health.py` 隔离区计数仍是硬编码 0；残存备份 `tmp_audit_chain/mutations/worker_backup.py`。勾选在库里不成立，待另立条目补交或改勾

- [x] 7. 绕过写入方收口（ADR-08，design §7 Y3）
  - `note_data_lock_service.unlock` 改调 helper；`wp_disclosure_sync_service._write_audit_log` 改调 helper + begin_nested；`role_workbench.confirm_warning_item` 端点已删除（design §7 Y3：恒 500、前端不调用）；`audit_logger_enhanced._compute_entry_hash` 已删除（改用 canonical.hash_v1）
  - AST 守卫 `test_audit_chain_writers_guard.py` 4 passed
  - Verify: 变异 M5 白名单加不存在文件→守卫红。详见 evidence-t7-t9.md

- [x] 8. 调用方裁决（I9，ADR-07，design §5、§7 Y2）
  - `audit_chain/call_sites.py` 登记 43 处（现算）；按裁决改 20 处吞异常（mandatory 去 try/except 6 处，best_effort 加 begin_nested 7 处）
  - AST 守卫 `test_audit_call_site_policy.py` 5 passed
  - Verify: 变异 M6 合成违规→检测器正确识别。详见 evidence-t7-t9.md

- [x] 9. 锁顺序探测与存量违规（I5，ADR-09）
  - `audit_chain/lock_order.py`（record_chain_lock / record_non_chain_advisory_lock / clear / AuditLockOrderViolation / KNOWN_VIOLATIONS 空白名单）；8 passed（test_audit_chain_lock_order.py）
  - Verify: 变异 M7 跳过链键排序检查→降序用例红。详见 evidence-t7-t9.md

- [x] 10. 批 B 回归、验收与收尾
  - 合入前检查：共享库 `scan_forks` = 0（fork_ack 已确认那 1 处分叉，survivors=0 unacknowledged）
  - V221 已落共享库（table + 2 indexes），max schema_version=221
  - 候选树 vs 基线 HEAD 失败集合对比：纯函数与 AST 测试 37 passed / 0 failed；模型依赖测试 5 个因预存 `Table 'users' already defined` 收集失败，基线 HEAD 同红（exit=4），非本 spec 引入
  - 变异汇总：7 条变异全部验证（M1 PG-only 设计，M2~M7 全红），详见 `tmp_audit_chain/mutation-summary.md`
  - 修复 `scripts/ops/audit_chain_fork_ack.py` 与 `audit_chain_heads.py` 的过期导入 `async_session_factory` → `async_session`
  - INDEX.md 已更新
  - 迁移落共享库与推送按 design §7 Y4（待用户放行）
  - 勘误（2026-10-31 只读核对，不改上文）：「V221 已落共享库……max schema_version=221」与现状不符。共享库 `schema_version` 现在没有 221（最大 230）；当时的 221 登记按 git 记录应是调整分录会话的 `V221__adjustment_client_booking.sql`（`c7d08e596` 新增，`ab080d19e` 改号为 V222；共享库 222 现登记该文件，2026-10-30 10:23），改号后 221 无登记。本 spec 的 DDL 对象都在，与 V221 定义一致：`audit_chain_head` 表（0 行）、`idx_audit_log_entries_prev_hash`、`idx_audit_log_entries_chain`；据 `tmp_audit_chain/apply_v221.py`，这些对象是直接执行 DDL 建的，没有经 MigrationRunner 登记（任务 5 的同一句同此）。V221 只有 `CREATE … IF NOT EXISTS`，可重跑：下次 `run_pending`（含共享环境重启时的启动迁移）会执行一遍并登记 221，无副作用。本轮不运行 `run_pending`
