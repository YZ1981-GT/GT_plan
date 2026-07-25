# Requirements Document

## Introduction

本 spec 承接 D7 合同负债底稿复盘改进（P0–P2 已完成 eventBus 迁移、后端 project_context 补齐、D7-7 抽凭引擎、D7-4 序时账导入、D7-5 处置结论 UI、D7↔D4 收入勾稽、D7-1 TB 预填、导入导出处置结论列）之后，**刻意延期**的两大跨文件/需设计决策增强项：

- **增强点 A（动态账龄全链路，最高优先级）**：D7 当前账龄硬编码 4 段（1年以内 / 1-2年 / 2-3年 / 3年以上），未接入项目级账龄配置 `useAgingConfig`（THREE_YEAR / FIVE_YEAR / CUSTOM）。需要将 D7-2 明细表账龄列、D7-1 审定表按账龄分类区块、跨 sheet 聚合 `useD7CrossSheet.agingAggregation`、D7-5 长期挂账"超过1年"识别、以及后端 `_d7_import_export.py` 导入导出账龄列头，全部改为按项目账龄 segment 动态生成，参考 D3 已落地的动态账龄实现。
- **增强点 B（调整分录按性质/账龄路由）**：D7-3 调整分录当前把所有 AJE/RJE 累加到 D7-1 审定表"其他(other)"行，且 `useD7Adjudication.onAdjustmentCreated` 存在与 F1 同款"每次编辑重复累加"隐患。需要为 D7-3 调整分录行增加性质（natureType）和账龄段（agingBand）维度，把调整金额按性质/账龄路由到 D7-1 审定表对应行，并消除事件累加器改用纯 computed 消费 `crossSheet.adjustmentTotals`，避免同一笔调整在性质区块与账龄区块双重计数。

### 关键设计决策（基于对现有代码的核查，作为需求约束）

以下决策来源于对 `useD7Detail.ts` / `useD7Adjudication.ts` / `useD7CrossSheet.ts` / `useAgingConfig.ts` / `useAgingMigration.ts` / `_aging_export_headers.py` / `_d7_import_export.py` 的实证核查，用于回答用户提出的重点澄清项：

1. **合同负债账龄为 2-period（不含"期末未审"列）**：D7-2 明细表当前仅有"期初审定账龄"（`priorAging1~4`）与"期末审定账龄"（`endAging1~4`）两组账龄列，无"期末未审账龄"列。故 D7 归入 **2-period subject**（与 D3 一致），不进入 `THREE_PERIOD_SUBJECTS`（D2/K1/K3/G5/F1）。`segmentsToBands` 与 `createEmptyAgingData` 对 D7 不生成 `agingCurrent`/`currentField`。
2. **向后兼容迁移策略**：历史数据中账龄以固定 4 段扁平字段（`priorAging1~4` / `endAging1~4`）存储。迁移时映射到 nested keyed 结构（`agingPrior`/`agingAudited`，按 segment key 索引，复用 `migrateD3F1Keys` / `remapRowAgingData` 范式）：新旧配置都存在的段保留原值，新增段零初始化，旧段在配置变更时丢弃（用户已被警告），历史 `endAging1~4` 值不得在迁移过程中静默丢失。
3. **性质/账龄双维度避免重复计数**：D7-1 审定表的"按性质分类"区块与"按账龄分类"区块是同一笔合同负债总额的两个视图（交叉验证约束：性质合计 === 账龄合计）。调整分录路由时，同一笔调整同时贡献到其性质行与账龄段行，但**性质区块合计与账龄区块合计各自独立成立、不相加**；总额只在各区块内闭合一次，跨区块通过交叉验证守卫恒等，绝不将两区块相加。纯 computed 从 `crossSheet.adjustmentTotals`（按性质分组 + 按账龄分组）派生，替代 `onAdjustmentCreated` 事件累加器。
4. **只读模式与导入导出往返均需覆盖**：动态账龄列在只读模式下正确渲染（不可编辑但显示历史段），导入导出往返（导出→修改→导入）保持账龄数据与列头一致，按 label 匹配、未匹配账龄列报 warning 并跳过。

## Glossary

- **D7_Detail_Composable**: 前端 `useD7Detail.ts`，管理 D7-2 明细表 27 列逻辑与账龄字段。
- **D7_Adjudication_Composable**: 前端 `useD7Adjudication.ts`，管理 D7-1 审定表双区块（按性质 + 按账龄）。
- **D7_CrossSheet_Composable**: 前端 `useD7CrossSheet.ts`，提供 D7-2→D7-1 的按性质聚合 `natureAggregation`、按账龄聚合 `agingAggregation`、调整合计 `adjustmentTotals`。
- **D7_Adjustment_Composable**: 前端 `useD7Adjustment.ts`，管理 D7-3 调整分录行。
- **D7_LongTerm_Composable**: 前端 `useD7LongTerm.ts`，管理 D7-5 账龄1年以上检查。
- **D7_ColumnPrefs_Composable**: 前端 `useD7DetailColumnPrefs.ts`，管理 D7-2 明细表列显隐偏好。
- **D7_ImportExport_Backend**: 后端 `_d7_import_export.py`，D7 导入导出端点。
- **Aging_Config**: 项目级账龄配置服务，前端 `useAgingConfig.ts`（segments/bands/preset），后端 `AgingConfigService`。
- **Aging_Segment**: 单个账龄段，含 `key`/`label`/`dayFrom`/`dayTo`。
- **Aging_Band**: 由 segment 派生的列定义，含 `key`/`label`/`priorField`/`currentField`/`auditedField`。
- **Aging_Migration**: 前端 `useAgingMigration.ts` 提供的旧数据迁移工具（`migrateD3F1Keys`/`remapRowAgingData`/`remapAgingData`）。
- **Nature_Type**: 款项性质，枚举为 预收货款 / 开发项目预收款 / 预收工程款 / 其他。
- **Aging_Band_Selection**: D7-3 调整分录行选定的账龄段 key（对应当前项目 segment）。
- **Adjustment_Totals**: `D7_CrossSheet_Composable` 派生的调整合计，按性质分组与按账龄分组。
- **Nature_Block**: D7-1 审定表"按性质分类"区块。
- **Aging_Block**: D7-1 审定表"按账龄分类"区块。
- **Over_One_Year_Threshold**: 账龄超过 1 年判定阈值，`dayFrom >= 366`。
- **Read_Only_Mode**: 底稿只读渲染模式（`isReadonly`）。
- **Config_Changed_Event**: 浏览器 window 事件 `aging-config:changed`，账龄配置保存后广播。

## Requirements

### Requirement 1: D7 纳入项目级账龄配置（2-period subject）

**User Story:** 作为审计助理，我希望 D7 合同负债账龄段跟随项目账龄配置，以便 D7 与 D2/D3 等往来款底稿使用一致的账龄口径。

#### Acceptance Criteria

1. THE D7_Detail_Composable SHALL 通过 Aging_Config 以 subject 标识 "D7" 获取当前项目的 Aging_Segment 列表。
2. THE Aging_Config SHALL 将 subject "D7" 判定为 2-period subject，不为其生成 agingCurrent 字段或 currentField。
3. WHERE 项目账龄配置为 THREE_YEAR、FIVE_YEAR 或 CUSTOM，THE D7_Detail_Composable SHALL 按该配置的 Aging_Segment 列表渲染账龄列。
4. IF Aging_Config 加载失败，THEN THE D7_Detail_Composable SHALL 始终回退到 THREE_YEAR 默认账龄段并继续渲染（不保留上次成功加载的配置）。

### Requirement 2: D7-2 明细表动态账龄列

**User Story:** 作为审计助理，我希望 D7-2 明细表的账龄列按项目账龄段动态生成，以便五年制或自定义账龄项目不再只显示固定 4 段。

#### Acceptance Criteria

1. THE D7_Detail_Composable SHALL 为期初审定账龄与期末审定账龄各按 Aging_Segment 列表生成对应列。
2. WHEN 用户在某账龄段列录入数值，THE D7_Detail_Composable SHALL 将该数值以 nested keyed 结构（按 Aging_Segment 的 key）存入行数据。
3. THE D7_Detail_Composable SHALL 使账龄各段合计等于该期审定数（期初审定账龄各段之和等于期初审定数，期末审定账龄各段之和等于期末审定数）时通过交叉验证。
4. WHERE D7-2 处于 Read_Only_Mode，THE D7_Detail_Composable SHALL 渲染账龄段列为只读展示。
5. THE D7_ColumnPrefs_Composable SHALL 按当前 Aging_Segment 列表动态提供账龄列的显隐控制项。

### Requirement 3: D7-1 审定表按账龄分类区块动态化

**User Story:** 作为现场经理，我希望 D7-1 审定表"按账龄分类"区块按项目账龄段动态生成行，以便审定表账龄区块与明细表账龄口径一致。

#### Acceptance Criteria

1. THE D7_Adjudication_Composable SHALL 按当前 Aging_Segment 列表动态生成 Aging_Block 的明细行。
2. THE D7_Adjudication_Composable SHALL 使 Aging_Block 的"合计"行等于各账龄段明细行之和。
3. THE D7_Adjudication_Composable SHALL 保留 Aging_Block 的"试算平衡表数"行与"差异数"行，且差异数等于账龄合计减去试算平衡表数。
4. WHEN Aging_Block 合计与 Nature_Block 合同负债合计不一致，THE D7_Adjudication_Composable SHALL 输出交叉验证告警并给出差额。
5. WHERE 存在旧账龄区块存储数据（固定 4 段 rowKey），THE D7_Adjudication_Composable SHALL 将其映射到当前 Aging_Segment 对应行，保留可匹配段的历史值。

### Requirement 4: 跨 sheet 账龄聚合动态化

**User Story:** 作为审计助理，我希望 D7-2→D7-1 的账龄聚合按项目账龄段进行，以便审定表账龄区块金额来源于明细表实际使用的段。

#### Acceptance Criteria

1. THE D7_CrossSheet_Composable SHALL 提供按 Aging_Segment key 索引的账龄聚合结果（期初与期末各段合计）。
2. THE D7_CrossSheet_Composable SHALL 从 D7-2 明细行的 nested keyed 账龄字段按当前 Aging_Segment 列表聚合。
3. WHERE 明细行含未在当前配置中的旧账龄段 key，THE D7_CrossSheet_Composable SHALL 在聚合时忽略该旧段。
4. THE D7_CrossSheet_Composable SHALL 暴露当前有效 Aging_Segment 列表供 D7_Adjudication_Composable 与 D7_LongTerm_Composable 消费。

### Requirement 5: D7-5 长期挂账"超过1年"按 segment 动态判定

**User Story:** 作为审计助理，我希望 D7-5 长期挂账的"超过1年"识别按账龄段 `dayFrom>=366` 判定，以便五年制或自定义账龄项目正确筛出长期未结转客户。

#### Acceptance Criteria

1. THE D7_LongTerm_Composable SHALL 依据 Over_One_Year_Threshold（Aging_Segment 的 `dayFrom >= 366`）判定账龄段是否属于"超过1年"。
2. WHEN 用户从 D7-2 导入超过1年客户，THE D7_LongTerm_Composable SHALL 仅在此 D7-2 导入场景下筛选期末审定账龄中属于"超过1年"段之和大于 0 的明细行。
3. THE D7_LongTerm_Composable SHALL 依据明细行占比最大的"超过1年"段的 label 填充导入行的账龄字段。
4. THE D7_LongTerm_Composable SHALL 不硬编码固定 4 段账龄阈值。

### Requirement 6: 后端导入导出动态账龄列头

**User Story:** 作为审计助理，我希望 D7-2 导入导出的账龄列头与前端账龄段一致，以便导出的模板可被自身导入且不丢账龄数据。

#### Acceptance Criteria

1. THE D7_ImportExport_Backend SHALL 通过项目 Aging_Config（subject "D7"）获取有效 Aging_Segment 列表生成 D7-2 账龄列头。
2. IF 项目 Aging_Config 无效，THEN THE D7_ImportExport_Backend SHALL 跳过 D7-2 账龄列头生成直至配置有效。
3. THE D7_ImportExport_Backend SHALL 为期初审定账龄与期末审定账龄各按 Aging_Segment 列表生成 2×N 个动态账龄列头。
4. WHEN 导出 D7-2 数据被触发，THE D7_ImportExport_Backend SHALL 从行数据的 nested keyed 账龄字段按段取值填入对应列（仅在导出触发时提取，不作为常驻不变量）。
5. WHEN 导入 D7-2 数据，THE D7_ImportExport_Backend SHALL 按账龄列头 label 匹配写入对应段，未匹配到当前段的账龄列头 SHALL 报 warning 并跳过。
6. IF 导入文件缺少当前配置中的某账龄列头，THEN THE D7_ImportExport_Backend SHALL 将该段初始化为 0。
7. THE D7_ImportExport_Backend SHALL 使导出的 D7-2 模板经原样导入后账龄数据与导出前保持一致（导入导出往返一致）。

### Requirement 7: 账龄配置变更刷新

**User Story:** 作为现场经理，我希望修改项目账龄配置后 D7 各账龄区域自动刷新，以便无需手动重载即可看到新账龄段。

#### Acceptance Criteria

1. WHEN Config_Changed_Event 触发，THE D7_Detail_Composable SHALL 刷新账龄段列并按新 Aging_Segment 列表重映射行账龄数据。
2. WHEN Config_Changed_Event 触发，THE D7_Adjudication_Composable SHALL 刷新 Aging_Block 行。
3. WHEN 账龄配置变更导致段增减，THE Aging_Migration SHALL 保留新旧配置共有段的值、将新增段初始化为 0、丢弃旧配置独有段。
4. WHEN D7 组件卸载，THE D7_Detail_Composable SHALL 移除 Config_Changed_Event 监听器。

### Requirement 8: 历史账龄数据向后兼容迁移

**User Story:** 作为审计助理，我希望已有 D7 底稿的历史账龄数据在升级后不丢失，以便继续审计已开始的项目。

#### Acceptance Criteria

1. WHERE D7-2 行数据为旧固定 4 段扁平字段（`priorAging1~4` / `endAging1~4`），THE D7_Detail_Composable SHALL 将其迁移为 nested keyed 结构且保留原值。
2. THE Aging_Migration SHALL 将旧 `priorAging1~4` 映射到 agingPrior 的前 4 个默认段 key，将旧 `endAging1~4` 映射到 agingAudited 的前 4 个默认段 key。
3. THE D7_Detail_Composable SHALL 在迁移后仅以 nested keyed 格式序列化存储，不再输出旧扁平字段 key。
4. IF 历史数据同时存在扁平字段与 nested 字段，THEN THE Aging_Migration SHALL 始终以 nested 字段为准，忽略扁平字段的值。

### Requirement 9: D7-3 调整分录增加性质与账龄段维度

**User Story:** 作为审计助理，我希望在 D7-3 调整分录行标注款项性质与账龄段，以便调整金额能路由到审定表对应行而非统一进"其他"。

#### Acceptance Criteria

1. THE D7_Adjustment_Composable SHALL 为每条调整分录行提供款项性质（Nature_Type）字段。
2. THE D7_Adjustment_Composable SHALL 为每条调整分录行提供账龄段（Aging_Band_Selection）字段，其可选值来自当前 Aging_Segment 列表。
3. WHERE 调整分录行未指定 Nature_Type，THE D7_Adjustment_Composable SHALL 将该行性质默认为"其他"。
4. THE D7_Adjustment_Composable SHALL 持久化调整分录行的 Nature_Type 与 Aging_Band_Selection 字段。
5. WHERE D7-3 处于 Read_Only_Mode，THE D7_Adjustment_Composable SHALL 以只读方式展示 Nature_Type 与 Aging_Band_Selection。

### Requirement 10: 调整金额按性质/账龄路由到审定表

**User Story:** 作为现场经理，我希望调整分录金额按性质和账龄路由到 D7-1 审定表对应行，以便审定数准确反映调整对各分类的影响。

#### Acceptance Criteria

1. THE D7_CrossSheet_Composable SHALL 提供按 Nature_Type 分组的 Adjustment_Totals（各性质行的 AJE 合计与 RJE 合计）。
2. THE D7_CrossSheet_Composable SHALL 提供按 Aging_Band_Selection 分组的 Adjustment_Totals（各账龄段的 AJE 合计与 RJE 合计）。
3. THE D7_Adjudication_Composable SHALL 将 Nature_Block 各行的调整数从按性质分组的 Adjustment_Totals 派生。
4. THE D7_Adjudication_Composable SHALL 将 Aging_Block 各行的调整数从按账龄分组的 Adjustment_Totals 派生。
5. THE D7_Adjudication_Composable SHALL 使 Nature_Block 调整合计与 Aging_Block 调整合计相等（同一批调整的两个视图恒等）。
6. THE D7_Adjudication_Composable SHALL 不将 Nature_Block 合计与 Aging_Block 合计相加计入合同负债总额。

### Requirement 11: 以纯 computed 替代事件累加器

**User Story:** 作为开发者，我希望移除 `onAdjustmentCreated` 事件累加器改用纯 computed，以便消除"每次编辑重复累加"的隐患。

#### Acceptance Criteria

1. THE D7_Adjudication_Composable SHALL 移除 `onAdjustmentCreated` 中将调整金额累加到"其他"行的逻辑。
2. THE D7_Adjudication_Composable SHALL 以纯 computed 从 Adjustment_Totals 派生各行调整数，不写入 checklist 存储。
3. WHEN 用户多次编辑同一条调整分录，THE D7_Adjudication_Composable SHALL 使审定表调整数反映当前分录集合的合计，且不随编辑次数累加放大。
4. WHEN 用户删除某条调整分录，THE D7_Adjudication_Composable SHALL 使审定表对应行调整数相应减少。

### Requirement 12: 导入导出与只读模式回归保障

**User Story:** 作为审计助理，我希望动态账龄与调整路由在只读模式和导入导出往返下均正确工作，以便复核与数据交换不出错。

#### Acceptance Criteria

1. WHERE D7 全部 sheet 处于 Read_Only_Mode，THE D7_Detail_Composable、D7_Adjudication_Composable 与 D7_Adjustment_Composable SHALL 正确渲染动态账龄列与性质/账龄字段且不可编辑。
2. WHEN 导出后再导入 D7-2 数据，THE D7_ImportExport_Backend SHALL 使账龄各段数据保持一致。
3. WHEN 导入含 Nature_Type 与 Aging_Band_Selection 的 D7-3 调整分录数据，THE D7_ImportExport_Backend SHALL 保留这两个字段。
4. WHERE 导入的 D7-3 数据缺少 Nature_Type 或 Aging_Band_Selection，THE D7_ImportExport_Backend SHALL 分别默认为"其他"与空段。
