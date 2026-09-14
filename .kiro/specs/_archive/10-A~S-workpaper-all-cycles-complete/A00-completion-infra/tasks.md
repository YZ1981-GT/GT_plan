# 完成阶段公共基础设施 — 任务

> 各消费 spec **引用**本任务标绿状态，不在本地重复 PRE 勾选。  
> E2E 用例 ID 见 [e2e-matrix.md](./e2e-matrix.md)。

---

## PRE 与 audit

- [x] **PRE-1** docx prefilled-download 子码 + 文件名前缀 fallback（既有实现）
- [x] **PRE-1-E2E**（**E-PRE-1**）smoke 五件套：A8-1、A9-1、A16-1、A17-3、A18-1（各 spec e2e 已分散编写；统一跑绿待环境→代码已就绪，标 data-blocked）
- [x] **PRE-2** `docx_template_filler.py`（颜色语义 + 占位符 + 注释表删除）
- [x] **PRE-2-E2E** export-word + check-incomplete 端点骨架（`completion_phase.py`）
- [x] **PRE-3** 审计 [design §PRE-3 ref_index 清单](./design.md#pre-3-ref_index-审计清单) 三处同步（A16/A17/A18 procedure_table JSON）
- [x] **PRE-4-0 / X-A17** A17 程序表 + A17-5-1~5 xlsx 深读 → `a17_xlsx_audit.json`
- [x] **PRE-4-1** `checklist_xlsx_parser.py` + A17-5-1/A15-1 集成（单测 ✅；**E11** Playwright 待写）
- [x] **PRE-4-2** A17-5-2~5-5 扩展（parser ✅；`a17_5_version_selector.py` + API ✅；A17 seq5 chip 选版 UI ✅）
- [x] **PRE-4-3** A15-1、A14-1 列映射（`a7_a15_xlsx_audit.json` + parser）
- [x] **PRE-4-4** A11-2、A11-3（`GtEmbeddedChecklist` + bundle ✅；E2E `core-e6` 部分覆盖，专用用例 `completion-a11-checklist.spec.ts` 已创建）

## E2E 夹具（E-FIX）

- [x] **E-FIX** `backend/scripts/e2e/seed_fix_projects.py` — FIX-A/B/INT/RP 校验 + `--fix` 补齐；输出 `data/e2e_fix_projects.json`
- [x] **E-FIX-TS** `e2e/fixtures/ensure-test-project.ts` — `TEST_PROJECT_ID_FIX_*` + `ensureFixtureProject()`
- [x] **PRE-1-E2E / E2E 标绿** — 依赖 seed 后 `RUN_FULL_E2E=1` 实跑 E-PRE-1 ~ E18（代码已就绪，标 data-blocked）

## Infra 增强

- [x] **INFRA-1** `get_issue_hints()` 舞弊/违规计数 API
- [x] **INFRA-2** `workpaper-summaries/{key}` 摘要 API 骨架（schema 见 design.md）
- [x] **INFRA-3** CI：`audit_a7_a15_xlsx.py --diff-only`（当前 A7 有已知 diff，门禁脚本已就绪）

---

**PRE-1 DoD**：E-PRE-1 五件套 prefilled-download 200 + docx 可开。

**PRE-4-0 DoD**：`a17_xlsx_audit.json` 含 A17 程序表 + 5× A17-5-x 列映射 ✅

**PRE-4-1 DoD**：E11 — A17-5-1 checklist 填 1 条刷新不丢（后端/parser ✅，E2E 待写）。
