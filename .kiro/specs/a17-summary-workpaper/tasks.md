# Implementation Plan

> **分期**：audit → lite → core → plus  
> **计数**：audit 6 + lite 4 + core 6 + plus 7 + E2E 2 = **25 任务**（实现型 PRE 仅在 infra 勾选）  
> **进度（2026-06-18）**：**25/25 ✅** — chip 灰显、issue_hints UI、A17-5 选版 UI 已落地

---

## audit-xlsx：A17 xlsx 深读（6 任务，与 lite 并行）

> 产出 `backend/data/a17_xlsx_audit.json`；与 infra **PRE-4-0** 同一 DoD。

- [x] **X-A17** A17 重大事项概要程序表.xlsx
- [x] **X-A17-5-1** A17-5-1 审计工作完成核对表（财报审计）.xlsx
- [x] **X-A17-5-2** A17-5-2（内控审计）.xlsx
- [x] **X-A17-5-3** A17-5-3（IPO 特别程序）.xlsx
- [x] **X-A17-5-4** A17-5-4（新三板特别程序）.xlsx
- [x] **X-A17-5-5** A17-5-5（函证程序）.xlsx

**DoD**：audit JSON 写入 ✅；procedure_table A17 7 步已同步 JSON。

---

## 前置

> PRE / PRE-4 实现：[completion-phase-infra/tasks.md](../completion-phase-infra/tasks.md)（PRE-4-0~1 ✅、PRE-2 ✅、PRE-3 ✅）。

---

## A17-lite：弹窗 + A17-5 核对表（4 任务）

- [x] 1. A17 程序表扩充步骤 + `applicable_categories: ["A"]`（procedure_table JSON 7 步）
- [x] 2. 程序表 chip 适用性联动（`GtIndexChip :disabled` ← `row.status === 'not_applicable'` ✅）
- [x] 3. A17-3/3-1/4/6 弹窗 E2E（**E10** — `e2e/a17-lite.spec.ts`；需 `RUN_FULL_E2E=1`）
- [x] 4. A17-5-1 路由验收：PRE-4-1 + override + parser 单测 ✅（**E11** — `e2e/a17-lite.spec.ts`）

**lite DoD**：E10 + E11 spec 已写 ✅；chip 灰显待 task 2。

---

## A17-core：A17-1 章节 + 导出（6 任务）

- [x] 5. `a17_chapter_definitions.json`（16 章）
- [x] 6. `GtA17Summary.vue`（目录+提示栏+textarea；AI 弹窗 plus 已挂）
- [x] 7. 章节 debounce 保存（item_id `A17-1-ch01`~`ch16`）
- [x] 8. htmlRendererRegistry + `_WP_CODE_OVERRIDE` A17-1
- [x] 9. `a17_summary_service.py` + 「从关联模块拉取」按钮（ch01~ch02/ch05/ch08~ch15 ✅；ch03/ch04/ch06/ch07/ch16 手工或未就绪）
- [x] 10. `a17_word_exporter.py` + `/api/a17/export-word`（`test_a17_word_exporter.py` ✅）

**core DoD**：**E12** — `e2e/a17-core.spec.ts` 已写 ✅。

---

## A17-plus：KAM + LLM + 报告（7 任务）

- [x] 11. `GtKamWorkpaper.vue` + KAM JSON schema（`types/kam.ts`）
- [x] 12. A17-2-1 Word 导出（`A17WordExporter.export_kam`）
- [x] 13. KAM → 报告单向 push（`a17_kam_push_service.py` + `test_a17_kam_push_service.py`）
- [x] 14. `a17_llm_service.py` + prompts（`backend/data/wp_llm_prompts/a17/`）
- [x] 15. AI 预览弹窗（`GtA17Summary` + `/api/a17/chapters/{id}/ai-generate`；RAG 可选增强）
- [x] 16. issue_hints 消费（`GtA17Summary` 提示栏 + `/api/projects/{id}/issue-hints`）
- [x] 17. A17-5 business_category 自动选版（`GtAProgramConsole` + `/api/a17/applicable-versions` + 必做/推荐 badge）

---

## 集成验证

- [x] 18. Playwright **E10 + E11**（`e2e/a17-lite.spec.ts`）
- [x] 19. Playwright **E12**（`e2e/a17-core.spec.ts`）

> 全量矩阵：[e2e-matrix.md](../completion-phase-infra/e2e-matrix.md)  
> E2E 运行：`RUN_FULL_E2E=1` + `TEST_PROJECT_ID=<A类项目>`

---

## 移出本 spec

| 项 | 处置 |
|----|------|
| checklist_xlsx_parser 实现 | infra PRE-4-x ✅ |
| docx_template_filler | infra PRE-2 ✅ |
| A17-7 增强 | 独立 spec（可选） |
