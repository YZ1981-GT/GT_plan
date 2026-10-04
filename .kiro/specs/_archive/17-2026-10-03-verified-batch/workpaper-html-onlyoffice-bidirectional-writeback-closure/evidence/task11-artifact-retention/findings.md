# Task 11 交付：CanonicalArtifactRepository、安全校验、candidate 隔离、RetentionPolicy 与 orphan reconciliation

spec: `workpaper-html-onlyoffice-bidirectional-writeback-closure` Task 11
Requirements 2.4 / 3.4 / 5.6 / 5.7 / 5.8 / 5.9 / 5.11 / 9.6 / 9.7 / 10.7 / 10.8 / 14.11
Properties 5 / 17 / 42 / 60

**这是实现 + 守卫，不是探针。** Task 7 已把平台边界（Windows 占用、跨卷、目录 fsync、
DB rollback 不回滚文件）实测固化在 `backend/data/workpaper_staged_artifact_boundary_contract.json`；
本任务按那批事实实现生产代码，并把契约**当期望值来源**反向锁死实现。

## 一、新建文件清单

| 文件 | 内容 |
|---|---|
| `backend/data/workpaper_sync_limits.json` | Requirement 14.11 预算 + OOXML 安全策略的**唯一真源** |
| `backend/data/workpaper_sync_retention_policy.json` | 版本化 retention 策略（10 个 class，`workpaper-sync-retention:v1`） |
| `backend/app/services/workpaper_sync/limits.py` | 预算加载 + 六个纯预算门；缺配置**抛异常不 fallback** |
| `backend/app/services/workpaper_sync/ooxml_security.py` | 10 道有序 OOXML 安全门 + projection 行/field 预算 |
| `backend/app/services/workpaper_sync/artifacts.py` | `CanonicalArtifactRepository` + `OrphanReconciler` |
| `backend/app/services/workpaper_sync/retention.py` | `RetentionPolicyService`（dry-run / 二次引用复核 / 逐对象审计） |
| `backend/tests/workpaper_sync/test_task11_artifact_repository.py` | 47 例文件系统/安全/预算/candidate 守卫 |
| `backend/tests/workpaper_sync/test_task11_retention_orphan_pg.py` | 12 例真实 PostgreSQL 守卫（Property 5 / orphan / retention） |
| `backend/scripts/diagnose/mutate_task11_artifact_retention_guards.py` | 60 条变异 + 2 条对照 |
| `backend/scripts/diagnose/probe_task11_artifact_retention_observations.py` | 观测采集（只读，产出 `fs_observations.json`） |
| `backend/app/services/workpaper_sync/__init__.py` | **改动**：包 docstring 补 Task 11 四个模块 |

未改动任何既有生产代码，未新增迁移（V151 已覆盖全部表；删除审计以内容寻址 evidence
artifact 持久化，见 §五）。

## 二、Property 判定证据

| Property | 判据 | 测试文件::断言 |
|---|---|---|
| **Property 5**（staged artifact 与 DB pointer 不产生悬空可见态） | publish 之后注入 DB 失败（真实事务 + `RuntimeError`）⇒ pointer 仍指 gen 1、五表行数等于 baseline、**文件仍在且 sha256 不变**；随后 reconciliation 登记 orphan；GC 只在 grace 过后 + 二次确认零引用才删；全程 resolver 结果不变 | `test_task11_retention_orphan_pg.py::test_property_5_publish_then_db_rollback_leaves_invisible_orphan`（`pointer_unchanged` / `counts_equal_baseline` / `file_survived_db_rollback` / `file_sha_unchanged`）· `::test_orphan_reconciliation_registers_and_marks` · `::test_apply_deletes_only_after_unreferenced_and_writes_audit`（`pointer_after.generation == 1`） |
| **Property 17**（callback 文件先隔离校验） | 9 类恶意/不合规 incoming 全部只能落 `quarantined` 且 `durable_at IS NULL`；合法 incoming 只能 `durable`；`release_quarantined` / `promote_incoming_to_published` 恒抛；quarantined 只允许 authorization-first download-only；zip bomb 展开越界即中止且内存受界 | `test_task11_artifact_repository.py::test_property_17_malicious_incoming_is_quarantined_never_durable`（9 个 parametrize）· `::test_property_17_incoming_sealing_is_delivery_scoped_and_durable` · `::test_property_17_quarantine_is_permanent_and_download_only` · `::test_property_17_zip_bomb_is_quarantined_with_bounded_memory`（`peak < peak_memory_budget_bytes`）· `::test_authorization_precedes_any_resource_read` |
| **Property 42**（路径安全） | 契约 `path_safety.must_reject` 的 **8 类**逃逸逐条被 `ArtifactPathError` 拒（含**真建的软链接**）；`inside_ok` 被接受；同一相对路径在两个 project 根下解析到不同绝对路径；hypothesis 随机拼接路径「要么在根内、要么被拒，无第三种」 | `test_task11_artifact_repository.py::test_contract_path_safety_cases_all_rejected`（用例集与契约 `must_reject` **相等**才通过）· `::test_property_42_resolution_never_escapes_project_root` |
| **Property 60**（大文件预算 fail visible） | 六个预算逐个做 N-1 / N / N+1；entry 数用**生产数字 20000** 端到端；行/field 用生产数字 100000 / 200000 并经真实 projection 结构；压缩/展开/压缩比在纯门用生产数字 + 缩放预算下的端到端；staging 阶段越界即中止且不留半成品；生产代码零预算字面量 | `test_task11_artifact_repository.py::test_property_60_scalar_budget_boundaries`（3 参数）· `::test_property_60_compression_ratio_boundaries` · `::test_property_60_table_rows_and_projection_fields_boundaries` · `::test_property_60_zip_entry_boundaries_end_to_end` · `::test_property_60_streaming_stage_aborts_at_cap_without_partial_residue` · `::test_property_60_expanded_and_ratio_gates_end_to_end` · `::test_budgets_have_no_second_source_in_production_code` · `::test_limits_config_matches_requirement_14_11_exactly` |

## 三、Requirement 14.11 的实测结果

预算真源 `backend/data/workpaper_sync_limits.json`，六项与 AC 逐条相等（守卫
`test_limits_config_matches_requirement_14_11_exactly` 锁死）：

| 预算 | 值 | N-1 | N | N+1 |
|---|---|---|---|---|
| 压缩 OOXML | 52428800（50 MiB） | accepted | accepted | rejected |
| 展开总量 | 536870912（512 MiB） | accepted | accepted | rejected |
| ZIP entries | 20000 | accepted | accepted | rejected |
| 压缩比 | 100 | accepted | accepted | rejected |
| 单表行数 | 100000 | accepted | accepted | rejected |
| 单 projection fields | 200000 | accepted | accepted | rejected |

**OOXML 安全校验实测**（`fs_observations.json` → `ooxml_gates.observed_rejections`）：

| 注入 | 拒绝门 | error_code |
|---|---|---|
| 非 ZIP（`<html/>`） | `zip_magic` | `ooxml_structure_invalid` |
| **polyglot**（前置 `MZ` stub 的自解压包） | `zip_magic` | `ooxml_structure_invalid` |
| 扩展名伪装（xlsx 字节声明 docx） | `document_type` | `ooxml_structure_invalid` |
| 缺 `[Content_Types].xml` | `required_parts` | `ooxml_structure_invalid` |
| entry 名 `../evil.xml` | `entry_names` | `ooxml_security_rejected` |
| entry 名 `/etc/passwd` | `entry_names` | `ooxml_security_rejected` |
| 宏 `xl/vbaProject.bin` | `macros` | `ooxml_security_rejected` |
| 外部关系 `TargetMode="External"` | `external_relationships` | `ooxml_security_rejected` |
| 嵌入对象 `xl/embeddings/*` | `embedded_objects` | `ooxml_security_rejected` |
| zip bomb（声明 64 MiB，cap 8 MiB） | `max_expanded_bytes` | `capacity_budget_exceeded` |

门顺序实测 = `zip_magic → entry_names → zip_entries → compressed_size → expanded_size →
required_parts → document_type → external_relationships → macros → embedded_objects`，
且守卫用**双门同时超限**的输入证明顺序（报出的必须是更早那个）。

**内存受界实测**：声明 64 MiB 展开、cap 8 MiB ⇒ `tracemalloc` 峰值 **969318 字节**
（< 预算 16777216）。把 `src.read(chunk)` 改成 `src.read()` 的变异（M17）会让峰值突破预算
并被守卫抓到 —— 这是唯一能证明「流式」本身的判据。

## 四、Windows 边界与 Task 7 契约的一致性

| 契约字段 | 实现行为 | 实测 |
|---|---|---|
| `diagnostic_mapping.target_occupied` | `FILE_IN_USE`, `held='target'` | winerror **5**，旧内容完好 |
| `diagnostic_mapping.source_occupied` | `FILE_IN_USE`, `held='source'` | winerror **32** |
| `diagnostic_mapping.cross_volume` | `CROSS_VOLUME_RENAME` | winerror **17**，源存留、目标不存在 |
| 其他 IO 错误 | `PUBLISH_IO_ERROR` | winerror 1224 → 不误诊成上面两类 |
| `staging.directory_fsync.supported_on_windows = false` | 只对**文件** `os.fsync`；`StagedArtifact.directory_fsync_performed` 恒 False | `os.open(dir)` → `PermissionError`（stage=`open`） |
| `publish.content_addressed.target_name_pattern` | `{generation:09d}-{sha12}{ext}` | `000000007-<sha12>.xlsx` |
| `publish.content_addressed.idempotency_scope = path_and_sha256` | 目标已存在且内容相同 ⇒ **不执行 replace**，`reused=True` | 重复 publish 同路径同 sha；且**目标被占用时仍成功**（不走 replace） |
| 跨卷必须 fail visible | `publish_*` 先判同卷并抛 `CrossVolumeError`；`atomic_replace` 另按真实 OSError 归类 | 两条路径各有独立判据（前置校验 + EXDEV 归类） |
| `db_boundary.resolver_exclusion` | `assert_canonical_resolvable` 只放行 `state=published` 且 `kind∈{canonical,projection}` | candidate / incoming(durable) / incoming(quarantined) / orphan 各自专属 error_code；V151 trigger 是第二道锁（pgcode 23514） |

## 五、RetentionPolicy 的 dry-run 与二次引用检查覆盖

策略 `workpaper-sync-retention:v1`，10 个 class（`default` / `orphan_canonical` /
`incoming_durable` / `incoming_quarantined` / `upgrade_candidate` / `trace_bundle` /
`evidence_manifest` / `retention_audit` / `definition` / `staging_temp`），逐 class 声明
敏感级别、TTL、grace、`age_anchor`、`deletable`、`honor_legal_hold`、
`requires_orphaned_at` 与 `access_roles`（Requirement 10.7 最小权限）。

**判定顺序即语义顺序**，逐档都有独立 reason 与真实场景覆盖：

| 分支 | reason | 告警 | 覆盖场景 |
|---|---|---|---|
| 无策略 | `no_policy_retain_and_alert` | ✅ | `retention_class='bogus_class'` |
| class 与 kind/state 不匹配 | `class_scope_mismatch` | ✅ | `orphan_canonical` 类但 state=published |
| 法务冻结 | `legal_hold` | — | `legal_hold=true` |
| 类不可删 | `class_not_deletable` | — | `definition` 类（无 legal hold ⇒ 该分支可达） |
| orphan 无 `orphaned_at` | `orphaned_at_missing` | ✅ | state=orphan 但未对账 |
| anchor 时间戳缺失 | `age_anchor_missing` | ✅ | 声明分支（策略校验保证 anchor 合法） |
| TTL 未到 | `ttl_not_elapsed` | — | 刚对账出的 orphan |
| **TTL 已过、grace 未过** | `grace_not_elapsed` | — | backdate 到 `ttl+grace/2` |
| in-flight operation | `in_flight_operation` | ✅ | `created_by_operation_id` 指向 `state='merging'` |
| dry-run 阶段发现引用 | `reference_found_on_plan` | — | — |
| **apply 二次复核发现引用** | `reference_found_on_recheck` | ✅ | plan 之后插入 `definition_artifact.blob_artifact_id` 引用 |
| 复核时状态已变 | `state_changed_on_recheck` | ✅ | 声明分支 |
| 删除失败（占用/路径） | `delete_failed` | ✅ | 声明分支 |
| 通过 | `delete` / `grace_elapsed_and_unreferenced` | — | 移除引用后真删 |

**二次引用检查的完整性由「声明清单 ↔ V151 DDL 双向比对」保证**：
`REFERENCE_SOURCES` 登记 **12** 条引用来源（10 张表 12 列），守卫
`test_reference_sources_match_v151_ddl_bidirectionally` 从迁移文本反向抓出所有引用
`working_paper_artifact(id)` 的列并要求集合**相等**。将来新迁移加了 FK 而忘了登记，
CI 立刻红 —— 而不是等到某天 GC 把还在用的文件删掉。

`references_of()` **逐表一条 SQL 并逐条记名**（不写大 UNION：命中哪张表必须进审计），
且**不设 `except Exception`** —— 表名/列名拼错会直接 `ProgrammingError`。守卫
`test_reference_sources_all_execute_against_real_schema` 用真实 schema 跑一次全部 12 条，
证明它们都是有效 SQL 而不是静默 0 行。

**审计持久化**：每轮判定（dry-run 与 apply 各一份）序列化成 JSON 并以
`retention_class='retention_audit'` + `legal_hold=true` **内容寻址不可变发布**；
`retention_audit` 类 `deletable=false`，形成自证闭环（否则下一轮 GC 会抹掉上一轮的删除记录）。
未新增迁移的理由：V151 已有 `working_paper_artifact`，审计作为 evidence artifact 落在
`.evidence/_retention/{run_id}/evidence-{sha12}.json`，内容寻址即防篡改，且 `dry_run`
真假各留一份（Requirement 5.11「dry-run 和删除清单均持久化」）。

## 六、变异检验四态统计

| 轮次 | RED | GREEN | ANCHOR-MISS | WRONG-TEST | 备注 |
|---|---|---|---|---|---|
| 锚点自检（`--check-anchors`） | — | — | 3 → **0** | — | 3 条缩进/offset 写错，修正后 59/59 OK |
| 首轮 `--run all`（59 条） | 55 | **2** | 0 | **2** | 逐条归因见下 |
| 复测 `--run all`（60 条） | **60** | **0** | **0** | **0** | 报告：`mutation_report.json` |
| 对照项（预期 GREEN） | — | 2 | — | — | 报告：`mutation_controls.json` |

还原核验：每条变异 `restored=True`；跑完无 `.mutbak` 残留；`--check-anchors` 只读性
核验（目标文件 md5 全未变）通过。覆盖面：2/2 个登记守卫文件都被至少一条变异打红。

### 首轮 2 条 WRONG-TEST：脚本缺陷（不是守卫缺陷）

**M36 / M37** 把多行 `raise X(` 的首行换成 `return None`，续行的字符串拼接随即变成缩进
错误 ⇒ 整文件 collect error ⇒ pytest 报的是**文件级** ERROR（不带 `::test_name`），
`want` 匹配不到。改成 `_ = (` 后续行原样成为括号内表达式，语法合法、行为归零 ⇒ 两条均 RED。

> 教训：变异必须保持语法合法。「整行替换成语义相反但合法的表达式」这条纪律对
> **多行语句的首行**尤其重要 —— 首行替换会连带破坏续行。

### 首轮 2 条 GREEN：两个真实守卫缺陷（已修，均非降标）

**M46**（去掉 grace 判定 → GREEN）：采集里 orphan 的 `orphaned_at` 就是对账那一刻，
age≈0 ⇒ **TTL 门先短路**，grace 门从未被执行。也就是说 grace 窗口根本没被测到。
→ 补场景 C2：backdate 到 `ttl + grace/2`，断言 `reason == 'grace_not_elapsed'`；
并把场景 C 的断言从「ttl 或 grace 二者之一」收紧成 `'ttl_not_elapsed' in reasons`。复测 RED。

**M58**（不再标记「published 但无引用」的 orphan → GREEN）：采集里所有 published
artifact 都被 representation / content_version 引用，Task 7 db4 的**形态二**在本采集里
不存在 ⇒ `OrphanReconciler` 的标记分支从未执行。
→ 补前置：单独提交一个无任何引用的 published canonical artifact（就是「artifact row 先
提交、pointer 事务失败」的真实形态），断言 `marked` 命中它。复测 RED。

**追查 M58 时发现的生产缺陷（已修）**：标记 orphan 只改 `state`/`orphaned_at`，
`retention_class` 仍是 `default`，而 `default.applies_to_states` 只含 `published`
⇒ 这批 orphan 会被 RetentionPolicy 永久判 `class_scope_mismatch`（保留 + 告警）：
**既回收不了、又持续刷屏**。修法是标记时同步 `retention_class='orphan_canonical'`，
并新增变异 **M60** 锁死该行为。

### 对照项（自证判定不是字符串匹配）

| id | 变异 | 判定 | 期望 |
|---|---|---|---|
| C01 | 只改预算超限的错误文案 | GREEN | GREEN |
| C02 | 只改一行注释 | GREEN | GREEN |

两条都 GREEN ⇒ 守卫判据是**行为/结构**，没有任何一条在断言错误文案或源码注释。
（对照项刻意不进 `--run all`：一条故意的 GREEN 会让 `run_cli` 退出码恒非零。
运行方式见 `mutation_controls.json` 的产出脚本说明。）

## 七、守卫运行结果

| 文件 | 结果 |
|---|---|
| `test_task11_artifact_repository.py` | **47 passed** (3.3s) |
| `test_task11_retention_orphan_pg.py` | **12 passed** (8.0s) |
| 合计 | **59 passed** (10.9s) |

辐射面复核（按引用关系反查，不跑全量 1500+ 文件）：
`backend/tests/workpaper_sync`（5 文件）+ Wave 0 的 3 个 workpaper_sync 契约守卫 +
4 个 mutation-kit 治理守卫 = **273 passed / 2 failed**。两条失败均为**既有状态**，
与本任务改动无关：

1. `test_mutation_kit_adoption.py::test_new_scripts_must_use_the_shared_kit` —— 违规名单里
   **不含**本任务脚本（本脚本走 `_mutation_kit.run_cli`），列出的 14 个是既有
   `check/` 与其他 task 的脚本。
2. `test_mutation_kit_scripts_tracked.py::test_every_mutation_script_is_tracked_or_exempt` ——
   9 个变异脚本 `??` 未跟踪，其中 8 个属于本 spec 的其他 task。本任务的
   `mutate_task11_artifact_retention_guards.py` 也在其中 ⇒ **收口时必须 `git add`**
   （见 §八）。

## 八、产物入库状态（`git status --porcelain`）

```
?? backend/app/services/workpaper_sync/            （目录整体未跟踪：含 Task 10 的 models/repository 与本任务 4 个模块）
?? backend/tests/workpaper_sync/                   （目录整体未跟踪：含 Task 10 的 2 个守卫与本任务 2 个守卫）
?? backend/data/workpaper_sync_limits.json
?? backend/data/workpaper_sync_retention_policy.json
?? backend/scripts/diagnose/mutate_task11_artifact_retention_guards.py
?? backend/scripts/diagnose/probe_task11_artifact_retention_observations.py
?? .kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/
```

🔴 **全部 Task 11 产物均为 `??` 未跟踪**（与本 spec 其他 task 同状态）。两条后果：
① `test_mutation_kit_scripts_tracked` 在干净 checkout 下必挂；② 丢工作树即全部蒸发。
本任务未擅自 `git add`（工作树有并发会话在途，且 commit 由收口方决定），请在收口时
把上述清单一并入库。

## 九、明确未覆盖项（不标成功）

| 项 | 状态 | 阻塞点 | 替代证据 |
|---|---|---|---|
| 压缩 50 MiB / 展开 512 MiB 的**端到端** N-1/N/N+1 | 只做纯门边界 + 缩放预算的端到端 | GiB 级 IO 会让守卫从 10s 变成分钟级 | 纯门用生产数字做三点边界；端到端用缩放预算证明**同一条门**真的被调用（M15/M16 变异证明调用点存在） |
| `os.replace` 自身被中断的半成品 | 未独立注入 | 单次 `MoveFileExW` 元数据调用，用户态无法注入中断点 | 沿用 Task 7 fs3 的 5315 次 size 采样 + 968 次 content 采样（中间态 0） |
| 杀毒软件扫描导致的 rename 冲突 | 未注入 | 无法确定性触发 AV 扫描窗口 | Task 7 fs5 已证明任意进程持句柄即 WinError 5，AV 属同一失败模式同一诊断码 |
| `state_changed_on_recheck` / `age_anchor_missing` / `delete_failed` 三条 reason | 只有声明分支，无行为场景 | 分别需要「plan 与 apply 之间人为改 state」「策略允许非法 anchor」「文件被占用时删除」三种构造 | 三条都在 `alert_retain_reasons` 里且落在同一 `_retain()` 路径上；其余 10 条 reason 有真实场景覆盖 |
| `RepresentationService.finalize_candidate()` 的 DB 侧 finalize | 超出 Task 11 | 由 Task 12/15 承接 | 本任务只交付**文件系统侧** `finalize_candidate_artifact()`（复制 + 前后 digest 校验），并证明 candidate 永不进 resolver 命名空间 |

## 十、文件清单（evidence）

| 文件 | 内容 |
|---|---|
| `findings.md` | 本文件 |
| `fs_observations.json` | 文件系统/安全/预算/路径/definition store/retention 策略的原始观测（每字段注明由哪条测试重算） |
| `guard_run.json` | 两个守卫文件与合并运行的摘要、退出码、耗时 |
| `mutation_report.json` | 60 条变异的四态结果 |
| `mutation_controls.json` | 2 条对照项（预期 GREEN）结果 |
