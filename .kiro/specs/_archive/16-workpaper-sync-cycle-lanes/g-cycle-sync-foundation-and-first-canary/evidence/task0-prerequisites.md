# Task 0 证据：前置依赖核查（`git show HEAD:` 判定，不读工作树）

**执行时间**：2026-09-27　**HEAD**：`07eb3fb75`（`work/2026-09-14-d4-dual-mode-p0-fixes`）

🔴 判定方式一律 `git show HEAD:<path>`，**不读工作树** —— 工作树有并发会话在改
D3/D2/E1 相关文件（`git status` 实测 70+ 改动），读工作树会把别人未提交的东西当成 HEAD 事实。

## 四条框架层前置：全部在 HEAD

| 前置 | 判定命令 | 结果 |
|---|---|---|
| `RowTableSheetSpec` | `git show HEAD:backend/app/services/workpaper_sync/phase5_row_table_sheet.py \| Select-String "^class "` | ✅ `class RowTableSheetSpec` + `AgingGroupSpec` / `AgingLayout` / `StoreKind`，配套 20+ 顶层函数（`build_store_projection` / `merge_projection_into_store_rows` / `attach_sibling_bindings` / `spec_to_contract_sheet_payload` …） |
| `phase5_transposed_sheet.TransposedSheetSpec` | 同上 | ✅ `class TransposedSheetSpec` + **全引擎**（`build_store_projection` / `merge_projection_into_store` / `resolve_managed_sheet` / `materialize_transposed_workbook` / `materialize_file` / `extract_file` / `_copy_column`）⇒ GC-4 可实施，不必留「只裁决不实施」 |
| `StoreMergePlan.oo_crash_neutralization_fn` | `git show HEAD:backend/app/services/workpaper_sync/store_item_registry.py \| Select-String "oo_crash_neutralization_fn"` | ✅ 字段声明 `oo_crash_neutralization_fn: str \| None = None`；HEAD 上已有 **1 个**消费者（`g7.soe_subsidiary_disclosure` 的 plan 传 `"neutralize_oo_crash_if_formulas"`） |
| `g7_oo_crash_if_neutralize.neutralize_oo_crash_if_formulas` | `git show HEAD:…/g7_oo_crash_if_neutralize.py \| Select-String "^def \|_BARE_IF_CALL"` | ✅ **函数体在 HEAD**（不只是 import）：`def neutralize_oo_crash_if_formulas(path) -> tuple[str, ...]` + `_strip_bare_if_cells` + `_repack_dropping` + `_BARE_IF_CALL` |

### 🔴 关于「调用点在 HEAD、函数体从未落地」的历史

tasks.md Task 0 要求专门核这一条。**该历史已被修复**：函数体现在有独立伴生模块
`g7_oo_crash_if_neutralize.py`，其模块 docstring 逐字记载了这段历史
（「那两处调用点是 commit `82f58ea44` 推上来的，而函数本体**从未随任何 commit 落地**」）
以及修复方式（唯一定义在本模块，`pilot_g7_two_level_dynamic` re-export ⇒
`adapters/excel.py` 那两处延迟 import 形态一字不改仍可解析）。

⇒ **Task 6（13 册挂中性化）无阻塞**。

## 真实正则逐字取得（GC-2 / GF-P8 的判据基础）

```python
_BARE_IF_CALL: Final[re.Pattern[str]] = re.compile(r"(?<![A-Za-z0-9_.])IF\s*\(")
```

lookbehind 挡住 `SUMIF(` / `COUNTIF(` / `AVERAGEIF(`；`IFERROR(` / `IFS(` / `IFNA(` 因 `IF` 后不是 `(`
压根不命中；**含** `IFERROR(IF(...))` 的内层 IF（它一样进 `cIF`，故意算命中）。

## 🔴 现算发现：spec RG-4 表里的数字是「正则出现次数」，不是「格数」

tasks.md Task 3 要求「用 `_BARE_IF_CALL` 真实正则现算 13 册裸 IF（G1 141 / G4 186 / G6 192 …）」。
本轮用**两种口径**各算一遍：

| 口径 | 做法 | G1 | G2 | G3 | G4 | G5 | G6 | G7 |
|---|---|---|---|---|---|---|---|---|
| A 格数（权威） | 跑生产函数 `neutralize_oo_crash_if_formulas(副本)`，数返回的 `sheet.xml!REF` 条数 | 71 | 21 | 18 | 154 | 61 | 137 | **1065** |
| A' 格数（旁证） | openpyxl 遍历，每格 `search` 命中算 1 | 71 | 21 | 18 | 154 | 61 | 137 | 1065 |
| B 出现次数 | 每格 `findall` 求和（spec 表里的数） | 141 | 40 | 36 | 186 | 122 | 192 | 2325 |

**口径 A 才是权威**，两条硬证据：

1. `g7_oo_crash_if_neutralize.py` 的 `_strip_bare_if_cells` docstring 逐字写着
   「实测 G7 权威模板 **1065** 个裸 IF 格」—— 与口径 A 一字不差；
2. 中性化是**按 `<c>` 元素摘 `<f>`**，一格里嵌两层 IF 也只摘一次 ⇒
   「需要处置的对象数」天然是格数。

spec 表里把口径 B 的数字标成「格」，是**标注口径错误**；实质结论
（13 册全 > 0 ⇒ 13 册全挂中性化）两种口径都成立，不影响任何裁决。
⇒ 本 spec 的判据（GF-P8）一律用**口径 A**，并在判据里写明两种口径的差与选择理由。

另两处 spec 声明经现算**正确**（两种口径同值，因该 sheet 每格只含一层 IF）：
`明细分析表G11-2` = **44** 格 · `明细表G4-2` = **2** 格。

### 逐册裸 IF 格数（口径 A，`neutralize_oo_crash_if_formulas` 现算）

| 册 | 格数 | 分布（sheet → 格数） |
|---|---|---|
| G1 交易性金融资产 | 71 | 审定表G1-1 63 · 合同现金流量特征分析G1-10 5 · 业务模式分析G1-8 3 |
| G2 应收利息 | 21 | 审定表G2-1 19 · 应收利息坏账准备测算G2-7 2 |
| G3 应收股利 | 18 | 审定表G3-1 18 |
| G4 债权投资 | 154 | 附注披露（上市）77 · 附注披露（国企）38 · 审定表G4-1 29 · 合同现金流量特征分析G4-6 5 · **明细表G4-2 2** · 业务模式分析G4-5 2 · 债权投资减值准备测算表G4-10 1 |
| G5 长期应收款 | 61 | **审定表G5-1 61（全部集中此张；主受管表 G5-2 零命中）** |
| G6 其他债权投资 | 137 | 附注披露（上市）80 · 审定表G6-1 48 · 合同现金流量特征分析G6-8 5 · 业务模式分析G6-7 3 · 其他债权投资减值准备测算表G6-12 1 |
| G8 | 12 | 审定表G8-1 12 |
| G9 | 42 | 审定表G9-1 42 |
| G10 | 28 | 审定表G10-1 28 |
| G11 投资收益 | 95 | **明细分析表G11-2 44** · 收益率分析表G11-4 32 · 审定表G11-1 19 |
| G12 | 7 | 审定表G12-1 7 |
| G13 | 11 | 审定表G13-1 11 |
| G14 | 11 | 审定表G14-1 11 |
| （G0 已排除） | 16 | 函证结果汇总表G0-1 16 |
| （G7 已排除） | 1065 | 12 张 sheet，最多 权益法测算表G7-14 200 |

**13/13 册命中** ⇒ GC-2「per-file 保守策略」成立。
**13 张审定表全部命中** ⇒ GF-H5「审定表统一后置」的共性证据①成立。

幂等性同轮实证：每册中性化后**复跑返回 `()`**（一个字节都不写），
这是 `verify_unmanaged_regions` 能用同一口径比 before/after 的前提。

## 零回归基线（GC-10：现算，不写死数字）

`check_sync_provider_golden_digest.PROVIDERS` HEAD 成员（**逐项**，不断言集合大小）：

```
b60(pilot_simple_checklist,PILOT_ADAPTER_ID) · d1 · d2(pilot_d2_large_json,PILOT_ADAPTER_ID)
d3 · d4 · d5 · d6 · d7 · e1 · f1
```

契约目录 `backend/data/workpaper_sync_contracts/` 当前 json（除 `_example.candidate.json`）：
`b60.hour_budget` · `d1.notes_receivable_detail` · `d2.receivable_detail` ·
`d3.prepaid_receipts_detail` · `d4.revenue_detail` · `d5.receivables_financing_detail` ·
`d6.contract_assets_detail` · `d7.contract_liabilities_detail` · `e1.monetary_fund_detail` ·
`f1.prepayment_detail` · `g7.soe_subsidiary_disclosure` · `h1.disposal_check`

🔴 **spec design §GC-10 的表述需修正**：它写「`PROVIDERS` 已含 … (+g7/h1)」，
实测 **g7 / h1 不在 `PROVIDERS` 里**（它们有契约但未纳入该 digest 门），而 **f1 在**
（并发会话本轮交付）。这正好实证 GC-10 本身的裁决：**任何写死的成员快照都会 stale**
⇒ 判据只断言「非 G 的 digest 逐项不变」，成员清单现算。

## 结论

| Task | 阻塞状态 |
|---|---|
| Task 6（13 册挂中性化） | ✅ 无阻塞（函数体 + 声明式挂点均在 HEAD） |
| GC-4 / g4-g6 Task 10、15 / g5 Task 11（转置） | ✅ 无阻塞（`TransposedSheetSpec` 全引擎在 HEAD，不止类型） |
| Task 11~12（G2 provider + 薄声明） | ✅ 无阻塞（`RowTableSheetSpec` 在 HEAD） |
| Task 14（发布链第③环） | 🔴 仍卡 BP-1~BP-3（平台级供给），按 spec 要求如实 `upstream_gap` |
| Task 16（真栈验收） | 🔴 仍卡 BP-4（真 OO 9.4 场景集） |
