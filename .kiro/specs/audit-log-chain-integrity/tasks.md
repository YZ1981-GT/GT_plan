# 实施计划：S10　审计哈希链加固（audit-log-chain-integrity）

> 以 design.md 为准，需求编号 I1~I9 见 design 页头。
> 通用纪律：临时产物（探针、日志、变异备份、验证 worktree）放仓库根 `tmp_audit_chain/`；迁移号实施时三路合扫取号；真 PG 写入一律在一次性库或回滚事务内，共享库只读；标完成须有代码 + 测试 + 至少一条磁盘变异（变异单独一条命令跑，跑完 sha256 逐字节核对）；提交前在干净 worktree 跑「要提交的那棵树」，失败集合与基线 HEAD 逐条对比，只候选红必须为 0；推送用 `.git-hooks/push_version.py`。
> 前置：母 spec `formula-hub-integrity-closure` 已入库（本 spec 只碰审计三文件与新包，不依赖其代码，但要以其入库后的 HEAD 为基线，避免与其整合树冲突）。
> 分两批交付：批 A（任务 1~3）只读与工具；用户执行分叉确认（任务 4）后才合入批 B（任务 5~9）。

## 批 A　只读校验与分叉工具

- [ ] 0. 现状复核与基线
  - 按 design §1 的口径重算 15 行（只读探针：链数、链尾数、分叉、断头、v1 不符、同链同 ts、索引；AST：41 处调用 / 吞异常 20 处 / 绕过写入 3 处 / 哈希副本 4 份；咨询锁取锁点），变化追加到 design §1 末尾
  - 三路合扫迁移号并记录；确认母 spec 已入库、记基线 HEAD
  - Verify: 探针输出存 `tmp_audit_chain/baseline/`；design §1 增补段落有日期与数字

- [ ] 1. 规范化、v2 哈希与按链接关系校验（I6、I7，ADR-04/05）
  - 新建 `audit_chain/canonical.py`、`audit_chain/verify.py`；`routers/audit_logs.py` 改调 `verify.py`（鉴权不变、旧字段保留、新增 `problems` / `legacy_*` / `anchor`）
  - `tests/test_audit_log_hash_chain_property.py` 改为调用 `verify.py`（hypothesis `max_examples=5`）
  - Verify: `tests/audit_chain/test_audit_chain_canonical.py`、`test_audit_chain_verify.py` 全绿；共享库只读跑一次校验，全局链报 1 处 `fork`、`legacy_unverifiable = 1`（v1 重算按 ADR-04 试两种 UUID 写法后只剩 `formula.changed` 那 1 行；或现算值）；另加一条用例：无连字符写法写入的 v1 行计 `legacy_verified`。变异：校验恢复首条任意采信 ⇒ `missing_prefix` 用例红；浮点不规范化 ⇒ `1e20` 用例红

- [ ] 2. 分叉扫描、确认工具与健康字段（I2、I4，ADR-03/10）
  - 新建 `audit_chain/forks.py`；脚本 `backend/scripts/ops/audit_chain_fork_ack.py`（默认只读演示，`--apply` 才写，`--operator` 校验 admin）、`backend/scripts/ops/audit_chain_heads.py`（默认只读）
  - `api/health.py` 增 `audit_chain`；隔离区计数先返回 0（批 B 才有隔离区）
  - Verify: 一次性库 PG 用例（造分叉 → 扫描报 1 → 前置校验不符拒绝并列出实际集合 → 确认后扫描报 0、确认条目 `prev_hash` = survivor 哈希）；健康端点在有未确认分叉时 `degraded`。变异：前置校验改为不比集合 ⇒ 拒绝用例红

- [ ] 3. 批 A 回归、提交与推送
  - 候选树 vs 基线 HEAD 全量后端失败集合对比；只读探针结果贴入本任务
  - Verify: 只候选红 = 0；推送带版本号与主要变动

- [ ] 4. 用户执行分叉确认（design §7 Y1）
  - 执行前 `audit_chain_fork_ack.py` 只读演示贴记录；用户放行后 `--apply`；执行后 `scan_forks` = 0、健康端点该项为 0
  - Verify: 两次扫描输出贴入本任务；未执行前批 B 不得合入

## 批 B　fail-closed 写入

- [ ] 5. 迁移、链尾表与写链内核（I1、I8，ADR-01/02）
  - `V{n}` / `R{n}`（链尾表 + 两个索引）；ORM `AuditChainHead`；`audit_chain/head.py`；`audit_log_helper.append_audit_log` 改薄封装、删 `_get_prev_hash` 与本地哈希函数；`append_audit_log_batch`
  - `MigrationRunner(...).run_pending()` 落本地库（与启动同一路径）
  - Verify: 三层一致用例；一次性库 PG：两会话并发同链 ⇒ 链长 2 且衔接、绕过写入 ⇒ `AuditChainBypassed`、多尾链 ⇒ `AuditChainForked`、确认后可续写；`test_audit_log_helper.py` 改写后全绿。变异：去掉 `lock_chain` ⇒ 并发用例红；读链尾异常改回创世 ⇒ fail-closed 用例红；去掉 `EXISTS` ⇒ 绕过用例红

- [ ] 6. worker 逐链事务与隔离区（I3，ADR-06）
  - `workers/audit_log_writer_worker.py`：每链一个事务调 `append_entry`、失败入 `audit:log:quarantine:<chain_key>`、重试上限后入隔离区不丢弃、每 30 轮重放、删 `hash(lock_key)` 与无锁降级；健康字段接入隔离区计数
  - `test_audit_log_enhanced.py` 的整对象替换 `settings` 改为只替换属性
  - Verify: 一次性库 + Redis 15 号库：两条链其一注入失败 ⇒ 另一条已提交、失败条目在隔离区且计数进健康字段；重放成功出列。变异：改回整批一个事务 ⇒ 隔离用例红

- [ ] 7. 绕过写入方收口（ADR-08，design §7 Y3）
  - `note_data_lock_service.unlock`、`wp_disclosure_sync_service._write_audit_log` 改调 helper；`role_workbench` 的 `confirm-warning` 按 Y3 删除或改调 helper；`audit_logger_enhanced._compute_entry_hash` 现读调用方后删除或改调 `canonical.hash_v1`
  - AST 守卫 `tests/audit_chain/test_audit_chain_writers_guard.py`（构造点白名单、SQL 文本禁写，带违规样本自检）
  - Verify: 解锁端点、HTML 附注同步端点各一条 TestClient 用例（回滚事务）写入成功且审计条目在链上。变异：守卫白名单加一个不存在的文件 ⇒ 守卫红

- [ ] 8. 调用方裁决（I9，ADR-07，design §5、§7 Y2）
  - `audit_chain/call_sites.py` 登记 41 处（实施时现算）；按裁决改 20 处吞异常调用点（`best_effort` 补 `begin_nested`，`mandatory` 去掉捕获）
  - AST 守卫 `test_audit_call_site_policy.py`
  - Verify: 守卫全绿；每类策略各一条端点级用例（mandatory 的审计失败 ⇒ 业务表不变且返回错误；best_effort 的审计失败 ⇒ 业务成功、计数 +1、事务未中止）。变异：守卫跳过 `mandatory` 形态检查 ⇒ 自检红

- [ ] 9. 锁顺序探测与存量违规（I5，ADR-09）
  - `audit_chain/lock_order.py` + conftest 设 `GT_AUDIT_LOCK_ORDER_STRICT=1`；以严格模式跑后端回归收集违规；能挪的把审计调用挪到事务末尾，挪不了的进白名单（理由 + 只许变短的断言）；多链写入改用 `append_audit_log_batch`
  - Verify: 探测器单测（构造违规 / 不违规语句序列）；回归中严格模式违规 = 白名单条数。变异：探测器不检查第二条链键顺序 ⇒ 用例红

- [ ] 10. 批 B 回归、验收与收尾
  - 合入前检查：共享库 `scan_forks` = 0 的输出（任务 4）；候选树 vs 基线 HEAD 失败集合对比；变异记录汇总（任务 1、2、5~9）；verify-chain 端点在共享库只读跑一次，记录 `valid` 与 `legacy_unverifiable`
  - 迁移落共享库与推送按 design §7 Y4（用户放行后执行）
  - INDEX.md 本行与 memory.md 任务状态更新
  - Verify: 只候选红 = 0；推送带版本号与主要变动
