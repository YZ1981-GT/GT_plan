# 任务清单：迁移完整性与枚举漂移收口

> 需求：#[[file:.kiro/specs/migration-integrity-and-enum-drift-closure/requirements.md]]
> 设计：#[[file:.kiro/specs/migration-integrity-and-enum-drift-closure/design.md]]
> 纪律：迁移号实施前重扫；真库写操作经迁移 runner 或显式脚本（postgres MCP 只读）；探针 `_` 前缀用完即删。

- [x] 1. V171 / R171 补齐 V128 缺失效果
  - [x] 1.1 重扫迁移号；写 V171 / R171（幂等）
    - 证据：扫描时最高 V170（V169/V170 为并行会话产物）→ 取 V171；全部语句 `IF EXISTS` / `CREATE OR REPLACE`；R171 先恢复首版触发器与函数再删新触发器，注释置 NULL，evgov 函数体不回退（design §一）
  - [x] 1.2 runner 执行；现查触发器绑定 / 函数体 / 表注释
    - 证据：runner 输出 `executed ['171'] failed []`；现查 `confirmation_action_log` 两个触发器绑到 `evgov_forbid_update/delete`，首版专用函数 0 个，两表注释与 V171 逐字一致；`schema_version` 中 V128 checksum 未动（仍为 `0727d53b…`）
  - [x] 1.3 真库用例：拒绝码 23514 / 23001 + 其余 evgov 表不变；删除两个 xfail 占位
    - 证据：`tests/test_migration_integrity_pg.py` 回滚事务内实测 UPDATE→23514、DELETE→23001（报文含表名）；V171 前同一探测为 P0001。其余 evgov：11 条绑定全部与事件匹配；有数据的 4 张表逐表实测码不变；6 张空表由「临时表绑定共享函数实测 23514/23001」兜底推出（design §六）
    - 证据：`confirmation_evidence/test_properties_pbt.py` 删除 `test_action_log_rejects_update/delete` 两个 `xfail + assert False` 占位，原位留指向真库用例的注释
  - _需求：1.1–1.5_

- [x] 2. 零语句迁移守卫
  - [x] 2.1 `EmptyMigrationError` + `_declares_noop`
    - 证据：`migration_runner._apply_migration` 分句后 0 条且注释无 `no-op` → 抛 `EmptyMigrationError`，走既有失败分支（记 `schema_migration_failures`、不写 `schema_version`）
  - [x] 2.2 SQLite 单测三例
    - 证据（实施调整：并入既有 `tests/test_migration_runner.py`，未新建文件）：纯注释 / 空白 / 空文件 3 种参数化被拒且未登记、补内容后成功；`no-op` 声明放行；真实 V001 仍声明 no-op。迁移套件 78 passed 2 skipped；变异 G1 4/4 RED
  - _需求：2.1–2.3_

- [x] 3. checksum 漂移登记 + 健康接线
  - [x] 3.1 `migration_drift_ledger.py`（7 条逐条结论）
    - 证据：V042/046/105/128/143/151/163 各记 stored / current 全长 checksum + 中文结论；按 `(version, stored, current)` 三元组比较；docstring 如实写明盲区（有人把登记值改写成当前 checksum 时无法与新库区分）
  - [x] 3.2 `CRITICAL_DRIFT_TYPES` 单一真源；scan 追加 `checksum_drift`；health / startup_registry 引用
    - 证据：`schema_drift_detector.CRITICAL_DRIFT_TYPES = {orm_extra, enum_mismatch, checksum_drift}` + `count_critical()`；`health._query_schema_drift`、`startup_registry._task_run_schema_drift_check` 改用之；`_diff_checksums` 扫描失败返回可见 critical 项（不 fail-open）；`schema_drift_log.drift_type` 为 VARCHAR(50) 且表上仅 PK 约束（现查）
    - 已知残留：`main._run_schema_drift_check`（真实启动路径）仍手写二元集合 —— main.py 有并发会话改动不触碰，`xfail(strict=True)` 钉住（design §七）；只影响启动日志的 critical 计数，health 判定正确
  - [x] 3.3 离线守卫 + 真库守卫（现场未解释为 0）
    - 证据：`tests/test_migration_drift_ledger.py` 18 例（current 与 runner 同一算法实算一致 / 三元组四种变体全判未解释 / 无重复版本 / V042 = sha256 空串）；真库现场原始漂移 7 条、未解释 0 条，比较确实发生（schema_version 与磁盘交集 >100）；变异 G2 / G8 / G9 / G10 / G11 全 RED
  - _需求：3.1–3.4_

- [x] 4. 枚举漂移按列检测
  - [x] 4.1 `collect_orm_enum_columns` / `diff_enum_columns` 纯函数；`_diff_enums` 改用之
    - 证据：期望标签取 `Enum.enums`、实际类型取 public 列的 `(data_type, udt_schema, udt_name)`、标签只取 public 的 `pg_enum`；`DriftItem` 填真实表列；`fetch_public_enum_catalog(conn)` 供真库守卫在回滚事务内复用；采集失败返回可见 critical 项
    - 实施中新发现（design §三补）：过滤名单原先作用于全部漂移类型，外部租户前缀 `notification` 吞掉 ORM 表 `notifications` 的全部发现 → `_apply_suppressions` 只作用于 db_extra 且外部租户前缀只作用于非 ORM 表；现场复扫 `notifications` 0 条（潜伏漏洞，未掩盖真实缺口）；变异 G7 / G12 RED
  - [x] 4.2 离线单测（三处旧缺陷 + 两个旧误报 + 两个真缺口）
    - 证据：`tests/test_enum_drift_columns.py` 11 例；另含真实 metadata 不变量「同一 PG 枚举类型的所有列声明同一套标签」（离线即可抓住真缺口 2 这一类）；变异 G3 / G4 RED
    - 现场核验：memory 所记「confirmation_risk_level_enum 缺 pass、workpaper_task_status_enum 缺 4 值」为旧实现比较 `.value` 的**误报** —— public 标签正是成员名 `pass_` / `PENDING…`
  - _需求：4.1–4.4_

- [x] 5. 两个模型修复
  - [x] 5.1 `GTWpCoding.wp_type` 非原生枚举；`WorkpaperReviewRecord.review_status` 用 `ReviewStatus`
    - 证据：`sa.Enum(GTWpType, name="gt_wp_type", native_enum=False, create_constraint=False, length=50)`；`Mapped[ReviewStatus]` + `Enum(ReviewStatus, name="review_status_enum")`；两处均零业务调用方改动（`gt_coding_service` 的 `.value` 分支不变）
  - [x] 5.2 真库回滚事务验证；现场 `_diff_enums` 为空
    - 证据：真库插入 + 按 wp_type 查询读回 `GTWpType:general`；`review_status=pending_review` 插入读回 `ReviewStatus:pending_review`；反向对照：原生 `gt_wp_type` 绑定 42704、`pending` 写共享枚举 22P02；现场 ORM 原生枚举列 117、枚举漂移 0；结束复查零残留（含 `tmp_migguard_*` schema 0 个）；变异 G5 / G6 RED
  - _需求：5.1–5.3_

- [x] 6. 验证
  - [x] 6.1 相关套件全绿、预存红归因
    - 证据：迁移 runner ×4 / 登记表 / 枚举 / 检测器 / 真库守卫 / health ×2 / startup_registry / gt_coding / custom_dsl_coding / confirmation_evidence / evgov capstone 合跑 315 passed 2 skipped 26 xfailed，2 failed 均在 `test_startup_registry.py`（`test_health_includes_startup_report` / `test_main_reexports_start_workers`）—— 改动文件全部换回 HEAD 复跑同样 2 红，预存（startup_registry 未接入 main）；另跑依赖 collaboration_models 的 3 个文件 107 passed
  - [x] 6.2 变异证明（design §六）
    - 证据：`_mig_mutation_check.py` 12 条（G1–G12）全部 RED，每条还原后 sha256 逐字节一致
  - [x] 6.3 INDEX.md 登记；探针删除
    - 证据：INDEX.md「一、Active Specs」表新增本 spec 一行（现扫 21/21）。探针清理 **15 个** `_mig_*`
      （`backend/scripts/diagnose/`，含 `_mig_mutation_check.py` / `_mig_live_scan*.py` / `_mig_snap_dump.py` /
      `_mig_m08_check.py` / `_mig_filter_probe.py` / `_mig_show.py` 与各自 `.txt` 输出）+ `__pycache__` 下同名 pyc
    - 🔴 删除前逐个核实 `git ls-files --error-unmatch`：92 个 `_` 前缀探针**全部未被 git 跟踪** ⇒ 删除零 git 影响。
      删后 `backend/scripts` 下 15 个 `D` 项经 `git log` 核实来自 commit `03f295427`（`_g_sibling_sheet_probe.py` /
      `_probe_f345_*.py` / `_gen_f_cycle_procedures.py` 等，分布在 `e2e`/`fix`/`gen`/`migrate`/`seed` 子目录），
      与本轮删除的文件名**零重叠**，属**预存删除**（并发会话或先前清理），不是本轮造成
    - 遗留（不越界处理）：`_kb_drift_history.py` / `_kb_enum_probe.py` / `_kb_evgov_codes.py` /
      `_kb_migration_probe.py` / `_kb_v128_history.py` / `_kb_drift_effects.py` 六个探针虽内容属本 spec
      （V128 / enum / evgov），但命名在 `_kb_*` 命名空间下，归 `knowledge-base-retrieval-and-authz-closure`
      的 Task 13.3 一并清理，避免两个 spec 交叉删同一批文件
  - _需求：6.1–6.2_
