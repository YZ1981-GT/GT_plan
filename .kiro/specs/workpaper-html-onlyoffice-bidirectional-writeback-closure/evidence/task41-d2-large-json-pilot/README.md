# Task 41 — D2 大 JSON 子表 Excel pilot（证据）

spec: `workpaper-html-onlyoffice-bidirectional-writeback-closure` · Wave 4 Task 41
Requirements: 6.9, 6.11, 6.12, 12.1, 12.2, 12.10, 14.1, 14.11
Properties: **P27 / P29 / P49 / P60 / P69**

> 真实 OnlyOffice 9.4 与真实浏览器未执行 ⇒ 本 pilot 整体保持 **UNVERIFIABLE**；
> `pilot_harness.assess_pilot_classes()[d2_large_json].status` 实测仍是 `unverifiable`，
> `pilot_coverage_summary()["all_verified"] is False`。

---

## 1. 冻结的 entry 与选型三条件（在真实数据上现推）

| 项 | 实测值 |
|---|---|
| `PILOT_ENTRY_ID` | `xlsx/gt-d2-accounts-receivable` |
| `assess_pilot_classes()[d2_large_json].candidate_entry_ids` | **1 个**（就是它）；`bidirectional` **0 个** |
| `independent_entry` / `parent_entry_id` | `true` / `null` |
| `wp_match.wp_code_patterns` | `["D2A"]` |
| `scenario_profile.profile_id` | `xlsx.editable.shared.single.room_service_wired.v1`（178 条 entry 的多数形态） |
| `required_scenario_set_digest` | `76d494560e931d51ef91c328e97348cf5d5a274599be8338c428f26aba590fdc`（B60 是 `984681c2…`，**不同**） |
| required scenario 条数 | **24**（`close_required=true` / `substituted=false`） |

### 🔴 第 2 条必要条件与 Task 40 **形态不同**

Task 40 用「wp_code 与 `wp_templates/_index.json` 精确相等」证明 `find_template_file()` 不会
回退到父级程序表。本 entry **不满足**它：`wp_code_patterns == ["D2A"]`，而索引里三份 D2 模板的
`wp_code` 都是 `D2`。那条判据的**目的**由三条实测事实等价满足，每条单独可打红：

| 判据 | 实测 |
|---|---|
| `find_template_file("D2A")` | `None` |
| `find_template_file_any("D2A")` | `None` |
| `find_all_template_files("D2A")` | `[]` |
| `D2A.yaml` 的 `template_path`（配置真源，`wp_code: D2A` 一一对应） | `backend/wp_templates/D/D2-1至D2-4  应收账款- 审定表明细表（Leap-常规程序）.xlsx` |
| 父码 `find_template_file("D2")` | **同一份文件** |

「零回退的最强形态是根本没有回退」：`D2A` 既不精确命中索引、`wp_templates/D` 下无以 `D2A`
开头的文件、`"-" not in "D2A"` 所以连子表回退分支都进不去。

判定逻辑在 `pilot_d2_large_json.assert_no_implicit_template_fallback()`（纯函数），
**观测器**在 `backend/scripts/gen/generate_pilot_d2_large_json_contract.py::observe_template_resolution()`
——`find_template_file*` 是 Task 19 清册登记的 non-canonical resolver 符号，放进 `backend/app/`
会给 Task 20 收口门增债（首轮实测：本函数被判成 `writer_resolver`，`.replace` 还被当成
artifact write）。清册生成器只扫 `backend/app`，脚本不在其内。

---

## 2. 逐 sheet 审核结论（openpyxl 直读权威模板）

权威模板 `D/D2-1至D2-4  应收账款- 审定表明细表（Leap-常规程序）.xlsx`
（🔴 `D2-4` 与 `应收账款` 之间**两个空格**），123,162 字节，
`sha256=31e7992ba1e83952620e1777d108b46f7e7817dcdc9484c07f079f1dd3af0afa`（跑完全部测试字节原样）。

工作簿 **11** 张 sheet，逐张审核后**只**声明第 8 张：

| # | sheet | 审核结论 |
|---|---|---|
| 1 | `底稿目录` | 元信息/索引号表，无受管业务行 ⇒ 不声明 |
| 2 | `应收账款实质性程序表D2A` | 程序清单（`a-program-console`），非大 JSON 子表 ⇒ 不声明 |
| 3 | `审定表D2-1` | 审定表（Tier A/B 属 D 循环既有取数域）⇒ 不声明 |
| 4–7 | `附注披露信息(上市公司）D2-1` / `（国企）D2-1` / `(上市公司)` / `(国企)` | 附注披露，走附注同步链 ⇒ 不声明 |
| **8** | **`明细表D2-2`** | **受管 sheet**：866KB 大 JSON 载荷唯一落点 |
| 9 | `坏账准备明细表D2-3` | 另一张表（`D2-bd-*` items）⇒ 本轮不声明 |
| 10 | `调整分录汇总表D2-4` | 调整分录 ⇒ 不声明 |
| 11 | `GT_Custom` | 平台自有隐藏 sheet ⇒ 不声明 |

> `excel_extract.managed_tables_of()` 对「受管 sheet 之外还声明了表」显式 fail closed，
> 一次 extract 只覆盖一张 sheet。守卫 `test_managed_sheet_is_one_of_eleven_and_only_it_is_declared`
> 把「11 张 / 只声明 1 张 / 只 1 个 table」写成硬判据。

### `明细表D2-2` 的真实网格

* dims `A1:AM35`，`max_column == 39`，28 处 merge。
* **两级表头 11/12 行**：行 11 给 24 个列组标题，其中三个横跨 6 列的账龄组
  （`I11:N11 期初审定账龄` / `T11:Y11 期末未审账龄` / `AC11:AH11 期末审定账龄`）的二级标题在行 12；
  其余 21 列都是 `X11:X12` 纵向合并 ⇒ `header_rows = 2`，**21 + 3×6 = 39 列**。
* **数据区 13..25 行**（`A25` 是模板占位 `……`）。
* **`Q/S/AB` 三列逐行有真公式**（13 行 × 3 列 = 39 次逐格比对全中）：
  `=E{r}+O{r}-P{r}` / `=Q{r}+R{r}` / `=S{r}+Z{r}+AA{r}` ⇒ `mode=formula` + 三段 `formula_mask`。
* 🔴 **`H`（期初审定余额）模板内无公式**（13 行逐格实测全为非公式）⇒ 契约以源 xlsx 为准判
  `editable`。前端 `useD2Detail.recalcRow()` 把它算成 `priorUnadjusted+priorAje+priorRje`，
  两侧口径不同是**存量**差异；`test_column_h_has_no_formula_in_the_template` 把它钉住：
  模板哪天真加了公式，守卫立刻打红。
* **`A26 合计` 是 footer**（`E26..AH26` 全是 `SUM(x13:x25)`）⇒ `footer_anchor = {marker: 合计,
  search_column: A}`，不写死行号。
* 行 27 `账龄占比` / 28 `账龄逻辑校验` / 29 `三、审计说明：` / 33 `四、审计结论：` 属未管理区域。
* 隐藏 row UUID 列取 **`AN`**（`managed_last_col=AM` 右侧第一列，模板里为空）。

### 逐字段 `source_ref`（39 个，全部指向真实单元格）

`source_ref = 源xlsx!明细表D2-2!{列}13`（第一条数据行）；
`header_source_ref` 指向表头格（账龄列 → 行 12，其余 → 行 11）；
账龄列额外带 `group_source_ref` 指向组标题格。

| 列 | `column_key` | mode | value_type | `header_source_ref` | 表头实测文本 | store json 路径 |
|---|---|---|---|---|---|---|
| A | `seq` | editable | integer | `A11` | 序号 | `seq` |
| B | `customer_name` | editable | text | `B11` | 客户名称 | `customerName` |
| C | `company_code` | editable | text | `C11` | 公司代码 | `companyCode` |
| D | `relation_type` | editable | enum | `D11` | 关联方类型 | `relationType` |
| E | `prior_unadjusted` | editable | amount | `E11` | 期初未审余额 | `priorUnadjusted` |
| F | `prior_aje` | editable | amount | `F11` | 期初账项调整 | `priorAje` |
| G | `prior_rje` | editable | amount | `G11` | 期初重分类调整 | `priorRje` |
| H | `prior_audited` | editable | amount | `H11` | 期初审定余额 | `priorAudited` |
| I–N | `aging_prior_{within1,y1to2,y2to3,y3to4,y4to5,over5}` | editable | amount | `I12`..`N12` | 1年以内 / 1-2年 / 2-3年 / 3-4年 / 4-5年 / 5年以上 | `agingPrior/{段}`（组标题 `I11 期初审定账龄`） |
| O | `debit_occurrence` | editable | amount | `O11` | 借方发生 | `debitOccurrence` |
| P | `credit_occurrence` | editable | amount | `P11` | 贷方发生 | `creditOccurrence` |
| **Q** | `end_balance` | **formula** | amount | `Q11` | 期末余额 | `endBalance` |
| R | `reclassification` | editable | amount | `R11` | 被审计单位重分类调整 | `reclassification` |
| **S** | `current_unadjusted` | **formula** | amount | `S11` | 期末未审余额 | `currentUnadjusted` |
| T–Y | `aging_current_*` | editable | amount | `T12`..`Y12` | 同六段 | `agingCurrent/{段}`（组标题 `T11 期末未审账龄`） |
| Z | `current_aje` | editable | amount | `Z11` | 账项调整 | `currentAje` |
| AA | `current_rje` | editable | amount | `AA11` | 重分类调整 | `currentRje` |
| **AB** | `current_audited` | **formula** | amount | `AB11` | 期末审定余额 | `currentAudited` |
| AC–AH | `aging_audited_*` | editable | amount | `AC12`..`AH12` | 同六段 | `agingAudited/{段}`（组标题 `AC11 期末审定账龄`） |
| AI | `credit_risk_classification` | editable | enum | `AI11` | 信用风险组合方式 | `creditRiskClassification` |
| AJ | `group_name` | editable | text | `AJ11` | 组合名称 | `groupName` |
| AK | `is_confirmation` | editable | **boolean** | `AK11` | 是否函证 | `isConfirmation` |
| AL | `post_payment` | editable | amount | `AL11` | 期后回款 | `postPayment` |
| AM | `remark` | editable | text | `AM11` | 备注 | `remark` |

覆盖计数硬判据（空集恒等价不算通过）：**39** 字段 / **36** editable / **3** protected /
**39** 次表头文本比对 / **18** 次组标题比对 / **39** 次公式逐格比对（3 列 × 13 行）/
**13** 次 H 列无公式比对 / 未管理区域 **8** 个 aspect 覆盖计数
（`4 / 593 / 17 / 10 / 2 / 13 / 498 / 3`，`part_count=50`）全部 > 0。

### 三源锁死

1. **源 xlsx** 行 11/12 的真实文本 → openpyxl 直读比对；
2. **前端列真源** `useD2DetailColumnPrefs.ts::FIXED_COLUMNS`（**21** 条，键序与 Excel 列序逐项相同）；
3. **账龄真源** `useAgingConfig.ts::PRESET_SEGMENTS.FIVE_YEAR`（**6** 段 key/label，与行 12 六个二级表头逐字相等）。

---

## 3. 866KB 载荷：实测大小与拆法

真实项目底稿 `wp_id=e2c95d10-181d-4549-8910-d5ab5bc5edd1`（`public.checklist_responses`，**只读**）：

| 项 | 实测 |
|---|---|
| `D2-*` item 条数 | **24** |
| `remark` 合计字节 | **915,155** |
| `item_id='D2-detail-rows'` 单条字节 | **906,239** = 885.0 KiB = 0.864 MiB（AC 6.12 的「866KB+」量级） |
| 该条 `sha256` | `6c5d6d4c33f0b1393a59612c9dc3a7c3b42348bbb5ce5c60b4153aa40215950e` |
| 行数 / 唯一行身份 | **1260 / 1260**（零重复、零空值） |
| 每行键数 | **25**（22 标量 + 3 个 aging 嵌套对象 × 6 段 ⇒ **每行 40 个叶子**、`rowId` 之外 **39 个受管字段**） |
| 拆出的 stable field | **1260 × 39 = 49,140** |
| `iter_store_rows` tracemalloc 峰值 | 2,698,857 字节（< 16 MiB 流式内存预算） |

**拆法**：整张表今天在库里就是这一条 `remark` 里的一个 JSON 数组字符串（**字面意义上的
「整 JSON 一个字段」**）。本 pilot 把它拆成

```
receivable_detail_rows/{rowId}/{column_key}   ← 39 个 column_key
```

* 行身份取载荷里**已有**的 `rowId`（形如 `dr-mrgi0qg1-fwwmgum`）⇒
  `row_identity.json_pointer = /rows/*/rowId`；数组下标**永不**进入任何 key
  （守卫断言 projection 键里没有 `/\d+/` 形态）。
* 嵌套 aging 对象展开成 18 个**独立**字段（`aging_prior_y2to3` 等），
  嵌套对象本身不是字段。
* 流式：`iter_store_rows` 逐行 yield，`build_store_projection` 逐行喂 Task 37 的
  `StreamingProjectionBudget`（本模块不含任何阈值数字）。
* 四类坏载荷各自 fail closed 且**错误分型互不相同**（`StorePayloadError` vs
  `PilotSelectionError`，集合基数 == 2）：非数组 / 非对象元素 / 非法 JSON / 缺 `rowId` / 重复 `rowId`。

---

## 4. 五个 digest

| 项 | 值 |
|---|---|
| authority model definition | `canonical_digest(authority_model_payload())`（真库侧比对通过；`projection_contract` / `merge_model=stable_field_three_way`） |
| template definition | `canonical_digest(template_definition_payload())`（含 `normalized_structure_hash`） |
| instrumentation definition | `canonical_digest(instrumentation_definition_payload())` |
| **per-entry contract canonical** | **`bdd2f6494185777ce429ea04940510bcf6cf59c4f8a837c48251a4b4dfc86007`**（磁盘 29,516 字节 / 39 字段 / 3 protected） |
| definition bundle canonical | 每次发布新 UUID；真库侧 `bundle_canonical_digest()` 重算逐字相等（`test_bundle_digest_matches_the_canonical_recompute`） |
| 权威模板 blob | `31e7992ba1e83952620e1777d108b46f7e7817dcdc9484c07f079f1dd3af0afa` |

磁盘契约 ↔ 现算 payload **双向锁死**；两个生产入口
（`publish_pilot_definitions` / `attach_pilot_adapters`）都必须经
`assert_contract_file_matches_source()`（AST 判据，Task 40 的 M26 教训）。

---

## 5. finalize 现状：被登记的上游缺口挡住（照 Task 40 处置）

`adapter_registered=False` 是**顺序**而不是遗漏：任务正文要求「仅在 Task 36 将其 non-current
candidate finalize 为 published representation 后启用 adapter/宿主」，而 finalize 被欠账 ① 挡住。
处置 = **fail closed 抛可分辨异常、绝不返回 `None`**；manifest capability 仍是
`single_onlyoffice` / `adapter_id=null`；sync manifest digest **未变**
（`8b4f15a5e012f71870cdffb533c906968bb43c036cb9725fd4ec9428a039ef28`）；
契约孤儿由 `RegistryReport.contract_files_without_adapter` 持续可见。

### 三条登记的上游缺口

| # | 缺口 | 可打红的实测判据 | owner 建议 |
|---|---|---|---|
| ① | `UPSTREAM_DEBT_PUBLISHED_IDENTITY_OBSERVER`（与 Task 40 同一条）：缺「published representation artifact → `FrozenEntryDefinitions`」的公共观测器 | `resolve_published_frozen_definitions()` 抛 `PilotSelectionError`，`test_resolve_published_definitions_never_returns_none` | engine 侧（Task 38 后续） |
| ② | **本任务新发现** `UPSTREAM_DEBT_DYNAMIC_FAMILY_GATED_ON_MOUNT_CARDINALITY`：AC 6.9 自己的场景 `dynamic_row_add_delete_reorder_copy` 只在 `scenario_profile.mount_cardinality == "dynamic"` 时进 required set，而该字段量的是**前端宿主挂载基数**。实测全 manifest **186** 条 entry 里 `dynamic` **只有 1 条且是 docx**（`docx/gt-wp-renderer`）⇒ 该场景对**任何 xlsx entry** 结构性不可达，包括 AC 6.9/6.12 点名的 D2 与 Tasks 42/43 的 H1/G7 | `assert_dynamic_family_is_unreachable_for_xlsx_entries()` +「把本 entry profile 改成 dynamic ⇒ 必抛」的反向自检；`test_dynamic_family_gate_reads_mount_cardinality_not_the_contract` 从 `evidence.py` 源码取门的形态 | evidence 推导侧（Task 39 后续）。修法需把 contract 的 `row_identity` 声明喂进 required-set 推导，会改动 H1/G7 的 required digest ⇒ 设计级变更 |
| ③ | **本任务新发现** `UPSTREAM_DEBT_BOOLEAN_CELL_ROUNDTRIP`：`value_type=boolean` 的 Excel 受管格端到端不自洽 —— `excel_materialize._write_kind_for(boolean)` 归 `number_literal`、`_render_number(True) == "1"` ⇒ 落盘 `<v>1</v>`（无 `t="b"`）；extract 读回 int `1`；`merge.normalize_value(1, boolean)` 明令拒绝 0/1 折叠 ⇒ **每行一条 `type_normalization_failure`** | `TestBooleanCellIsAKnownUpstreamIncoherence` 四条：写入形态 / 规范化拒绝 / 实测 13 行异常且**只**落在 `is_confirmation` / 反向自检（写成真 `t="b"` 布尔格 ⇒ 异常归零、507 字段、值集合 `{True, False}`） | engine 侧（Task 37/38 后续）。二选一：`_write_kind_for` 对 boolean 写真布尔格，或 `normalize_value` 对 boolean 折叠 0/1 |

> 缺口 ③ 为什么**不**靠改 `value_type` 绕开：`is_confirmation` 的类型真源是前端
> `useD2Detail.DetailRow.isConfirmation: boolean`，改成 `text`/`enum` 就得在拆分里自造一个
> bool→「是/否」映射（无来源自造字段，Requirement 6.1 明令禁止）。变异 **M36** 就是这条：
> 把它改判成 `text` 必须打红。

---

## 6. Property oracle 落点

| Property | 落点场景（**本 entry 自己的 required set 里**） | 今天的判定态 |
|---|---|---|
| **P27** delete/update 冲突不整表覆盖 | `different_field_merge` + `same_field_conflict_resolve` | `passed`（离线可判定；真库侧在**真实 1260 行**上跑 delete/update oracle） |
| **P29** materialize/extract roundtrip | `oo_to_html` | `unverifiable`（需真实 OO forcesave） |
| **P49** 四类 pilot 均覆盖 | `identity_retention` | `unverifiable`（AC 6.16 明令真实 OO 9.4 黑盒探针） |
| **P60** 大文件预算 fail visible | `oo_to_html` | `unverifiable`（场景态）；预算判据本身在**真实载荷**与真实 artifact 上端到端跑通 |
| **P69** evidence 由逐 scenario 实体闭合 | `single_participant_close` | `passed` |

🔴 **P27 为什么不落 `dynamic_row_add_delete_reorder_copy`**：那是 AC 6.9 自己的场景，但受缺口 ②
影响对任何 xlsx entry 都进不了 required set。落在 merge 家族两条（真实存在于分母里）+ 在真实
1260 行载荷上跑 oracle，是「不放宽判据、也不假装场景存在」的唯一诚实解。

---

## 7. required scenario set 与逐场景结果（真库 run）

24 条，`required_scenario_set_digest = 76d49456…`，`open_run` 的 digest 与 plan 现推一致。

| 结果 | 条数 | 场景 |
|---|---|---|
| `unverifiable` | **10** | `html_to_oo` / `oo_to_html` / `identity_retention` / `frozen_base_status_6_2_dedupe` / `browser_crash_no_userdata_recovery_case` / `refresh_required_reopen` / `two_user_close_order_a_then_b` / `two_user_close_order_b_then_a` / `b_close_before_a_forcesave_terminal` / `b_close_after_a_forcesave_terminal` |
| `failed` | **2** | `same_application_higher_sequence_fold`（Task 32 欠账：room latest-durable 无读路由）/ `wrong_prior_confirmation_bundle_fence_contributor_rejected`（Task 32 欠账：claim 不校验 generation/fence/bundle/contributor） |
| `passed` | **12** | 其余（含字段级两条、`download_only_zero_three_entities`、四条 close/leader、`rollback`、`quarantined_*`、`cross_participant_idempotency_409`、`opaque_version_rollback_*`、`authorization_first_recovery_claim`、`single_participant_close`） |

* **判定顺序不可交换**：两条上游缺口场景是 `failed` 而**不是** `unverifiable`
  （缺的是实现不是环境；判成 unverifiable 会让接上 OO 后自动变绿）。
* `aggregate_result = failed`（**不是** passed）⇒ Property 49 后半句成立。
* 24 条 required == 24 行 persisted（分母 == 分子）；实体零复用，且故意复用同一
  operation/application 时第二条被 `HarnessRejected` 拒。
* `ScenarioObservation` 无 `result` 字段、`record_scenario` 无 `result` 入参、
  `finalize_run` 无 `aggregate_result`/`verified_at` 入参。

---

## 8. 分块 sidecar 与预算：N-1 / N / N+1 实测

### 真实载荷（1260 行 / 49,140 字段）

| 边界 | N-1 | N | N+1 |
|---|---|---|---|
| `max_table_rows` | **REJECT** `budget=max_table_rows observed=1260 limit=1259` | 通过 | 通过 |
| `max_projection_fields` | **REJECT** `budget=max_projection_fields observed=49140 limit=49139` | 通过 | 通过 |

生产预算是单一真源（`max_table_rows=100000` / `max_projection_fields=200000`），真实载荷远在界内；
`test_production_limits_are_the_single_source` 断言本 pilot 源码里**不出现**任何阈值数字。

### 三侧真样本（观测量相对固定预算）

`max_table_rows=5` 下喂 4 / 5 / 6 行真实形态数据 ⇒ 前两者通过、第三者
`BudgetExceededError(observed=6, limit=5)`。

### 端到端挂在 extract 上（真实 instrumented 工作簿，13 行 × 39 = 507 字段）

| 边界 | 实测 |
|---|---|
| `max_table_rows` | N=13 通过、N-1=12 REJECT（`observed=13`） |
| `max_projection_fields` | N=507 通过、N-1=506 REJECT |
| `max_zip_entries` | =entries 通过、-1 REJECT |
| `max_compressed_bytes` | =size 通过、-1 REJECT |
| 越界中止 | sidecar 半成品被删（`not sidecar.exists()`）—— 不留被截断的 gzip |

### 分块 sidecar

| 项 | 实测 |
|---|---|
| `rows_per_chunk(load_limits())` | **64**（= `peak_memory_budget_bytes // chunk_bytes` 派生，非写死） |
| 缩小预算 `chunk_bytes * 4` ⇒ | `rows_per_chunk=4`、`chunk_count=4`（`ceil(13/4)`），且 projection 值集合与不分块**完全相同** |
| 真实 49,140 字段 sidecar | gzip NDJSON、字段数 49,140、header `contract_id/table_key/schema_version` 正确、**两次导出逐字节相同**（`mtime=0` + `filename=""`）、体积 < 906,239 字节 |
| 峰值内存 | `tracemalloc` 实测 < `peak_memory_budget_bytes`（16 MiB） |

---

## 9. Property 27 在真实载荷上的实测（不覆盖其他 item/section）

一侧删第 8 行（`dr-mrgi0qg1-5n3nhbe`）、另一侧改同一 `rowId` 的 `remark`：

| 判据 | 实测 |
|---|---|
| 冲突条数 | **1** |
| 冲突 kind | `delete_update`（唯一） |
| 冲突键 | `receivable_detail_rows/dr-mrgi0qg1-5n3nhbe/remark` |
| 涉及冲突的行 | 只有受害行 |
| 受害行 lifecycle / held | `delete_update_conflict` / `True` |
| **其余 1259 行 × 39 = 49,101 个字段逐字段与 base 相同** | 不符 **0** 条 |
| 其余行被 hold | **0** 行 |
| 重排 1260 行（首行确实变了） | 冲突 **0** |
| 新增一行（39 个字段） | 冲突 **0**，新行进 merged、既有行完好 |
| 同一底稿另外 **23** 条 item | 一个都不在契约声明里；merged 的键前缀只有 `receivable_detail_rows`；merged 的 row_key 全是载荷自己的 1260 个 |

> 「不覆盖其他 item/section」是**非空**判据：1259 个其他行 + 23 个其他 item。
> 契约里每个字段都带 `store_item_id = D2-detail-rows`，且守卫用正则确认契约里
> 不出现任何别的 `D2-*` item id。

---

## 10. 变异检验（46 条，全部 RED）

脚本 `backend/scripts/diagnose/mutate_task41_d2_large_json_pilot_guards.py`
（`--check-anchors` 实测 **46/46 OK、0 MISS**，只读性核验通过）。

| 批次 | 落盘 | 结果 |
|---|---|---|
| M01–M11 | `mutation_batch1.json` | 10 RED + **1 WRONG-TEST（M10）** |
| M12–M22 | `mutation_batch2.json` | 11 RED |
| M23–M33 | `mutation_batch3.json` | 11 RED |
| M34–M44 | `mutation_batch4.json` | 10 RED + **1 ANCHOR-MISS（M37）** |
| M10 / M37 复跑 | `mutation_batch5_refix.json` | 2 RED |
| M33/M34/M41/M42（接线修法后复跑） | `mutation_batch6_after_attach_fix.json` | 4 RED |
| M45 / M46（接线分支新增） | `mutation_batch7_attach_branch.json` + `mutation_batch8_m46_refix.json` | 2 RED（M46 首轮 offset 差 1 ⇒ ANCHOR-MISS，修正后 RED） |

### 首轮非 RED 逐条归因（**全部是脚本缺陷，不是生产代码问题**）

| id | 首轮判定 | 根因 | 修法 |
|---|---|---|---|
| **M10** | WRONG-TEST | `want` 写成 `TestAuthoritativeTemplate::…`，而该测试住在 `TestFrozenEntrySelection`。`_mutation_kit.cli._locate_want()` 只比 nodeid **末段（方法名）**，类名写错 `--list`/`--check-anchors` 都查不出来（Task 40 的 M14 同款） | 改 `want` 的类名 → RED |
| **M37** | ANCHOR-MISS | `scope_check` 用 `json.dumps(True)` ⇒ 比的是 `true`（小写），而 `registry.py` 里是 Python 字面量 `True` ⇒ 作用域自证恒失败 | `_ledger_row_field_is` 改收**源码字面量** → RED |
| **M46** | ANCHOR-MISS | `scope + offset` 差 1（docstring 行数） | offset 10 → 11 → RED |

### 覆盖的判据分类

模板哨兵 2 · 选型必要条件 8 · 契约↔源侧双向锁 12 · 三源列锁 2 · authority/DAG 2 ·
载荷拆分 6 · 顺序门与三条欠账 4 · 交付登记 2 · 生产接线 4 · 真库发布 2。

---

## 11. 辐射面（AST 级推导，非词面搜索）

`backend/scripts/diagnose/select_task41_radiation.py` → **41 个测试文件**
（分母：`backend/tests` 下 **2300** 个）。

* 首轮：**12 failed / 2450 passed / 45 skipped**（6m49s）。
* 修完真实缺陷后：**4 failed / 2460 passed / 45 skipped**（6m45s）。
* 剩下的 4 条是**既有红**，与本任务无关：`backend/tests/integration/test_render_pipeline_e2e.py`
  的四条（"期望 ≥14 个手工 YAML，实际 0" / 总 schema 数 0 / componentType 白名单含约 200 个
  意外项）。它们被拉进辐射面只因为本任务的证据清单里含 `D2A.yaml` 这个**文件名**；
  `git status -- backend/data/ledger_adapters/` 实测**零改动**，且四条在**单独运行**
  `test_render_pipeline_e2e.py` 时同样红（4 failed / 16 passed / 37 skipped）。

### 🔴 辐射面抓出的真实缺陷（本任务引入，已修）

`test_task28_sync_router_pg.py` 首轮 **8 例打红**：

```
PilotSelectionError: entry xlsx/gt-d2-accounts-receivable 的 manifest capability=single_onlyoffice
  @ wp_sync_router.py:506 <- wp_sync_router.py:518 <- wp_sync_router.py:1845
```

根因：Task 28 的路由守卫 `ENTRY = "xlsx/gt-d2-accounts-receivable"` —— 正是本 pilot 冻结的
entry。它的 fixture 里有 entry_state + published representation + bundle，于是我的
`attach_pilot_adapters` 走到 `assert_manifest_capability_enabled()` 并**抛异常**，
把 `_registration` / `_apply_durable_incoming` 对**所有** entry 都变成 500 ——
一个尚未启用的 pilot 把整条 sync 路由拖下水。

修法（不是放宽判据）：

* 新增真值判定 `manifest_capability_enabled()`，实现**委派**给
  `assert_manifest_capability_enabled()`（只把它的异常翻成布尔，`except` 只捕获
  `PilotSelectionError` 这一个窄类型 —— 宽 `except Exception` 会把 manifest 读不出来
  之类的真故障也吞成「未启用」）；
* `attach_pilot_adapters` 把「capability 未启用」当成与「还没 finalize」**同一类事实**：
  提前 `return ()` 且**一次库都不读**；
* 顺序门本身没动：守卫直接调 `assert_manifest_capability_enabled()`（变异 M33 仍 RED），
  本 entry 在 registry 里依旧没有 adapter ⇒ `_registration` 以 422 `adapter_not_ready`
  收场（fail visible），契约孤儿仍在 `contract_files_without_adapter` 里；
* 新增两条守卫（`test_capability_predicate_agrees_with_the_ordering_gate` /
  `test_attach_is_a_no_op_before_enablement_and_never_raises`，后者传 `session=None`，
  「返回空元组」同时证明了「没读库」）与两条变异（**M45 / M46**）。

修完 `test_task28_sync_router_pg.py` **47 passed**。

> 跨 pilot 观察（**Task 40 文件领地，本任务未改**）：`pilot_simple_checklist.attach_pilot_adapters`
> 有**同款**潜在缺陷（同一位置抛 `assert_manifest_capability_enabled()`）。它今天不发作只因为
> 没有守卫用 `xlsx/b60/gt-b60-bundle` 当 fixture entry。建议 Task 40 owner 按同一修法收口。

---

## 12. 测试与门禁实测值

| 项 | 实测 |
|---|---|
| `test_task41_d2_large_json_pilot.py` | **108 passed** |
| `test_task41_d2_large_json_pilot_pg.py` | **37 passed** |
| 两者合计 | **145 passed** |
| `backend/tests/workpaper_sync/`（整目录） | **3507 passed / 0 failed / 0 errors**（7m55s） |
| `test_task28_sync_router_pg.py`（修后） | 47 passed |
| 辐射面 | 41 文件 / 2460 passed / 4 既有红 |

### 六门禁

| 门禁 | 实测 |
|---|---|
| `check_workpaper_writer_revision_gate.py` | `rows=319 writers=269 resolvers=71 retired=3`、`multi_resolver=4`、`unadjudicated_writer=236`、`unadjudicated_resolver=34`、`non_canonical_resolver_only=63`、`bypasses_unified_commit=261`、`writes_legacy_version_field=5`、`owns_direct_commit=105`、`writer_without_characterization_test=208`、`missing_required_domain=0`、**`total blocking facts=916`**、`[BLOCKED]`（Task 20 按设计留红）—— **与基线逐项相同，零新增欠账** |
| `generate_workpaper_writer_inventory.py --check` | `[OK] inventory digest b2bde05b4a25bc5b51f01914d4589836326a5884b4c4812e56bc3a503e46e58b`（**未过期**：本模块 0 条 writer/resolver 行） |
| `generate_workpaper_resolver_migration_matrix.py --check` | OK、`row_count=78 migrated=14 deferred=64 regressed=0` |
| `generate_workpaper_sync_frontend_contract.py --check` | OK、digest `ca3b003aeaad2f154677a9f9e499fd66e306c5ff49882c169ccc720fa0056c5b` |
| `generate_workpaper_sync_manifest.py --check` | OK、digest `8b4f15a5e012f71870cdffb533c906968bb43c036cb9725fd4ec9428a039ef28`（`entries=186 / independent=142 / parent_duplicates=43 / unadjudicated=136 / unreachable=1`）—— **未变**（capability 未启用） |
| `generate_workpaper_word_template_adjudication.py --check` | OK、50 行、`unadjudicated=0` |
| `generate_pilot_d2_large_json_contract.py --check`（新增） | `OK d2.receivable_detail.json bytes=29516 fields=39 protected=3 canonical_sha256=bdd2f649…` |
| `check_workpaper_ac_coverage_gate.py` | exit 1 **既有状态**（Task 8 的 `no_property_oracle=101` 债） |

**新迁移 V 号：无**（本任务不需要 schema 变更；沿用 Task 9 的 V151）。

---

## 13. 交付清单（🔴 全部 `??` 未跟踪）

`git status --porcelain` 实测本任务 9 个产物全是 `??`（本工作树的 `backend/app/**` 与
`backend/tests/**` 整体未跟踪）：

```
?? backend/app/services/workpaper_sync/pilot_d2_large_json.py         （新建）
?? backend/app/services/workpaper_sync/adapters/registry.py           （只加不动：登记表追加第二条）
?? backend/app/routers/wp_sync_router.py                              （只加不动：两个接线点各加 D2 attach）
?? backend/data/workpaper_sync_contracts/d2.receivable_detail.json    （新建，29,516 字节）
?? backend/scripts/gen/generate_pilot_d2_large_json_contract.py       （新建）
?? backend/scripts/diagnose/mutate_task41_d2_large_json_pilot_guards.py（新建）
?? backend/scripts/diagnose/select_task41_radiation.py                （新建）
?? backend/tests/workpaper_sync/test_task41_d2_large_json_pilot.py    （新建）
?? backend/tests/workpaper_sync/test_task41_d2_large_json_pilot_pg.py （新建）
```

加上本 evidence 目录。**丢工作树即全部蒸发**，且挂进 CI 的 job 在干净 checkout 下必挂
（本 spec 的守卫套件目前**没有**任何 CI job，`governance-checks.yml` 未被本任务触碰）。

`backend/wp_templates/` 与 `backend/data/ledger_adapters/` 实测零改动；真实底稿
`checklist_responses` 只读（跑完 sha256 复核仍是 `6c5d6d4c…`）。
