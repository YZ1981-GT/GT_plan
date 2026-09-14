# Task 30 关门证据：durable protocol / application / close exactly-one / recovery

spec: `workpaper-html-onlyoffice-bidirectional-writeback-closure` · Wave 2 Task 30

## 结论（先说判定）

**本门通过**（2026-08-29 spec 修订后的判定；修订前为「不过」，见下节）。

本门原本唯一未满足的准则是 `多 resolver writer=0`（gate issue key `multi_resolver`）。本门在
活体库上实测证明它在**本门这个位置**不可满足（供给只能来自 Task 36，而 Task 36 依赖本门 ——
与「Task 20 → Task 30」同形的第二次成环），故经用户批准，该 criterion 的**裁决归属**已再次
移交 **Task 71**（`legacy_delete` gate 成员）。本门其余准则均已独立验证通过 ⇒ 判定翻为
**通过**。

`multi_resolver` 的计数本身**没有**变化，也没有被从门里摘掉：

| | 修订前 | 修订后 |
|---|---|---|
| `check_workpaper_writer_revision_gate.py` 的 `multi_resolver` 计数 | **4** | **4** |
| 门总阻塞事实 | **917** | **917** |
| 门退出码 | `1` `[BLOCKED]` | `1` `[BLOCKED]` |
| 该 criterion 的裁决归属 | Task 30 | **Task 71** |

四条行在 Task 12 resolver 矩阵里的状态（`group=oo_room`，`--check` OK、`regressed=0`）。
`blocking_task`（真实供给阻塞）与 `adjudication_owner_task`（裁决归属）是**两个独立字段**：

| 行 | 矩阵 status | blocking_task | adjudication_owner_task | resolver 身份 |
|---|---|---|---|---|
| `get_sheet_onlyoffice_config` | `deferred` | `21,25,26,36` | `71` | `_resolve_custom_wp_file` / `_resolve_wp_file` / `find_template_file_any` |
| `get_sheet_wopi_contents` | `deferred` | `21,25,26,36` | `71` | 同上 |
| `get_whole_excel_grid` | `deferred` | `21,25,26,36` | `71` | `_resolve_wp_file` / `find_template_file_any` |
| `post_sheet_onlyoffice_callback` | `deferred` | `21,25,26,36` | `71` | `_onlyoffice_storage_dir` / `_resolve_custom_wp_file` |

本门的其余边界不变：Task 4–7 的真实 OO probe 文档**未**被当作已通过（本门的集成半用可编程
Command transport，真实 OO 9.4 属 Task 44/70）。前端/engine pilot 的放行由本门通过后的
Wave 3 依赖边承担，`bulk_adapters` gate `["20","30","44"]` 仍因 **Task 20 未过**（236
`unadjudicated_writer` + 261 `bypasses_unified_commit`）与 Task 44 未执行而不放行 —— 这与本
criterion 无关，见下节。

## 为什么 `multi_resolver` 迁不了零（四条前提，逐条可核）

1. **判据形态**：`multi_resolver` = 一个函数体内抵达 ≥2 个 legacy resolver 符号
   （`generate_workpaper_writer_inventory._RESOLVER_SYMBOLS`，9 个）。所以只要「哪个文件
   是权威」这件事仍需组合模板查找 + OO 缓存 + custom 业务文件三者，就必有一个函数是
   multi。把组合搬进 helper 只是把这一行**换个位置**（生成器扫 `backend/app` 全域）；
   把 helper 改名到符号集之外则是**绕判据**，本门不做。
2. **替代 substrate 的准入条件**：design「现有 `wp_onlyoffice_router.py` 保留 URL 兼容，
   但逻辑下沉」一节明确统一 resolver **只接受 published representation + approved
   non-null bundle**。源码侧两条实证（`test_task30_closure_gate.py::
   test_the_unified_resolver_really_requires_a_published_approved_substrate` 锁死）：
   `WorkpaperSyncRepository.create_representation` 必过 `assert_bundle_usable`；
   `materialize_coordinator` 为「无 published substrate」保留并真的 `raise`
   `SubstrateNotPublishedError`。
3. **实测供给为零**（活体库，只读查询）：`working_paper_content_representation` /
   `working_paper_content_version` / `working_paper_sync_definition_bundle` /
   `working_paper_oo_room` / `working_paper_sync_entry_state` **全部 0 行**，而
   `working_paper` 有 **2806** 条存活底稿；`backend/data/workpaper_sync_contracts/` 下只有
   `_example.candidate.json`（零份 approved per-entry contract）；
   `workpaper_sync_legacy_baseline.json` 记 186 个 entry 中 **142** 个 `missing_adapter`。
4. **供给由 Wave 3/4 产生**：published representation 只能由 Task 36 的
   `finalizeCandidate(entry)` 在**逐 entry**人工审核并发布 approved contract + authority
   model + non-null bundle 之后生成（Task 36 正文明写「不得复用其他 pilot 的 contract /
   bundle / candidate」）。而 Task 36 属 Wave 3，本门正是它的前置门。

⇒ 今天把这 4 条改成「只经 substrate 取数」= 2806 份底稿的 OO 入口全部 fail closed；
保留 legacy 回退 = `multi_resolver ≥ 1`。**这是与「Task 20 → Task 30」同形的第二次成环**，
其真实阻塞不是 Task 25/26（已落地）而是 **Task 36**，而 Task 36 依赖本门 ⇒ criterion 留在
本门永远归不了零。该结论已写进 Task 12 矩阵 POLICY 的 `blocking_task` / `reason`（源码派生 +
digest 锁死），并由三条判据守住：

* `test_the_criterion_is_either_cleared_or_its_blocker_is_registered` —— **双条件式**：
  计数非零 ⇔ 那些行仍登记 `deferred` 且写明阻塞。刻意**不**写 `assert count == 4`，
  否则真清零那天守卫会反过来拦人（把缺陷冻成基线）；写成双条件式则相反：清零那天它
  强制把 deferral 登记一并撤销。
* `test_the_registered_blocker_points_at_a_task_that_really_gates_publication` ——
  `blocking_task` 里必须有一个任务号，其 tasks.md 正文真的承担 approved per-entry
  contract + candidate finalize 这道发布门。
* `test_recomputation_and_the_gate_agree_on_the_multi_resolver_rows` —— 门的报告 ×
  本文件**独立**的 AST 重算，双向比对（两条推导链）。

## 交接措辞与门行为的矛盾（本门负责的登记）

tasks.md Task 20 原文写「**故本门不再评估该 criterion**」，而门**仍**把 `multi_resolver`
计入 `has_debt`。已按事实改 tasks.md（未改门）：移交的是**裁决归属**，不是把它从门里摘掉
—— 删掉计算与「归零」在报告里逐字相同（fail-open），而归属方正是靠这个计数验零。
故 Task 20 在该 criterion 上同样保持红，这与「Task 20 本就因 236 `unadjudicated_writer` +
261 `bypasses_unified_commit` 而红」不冲突。改动后 `test_task20_writer_gate.py` 32/32 仍绿
（它的归属判据从 tasks.md 现场解析，措辞与表分组一旦不一致就红）。

**本门的任何产物都不把平台表述成 writer-clean**：门总阻塞事实 **917**（`multi_resolver` 4
+ `unadjudicated_writer` 236 + `bypasses_unified_commit` 261 + …），见
`writer_gate_after.txt`（修订后复测同值，见 `writer_gate_after_relocation.txt`）。

## 2026-08-29 spec 修订：裁决归属第二跳 Task 30 → Task 71（用户批准）

`多 resolver writer=0` 在本门位置不可满足（上一节四条前提，其中第 4 条的 Task 36 **依赖本
门**），故 criterion 的裁决归属移交 Task 71，本门判定翻为**通过**。移交链因此是
**Task 20 → Task 30 → Task 71**，三跳都在 tasks.md 留了显式交接语，判据从文档现场派生。

### 为什么是 Task 71，以及为什么这一跳不会造出新环

* Task 71 在依赖图里 `"71": ["7","8","30","44","61","68","69","70"]` —— **本就依赖 Task 30**，
  归属往「已经依赖放手方」的任务移，方向上不可能成环（已用依赖图拓扑排序复核：73 个节点全部
  排出，环余项 0；越 wave 反向边 0）。
* Task 71 是 `legacy_delete` gate `["67","68","69","70","71"]` 成员，而 criterion 真正能归零的
  时点正是「每个 entry 都已有 published representation」= legacy 回退可删的时点。归属与它把守
  的门在语义上对齐（真正执行删除的是 Task 72，它依赖 71）。

### 🔴 `bulk_adapters` 的成环风险：措辞被**丢掉**，不是被搬走

本门原文那句「任一行仍 `deferred` 或计数非零则本门不过，`bulk_adapters` gate 亦不得放行 bulk
adapter 迁移」**不能**原样搬到 Task 71：`bulk_adapters = ["20","30","44"]`，而 bulk adapter
迁移是 Wave 5（Task 46–57）。归属在 Wave 7 却继续挂 `bulk_adapters` ⇒ **Wave 5 依赖 Wave 7**，
与它要修的那个环同形。

处置：**丢掉该 linkage，并把理由写进 Task 71 的 clause 本身**（bulk adapter 不能等在排在它
之后的全局 legacy 删除上）。Task 20 正文末尾那句「放行保护由 `bulk_adapters` gate 中的
Task 30 承担」在第二跳后变成**假陈述**（Task 30 不再因这 4 行而红），故一并改写为第二跳的
追述 + 「本 criterion 自此不挂 `bulk_adapters`」—— 这是本次的第三处 tasks.md 改动，不是静默
携带。`bulk_adapters` 的放行仍由 Task 20/30/44 各自的其余准则把守（Task 20 今天就因 236 + 261
而红）。

移交方向的安全性不靠这段散文：`test_task30_closure_gate.py::
test_relocating_the_criterion_did_not_invert_the_wave_order` 按 tasks.md 的依赖图 JSON 断言
「归属 ∈ `legacy_delete`」「归属 ∉ `bulk_adapters`」「wave(归属) > wave(bulk adapter lane)」
「放手方仍 ∈ `bulk_adapters`」「归属任务依赖放手方」五条，M32 变异（把 `"71"` 加进
`bulk_adapters`）实测 **RED** 且只打红这一条。

### 矩阵登记形状：两个字段，不合并

Task 12 矩阵的 8 条 `oo_room` 行现在带两个独立字段：

* `blocking_task` = `"21,25,26,36"` —— **不变**。它回答「什么不落地这几行就迁不了」，而
  `test_the_registered_blocker_points_at_a_task_that_really_gates_publication` 要求其中至少一个
  任务的正文真的承担 approved per-entry contract + candidate finalize 那道发布门（Task 36）。
* `adjudication_owner_task` = `"71"` —— **新增**。它回答「哪一道门的验收卡在这条 criterion 上」。

合并成一个字段会让上面那条判据指向 Task 71，而 Task 71 不是发布门 ⇒ 判据当场失去意义。故
判据额外断言 `adjudication_owner_task != blocking_task`。新字段不是 additive 死代码：
`test_the_criterion_is_either_cleared_or_its_blocker_is_registered` 把它与 tasks.md 派生的归属
双向锁死，M31 变异（把登记改回 `"30"`）实测 **RED** 且只打红这一条。

### 守卫「换归属，不换在场」——两条关键性质如何保住

判据**留在原文件**（`test_task30_closure_gate.py` §1 / `test_task20_writer_gate.py` §6），形态
照抄第一跳：`test_task20_writer_gate.py` §6 至今持有归属 Task 30 的那条 criterion。放手方留下
可跑的守卫而不是一句承诺；Task 71 尚未开工，此刻新建 `test_task71_*.py` 只会让判据无人维护。
文件名记的是**作者**，归属由 tasks.md 现场派生。

| 性质 | 怎么保住的 |
|---|---|
| **双条件式**（不是 `assert count == 4`） | `test_the_criterion_is_either_cleared_or_its_blocker_is_registered` 原样保留：`计数非零 ⇔ 那些行仍登记 deferred`。归零那天它强制**撤销登记**而不是拦人。新增的 `adjudication_owner_task` 断言在同一分支内，`reported` 为空时直接 `return`，故清零后也不会反过来打红 |
| **行为级**（不是「键是否存在」） | `test_the_gate_still_counts_the_criterion_its_owner_verifies_zero_with` 与 `test_the_gate_still_evaluates_the_relocated_criterion` 都仍然**真喂一条合成的多 resolver 行**进门看它被点名，并用单 resolver 行证明判据不恒真。M24（门内短路成 `if False`）与 Task 20 侧 M15 实测均 **RED** |

归属号一律**派生不硬写**：`_criterion_owner_task()` 只认 `自 Task M 移交至本门`（接手）与
`已移交 Task N`（放手），且要求接手方**恰一个**。移交链由放手/接手事件的文档顺序拼出
（`relinquished == ["20","30"]` / `assumed == ["71"]`）—— 原实现是单值 dict，第二跳会把第一跳
**静默覆盖**掉，于是「为什么它不在 Task 20」下一轮又要从头推导。另加一条：放手方不得同时留着
待清行名单（移交被写成复制 ⇒ 文档里有两个归属答案，而两处各自都能解析成功）。

### 修订后的复测

| 项 | 结果 |
|---|---|
| `check_workpaper_writer_revision_gate.py` | `multi_resolver=4`、总阻塞事实 **917**、`[BLOCKED]` RC=1（与修订前逐项同值，见 `writer_gate_after_relocation.txt`） |
| `generate_workpaper_resolver_migration_matrix.py --check` | OK：79 行 / 13 migrated / 66 deferred / **regressed 0**；`stats` 逐字段未变，仅 `matrix_digest` 变 |
| 变异 M24 / M25 / M31 / M32 | 全 **RED**，各自命中**预测的**那条判据，`restored=True` 且 `restored_sha256` == 磁盘当前 sha256（`mutation_batch6_relocation.json`） |
| 变异 M29（对照，`expect_green`） | `added=[]` / `hit=[]` ⇒ 对照成立（tally 里显示 `RED` 是 `expect_green` 的 GREEN→RED 映射，判据看 `added`/`hit`，`mutation_batch6_control.json`） |
| 变异 Task 20 侧 M15 | **RED**，命中改名后的两条（`mutation_task20_m15_after_relocation.json`） |
| 锚点自检 | Task 30 侧 **32/32 OK**（新增 M31/M32）、Task 20 侧 **20/20 OK**，只读性核验通过，无 `*.mutbak` 残留 |
| 回归 | `test_task30_closure_gate{,_pg}.py` + `test_task20_writer_gate.py` + `test_task12_canonical_resolver.py` + `test_task14_merge_conflicts.py` + `test_task28_sync_router.py` + `test_task29_timeline_evidence.py` + `test_workpaper_ac_coverage_matrix.py` + `test_workpaper_writer_inventory.py` + `test_workpaper_staged_artifact_boundary_contract.py` ⇒ **700 passed / 0 failed** |
| 变异基线 | 逐文件实测 10 + 39 + 97 + 90 + 88 = **324**。与上一轮同值**不是**没变：本轮 +1（离线文件 9 → 10），task21/22/24 侧被并发会话 −1，恰好相抵；冻结基线已从 322 改为 324 并在脚本里写明来源 |

### AC 覆盖矩阵重生成的逐字段 diff（含一处**不是本次引入**的漂移）

改 tasks.md 必使 `workpaper_ac_coverage_matrix.json` 陈旧，已 `--apply` 重生成。逐字段 diff：

* **移动**：`sources[tasks.md]`（bytes 113696 → 116317、lines 643 → 644、sha256 变）、派生
  `facts_digest`、`matrix_digest`；`tasks` 里两处 —— `72.tasks_line 636 → 637`（插入一行的机械
  后果）与 **`29.state "-" → "x"`**。
* **未动**：`acceptance_criteria` / `properties` / `oracle_families` / `evidence_classes` /
  `duplicate_family_coverage` / `stale_references` / `overlay_digest` / `stats` **全部逐字节相等**
  —— `ac=170 property=72 task=73 family=14 clean_ac=69`、
  `defects={'no_dependency_edge': 1, 'no_property_oracle': 101, 'self_certified_single_task': 8}`、
  `stale_reference_count=0`。Task 8 的 `no_property_oracle=101` 既未吸收也未恶化。
* 🔴 **`29.state` 那一处不是本次改动引入的**：磁盘上那份矩阵记的 tasks.md sha256 是
  `b91b5b1e…`，而本次动手**之前**实测的 tasks.md sha256 是 `63639ab8…`，两者 bytes/lines 完全
  相同（113696 / 643）—— 等长改动，正是并发会话把 Task 29 的复选框从 `[-]` 翻成 `[x]` 而没有
  重生成矩阵。也就是说矩阵在本次改动前**已经陈旧**，本次重生成必然把它一起吸收。此处显式登记，
  不混进本次的账。

## 独立集成验证（本门自建，不引用各任务自己的守卫）

`backend/tests/workpaper_sync/test_task30_closure_gate_pg.py` —— 真实 PostgreSQL、
scratch schema `tmp_task30_gate_<hex>`、一次 `asyncio.run` 采集、**回读数据库行**而不采信
服务返回对象。**39 passed**。覆盖：

| 域 | 判据 |
|---|---|
| shell → correlation | accepted 后两 link 皆空 + application 0 行；durable correlation 原地成 primary；`application_key` == 测试**独立** sha256 重算值；origin == effective 起始相等 |
| 收敛（6 路真并发） | 恰 1 application + 恰 1 个自称创建者；1 primary + 5 direct terminal duplicates；0 stranded / 0 chained / 0 cyclic；**争用凭证**：6 个不同 `pg_backend_pid` + `max(t_ready) <= min(t_call)` |
| same-app fold | fold 路径**真的跑过**（至少一次 `folded_from` 非空）；origin 不变、effective == max、不 self-supersede |
| 复合幂等键 + fingerprint | 跨 participant / 换 payload / 换 contributor 三种均 409，错误文案**不含**旧 request/operation id，operation 行数 delta 0；逐字等值重放是 cache hit（反向自检） |
| quarantine 三层 | `durable_at IS NULL`；application 入口拒且**拒绝类型必须是隔离那一条**；representation 不得由 quarantined artifact 背书 |
| close exactly-one | single / A→B / B→A 各恰 1 条 capture 且**恰一次创建**；barrier 按 `has_predecessor` 分支；reconciler 重入不再建 capture、不换 leader、eligibility digest 相同；comparator 真的在 ≥2 候选上跑过且未短路 |
| leader 失权 | 三条失格判据**各有一个独立场景**（撤权 / lease 过期 / 非 closing），每场景只触发一条；失权者由测试按 `max(intent_sequence, id)` **自行预测**，不问服务 |
| 无 successor | `recovery_required` + 0 capture + 0 活 intent |
| recovery | crash case claim 前三实体全 NULL；普通 retry 拒 nullable-operation；authorization-first claim 同事务出三实体 + ≥3 条存活 scope row；download-only 三实体保持 NULL |
| scope tombstone | retire 只置 `retired_at`、行物理保留；id 复用在**域层**（`ScopeIntegrityError`）与**库层**（sqlstate 23505）各拒一次；物理 DELETE 被 trigger 拒（23514，文案指名表 + `retired_at`） |

`backend/tests/workpaper_sync/test_task30_closure_gate.py`（离线，**10 passed**；2026-08-29
修订新增一条移交方向判据）：`multi_resolver` 三条判据、裁决归属移交不倒转 wave 序、substrate
前提两条实证、Task 29 移交债的复核、delivery owner 按 `durable_at`（同 state 只翻
`durable_at`）、quarantine 允许/禁止双向。

## 变异矩阵（32 条，**全部 RED**；报告见 `mutation_batch*.json`）

选择集 = 本门两个文件 + Task 21 / Task 22（本门修好了它们的判据形态）+ Task 24
（close comparator / eligibility 分支）。基线 322→324 passed（中途新增一条判据），
2026-08-29 修订后逐文件实测仍为 324（10+39+97+90+88，本轮 +1 与并发会话 −1 相抵）。
每条变异均 `restored=True` 且 `restored_sha256` == 当前磁盘 sha256，无 `*.mutbak` 残留。
M31/M32 为 2026-08-29 修订新增（裁决归属登记 + 移交方向的 wave 序）。

| id | 注入点 | 语义 | 预测→实测 |
|---|---|---|---|
| M01 | `models.classify_operation_shape` | 漏 normal shell（shell 报成 primary） | `test_accepted_creates_a_shell_...` → **RED** |
| M02 | `repository.correlate_durable_incoming` | 删除 duplicate pointer | `..._n_minus_one_direct_terminal_duplicates` → **RED** |
| M03 | 同上 | duplicate pointer 自环 | `..._no_stranded_chained_or_cyclic_shell` → **RED** |
| M04 | 同上 | duplicate 再绑 application | `..._n_minus_one_direct_terminal_duplicates` → **RED** |
| M05 | `models.fold_effective_sequence` | fold 恒不推进 | `test_the_fold_path_actually_executed` → **RED** |
| M06 | `repository`（self-supersede 门） | same-app 自我 supersede | `test_fold_keeps_origin_immutable_...` → **RED** |
| M07 | `repository`（fold 分支） | `origin_request_sequence` 可变 | 同上 → **RED** |
| M08 | `models.compute_application_key` | key 丢掉 incoming digest | `test_application_key_is_the_frozen_identity_digest` → **RED** |
| M09 | `models.compute_frozen_request_fingerprint` | 丢掉 client edit epoch | `..._conflicts_...[payload_differs]` → **RED** |
| M10 | 同上 | 丢掉 contributor 快照 | `..._conflicts_...[contributors_differ]` → **RED** |
| M11 | `repository`（幂等冲突文案） | 冲突时返回旧 request id | `..._conflicts_...[cross_participant]` → **RED** |
| M12 | `callback_delivery.classify_delivery_ownership` | delivery gate 改回按 terminal 判 owner | `test_delivery_ownership_is_decided_by_durable_at_...` → **RED** |
| M13 | `QUARANTINE_ALLOWED_OPERATIONS` | quarantined 进 application | `test_the_quarantine_boundary_...` → **RED** |
| M14 | 同上 | quarantined release | 同上 → **RED** |
| M15 | `repository.assert_incoming_durable` | 隔离那道门短路 | `test_quarantined_incoming_is_refused_at_the_application_entry` → **RED** |
| M16 | `close_intent.close_leader_sort_key` | comparator 丢掉 sequence | `test_leader_is_highest_sequence_...`（Task 24） → **RED** |
| M17 | `repository`（`eligible()` 撤权分支） | 撤权不再失格 | `test_leader_revoked_before_promotion_...` → **RED** |
| M18 | `repository`（`eligible()` closing 分支） | closing 仍计 active | `test_a_non_closing_participant_is_not_a_leader_candidate` → **RED** |
| M19 | `repository.reconcile_close_intents` | reconciler 不再幂等 | `test_reconciler_is_reentrant_...[order_ab]` → **RED** |
| M20 | 同上（无 successor 终态） | `recovery_required` → `superseded` | `test_no_successor_lands_recovery_required_...` → **RED** |
| M21 | `repository.retire_scope` | 不再落 `retired_at` | `test_retiring_a_scope_row_keeps_the_tombstone_physically` → **RED** |
| M22 | `repository.register_scope` | 域层不再拒 id 复用 | `test_a_retired_resource_id_cannot_be_reused` → **RED** |
| M23 | `repository.create_representation` | 不再要求 approved bundle | `test_the_unified_resolver_really_requires_...` → **RED** |
| M24 | `check_workpaper_writer_revision_gate` | 门不再计 `multi_resolver` | `test_the_gate_still_counts_the_criterion_its_owner_verifies_zero_with` → **RED** |
| M25 | resolver 矩阵 JSON（8 处） | 阻塞登记指向不存在的任务 | `test_the_registered_blocker_points_at_...` → **RED** |
| M31 | resolver 矩阵 JSON（8 处） | 裁决归属登记改回上一跳（`"71"` → `"30"`） | `test_the_criterion_is_either_cleared_or_its_blocker_is_registered` → **RED** |
| M32 | tasks.md 依赖图 JSON | 把归属方 Task 71 挂进 `bulk_adapters` gate | `test_relocating_the_criterion_did_not_invert_the_wave_order` → **RED** |
| M26 | `rooms.py` | 另写契约常量 `= 120` | Task 21 契约数值判据 → **RED** |
| M27 | `rooms.py` | 另写 JSON 解析（字符串键取契约值） | 同上 → **RED** |
| M28 | `callback_delivery.py` | 新增第二处 `jwt.decode` | Task 22 token 判据 → **RED** |
| M29 | `rooms.py` | **对照项**：加一个与契约无关的常量 | 期望 GREEN（`added=[]`、`hit=[]`）→ 对照成立 |
| M30 | `repository`（`eligible()` 过期分支） | lease 过期不再失格 | `test_no_successor_lands_recovery_required_...` → **RED** |

### 首轮三条 GREEN（= 本门判据缺陷）与修法

| id | GREEN 原因 | 修法 |
|---|---|---|
| M15 | `assert_incoming_durable` 里「隔离」与「非 durable」两条分支共享拒绝**结果**，判据只断言「被拒」⇒ 短路前者仍绿（本 spec 点名的形态 (a)） | 判据改为断言拒绝**类型**是 `QuarantinedIncomingError` |
| M17 | 场景同时把 participant 的 `state` 改成 `revoked` **且**置 `revoked_at` ⇒ 两条失格判据同时成立 | 场景只置 `revoked_at`（state 保持 `closing`）；三条失格判据各拆一个独立场景 |
| M18 | 同上（无独立的「非 closing」场景） | 新增 `not_closing` 场景（只把 state 改回 `active`），并补 M30 覆盖过期分支 |

另有一条**自证式判据**在跑变异**之前**被自查出并修掉：`application_key` 的期望值原先调用
生产 `compute_application_key()` 计算 ⇒ M08 那类「从 key 里删一个分量」会同时改动两侧、
等式恒成立（self-certifying tautology）。现改为测试侧独立 `sha256("|".join(...))`。

## 两条移交过来的既有红（`command_service.py`）——已修，修的是判据

两条都**不是**生产缺陷：`command_service.py` 的两处行为都是契约要求的正确做法。原判据是
**字符出现型代理判据**，既打红正确行为、又漏掉真缺陷。

1. `test_task21…test_contract_numbers_have_single_source_in_oo_contract`
   * 原判据：剥注释/字符串后扫子串 `forcesave_callback_wait_timeout_seconds`。
     `_strip_comments_and_strings` 抹掉**全部**字符串常量 ⇒ 该子串剥完后**只可能**以标识符
     形态存活，也就是 `timers.forcesave_callback_wait_timeout_seconds` 这种**从契约对象读
     字段**的正确写法；真缺陷（`X = 120` 自写常量）里没有那个子串、数值 `120` 也不在扫描
     名单里。同一函数读 `timers.in_flight_grace_seconds` 却不被点名 —— 名单本身即随手。
   * 现判据（两条 AST）：**H1** 任一同步域模块把契约数值**绑定到契约同名标识符**（赋值 /
     带注解赋值 / 形参默认值 / 关键字实参），或出现 `52428800` 字面量；**H2** 只有 loader
     可以用字符串下标 / `getattr` 字面量取契约键。键集由 `dataclasses.fields(Timers)`
     **派生**（+ 下载字节上限），不在测试里抄。
   * 变异证明：M26（另写常量）RED、M27（另写解析）RED、M29（无关常量）GREEN。
2. `test_task22…test_jwt_decoding_lives_only_in_callback_route`
   * 原判据：`^\s*(from jose|import jose)` —— 把「解 token」与「签 token」混成一件事。
     Task 24 的 `sign_command_token()` 必须 import jose（契约
     `command_service.jwt.required=true`），于是判据必然打红一个正确模块；反过来在
     `callback_delivery.py` 里新增 `jwt.decode` 只会让本已为红的列表多一项，新缺陷混不出来。
   * 现判据：对**调用点**断言，两侧都给正向下限 —— `decode` 调用点 == {`callback_route.py`}
     且 ≥1；`encode` 调用点 == {`callback_route.py`（route token）, `command_service.py`
     （出站 Command token）} 且各 ≥1。两种 token 各有唯一签发者，多一个即红。
   * 变异证明：M28 RED。

## Task 29 移交的 evidence schema 债：**保持登记**，理由如下

`quarantined_rejects_application_and_engine` 在 V151 下无法记成 `result='passed'`
（AC 5.6 要求 `application_ids` 恒空，`ck_wpees_standard_requires_entities` 要求非
`download_only/recovery_reject` 的 passed 行 `application_ids >= 1`）。**不在本门修**：

1. **登记的 owner 就是别人**：`SCHEMA_UNREPRESENTABLE_SCENARIOS` 的 reason 明写
   「owner: evidence schema（V151 需要一个 `authorization_reject` kind）」，解法归 Task 9
   建表 / Task 39 harness / Task 70 全量刷新。
2. **现在加等于 additive 死代码**：`scenario_kind` 由 entity 形态**单点推导**
   （`RequiredScenario.kind`），而真正写 scenario 行的生产者是 Task 39 的 harness ——
   它还不存在。新增一个无人产出的 kind，正是本 spec 反复付过代价的「假绿第①源」。
3. **爆炸半径落在别人的交付物上**：29 个文件引用 V151 迁移文件，其中十余个 pg harness
   按文件路径显式 apply 它；新增 `V153` 要么逐个改那些 harness（改别人已变异验证过的
   守卫），要么让 scratch schema 与生产 schema 分叉。且 `MigrationRunner` 只在后端启动时
   应用迁移，活体库要重启才生效。
4. **行为不欠账**：本门直接验了**行为**（quarantined 在 application / engine / 库层三处被拒，
   见上表 quarantine 三层 + M13/M14/M15），并复核了登记本身今天仍成立
   （`test_the_quarantine_scenario_is_still_required_and_still_unrepresentable`：场景仍在
   required set、kind 仍是 `standard`、`schema_representable_as_passed` 仍为假、V151 两条
   CHECK 的 kind 名单**逐字**未变、登记表恰一条）。债一旦解（例如真加了
   `authorization_reject`），该判据立刻红 ⇒ 登记必须撤销。这就是「债」与「豁免」的差别。

## 辐射面与回归

辐射面由 `radiation_task30_closure_gate.py` **AST 实扫**得出（2283 个测试文件 → **47** 个
辐射）。判据分两通道：代码符号走 `Import`/`ImportFrom`；数据/脚本产物（JSON、生成器、门
脚本、tasks.md）走**非 docstring 的字符串常量** —— 本 spec 的注释里大量逐字引用这些文件名，
裸词搜会把说明文字算成引用。

`py -3 -m pytest <47 个辐射文件 + 我改过的 2 个>`：**2846 passed / 0 failed**（7分13秒）。

### 顺手修掉的既有红（47 条）—— 逐条说明改了什么、为什么

| 文件 | 改前 | 改后 | 改动 |
|---|---|---|---|
| `test_wp_onlyoffice_router.py` | 34 passed / **26 failed** | **60 passed** | 31 处 `app.include_router(router)` 后各补一行 `app.include_router(public_router)` |
| `test_onlyoffice_wopi_auth.py` | 0 passed / **10 failed** | **13 passed** | 同上（1 处）+ import `public_router` |
| `test_onlyoffice_session_lifecycle.py` | 5 passed / **11 failed** | **21 passed** | 同上（6 处，含内联的 `app2`）+ 3 处 `side_effect=[...]` 改 `_sequenced_execute(...)` |

* **为什么该改**：callback / `wopi/contents` / `onlyoffice/health` 三个端点挂在
  `public_router`（机对机入口，刻意绕过 `dedicated_wp_gate` 的 `get_current_user`），
  而生产 `router_registry.workpaper` **同时**注册 `router` 与 `public_router`。测试 app 只挂
  `router` ⇒ 这三个端点在测试里**根本不存在** ⇒ 26+21 条断言全在测 404，
  Task 28 新加的 room-bound 委派分支也就完全没有测试覆盖。这是**harness 与生产接线不一致**，
  不是被测行为的问题。
* `_sequenced_execute`：把固定长度 `side_effect=[wp, proj]` 换成「前 N 次按序返回、之后**恒**
  返回空结果」。Task 21 起 `resolve_room_doc_key()` 多一次 room 查询（doc_key 改由 room 身份
  派生），统一门在同一注入 session 上还会再查若干次；固定列表耗尽即 `StopAsyncIteration`，
  失败原因与被测行为无关。尾部空结果不是造数据 —— 对 room 查询而言，
  `scalar_one_or_none() -> None` 正是生产的基线代际路径（无存活 room ⇒ 按 generation 1 派生）。
* 另：因改了 tasks.md，`workpaper_ac_coverage_matrix.json` 需重新生成（3 条新鲜度判据红）。
  重生成前后逐字段 diff：**只有** tasks.md 的 sha256/bytes 与派生 `facts_digest` 变化，
  AC/property/task/defect 计数逐项不变（`ac=170 property=72 task=73`，
  `defects={'no_dependency_edge': 1, 'no_property_oracle': 101, 'self_certified_single_task': 8}`）。

## 本门**未**覆盖、由谁验（诚实边界）

Task 30 正文点名的以下变异落在 Task 25~28 的 router/coordinator 判据面上，本门的集成半
没有复现那些入口，故不在本脚本清单里：cache-before-auth、numeric revision 作
route/scope key、merged≠incoming 仍放行、route participant 当唯一作者、直接发布 candidate、
跳过 transition event、允许 null close initiator。它们各自由
`test_task28_sync_router*.py`（前四条 + numeric revision 无碰撞）、
`test_task27_conflict_resolution*.py`（rollback / candidate）、
`test_task24_close_intent.py::test_null_initiator_is_refused_before_the_command_service_call`
承担，本轮全部随辐射面跑过且绿。**本门不把它们记作自己独立验过。**

真实 OnlyOffice 9.4 probe / pilot：**未执行**，本门不冒充（Task 44/70 范围）。

## 复现命令

```
py -3 backend/scripts/check/check_workpaper_writer_revision_gate.py
py -3 backend/scripts/gen/generate_workpaper_resolver_migration_matrix.py --check
py -3 -m pytest backend/tests/workpaper_sync/test_task30_closure_gate.py backend/tests/workpaper_sync/test_task30_closure_gate_pg.py -q
py -3 backend/scripts/diagnose/radiation_task30_closure_gate.py
py -3 backend/scripts/diagnose/mutate_task30_closure_gate_guards.py --check-anchors
py -3 backend/scripts/diagnose/mutate_task30_closure_gate_guards.py --run M01,M02,M03   # 前台分批；--run all 约 27 分钟
py -3 backend/scripts/gen/generate_workpaper_ac_coverage_matrix.py --check
# 2026-08-29 修订（裁决归属 Task 30 → Task 71）的复现：
py -3 backend/scripts/diagnose/mutate_task30_closure_gate_guards.py --run M24,M25,M31,M32
py -3 backend/scripts/diagnose/mutate_task20_writer_gate_guards.py --run M15 --out <path>
```
