# A14 内部控制缺陷底稿族（子 spec）

> **父 spec**：[a7-a15-completion-workpapers](../a7-a15-completion-workpapers/requirements.md)  
> **公共依赖**：[completion-phase-infra](../completion-phase-infra/requirements.md)（PRE-4 阶段 3）  
> **联动**：[linkage.md](../completion-phase-infra/linkage.md)  
> **audit 权威**：`backend/data/a7_a15_xlsx_audit.json`（X-A14~6 ✅）

## 范围（7 物理文件）

| wp_code | runtime | 分期 |
|---------|---------|------|
| A14 程序表 | a-program-console | lite |
| A14-1 | checklist-table | core |
| A14-2 | d-form-table | core |
| A14-3 | **a14-3-workbook**（多 sheet Tab） | core |
| A14-4 | d-form-table | core |
| A14-5 | d-form-table | plus |
| A14-6 | e-control-test | plus |

程序表 **6 步**：seq2→A14-2,3,4；seq3→A14-5；seq4→A14-1；seq6→A14-6。

**禁止** A14-2~6 一律标 univer。

## A14-3 定案

6 sheet 物理文件 → **`a14-3-workbook`** Tab 容器（非单一 d-form-table）。详见父 spec design §A14-3 workbook。

## 下游消费

| 消费方 | 内容 |
|--------|------|
| A9 弹窗 | 缺陷计数/等级 guidance（plus） |
| A17 ch07 舞弊 | A14-1 + 摘要 API `control_deficiency` |
| A18 议题 2 | 手动 chip + issue_hints |

## 任务

详单：[tasks.md](./tasks.md)

## 设计

[design.md](./design.md)

## 已知陷阱

- A14-2 文件内首 sheet 误标 A14-4 → 以 audit sheet 顺序为准
- A14 seq2 xlsx H 列乱码 → ref 以 JSON 为准
- 示例 sheet → `example-skip`，不注册 runtime

## 现状

| 项 | 状态 |
|----|------|
| audit X-A14~6 | ✅ |
| A14-1 checklist | ❌ PRE-4-3 |
| A14-3 workbook | ❌ |
| A14-6 e-control | ❌ plus |
