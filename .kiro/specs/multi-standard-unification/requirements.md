# 需求文档：多准则状态统一（multi-standard-unification）

## 引言

当前项目的"适用准则"状态散落在 4 套口径、4 个位置，各模块各读各的，切换时极易不一致：
- `project.wizard_state.basic_info.data.template_type`（项目向导）
- 附注用 `current_standard`（soe_standalone / listed_standalone / soe_consolidated / listed_consolidated）
- 底稿用 `scenario`（normal / ipo / listed / transfer / restructure / fraud_response）
- 报表用 `applicable_standard`

**核心问题**：
1. 无单一真理源——切换准则时各模块各读各的，不一致是必然
2. 附注层已有成熟的 SOE↔Listed 互转（note_conversion_service V2 + ADR-021 + PBT roundtrip），但底稿层只有"生成时文件裁剪"（`_filter_files_by_scenario`），**没有"已编制底稿 SOE↔Listed 切换"能力**
3. 准则差异是多维的（企业性质 × 单体/合并 × 上市阶段），当前用扁平字符串表达，组合爆炸

本 spec 建立统一准则状态源 + 给底稿层补切换能力（复用附注层已验证的转换模式）。

## 需求

### 需求 1：建立结构化统一准则状态源

**用户故事**：作为项目负责人，我希望项目的"适用准则"有一个唯一的结构化真理源，以便各模块（底稿/附注/报表）读同一个源，切换时全局一致。

**验收标准**：
1. THE system SHALL 在 `projects` 表新增结构化字段 `applicable_standard_v2`（JSONB），包含 `{entity_type: "soe"|"listed"|"private", scope: "standalone"|"consolidated", stage: "normal"|"ipo"|"transfer"|"restructure"|"fraud_response"}`
2. WHEN 项目创建/向导完成时，THE system SHALL 从 `wizard_state.template_type` 派生并写入 `applicable_standard_v2`
3. WHEN 任何模块需要读取准则状态，THE system SHALL 从 `applicable_standard_v2` 读取（而非各自的散落字段）
4. WHERE 旧字段（template_type / current_standard / scenario / applicable_standard）仍存在，THE system SHALL 保持向后兼容（迁移期双写，新字段为权威）
5. WHEN `applicable_standard_v2` 变更，THE system SHALL 发出 `STANDARD_CHANGED` 事件通知各模块

### 需求 2：底稿层准则切换能力

**用户故事**：作为项目负责人，我希望项目中途从国企变上市时，已编制的底稿能切换准则并保留用户已填数据，而非重新生成丢数据。

**验收标准**：
1. WHEN 项目准则从 SOE 切换到 Listed（或反向），THE system SHALL 对已编制底稿执行切换：共有底稿保留用户数据 / SOE 独有底稿归档 / Listed 独有底稿创建
2. WHEN 底稿切换执行，THE system SHALL 保留共有底稿的 `parsed_data`（用户已填内容）不丢失
3. WHEN 底稿切换执行，THE system SHALL 记录切换历史（`template_lineage.conversion_reason`），支持审计追溯
4. IF 某底稿在切换时存在未保存编辑，THEN THE system SHALL 拒绝切换并提示"请先保存所有底稿"
5. WHEN 底稿切换完成，THE system SHALL 更新 `workpaper_sheet_classification` 中受影响底稿的分类（如有变化）

### 需求 3：附注层准则切换对齐（已有能力的接入）

**用户故事**：作为系统维护者，我希望附注层已有的 note_conversion_service V2 切换能力接入统一准则源，以便准则切换时附注自动跟随。

**验收标准**：
1. WHEN `STANDARD_CHANGED` 事件触发，THE system SHALL 自动调用 `note_conversion_service` 执行附注切换
2. WHEN 附注切换执行，THE system SHALL 复用已有的 section_id 保留 + 共有章节不丢编辑 + soe_only 归档 / listed_only 创建逻辑
3. WHEN 附注切换完成，THE system SHALL 更新 `current_standard` 字段与 `applicable_standard_v2` 一致

### 需求 4：报表层准则切换对齐

**验收标准**：
1. WHEN `STANDARD_CHANGED` 事件触发，THE system SHALL 更新报表的 `applicable_standard` 字段
2. WHEN 报表准则变更，THE system SHALL 标记现有报表为 stale（需重新生成）

### 需求 5：切换预览与影响范围

**用户故事**：作为项目负责人，我希望切换准则前能预览"将影响哪些底稿/附注/报表"，以便做出知情决策。

**验收标准**：
1. WHEN 用户发起准则切换前，THE system SHALL 返回影响预览：将归档的底稿/附注列表 + 将新建的列表 + 将标记 stale 的报表
2. WHEN 用户确认切换，THE system SHALL 按预览执行
3. IF 用户取消，THEN THE system SHALL 不做任何变更

### 需求 6：迁移兼容

**验收标准**：
1. THE system SHALL 提供一次性迁移脚本，从现有 4 套散落字段推断并填充 `applicable_standard_v2`
2. WHEN 迁移完成，THE system SHALL 使所有现有项目的 `applicable_standard_v2` 非空
3. WHERE 无法推断（如旧项目缺 wizard_state），THE system SHALL 默认填充 `{entity_type: "soe", scope: "standalone", stage: "normal"}`

## 范围边界

- 不改 note_conversion_service 内部逻辑（已成熟，只接入事件）
- 不改模板文件本身（准则差异体现在底稿清单/分类，非模板内容）
- 不做 UI 准则切换向导（本 spec 只做后端能力，前端 UI 是后续 spec）
- 不处理"合并↔单体"切换（只处理 SOE↔Listed，合并切换是更复杂的独立问题）
