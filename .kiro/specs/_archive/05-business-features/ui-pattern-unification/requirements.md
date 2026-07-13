# Requirements Document

## Introduction

统一审计平台前端两个基础设施组件（抽凭引擎、版本链）的集成模式差异。早期组件使用 `<el-collapse>` 面板内嵌抽凭引擎（占页面空间），后期组件已统一为 dialog-mode（工具栏按钮 → 弹窗 → @filled 填入）。版本链方面，少数组件直接使用低层 `useVersionTrail` composable，大多数已迁移到封装更高的 `useWorkpaperVersionToolbar`（含 autoSnapshot + 工具栏按钮 + GtWpVersionTrail drawer 集成）。本需求将残留的旧模式组件全部迁移到新标准模式。

## Glossary

- **Sampling_Engine**: GtVoucherSamplingEngine 组件，支持 dialog-mode prop 与 @filled emit 的抽凭引擎
- **Dialog_Mode**: 抽凭引擎的弹窗集成模式——工具栏按钮触发 → 弹窗内完成抽凭配置与执行 → @filled 事件将样本数据返回父组件
- **Collapse_Mode**: 抽凭引擎的旧集成模式——使用 `<el-collapse>` 面板将引擎内嵌在页面内，占用垂直空间
- **Version_Toolbar**: `useWorkpaperVersionToolbar` composable，封装 useVersionTrail + autoSnapshot + 版本历史按钮 + GtWpVersionTrail drawer
- **Version_Trail_Legacy**: 直接使用底层 `useVersionTrail` composable 或自建版本逻辑的旧模式
- **Target_Components_Sampling**: D2TabVoucherCheck / F2ValuationTestSheet / F2TabPurchaseInboundCheck / F2TabMaterialUsageCheck / F5TabMajorAdjustment（需迁移抽凭模式的组件集）
- **Target_Components_Version**: GtG5LongTermReceivable / GtConfirmationAlternativeL05（需迁移版本链模式的组件集）
- **Reference_Standard_Sampling**: G5TabVoucherCheck.vue 中的 dialog-mode 集成方式
- **Reference_Standard_Version**: GtG4BondInvestmentMain.vue 等使用 useWorkpaperVersionToolbar 的集成方式
- **Platform**: 审计底稿前端平台（Vue 3 + Element Plus）

## Requirements

### Requirement 1: 抽凭引擎迁移至 Dialog Mode

**User Story:** As a 审计助理, I want 抽凭引擎以弹窗方式呈现而非占用底稿编辑空间的折叠面板, so that 底稿页面更紧凑且操作流程与其他循环一致。

#### Acceptance Criteria

1. WHEN Target_Components_Sampling 中任一组件被渲染, THE Platform SHALL 以工具栏按钮形式提供抽凭入口（不使用 el-collapse 面板）
2. WHEN 用户点击抽凭工具栏按钮, THE Sampling_Engine SHALL 以 Dialog_Mode 弹窗方式打开
3. WHEN Sampling_Engine 完成抽凭并触发 @filled 事件, THE Platform SHALL 将样本数据填入对应组件的表格行中
4. THE Platform SHALL 移除 Target_Components_Sampling 中所有 `<el-collapse>` 包裹 GtVoucherSamplingEngine 的代码结构
5. WHEN 迁移完成后, THE Platform SHALL 保持各组件原有的 accountCode / phase / defaultMethod 等业务参数不变
6. WHEN 迁移完成后, THE Platform SHALL 保持各组件原有的 @filled 回调逻辑（样本到表格行的映射规则）不变

### Requirement 2: D2TabVoucherCheck 抽凭模式迁移

**User Story:** As a 审计助理, I want D2 往来款凭证检查的抽凭操作与 G/K/H 循环一致, so that 跨循环操作体验统一。

#### Acceptance Criteria

1. WHEN D2TabVoucherCheck 组件加载完成, THE Platform SHALL 在工具栏区域显示抽凭按钮
2. THE Platform SHALL 移除 D2TabVoucherCheck 中的 `<el-collapse class="sampling-engine-collapse">` 结构
3. WHEN 抽凭完成, THE Platform SHALL 使用与原 handleSamplingFilled 相同的逻辑将凭证填入检查表
4. THE Platform SHALL 保持 accountCode="1122" 参数不变

### Requirement 3: F2 检查表组件抽凭模式迁移

**User Story:** As a 审计助理, I want F2 存货循环的抽凭操作与其他循环一致, so that 操作习惯无需切换。

#### Acceptance Criteria

1. WHEN F2ValuationTestSheet 组件加载完成, THE Platform SHALL 在工具栏区域显示抽凭按钮（替代 el-collapse 面板）
2. THE Platform SHALL 移除 F2ValuationTestSheet 中 `<el-collapse class="sampling-collapse">` 结构
3. WHEN F2TabPurchaseInboundCheck 组件加载完成, THE Platform SHALL 在工具栏区域显示抽凭按钮
4. WHEN F2TabMaterialUsageCheck 组件加载完成, THE Platform SHALL 在工具栏区域显示抽凭按钮
5. WHEN 抽凭完成, THE Platform SHALL 对每个组件保持与原有 handleSamplingFilled / handleAutoExtractFilled 相同的数据映射逻辑

### Requirement 4: F5TabMajorAdjustment 抽凭模式迁移

**User Story:** As a 审计助理, I want F5 营业成本重大调整的抽凭操作与标准 dialog-mode 一致, so that 不再有折叠面板占用页面空间。

#### Acceptance Criteria

1. WHEN F5TabMajorAdjustment 组件加载完成, THE Platform SHALL 在工具栏区域显示抽凭按钮
2. THE Platform SHALL 移除 F5TabMajorAdjustment 中 `<el-collapse class="f5-sampling">` 结构
3. WHEN 抽凭完成, THE Platform SHALL 保持 accountCode="6401" 及 phase="final" 参数不变
4. WHEN 抽凭完成, THE Platform SHALL 使用与原 handleSamplingFilled 相同的凭证到行的映射逻辑

### Requirement 5: GtG5LongTermReceivable 版本链模式迁移

**User Story:** As a 审计助理, I want G5 长期应收款底稿的版本链操作与其他 G 循环底稿一致, so that 版本快照与历史查看入口统一。

#### Acceptance Criteria

1. THE Platform SHALL 将 GtG5LongTermReceivable 中的 `useVersionTrail` 直接调用替换为 `useWorkpaperVersionToolbar`
2. WHEN 用户保存底稿数据, THE Version_Toolbar SHALL 自动触发 debounce 快照（autoSnapshot）
3. WHEN 用户点击版本历史按钮, THE Version_Toolbar SHALL 打开 GtWpVersionTrail drawer
4. THE Platform SHALL 移除 GtG5LongTermReceivable 中旧的 `autoSnapshot` 手动调用与 `versionTrailRef.value?.open?.()` 逻辑
5. WHEN 迁移完成后, THE Platform SHALL 保持版本快照的创建/对比/回滚功能不变

### Requirement 6: GtConfirmationAlternativeL05 版本链模式迁移

**User Story:** As a 审计助理, I want L05 替代程序底稿的版本链操作与平台标准一致, so that 版本管理体验统一。

#### Acceptance Criteria

1. THE Platform SHALL 将 GtConfirmationAlternativeL05 中的自建版本逻辑替换为 `useWorkpaperVersionToolbar`
2. WHEN 用户保存数据, THE Version_Toolbar SHALL 自动触发 debounce 快照
3. WHEN 用户点击版本历史按钮, THE Version_Toolbar SHALL 打开 GtWpVersionTrail drawer
4. THE Platform SHALL 移除该组件中与版本链相关的自建代码

### Requirement 7: 功能等价性保障

**User Story:** As a 现场经理, I want 模式统一迁移不改变任何现有功能行为, so that 已编制底稿数据安全。

#### Acceptance Criteria

1. WHEN 迁移完成后, THE Platform SHALL 保持所有组件的抽凭样本数据格式与原有格式完全一致
2. WHEN 迁移完成后, THE Platform SHALL 保持所有组件的版本快照 API 调用（创建/查询/对比/回滚）不变
3. WHEN 迁移完成后, THE Platform SHALL 保持所有组件的 checklist_responses 存储 item_id 不变
4. IF 迁移过程中发现组件存在未使用 @filled 事件的抽凭集成, THEN THE Platform SHALL 保留原有回调函数签名并适配 dialog-mode emit payload

### Requirement 8: 渐进式迁移支持

**User Story:** As a 开发者, I want 逐个组件独立迁移且互不影响, so that 可以分批验证。

#### Acceptance Criteria

1. THE Platform SHALL 支持逐个组件独立完成迁移（不要求一次性全部改造）
2. WHEN 某个组件完成迁移, THE Platform SHALL 保持其他未迁移组件正常运行
3. THE Platform SHALL 不引入新的共享状态或跨组件依赖
4. THE Platform SHALL 不修改 GtVoucherSamplingEngine 组件本身的 API（props / emits）
5. THE Platform SHALL 不修改 useWorkpaperVersionToolbar composable 本身的 API

### Requirement 9: 已有测试兼容性

**User Story:** As a 开发者, I want 迁移不破坏已有的 PBT 和单元测试, so that 质量保障链不中断。

#### Acceptance Criteria

1. WHEN 迁移完成后, THE Platform SHALL 通过所有已有的 voucherSampling.property.spec.ts 测试
2. WHEN 迁移完成后, THE Platform SHALL 通过所有已有的 versionTrail.spec.ts 测试
3. THE Platform SHALL 不修改任何已有测试文件的断言逻辑
