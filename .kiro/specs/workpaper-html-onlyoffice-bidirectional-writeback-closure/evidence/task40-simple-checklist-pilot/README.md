# Task 40 evidence：简单 checklist Excel pilot（冻结 entry `xlsx/b60/gt-b60-bundle`）

spec: `workpaper-html-onlyoffice-bidirectional-writeback-closure` · Wave 3 Task 40
Requirements: 3.7, 4.11, 6.8, 6.11, 12.1, 12.2, 12.10, 12.12, 14.1, 14.2
Properties: **P11 / P25 / P26 / P29 / P49 / P55 / P62 / P69**

## 一句话结论

四类 pilot 里的 `simple_checklist` 这一类，选定了 **`xlsx/b60/gt-b60-bundle`**（B60-1 审计项目
工时预算与控制表），走完 `template → instrumentation → contract → bundle` 四段真发布，
required scenario set 实测 **24 条**逐条落库（各自实体，44 个实体全 distinct），
`aggregate_result` 由服务端重算落 **`failed`** —— **没有**真实 OnlyOffice/浏览器，
11 条 UNVERIFIABLE、2 条 `upstream_gap` 记 failed，`simple_checklist` 这一类仍是
**UNVERIFIABLE**。adapter **未注册**、manifest capability **未启用**（`single_onlyoffice`），
因为 Task 36 finalize 被一条登记的上游缺口挡住 —— 这是任务正文要求的顺序，不是遗漏。

## 交付物

| 文件 | 性质 | 说明 |
|---|---|---|
| `backend/app/services/workpaper_sync/pilot_simple_checklist.py` | 新建 | 冻结身份常量 + 选型三条件现推 + per-entry contract payload + 四段发布编排 + 顺序门 + 生产接线 |
| `backend/data/workpaper_sync_contracts/b60.hour_budget.json` | 新建 | per-entry 契约（15 个受管字段，逐字段 `source_ref` / `header_source_ref`） |
| `backend/tests/workpaper_sync/test_task40_simple_checklist_pilot.py` | 新建 | 53 例离线守卫 |
| `backend/tests/workpaper_sync/test_task40_simple_checklist_pilot_pg.py` | 新建 | 24 例真库守卫（一次 `asyncio.run` 采集 + scratch schema） |
| `backend/scripts/diagnose/mutate_task40_simple_checklist_pilot_guards.py` | 新建 | 26 条变异，**全部 RED** |
| `backend/scripts/diagnose/select_task40_radiation.py` | 新建 | AST 级辐射面选取（22/2298） |
| `backend/data/workpaper_writer_inventory.json` | 重生成 | 本轮裁决使 pilot 的 resolver 行整行消失（319 行） |
| `backend/data/workpaper_resolver_migration_matrix.json` | 重生成 | 随 `inventory_digest` 联动（78 行） |
| `backend/app/services/workpaper_sync/adapters/registry.py` | 只加不动 | `DELIVERED_PER_ENTRY_CONTRACTS` 追加一条（`adapter_registered: false`） |
| `backend/app/routers/wp_sync_router.py` | 只加不动 | 两个接线点调用 `attach_pilot_adapters` |

无新迁移：本任务只写 V151 已有的 `working_paper_sync_test_run` /
`working_paper_entry_evidence_scenario` / definition & bundle 三张表。

## 为什么冻结的是 `xlsx/b60/gt-b60-bundle`

Task 39 的 `assess_pilot_classes()` 把 `simple_checklist` 定义成「xlsx 且 entry_id 不匹配
d2/h1/g7」，实测 **174** 个候选。在这 174 个里再叠三条**机器可判**的必要条件，剩下恰好一个：

| 必要条件 | 依据 | 实测 |
|---|---|---|
| `independent_entry = true` | AC 12.1 原文「每个**独立** entry」；43 条 `parent_duplicate` 被 `registry.register()` 直接拒 | 独立候选 16 个 |
| `wp_code_patterns` 里存在与 `wp_templates/_index.json` 的 `wp_code` **精确相等**的码 | `find_template_file()` 找不到自有模板时会一路回退到**父级程序表**，契约的 `source_ref` 就会指向另一份底稿的单元格 —— 本 spec 已为此付过两次学费 | 16 个 independent 候选里 **15** 个是回退形态，只有 `B60` 零回退 |
| `scenario_profile = xlsx.editable.shared.single.room_service_wired.v1` | 178 条 entry 的多数形态 ⇒ required set 是 shared+editable 标准集，不走 authority-model 替换分支，P25/P26 的字段级两场景**必跑** | ✓ |

`assert_pilot_entry_selectable()` 在**真实** manifest / 真实 `_index.json` 上把这三条**重新
推导一遍**（不是断言常量等于常量），任一不成立即 `PilotSelectionError`。四条 fail-closed
分支各有一条守卫（M03~M06 逐条打红）。

## 权威模板与逐字段 source_ref 依据

* 唯一载体：`backend/wp_templates/B/B60-1 审计项目工时预算与控制表.xlsx`
* 字节哨兵 `TEMPLATE_SHA256 = 65154146ed3b88a3c2908e064ceb29b6bc73e842559934cbaf2b6893421bd0b0`
  （16568 字节）；`read_authoritative_template()` **每次读都比对**，改一个字节即抛
  （Requirement 9.9：运行时只读）。参考副本 `基础数据/致同通用审计程序及底稿模板…`
  **一次都没读**（`test_reference_copy_is_never_read` 用代码路径判据锁死）。
* 工作簿 4 张 sheet（`底稿目录` / `B60-1工时预算与控制表` / `B60-1工时预算与控制板（按阶段）`
  / 隐藏 `GT_Custom`），契约**只**声明第二张。

openpyxl 直读的真实网格（守卫逐格比对，期望值从**源侧**取，不用被测函数算）：

| 契约声明 | 源 xlsx 真实单元格 | 实测内容 |
|---|---|---|
| `header_rows = 2` | 5/6 两行 + 合并 `C5:D5` `G5:H5` `A5:A6` `B5:B6` `E5:E6` `F5:F6` | ✓ |
| `grade` A 列 | `A5` | `级别` |
| `member_name` B 列 | `B5` | `姓名` |
| `budget_execution_hours` C 列 | `C6` | `执行工时`（父格 `C5 预算工时`） |
| `budget_review_hours` D 列 | `D6` | `复核工时` |
| `hourly_rate` E 列 | `E5` | `小时费用` |
| `budget_cost` F 列（`mode=formula`） | `F5` | `费用预算`；`F7..F23` 逐格 `=(C{r}+D{r})*E{r}` |
| `actual_execution_hours` G 列 | `G6` | `执行工时`（父格 `G5 实际工时`） |
| `actual_review_hours` H 列 | `H6` | `复核工时` |
| `variance_note` I 列 | `I5` | `差异说明` |
| 数据区 7..23（17 行） | `A7 合伙人` … `A22 项目质量控制复核人员`，第 23 行是模板留的可增行 | ✓ |
| `footer_anchor{marker:合计, search_column:A}` | `A24` | `合计`（不写死行号） |
| 6 个静态元信息字段 | `A3/A4/C3/C4/E3/E4` 标签，值格恒在右侧一列 | `被审计单位名称：` `会计期间：` `编制人：` `复核人：` `编制日期：` `复核日期：` |
| 隐藏 row UUID 列 `J` | 必须严格在 `I` 右侧 | ✓ |

`G3 索引号：B60-1` 是固定文案，不入契约。覆盖计数硬判据（空集恒等价不算通过）：
受管字段 **15**（行域 9 + 元信息 6）· editable **14** · protected **1** ·
表头逐格比对 **9** 次 · 静态标签逐格比对 **6** 次 · 公式逐行比对 **17** 次。

## authority model / contract / bundle 的 digest

真库实测（scratch schema，`run_facts.json` 是原始快照）：

| 对象 | logical_id | sha256 |
|---|---|---|
| authority model definition | `b60.hour_budget.authority-model` | `de0a8376ff8c89cceb8b9e9fead6cb849a692cd9c9359bc44a558222721b460c` |
| template definition | `b60.hour_budget.template` | `3dc00385534a85211da311ce68579ddcd77f8a3ef55f3c312d96b8ec3cbdfb1f` |
| instrumentation definition | `b60.hour_budget.instrumentation` | `8a1319384f807f35a868cb66647bf8c0d88f678684992e2017ead6669642df21` |
| contract definition | `b60.hour_budget` | `527e6e38ba3aaf6763867fd0b442821615940e3c5c7ab5fa2130bc000635cd0b` |
| **definition bundle**（non-null，`approved`） | — | `98289fd059c8ccb76fe8e92bd85448597611ddd71972541091b69ab7fcf24eda` |
| 模板 normalized structure hash | — | `47d3f903004328b11f8cb384162ea2f16ef6fbfbfc7f4babb6ba18549e6d225f` |

* `authority_model = projection_contract` ⇒ 三个 typed slot 实测**全是** approved
  `definition`（不是 typed null marker），bundle canonical digest 与独立重算逐字相同。
* 磁盘契约里的两个 digest **不是手抄常量**：`assert_contract_file_matches_source()` 把
  磁盘 payload 与本模块现算 payload **双向**锁死（改任一侧都打红：M07 改源侧、M08/M09/M10
  改磁盘侧）。
* 顺序真的被强制：先发 contract 再发 template 被 `assert_publish_order` 拒，
  实测消息「发布 DAG 违规：contract 的前置阶段 ['template', 'instrumentation'] 尚未 approved」。
* **没有复用任何其它 pilot 的 contract / bundle / candidate**：contract_id 就是
  `b60.hour_budget`（= adapter_id = 契约文件名，registry RG-4 双向锁），四个 definition 的
  logical_id 全部以它为前缀，bundle 现发。

## published representation / finalize 的现状

`resolve_published_frozen_definitions()` **刻意未实现**，按登记欠账
`UPSTREAM_DEBT_PUBLISHED_IDENTITY_OBSERVER` **抛可分辨异常**（不返回 `None`）：

> 缺「published representation artifact → `FrozenEntryDefinitions`」的公共观测器。
> `excel_entry_gate.ExcelEntryDefinitionLoader.load()` 的 `identity_inventory` /
> `observed_structure` / `observed_business_sheets` / `observed_dynamic_columns` 四个入参
> 今天只能由 Task 17 的 candidate evidence 在 **finalize 那一刻**提供；请求时刻没有等价来源。
> ⇒ 请求路径上的 adapter 组装只能 fail closed。owner 建议归 engine 侧（Task 38 后续）。

因此**今天没有 published representation id/generation**，`attach_pilot_adapters()` 恒返回
空元组，`assert_manifest_capability_enabled()` 恒抛。这是任务正文「经 Task 36 finalize 成
published representation 后，**方可**注册 adapter / 接宿主 / 启用 capability」的忠实执行：

* manifest 维持 `capability=single_onlyoffice` / `adapter_id=null`
  ⇒ manifest digest **未变**（`8b4f15a5…`）；
* 「契约有了而 adapter 没注册」作为**可见欠账**报出来：`registry.build_report()` 的
  `contract_files_without_adapter` 含 `b60.hour_budget`、`closed=False`，交付登记表那一行
  `adapter_registered=false`（M20/M21 逐条打红）；
* 提前启用 capability 会被 RG-16 拒 —— 且拒的是 **RG-16 而不是 RG-18**：本 entry 的宿主
  **实测**已暴露结构化 ↔ OO 模式切换（descriptor mode = `bidirectional`），与 manifest 的
  `single_onlyoffice` 直接矛盾，`register()` 的 ③ profile 判据先于 ④ 伪双向。
  `test_capability_enable_would_clear_the_existing_rg16_drift` 把「将来启用是**消除**既有
  漂移」写成可执行事实（同一 profile 在 `bidirectional` 下三条 profile 判据全过）。

## 每条 Property 的 oracle 落点

`PROPERTY_ORACLE_LANDING` 与 `pilot_harness.SCENARIO_ORACLES` 双向锁，并且每个落点
**必须在本 entry 自己的 required set 里**（否则等于这条 Property 在本 entry 上从未跑到）。

| Property | 落点 scenario | 今日判定 | 判据 |
|---|---|---|---|
| **P11** descriptor 唯一 + ready 后确认 | `html_to_oo` | UNVERIFIABLE | 需真实 DocEditor 生命周期与 `onDocumentReady` 幂等确认 ⇒ `needs_black_box` |
| **P25** 不同字段自动合并 | `different_field_merge` | **passed** | 用**本契约自己的** stable key（`hour_budget_rows/{row}/member_name` 与 `/variance_note`）真跑三方 merge；`conflict_count==0` 且 A 键取 current、B 键取 incoming |
| **P26** 同字段异值必冲突 | `same_field_conflict_resolve` | **passed** | base=A/current=B/incoming=C 三值完整、不得采纳任一侧、merged ≠ incoming |
| **P29** materialize/extract roundtrip | `oo_to_html` | UNVERIFIABLE | 需真实 OO 产出的 xlsx 字节 |
| **P49** 四类 pilot 覆盖 | `identity_retention` + `assess_pilot_classes()` | UNVERIFIABLE | 类边界由 harness 判定（不由本模块声明）；`status=unverifiable`、`verified_entry_ids=()`、`all_verified=False` |
| **P55** 真浏览器双向闭环 | `html_to_oo` + `oo_to_html` | UNVERIFIABLE | 两向都要真实环境 |
| **P62** server last-applied 与 client-confirmed 不混同 | `refresh_required_reopen` | UNVERIFIABLE | 需真实 room 的 `refresh_required` 与新 generation ack |
| **P69** evidence 由逐场景实体 + 服务端重算闭合 | `single_participant_close` + 整个 24 条重算 | **passed**（该场景）；run 级 `failed` | required==observed（24/24）、44 个实体全 distinct、`ordinal` 稠密唯一、每行绑已发布 trace bundle、`aggregate_result` 由服务端重算 |

`test_field_level_properties_are_not_substituted_away` 额外锁住：`projection_contract` ⇒
AC 12.12 的字段级两场景**不得**被 `authoritative_revision_conflict` / `no_silent_overwrite`
替换（M16 把 authority model 换成 opaque 即打红）。

## required scenario set 实测（24 条）与逐场景结果

`plan.scenario_count = 24`（`substituted=false` · `close_required=true` ·
`required_digest = 984681c2c537d0ec064889de625323f79152f6a7c8a27794961de2f46a796ce6` ·
`typed_child_digest = 172959c4ecd1e71c3c60647d31f529612302ef55eab67330b19d0019351e74f2`）。
落库 24 行，`passed 11 / unverifiable 11 / failed 2`：

| 结果 | 条数 | 场景 |
|---|---|---|
| **passed**（离线可判） | 11 | `different_field_merge` · `same_field_conflict_resolve` · `cross_participant_idempotency_409` · `opaque_version_rollback_no_numeric_collision` · `authorization_first_recovery_claim` · `download_only_zero_three_entities` · `rollback` · `single_participant_close` · `close_leader_revoked_successor_exactly_one` · `close_leader_revoked_no_successor_recovery_required` · `close_reconciler_reentrant_exactly_one_capture` |
| **unverifiable**（黑盒环境缺失） | 11 | `html_to_oo` · `oo_to_html` · `identity_retention` · `frozen_base_status_6_2_dedupe` · `browser_crash_no_userdata_recovery_case` · `refresh_required_reopen` · `two_user_close_order_a_then_b` · `two_user_close_order_b_then_a` · `b_close_before_a_forcesave_terminal` · `b_close_after_a_forcesave_terminal` · `quarantined_rejects_application_and_engine` |
| **failed**（`upstream_gap`，Task 32 实现缺口） | 2 | `same_application_higher_sequence_fold` · `wrong_prior_confirmation_bundle_fence_contributor_rejected` |

🔴 判定顺序不可交换：harness 的 `run_scenario_oracle()` 把「上游实现缺口 → failed」放在
「黑盒环境缺失 → unverifiable」**之前**。否则接了 OO 之后这两条会自动变绿，而它们其实
永远不会通过。`aggregate_result` 由服务端重算 = **`failed`**（`finished_at` 已落），
`ScenarioObservation` 没有 `result` 字段、`finalize_run()` 没有 `aggregate_result` 入参 ——
调用方无法供结果。

## evidence 逐场景各自实体（AC 12.10）

* 实测 **44** 个实体（operation / application / recovery case）**全 distinct**
  （`total == distinct == 44`）；
* 反向自检：故意让两条场景（`html_to_oo` / `oo_to_html`）共用同一 operation+application ⇒
  第一条写入成功、第二条被 `assert_no_reuse_within_run` 以
  **`entity_reused_within_run`** 拒（不是"看起来没复用"，是写入期真拒）；
* `download_only_zero_three_entities` 实测零 operation / 零 application；
* 每行都绑一条**已发布**的 trace bundle artifact（digest 逐行不同）。

## 变异检验：26 条全 RED（首轮 23 RED / 1 WRONG-TEST / 2 GREEN）

```
py -3 backend/scripts/diagnose/mutate_task40_simple_checklist_pilot_guards.py --check-anchors
  → 26/26 OK，0 MISS，只读性核验通过
py -3 backend/scripts/diagnose/mutate_task40_simple_checklist_pilot_guards.py --run all \
    --out …/evidence/task40-simple-checklist-pilot/mutation_report.json
  → RED 26 / 26，exit 0，守卫文件覆盖面 3/3
```

分母（`guard_files`）= 本任务新建的两个守卫文件 + Task 13 被本任务从「绝对空清册」翻转成
「登记锁」的那一个类。基线 **82 passed**（离线 53 + 真库 24 + Task 13 边界 6，10.3s）。

### 交接时的脚本缺陷：`--check-anchors` 从未跑过

接手时脚本在 `--list` 阶段就 `TypeError: Mutation.__init__() missing 1 required
positional argument: 'want'`。根因不是"写到一半被中断"（26 条声明是完整的），而是
**`_mutation_kit.spec.Mutation` 的 `want: str` 是无默认值的必填字段**，而 10 条变异只给了
`wants=`。平台 39 个用 `wants=` 的脚本无一例外都同时给 `want=`（主目标）+ `wants=`（其余
目标，判定取并集）。修法：把每条的第一个目标提到 `want=`，其余留在 `wants=`。
另修 M26 的 `scope+offset` —— 原写 `offset=13` 指到了 `authority = await
publisher.publish_definition(`，正确值是 **11**（`anchor` 在两处出现，必须相对定位）。

### 首轮非 RED 的逐条归因

| id | 首轮 | 归因 | 修法 |
|---|---|---|---|
| **M14** | WRONG-TEST | **脚本缺陷**：`want` 写成 `TestAuthoritativeTemplate::test_uuid_column_sits_right_of_the_managed_business_columns`，而该测试住在 `TestContractIsGroundedInTheTemplate`。`--list` 的 want 可定位性检查只比 nodeid **末段**（方法名），类名写错它查不出来 | 改正类名前缀。**顺带发现真守卫缺陷**：该测试原有 `spec.uuid_col == P.UUID_COL` / `spec.managed_last_col == P.MANAGED_LAST_COL` 两条是自证式同义反复（两侧读同一常量），真正抓住 `UUID_COL="H"` 的是 Task 17 `ExcelInstrumentationSpec` 的构造期校验。已把期望值改成从**磁盘契约的真实列集合**推导（`columns == ABCDEFGHI`，`uuid_col > columns[-1]`） |
| **M24** | GREEN | **无效变异**（`why` 的因果链不成立，不是守卫缺陷）：`build_bundle_canonical_payload()` 放进 payload 的是 `authority_model: {type: definition, sha256: <authority definition digest>}`，**不是**枚举；枚举只参与 `validate_bundle_slots()` 的分支选择，而 `projection_contract` 与 `custom_authoritative_ooxml` 对「三 slot 全是 approved definition」判定完全相同 ⇒ 该改动在 digest 与库行上**都不可观测** | 换成攻击真正进入 digest 的那一项：`authority_model_definition_sha256=authority.sha256` → 假 digest（`scope+offset` 相对定位，该行在文件里出现两次） |
| **M26** | GREEN | **真守卫缺陷**：`test_disk_contract_matches_the_source_of_truth` 自己直接调那把双向锁，从不检查**生产路径**用的是哪一个 ⇒ 把 `publish_pilot_definitions()` 里的 `assert_contract_file_matches_source()` 换成 `load_pilot_contract()` 后 82 例全绿。判据与生产路径脱钩 = 一份被手改过的契约可以照常发布 | 新增 `test_both_production_paths_go_through_the_bidirectional_contract_lock`：AST 断言 `publish_pilot_definitions` / `attach_pilot_adapters` **都**调双向锁、**都不**直接 `load_pilot_contract` |

结论与前几轮一致：首轮非 RED **几乎都是守卫/脚本缺陷，不是生产代码问题** —— 本轮 3 条
里 1 条脚本缺陷、1 条无效变异、1 条守卫缺陷，生产代码 0 处需要改。

## `pilot_simple_checklist::_template_index_wp_codes` 的裁决

Task 59 收尾时把 writer gate 的 `total blocking facts` 从 916 顶到 **918**、
`non_canonical_resolver_only` 从 63 顶到 **64**，归因是这一行同时命中
`non_canonical_resolver_only` 与 `unadjudicated_resolver`。归因实测（`evaluate_gate()` 逐条查表）：
该行只命中这两条，别的一条不沾。

**裁决：两个 overlay 桶都不进，改成让它不再被发现。**

| 方案 | 结果 | 为什么不行 / 行 |
|---|---|---|
| 进 `adjudications` | 918 → **917** | 只清 `unadjudicated_resolver`（status 变 adjudicated）；`non_canonical_resolver_only` 是 **AST 派生事实**（`bool(resolvers) and "resolve_wp_file" not in resolvers`），盖一个 domain 标签清不掉。而这个函数**永远不该**走 `resolve_wp_file` —— 那是底稿产物的 canonical resolver，不是模板索引的 ⇒ 这条红没有收敛路径 |
| 进 `retired_adjudications` | **结构性不可能** | 生成器 `_build_retired_writers()` 明文拒绝：`retired adjudication … is discovered as a writer/resolver again -- the source regressed …; move it back into adjudications`。一个仍被发现的行不可能是"已退役" |
| **不再自己拼路径** | 918 → **916** ✓ | 该行只因 `_BACKEND_ROOT / "wp_templates" / "_index.json"` 这一处 `ast.BinOp` 被分类成 resolver（`resolver_identities=["<ad_hoc_path_construction>"]`）。改取 `wp_template_finder.INDEX_FILE` 后 `ad_hoc_paths` 为空 ⇒ `resolves=False` ⇒ **整行从 `entries` 消失** |

第三条同时消掉一个真问题：模板库在哪本来由 `wp_template_finder` 单独持有，这里再拼一次
就是同一事实的第二个真源 —— 而本函数的用途恰恰是「判断 `find_template_file()` 会不会回退
到父级程序表」，两侧看的不是同一个索引时这个判断本身就失效。`wp_template_finder.py`
**未被修改**（只读它的 `INDEX_FILE` 常量）。

配套守卫 `TestPilotIntroducesNoResolverDebt`（4 例）—— 没有它，任何人把路径拼回来都不会
有判据打红，收口门禁的数字只会在下一次 `--apply` 时悄悄涨回去：

1. `test_no_function_in_this_module_is_classified_as_writer_or_resolver`：用**生成器本体**的
   `_iter_functions` / `_collect_facts` / `_classify` 跑本模块全部函数（`checked >= 20` 防
   遍历谓词失效导致空集恒真），要求分类结果为空集；
2. `test_the_generator_would_still_flag_the_retired_ad_hoc_path`：**反向自检** —— 把旧形态
   那一行喂回分类器，必须仍判 `resolver` + `identities == ["<ad_hoc_path_construction>"]`
   （否则第 1 条是空判据）；
3. `test_index_path_comes_from_the_template_finder`：真调 `_template_index_wp_codes()`
   （`len > 100` 且含 `B60`），且 `INDEX_FILE.parent` 与 carrier gate 的 authority root
   落在同一棵模板库下 —— 不是只查符号出现；
4. `test_neither_overlay_bucket_carries_this_module` + `test_inventory_on_disk_has_no_row_for_this_module`：
   裁决结论本身可被falsify。

### 门禁回落实测

```
py -3 backend/scripts/check/check_workpaper_writer_revision_gate.py
  rows=319 writers=269 resolvers=71 retired=3        （改动前 320 / 269 / 72 / 3）
  unadjudicated_resolver: 34                          （改动前 35）
  non_canonical_resolver_only: 63                     （改动前 64）
  multi_resolver: 4 · unadjudicated_writer: 236 · bypasses_unified_commit: 261
  writes_legacy_version_field: 5 · owns_direct_commit: 105
  writer_without_characterization_test: 208 · missing_required_domain: 0
  total blocking facts: 916                           （改动前 918）
  [BLOCKED] exit 1 —— Task 20 按设计留红
```

生成物链（每轮都踩，本轮照做）：改 `backend/app` 生产模块 ⇒
`workpaper_writer_inventory.json` 的 `source_digest` 过期 ⇒ 门禁会**提前**以
「stale inventory」失败而不是按设计报数 ⇒ `--apply` 重生成（新
`inventory_digest = b2bde05b4a25bc5b51f01914d4589836326a5884b4c4812e56bc3a503e46e58b`）
⇒ 因 `matrix_digest` 含 `inventory_digest`，矩阵**必须随之** `--apply`。

矩阵变动**归因型**核对（不是全局等值型 —— rows 按 writer_id 排序，删一行会让后续行整体
位移）：`row_count 79 → 78`、`deferred 65 → 64`、`resolver_fork_count 64 → 63`、
`migrated 14` 不变、**`regressed = 0`**；被删的正是原下标 62 的
`app.services.workpaper_sync.pilot_simple_checklist::_template_index_wp_codes`（status
`deferred`、group `template_provisioning`）。`by_group.template_provisioning 4 → 3`
是同一行的归属组，其余 11 个组一个不变。

## 辐射面

`select_task40_radiation.py` 比 Task 39 的选取器多一类结构化证据：**生成物文件名**
（`ast.Constant` 字符串）。理由 —— 本任务重生成了两份 JSON，而消费它们的守卫
（Task 12 `test_matrix_is_fresh`、Task 20 writer gate、Task 30 closure gate、Wave 0 writer
清册特征测试）在 import 图与符号图上**都看不见**这次改动，漏掉这一类就会得出「辐射面
全绿」而 CI 在干净 checkout 下打红。只看 `ast.Constant` 而不是整文件 grep：登记表的 `why`
文案与本任务守卫的 docstring 里也写着这些文件名，词面匹配会把它们全算进来。

实测 **22 / 2298** 个测试文件，跑完 **1332 passed / 8 failed（4m13s）**。8 条全部是既有红，
与本任务无关：`test_wp_template_finder_d4_prefix.py` **7** 例（该模块缺
`find_whole_workbook_template` / `_wp_code_filename_prefix_ok`）+
`test_x3_column_alignment.py` **1** 例（`x3` spec 的 evidence 快照文件缺失）。两者都在
`backend/tests/` 根目录、都在交接说明的既有红清单里。

## 五门禁实测

| 门禁 | exit | 实测 |
|---|---|---|
| `check_workpaper_writer_revision_gate.py` | **1**（按设计） | 916 / `non_canonical_resolver_only=63` / `unadjudicated_resolver=34` / `unadjudicated_writer=236` / `bypasses_unified_commit=261` / `writes_legacy_version_field=5` / `multi_resolver=4` |
| `generate_workpaper_resolver_migration_matrix.py --check` | 0 | `row_count=78 migrated=14 deferred=64 regressed=0` |
| `generate_workpaper_sync_frontend_contract.py --check` | 0 | digest `ca3b003aeaad2f154677a9f9e499fd66e306c5ff49882c169ccc720fa0056c5b`（**未变**） |
| `generate_workpaper_sync_manifest.py --check` | 0 | digest `8b4f15a5e012f71870cdffb533c906968bb43c036cb9725fd4ec9428a039ef28`（**未变** —— capability 未启用，`entries=186` / `independent=142` / `by_component` / `room_model` / `scenario_profiles` 全部与改动前逐字相同） |
| `generate_workpaper_word_template_adjudication.py --check` | 0 | 50 行、`unadjudicated=0` |

## 新登记的债

| 债 | owner 建议 | 说明 |
|---|---|---|
| 缺「published representation artifact → `FrozenEntryDefinitions`」公共观测器 | engine 侧（Task 38 后续） | 见 `UPSTREAM_DEBT_PUBLISHED_IDENTITY_OBSERVER`。它挡住 Task 36 finalize ⇒ 本 pilot 的 adapter 注册 / capability 启用 / published representation 三步全部停在门前。这是本任务**唯一**未完成的正文动作，且是刻意 fail closed 而不是造一个假 adapter |
| `b60.hour_budget` 是「契约孤儿」 | 同上 | 已作为可见欠账进 `registry.build_report().contract_files_without_adapter`，交付登记表那一行 `adapter_registered=false`。上一条债解除后应一并转正 |
| `_mutation_kit.cli._locate_want()` 只比 nodeid 末段 | kit owner | 类名写错（M14 首轮）在 `--list` 下查不出来，只能等 `--run` 判成 WRONG-TEST。建议把类名段也纳入定位校验 |
