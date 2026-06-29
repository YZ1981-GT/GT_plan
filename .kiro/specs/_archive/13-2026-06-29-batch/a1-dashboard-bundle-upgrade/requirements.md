# 需求文档：A1 Dashboard 子底稿内嵌升级

## 简介

GtA1Dashboard.vue 是审计项目总控仪表盘（A1 审计程序总控表）。聚合推送后，A1-11~A1-16 已在 `wp_code_overrides` 中映射为 `skip`，但 GtA1Dashboard 尚未内嵌渲染这些子底稿。本次升级在现有仪表盘下方新增 Tab 区域，内嵌 6 个子底稿的渲染组件，并建立依赖联动逻辑（A17→A1-11→A1-15），使签发链路完整可操作。

## 术语表

- **GtA1Dashboard**：A1 项目总控仪表盘组件（现有 ~450 行）
- **useA1SubWorkpapers**：新增轻量 composable，管理子底稿 wp_id 解析、完成状态追踪、依赖规则
- **A1-11_签发流转控制表**：签发流程核心子底稿，依赖 A17 审计总结完成后才能签发
- **A1-12_审计质量控制检查表**：QC 复核用核对表
- **A1-13_分析性复核_期初**：期初余额分析性复核
- **A1-14_分析性复核_期末**：期末余额分析性复核
- **A1-15_归档检查表**：归档阶段检查表，依赖 A1-11 签发完成
- **A1-16_交接检查表**：项目交接时使用的检查表
- **GtA111SigningForm**：A1-11 签发流转控制表专用渲染组件（已存在，componentType='a1-11-signing-form'）
- **GtChecklistTable**：通用核对表渲染组件（componentType='checklist-table'）
- **GtAnalyticalReview**：分析性复核渲染组件（componentType='analytical-review'）
- **CompletionStatus**：子表完成三态标识——`completed` / `in_progress` / `not_started`
- **EventBus**：进程内事件总线，用于跨组件通知（如 A17 完成事件）

## 需求

### 需求 1：子底稿 Tab 区域渲染

**用户故事：** 作为审计助理，我希望在 A1 项目仪表盘的现有阶段卡片下方看到子底稿 Tab 区域，这样我可以直接在仪表盘内访问 A1-11~A1-16 各子底稿。

#### 验收标准

1. THE GtA1Dashboard SHALL 在现有阶段卡片区域（`.gt-a1-dashboard__phases`）下方渲染一个 el-tabs 组件
2. THE el-tabs SHALL 包含以下 Tab（按序）：A1-11（签发流转控制表）、A1-12（审计质量控制检查表）、A1-13（分析性复核-期初）、A1-14（分析性复核-期末）、A1-15（归档检查表）、A1-16（交接检查表）
3. WHEN Tab 区域内无任何适用子底稿时，THE GtA1Dashboard SHALL 隐藏整个 Tab 区域
4. THE Tab 区域 SHALL 使用折叠式设计，默认展开，用户可手动收起

### 需求 2：子底稿组件分发

**用户故事：** 作为审计助理，我希望每个子底稿 Tab 渲染对应的专属组件，这样我可以在正确的界面内完成各项操作。

#### 验收标准

1. WHEN A1-11 Tab 被选中时，THE GtA1Dashboard SHALL 渲染 GtA111SigningForm 组件并传入对应子底稿的 wp_id
2. WHEN A1-12 Tab 被选中时，THE GtA1Dashboard SHALL 渲染 GtChecklistTable 组件并传入对应子底稿的 wp_id
3. WHEN A1-13 Tab 被选中时，THE GtA1Dashboard SHALL 渲染 GtAnalyticalReview 组件并传入对应子底稿的 wp_id
4. WHEN A1-14 Tab 被选中时，THE GtA1Dashboard SHALL 渲染 GtAnalyticalReview 组件并传入对应子底稿的 wp_id
5. WHEN A1-15 Tab 被选中时，THE GtA1Dashboard SHALL 渲染 GtChecklistTable 组件并传入对应子底稿的 wp_id
6. WHEN A1-16 Tab 被选中时，THE GtA1Dashboard SHALL 渲染 GtChecklistTable 组件并传入对应子底稿的 wp_id

### 需求 3：子底稿 wp_id 解析

**用户故事：** 作为审计助理，我希望每个子 Tab 能正确加载对应子底稿的数据，而非加载父底稿 A1 的数据。

#### 验收标准

1. THE useA1SubWorkpapers SHALL 通过项目 wp_index 查询获取 A1-11~A1-16 各子底稿的 wp_id
2. WHEN 组件挂载时，THE useA1SubWorkpapers SHALL 调用 getWpIndex API 获取当前项目下所有 A1 系列子底稿的 wp_id 映射
3. IF 某子底稿在当前项目中不存在（无 wp_id），THEN THE GtA1Dashboard SHALL 隐藏对应 Tab
4. THE useA1SubWorkpapers SHALL 将解析到的子底稿 wp_id 传递给对应的子渲染组件

### 需求 4：A1-11 对 A17 的依赖（签发锁定）

**用户故事：** 作为业务合伙人，我希望在 A17 审计总结未完成前，A1-11 签发流转控制表处于锁定状态，确保签发前所有审计总结工作已完成。

#### 验收标准

1. WHILE A17 审计总结未标记为完成时，THE GtA1Dashboard SHALL 将 A1-11 Tab 设为只读模式
2. WHEN A17 审计总结标记为完成时，THE GtA1Dashboard SHALL 解锁 A1-11 Tab 为可编辑状态
3. WHILE A1-11 处于锁定状态时，THE GtA1Dashboard SHALL 在 A1-11 Tab 内容区域顶部显示警告提示："A17 审计总结未完成，无法进行签发操作"
4. THE useA1SubWorkpapers SHALL 通过 EventBus 监听 `a17-audit-summary-completed` 事件来更新 A17 完成状态

### 需求 5：A1-15 对 A1-11 的依赖（归档锁定）

**用户故事：** 作为现场经理，我希望在 A1-11 签发流转控制表未完成签发前，A1-15 归档检查表处于锁定状态，确保归档前签发流程已完成。

#### 验收标准

1. WHILE A1-11 签发流转控制表未标记为已签发时，THE GtA1Dashboard SHALL 将 A1-15 Tab 设为只读模式
2. WHEN A1-11 签发流转控制表标记为已签发时，THE GtA1Dashboard SHALL 解锁 A1-15 Tab 为可编辑状态
3. WHILE A1-15 处于锁定状态时，THE GtA1Dashboard SHALL 在 A1-15 Tab 内容区域顶部显示警告提示："A1-11 签发流转控制表未完成，无法进行归档检查"
4. THE useA1SubWorkpapers SHALL 通过 EventBus 监听 `a1-11-signing-completed` 事件来更新 A1-11 签发状态

### 需求 6：签发阶段进度集成

**用户故事：** 作为现场经理，我希望仪表盘顶部的环形进度和"复核与归档"阶段进度条能反映 A1-11 + A1-15 + A1-16 的完成状态，使项目整体进度真实可见。

#### 验收标准

1. THE GtA1Dashboard 的环形进度百分比计算 SHALL 将 A1-11、A1-15、A1-16 的完成状态纳入总项目程序数
2. THE "复核与归档（signoff）" 阶段进度条 SHALL 将 A1-11、A1-15、A1-16 完成状态计入该阶段完成比例
3. WHEN A1-11 标记为已签发时，THE 进度计算 SHALL 将 A1-11 计为已完成
4. WHEN A1-15 归档检查表所有项完成时，THE 进度计算 SHALL 将 A1-15 计为已完成
5. WHEN A1-16 交接检查表所有项完成时，THE 进度计算 SHALL 将 A1-16 计为已完成

### 需求 7：Tab 路由（sheetName 外部跳转）

**用户故事：** 作为审计助理，我希望从底稿目录或其他组件的 RefChip 跳转时能直接定位到 A1 仪表盘的特定子底稿 Tab，而不是每次都手动查找。

#### 验收标准

1. WHEN 外部通过 sheetName prop 传入 'A1-11'~'A1-16' 时，THE GtA1Dashboard SHALL 直接激活对应子底稿 Tab
2. WHEN URL query 参数包含 `?sheet=A1-15` 时，THE GtA1Dashboard SHALL 解析该参数并激活对应 Tab
3. IF sheetName 指定的值不在可见 Tab 列表中，THEN THE GtA1Dashboard SHALL 保持当前状态（不激活任何子底稿 Tab）

### 需求 8：只读模式透传

**用户故事：** 作为质量控制复核合伙人，我希望在只读复核模式下打开 A1 仪表盘时，所有子底稿 Tab 内容均不可编辑。

#### 验收标准

1. WHEN GtA1Dashboard 的 readonly prop 为 true 时，THE GtA1Dashboard SHALL 将 readonly 传递给所有子底稿渲染组件
2. WHILE 处于只读模式时，THE GtA111SigningForm SHALL 禁止签发操作
3. WHILE 处于只读模式时，THE GtChecklistTable SHALL 禁止核对项勾选和填写
4. WHILE 处于只读模式时，THE GtAnalyticalReview SHALL 禁止数据修改

### 需求 9：适用性控制

**用户故事：** 作为现场经理，我希望仅显示当前项目实际存在的子底稿 Tab，避免显示项目中未创建的子底稿。

#### 验收标准

1. THE GtA1Dashboard SHALL 根据 wp_index 中是否存在对应 wp_code 的底稿来判断各子 Tab 是否显示
2. WHEN 项目 wp_index 中无 A1-13 和 A1-14 条目时，THE GtA1Dashboard SHALL 隐藏分析性复核相关 Tab
3. WHEN 项目 wp_index 中所有 A1-11~A1-16 均不存在时，THE GtA1Dashboard SHALL 隐藏整个子底稿 Tab 区域

### 需求 10：EventBus 集成

**用户故事：** 作为审计助理，我希望当 A17 审计总结完成或 A1-11 签发完成时，仪表盘能自动感知并更新锁定状态，无需手动刷新页面。

#### 验收标准

1. THE useA1SubWorkpapers SHALL 在组件挂载时注册 EventBus 监听器，监听 `a17-audit-summary-completed` 事件
2. THE useA1SubWorkpapers SHALL 在组件挂载时注册 EventBus 监听器，监听 `a1-11-signing-completed` 事件
3. WHEN `a17-audit-summary-completed` 事件触发时，THE useA1SubWorkpapers SHALL 将 A17 完成状态更新为 true 并解锁 A1-11
4. WHEN `a1-11-signing-completed` 事件触发时，THE useA1SubWorkpapers SHALL 将 A1-11 签发状态更新为 true 并解锁 A1-15
5. THE useA1SubWorkpapers SHALL 在组件卸载时移除所有 EventBus 监听器
