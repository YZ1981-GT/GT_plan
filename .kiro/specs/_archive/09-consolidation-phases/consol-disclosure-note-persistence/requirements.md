# Requirements Document

## Introduction

合并模块 P1 复盘发现两处「已建成但空转」的合并附注 V2 能力：

1. **落库空转**：`generate_full_consol_notes` 已能生成 180 章节并携带 `consolidation_breakdown`
   穿透 provenance，`_persist_consol_sections_v2` 落库骨架也已由 disclosure-note-linkage-completion
   建成，但整条链路（读端 dispatcher / 级联步骤 6 / 落库 Step 8）均硬编码在全局开关
   `CONSOL_NOTES_V2_ENABLED`（config 默认 False）之后 → 生产从不触发，`disclosure_notes` 中合并
   provenance 恒 0 行，附注级穿透端点 `consol-breakdown` 恒返回空。
2. **双真源风险**：合并附注表格渲染走 `consol_note_data`（老路径），穿透 provenance 只在实时生成的
   章节 dict 内存里，两者未收敛，前端无从按项目可控地启用。

本 spec 将 V2 落库/穿透从「全局灰度默认关」收敛为「按项目可控 opt-in + 严格零回归」，使单个合并项目
可开启后：读端走 V2 生成、Step 8 落库 provenance、既有 `ConsolBreakdownDialog`（穿透弹窗，读
`consol-breakdown` 端点从落库表取数）真正显示子公司贡献明细。**穿透显示唯一来源=落库 + 端点**
（P1-A(a) 决策：不在读端 schema 携带 breakdown 字段——该字段无消费者，已删）。

**关键决策**：

- **Decision 1（推进启用）**：穿透基础设施（生成/落库/端点/前端弹窗）均已建齐，仅缺按项目 gate。
  加法式改造，零回归。
- **Decision 2（provenance-only）**：落库仅写 provenance 三字段（`source_project_id` /
  `consolidation_breakdown` / `last_sync_source`），**不落 V2 aggregate 的 table_data 作渲染表**
  （其 shape 与附注渲染契约不兼容），表格渲染唯一真源保留 `consol_note_data` 老路径。
- **不改级联步骤 6 门控**：`consol_cascade_refresh_service` 步骤 6 的 `patch({module}.settings)` 单测
  以模块引用方式打桩，改为读真实 settings 的灰度服务会破坏该单测；且读端 dispatcher 改按项目后，
  查看附注时已按需触发落库，级联步骤保持全局门控即可，无需改动。

## Glossary

| 术语 | 含义 |
|------|------|
| V2 合并附注 | `generate_full_consol_notes`：消费子公司单体附注汇总的 180 章节生成路径 |
| dispatcher | `generate_consol_notes_with_flag`：读/建/存端点统一入口，按 flag 选 V2 或老版 |
| Step 8 落库 | `generate_full_consol_notes` 尾部调 `_persist_consol_sections_v2` 写 provenance |
| provenance | 章节 `consolidation_breakdown = {by_company:[...], computed_at}` 子公司贡献明细 |
| 项目级 opt-in | `project.wizard_state.consol_notes_v2_enabled`（JSONB，默认 False） |
| 生效值 | `全局 CONSOL_NOTES_V2_ENABLED OR 项目 opt-in` |
| 穿透弹窗 | 前端 `ConsolBreakdownDialog`（source=note），读 `consol-breakdown` 端点显示 by_company |

## Requirements

### Requirement 1: 按项目灰度统一入口

**User Story:** 作为平台，我希望有一个统一的按项目灰度判定，使合并附注 V2 可对单个项目 opt-in 启用，
而不影响其它项目。

#### Acceptance Criteria

1. WHEN 判定某项目是否启用 V2 THEN 系统 SHALL 提供 `is_consol_note_v2_enabled(db, project_id)`：
   全局 `CONSOL_NOTES_V2_ENABLED=True` → True（向后兼容全开，不查项目级）；否则查
   `project.wizard_state.consol_notes_v2_enabled`（默认 False）。
2. WHEN 项目不存在 / `wizard_state` 非 dict / 任何异常 THEN 系统 SHALL fail-open 返回 False（绝不误开）。
3. WHEN 全局开关为 True THEN 系统 SHALL 短路返回 True 而不查库（镜像 `is_note_formula_enabled`，
   保证既有 `monkeypatch(settings, ...)` 单测零回归）。

### Requirement 2: 读端按项目返回 V2 章节

**User Story:** 作为审计人员，我希望对已 opt-in 的合并项目，查看合并附注时走 V2 生成路径。

#### Acceptance Criteria

1. WHEN `generate_consol_notes_with_flag` 被调用 THEN 系统 SHALL 用 `is_consol_note_v2_enabled`
   判定；生效则走 V2 生成 + 适配为 `ConsolDisclosureSection`，否则老版 7 骨架章节。
2. WHEN 读端返回章节 THEN 系统 SHALL **不在读端 schema 携带穿透 provenance**（P1-A(a) 决策：
   `ConsolDisclosureSection` 不新增字段，穿透明细唯一来源=Step 8 落库 + `consol-breakdown` 端点）。
3. WHEN 未 opt-in 且全局关 THEN 读端返回结构 SHALL 与改造前逐字节一致（老版章节）。

### Requirement 3: Step 8 落库按项目触发（provenance-only）

**User Story:** 作为平台，我希望对已 opt-in 的项目，V2 生成时落库穿透 provenance，供穿透端点读取。

#### Acceptance Criteria

1. WHEN `generate_full_consol_notes` 执行到 Step 8 THEN 系统 SHALL 用 `is_consol_note_v2_enabled`
   门控 `_persist_consol_sections_v2`（生效才落库）。
2. WHEN 落库 THEN 系统 SHALL 仅写 provenance 三字段，不覆盖既有渲染 `table_data`（裁决 C）。
3. WHEN 全局关且未 opt-in THEN Step 8 SHALL 不调用 `_persist_consol_sections_v2`（既有 Property 9 单测
   以 `monkeypatch(settings)` 打桩，须保持通过）。

### Requirement 4: 灰度配置端点

**User Story:** 作为现场经理，我希望能对合并项目开启/关闭合并附注 V2。

#### Acceptance Criteria

1. WHEN `GET /api/consolidation/notes/{project_id}/config/consol-note-gray` THEN 系统 SHALL 返回
   `{project_enabled, global_enabled, effective_enabled}`（readonly 权限）。
2. WHEN `PUT /api/consolidation/notes/{project_id}/config/consol-note-gray` 带 `{enabled}` THEN 系统
   SHALL 写 `project.wizard_state.consol_notes_v2_enabled`（flag_modified 落库）并返回最新灰度状态
   （edit 权限，现场经理+）。
3. WHEN 项目不存在 THEN 端点 SHALL 返回 404。
4. WHEN 配置路由注册 THEN 其路径 `{project_id}/config/consol-note-gray`（3 段静态）SHALL 不与
   `{project_id}/{year}`（2 段 int）冲突。

### Requirement 5: 零回归与向后兼容

**User Story:** 作为平台维护者，我要求本改造对未 opt-in 项目与既有测试逐字节零回归。

#### Acceptance Criteria

1. WHEN 全局开关 True THEN 所有既有以 `monkeypatch(settings, "CONSOL_NOTES_V2_ENABLED", True)` 的单测
   SHALL 仍通过（灰度服务短路返 True）。
2. WHEN 级联刷新步骤 6 THEN 其门控 SHALL 保持全局 `CONSOL_NOTES_V2_ENABLED`（不改，避免破坏
   `patch({module}.settings)` 单测）。
3. WHEN 适配器 `_adapt_v2_sections_to_schema` 处理任意 V2 章节形态 THEN 其 SHALL 永不抛错且输出
   合法 `ConsolDisclosureSection`（不新增字段，S4 契约测试仍通过）。

### Requirement 6: 属性化可测

**User Story:** 作为平台维护者，我希望灰度判定逻辑有属性测试守卫，防止后续改动引入误开/误关。

#### Acceptance Criteria

1. WHEN 校验灰度服务 THEN 系统 SHALL 提供属性测试覆盖：全局开/关 × 项目 opt-in 开/关 → 生效值 ==
   `global OR optin`；项目不存在 / 非 dict / 异常 → False。
