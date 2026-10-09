# Task 0 前置依赖核查（F4）

**执行**：2026-09-26　**基线**：工作树（HEAD `07eb3fb75` + 并发会话 WIP）

主证据见 `.kiro/specs/f3-sync-coverage-and-first-canary/evidence/task0-prerequisites.md`
（F3/F4/F5 三 spec 共用：框架层 `RowTableSheetSpec` / 锚行 footer / 兄弟 Table ref / nested 路径 /
`merge` 保护 / 模板覆盖层 / D3 provider 范式 / 发布链五环与登记点 / FC-11 根因 / F1 并发实施）。
本文件只记 F4 特有项。

## 补-1：兄弟 Table ref 位移（F4 依赖面最大）✅ 能力就绪，🔴 但 spec 的 `uuid_col` 声明有缺陷

F4 有 **8 个同 sheet 多区**（全 F 循环最多）：F4-7 五区 + F4-8 两区 + F4-1 两区（共 9 区分布在 3 张 sheet）。
框架层能力实测就绪（主证据 §3），生产先例 D3-4 双区 / D3-7 双区。

🔴 **阻塞点**：同 sheet 多区靠 **`uuid_col` 配对** spec ↔ contract table
（`phase5_row_table_sheet.spec_to_contract_sheet_payload` L~255 注释：「同 sheet 双区配对键……用 `uuid_col`
把 spec 与 table 一一配对。缺它 → 匹配 0 张 → ProviderCapabilityError」）。

而 F4 design 的受管区清单把同 sheet 各区的 UUID 列写成**同一列**：

| sheet | design 声明 | 区数 | 判定 |
|---|---|---|---|
| F4-7 未入账检查表 | 五区全写 **L** | 5 | 🔴 配对失败 |
| F4-8 应付账款检查表 | 两区全写 **S** | 2 | 🔴 配对失败 |
| F4-1 审定表 | 两区全写 **M** | 2 | 🔴 配对失败 |

生产先例对照：D3-4 两区用 **J / K**，D3-7 两区用 **R / S** —— 逐区独立空列。

⇒ **Task 2 SHALL 为 F4-7 五区 / F4-8 两区 / F4-1 两区逐区实测独立空列**（共需 9 个互不相同的 uuid_col），
不得沿用 design 的同列声明。若某 sheet 的空列不足（如 F4-7 max_col=N，A-K 业务列 ⇒ 仅 L/M/N 三列可用而需五个）
则须裁决：①按区分段复用行区间外的列 ②扩 max_col（instrumentation 扩列，同 F5 的 UUID ≥ max_col 情形）
③该 sheet 拆多次受管。此裁决在 Task 13/14 前必须落地。

## 补-2：F3 spec 的 FC-11 工具链修复状态

F4 Task 18 的 blocking 原文：「依赖 F3 spec 已修工具链（`_ensure_cells` 只写 `cells`），否则再次运行脚本
会把 `items` 造回来」。

实测（2026-09-26 本批实施起点）：
- `fix_f_cycle_prefill_presets.py` 的根因**两处**未修（主证据 §9：`_ensure_cells` L417-432 + `new_block` L406-414）
- F4 三块 `[224]` / `[225]`(全角) / `[307]`(半角) 现状：`cells: []` + `items` 各 2 条 ⇒ 运行时死配置属实
- `convert_prefill_presets()` 现算 `workpaper:F4 = 18`（F4 另有非 items 型块贡献这 18 条）

⇒ 本批实施把 F3 的工具链根因修复排在 F4 数据迁移**之前**（统一 todo #2 → #3），依赖关系满足。

## 补-3：`F4A` 幻影码撞真码（三条隔离判据的前提逐条实测）

| 判据 | 实测 |
|---|---|
| ① `backend/wp_templates/_index.json` 无 `F4A` 条目 | 待 Task 2/3 现算取证（spec 记「只有 `F4`」） |
| ② `assert_no_implicit_template_fallback('F4A')` 通过 | 能力就绪（D3:296 范式；F1 provider 已有同款实现 L130） |
| ③ provisioner 用裁决真码 `["F4"]` | 裁决文件 `workpaper_sync_entry_wp_code_adjudication.json` 现 F 循环 0 条，Task 1 新增 |

撞码事实源：`backend/app/data/wp_code_overrides.json:549` `"F4A": "f4-accounts-payable"`（待 Task 3 逐字复核）。

## 补-4：F4 slice 逐元素实测（Task 1 前半）

`backend/data/workpaper_sync_f_cycle_manifest_slice.json` → `xlsx/gt-f4-accounts-payable`：

```
wp_code_pattern             "F4A"
capability                  null
capability_verdict_stage    "pipeline_entry_pending_definition_delivery"
capability_target           "bidirectional"
capability_target_blocked_by ["BP-1","BP-2","BP-3","BP-4"]      ← 🔴 不含 BP-5/BP-7/BP-9
migration_state             "legacy_fake_bidirectional"
adapter_id / authority_model / definition_bundle
  / instrumentation_candidate / published_representation   全 null（五个 null 供给位）
template_ref                "F/F4 应付账款.xlsx"
mount_count                 2
scenario_profile_id         "xlsx.editable.shared.single.room_service_wired.v1"
html_counterpart_verdict    "exists"
manifest_mirror.capability  "single_onlyoffice"   + divergence_from_slice 已登记（FC-12 属实）
ui_toolbar_gate             "v-if=\"showHtmlToolbar\""
```

⇒ 与 requirements「F4 当前状态实测」表逐项一致，slice **未过期**。

## 补-5：F4 特有结论

| 项 | 判定 |
|---|---|
| FC-10 前置 | ✅ **不需要**（红基线 B6）；但结论须 Task 2 逐列取证（F4-1 K / F4-4 E / F4-8 G 均为公式列） |
| 模板缺陷 | ✅ 无（F 循环两处模板真实缺陷在 F2-26!J9 与 F5-7!G31，F4 零命中） |
| BP-7 | ⚠️ 仅 F4-1 一处 `custom-${index}`，且有 `defaults[index]?.rowKey` 兜底 ⇒ 风险低于 F2/F5，但受管前仍须修（需求 6.2） |
| 同 sheet 多区 | 🔴 见补-1，`uuid_col` 须逐区独立 |
| 三家审定表统一口径 | 🔴 依赖 F1 spec 需求 7.3；F1 spec 现 0/22 未实施 ⇒ F4-1 取数不得改、不得受管（Task 19 保持 `[ ]*`） |
