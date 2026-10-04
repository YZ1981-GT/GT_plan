# Task 0 证据：前置依赖核查（`git show HEAD:` 判定，不读工作树）

**执行日期**：2026-09-27　**HEAD**：`b69481836`（`work/2026-09-14-d4-dual-mode-p0-fixes`）

## 一、四项前置全部在 HEAD 确认存在

| 前置 | 判定命令 | 结果 |
|---|---|---|
| `RowTableSheetSpec` | `git show HEAD:backend/app/services/workpaper_sync/phase5_row_table_sheet.py \| Select-String "^class RowTableSheetSpec"` | ✅ 命中 |
| `spec_to_contract_sheet_payload` / `build_store_projection` / `merge_projection_into_store_rows` / `iter_store_rows` | 同上文件 | ✅ 四个函数全在 |
| `merge._protection` 格级判定 | `git show HEAD:…/merge.py \| Select-String "_protection"` | ✅ `def _protection(template: _FieldTemplate) -> ProtectionPolicy` + 调用点 |
| `StoreMergePlan.oo_crash_neutralization_fn` | `git show HEAD:…/store_item_registry.py` | ✅ 字段声明 + g7/h1/g2 三处赋值 |
| 🔴 `g7_oo_crash_if_neutralize.neutralize_oo_crash_if_formulas` **函数体** | `git show HEAD:…/g7_oo_crash_if_neutralize.py \| Select-String "^def "` | ✅ **函数体在 HEAD**（`def neutralize_oo_crash_if_formulas(path: Path) -> tuple[str, ...]`），另有 `_strip_bare_if_cells` / `_repack_dropping` 与 `_BARE_IF_CALL` 正则 `(?<![A-Za-z0-9_.])IF\s*\(` |

🔴 HC-12 第 3 条要求的「不能只看 import」已满足：本次按 `^def ` 取的是**定义行**，不是调用点。

## 二、契约 schema 四级表头扩容（本 spec 交付的平台级前置）

`contracts._parse_table` 的 `header_rows` 值域原为 **1..3**（Task 13），而 H 循环
**五条 entry 的主受管表是四级表头**：

| entry | 主受管 sheet | 表头行 |
|---|---|---|
| H2 | `明细表H2-2` | R9/R10/R11/R12 |
| H4 | `明细表H4-2` | R8/R9/R10/R11 |
| H5 | `明细表H5-2` | R9/R10/R11/R12 |
| H7 | `明细表（成本模式）H7-2` | R9/R10/R11/R12 |
| H8 | `明细表H8-2` | R8/R9/R10/R11 |

上界停在 3 时这五条只能二选一：下移 anchor 丢最外层分组（压扁列结构），或整条不接双向。
Task 42 的 H1 pilot 正撞在这里并登记欠账 `UPSTREAM_DEBT_FOUR_LEVEL_HEADER_NOT_EXPRESSIBLE`。

**处置**：新增 `contracts.MIN_HEADER_ROWS = 1` / `contracts.MAX_HEADER_ROWS = 4`，
校验改用常量。下游只有两个消费者且与上界无关：
`TableSpec.two_level_header`（`>= 2`）与 `merge._first_data_row_of()`（`anchor 行 + header_rows` 纯算术）。

同步改动的两处既有判据（**只改判据方向，不改 H1 契约字节**）：

1. `test_task13_contract_registry.py::test_header_rows_domain` 参数 `[0, 4, "2", True]` → `[0, 5, "2", True]`，
   并新增 `test_four_level_header_is_expressible` 断言 `header_rows == 4` 必须通过；
2. `test_task42_h1_grouped_dynamic_pilot.py` 两处：
   `test_header_rows_is_three_and_is_the_schema_upper_bound` 的域外值 4→5；
   `test_four_level_header_debt_is_a_measured_schema_limit` 改向为「源侧四级仍是事实 + 上界已扩到 4 + 欠账文案保持冻结」。

🔴 **H1 的契约 / adapter / golden digest 一字未改**（HC-8）：
`h1.disposal_check.json` 与 `definition_store/contracts/*` 里那段欠账叙述是冻结的历史记录，
改它会动 golden digest。欠账已结清这一事实记在 `contracts.MAX_HEADER_ROWS` 的注释与本文件。

## 三、改动前的既有红基线（**不是**本 spec 引入）

`tests/workpaper_sync/test_task13_contract_registry.py` + `test_task42_h1_grouped_dynamic_pilot.py`
在**未打本 spec 任何补丁**时（`git stash` 三文件后实测）：

```
6 failed, 375 passed
FAILED test_task13…::TestRegistryReportHasAProductionConsumer::test_registry_facts_participate_in_the_blocking_total
FAILED test_task13…::TestRegistryReportHasAProductionConsumer::test_unregistered_registry_fact_is_rejected
FAILED test_task13…::TestTask13ScopeBoundary::test_contract_directory_matches_the_delivery_ledger
FAILED test_task42…::TestProductionWiring::test_router_calls_the_h1_attach_on_both_paths
FAILED test_task42…::TestProductionWiring::test_router_still_calls_the_other_two_pilot_attaches
FAILED test_task42…::TestPilotIntroducesNoResolverDebt::test_no_function_in_this_module_is_classified_as_writer_or_resolver
```

根因均在**并发会话的 F2 在飞作业面**，与 H 循环无关：

* `DELIVERED_PER_ENTRY_CONTRACTS` 已登记 `f2.inventory_main` / `f2.stocktake_bundle` /
  `f2.inventory_valuation` / `f2.inventory_special` 四条，但
  `backend/data/workpaper_sync_contracts/` 里**没有**这四个 json（`git ls-tree HEAD` 亦无）
  ⇒ 登记表与文件双向等值判据打红；
* provider 模块数 327 → 372（并发会话新增 D3/D5/D6/D7/E1/F3/F4/F5/G2 各 per-sheet 模块）。

打完本 spec 补丁后同两文件实测 **4 failed, 378 passed** —— 少的两条是 flaky 的 router 文本判据，
其余 4 条与上表同源。🔴 本 spec **不修**这些红（属并发会话作业面，协作铁律：不碰）。

### 完整既有红清册（H 相关面，逐条经 `git stash` 双跑确认）

| # | 测试 | 根因（全在并发会话作业面） |
|---|---|---|
| 1 | `test_task13…::test_registry_facts_participate_in_the_blocking_total` | 同 3 |
| 2 | `test_task13…::test_unregistered_registry_fact_is_rejected` | 同 3 |
| 3 | `test_task13…::test_contract_directory_matches_the_delivery_ledger` | `DELIVERED_PER_ENTRY_CONTRACTS` 登记了 `f2.inventory_main` / `f2.stocktake_bundle` / `f2.inventory_valuation` / `f2.inventory_special` 四条，但 `backend/data/workpaper_sync_contracts/` **没有**这四个 json（`git ls-tree HEAD` 亦无）⇒ 登记表↔文件双向等值判据打红 |
| 4 | `test_task43…::test_contract_is_registered_in_the_delivery_ledger` | 同 3（断言 `set(available_contract_ids()) == 登记集`，差集正是那 4 条 f2） |
| 5 | `test_registration_isolation_and_alignment…[f1]` | 🔴 `phase5_f1_prepayment.build_contract_payload()` **产出的 payload 本身**过不了 `parse_contract`（`sheets[f16-managed].tables[related_party_rows]: table anchor 必须是 A1 单元格，实得 None`）—— 不是磁盘文件的问题 |
| 6 | `test_task42…::test_no_function_in_this_module_is_classified_as_writer_or_resolver` | provider 模块数 327 → **372**（并发会话新增 D3/D5/D6/D7/E1/F3/F4/F5/G2 各 per-sheet 模块） |
| 7 | `test_bp61_row_uuid_instantiation_gate…::test_contract_has_only_row_scoped_fields` | `d2.receivable_detail` 出现非行域字段（与 H 无关；`git stash` 双跑均红） |

🔴 **第 5 条同时卡死平台级零回归门** `backend/scripts/check/check_sync_provider_golden_digest.py`：
f1 在 `PROVIDERS` 里排在 h9 之前，`run()` 在 f1 上就抛 ⇒ 整个门跑不起来。
本 spec 的处置是**不修 f1**（属它自己的作业面、且其文件不在本轮改动面），
改为在 `tests/workpaper_sync/test_h9_canary_and_contract.py::TestH9GoldenDigest`
自带 h9 的三层 digest 判据（contract / instrumentation / projection），
并用 `test_the_platform_gate_is_blocked_by_a_pre_existing_f1_defect` 把阻塞源钉住。
f1 修好后那条判据会打红 ⇒ 提示删掉它、直接依赖平台门。

🔴 本 spec **不修**上述任何一条（并发会话在飞，协作铁律：不碰）。
