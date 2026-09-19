# 需求文档：附注语义结构与前端呈现优化

## Introduction

本 spec 聚焦附注模块下一轮专项优化：会计政策长文本呈现、报表科目主要注释、关联方交易章节、国企/上市与合并/单体版本差异、附注表格语义、公式治理、底稿披露表联动、离线模板友好性。它建立在既有 `disclosure-note-linkage-and-slimdown` 之上，不重复解决假性刷新、auto_pull 和 DisclosureEditor 瘦身问题。

最高约束：`DisclosureNote.table_data` 仍为唯一真源；新增结构必须通过 sidecar 兼容扩展，不破坏 `_cell_modes`、`_cell_meta`、`_formulas`、`_tables` 既有契约。

## Requirements

### Requirement 1：会计政策条款化审阅模式

**User Story:** 作为审计经理，我希望会计政策章节按条款呈现，并能快速查看与模板、上年的差异，以便我只复核本年有变化的内容。

#### Acceptance Criteria

1. THE system SHALL 将会计政策长文本拆分为条款级结构，包含 `clause_id`、标题、层级、本年内容、模板内容、上年内容、变量列表、确认状态。
2. WHEN 条款内容与上年或模板一致，THE system SHALL 标记为 unchanged，并支持批量确认。
3. WHEN 条款内容存在差异，THE system SHALL 展示差异摘要，并支持只看有差异条款。
4. WHEN 条款包含项目变量，THE system SHALL 高亮变量并显示变量来源。
5. THE system SHALL 禁止 AI 草稿直接覆盖 confirmed 条款，必须人工确认。

### Requirement 2：数据披露四维上下文

**User Story:** 作为审计助理，我希望在科目注释和关联方章节中按单位、年度、科目明细、金额口径快速切换，以便快速核对披露数据。

#### Acceptance Criteria

1. THE system SHALL 在数据披露模式展示四维上下文栏：单位、年度、科目及明细、金额口径。
2. WHEN 用户切换单位或年度，THE system SHALL 刷新当前章节表格、公式结果和校验状态。
3. WHEN 用户切换科目或明细，THE system SHALL 定位到对应 table/card，而不要求用户重新展开章节树。
4. WHEN 金额口径切换，THE system SHALL 显示对应列、公式和报表一致性校验。
5. THE 四维上下文 SHALL 支持国企/上市、合并/单体不同模板差异。

### Requirement 3：表格语义结构 sidecar

**User Story:** 作为附注模板维护者，我希望表格中标题行、分组行、数据行、合计行、提示事项被系统明确区分，以便避免用户误改标题和结构。

#### Acceptance Criteria

1. THE system SHALL 支持 `table_id`，用于区分同一章节内多张表。
2. THE system SHALL 支持 `row_id`、`row_type`，枚举至少包括 `table_title`、`group_header`、`data`、`subtotal`、`total`、`note_tip`、`footnote`、`blank`、`custom`。
3. THE system SHALL 支持 `columns[].col_id`，公式和取数绑定 SHALL 优先使用 `col_id` 而非列下标。
4. WHEN 用户普通编辑数据，THE system SHALL 默认禁止修改 `table_title`、`group_header`、`total` 等结构行。
5. THE system SHALL 保持 `headers[]`、`rows[].values[]` 兼容，不破坏旧代码读取。

### Requirement 4：公式治理与单元格来源面板

**User Story:** 作为复核人，我希望点击附注金额单元格时能看到公式、来源、执行结果、错误、手工覆盖和恢复自动取数入口，以便判断数字是否可靠。

#### Acceptance Criteria

1. THE system SHALL 为公式单元格展示 `formula_id`、表达式、来源、依赖、最近执行结果、最近错误、执行时间。
2. WHEN 单元格为 manual 或 locked，THE system SHALL 展示覆盖状态和覆盖前自动值。
3. WHEN 公式执行失败，THE system SHALL 在表格、章节树和附注质量清单中显示错误状态。
4. WHEN 用户选择恢复自动取数，THE system SHALL 使用保留的公式或 binding 重新取数，不得覆盖 locked 单元格。
5. THE system SHALL 支持公式依赖图，展示 TB、WP、REPORT、NOTE、PRIOR 等来源。

### Requirement 5：底稿披露表绑定注册表

**User Story:** 作为审计平台维护者，我希望附注取数不依赖行标题文字匹配，而是使用稳定绑定注册表，以便模板升级和标题调整不破坏取数。

#### Acceptance Criteria

1. THE system SHALL 定义 `note_binding_registry`，用 `section_id/table_id/row_id/col_id` 绑定来源。
2. THE binding SHALL 支持来源：trial_balance、ledger、workpaper、report、prior_note、manual、formula、ai_draft。
3. WHEN 底稿披露表数据变化，THE system SHALL 定位受影响的章节、表格、行、列。
4. WHEN 绑定来源缺失，THE system SHALL 标记为 source_missing，不得静默写 0。
5. THE system SHALL 支持绑定来源穿透到底稿、报表、试算表或上年附注。

### Requirement 6：披露平衡校验

**User Story:** 作为项目合伙人，我希望关键科目附注与报表数自动核对，以便签发前发现附注与报表不一致。

#### Acceptance Criteria

1. THE system SHALL 支持为关键附注配置披露平衡规则。
2. WHEN 附注明细合计与报表项目金额不一致，THE system SHALL 显示差异金额和来源。
3. WHEN 差异超过容差，THE system SHALL 在章节树、质量清单、签发页显示 blocking 或 warning。
4. THE system SHALL 至少支持应收账款、固定资产、货币资金、关联方余额等关键章节试点。
5. THE 校验 SHALL 尊重 manual override，并提示复核人关注。

### Requirement 7：离线模板工作包优化

**User Story:** 作为审计助理，我希望导出的离线附注模板像可填报工作包，而不是难懂的数据 dump，以便离线填报更快捷准确。

#### Acceptance Criteria

1. THE offline workbook SHALL 包含填报说明、章节清单、政策条款、科目披露、校验结果等 sheet。
2. THE workbook SHALL 用统一颜色标识可填、锁定、来源底稿、需复核、校验失败、上年/模板参考。
3. WHEN 用户填写离线模板，THE workbook SHALL 保护锁定单元格和公式列。
4. WHEN 离线模板导入，THE system SHALL 识别手工修改、公式列修改、结构变更和冲突。
5. THE offline workbook SHALL 保留 section/table/row/col 语义 ID，便于回传合并。

### Requirement 8：模板变体矩阵

**User Story:** 作为模板管理员，我希望国企/上市、合并/单体四种版本按语义章节映射，以便维护差异而不是维护四套孤岛模板。

#### Acceptance Criteria

1. THE system SHALL 定义 `semantic_section_id`，映射 soe_standalone、soe_consolidated、listed_standalone、listed_consolidated。
2. WHEN 用户切换模板版本，THE system SHALL 展示对应章节、独有章节、缺失章节、表格结构差异。
3. THE system SHALL 支持记录同一语义章节在不同版本下的标题、编号、适用范围和表格差异。
4. WHEN 模板差异影响取数或公式，THE system SHALL 标记需复核。

### Requirement 9：关联方披露专项治理

**User Story:** 作为 EQCR 或项目合伙人，我希望关联方披露章节能单独呈现关联方主体、交易、余额、证据和报表一致性，以便识别关联方披露是否完整准确。

#### Acceptance Criteria

1. THE system SHALL 将关联方章节作为数据披露模式的专项试点，而非仅作为普通科目表格。
2. THE system SHALL 支持从关联方模块、EQCR 关联方、附件、函证、手工交易明细和报表余额取数或建立引用。
3. WHEN 关联方交易或余额与报表项目不一致，THE system SHALL 在质量清单中显示差异。
4. WHEN 关联方主体缺少关系说明、交易性质或余额说明，THE system SHALL 标记为 warning 或 blocking。

### Requirement 10：附注质量清单

**User Story:** 作为项目经理和合伙人，我希望看到附注质量清单，以便在签发前确认附注完整、准确、可导出。

#### Acceptance Criteria

1. THE system SHALL 生成附注质量清单，包含完整性、适用性、金额一致性、公式错误、stale、manual override、AI 未确认、Word 样式、交叉引用、导出可用性。
2. WHEN 存在 blocking 项，THE system SHALL 阻止签发或要求合伙人显式确认。
3. THE quality checklist SHALL 支持从问题项跳转到章节、表格、单元格或证据来源。
4. THE quality checklist SHALL 使用统一结果 schema，包含 level、category、section_id、table_id、row_id、col_id、message、route。

### Requirement 11：模板源与绑定配置校验

**User Story:** 作为平台维护者，我希望附注语义扩展能明确基于哪些模板源，并对绑定注册表进行自动校验，以便避免模板和绑定漂移。

#### Acceptance Criteria

1. THE system SHALL 明确本 spec 读取和派生的模板源清单。
2. THE system SHALL 提供 semantic sidecar 生成脚本，基于现有模板生成候选 sidecar 和 diff 报告，不直接覆盖主模板。
3. THE system SHALL 校验 binding registry 中的 section/table/row/col 是否存在于模板结构。
4. THE system SHALL 校验绑定来源 wp_code/source 枚举/重复绑定是否合法。

### Requirement 12：离线导入兼容

**User Story:** 作为项目组成员，我希望新旧离线附注模板都能被系统识别，并在结构被误改时给出清楚冲突提示，以便离线协作不中断。

#### Acceptance Criteria

1. THE system SHALL 保持旧版离线包可导入。
2. THE semantic workbook SHALL 通过隐藏 `_meta` 标识版本、模板类型和语义结构版本。
3. WHEN 用户修改隐藏语义列或锁定单元格，THE system SHALL 标记结构冲突或锁定冲突，不得静默覆盖。
4. THE system SHALL 在导入结果中区分内容修改、公式列修改、结构变更和冲突。

## 实施批次

- **P0-MVP**：政策条款审阅原型、数据披露四维上下文、`row_type`、`table_id/col_id`、单元格来源面板。
- **P0-Full**：质量清单基础、结构编辑权限边界、离线模板说明页。
- **P1**：binding registry、公式依赖图、披露平衡校验、关键科目与关联方试点。
- **P2**：模板变体矩阵、离线工作包优化、样式一致性测试、模板优化回流。

## Scope

- 不改变 `DisclosureNote.table_data` 唯一真源原则。
- 不删除现有 `DisclosureEditor`、`StructureEditor`、`FormulaManagerDialog`。
- 不重复实现 `disclosure-note-linkage-and-slimdown` 已覆盖的真实刷新与 auto_pull 修复。
- 所有新增结构必须兼容旧 `headers/rows/values/_cell_modes/_cell_meta/_formulas/_tables`。
