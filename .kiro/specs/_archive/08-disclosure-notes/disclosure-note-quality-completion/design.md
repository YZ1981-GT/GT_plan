# Design Document

## Overview

本 spec 的核心发现（读码实证）：附注表内公式/校验/stale/linkage 的**能力基础设施已由前序 spec（disclosure-note-formula-data-population、disclosure-note-linkage-completion）建成，但在生产处于休眠/未激活状态**：

| 能力 | 已有 | 生产状态 | 缺口 |
|------|------|----------|------|
| 表内公式求值 | `disclosure_engine._evaluate_note_formulas` + `note_formula_derivation.derive_note_formulas` + `note_formula_gray_service.is_note_formula_enabled` | `has_formulas=0`（灰度全关，无项目启用） | 激活入口 + 验证 refill 注入 |
| 校验落库 | `run_validation_best_effort` + `validate_all` + `note_validation_results` | 122 次全空（无 binding 可比） | 依赖公式激活后有对象 |
| stale 定向 | `mark_notes_stale_for_report_change`（report/report_fallback） | 221 全 fallback（linkage 空） | 就绪度暴露区分 + linkage 数据 |
| linkage 诊断 | `report_note_linkage.diagnose_missing_write_linkage` | 零业务条目 | 诊断暴露 + 示例 seed（禁批量） |
| 合并附注 V2 | `consol_disclosure_service.generate_full_consol_notes` | 只返 list 不落库 | 落 disclosure_notes + 穿透 |
| markdown 归一 | 渲染层（本轮 P0-1 已修） | 218 条存量 + 生成侧仍写 markdown | 源头止血 + 存量诊断/清理 |

因此本 spec 是「**激活 + 最后一公里 + consol V2 + markdown 源头止血**」而非从零重建。所有改动 additive + 灰度默认关 + 零回归。

## Architecture

```
生成/refill (disclosure_engine)
  ├─ [R1] LLM 叙述 → _sanitize_note_narrative(markdown→纯文本/HTML) → text_content   ← 源头止血
  ├─ [R2] _formula_on=is_note_formula_enabled(db,pid) → _evaluate_note_formulas 注入/求值 _formulas  ← 激活
  └─ [R3] run_validation_best_effort → note_validation_results (有 binding→真 findings)  ← 依赖 R2

报表变更 → mark_notes_stale_for_report_change
  └─ [R4] linkage 命中→stale_source='report' / 否则 'report_fallback'
           → note_readiness_service 暴露 report vs report_fallback 区分

report_note_linkage.json (逐节增量, 禁批量臆造)
  ├─ [R5] diagnose_missing_write_linkage → 只读诊断端点/看板
  └─ [R5] seed 少量单行 1:1 强证据章节示例

合并刷新 → generate_full_consol_notes
  └─ [R6] CONSOL_NOTES_V2_ENABLED → _persist_consol_sections_v2 upsert disclosure_notes
           (source_project_id + consolidation_breakdown + last_sync_source='consolidation')
```

## Components and Interfaces

### R1 · markdown 源头止血
- **新增** `note_content_utils.sanitize_note_narrative(text) -> str`（纯函数）：markdown→纯文本或轻量 HTML（`###`→去标记保文字/`**x**`→`x`/`- `列表→保留文字），幂等（已是纯文本/HTML 原样）。
- `disclosure_engine._generate_text_with_llm` 写 `text_content` 前调它（LLM 产出经归一，不再写 markdown 语法）。
- **前端渲染层**（P0-1 已完成）：`DisclosureEditor.renderNoteTextToHtml` markdown→HTML 归一，作止血冗余。
- **诊断/清理脚本** `scripts/diagnose_note_text_markdown.py`：只读统计 + `--apply` 带备份表一次性清理（幂等、可回滚，走 `sanitize_note_narrative`）。

### R2 · 表内公式激活 + 按项目灰度
- **验证** `disclosure_engine._evaluate_note_formulas`（灰度内）在 refill 时对存量附注注入/求值 `table_data._formulas`（gray-on 时 has_formulas>0）。
- **新增/复用端点** `PUT /api/disclosure-notes/{pid}/{year}/formula-gray`（manager/partner+）：写 `project.wizard_state.disclosure_note_formula_enabled`（JSONB，无新列）。若已存在则复用。
- `note_readiness_service.build_readiness` summary 增 `formula_enabled`（复用 `is_note_formula_enabled`）。
- **不改** `resolve_formula`/`derive_note_formulas`/source 枚举；手工优先由既有 `_evaluate_note_formulas` 保证。

### R3 · 校验有意义
- **验证** gray-on 后 `validate_all` 对合计/movement 恒等式产出真 findings；`run_validation_best_effort` 已接生成/刷新/同步四点。
- 就绪度/左树 findings 徽标已有（`latest_findings_by_section`），验证端到端。

### R4 · stale 诚实
- **验证** `mark_notes_stale_for_report_change` 写 report/report_fallback（已实现）。
- `note_readiness_service` 输出层区分 `stale_report`（定向）vs `stale_report_fallback`（保守），前端就绪度看板显式标注。

### R5 · linkage 逐节增量 + 诊断（禁批量）
- **暴露** `diagnose_missing_write_linkage` 为只读端点 `GET .../linkage-gaps`（列「有报表汇总但无 linkage」章节）。
- **seed** 少量单行 1:1 强证据章节（如货币资金 BS-002↔五、1 合计）到 `report_note_linkage.json`，其余记 backlog 不臆造。
- linkage 单一真源被 stale 定向 / 报表→附注同步 / 报表行「关联附注」引用复用（已有 `ReportNoteLinkage`）。

### R6 · 合并附注 V2 落库
- **新增** `consol_disclosure_service._persist_consol_sections_v2(db, project_id, year, sections)`：复用单体 `sync_from_workpaper` 的软删复活/`_resolve_section_meta`/manual_override 跳过/幂等 upsert 范式；写 `source_project_id`+`consolidation_breakdown`+`last_sync_source='consolidation'`。
- `generate_full_consol_notes` 末尾在 `CONSOL_NOTES_V2_ENABLED`（默认 False）时调它（Step8，不改现有 cascade 调用点）。
- **落库前** `_consol_table_data_compatible(section)` 核实 aggregate table_data 与前端渲染契约（`sub_table_data`/`_tables`/`headers`）；不兼容→结构适配或仅落 provenance（不产空表）。
- 附注级穿透端点读 `consolidation_breakdown` → `has_breakdown=true`。

## Data Models

- 无新表、无新列。
  - R2 灰度：`project.wizard_state.disclosure_note_formula_enabled`（JSONB bool）。
  - R6：复用既有 `disclosure_notes.source_project_id`/`consolidation_breakdown`/`last_sync_source`。
  - R1 清理备份：脚本建临时备份表 `_note_text_markdown_backup`（一次性，可回滚）。
  - R5：`report_note_linkage.json` 逐节追加条目。

## Correctness Properties

### Property 1: markdown 归一幂等
**Validates: Requirements 1.1, 1.4, 1.5**
`sanitize_note_narrative(x)` 幂等（已是纯文本/HTML 原样返回），且输出不含 `###`/裸 `**`markdown 标记。

### Property 2: 灰度两态零回归
**Validates: Requirements 2.2, 7.1, 7.3**
`DISCLOSURE_NOTE_FORMULA_ENABLED=False` 且项目未 override 时，refill/generate 输出的 table_data 与激活前逐字节等价（不注入 `_formulas`）。

### Property 3: formula 注入手工优先
**Validates: Requirements 2.1, 2.5**
gray-on 时，某单元格若 `_cell_modes[i]=manual` 且有值，公式结果不覆盖。

### Property 4: 校验 skip-on-missing
**Validates: Requirements 3.1, 3.2**
缺数据源→passed=True+skipped；有 binding 且合计/恒等式不平→产 error/warning。

### Property 5: stale 定向 vs 兜底
**Validates: Requirements 4.1, 4.2**
linkage 命中章节→`stale_source='report'`；无 linkage→`'report_fallback'`。

### Property 6: consol 落库章节隔离
**Validates: Requirements 6.1, 6.3, 6.4**
`CONSOL_NOTES_V2_ENABLED=True` 时合并章节按 (project_id,year,note_section) upsert，不与单体附注冲突；False 时不落库（零回归）。

### Property 7: linkage 坐标非法跳过
**Validates: Requirements 5.1**
非法/缺失 cell 坐标自动跳过并记录，不写非目标单元格。

### Property 8: 灰度端点权限
**Validates: Requirements 2.3**
formula-gray 端点仅 manager/partner+ 可写，写入 wizard_state 不新增列。

## Error Handling

- R1 sanitize 转换失败→段落包裹降级（保底不丢内容）。
- R2 `is_note_formula_enabled` 异常→fail-open False（绝不误开）。
- R3 `run_validation_best_effort` 异常→rollback 校验事务，不影响主操作（已实现）。
- R6 `_persist_consol_sections_v2` 单章节异常→记 warning 跳过该章节，不中断其余；整体 fail-open 不阻断 cascade。
- R5 linkage 坐标非法→跳过 + 记录（已实现）。

## Testing Strategy

- PBT：Property 1（sanitize 幂等/无 markdown）、Property 2（灰度两态）、Property 3（手工优先）。
- 契约测试：Property 4（校验 skip/真发现）、Property 5（stale 双源）、Property 6（consol 落库隔离+灰度关零回归）、Property 7（坐标非法跳过）、Property 8（权限）。
- 零回归门：附注域全量测试通过（排除 pre-existing 污染：hardening/engine_v2/variant_matrix/offline_*/migrate_disclosure_notes import 路径）。
- live/round-trip：consol V2 用真实项目 create→verify→restore（RESTORED_IDENTICAL）；formula 激活用真实项目 gray-on refill 验证 has_formulas>0 后 restore。
- Playwright（可选）：markdown 章节渲染无字面 `###`；就绪度看板 stale 区分。

## Migration

无 DB 迁移（全 additive，复用既有列 + wizard_state JSONB + JSON 配置文件）。R1 清理脚本建一次性备份表（非迁移）。
