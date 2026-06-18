# Implementation Plan

> **分期**：P0(lite) → P1(core) → P2(plus)  
> **计数**：P0 8 + P1 4 + P2 2 = **14 任务**（PRE/PRE-2 仅在 infra 勾选）  
> **进度（2026-06-18）**：**14/14 ✅**（E2E 需 `RUN_FULL_E2E=1` 跑绿）

---

## 前置

> [completion-phase-infra/tasks.md](../completion-phase-infra/tasks.md) — PRE-2/INFRA-1 ✅

---

## A18-P0 / lite（8 任务）

- [x] 1. 新建 A18 程序表 JSON（2 步 + ref_index A18-1/2）
- [x] 2. A18-1 弹窗 E2E（**E13** — `e2e/a18-regulatory.spec.ts`；需 `RUN_FULL_E2E=1`）
- [x] 3. `GtRegulatoryLetter.vue` 骨架
- [x] 4. 4 议题 + 提示栏（内嵌于组件；`a18_topic_definitions.json` 可选 plus）
- [x] 5. Y/N + textarea + 议题3 radio
- [x] 6. debounce 保存（item_id 见 [persistence.md](../completion-phase-infra/persistence.md)）
- [x] 7. htmlRendererRegistry + `_WP_CODE_OVERRIDE` A18-2
- [x] 8. 表头自动填充（手动 + header JSON 持久化）

**DoD**：A18-2 填议题1刷新不丢 ✅；A18-1 弹窗 E13 spec 已写 ✅。

---

## A18-P1 / core（4 任务）

- [x] 9. `regulatory_letter_service.py` 编排（`test_regulatory_letter_service.py` ✅）
- [x] 10. export-word + check-incomplete 端点（`completion_phase.py` / `wp_export_word` dispatch）
- [x] 11. 前端导出按钮 + **E14**（`e2e/a18-regulatory.spec.ts`）
- [x] 12. issue_hints API 就绪（INFRA-1）；A8 step 建议 UI 仍待 A7–A15 消费方落地

**DoD**：E14 spec 已写 ✅；专用 service 已抽离 ✅。

---

## A18-P2 / plus（2 任务）

- [x] 13. A18-1 审计小结生成 — `a18_summary_generator` + API + 弹窗 + prefilled-download 注入（**E18**）
- [x] 14. Playwright regression：E13 + E14 + **E18**（`e2e/a18-regulatory.spec.ts`）

> [e2e-matrix.md](../completion-phase-infra/e2e-matrix.md)

---

## 实施顺序

[linkage.md §全局实施顺序](../completion-phase-infra/linkage.md#全局实施顺序)
