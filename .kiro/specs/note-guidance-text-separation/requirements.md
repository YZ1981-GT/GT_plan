# Requirements Document

## Introduction

GT 审计平台附注模块（`disclosure_notes` 表）的富文本字段 `text_content` 当前混装两类性质完全不同的内容，系统无法区分：

1. **提示性/指引文字**：如 `（注：应披露公允价值确认依据。）`、`【提示：参考附注八、5】`、`（说明固定资产的确认条件、分类、计价方法...）`、`（企业应评价自报告...）` —— 给填表人看的填写指引，不应进入最终交付件。
2. **实质性正文**：会计政策段落、用户实际撰写的披露说明 —— 必须进入交付件。

全库 906 个非空 `text_content` 章节统计显示：62%（566 个）含实质正文，28%（258 个）为纯提示/提示+标题、无实质正文，9%（82 个）为纯表格标题行。即约 37%（340 个）章节按现状导出会污染交付件（导出纯提示语或表格标题）。

经真实数据核实，纯规则识别（按 `（注/提示/【】）` 前缀判别）不可靠：大量指引是 `（说明...）`、`（企业应...）` 这类括号包裹的祈使句，无固定前缀，自动识别会误判。因此本特性在数据层显式分流，分流时机以人确认为准，不依赖纯自动猜测。

导出链路存在两处缺陷（`backend/app/services/note_word_exporter.py`）：
- `should_skip_empty_section`（`note_word_dynamic_styles.py`）只要 `text_content` 非空即判定"有内容、不跳过"，导致仅提示语+空表的章节被误保留导出。
- 正文渲染将 `text_content` 整段原样塞进 Word（programmatic 路径与 template 占位符替换两条链路），提示语原封不动进入交付件。

### 选定方案（方案 A，用户已拍板）

新增字段 `guidance_text`，将提示性/指引文字从 `text_content` 移出单独存储：

- `text_content` 从此只存实质正文，导出判空与导出渲染天然干净。
- `guidance_text` 在前端编辑器以灰色/可折叠提示条形式显示，引导填写但不可导出。
- 生成附注时（`disclosure_engine.py`）把模板提示语写入 `guidance_text`、实质正文写 `text_content`、表格标题写进表格名（不灌正文）。
- 存量数据需一次性拆分迁移，把已有 `text_content` 中的提示语抽到 `guidance_text`。

### 交付件溯源联动约束

交付件溯源 `deliverable_writeback_service` 与快照哈希 `compute_snapshot_hash_from_parts` 当前基于 `text_content` 计算。提示语移出 `text_content` 后溯源哈希更准确（提示语变动不再误触 stale），但迁移导致存量 `text_content` 内容变化会改变存量快照哈希，需评估对 stale 标记的影响，确保迁移不误触发大规模 stale。

### 项目铁律约束（贯穿本特性）

- DB 迁移走 MigrationRunner 运行时迁移，`backend/migrations/V*.sql` 与 `R*.sql` 配对，`CREATE`/`ALTER` 必带 `IF NOT EXISTS`，当前最高 V072，本特性用 V073。
- 三层一致：DB 迁移 + ORM `Mapped[]` + service 方法，缺一即伪绿。
- 存量数据操作必须备份可回滚 + 预览人工核对，禁止纯自动规则批量改（曾因纯自动规则误清空过数据）。
- 改后必 Playwright 实测，测试项目用辽宁卫生 `37814426-a29e-4fc2-9313-a59d229bf7b0`、和平药房 `5942c12e-65fb-4187-ace3-79d45a90cb53`。
- UI 全中文化 + GT 紫令牌（核心紫 `#4b2d77`）。
- 前端唯一路径 `audit-platform/frontend/`。

## Glossary

- **Disclosure_Note**：附注章节记录，对应 `disclosure_notes` 表 / `DisclosureNote` ORM。
- **Text_Content**：附注实质正文字段 `text_content`，迁移后仅存实质性披露正文。
- **Guidance_Text**：本特性新增的指引文字字段 `guidance_text`，存储提示性/指引文字，不参与导出。
- **Disclosure_Engine**：附注生成服务 `disclosure_engine.py`，从模板生成附注章节。
- **Note_Word_Exporter**：附注 Word 导出服务 `note_word_exporter.py`，含 programmatic、template 与 html 三条导出路径。
- **Skip_Empty_Checker**：导出判空函数 `should_skip_empty_section`（`note_word_dynamic_styles.py`）。
- **Note_Editor**：前端附注编辑器 `DisclosureEditor`（`audit-platform/frontend/`）。
- **Migration_Script**：将 `text_content` 中提示语拆分到 `guidance_text` 的存量数据迁移脚本（DDL 用 V073/R073 配对，数据拆分用带预览的一次性脚本）。
- **Backup_Table**：存量迁移前的备份表（参考已有 `_note_text_ch8_backup` 表做法），支持回滚。
- **Snapshot_Hash**：交付件章节快照哈希 `compute_snapshot_hash_from_parts`，当前基于 `text_content` 计算。
- **Stale_Mark**：交付件章节的过期标记 `is_stale`，用于提示重新导出。

## Requirements

### Requirement 1: guidance_text 数据模型（三层一致）

**User Story:** 作为后端开发者，我想为附注新增独立的指引文字字段并保持数据库、ORM 与服务三层一致，以便系统能在数据层区分指引文字与实质正文。

#### Acceptance Criteria

1. THE Migration_Script SHALL 通过配对的 V073 与 R073 脚本为 `disclosure_notes` 表新增 `guidance_text` 列（PostgreSQL `TEXT` 类型，无长度上限，可空），与现有 `text_content`（ORM `Mapped[str | None]` + `Text`）同形态——确保可容纳数百字的长指引（如「八、27」数据资源指引）。
2. THE Migration_Script 的 `ALTER TABLE ... ADD COLUMN` 语句 SHALL 使用 `IF NOT EXISTS` 保证幂等。
3. THE DisclosureNote ORM 模型 SHALL 包含与 `guidance_text` 列对应的 `Mapped[str | None]` 定义。
4. THE Disclosure_Engine 与附注 service SHALL 提供读写 `guidance_text` 字段的方法。
5. WHERE `guidance_text` 为 NULL 或空字符串，THE Disclosure_Note SHALL 表现为无指引文字（与现状行为一致）。
6. WHEN 数据库迁移、ORM 模型与 service 方法三层任一缺失对 `guidance_text` 的定义，THE 校验 SHALL 判定为不通过（伪绿）。

### Requirement 2: 生成逻辑三类内容分流

**User Story:** 作为附注填表用户，我想在系统生成附注时自动把提示语、实质正文与表格标题分流到正确位置，以便生成的章节正文不混入指引文字。

#### Acceptance Criteria

1. WHEN Disclosure_Engine 生成附注章节，THE Disclosure_Engine SHALL 将模板中的提示性/指引文字写入 `guidance_text`。
2. WHEN Disclosure_Engine 生成附注章节，THE Disclosure_Engine SHALL 将实质性正文写入 `text_content`。
3. WHEN Disclosure_Engine 生成附注章节且模板内容为表格标题，THE Disclosure_Engine SHALL 将表格标题写入表格名，且 SHALL NOT 将表格标题写入 `text_content`。
4. WHERE 章节无实质正文来源（无上年附注、无 LLM 生成结果），THE Disclosure_Engine SHALL 将 `text_content` 留空，且仅在 `guidance_text` 中保留指引文字。（注：`disclosure_engine.py` 优先级3「模板默认文字」灌正文的逻辑此前已临时注释掉留空，本特性实施时应将其正式改为"提示语→guidance_text"分流，替换该临时注释，避免重复或冲突。）
5. WHEN Disclosure_Engine 完成章节生成，THE Disclosure_Engine SHALL 使 `text_content` 不包含已分流至 `guidance_text` 的指引文字。

### Requirement 3: 前端编辑器指引提示条展示

**User Story:** 作为附注填表用户，我想在编辑器中以只读提示条看到指引文字、在正文区编辑实质内容，以便我能按指引填写而不会把指引误当正文导出。

#### Acceptance Criteria

1. WHERE 章节存在非空 `guidance_text`，THE Note_Editor SHALL 以灰色提示条形式展示 `guidance_text`。
2. THE Note_Editor SHALL 将 `guidance_text` 提示条渲染为只读，且 SHALL 仅允许用户编辑 `text_content` 正文区。
3. THE Note_Editor 展示的 `guidance_text` 提示条 SHALL 不参与导出。
4. WHERE 章节 `guidance_text` 为空，THE Note_Editor SHALL 不渲染提示条，正文编辑区行为与现状一致。
5. THE Note_Editor 的提示条 SHALL 使用 GT 紫令牌配色，且界面文本 SHALL 为中文。

### Requirement 4: 导出判空与渲染修正

**User Story:** 作为审计报告交付用户，我想导出的附注 Word 只包含实质正文与表格、不含指引文字，以便交付件干净专业。

#### Acceptance Criteria

1. WHEN Skip_Empty_Checker 判定章节是否跳过，THE Skip_Empty_Checker SHALL 仅依据 `text_content` 与表格数据判空，且 SHALL NOT 因 `guidance_text` 非空而判定章节有内容。
2. IF 章节 `text_content` 为空且所有表格为空，THEN THE Skip_Empty_Checker SHALL 判定该章节应跳过，即使 `guidance_text` 非空。
3. WHEN Note_Word_Exporter 渲染章节正文，THE Note_Word_Exporter SHALL 仅导出 `text_content`，且 SHALL NOT 导出 `guidance_text`。
4. THE Note_Word_Exporter 的 programmatic、template 与 html 三条导出路径 SHALL 均不导出 `guidance_text`。
5. WHEN 一个仅含提示语、无实质正文、表格为空的章节被导出，THE Note_Word_Exporter SHALL 跳过该章节（不产生空内容章节）。

### Requirement 5: 存量数据拆分迁移（预览-核对-执行）

**User Story:** 作为平台运维人员，我想在拆分存量 text_content 前先预览拆分清单并人工核对、保留可回滚备份，以便避免纯自动规则误判误清空数据。

#### Acceptance Criteria

1. WHEN Migration_Script 在执行前运行预览模式，THE Migration_Script SHALL 打印每个待拆分章节的拆分清单，列出"将抽取为 guidance_text 的内容"与"将保留为 text_content 的内容"供人工核对。
2. THE Migration_Script SHALL 在执行实际拆分写入前创建 Backup_Table（参考 `_note_text_ch8_backup` 做法），完整保存源 `text_content` 以支持回滚。
3. WHERE 操作员未确认执行，THE Migration_Script SHALL 仅输出预览清单且 SHALL NOT 修改 `disclosure_notes` 表数据。
4. WHEN 操作员确认执行拆分，THE Migration_Script SHALL 将识别出的指引文字写入 `guidance_text`，并将剩余实质正文写回 `text_content`。
5. IF 章节无法被可靠识别出指引文字，THEN THE Migration_Script SHALL 保留该章节 `text_content` 不变且 `guidance_text` 留空（不拆分，留待人工处理），而非强行拆分。
6. WHEN 操作员执行回滚，THE Migration_Script SHALL 从 Backup_Table 完整恢复源 `text_content`。
7. THE Migration_Script SHALL 支持按项目范围执行（如仅辽宁卫生项目或全项目），范围由操作员显式指定。
8. FOR ALL 拆分章节，迁移后 `guidance_text` 与 `text_content` 重新合并 SHALL 等价于源 `text_content`（不丢失任何字符，往返一致性）。

### Requirement 6: 交付件溯源联动

**User Story:** 作为审计质控人员，我想评估提示语移出 text_content 对快照哈希与 stale 标记的影响，以便迁移不会误触发大规模章节 stale 提示。

#### Acceptance Criteria

1. THE Snapshot_Hash 函数 `compute_snapshot_hash_from_parts` 当前已仅基于 `section_code` + `text_content` + `table_data` + 审定金额计算（不含指引文字），其签名 SHALL 保持不变；本特性 SHALL NOT 改动该函数实现。
2. WHEN 存量迁移把指引文字从 `text_content` 移出，THE 迁移流程 SHALL 认知到这会改变传入 `compute_snapshot_hash_from_parts` 的 `text_content` 值、从而改变章节源快照哈希。
3. THE 迁移流程 SHALL 提供评估手段，识别哪些章节的源快照哈希因 `text_content` 变更而变化。
4. WHEN 存量拆分迁移完成，THE Migration_Script SHALL 同步重算受影响章节的源快照基线哈希并回写至交付件章节状态基线（`deliverable_section_state`），使迁移后首次比对结果与迁移前一致、不产生因迁移导致的哈希差异。
5. WHERE 章节 `text_content` 因迁移仅移除了指引文字而实质正文未变，THE 迁移流程 SHALL 通过上述基线回写避免将这些章节标记为 Stale_Mark。
6. WHEN 迁移完成，THE 系统 SHALL NOT 因纯指引文字移除而把未实质变更的章节全量标记 Stale_Mark。

### Requirement 7: 向后兼容

**User Story:** 作为现有附注用户，我想在 guidance_text 为空时系统行为与现状完全一致，以便迁移不影响未拆分章节与既有导出链路。

#### Acceptance Criteria

1. WHERE 章节 `guidance_text` 为空或 NULL，THE 系统在生成、编辑、导出全链路 SHALL 表现为与迁移前一致的行为。
2. THE 离线导出包、template 模板填充与 programmatic 三条导出路径 SHALL 均适配 `guidance_text` 字段（读取存在性不报错，且不导出指引文字）。
2a. WHERE 附注通过 `note_offline_export_service` 离线导出并再导回（可往返编辑链路），THE 系统 SHALL 在导出/导入往返中保留 `guidance_text`（不丢失），且 SHALL NOT 将 `guidance_text` 内容当作正文导回污染 `text_content`。
3. WHEN 既有章节尚未执行存量拆分迁移，THE 系统 SHALL 正常生成、编辑与导出该章节（不因缺少 `guidance_text` 数据而报错）。
4. THE 附注列表、目录树与按 `sort_order` 排序逻辑 SHALL 不因新增 `guidance_text` 字段而改变。

### Requirement 8: 测试覆盖

**User Story:** 作为质控人员，我想本特性的数据模型、生成分流、导出修正与存量迁移都有测试覆盖，以便防止回归与伪绿。

#### Acceptance Criteria

1. THE 系统 SHALL 包含验证三层一致的测试，覆盖 `guidance_text` 在迁移、ORM 与 service 三层的定义一致性。
2. THE 系统 SHALL 包含验证导出判空的测试，覆盖"仅含 guidance_text 的空正文章节被跳过"与"含 text_content 正文章节不被跳过"。
3. THE 系统 SHALL 包含验证导出渲染的测试，覆盖三条导出路径均不输出 `guidance_text`。
4. THE 系统 SHALL 包含验证存量拆分往返一致性的测试，即 `guidance_text` 与拆分后 `text_content` 重新合并等价于源 `text_content`。
5. THE 系统 SHALL 包含验证迁移幂等与回滚的测试，重复执行预览不修改数据、回滚后从 Backup_Table 完整恢复源 `text_content`。
5a. THE 系统 SHALL 包含验证「迁移后源快照基线哈希重算回写」的测试，覆盖"仅移除指引文字的章节迁移后比对不产生 stale"。
5b. THE 系统 SHALL 包含验证离线导出/导入往返保留 `guidance_text` 且不污染 `text_content` 的测试。
6. WHERE 编写 Property-Based Test，THE 系统 SHALL 将 `max_examples` 设置为 5。
7. WHEN 全链路改动完成，THE 系统 SHALL 通过 Playwright 在辽宁卫生与和平药房项目实测附注编辑器提示条展示与导出不含指引文字。

## 待澄清问题（Open Questions）

1. **存量指引识别方式**：纯前缀规则不可靠，预览阶段用于识别指引文字的判别逻辑（启发式规则集 / 人工标注 / LLM 辅助）尚未确定，需在设计阶段权衡。当前需求约束为"无法可靠识别即不拆分、留待人工处理"。
2. **字段存储形态**：`guidance_text` 采用独立列还是 `metadata` JSON 子字段，需在设计阶段权衡（独立列利于查询与三层校验，JSON 子字段免迁移列）。本需求按独立列描述，设计阶段可调整。
3. **stale 抑制具体实现**：避免大规模 stale 的策略已在 R6.4 定为"迁移后重算并回写源快照基线哈希"；其具体实现细节（复用哪个 service 方法重算、批量回写的事务边界、是否需临时抑制传播）需在设计阶段定。
