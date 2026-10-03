# Task 74 证据（第一半：逐 domain 裁决）—— **两条准则归零，其余 12 条一条未动**

Requirements 2.1、2.2、2.11、2.12、9.11、12.6、12.7、13.4 · Property 4、Property 61

**结论先行**：`check_workpaper_writer_revision_gate.py` 的 `unadjudicated_writer` **236 → 0**、
`unadjudicated_resolver` **34 → 0**，合计 blocking facts **916 → 646**，其余 12 条准则**逐条相等**。
门仍是**红**（退出码 1）—— Task 74 的第二半（逐 writer 迁 `ContentMutationService.commit(...)`）
本轮**没做**，261 / 105 / 208 / 63 / 5 如实留红。**Task 74 因此不得标 completed。**

> 本轮范围由用户明确缩窄为「只做逐 domain 裁决」。终局判据（14 条全零）今天本就不可达：
> `multi_resolver` = 4，真实阻塞是 Task 36 的逐 entry 供给（Task 71 / Task 72 两次独立实测一致）。

---

## 一、14 条准则对照表（门现算）

| # | 准则（issue key） | 裁决前 | 裁决后 | 本轮定位 |
|---|---|---|---|---|
| 1 | `unadjudicated_writer` | **236** | **0** | ✅ 本轮目标 |
| 2 | `unadjudicated_resolver` | **34** | **0** | ✅ 本轮目标 |
| 3 | `bypasses_unified_commit` | 261 | 261 | 本轮不动（第二半） |
| 4 | `owns_direct_commit` | 105 | 105 | 本轮不动（第二半） |
| 5 | `writer_without_characterization_test` | 208 | 208 | 本轮不动（第二半） |
| 6 | `non_canonical_resolver_only` | 63 | 63 | 本轮不动（第二半） |
| 7 | `writes_legacy_version_field` | 5 | 5 | 本轮不动（第二半） |
| 8 | `multi_resolver` | 4 | 4 | 归属 Task 71，阻塞在 Task 36 |
| 9 | `keeps_legacy_write_path_beside_unified_commit` | 0 | 0 | Task 20 守住，不许顶回非零 |
| 10 | `after_save_still_increments_revision` | 0 | 0 | Task 20 守住，不许顶回非零 |
| 11 | `representation_upgrade_increments_business_revision` | 0 | 0 | Task 20 守住，不许顶回非零 |
| 12 | `artifact_snapshot_writer_not_verifiable` | 0 | 0 | Task 20 守住，不许顶回非零 |
| 13 | `retired_writer_not_verifiable` | 0 | 0 | Task 20 守住，不许顶回非零 |
| 14 | `missing_required_domain` | 0 | 0 | Task 20 守住，不许顶回非零 |
| — | **合计 blocking facts** | **916** | **646** | |

第 10 条值得单记：本轮把两条**真实**的保存后/事件副作用行裁决进了 `orchestrator_side_effect`
（`ConsistencyCheckService.update_workpaper_consistency`、`register_event_handlers._on_b514_high_risk`），
于是 Task 20 证据 §九 登记的「`entries` 侧那个 `if domain == 'orchestrator_side_effect'` 分支不可达」
**不再成立** —— 该分支现在有分母了，且两行都不写任何版本字段，所以准则仍为 0。这条分支的可达性
由 `test_the_two_new_lanes_buy_nothing` 的反向对照实测（把统一计数器那行标成该 domain ⇒ 准则立刻
点名它）。

## 二、270 行裁决的 lane 分布

| lane | 行数 | 说明 |
|---|---|---|
| `checklist_response_store` | **125** | Requirement 9.11 的第二权威存储。Task 20 证据 §四.1 记的「被声明出来又空着的 lane」现在有人了 |
| `dedicated_router` | 65 | 专用循环计算/编辑/prefill/程序状态栈写 `working_paper.parsed_data` |
| `export_storage_resolver` | 41 | 下载/导出/预览/模板查找/出品物渲染的物理路径解析 |
| `html_save` | 16 | 写 `parsed_data.html_data`（含 `_f0/_g0/_h0/_k0/_l0` 的 `_save_html_data` 与 excel_html sidecar 的编辑保存） |
| `template_provisioning` | 12 | 从模板/转换源落地底稿文件与 `working_paper` 行 |
| `wopi` | 3 | WOPI host 的读侧（走 canonical `resolve_wp_file`） |
| `orchestrator_side_effect` | 2 | 保存后一致性回写 + B51-4 事件处理器 |
| `read_only_evaluation` | 2 | QC 试运行的内存 DTO / 上下文（零持久化） |
| `history_restore` / `oo_callback` / `unified_commit_substrate` / `upload_import` | 各 1 | 版本快照列举 / sidecar 的 OO 摄取 / 统一计数器 CAS 原语 / 附件晋级 |

裁决后全量 domain 分布（含 Task 3 的 49 条）：`checklist_response_store` 125 · `dedicated_router` 71 ·
`export_storage_resolver` 54 · `template_provisioning` 18 · `html_save` 17 · `f2_word_sync` 6 ·
`wopi` 6 · `custom` 5 · `upload_import` 5 · `history_restore` 3 · `oo_callback` 2 ·
`orchestrator_side_effect` 2 · `read_only_evaluation` 2 · `rollback` 2 · `unified_commit_substrate` 1。

**新增两条 lane**（`_DOMAINS` 是地板不是天花板，Task 3 自己就用了正文枚举之外的
`template_provisioning`）：`unified_commit_substrate`（统一协议自己的写入原语）与
`read_only_evaluation`（AST 认作 writer 但零持久化）。两条都**买不到任何东西** —— 见 §四。

## 三、注解怎么保证不是模板

注解 = **人工裁决**（lane 归属理由 `why` + 迁移目标/阻塞 `target`，写在
`backend/scripts/gen/adjudicate_task74_writer_domains.py` 的规则表里，17 条规则 + 12 条逐 writer 精确
裁决）**+ 逐行派生的事实**（身份、`source_path`、反向委派入边、实测 facts、结构形态、characterization
证据状态）。渲染出的 270 条注解长度 884–1493 字符，**两两不同**。

判据不是「注解非空」（生成器早就拒空），而是三条：

| 判据 | 守什么 | 复制粘贴时为什么会红 |
|---|---|---|
| `test_every_note_cites_exactly_the_facts_that_row_has` | 注解 `Measured:` 段里反引号包住的 token 与该行 facts **双向**相等 | 粘来的注解引用的是**别行**的列/委派/resolver ⇒ `invented` 非空、`missing` 非空 |
| `test_every_note_is_anchored_on_its_own_row` | 注解开头必须是这一行自己的 `qualname` + `source_path` | 前缀是别人的 ⇒ 红 |
| `test_notes_are_pairwise_distinct_and_carry_no_placeholder` | 两两不同 + 无「待裁决/见上/TBD/pending」等占位词 + ≥200 字 | 逐字相同 ⇒ 红 |

**规则表 fail-closed**：任何一行命不中规则即 `SystemExit`，**绝不给默认 lane**（默认 lane 就是
「未裁决伪装成已裁决」）。`test_the_authoring_rules_refuse_an_unmatched_row` 喂一条合成孤儿行，
`test_the_rule_table_has_no_catch_all` 反向自检每条规则都不是恒真。

## 四、四件禁止事项：一件都没做（可复核方式）

| 禁令 | 本轮实际改动 | 复核方式 |
|---|---|---|
| 加豁免列 / overlay 级 `allow_bypass` | overlay 每条裁决**只有** `domain` + `version_domain_note` 两个键 | `test_the_overlay_still_has_no_exemption_field`（270 条逐条）+ Task 3 的 `test_adjudications_are_domain_labels_not_bypass_exemptions`；变异 **N04** 塞一个 `allow_bypass` ⇒ RED |
| 缩小分母（`_APP_ROOT` / `_is_production_source` / `_CONTENT_STORES`） | 三处**一个字节未改**；行分母仍 319 行（writers 269 / resolvers 71） | 生成器 diff 只有 `_DOMAINS` 加两条 lane（含注释）；Task 20 的 M16/M17/M18 复跑仍 RED |
| 把 `raise WriterGateError` 改成报 0 | 门里三处空分母 `raise` 未改 | Task 20 的 M10/M11/M12 复跑仍 RED |
| 删掉任何一条 criterion 的计算 | 门的 14 个 key 全在，`has_debt` 仍是 14 条的 `any()` | 变异 **N05** 把未裁决准则短路成 `if False` ⇒ RED（靠「摘掉裁决必须回到 236/34」反向证明门真的在算） |

**最关键的一条行为级判据**：`test_adjudicating_clears_exactly_two_criteria` —— 把本轮 270 条裁决
从 overlay 摘掉、从源码重推清册、再量门，差异必须**恰好**是那两条回到 236 / 34，其余 12 条逐条
字节相等。它比「读门的源码看有没有豁免列」强：即便有人把豁免藏进 verdict 的算式（变异 **N06**
就是这么干的：让 `bypasses_unified_commit` 看一眼 `adjudication`），这条也会红。

## 五、变异检验

### 5.1 本任务新守卫（`mutation_report.json`）：**7/7 RED**，全部命中预测项

| # | 落点 | 手法 | 命中判据 |
|---|---|---|---|
| N01 | 裁决脚本 | 命不中规则时给默认 lane 而不抛错 | `test_the_authoring_rules_refuse_an_unmatched_row` |
| N02 | 裁决脚本 | 把最大那条规则改成恒真（catch-all） | `test_the_rule_table_has_no_catch_all` |
| N03 | overlay | 把一行的注解**原样粘**到另一行 | `test_every_note_cites_exactly_the_facts_that_row_has`（+ 身份、两两不同两条同时红） |
| N04 | overlay | 加 `allow_bypass: true` 豁免字段 | `test_the_overlay_still_has_no_exemption_field` |
| N05 | 门 | 未裁决准则短路成 `if False`（键在、恒零） | `test_adjudicating_clears_exactly_two_criteria` |
| N06 | 生成器 | 让 `bypasses_unified_commit` 看 `adjudication`（裁决即豁免） | `test_adjudicating_clears_exactly_two_criteria` |
| N07 | 门 | 把新造的 lane 塞进 `_REQUIRED_DOMAINS` | `test_the_required_domains_stay_a_proper_floor` |

### 5.2 Task 20 守卫复跑（`mutation_task20_rerun.json`）：21 条 → 18 RED / 2 GREEN / 1 WRONG-TEST，两条非 RED **逐条归因并修好**（`mutation_task20_rerun_m13_m19.json`：M13 / M19 均转 RED）

| 变异 | 首轮 | 归因 | 处置 |
|---|---|---|---|
| M04 | GREEN | **无效变异**（Task 20 声明期即写明的负对照） | 保留 |
| M13 | WRONG-TEST | **脚本缺陷（`want` 过期）**：判据在 Task 30 的移交整改里改名为 `test_the_gate_evaluates_exactly_the_criteria_the_spec_names`，脚本仍写旧名 `..._every_criterion_task20_names`。实际打红的正是改名后那条（见 `added`） | 改 `want`，复跑 **RED** |
| M19 | GREEN | **本轮改动导致的无效变异**：原变异只把 `template_provisioning` 收进 `_REQUIRED_DOMAINS`，那是 Task 3 时代**唯一**的越界 lane；本轮又多了 `checklist_response_store` / `unified_commit_substrate` / `read_only_evaluation` 三个证人 ⇒ 只抹一个已不能让 `adjudicated - required` 变空 | 扩写成四个一起加，复跑 **RED** |

`--check-anchors` 21/21 命中（`_DOMAINS` 与 tasks.md 都被本轮改过，锚点未漂）。

### 5.3 Task 72 门的 out-of-band 登记（新增 M31 / M32，连同重锚的 M20）：**3/3 RED**

## 六、墓碑删除（用户点名的 out-of-band 清理）

删除对象：`audit-platform/frontend/src/components/workpaper/composables/useG7LonTerDualMode.ts`（231 字节）。

**四条依据独立复核结果（全部成立）**：

| 依据 | 复核方式 | 结果 |
|---|---|---|
| 内容只是 `@deprecated` 别名 re-export | 读全文 | ✅ 一条注释 + 一个 `export {...} from './useG7DualMode'` |
| `./useG7DualMode` 已被 Task 45 删除 ⇒ 死 re-export | 文件不存在；`test_task45_pilot_legacy_deletion.py` 把它列在已删清单；宿主 `GtG7LongTermEquityMain.vue` 注释写明改用 bridge | ✅ 且 `npx tsc --noEmit` 单文件实测 **TS2307 `Cannot find module './useG7DualMode'`** |
| 零 importer（含 `.vue`/`.ts`/测试/生成物） | 全仓库搜 `useG7LonTerDualMode` | ✅ 只有它自己 + Task 66 计划 JSON |
| Task 66 计划登记 | 计划 `items[43]`：`disposition=pending_delete`、`category=legacy_composable`、`sha256=b8e60abc…c8da` 与盘上逐字节相等 | ✅ |

AC 1.7 逐字：「不可达旧桩 SHALL 删除；不得以豁免或 `DEPRECATED` 注释长期保留」。

**Task 72 门的处理形态（没有放水）**：门里新增 `OUT_OF_BAND_REMOVALS` **有归属的登记**，
`validate_out_of_band_removals()` 对每条现场核验三件事 —— ①在 Task 66 计划的待删集合里 ②盘上确实
已不在 ③计划登记的 `disposition`/`category` 与登记声明一致。任一不成立即进 `verdict.structural_errors`。

* `paths_missing_from_disk` / `digest_drift_paths` **照旧全量报出**（分母没变小），另加
  `out_of_band_removed_paths` 与 `unexplained_*` 两组字段；结论口径改用 `unexplained_*`。
* **仅覆盖「整文件不在了」**：文件仍在、内容被改（digest 漂移）**永不**被登记豁免。
* `stage_b.executed` 仍 `false`、`files_deleted` 仍 `0`、`state` 仍 `blocked` —— Stage B 没有跑。
* 实测报告：`structural_errors = 0`，`unexplained_paths_missing_from_disk = []`。
* **Stage A 的 7 条失败谓词删前删后逐条同名同集合**（实测对照：恢复文件再删一次，两次都是同一组 7 条；
  被删那条只让 landing 的失败清单从 2 条变 3 条，`every_pending_delete_uniquely_lands_in_plan` 早已因
  2 条 `rollback_not_recoverable` 为红）。

**变异锚点（证明登记不能当万能豁免）**：M31 打掉「盘上还在就不算移除」的核验、M32 打掉「必须落在
计划里」的核验，两条都必须让 `test_planting_an_unrelated_path_in_the_registry_still_turns_the_proof_red`
打红 —— 实测 **RED / RED**。该测试本身还逐条断言三种伪登记（还在盘上 / 计划外 / disposition 不符）
各自被点名，并把伪登记喂进 `build_stage_b` + `build_verdict`，要求「磁盘未动」翻假且结构错误点名它。

## 七、测试结果

| 范围 | 结果 |
|---|---|
| `workpaper_sync/test_task74_domain_adjudication.py`（新建 10 条） | **10 passed** |
| `test_workpaper_writer_inventory.py`（Task 3，同批搬动 2 处） | **38 passed** |
| `workpaper_sync/test_task20_writer_gate.py`（同批搬动 1 处） | **32 passed** |
| `workpaper_sync_predelete/test_task72_pre_delete_eligibility.py`（+3 条） | **65 passed** |
| `workpaper_sync/test_task66_legacy_deletion_plan.py` + `test_task45_pilot_legacy_deletion.py` | 2 failed / 109 passed（归因见 §八） |

同批搬动的三处期望值（各有变异 falsifier）：

* `test_workpaper_writer_inventory.py::test_unified_revision_gate_is_red_and_names_every_reason`
  —— `assert issues["unadjudicated_writer"]` 改成 `assert not ...` **并补强**：门点名的每一行都必须
  在 overlay 里查到非空理由（原判据留了「本来就是未裁决行」这个逃生口，归零后该逃生口关闭）；
* `workpaper_sync/test_task20_writer_gate.py::test_the_gate_is_red_and_names_its_blocking_rows`
  —— 同上，并保留「门仍红 + Task 19 交接那一行仍在阻塞名单 + 理由文本仍含 `wp_id`/`10.6`/`12.7`」；
* `test_workpaper_writer_inventory.py::test_after_save_side_effect_handler_no_longer_moves_a_version`
  的**反向核查 3** —— 原来直接在活体清册上断言「清空退役台账 ⇒ `orchestrator_side_effect` 缺失」，
  而本轮该 domain 在 `entries` 侧也有了行。判据改在**构造**的清册上做（先摘掉 `entries` 侧该 domain，
  让台账重新成为唯一来源，并先断言构造出的清册本身仍绿，否则下一步证明不了任何东西）。

## 八、上游锁复跑与新增红归因

| 锁 | 基线 | 本轮 | 判定 |
|---|---|---|---|
| Task 67 | 2 failed（BP-72-8） | 2 failed | 与基线一致 |
| Task 68 | 0 | **3 failed** | **新增，逐条归因见下** |
| Task 69 | 1 failed（BP-70-6） | 1 failed | 与基线一致 |
| Task 70 | 1 failed（BP-71-8） | 1 failed | 与基线一致 |
| Task 71 自有锁 | 2 failed | 2 failed | 与基线一致 |
| Task 66 | — | 2 failed | **1 条新增（我的删除）+ 1 条既存** |

**Task 68 的 3 条新增红同一个根因**：本轮新建的守卫文件
`backend/tests/workpaper_sync/test_task74_domain_adjudication.py` 引用了 Task 68 追踪的那批模块 ⇒ 它
按**引用关系派生**的辐射面从 **94 → 95**。实测把新旧两侧求差集，唯一新增文件就是这一个
（`only fresh: ['backend/tests/workpaper_sync/test_task74_domain_adjudication.py']`，`only record: []`）。
三条失败分别是辐射面 digest、`surface_size`、以及现算判定 `failed` vs 记录 `passed`。
**没有重生成 Task 68 的报告** —— 那是上游产物，重生成会改 source commit 并再打红上游四把锁（BP-71-5
已踩过）。→ **BP-74-1**，owner Task 68。

**Task 66 的 2 条**：
* `TestThreeWayLock::test_every_item_path_exists_and_hash_matches_disk` —— **我的删除导致**（实测：
  恢复该文件后同一组 11 条全绿）。这是计划内路径被 out-of-band 移除的必然后果，Stage B 真执行后
  重生成计划即消。→ **BP-74-2**，owner Task 72 Stage B。
* `TestGeneratorIsIdempotentAndCheckIsStrict::test_check_matches_the_file_on_disk` —— **既存**（实测：
  恢复该文件后**仍然失败**，磁盘 `9d85cf620ba7` vs 现算 `6527f922ca3d`），并发会话改了计划覆盖面内的
  其它文件。→ **BP-74-3**，owner Task 66/并发方。

**Task 71 自有锁的第二条**（`test_upstream_lock_impact_is_measured_and_owned`）：它锁「全树 test 文件
计数的增量恰好是 1」。实测把我的守卫文件临时移出后仍不成立（2342 vs 2341 期望），说明**在我之前就已
经红**（并发会话也在加测试文件）；我的文件让增量再 +1。→ 与基线一致，不算新增。

## 九、BP 清册

| BP | 形态 | owner |
|---|---|---|
| **BP-74-1** | 新建守卫文件使 Task 68 引用派生辐射面 94 → 95，其冻结报告的 digest / `surface_size` / 现算判定三处过期 | Task 68 |
| **BP-74-2** | out-of-band 移除一条计划内路径 ⇒ Task 66 三边锁的「路径在盘上且 hash 相等」那一边失守 | Task 72 Stage B（真执行后重生成计划即消） |
| **BP-74-3** | Task 66 计划的 `--check` 逐字节锁**既存**失败（与本轮无关，恢复文件后仍红） | Task 66 / 并发方 |
| **BP-74-4** | `mutate_task20_writer_gate_guards.py` 的 M13 `want` 在 Task 30 改名后过期 ⇒ 真 RED 被判成 WRONG-TEST。**本轮已修**，但同类风险普遍存在：变异脚本的 `want` 是硬写的 nodeid，改名不会打红 | 平台级（建议给 `_mutation_kit` 加「`want` 必须在守卫文件里真实存在」的声明期校验） |
| **BP-74-5** | `bump_content_revision` 仍被记成 `bypasses_unified_commit` —— 谓词把「唯一允许移动版本的写入者」与「绕过统一入口的 writer」混在一个判据里。本轮只裁决 lane（`unified_commit_substrate`），**没有**动谓词 | 单独立项（Task 20 证据 §四.2 已建议） |
| **BP-74-6** | `writer_without_characterization_test` = 208 里有相当一部分是「真的有测试、但只经 HTTP 路由驱动」，谓词还不认路由证据 ⇒ 系统性低估覆盖 | Task 74 第二半 / 独立一块（Task 20 证据 §三.1 已登记） |
| 既存引用 | BP-70-6（Task 69 锁）· BP-71-3 · BP-71-5（重生成上游即级联 stale）· BP-71-8（Task 70 锁）· BP-72-8（Task 67 锁） | 各自 owner |

## 十、文件清单

| 文件 | 角色 |
|---|---|
| `overlay_before.json` / `inventory_before.json` | 改造前快照（`task74_rows` fixture 靠它做减法，界定「本轮加的那 270 条」） |
| `mutation_report.json` | N01–N07 逐条判定（7/7 RED） |
| `mutation_task20_rerun.json` | Task 20 变异全量复跑（18 RED / 2 GREEN / 1 WRONG-TEST） |
| `mutation_task20_rerun_m13_m19.json` | 两条非 RED 修好后的复跑（2/2 RED） |
| `gate_after.json` | 裁决后门的完整 issue map（`--json`） |
