# Implementation Plan

> **分期**：P0(lite) → P1(core) → P2(plus)  
> **计数**：P0 8 + P1 4 + P2 2 = **14 任务**（PRE/PRE-2 仅在 infra 勾选）

---

## 前置

> [completion-phase-infra/tasks.md](../completion-phase-infra/tasks.md)

---

## A18-P0 / lite（8 任务）

- [x] 1. 新建 A18 程序表 JSON（2+ 步 + ref_index A18-1/2）
- [x] 2. A18-1 弹窗 E2E（**E13**；PRE-1/3）
- [x] 3. `GtRegulatoryLetter.vue` 骨架
- [x] 4. 4 议题 + 提示栏（`a18_topic_definitions.json`）
- [x] 5. Y/N + textarea + 议题3 radio + GtIndexChip
- [x] 6. debounce 保存（item_id 见 [persistence.md](../completion-phase-infra/persistence.md)）
- [x] 7. htmlRendererRegistry + `_WP_CODE_OVERRIDE` A18-2
- [x] 8. 表头自动填充

**DoD**：E13 + A18-2 填议题1刷新不丢。

---

## A18-P1 / core（4 任务）

- [x] 9. `regulatory_letter_service.py` 编排（依赖 infra **PRE-2**）
- [x] 10. export-word + check-incomplete 端点（infra PRE-2-E2E）
- [x] 11. 前端导出 + 未完成警告（**E14**）
- [x] 12. issue_hints + A8 step 建议（INFRA-1 + A7–A15 lite A8）

**DoD**：E14 通过。

---

## A18-P2 / plus（2 任务）

- [x] 13. A18-1 审计小结生成 — **blocked A17-core**（**E18**）
- [x] 14. Playwright regression：E13 + E14

> [e2e-matrix.md](../completion-phase-infra/e2e-matrix.md)

---

## 实施顺序

[linkage.md §全局实施顺序](../completion-phase-infra/linkage.md#全局实施顺序)
