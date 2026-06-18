# 完成阶段公共基础设施 — 任务

> 各消费 spec **引用**本任务标绿状态，不在本地重复 PRE 勾选。  
> E2E 用例 ID 见 [e2e-matrix.md](./e2e-matrix.md)。

---

## PRE 与 audit

- [x] **PRE-1（代码部分）** docx prefilled-download 子码 + 文件名前缀 fallback（`_match_filename_prefix`/`_find_docx_by_index_or_disk` 已落地）
- [ ]* **PRE-1-合伙人预填**（增量，可选）签字会计师/合伙人占位符预填（`staff_members` JOIN；现状代码保留不替换）
- [ ] **E-FIX** 确认/构造 E2E 种子项目 FIX-A（A类）+ FIX-B + FIX-INT + FIX-RP（A17/A18 E2E 前置）`[blocked:data]` — 需人工确认 PG 中 A 类项目可用性或编写 seed 脚本
- [ ] **PRE-1-E2E**（**E-PRE-1**）smoke 五件套：A8-1、A9-1、A16-1、A17-3、A18-1 `[depends:E-FIX]`
- [x] **PRE-2** `docx_template_filler.py`（颜色语义 + 占位符 + 注释表删除）
- [x] **PRE-2-E2E** export-word + check-incomplete 端点骨架
- [x] **PRE-3** 审计 [design §PRE-3 ref_index 清单](./design.md#pre-3-ref_index-审计清单) 三处同步
- [x] **PRE-4-0 / X-A17** A17 程序表 + A17-5-1~5 xlsx 深读 → `a17_xlsx_audit.json`
- [x] **PRE-4-1** `checklist_xlsx_parser.py` + A17-5-1 集成（**E11**）
- [x] **PRE-4-2** A17-5-2~5-5 扩展
- [x] **PRE-4-3** A15-1、A14-1 列映射（`a7_a15_xlsx_audit.json`）
- [x] **PRE-4-4** A11-2、A11-3

## Infra 增强

- [x] **INFRA-1** `get_issue_hints()` 舞弊/违规计数 API
- [x] **INFRA-2** `workpaper-summaries/{key}` 摘要 API 骨架（schema 见 design.md）
- [x] **INFRA-3** CI：`audit_a7_a15_xlsx.py --diff-only`；A17 audit 就绪后纳入

---

**PRE-1 DoD**：E-PRE-1 五件套 prefilled-download 200 + docx 可开。

**PRE-4-0 DoD**：`a17_xlsx_audit.json` 含 A17 程序表 + 5× A17-5-x 列映射。

**PRE-4-1 DoD**：E11 — A17-5-1 checklist 填 1 条刷新不丢。
