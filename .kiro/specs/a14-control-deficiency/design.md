# A14 内部控制缺陷 — 设计

> 持久化 A14-1：[persistence.md §A14-1](../completion-phase-infra/persistence.md)  
> PRE-4 阶段 3：infra [PRE-4-3](../completion-phase-infra/tasks.md)

---

## A14-3 workbook `GtA14_3Workbook.vue`

6 sheet（示例 skip 不注册）→ Tab：

| Tab id | sheet 名（以 audit 为准） | component |
|--------|---------------------------|-----------|
| defect-list | IT缺陷汇总表 | d-form-table |
| eval-step1~6 | 步骤一至六 | d-form-table |
| comm | 沟通纪要 | d-form-table |

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

seq4 → A14-1：`control_deficiency_count`（lite 可读 stub；core A14-1 落地后准确）。
