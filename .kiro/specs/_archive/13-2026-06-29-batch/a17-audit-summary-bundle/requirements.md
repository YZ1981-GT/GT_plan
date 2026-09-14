# 需求文档：A17 审计总结聚合升级

## 简介

将 A17（全面审核意见程序表）及其子底稿（A17-1 至 A17-7）从底稿目录中的独立条目聚合为单一 `a17-bundle` 组件，内部通过 Tab 导航切换渲染各子底稿。此模式与已有的 `a11-bundle`（A11 期后事项）和 `a15-bundle`（A15 持续经营）一致。

A17 审计总结是审计业务的核心签发底稿，子底稿之间存在业务联动关系：A17-5（核对表）完成状态驱动 A17-6（总结会议）和 A17-7（独立性签署）的可编辑性；A17-1（重大事项概要）自动引用 B50 风险评估和 D~N 循环审计发现；A17 主程序表的签发需满足所有前置条件。

## 术语表

- **A17_Bundle**：聚合组件，对外暴露为单一 componentType `a17-bundle`，内部通过 Tab 分发渲染 A17 主程序表及所有子底稿
- **wp_code_overrides**：底稿编码到 componentType 的精确映射 JSON 配置（`backend/app/data/wp_code_overrides.json`）
- **htmlRendererRegistry**：前端 componentType → Vue 组件的单一来源注册表
- **GtAProgramConsole**：审计程序表通用渲染组件
- **GtChecklistTable**：核对表通用渲染组件
- **WorkpaperWordEditor**：Word 模板（OnlyOffice）渲染组件
- **GtA17Summary**：A17-1 重大事项概要 16 章导航式编辑组件
- **IndependenceSigning**：独立性签署专用组件
- **GtEmbeddedChecklist**：嵌入式核对表组件（bundle 内 tab 渲染 checklist-table 的代理）
- **sheetName**：Tab 路由参数，用于外部跳转直接定位到指定子 Tab
- **适用性**：某些子底稿仅在特定项目类型下显示（如 A17-5-1~5-5 按审计业务类型选择性展示）
- **useA17BundleState**：轻量 composable，管理子表完成状态、联动规则和签发前置条件
- **完成状态（CompletionStatus）**：子表的三态标识——`completed`（已完成）/ `in_progress`（进行中）/ `not_started`（未开始）
- **签发前置条件**：A17 主程序表标记"审计总结完成"前必须满足的全部条件集合
- **KAM**：Key Audit Matter，关键审计事项（从 B50 风险评估和 D~N 循环发现中提取的重大事项）

## 需求

### 需求 1：聚合入口组件注册

**用户故事：** 作为审计助理，我希望在底稿目录点击 A17 时打开一个统一的聚合组件，而非默认的 a-program-console，这样我可以在同一界面内访问所有 A17 子底稿。

#### 验收标准

1. THE A17_Bundle SHALL 在 htmlRendererRegistry 中注册为 componentType `a17-bundle`，使用 defineAsyncComponent 延迟加载
2. WHEN wp_code_overrides 中 A17 的映射为 `a17-bundle` 时，THE 底稿渲染器 SHALL 加载并渲染 A17_Bundle 组件
3. THE A17_Bundle SHALL 接收 props：`wpId`（必填）、`sheetName`（可选，用于 Tab 路由）、`readonly`（可选）
4. THE A17_Bundle SHALL 使用 contextProps 策略 `standard`，由 GtWpRenderer 自动透传 wp-id、project-id、wp-code、year

### 需求 2：子底稿映射为 skip

**用户故事：** 作为现场经理，我不希望 A17 的子底稿（A17-1 至 A17-7）在底稿目录中重复显示为独立条目，因为它们已被聚合到 A17 bundle 内部 Tab 中。

#### 验收标准

1. WHEN A17_Bundle 启用后，THE wp_code_overrides SHALL 将以下编码映射为 `skip`：A17-1、A17-2-1、A17-3、A17-3-1、A17-4、A17-5-1、A17-5-2、A17-5-3、A17-5-4、A17-5-5、A17-6、A17-7
2. THE wp_code_overrides SHALL 将 A17 映射为 `a17-bundle`
3. WHEN 底稿目录加载时，THE 系统 SHALL 对 componentType 为 `skip` 的底稿不渲染为独立条目

### 需求 3：Tab 结构与内部渲染分发

**用户故事：** 作为审计助理，我希望在 A17 聚合组件内通过 Tab 切换查看和编辑各子底稿，每个 Tab 渲染对应的专属组件。

#### 验收标准

1. THE A17_Bundle SHALL 渲染以下 Tab（按序）：
   - `program`：全面审核意见程序表（渲染 GtAProgramConsole，embedded=true）
   - `A17-1`：重大事项概要（渲染 GtA17Summary）
   - `A17-2-1`：交审审计专项（渲染 WorkpaperWordEditor）
   - `A17-3`：业务备案报告（渲染 WorkpaperWordEditor）
   - `A17-3-1`：业务备案部门审计质量检查报告（渲染 WorkpaperWordEditor）
   - `A17-4`：本人义务注意事项通知（渲染 WorkpaperWordEditor）
   - `A17-5`：审计工作完成核对表（渲染 GtEmbeddedChecklist，按适用性显示 A17-5-1 至 A17-5-5）
   - `A17-6`：总结会议纪要（渲染 WorkpaperWordEditor）
   - `A17-7`：独立性签署（渲染 IndependenceSigning）
2. WHEN Tab `program` 被选中时，THE A17_Bundle SHALL 渲染 GtAProgramConsole 并传入 `wp-id` 和 `embedded=true`
3. WHEN Tab 为 word-template 类型时，THE A17_Bundle SHALL 渲染 WorkpaperWordEditor 并传入对应子底稿的 wp_id
4. WHEN Tab `A17-1` 被选中时，THE A17_Bundle SHALL 渲染 GtA17Summary 并传入 project-id 和 wp-id
5. WHEN Tab `A17-7` 被选中时，THE A17_Bundle SHALL 渲染 IndependenceSigning 并传入对应子底稿的 wp-id
6. WHEN Tab `A17-5` 被选中时，THE A17_Bundle SHALL 渲染 GtEmbeddedChecklist 并根据项目适用性确定显示 A17-5-1 至 A17-5-5 中的哪一个

### 需求 4：Tab 路由与外部跳转

**用户故事：** 作为审计助理，我希望从底稿目录或其他底稿中的 RefChip 跳转时能直接定位到 A17 聚合组件的特定子 Tab，而不是每次都从第一个 Tab 开始。

#### 验收标准

1. WHEN 外部通过 `navigate('A17', { sheet: 'A17-1' })` 跳转时，THE A17_Bundle SHALL 直接激活 `A17-1` Tab
2. WHEN URL query 参数包含 `?sheet=A17-3` 时，THE A17_Bundle SHALL 解析该参数并激活对应 Tab
3. WHEN props.sheetName 变更时，THE A17_Bundle SHALL 响应并切换到对应 Tab
4. IF sheetName 指定的值不在 Tab 定义列表中，THEN THE A17_Bundle SHALL 保持当前 Tab 不变（默认为 program Tab）

### 需求 5：子底稿 wp_id 解析

**用户故事：** 作为审计助理，我希望每个子 Tab 能正确加载对应子底稿的数据，而不是加载父底稿 A17 的数据。

#### 验收标准

1. THE A17_Bundle SHALL 通过项目 wp_index 查询获取各子底稿（A17-1 至 A17-7）的 wp_id
2. WHEN 组件挂载时，THE A17_Bundle SHALL 调用 API 获取当前项目下所有 A17 系列底稿的 wp_id 映射
3. IF 某子底稿在当前项目中不存在（无 wp_id），THEN THE A17_Bundle SHALL 隐藏或禁用对应 Tab
4. THE A17_Bundle SHALL 将解析到的子底稿 wp_id 传递给对应的子渲染组件

### 需求 6：适用性控制

**用户故事：** 作为现场经理，我希望 A17-5 系列核对表（5 种业务类型）只显示当前项目适用的那一种，避免审计助理误填不相关的核对表。

#### 验收标准

1. THE A17_Bundle SHALL 根据项目的业务类型（制版审计/内控审计/IPO/新三板/函证翻件）确定 A17-5 系列中哪个核对表适用
2. WHEN 项目存在多个适用的 A17-5 子底稿时，THE A17_Bundle SHALL 为每个适用的子底稿显示独立 Tab
3. WHEN 项目无任何适用的 A17-5 子底稿时，THE A17_Bundle SHALL 隐藏 A17-5 相关 Tab
4. THE A17_Bundle SHALL 通过 wp_index 中是否存在对应 wp_code 的底稿来判断适用性（有 wp_id 即适用）

### 需求 7：后端 componentType 注册

**用户故事：** 作为开发者，我希望新增的 `a17-bundle` componentType 通过后端校验，不导致启动报错。

#### 验收标准

1. THE 系统 SHALL 在 `VALID_COMPONENT_TYPES`（wp_classification_service.py）中注册 `a17-bundle`
2. WHEN 后端启动并调用 `validate_overrides` 时，THE 系统 SHALL 正常校验通过包含 `a17-bundle` 的 wp_code_overrides
3. THE htmlRendererRegistry 类型定义 SHALL 包含 `a17-bundle` 作为 HtmlComponentType 联合类型的一个成员

### 需求 8：只读模式透传

**用户故事：** 作为质量控制复核合伙人，我希望在只读复核模式下打开 A17 聚合组件时，所有子 Tab 内容均不可编辑。

#### 验收标准

1. WHEN A17_Bundle 的 readonly prop 为 true 时，THE A17_Bundle SHALL 将 readonly 传递给所有子渲染组件
2. WHILE 处于只读模式时，THE WorkpaperWordEditor SHALL 禁止编辑
3. WHILE 处于只读模式时，THE GtA17Summary SHALL 禁止章节内容修改
4. WHILE 处于只读模式时，THE GtChecklistTable SHALL 禁止核对项勾选和填写

### 需求 9：子表完成状态追踪

**用户故事：** 作为现场经理，我希望系统能自动追踪 A17 各子表的完成状态，驱动后续联动逻辑（A17-5 核对表完成 → A17-6/A17-7 可编辑），使签发流程有序推进。

#### 验收标准

1. THE useA17BundleState SHALL 追踪以下子表的完成状态：A17-1、A17-5（全部适用核对项）、A17-6、A17-7
2. WHEN A17-5 核对表所有适用项的 conclusion 均为非空值时，THE useA17BundleState SHALL 将 A17-5 完成状态标记为 `completed`
3. WHEN A17-5 核对表部分项已填写但未全部完成时，THE useA17BundleState SHALL 将 A17-5 完成状态标记为 `in_progress`
4. WHEN A17-5 核对表无任何项填写时，THE useA17BundleState SHALL 将 A17-5 完成状态标记为 `not_started`
5. THE useA17BundleState SHALL 通过读取各子底稿的 checklist_responses 数据推导完成状态
6. WHEN 用户切换到 A17 Bundle 时，THE useA17BundleState SHALL 自动加载各子表最新完成状态

### 需求 10：A17-5 → A17-6 联动（核对表完成 → 总结会议可编辑）

**用户故事：** 作为业务合伙人，我希望在审计完成核对表（A17-5）全部完成前，总结会议纪要（A17-6）处于不可编辑状态，确保总结会议在所有检查完毕后才能召开。

#### 验收标准

1. WHILE A17-5 完成状态为 `not_started` 或 `in_progress` 时，THE A17_Bundle SHALL 将 A17-6 Tab 设为只读模式
2. WHEN A17-5 完成状态变为 `completed` 时，THE A17_Bundle SHALL 解锁 A17-6 Tab 为可编辑状态
3. WHILE A17-6 处于锁定状态时，THE A17_Bundle SHALL 在 A17-6 Tab 内容区域顶部显示警告提示："A17-5 审计完成核对表未完成，无法编辑总结会议纪要"
4. WHEN 用户点击被锁定的 A17-6 Tab 时，THE A17_Bundle SHALL 允许查看内容但禁止编辑（readonly=true 覆盖）

### 需求 11：A17-5 → A17-7 联动（独立性相关项确认 → 独立性签署可编辑）

**用户故事：** 作为业务合伙人，我希望在审计完成核对表（A17-5）中独立性相关检查项确认完毕前，独立性签署（A17-7）处于不可编辑状态，确保独立性声明基于充分的检查。

#### 验收标准

1. WHILE A17-5 完成状态为 `not_started` 或 `in_progress` 时，THE A17_Bundle SHALL 将 A17-7 Tab 设为只读模式
2. WHEN A17-5 完成状态变为 `completed` 时，THE A17_Bundle SHALL 解锁 A17-7 Tab 为可编辑状态
3. WHILE A17-7 处于锁定状态时，THE A17_Bundle SHALL 在 A17-7 Tab 内容区域顶部显示警告提示："A17-5 审计完成核对表未完成，无法进行独立性签署"
4. WHEN 用户点击被锁定的 A17-7 Tab 时，THE A17_Bundle SHALL 允许查看已有内容但禁止签署操作

### 需求 12：A17 主程序表签发前置条件

**用户故事：** 作为业务合伙人，我希望 A17 主程序表只有在所有前置条件满足后才能标记为"审计总结完成"，确保签发流程的严谨性和完整性。

#### 验收标准

1. THE useA17BundleState SHALL 计算签发前置条件是否全部满足：A17-1（KAM 编制完成）+ A17-5（核对表全部完成）+ A17-7（独立性已签署）
2. WHILE 签发前置条件未全部满足时，THE A17_Bundle SHALL 在 program Tab 的签发按钮上显示禁用状态
3. WHEN 签发前置条件全部满足时，THE A17_Bundle SHALL 启用 program Tab 的签发功能
4. THE A17_Bundle SHALL 在 program Tab 显示签发前置条件清单及各项当前状态（✓ 已满足 / ✗ 未满足）
5. IF 用户尝试在前置条件未满足时签发，THEN THE A17_Bundle SHALL 显示阻断提示并列出未完成的前置条件项

### 需求 13：A17-1 重大事项自动引用

**用户故事：** 作为审计助理，我希望 A17-1 重大事项概要能自动引用 B50 风险评估和 D~N 循环审计中的重大发现，减少手工查找和转录的工作量。

#### 验收标准

1. THE useA17BundleState SHALL 提供 KAM 引用数据源接口，从 B50 风险评估拉取重大风险项
2. THE useA17BundleState SHALL 提供 KAM 引用数据源接口，从 D~N 循环审计发现中拉取重大错报或重大事项
3. WHEN A17-1 Tab 被选中时，THE A17_Bundle SHALL 向 GtA17Summary 传递 KAM 引用数据作为参考来源
4. THE GtA17Summary SHALL 在相关章节（ch12 关键审计事项）中展示 KAM 引用数据的摘要信息
5. IF B50 或 D~N 循环底稿中无重大发现，THEN THE useA17BundleState SHALL 返回空引用列表并在界面提示"暂无重大发现需引用"

### 需求 14：完成状态仪表盘

**用户故事：** 作为现场经理，我希望在 A17 聚合组件顶部看到各子表的完成进度总览（已完成/进行中/未开始），快速了解审计总结签发进度。

#### 验收标准

1. THE A17_Bundle SHALL 在 Tab 栏上方显示完成状态仪表盘条
2. THE 仪表盘 SHALL 显示各关键子表的完成状态图标和标签：A17-1（KAM）、A17-5（核对表）、A17-6（总结会议）、A17-7（独立性签署）
3. THE 仪表盘 SHALL 使用三色状态指示：绿色（✓ 已完成）、黄色（◐ 进行中）、灰色（○ 未开始）
4. WHEN 任一子表完成状态发生变化时，THE 仪表盘 SHALL 实时更新对应指示器状态
5. THE 仪表盘 SHALL 在所有关键前置条件满足时显示"可签发"整体状态标识
6. WHEN 用户点击仪表盘中的子表状态指示器时，THE A17_Bundle SHALL 切换到对应 Tab
