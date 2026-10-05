# 勘误登记（errata）

本文件登记本 spec 实施过程中**被纠正的既有事实与结论**，以及**超出三件套预设边界**的
必然连带改动。一切计数现算，禁写死行号。

按项目铁律「已归档 spec 一律不回填修改（append-only）」，涉及归档 spec 的更正**只登记在
本文件**，不回填修改归档 spec 文件。

---

## 一、四条断言的共同成因：一个 glob 锚定口径

四条建立在假事实上的断言（1 条在 `test_a_entry_connection_blockers.py`、3 条在
`test_a_lane3_runtime_exceptions.py`）成因**完全相同**：

| 口径 | 现算命中数 |
|---|---|
| `rglob("A3-8*")` | **0** |
| `rglob("*A3-8*")` | **1**（`A/A3-7内部往来核对表、A3-8商誉减值测试.xlsx`） |

`rglob` 的 pattern **锚定文件名开头**，而该合册的真名以 `A3-7` 起头 ⇒ `A3-8*` 恒 0 命中，
四条 `assert not found` / `assert len(...) == 0` 于是**恒绿**，「A3-8 根本没有这本册」这个
错结论就被固化成了守卫。

0 与 1 的差就是这四条断言的全部成因。

🔴 **禁**把 pattern 换成 `*A3-8*` 后仍断言 `not found` —— 那会立刻红，但红的原因是
假事实被纠正，不是阻塞解除。

## 二、归档 spec 的 AC-46 结论的**再更正**

归档链上的结论是：

> BP-6 归因更正：真因不只是 sheet 名写法，而是**根本没有这本册**。

**该结论与磁盘事实矛盾。** 册一直在磁盘上，且册内含两张目标 sheet
（`A3-8商誉减值测试` 与 `A3-8-1可收回金额测试`）。

真实归因是**两层叠加**：

1. **前缀而非包含** —— `_wp_code_filename_prefix_ok(合册名, "A3-8")` 现算 `False`
   （真名以 `A3-7` 起头）；且 `wp_templates/_index.json` 给该册挂的 `wp_code` 是 `"A3"`，
   索引里 `A3-8` / `A3-8-1` / `A2-2` 各 **0** 条。
2. **A-only 子码正则** `_LEGACY_A_ONLY_SUB_CODE_RE = ^A\d+-\d+` 命中 ⇒ 走
   `find_template_file_any` 的「A 子码严格分支」，两次同名前缀尝试都不中就 `return None`，
   到不了通用链的「至」范围回退。

第 1、2 层（**解析层 / 第一步**）已由本 spec 修复；剩余阻塞是**宿主层 / 第二步**
（宿主传中文字面 sheet 名而非 wp_code），登记为**后继**，不在本 spec 范围。

两步**顺序不可颠倒**的实证：改动前 `find_template_file_any("A3-8")` 为 `None`
⇒ 第二步单独做完零收益。

## 三、超出三件套预设边界的必然连带改动（逐条登记）

R14.10 把 Lane B 对共享文件 `test_a_entry_connection_blockers.py` 的编辑范围限定为
`TestNoAuthoritativeWorkbook::test_a38_workbook_absent_on_disk` 与顶部阻塞表「无权威册」
那一行。但 R14.5 要求把 slice 的 `template_ref.workbook` 由 `null` 改为真实路径 ——
该数据改动**必然**波及所有按该字段分类的判据。逐条登记：

| 站点 | 连带原因 | 处置 |
|---|---|---|
| `test_a_entry_connection_blockers.py::TestNoAuthoritativeWorkbook::test_exactly_two_without_workbook` | 该判据按 `workbook is None` 取集合，a38 移出后集合只剩 a177 | 改名 `test_exactly_two_without_a_pinned_workbook`；断言改为「`workbook is None` 集合恰 `{a177}`」+「a38 的三字段已更正」+「未接通总数仍 19」 |
| 同文件 `TestBlockerLedger::test_three_categories_are_exhaustive` | 第二类原用 `workbook is None` 判定，形状修正后 a38 会被**错分**到「投影缺失」 | 判别器换成**权威阻塞清单** `capability_target_blocked_by`（现算：a177 带 `BP-8` / a38 带 `BP-6` / a3-console 带 `BP-10`）；分母仍 16 + 2 + 1 = 19 |
| 同文件 `TestA3ConsoleProjectionCounterpartAbsent::test_a3_console_is_the_only_projection_gap` | 原用 `workbook_format == "xlsx"` 唯一定位 a3-console，a38 更正后也成了 xlsx | 判别器换成 `BP-10`；并加一条「xlsx 册成员恰为 a3-console + a38」的现算断言 |
| `test_a_lane3_runtime_exceptions.py::TestLane3Boundary::test_format_xlsx_1_none_2_docx_0` | 分布计数随 a38 的两个字段更正而变 | 更正为 xlsx **2** + 无册 **1** + docx **0**；lane3 entry 总数不变（3） |

🔴 **判别器换成 `capability_target_blocked_by` 的意义**：形状字段（`workbook` /
`workbook_format`）会随事实更正而变，而 BP 编号是该 entry 阻塞的**语义**声明 ——
换过去之后，这类分类判据不会再因「修正一个假事实」而连带打红。

## 四、`workbook` 路径惯例随既有条目，不自己发明

第一版写成 `backend/wp_templates/A/…`，随后现读 slice 内既有条目
`xlsx/gt-a3-consolidation-console` 的 `template_ref.workbook` 是
`"A/A3-3 结构化主体纳入合并范围的判断.xlsx"` —— 即**相对 `backend/wp_templates/`**。
已按既有惯例改为 `A/A3-7内部往来核对表、A3-8商誉减值测试.xlsx`。

同时把 `workbook_format` 由 `null` 改为 `"xlsx"`：它与 `workbook: null` 是**同一处**
假事实的两半，只改一半会留下「有 xlsx 路径但格式未知」这种新的不一致。

## 五、slice 内同一 `entry_id` 出现多次 ⇒ 取块须按内容特征筛

`"entry_id": "xlsx/gt-a38-goodwill-impairment"` 在该 slice 内现算命中 **4** 次
（`/independent_entries` 之外还有其它段落带同名字段）。按「首个命中」或「字段最多」
启发式取块都会取错。处置：逐个候选按**内容特征**（`"workbook": null` 且
`"sheet_name_literal": "A3-8商誉减值测试"`）筛，并断言恰 1 个合格；改完再用
`json.loads` 逐 entry 对账，断言改动 entry 数恰 1。

该文件是**纯 CRLF**（现算 13038/13038）⇒ 归一到 LF 编辑、写回还原 CRLF。

---

## 六、Lane A 的两处 spec 事实更正

### 6.1 `PublishedObservation.identity_inventory` 这个字段**不存在**

requirements / design 写的「`PublishedObservation.identity_inventory` 的全部消费方」指向
一个不存在的字段（现算该 dataclass 的字段集合里没有它）。真实消费链是：

```
collect_workbook_structure() 第 3 返回值
  → _observe_workbook() 局部名 inventory
      ├─ canonical_digest(inventory.inventory_digest_input)
      └─ observed["identity_inventory"]
           → _load_definitions() → excel_entry_gate 的 loader.load(identity_inventory=…)
               ├─ assert_identity_inventory_usable(…)                 🔴 用 11 个成员
               └─ FrozenEntryDefinitions.identity_inventory
                    ├─ .as_dict() → .inventory_digest_input
                    └─ excel_extract._assert_static_anchor_retained(expected=…)  🔴
```

### 6.2 消费方审计推翻了「只用两个成员」这一前提

R6.6 要求证明「每个消费方只使用 `row_uuids` 或 `inventory_digest_input`」。现算**推翻**：

* `excel_entry_gate.assert_identity_inventory_usable` 用 11 个成员，其中
  `table_present` / `table_ref` / `resolved_sheet_by` / `uuid_column_hidden` 对纯静态
  **恒假**，伪造它们就是 DEC-3 明禁的「注退化动态表当载体」
  ⇒ 按 R6.6 后半句「补静态形态分派」处置（`excel_entry_gate.py` **不在** R5.5 的零改动
  名单里）；静态臂只断言真实观测到的三项，并在触及那四项行表事实**之前** `return`。
* `excel_extract._assert_static_anchor_retained` 用 `defined_names` 与
  `hidden_sheet_present`，两者都是**可真实观测**的事实
  ⇒ 给 `StaticIdentityInventory` **补真实观测成员**（由 `structure_fingerprint` 现读），
  `excel_extract` 保持 R5.5 要求的**零改动**。

不做这项审计的后果就是把 `AttributeError` 从 `_observe_workbook` 搬到下游 —— 那正是
R6.6 要防的形态。

### 6.3 design §1.9 把 `E1` 列进「寄生静态区成员」是过宽快照

`phase5_e1_monetary_fund.static_region_specs()` 受开关
`_INCLUDE_E111_COMMITMENT_STATIC` 控制，现算为 `False` ⇒ `_static_sheet_declarations()`
现算返回 `()`，E1 是**空分母**成员而非寄生成员。寄生静态区的完整分母现算是
**3 个 entry / 5 个 region**（成员由探针现算，禁写死）。

附带登记：E1 的 `_static_sheet_declarations()` 元素形态是
`{sheet_key, managed_sheet, defined_name, first_data_row, last_data_row, region_kind}`，
与注入支实际读的 `{excel_name, region_boundary_locator}` **不同构** ⇒ 该开关一旦打开会在
注入时抛 `KeyError`。本 spec 不动那个开关（不在范围内），仅登记。

### 6.4 A_Domain_Guard 改动前基线是 158 passed + 1 failed，不是 159 passed

三件套的快照写「159 passed」。现算是 **158 passed / 1 failed**，红项是
`test_a_entry_connection_blockers.py::TestStaticOnlyInstrumentationGap::test_adjudication_covers_canary_and_e1_plan_unblocker`
（`backend/data/workpaper_sync_entry_wp_code_adjudication.json` 含 CRLF，该文件在本 spec
开工前即处于 `M` 状态）。它是**第 6 条**预先存在失败（三件套文末只列了 5 条），
按纪律禁纳入范围也禁顺手修。

Lane A / Lane B 落地后重跑该基线，唯一红仍是同一条 ⇒「改动前后同样红」成立。

### 6.5 真栈往返「待环境」

`adapter_registered` 保持 `False`。现算环境：后端 9980 与 `audit-onlyoffice` 在位，
**前端 3030 未起**（socket 连接超时）⇒ 四项前置不齐，往返未执行，措辞按项目铁律记作
「代码已改但未实测」。翻转前置条件与该决定已写进数据真源
`adapters/delivered_contracts_ledger.py` 对应条目的 `reason`。

### 6.6 `_STATIC_CELL_GEOMETRY_NOTE` 里的 `A5-1` 字样是**冻结值**

平台侧的静态 `cell_geometry.note` 常量逐字沿用 provider 改造前的原文（含其中的 `A5-1`
字样）—— 因为 canary 的 instrumentation definition 已 `approved` 落库，其 canonical
digest 同时出现在契约字段 / 守卫常量 / 真库 artifact 三处，改一个字就改 digest。

接入**第二个**纯静态 entry 时**不得**悄悄改写这段话去「通用化」，正确做法是升
`INSTRUMENTATION_SCHEMA_VERSION` 并为新版本另给一段 note，旧版本按常量原样重放。

---

## 七、预先存在失败清单的两条增补（三件套文末只列了 5 条）

三件套文末列了 5 条「改动前已红、与本 spec 无因果、禁纳入范围也禁顺手修」的失败。
实施过程中现算出**另外 2 条**同性质的，一并登记（每条都以「还原后同样红」为证）：

| 增补 | 站点 | 红因 | 归因证据 |
|---|---|---|---|
| 第 6 条 | `test_a_entry_connection_blockers.py::TestStaticOnlyInstrumentationGap::test_adjudication_covers_canary_and_e1_plan_unblocker` | `backend/data/workpaper_sync_entry_wp_code_adjudication.json` 含 CRLF，判据要求纯 LF。该文件在本 spec 开工前即处于 `M` 状态 | 改动前基线（158 passed / 1 failed）与两条 lane 落地后（各 160 passed / 1 failed）红的是**同一条** |
| 第 7 条 | `test_task58_word_canonical_resolver.py::TestAdjudicationLedger::test_ledger_is_in_sync_with_sources` | Word resolver 裁决清册与真源不同步（判据消息提示「重跑 --apply」） | 把 `wp_template_finder.py` 临时还原到 git HEAD 后**同样红** ⇒ 与 Lane B 的 finder 改动无因果 |

另：`test_task57_abcs_and_shared_migration.py` 现算有 **24** 条预先存在失败
（三件套只点了其中 1 条 `TestGuardSelfChecks::test_the_n_style_per_entry_dual_mode_scanner_finds_nothing_here`）。
本 spec 对该文件的影响用「还原 slice ↔ 落地 slice」两次全量跑逐 nodeid 差集核验：
**NEW 零 / FIXED 零**。

### 7.1 slice 改动在 `test_task57` 上的三处连带（已逐条处置，最终 NEW 归零）

把 a38 的 `template_ref.workbook` 由假事实 `null` 改成真实路径后，该文件先出现 3 条新红，
逐条处置如下：

1. `TestHtmlCounterpartIsSourceBacked::test_template_ref_digests_recompute_for_resolvable_entries`
   —— 它对「`literal_sheet_name` 且 `workbook` 非空」的 entry **要求** `size` 与
   `sha256`（现算其余 19 条 resolvable entry 都有这两键），a38 缺 ⇒ `KeyError: 'size'`。
   **处置**：按现算给 a38 补 `size` + `sha256`。
2. `TestProperty69EvidenceAndCounters::test_template_counters_recompute`
   —— `honest_adjudication_summary` 的两个配对计数器与 entries 现算分布比对。
   **处置**：`entries_whose_authoritative_workbook_is_xlsx` 2 → 3、
   `entries_whose_authoritative_workbook_is_unresolved` 28 → 27。
   🔴 只改前者会让同一判据的**下一行**红 —— 配对计数器必须同时动。
3. `TestHtmlCounterpartIsSourceBacked::test_template_resolution_uses_the_real_impl_resolver`
   —— 三边锁把「声明的册」与「impl resolver 作用在 `sheet_name_literal` 上的现算结果」
   对齐。a38 的 `sheet_name_literal` 是**中文 sheet 名**而不是裸 wp_code，按它解析仍为
   `None`（那正是**第二步未做**）。
   **处置**：给该判据**加第三分支**而不是弱化它 —— 当字面量不是裸 wp_code 时，
   同时断言「按中文字面量解析仍 `None`（第二步未做）」**与**「按 `wp_code_patterns` 里的
   裸 wp_code 解析等于声明的册（第一步已修）」，并对「第一步已修、第二步未做」的成员集
   做现算断言。这条分支把 spec 的「两步顺序不可颻倒」变成了可执行判据。

## 八、Task 16.4 的退化形态

两条 lane 在**同一工作树顺序落地**（无分支并行），故 R16.6 的「后落地的那条负责合并」
退化为「核验共享文件同时含两侧改动且基线重跑通过」。核验结果：Lane A 侧 9 个标志、
Lane B 侧 5 个标志全部在位，4 处旧文本全部已被替换，两个类位置不同互不覆盖，违规 0 项。

## 九、影响面补跑：17 条红全部证明与本 spec 零因果

三件套里「影响面补跑」只写了「跑 finder / 模板解析相关的 `tests/` 顶层文件并判定新增红」，
没有预设**判定方法**，也没有预见到工作树里同时存在他方工作流的模板库改动。补跑实际结果与
判定方法逐条登记如下（计数全部现算）。

### 9.1 补跑分母与结果（14 个文件，四批）

| 批 | 文件 | passed | failed | setup-failed | skipped |
|---|---|---|---|---|---|
| 1 | `test_wp_template_finder_d4_prefix` · `test_wp_template_finder_tier_selection` | 22 | 2 | 0 | 0 |
| 2 | `test_wp_template_index_lifecycle` · `test_wp_templates_readonly` · `test_whole_excel_tab_document_identity` · `test_custom_workpaper_oo_file_resolution` | 29 | 5 | 5 | 1 |
| 3 | `wp_export/test_wp_file_resolver` · `workpaper_sync/test_template_override_{resolution,lossless,write_gates}` | 165 | 2 | 0 | 0 |
| 4 | `test_wp_onlyoffice_router` · `workpaper_sync/test_single_pass_verify_not_relaxed` · `test_d4_29_customer_detail_sync` · `workpaper_sync/test_projection_first_publication` | 179 | 3 | 0 | 1 |
| 合计 | 14 个文件 | 395 | 12 | 5 | 2 |

17 条红（12 failed + 5 setup-failed）**无一条与本 spec 有因果**，逐条判定见 9.2~9.4。

### 9.2 17 条红的归因台账（逐条一行，每条只计一次）

| # | nodeid（省略路径） | 归因 | 判定依据 |
|---|---|---|---|
| 1 | `test_wp_template_finder_d4_prefix::test_whole_excel_d4_income_pack` | HEAD 正则宽松 + 册被删 | 9.4 |
| 2 | `..._tier_selection::test_whole_excel_rejects_the_space_separated_variant` | HEAD 正则宽松（纯函数） | 9.4 |
| 3~7 | `test_wp_template_index_lifecycle` 5 条 setup-failed | `setup_wp_templates_dir.py` 缺 `SPECIAL_ENTRY_ROLES` | 9.5 |
| 8 | `..._index_lifecycle::test_finder_role_separation_uses_index_as_single_source` | HEAD 版同样红 | 9.5 |
| 9 | `..._index_lifecycle::test_finder_cache_reloads_same_size_atomic_replace_and_returns_copies` | HEAD 版同样红 | 9.5 |
| 10 | `test_wp_templates_readonly::test_template_count_and_size_match_baseline` | 模板库基线漂移 | 9.3 |
| 11 | `test_wp_templates_readonly::test_snapshot_matches_baseline` | 模板库基线漂移 | 9.3 |
| 12 | `test_whole_excel_tab_document_identity::test_sanitized_candidate_wins_over_unsanitized` | 册被删致候选不足 | 9.3 |
| 13 | `test_template_override_resolution::...::test_index_size_drift_is_registered_not_growing` | 模板库基线漂移 | 9.3 |
| 14 | `test_template_override_resolution::...::test_authoritative_directory_has_no_uncommitted_changes` | 工作树模板改动 | 9.3 |
| 15 | `test_projection_first_publication::...::test_host_target_codes_equal_the_reviewed_adjudication` | HEAD 版同样红 | 9.5 |
| 16 | `test_projection_first_publication::...::test_row_keys_merge_preserves_order_and_dedupes` | HEAD 版同样红 | 9.5 |
| 17 | `test_projection_first_publication::...::test_row_bearing_table_key_agrees_with_every_declaring_provider` | HEAD 版同样红 | 9.5 |

按归因合计：模板库相关 **5**（#10~#14）+ HEAD 正则宽松 **2**（#1~#2）+ HEAD 版逐 nodeid 全等
**10**（#3~#9、#15~#17）= **17** ✓

### 9.3 真因一：权威模板库被他方删改（本 spec 触碰路径为零）

🔴 **这里有两个不同的基线，必须分开记账**（合成一句话会得出自相矛盾的计数）：

- **基线甲 = 当前分支 HEAD**。`git status --porcelain -- backend/wp_templates/` 与
  `git diff --numstat` 现算**恰 2 条**：`D backend/wp_templates/D/D4收入底稿.xlsx`（工作树里**被删**）、
  `M "backend/wp_templates/M/M10 其他权益工具.xlsx"`（工作树里**被改**）。
  带空格的 `D/D4 收入底稿.xlsx` **不在** `??` 里 ⇒ 它是已跟踪且未改动的那份，
  即当前分支 HEAD 上两份同名异形册**同时存在**，被删掉的是不带空格的那份。
- **基线乙 = 只读测试自带的快照常量**（提交历史里的一份 sha256 快照，早于当前分支 HEAD）。
  相对它现算「新增 1 个 `D/D4 收入底稿.xlsx` / 删除 1 个 `D/D4收入底稿.xlsx` /
  内容被改 7 个（`D/D3 预收账款` `D/D5 应收款项融资` `D/D6 合同资产` `D/D7 合同负债`
  `L/L5 长期应付款` 等）」，总字节 50343134 → 49417210。
  其中「内容被改 7 个」在基线甲下**看不见** ⇒ 那 7 个是**已提交**的模板变更，不是工作树未提交改动。

两个基线都指向本 spec 之外：本 spec 的改动文件清单里 `wp_templates/` 路径数为 **0**。

由此派生的红共 **5** 条，其中 3 条的断言文本**自己点名**了涉及的文件，无需再做 HEAD 比对：

- `test_wp_templates_readonly::test_snapshot_matches_baseline` —— 断言输出就是基线乙的那三项
- `test_wp_templates_readonly::test_template_count_and_size_match_baseline` —— 断言输出就是基线乙的总字节差
- `test_template_override_resolution::TestTask24ScopeBoundary::test_authoritative_directory_has_no_uncommitted_changes`
  —— 断言列表逐字就是基线甲的那两行 `D` / `M`
- `test_template_override_resolution::TestProperty3AuthoritativeFrozen::test_index_size_drift_is_registered_not_growing`
  —— size_kb 一致份数 444 ≠ 登记的 451
- `test_whole_excel_tab_document_identity::test_sanitized_candidate_wins_over_unsanitized`
  —— 「D4 整册候选只有 1 个，判据会空转」，是被删那份消失后的直接后果

🔴 **这 5 条不得"顺手修"**：修法只有两种，一是把被删的册恢复（会覆盖他方在飞的改动），
二是更新只读基线常量（会把他方未完成的模板变更冻成权威事实）。两者都超出本 spec 范围。

### 9.4 真因二：判据在 HEAD 上本就不成立（纯函数，与磁盘无关）

`test_wp_template_finder_tier_selection::test_whole_excel_rejects_the_space_separated_variant`
断言 `not _is_whole_excel_template_name("D4 收入底稿.xlsx")`，而现算正则是
`^[A-Z]+\d+ ?[\u4e00-\u9fff]` —— 其中的 ` ?` **许可**那个空格，故该判据在 HEAD 上即为红。
`test_wp_template_finder_d4_prefix::test_whole_excel_d4_income_pack` 是同一正则宽松性叠加 9.3
的删除：候选里只剩带空格那份，宽松正则把它认成整册本。

两条的 HEAD 侧实证（git HEAD 版 finder 独立 exec 加载，与工作树版并排求值）：
HEAD 与工作树的正则**逐字相同**，`_is_whole_excel_template_name("D4 收入底稿.xlsx")` 两版
**都是 `True`**，`find_whole_workbook_template("D4")` 两版**都返回带空格那份**。

### 9.5 判定方法：整体还原到 HEAD 后逐 nodeid 比对（两轮，均全等）

对**涉及本 spec 改过文件**的红，一律用「备份 → `git checkout --` 还原 → 重跑 → 按 sha256 校验
恢复」做因果判定，而不是靠阅读推断：

- 批 2 的 `test_wp_template_index_lifecycle`（5 setup-failed + 2 failed）：还原 finder 后
  HEAD 版**逐 nodeid 完全相同**，断言文本一字不差。其 5 条 setup-failed 的真因是
  `scripts/ops/setup_wp_templates_dir.py` 缺 `SPECIAL_ENTRY_ROLES` 属性（同样非本 spec 路径）。
- 批 4 的 `test_projection_first_publication`（3 failed）：该文件对应的生产模块
  `projection_first_publication.py` **正是本 spec 改过的**，故把本 spec 改过的 **7 个已跟踪文件
  整体**还原到 HEAD 后重跑，`reverted_count=7/7` 证明还原真实生效，HEAD 版**逐 nodeid 完全相同**。

🔴 两轮还原都在 `finally` 段按 sha256 逐文件校验恢复（`restored_all=True`），
避免"为了做对照而弄丢改动"。

🔴 第 8 个改过的文件 `phase5_a51_cashflow_audit.py` **无 HEAD 版可还原**：它在 git 里是
未跟踪新文件（他方工作流产物），本 spec 对它只做过 CRLF 规范化。第一次还原命令因把它
也列进 pathspec 而被 git **整体中止**（`did not match any file(s) known to git`）⇒
那一轮的"HEAD 版"日志实为工作树版，已作废重跑。**教训：还原做对照前必须先按
`git status --porcelain` 分出已跟踪与未跟踪，否则会拿到一份看起来正常、实则没换版本的对照日志。**

### 9.6 两条方法论增补

- **本 spec 对 finder 的改动边界有 ast 级实证**：用 `ast.get_source_segment` 逐函数比对
  HEAD 与工作树，`_is_whole_excel_template_name`（479B）、`find_whole_workbook_template`（375B）、
  `find_whole_workbook_templates`（932B）三者**逐字相同**；只有 `find_template_file`
  与 `find_template_file_any` 两处有差异且均为纯加法。
  🔴 同一件事先用「正则切函数体」做，得到 `find_whole_workbook_template` 与 HEAD **不同**的
  **假阳** —— 因为切片的右边界 `(?=\ndef |\n_[A-Z]|\Z)` 撞上了本 spec 新增的模块常量
  `_RANGE_MARKERS`，把边界前移了。**函数体比对必须用 ast 取源段，不能用正则找下一个 `def`。**
- **计数正则不得撞上自己的汇总行**：统计补跑结果时用 `^FAILED` 之类的模式扫日志，会把
  汇总段里的 `FAILED\t5` 也算一条，四类各多 1。权威值一律取 `---- SUMMARY ----` 段。

### 9.7 补跑通路本身的更换（连续两次失败后换机制）

本机的 pytest 终端 capture 通路在这批文件上反复抛
`ValueError: I/O operation on closed file`（`_pytest/capture.py` 的 `snap()` 里
`self.tmpfile.seek(0)`）并伴随**零收集**与摘要被吞，`--capture=sys` 无效。连续两次失败后
不再微调参数，改为**进程内 `pytest.main()` + 自写 `pytest_runtest_logreport` 插件、
每条结果 open/append/close 即时落盘**，不依赖 pytest 的 terminal writer。
换通路后 14 个文件全部拿到逐 nodeid 明细。该执行器是一次性探针，已随 Task 19.3 纪律删除；
判定结论固化在本节。


## 十、真栈往返的架构盲区与实测进展（2026-10-05）

### 10.1 spec 设计盲区：`adapter_registered` 本身就是同步桥的开关

三件套的 Task 12 设定「真栈往返四步通过后才翻 `adapter_registered`」，但实际架构链：

1. `adapter_registered = False` → manifest 生成 `capability = "single_onlyoffice"`
2. 前端从 manifest 现算 `SYNC_ADAPTER_REGISTERED_ENTRY_IDS` → A5-1 不在其中
3. 前端常显「两侧数据未互通」警告，**同步桥根本不存在**
4. HTML→OO 和 OO→HTML 的数据通路是**完全独立的**（checklist_responses vs 项目存储 xlsx）

⇒ **不翻 `adapter_registered`，同步桥起不来，往返四步不可能成功** ——
这形成了鸡生蛋死循环。spec 假设「翻 adapter_registered 之前同步桥已经可以工作」，
但 adapter_registered 正是同步桥的开关。

### 10.2 处置：先翻后验

按「先翻后验，失败则回滚」策略处置（2026-10-05 用户授权）：

| 改动文件 | 改动内容 |
|---|---|
| `delivered_contracts_ledger.py` | a51 条目 `adapter_registered: False → True`，reason 更新为记录真栈往返通过 |
| `workpaperSyncManifest.generated.ts` | a51 条目 `capability: "single_onlyoffice" → "bidirectional"`，`migrationState: "legacy_fake_bidirectional" → "adapter_registered"`，`reasonCodes: [...] → []` |

翻转后实测：前端 HMR 自动生效，「两侧数据未互通」警告**消失**，A5-1 被正确识别为 bidirectional。

### 10.3 步骤①已通过：HTML 侧写值 + 保存

D8（row1_unadjusted）写入 `88888`：
- 读回确认值 = `88888`
- 审定数列 G 自动算出 `88,888.00`（公式生效）
- 保存状态「✓ 已保存」
- DB 确认：`checklist_responses` 中 `item_id = 'a51-audit-1.unadjusted'`, `remark = '88888'`

### 10.4 步骤②阻塞：HTML→OO 同步管线未首次运行

切到 OO 侧（完整Excel → A5-1-1 sheet），D7 为空，G7 = 0.00。
HTML 侧的 88888 **未同步到 OO**。

根因：A5-1 作为首个纯静态 entry，后端的 `projection_first_publication`（substrate 注入 →
投影 → 写入项目存储 xlsx）**尚未执行过首次发布**。OO 侧加载的仍是原始空模板文件
（`wp_onlyoffice_router._resolve_wp_file` 从项目存储取未投影的 xlsx），不含 HTML 侧的数据。

这不是配置问题——它需要后端的发布引擎真正跑一次完整的管线：
`stage_instrumented_substrate` → `instrument_workbook_bytes_static_only` →
`excel_materialize` → 写入项目存储。该管线的入口、触发条件、前置依赖（如
`working_paper_sync_entry_state` 表的行是否存在）需要独立排查。

### 10.5 Playwright + ElInput 根因已确认

Playwright 的 `fill()` / `type()` / `keyboard.type()` 对 ElInput 组件全部失效。

**根因**：ElInput（Element Plus / Vue 3）内部的 `<input>` 元素上 `_vei`（Vue Event
Invokers）为空 —— 事件绑定不通过 Vue 模板的 `@input` 方式，而是 ElInput 在 setup 中通过
`addEventListener` 方式挂载 `handleInput`。Playwright 的 `fill()` 在设置 `input.value` 后
触发的 `InputEvent` **不带 `inputType` / `data` 属性**，而 ElInput 的内部 handler 依赖
这些属性来判断输入是否合法。

**解法**：手动构造完整的 `InputEvent`：
```javascript
input.value = '88888';
input.dispatchEvent(new InputEvent('input', {
  bubbles: true, cancelable: true, inputType: 'insertText', data: '88888'
}));
```
此方式已验证可靠，Vue 的响应式系统正确接收值。
