# Task 1 证据：slice 复核 + 六条 wp_code 裁决条目 + BP-8 证据

spec: `g4-g6-shared-workbook-three-entry-lanes`
日期：2026-10-07

## 复核结论

### 1. adjudication JSON 六条 G4/G6 裁决已完备

`workpaper_sync_entry_wp_code_adjudication.json`（74 条裁决，digest `791b10a6e7b49d68ab2e…`）
中六条 G4/G6 entry 全部包含：

| entry_id | contract_id | `bp8_verbatim` | `belongs_to_entries` | `resolution` |
|---|---|---|---|---|
| `xlsx/gt-g4-bond-investment-ecl` | `g4.ecl_stage` | ✅ | ✅ G4 三条 | ✅ GC-1 |
| `xlsx/gt-g4-bond-investment-main` | `g4.bond_main` | ✅ | ✅ G4 三条 | ✅ GC-1 |
| `xlsx/gt-g4-bond-investment-sppi` | `g4.sppi_inventory` | ✅ | ✅ G4 三条 | ✅ GC-1 |
| `xlsx/gt-g6-other-bond-investment-ecl` | `g6.ecl_stage` | ✅ | ✅ G6 三条 | ✅ GC-1 |
| `xlsx/gt-g6-other-bond-main` | `g6.other_bond_main` | ✅ | ✅ G6 三条 | ✅ GC-1 |
| `xlsx/gt-g6-other-bond-sppi` | `g6.sppi_fair_value` | ✅ | ✅ G6 三条 | ✅ GC-1 |

BP-8 原文（`bp8_verbatim`）逐条一致：
> `G4 债权投资.xlsx` 与 `G6 其他债权投资.xlsx` 各服务 3 条 entry，而它们的 wp_code_patterns
> 分别同为 `G4B` / `G6O`。若 representation entry_id 只用 wp_code（或 wp_code_pattern），
> G4 的三条与 G6 的三条会各自互相顶掉对方的 entry pointer / representation generation。

GC-1 解法（`resolution`）逐条一致：
> entry pointer / working_paper_sync_entry_state 主键 / representation generation 一律用 entry_id；
> matcher 域用互斥 sheet_keys（沿用 F2-H1 解法，运行时走 resolve_for_entry(entry_id)）；
> 模板归属用 belongs_to_entries（复数），守卫断言 owner 模板并集 == entry 全集且每条 entry 恰被一张模板认领。

`belongs_to_entries` 三元组：
- G4 册：`["xlsx/gt-g4-bond-investment-main", "xlsx/gt-g4-bond-investment-sppi", "xlsx/gt-g4-bond-investment-ecl"]`
- G6 册：`["xlsx/gt-g6-other-bond-main", "xlsx/gt-g6-other-bond-sppi", "xlsx/gt-g6-other-bond-investment-ecl"]`

### 2. manifest 六条现状

六条全为 `capability=single_onlyoffice`、`migration_state=legacy_fake_bidirectional`、
`canonical_resolver=legacy_sheet_onlyoffice_router`。
- `wp_code_patterns`：G4 三条 `["G4B"]`、G6 三条 `["G6O"]`（幻影码）
- 真码：G4→`G4`、G6→`G6`（adjudication 的 `wp_codes` 字段）
- `sync_editor_host_mounted`：五条 `true`、G6-investment-ecl 为 `false`
  （mount_components 只有 `["GtOnlyOfficeSheet"]`，无 `WorkpaperSyncEditorHost`——Task 15/16 的接桥在途）

### 3. overlay 现状

- **无 G4/G6 bidirectional override**（overlay 的 `overrides` 数组无 G4/G6 条目）
- 唯一相关条目：`unreachable_rules` 里 `GtG6OtherBondEcl.vue` 历史 stub（已裁决不可达）
- tasks.md 勘误节记载的「G4-main/G6-main 随 13 条 G 翻 bidirectional」—— 指的是 overlay 中
  曾加过 override 但当前 HEAD 已无（可能在另一工作分支或已回退）

### 4. 已发布契约

| 契约文件 | 状态 |
|---|---|
| `g4.bond_main.json` | ✅ 已发布（无 adapter_id / entry_id 字段） |
| `g6.other_bond_main.json` | ✅ 已发布 |
| `g4.sppi_inventory.json` | ❌ 不存在 |
| `g4.ecl_stage.json` | ❌ 不存在 |
| `g6.sppi_fair_value.json` | ❌ 不存在 |
| `g6.ecl_stage.json` | ❌ 不存在 |

### 5. capability_target_blocked_by 复核

该字段只存在于 slice JSON（`workpaper_sync_g_cycle_manifest_slice.json`），不在 manifest/adjudication/overlay。
spec requirements 表中的 `blocked_by` 值已在 foundation Task 1 创建裁决时逐条核实，此处不重复。

### 6. digest 未变动

adjudication digest `791b10a6…` 是当前值，本 Task 无修改 ⇒ 不需要重算。

## 结论

Task 1 要求的三件事（`bp8_verbatim` + GC-1 解法 + `belongs_to_entries` 三元组）在 adjudication JSON
中**全部已完备**（foundation spec Task 1 交付物），digest 已是最新值。本 Task 标完成。
