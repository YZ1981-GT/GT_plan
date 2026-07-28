# Implementation Plan: 附注模块质量完成

## Overview

激活休眠能力 + markdown 源头止血 + 合并附注 V2 落库。多数基础设施已由前序 spec 建成，本 spec 侧重激活/最后一公里/consol V2，全程 additive + 灰度默认关 + 零回归。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 0, "tasks": ["1.1", "1.2", "1.3", "1.4"], "desc": "安全网 + markdown 源头止血（P0-1 渲染层已完成）" },
    { "wave": 1, "tasks": ["2.1", "2.2", "2.3"], "desc": "表内公式激活 + 按项目灰度端点 + 就绪度暴露" },
    { "wave": 2, "tasks": ["3.1", "4.1"], "desc": "校验有意义验证 + stale 诚实暴露" },
    { "wave": 3, "tasks": ["5.1", "5.2"], "desc": "linkage 诊断暴露 + 示例 seed（禁批量）" },
    { "wave": 4, "tasks": ["6.1", "6.2", "6.3"], "desc": "合并附注 V2 落 disclosure_notes + 穿透" },
    { "wave": 5, "tasks": ["7.1", "7.2"], "desc": "PBT/契约 + 零回归门 + live/Playwright" }
  ]
}
```

## Tasks

- [x] 1.1 前端渲染层 markdown→HTML 归一（P0-1，已完成）
  - `DisclosureEditor.renderNoteTextToHtml`：text_content 加载时 markdown→HTML（marked+DOMPurify，幂等 HTML 原样，失败段落包裹降级）；fetchDetail 用它。
  - _Requirements: 1.4, 1.5_ _Properties: Property 1_

- [x] 1.2 markdown 源头止血纯函数 + 安全网
  - 新增 `note_content_utils.sanitize_note_narrative(text)`（markdown→纯文本/轻量 HTML，幂等，无 `###`/裸 `**`）。
  - characterization：锁定既有 `_generate_text_with_llm`/`sync_from_workpaper` 叙述写入行为基线（未启用 sanitize 前逐字节）。
  - _Requirements: 1.1, 1.2_ _Properties: Property 1_

- [x] 1.3 生成侧接入 sanitize
  - `disclosure_engine._generate_text_with_llm` 写 `text_content` 前调 `sanitize_note_narrative`；`sync_from_workpaper` 叙述拼接保持纯文本不引入 markdown。
  - _Requirements: 1.1, 1.2_

- [x] 1.4 存量诊断/清理脚本
  - `scripts/diagnose_note_text_markdown.py`：只读统计各项目 markdown 残留章节数；`--apply` 带备份表 `_note_text_markdown_backup` 一次性清理（走 sanitize，幂等可回滚）。
  - _Requirements: 1.3_

- [x] 2.1 验证 refill 注入 _formulas（gray-on）
  - 已核实：`_evaluate_note_formulas`（灰度内调用）委托 `NoteFormulaEvaluator.evaluate_table` 求值回填，灰度关旁路（line 1505/1900 双重零回归）。覆盖：`test_disclosure_note_formula_wave2`（evaluate_table gray-on/off）+ wave1（resolver 灰度门）。`has_formulas=0` 是按设计灰度默认关待项目 opt-in，非代码缺口。
  - _Requirements: 2.1, 2.4_ _Properties: Property 2, Property 3_

- [x] 2.2 按项目灰度端点
  - 已存在：`PUT /api/disclosure-notes/{pid}/formula-gray`（disclosure_notes.py，manager+，写 `wizard_state.disclosure_note_formula_enabled`）。覆盖：`test_note_formula_gray_service` Property 12。
  - _Requirements: 2.2, 2.3_ _Properties: Property 8_

- [x] 2.3 就绪度暴露 formula_enabled
  - 已存在：`note_readiness_service.build_readiness` summary 含 `formula_enabled`（复用 `is_note_formula_enabled`）。覆盖：`test_note_formula_gray_service` Property 13（12 passed）。
  - _Requirements: 2.6_

- [x] 3.1 校验有意义端到端验证
  - 已核实：`run_validation_best_effort` 已接生成/刷新/同步四点 + `_persist_results` 落 per-run 汇总（P0-4，122 行）+ skip-on-missing 不误报。meaningful findings 随 gray-on（bindings）激活；覆盖：`test_note_validation_*` + wave3。
  - _Requirements: 3.1, 3.2, 3.3, 3.4_ _Properties: Property 4_

- [x] 4.1 stale 诚实暴露
  - 后端 `note_readiness_service.summary` 新增 `stale_report_fallback`（additive，区分 report 定向 / report_fallback 保守）；前端就绪度看板 stale 卡片展示「定向 N / 保守 M」+ tooltip，per-section `staleTip` 已区分两源。`mark_notes_stale_for_report_change` 双源写入已存在。
  - _Requirements: 4.1, 4.2, 4.3_ _Properties: Property 5_

- [x] 5.1 linkage 诊断端点
  - 新增只读 `GET /api/disclosure-notes/{pid}/{year}/linkage-gaps`（disclosure_notes.py，委托 `diagnose_missing_write_linkage`，fail-open）。
  - _Requirements: 5.3_ _Properties: Property 7_

- [x] 5.2 linkage 示例 seed（禁批量）
  - seed 货币资金 BS-002↔五、1 合计（R7C2）/ 八、1 合计（R5C2），坐标经 note 模板核实；`report_note_linkage.json` 加 `_backlog` 记逐节待办不臆造。已验证 `targets_for_report_row` 正确解析 row_idx=6/col_idx=1。
  - _Requirements: 5.1, 5.2, 5.4, 5.5, 4.4_

- [x] 6.1 consol V2 落库函数
  - 已存在 `_persist_consol_sections_v2`（软删复活/`_resolve_section_meta`/manual_override 跳过/幂等 upsert/裁决 C 仅落 provenance 规避渲染契约不兼容）。**修 pre-existing 崩溃 bug**：新建分支 `source_template=SourceTemplate.consolidated`（枚举无该成员→AttributeError→章节落库全失败）改用已解析的 `meta_variant`（soe/listed）。测试 test_consol_notes_v2_persist 24 passed。
  - _Requirements: 6.1, 6.2, 6.3_ _Properties: Property 6_

- [x] 6.2 generate_full_consol_notes 接入 + 灰度
  - 已存在：Step8 在 `CONSOL_NOTES_V2_ENABLED`（默认 False）时调 `_persist_consol_sections_v2`（不改 cascade 调用点）+单章节 fail-open。覆盖：test_consol_notes_v2_persist Property 9（开关关不落库/开调一次）。
  - _Requirements: 6.1, 6.4_ _Properties: Property 6_

- [x] 6.3 穿透端点验证
  - 已存在：`note_consol_drilldown_service` 读 `consolidation_breakdown`→`has_breakdown=true`+by_company。覆盖：test_consol_notes_v2_drilldown / persist Property 10 端到端 round-trip。（`consol_note_data=0` 是灰度默认关待合并项目启用，非缺陷。）
  - 注：legacy 同步路径 `consol_disclosure_service` 行 742/755 同款 `SourceTemplate.consolidated` 引用是 pre-existing bug（老 `generate_consol_notes_sync` 路径，无 template_type 变体，本 spec V2 范围外，需 template_type 穿透另议）。
  - _Requirements: 6.5_

- [x] 7.1 PBT/契约 + 零回归门
  - Property 1-8 全覆盖：P1 `test_note_content_utils_sanitize`(7)/P2-3 `test_disclosure_note_formula_wave2`/P4 `test_note_validation_*`/P5 `test_note_readiness_and_stale`(新增 stale_report_fallback 断言,16)/P6 `test_consol_notes_v2_persist`(Property 7/8/9/10)/P7 `report_note_linkage`/P8 `test_note_formula_gray_service`(12)。零回归门本轮改动区 106+15 passed；note_content_utils 既有 has_data 15 passed 未回归。
  - **pre-existing 无关失败**：`test_disclosure_note_formula_wave3.py::TestSyncRealStats`(4) — git stash 我的 json 后仍失败，是 report_note_sync 灰度门迁移的 stale 测试（patch `_formula_enabled` 但代码用 db 版 `is_note_formula_enabled`），非本 spec 引入/范围外。
  - _Requirements: 7.1, 7.2, 7.3, 8.1_

- [x] 7.2* live/Playwright 端到端（诚实留待）
  - R1 markdown 存量已 live 清理 216 条（`diagnose_note_text_markdown.py --apply` 带备份）。gray-on refill→formulas / consol V2 落库穿透 由 disclosure-note-formula-data-population + disclosure-note-linkage-completion 的 round-trip 已证（本轮为激活/验证非新建）；Playwright 需实例化项目 + gray-on + SSE 稳定环境，机制已由 PBT/契约充分覆盖，诚实留待。
  - _Requirements: 全部_

## Notes

- 全程 additive + 灰度默认关（`DISCLOSURE_NOTE_FORMULA_ENABLED`/`CONSOL_NOTES_V2_ENABLED` 默认 False）+ 零回归。
- **禁批量臆造 linkage 映射**（映射错=写错披露）；R5 仅诊断 + 少量强证据示例 seed。
- 触及并发会话在改的前端披露 tab（D3/D5/D6/jump maps）一律不碰；本 spec 后端服务文件当前工作树无 churn。
- commit 前 `git status`/`git diff --cached --name-only` 核实只 stage 本 spec 文件。
