# A14 内部控制缺陷 — 设计

> 持久化 A14-1：[persistence.md §A14-1](../completion-phase-infra/persistence.md)  
> PRE-4 阶段 3：infra [PRE-4-3](../completion-phase-infra/tasks.md)

---

## A14-3 workbook `GtA14_3Workbook.vue`

6 sheet（示例/参考 skip 不注册）→ Tab。**以 audit JSON 实物为准**（`a7_a15_xlsx_audit.json` A14-3）实际仅 **3 个有效 sheet**，其余 3 个是 `【示例1】`/`【示例2】`/`【参考】` → `example-skip`：

| Tab id | sheet 名（实物，以 audit 为准） | component |
|--------|------------------------------|-----------|
| defect-summary | A14-3 缺陷汇总 | d-form-table |
| it-eval | A14-3-1 IT控制缺陷评价 | d-form-table |
| comm | IT控制缺陷沟通会议纪要 | d-form-table |

> ⚠️ 旧 design 写的 `eval-step1~6 步骤一至六` **与实物不符**（A14-3 无六步骤评价 sheet，那是 A14-2/A14-4 的内容混淆）。实施按上表 3 Tab。
> 示例/参考 sheet 命中 `_should_skip_historical_sheet` 同类规则（`【示例】`/`【参考】`）不注册 runtime。

`_WP_CODE_OVERRIDE["A14-3"] = "a14-3-workbook"`

---

## A14-1 checklist

- R5+R6 双行表头；认定 6 列矩阵
- 动态行：`A14-1-row-{NNN}` + remark JSON（见 persistence.md）
- **禁止**与 A15-1 固定问卷共用同一 parser 分支

---

## A14-6 e-control-test（plus）

T4 非财务报告 Step1–7 + 结论；复用 `GtEControlTest` 模式（与循环底稿 e-control 对齐）。

---

## 程序表 auto_data

seq4 → A14-1：`control_deficiency_count`（A14-1 checklist 落地后准确 ✅）。

---

## 实施状态（2026-06-18）

| 组件 | 文件 | 状态 |
|------|------|------|
| A14-3 workbook | `GtA14_3Workbook.vue` | ✅ 3 Tab |
| A14-1 parser | `checklist_xlsx_parser.py` | ✅ |
| A14-5/6 | render schema + `GtEControlTest` | ✅ |
| E2E | `e2e/a14-1-checklist-table.spec.ts` | ✅ API 级 |
