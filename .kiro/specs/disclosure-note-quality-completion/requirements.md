# Requirements Document

## Introduction

附注模块经多轮复盘后，机制已基本齐备（结构化推送 29 科目已 wire、就绪度看板、校验落库、自动同步广泛接入、表头模板优先、stale_source 已填），但 postgres 实证仍有几处「能力就位但生产不产出/名不副实」的缺口：

- 附注正文 `text_content` 有 **218 条**残留 LLM markdown 草稿（`###`/`**`/`需补充` 123 条，跨 4 项目）。渲染层已在本轮直接修复（markdown→HTML 归一），但**生成/同步侧仍会向 text_content 写 markdown**（源头未止血），且存量脏数据仍在。
- 附注表内公式生产 **0 条**（`table_data._formulas` 全空）：引擎 `resolve_formula` 与模板 `note_template_bindings.json` 的 119 条 movement/合计 binding 都就绪，但**存量附注不会自动获得 binding**（binding 仅在生成时注入），且灰度 `DISCLOSURE_NOTE_FORMULA_ENABLED` 默认关、无项目启用。
- 校验跑了 **122 次全 error=0/warn=0**：因附注无 binding 可比对 + skip-on-missing 全过 → 校验「运行但无意义」，发现不了合计不平/变动表恒等式错。根因链回到 binding 缺失。
- stale 标记 **221 条全 `report_fallback`**：因 `report_note_linkage.json` 零业务条目 → 恒走全量兜底 → 「哪些附注真受报表变更影响」无法区分，标记退化成噪声。
- 合并附注双真源仍空（`consol_note_data`=0 + `disclosure_notes.consolidation_breakdown`=0）：合并附注 V2 未落 `disclosure_notes`，附注级穿透 `has_breakdown` 恒 false。

本 spec 系统化收敛这些缺口，遵循「零回归 + additive + 灰度默认关 + 禁臆造披露映射」原则。

## Glossary

- **text_content**: `disclosure_notes.text_content`，附注叙述正文（富文本框绑定）。
- **markdown 残留**: 历史「生成附注」LLM 把 markdown 草稿（`###`/`**`/`- 列表`/`需补充信息`）写入 text_content，而富文本框按 HTML 渲染 → 显示字面 markdown。
- **表内公式 binding**: `note_template_bindings.json` 声明的单元格公式（`source='formula'`/`formula_kind='sum'|'movement'`），生成/refill 时注入 `table_data._formulas` 供引擎 `resolve_formula` 求值。
- **movement 公式**: 变动表恒等式「期末=期初+增−减」。
- **sum 公式**: 同表同列 `row_type=data` 行求和得合计/小计。
- **DISCLOSURE_NOTE_FORMULA_ENABLED**: 表内公式求值灰度开关，默认 False（逐字节零回归）。
- **report_note_linkage**: `backend/data/disclosure/report_note_linkage.json`，报表行→附注单元格映射真源；当前零业务条目。
- **stale_source**: `disclosure_notes.stale_source`，标记附注 stale 的来源（`report`=linkage 命中的定向标记 / `report_fallback`=无 linkage 时全量保守标记 / 其他事件源）。
- **就绪度看板**: `note_readiness_service.build_readiness`，只读汇总各章节 has_data/同步/校验/stale 状态。
- **consol V2**: `consol_disclosure_service.generate_full_consol_notes`，合并附注生成，当前只返 list 不落 `disclosure_notes`。
- **consolidation_breakdown**: `disclosure_notes.consolidation_breakdown` JSONB，合并附注按主体穿透明细，激活附注级穿透 `has_breakdown`。
- **skip-on-missing**: 校验器缺数据源时 passed=True + details.skipped（不误报），是既有正确行为。

## Requirements

### Requirement 1: text_content markdown 源头止血 + 存量诊断

**User Story:** 作为审计师，我希望附注正文不再出现 `###`/`**` 等字面 markdown，且新生成的附注正文就是干净可读的富文本，不依赖前端渲染兜底。

#### Acceptance Criteria

1. WHEN 「生成附注」LLM 产出叙述 THEN 系统 SHALL 在写入 `text_content` 前将 markdown 归一为 HTML（或纯文本），不再向 text_content 写入 `###`/`**`/markdown 列表语法。
2. WHEN 底稿同步（`sync_from_workpaper`）推送叙述 `_note_texts` THEN 系统 SHALL 保持既有纯文本/HTML 拼接行为不引入 markdown。
3. WHEN 提供存量诊断脚本 THEN 系统 SHALL 只读统计各项目 text_content 含 markdown 残留的章节数（不自动改库），并支持带备份的一次性清理（幂等，可回滚）。
4. WHEN 前端加载任意 text_content THEN 渲染层 SHALL 保持已实现的 markdown→HTML 归一（幂等：HTML 原样），作为兜底与止血冗余。
5. WHERE text_content 已是 HTML THE 系统 SHALL 原样保留不二次转换。

### Requirement 2: 表内公式 binding 落存量附注 + 按项目灰度

**User Story:** 作为审计师，我希望附注的合计/变动表能自动计算并对得上，而不是永远手填、永远 0 公式。

#### Acceptance Criteria

1. WHEN refill/generate 附注 AND 项目已启用表内公式 THEN 系统 SHALL 将 `note_template_bindings.json` 对应章节的 formula binding 注入 `table_data._formulas`（存量附注经 refill 后即获得 binding）。
2. WHEN `DISCLOSURE_NOTE_FORMULA_ENABLED` 为全局 True OR 项目 `wizard_state.disclosure_note_formula_enabled` 为 True THEN 该项目 SHALL 启用表内公式求值；否则 SHALL 逐字节等价当前（不注入不求值）。
3. WHEN 提供按项目灰度端点 THEN manager/partner+ SHALL 可开关某项目的表内公式，写入 `wizard_state` JSONB（无新列）。
4. WHEN 引擎求值 formula binding THEN 系统 SHALL 复用既有 `resolve_formula`（sum/movement），不新增 source 枚举、不臆造未声明公式。
5. WHERE 某单元格已手工录入（manual 且有值） THE 系统 SHALL 手工优先，不用公式结果覆盖。
6. WHEN 就绪度看板汇总 THEN SHALL 暴露项目级 `formula_enabled` 状态。

### Requirement 3: 校验有意义 — 有 binding 后真发现问题

**User Story:** 作为质控复核人，我希望附注校验能真发现合计不平、变动表恒等式错，而不是恒 0 发现。

#### Acceptance Criteria

1. WHEN 附注含 formula binding AND 校验运行 THEN 系统 SHALL 对合计/小计/变动表恒等式产出真实 findings（不平→error/warning），不再因无可比对象恒 passed。
2. WHEN 缺数据源 THEN 系统 SHALL 保持 skip-on-missing（passed=True + skipped 标记），不误报。
3. WHEN 生成/刷新/同步后 THEN 系统 SHALL fail-open 自动补跑 `validate_all`（异常 rollback 校验事务不影响主操作），findings 落 `note_validation_results` per-run 汇总。
4. WHEN 就绪度看板/左树 THEN SHALL 按章节暴露 error/warning 计数徽标。

### Requirement 4: stale 诚实 — 区分定向 vs 全量兜底

**User Story:** 作为审计师，我希望「待刷新」标记能区分「这条附注真受报表变更影响」和「保守全量标记」，不被噪声淹没。

#### Acceptance Criteria

1. WHEN 报表变更触发 stale AND 存在 linkage 命中该章节 THEN 系统 SHALL 标 `stale_source='report'`（定向）。
2. WHEN 无 linkage 命中 THEN 系统 SHALL 标 `stale_source='report_fallback'`（全量保守），行为不变。
3. WHEN 就绪度看板/UI 展示 stale THEN SHALL 显式区分 `report`（定向，高置信）与 `report_fallback`（全量，低置信提示「保守标记」）。
4. WHEN linkage 有该章节条目 THEN 定向标记 SHALL 生效（依赖 R5 逐节维护的数据）。

### Requirement 5: report_note_linkage 逐节增量维护 + 诊断（禁批量臆造）

**User Story:** 作为审计师，我希望报表行与附注单元格的关系可逐节按源模板维护并被校验/stale/引用复用，而不是零条目恒空。

#### Acceptance Criteria

1. WHEN 维护 linkage THEN 系统 SHALL 支持按 note_section 逐节增量录入 `report_row_code → {note_section, cell, table_index}`（依据源模板/审计口径），且坐标非法/缺失自动跳过并记录。
2. WHEN 系统 THEN SHALL NOT 批量臆造报表行→附注单元格映射（映射错=写错披露）。
3. WHEN 提供只读诊断 THEN 系统 SHALL 列出「有报表行汇总但无 linkage 写值映射」的章节，供人工评估（不自动填）。
4. WHEN 已维护 linkage 的章节 THEN 报表→附注同步/stale 定向/报表行「关联附注」引用 SHALL 复用同一 linkage 单一真源。
5. WHEN 作为示例 THEN 系统 SHALL 只对少量单行 1:1（报表行↔附注单一合计）且强证据的章节 seed linkage，其余记录待办不臆造。

### Requirement 6: 合并附注 V2 落 disclosure_notes + 穿透

**User Story:** 作为集团审计的现场经理，我希望合并附注能进入统一的附注模块并支持按主体穿透，而不是停在第二套空存储。

#### Acceptance Criteria

1. WHEN `generate_full_consol_notes` 生成合并附注 AND `CONSOL_NOTES_V2_ENABLED` 为 True THEN 系统 SHALL 将合并章节 upsert 到 `disclosure_notes`（带 `source_project_id`、`consolidation_breakdown`、`last_sync_source='consolidation'`）。
2. WHEN 落库前 THEN 系统 SHALL 核实 aggregate 产出的 table_data 与前端附注渲染契约（sub_table_data/_tables/headers）兼容；不兼容则做结构适配或仅落 provenance（不产空表/报错）。
3. WHEN 合并附注章节与单体附注章节命名 THEN 系统 SHALL 靠 `disclosure_notes` 唯一键 (project_id,year,note_section) 隔离，复用既有软删复活/`_resolve_section_meta`/manual_override 跳过范式。
4. WHEN `CONSOL_NOTES_V2_ENABLED` 为 False（默认） THEN 系统 SHALL 逐字节等价当前（不落库）。
5. WHEN 落库成功 THEN 附注级穿透端点 SHALL 返回 `has_breakdown=true` + 按主体明细。

### Requirement 7: 零回归、灰度默认关、向后兼容

**User Story:** 作为平台维护者，我希望所有新能力默认关闭、additive 引入，未启用时既有附注/报表/交付/同步行为逐字节不变，可随时回退。

#### Acceptance Criteria

1. WHEN 未启用任何新灰度 THEN 所有既有附注/报表/交付/同步端点 SHALL 逐字节等价当前行为。
2. WHEN 新增字段/开关 THEN SHALL additive（不改表结构、不删既有字段、历史空值兼容）。
3. WHEN 分批实施 THEN 各波 SHALL 独立可回退（关灰度即回退）。
4. WHEN 触及并发会话在改文件 THEN SHALL 优先 additive 追加、commit 前核实只 stage 本 spec 文件。

### Requirement 8: 属性化可测

**User Story:** 作为质控复核人，我希望关键正确性属性有自动化测试守护，防止后续改动回归。

#### Acceptance Criteria

1. WHEN 交付 THEN 关键正确性属性（markdown 归一幂等/formula 注入手工优先/灰度两态零回归/stale 定向 vs 兜底/校验 skip-on-missing/consol 落库隔离/linkage 坐标非法跳过）SHALL 有 PBT 或契约测试覆盖。
