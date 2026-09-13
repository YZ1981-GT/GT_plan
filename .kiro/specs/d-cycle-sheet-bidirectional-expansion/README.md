# D 循环 sheet 级双向回写扩容

## 状态

- **父 entry 级**：D1–D7 均已 `capability=bidirectional`，各 **1** 张受管明细 §9.6 绿（D1-3 / D2-2 / D3-2 / D4-2 / D5-2 / D6-2 / D7-2）。
- **sheet 级**：大量 sibling 仍 dualMode / `GtOnlyOfficeSheet`；程序表/附注类应诚实判 `single_html`，不得强行单元格双向。
- **本轮首个 canary**：**D4-3 其他业务收入明细**（扩进既有 adapter `d4.revenue_detail`，不新开第二 adapter_id——registry「一 entry 一 adapter」）。

## 诚实边界

1. 「每个具体底稿」≠ 每张 xlsx sheet 都双向。checklist/程序/附注与网格不对齐的 → `single_html`。**调整分录汇总（D4-4）虽是扁平字段键表，但已由 `AdjustmentSyncService` 专用链 + 借贷平衡 + A13 联动驱动、且模板无行身份列 → 同归 `single_html`**。
2. 同一 workbook 多受管表：扩 `sheets[]` + 宿主按 sheet 切 `sheetKey`，**禁止**同 entry 注册第二个 `adapter_id`（除非先改 registry）。
3. D4 Excel 重分类列（D/I）HTML store 无字段 → mask/写 0，不进契约。

## 分波顺序（执行中）

| Wave | 目标 | 形态 | 状态 |
|---|---|---|---|
| 0 | D*-detail 七张已 verified | 各异 | ✅ |
| 1 | **D4-3** `D4-3-rows` | 字段键扁平行 | ✅ §9.6 绿（evidence `g5-1-d43-unified-path/`） |
| — | ~~D4-4 `D4-4-rows` 调整分录~~ | 字段键 | 🚫 **`single_html`**（无 UUID 行身份列 + `AdjustmentSyncService`/A13 hub 冲突；`T08-d44-single-html-adjudication.json`）— 不做单元格双向 |
| — | **D4-5** 会计政策检查 | 段落式多 item | ❌ **`single_html`**（`T08-d45-single-html-triage.json`）— 不得扩 sheets[] |
| 2 | **D1-2 按类别明细**（下一双向 canary，D4-4/D4-5 改判 single_html 后提前） | 字段键 | 待 |
| 4 | D2-3 坏账准备 | nested/多 item | 待 |
| 5 | D5-3 / D6-3 / D7-3… | 同族明细 | 待 |
| 6 | 分析类候选（D4-7…）逐表核映射 | 不定 | 待裁决 |
| 终 | 程序/附注/目录/政策检查 | — | → single_html 收口 |

配套盘点：[explore inventory](d3bae344-9fd0-4d13-9784-b6c248425e94)（D 循环 gap）。
