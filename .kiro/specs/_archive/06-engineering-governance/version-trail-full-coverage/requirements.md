# Requirements Document

## Introduction

系统性地将版本链能力（`useWorkpaperVersionToolbar` + `GtWpVersionTrail` 组件 + 保存后自动快照）接入所有 D~N 循环底稿主入口组件。当前仅 D2（`GtD2AccountsReceivable.vue`）已完成接入，S 循环（S3-S6/S12-S15/S20/S21）+ M8/M9 + 抽凭引擎已接入。本 spec 覆盖 D3~D7、E1、F1~F5、G1~G14、H1~H10、I1~I6、J1~J3、K1~K13、L1~L8、M1~M10、N1~N5 全部未接入底稿的标准化接线，并增加 CI 守卫确保新增底稿不遗漏版本链集成。

## Glossary

- **Version_Trail**: 底稿版本历史功能，包含版本快照创建、版本历史抽屉查看、版本对比能力
- **useWorkpaperVersionToolbar**: Vue composable，提供 `versionTrailRef`（组件引用）、`openVersionHistory`（打开历史抽屉）、`scheduleAutoSnapshot`（debounce 自动快照）
- **GtWpVersionTrail**: 版本历史 Drawer 组件，接收 `:workpaper-id` 和 `:project-id` props，通过 ref 绑定暴露 `openDrawer()` 方法
- **AutoSnapshot**: 保存后自动触发的版本快照，description 固定为"编辑后自动快照"
- **Main_Entry_Component**: D~N 循环底稿主入口 Vue 组件（如 GtD3PrepaidAccounts），负责 sheetName-based v-if 分发及全局 provide
- **CI_Guard**: 持续集成守卫脚本，静态扫描所有底稿主入口确保版本链集成不遗漏
- **Version_Trail_Ref**: `versionTrailRef` 引用，provide 给子 tab 组件用于触发版本历史查看
- **Save_Flow**: 底稿主入口的保存逻辑（formData.saveItemsFromEvent 或等效 PUT 调用后触发 scheduleAutoSnapshot）

## Requirements

### Requirement 1: D3~D7 底稿版本链接入

**User Story:** As a 审计助理, I want D3~D7 底稿在保存后自动创建版本快照并能查看版本历史, so that 我可以追溯每次编辑的变更记录。

#### Acceptance Criteria

1. WHEN GtD3PrepaidAccounts 组件挂载, THE Main_Entry_Component SHALL 调用 `useWorkpaperVersionToolbar` 并传入 wpId 和 projectId refs
2. WHEN GtD3PrepaidAccounts 保存数据成功, THE Main_Entry_Component SHALL 调用 `scheduleAutoSnapshot` 触发自动快照
3. THE Main_Entry_Component SHALL 在模板中挂载 `GtWpVersionTrail` 组件并通过 ref 绑定 `versionTrailRef`
4. THE Main_Entry_Component SHALL provide `versionTrailRef` 和 `openVersionHistory` 给子 tab 组件
5. WHEN 上述接线应用于 GtD4Revenue、GtD5OtherCurrentAssets、GtD6LongTermReceivables、GtD7OtherNonCurrentAssets, THE Main_Entry_Component SHALL 遵循相同的接入模式

### Requirement 2: E1 底稿版本链接入

**User Story:** As a 审计助理, I want E1 货币资金底稿在保存后自动创建版本快照, so that 现金与银行存款的审计过程有完整版本追溯。

#### Acceptance Criteria

1. WHEN GtE1CashAndBank 组件挂载, THE Main_Entry_Component SHALL 调用 `useWorkpaperVersionToolbar` 并传入 wpId 和 projectId refs
2. WHEN GtE1CashAndBank 保存数据成功, THE Main_Entry_Component SHALL 调用 `scheduleAutoSnapshot` 触发自动快照
3. THE Main_Entry_Component SHALL 在模板中挂载 `GtWpVersionTrail` 组件并绑定 `:workpaper-id` 和 `:project-id`
4. THE Main_Entry_Component SHALL provide `versionTrailRef` 和 `openVersionHistory` 给子 tab 组件

### Requirement 3: F1~F5 底稿版本链接入

**User Story:** As a 审计助理, I want F 循环存货及成本底稿在保存后自动创建版本快照, so that 存货盘点、成本测算的审计变更可追溯。

#### Acceptance Criteria

1. WHEN GtF1Inventory 组件挂载, THE Main_Entry_Component SHALL 调用 `useWorkpaperVersionToolbar` 并传入 wpId 和 projectId refs
2. WHEN GtF1Inventory 保存数据成功, THE Main_Entry_Component SHALL 调用 `scheduleAutoSnapshot` 触发自动快照
3. THE Main_Entry_Component SHALL 在模板中挂载 `GtWpVersionTrail` 组件并通过 ref 绑定
4. WHEN 上述接线应用于 GtF2CostOfSales（含子入口 GtF2InventoryMain/GtF2InventorySpecial/GtF2InventoryValuation/GtF2InventoryStocktake）、GtF3NotesPayable、GtF4AccountsPayable、GtF5CostOfSales, THE Main_Entry_Component SHALL 遵循相同的接入模式
5. IF F2 子入口组件（如 GtF2InventoryMain）独立持有 wpId/projectId, THEN THE Main_Entry_Component SHALL 在该子入口级别独立接入版本链

### Requirement 4: G1~G14 金融工具底稿版本链接入

**User Story:** As a 审计助理, I want G 循环金融工具底稿在保存后自动创建版本快照, so that 金融资产/负债的复杂审计过程有版本追溯。

#### Acceptance Criteria

1. WHEN GtG1 至 GtG14 中任一主入口组件挂载, THE Main_Entry_Component SHALL 调用 `useWorkpaperVersionToolbar` 并传入 wpId 和 projectId refs
2. WHEN 任一 G 类主入口保存数据成功, THE Main_Entry_Component SHALL 调用 `scheduleAutoSnapshot` 触发自动快照
3. THE Main_Entry_Component SHALL 在模板中挂载 `GtWpVersionTrail` 组件并通过 ref 绑定
4. THE Main_Entry_Component SHALL provide `versionTrailRef` 和 `openVersionHistory` 给子 tab 组件
5. THE Main_Entry_Component SHALL 对全部 14 个 G 类主入口（GtG1~GtG14）统一完成接入

### Requirement 5: H1~H10 固定资产底稿版本链接入

**User Story:** As a 审计助理, I want H 循环固定资产底稿在保存后自动创建版本快照, so that 固定资产折旧、减值测算的审计过程可追溯。

#### Acceptance Criteria

1. WHEN GtH1 至 GtH10 中任一主入口组件挂载, THE Main_Entry_Component SHALL 调用 `useWorkpaperVersionToolbar` 并传入 wpId 和 projectId refs
2. WHEN 任一 H 类主入口保存数据成功, THE Main_Entry_Component SHALL 调用 `scheduleAutoSnapshot` 触发自动快照
3. THE Main_Entry_Component SHALL 在模板中挂载 `GtWpVersionTrail` 组件并通过 ref 绑定
4. THE Main_Entry_Component SHALL provide `versionTrailRef` 和 `openVersionHistory` 给子 tab 组件

### Requirement 6: I1~I6 无形资产/商誉底稿版本链接入

**User Story:** As a 审计助理, I want I 循环无形资产底稿在保存后自动创建版本快照, so that 无形资产摊销与商誉减值的审计变更可追溯。

#### Acceptance Criteria

1. WHEN GtI1 至 GtI6 中任一主入口组件挂载, THE Main_Entry_Component SHALL 调用 `useWorkpaperVersionToolbar` 并传入 wpId 和 projectId refs
2. WHEN 任一 I 类主入口保存数据成功, THE Main_Entry_Component SHALL 调用 `scheduleAutoSnapshot` 触发自动快照
3. THE Main_Entry_Component SHALL 在模板中挂载 `GtWpVersionTrail` 组件并通过 ref 绑定
4. THE Main_Entry_Component SHALL provide `versionTrailRef` 和 `openVersionHistory` 给子 tab 组件

### Requirement 7: J1~J3 租赁底稿版本链接入

**User Story:** As a 审计助理, I want J 循环租赁底稿在保存后自动创建版本快照, so that 使用权资产与租赁负债的审计过程可追溯。

#### Acceptance Criteria

1. WHEN GtJ1 至 GtJ3 中任一主入口组件挂载, THE Main_Entry_Component SHALL 调用 `useWorkpaperVersionToolbar` 并传入 wpId 和 projectId refs
2. WHEN 任一 J 类主入口保存数据成功, THE Main_Entry_Component SHALL 调用 `scheduleAutoSnapshot` 触发自动快照
3. THE Main_Entry_Component SHALL 在模板中挂载 `GtWpVersionTrail` 组件并通过 ref 绑定
4. THE Main_Entry_Component SHALL provide `versionTrailRef` 和 `openVersionHistory` 给子 tab 组件

### Requirement 8: K1~K13 负债/收入/费用底稿版本链接入

**User Story:** As a 审计助理, I want K 循环底稿在保存后自动创建版本快照, so that 收入确认、费用列支的审计判断有版本追溯。

#### Acceptance Criteria

1. WHEN GtK1 至 GtK13 中任一主入口组件挂载, THE Main_Entry_Component SHALL 调用 `useWorkpaperVersionToolbar` 并传入 wpId 和 projectId refs
2. WHEN 任一 K 类主入口保存数据成功, THE Main_Entry_Component SHALL 调用 `scheduleAutoSnapshot` 触发自动快照
3. THE Main_Entry_Component SHALL 在模板中挂载 `GtWpVersionTrail` 组件并通过 ref 绑定
4. THE Main_Entry_Component SHALL provide `versionTrailRef` 和 `openVersionHistory` 给子 tab 组件

### Requirement 9: L1~L8 借款底稿版本链接入

**User Story:** As a 审计助理, I want L 循环借款底稿在保存后自动创建版本快照, so that 借款利息测算与还款核对的审计过程可追溯。

#### Acceptance Criteria

1. WHEN GtL1 至 GtL8 中任一主入口组件挂载, THE Main_Entry_Component SHALL 调用 `useWorkpaperVersionToolbar` 并传入 wpId 和 projectId refs
2. WHEN 任一 L 类主入口保存数据成功, THE Main_Entry_Component SHALL 调用 `scheduleAutoSnapshot` 触发自动快照
3. THE Main_Entry_Component SHALL 在模板中挂载 `GtWpVersionTrail` 组件并通过 ref 绑定
4. THE Main_Entry_Component SHALL provide `versionTrailRef` 和 `openVersionHistory` 给子 tab 组件

### Requirement 10: M1~M10 权益底稿版本链接入

**User Story:** As a 审计助理, I want M 循环权益底稿在保存后自动创建版本快照, so that 股本变动、利润分配的审计过程可追溯。

#### Acceptance Criteria

1. WHEN GtM1 至 GtM10 中任一主入口组件挂载, THE Main_Entry_Component SHALL 调用 `useWorkpaperVersionToolbar` 并传入 wpId 和 projectId refs
2. WHEN 任一 M 类主入口保存数据成功, THE Main_Entry_Component SHALL 调用 `scheduleAutoSnapshot` 触发自动快照
3. THE Main_Entry_Component SHALL 在模板中挂载 `GtWpVersionTrail` 组件并通过 ref 绑定
4. THE Main_Entry_Component SHALL provide `versionTrailRef` 和 `openVersionHistory` 给子 tab 组件

### Requirement 11: N1~N5 税项底稿版本链接入

**User Story:** As a 审计助理, I want N 循环税项底稿在保存后自动创建版本快照, so that 税项计算与递延税的审计过程可追溯。

#### Acceptance Criteria

1. WHEN GtN1 至 GtN5 中任一主入口组件挂载, THE Main_Entry_Component SHALL 调用 `useWorkpaperVersionToolbar` 并传入 wpId 和 projectId refs
2. WHEN 任一 N 类主入口保存数据成功, THE Main_Entry_Component SHALL 调用 `scheduleAutoSnapshot` 触发自动快照
3. THE Main_Entry_Component SHALL 在模板中挂载 `GtWpVersionTrail` 组件并通过 ref 绑定
4. THE Main_Entry_Component SHALL provide `versionTrailRef` 和 `openVersionHistory` 给子 tab 组件

### Requirement 12: GtWpVersionTrail 组件 Prop 绑定规范

**User Story:** As a 开发者, I want 版本链组件的 prop 绑定统一且正确, so that 版本快照能正确关联到底稿实例。

#### Acceptance Criteria

1. THE Main_Entry_Component SHALL 使用 `:workpaper-id="props.wpId"` 绑定底稿 ID（非 `:wp-id`）
2. THE Main_Entry_Component SHALL 使用 `:project-id="props.projectId"` 绑定项目 ID
3. THE Main_Entry_Component SHALL 使用 `ref="versionTrailRef"` 绑定组件引用
4. IF 主入口组件未接收 wpId 或 projectId props, THEN THE Main_Entry_Component SHALL 从其他来源（如 route params 或 inject）获取并传入

### Requirement 13: 自动快照统一 Description

**User Story:** As a 现场经理, I want 所有底稿自动快照使用统一的描述文本, so that 版本列表中能区分自动快照与手动快照。

#### Acceptance Criteria

1. THE AutoSnapshot SHALL 使用固定 description "编辑后自动快照"
2. THE AutoSnapshot SHALL 通过 `scheduleAutoSnapshot` 触发（debounce 3000ms 默认）
3. IF 保存操作失败, THEN THE Main_Entry_Component SHALL 不触发 scheduleAutoSnapshot

### Requirement 14: CI 守卫检查版本链集成

**User Story:** As a 开发者, I want CI 自动检查所有底稿主入口是否已接入版本链, so that 新增底稿不会遗漏版本链集成。

#### Acceptance Criteria

1. THE CI_Guard SHALL 扫描所有 D~N 底稿主入口组件文件
2. WHEN 主入口组件缺少 `useWorkpaperVersionToolbar` 导入或调用, THE CI_Guard SHALL 报告该文件为未接入
3. WHEN 主入口组件缺少 `GtWpVersionTrail` 模板挂载, THE CI_Guard SHALL 报告该文件为未接入
4. THE CI_Guard SHALL 以非零退出码阻断 CI（`--strict` 模式）
5. THE CI_Guard SHALL 维护一个白名单文件，允许豁免特定组件（如纯 OnlyOffice 底稿无 HTML 主入口的情况）

### Requirement 15: Provide 命名规范统一

**User Story:** As a 开发者, I want 各循环 provide 的版本链引用使用统一命名约定, so that 子 tab 组件可以用一致的 inject key 获取版本链能力。

#### Acceptance Criteria

1. THE Main_Entry_Component SHALL provide versionTrailRef 使用 key 格式 `{cyclePrefix}VersionTrailRef`（如 `d3VersionTrailRef`、`g4VersionTrailRef`）
2. THE Main_Entry_Component SHALL provide openVersionHistory 使用 key 格式 `{cyclePrefix}OpenVersionHistory`（如 `d3OpenVersionHistory`、`g4OpenVersionHistory`）
3. IF 子 tab 组件需要触发版本历史查看, THEN THE Main_Entry_Component SHALL 确保 inject key 可被正确解析
