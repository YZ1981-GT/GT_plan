# Implementation Plan

> **分期**：audit → lite → core → plus  
> **计数**：audit 6 + lite 4 + core 6 + plus 7 + E2E 2 = **25 任务**（实现型 PRE 仅在 infra 勾选）

---

## audit-xlsx：A17 xlsx 深读（6 任务，与 lite 并行）

> 产出 `backend/data/a17_xlsx_audit.json`；与 infra **PRE-4-0** 同一 DoD。

- [ ] **X-A17** A17 重大事项概要程序表.xlsx
- [ ] **X-A17-5-1** A17-5-1 审计工作完成核对表（财报审计）.xlsx
- [ ] **X-A17-5-2** A17-5-2（内控审计）.xlsx
- [ ] **X-A17-5-3** A17-5-3（IPO 特别程序）.xlsx
- [ ] **X-A17-5-4** A17-5-4（新三板特别程序）.xlsx
- [ ] **X-A17-5-5** A17-5-5（函证程序）.xlsx

**DoD**：audit JSON 写入；procedure_table A17 步数可与 xlsx diff。

---

## 前置

> PRE / PRE-4 实现：[completion-phase-infra/tasks.md](../completion-phase-infra/tasks.md)（PRE-4-0~2、PRE-2、PRE-3）。

---

## A17-lite：弹窗 + A17-5 核对表（4 任务）

- [ ] 1. A17 程序表扩充为 **5 步**（实物：seq1→A17-1 / seq2→A17-3 / seq3→A17-4 / seq4→A17-2 / seq5→A17-6，见 requirements §1）+ `applicable_categories: ["A"]`
- [ ] 2. 程序表 chip 适用性联动（灰显 + preventNavigate）
- [ ] 3. A17-3/3-1/4/6 弹窗 E2E（**E10**；依赖 PRE-1/3）
- [ ] 4. A17-5-1 路由验收：PRE-4-1 完成后 `_WP_CODE_OVERRIDE` + 填 1 条（**E11**）；PRE-4-2 完成后 5-2~5-5 版本选择

**lite DoD**：E10 + E11 通过。

---

## A17-core：A17-1 章节 + 导出（6 任务）

- [ ] 5. `a17_chapter_definitions.json`（**16 章**实物目录，见 requirements §4）
- [ ] 6. `GtA17Summary.vue`（目录+提示栏+textarea；无 AI）
- [ ] 7. 章节 debounce 保存（item_id 见 [persistence.md](../completion-phase-infra/persistence.md)）
- [ ] 8. htmlRendererRegistry + `_WP_CODE_OVERRIDE` A17-1
- [ ] 9. `a17_summary_service.py` + 「拉取」按钮（就绪表 requirements §4）
- [ ] 10. `a17_word_exporter.py` 编排（依赖 infra **PRE-2**）+ 完整性检查

**core DoD**：**E12** — 写 ch01 → export → 无蓝【】/XX。

---

## A17-plus：KAM + LLM + 报告（7 任务）

- [ ] 11. `GtKamWorkpaper.vue` + KAM JSON schema
- [ ] 12. A17-2-1 Word 导出（PRE-2）
- [ ] 13. KAM → 报告单向 push（**E17**）
- [ ] 14. `a17_llm_service.py` + prompts
- [ ] 15. RAG + AI 预览弹窗
- [ ] 16. issue_hints 消费（infra **INFRA-1**）
- [ ] 17. A17-5 business_category 自动选版（PRE-4-2 后）

---

## 集成验证

- [ ] 18. Playwright **E10 + E11**（lite）
- [ ] 19. Playwright **E12**（core）

> 全量矩阵：[e2e-matrix.md](../completion-phase-infra/e2e-matrix.md)

---

## 移出本 spec

| 项 | 处置 |
|----|------|
| checklist_xlsx_parser 实现 | infra PRE-4-x |
| docx_template_filler | infra PRE-2 |
| A17-7 增强 | 独立 spec（可选） |
