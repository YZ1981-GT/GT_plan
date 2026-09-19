# 需求文档：A16 管理层声明书聚合组件

## 简介

将 A16（管理层声明书）及其 7 个子底稿（A16-1 至 A16-7）从底稿目录中的独立条目聚合为单一 `a16-bundle` 组件，内部通过 Tab 导航切换渲染各子底稿。所有子底稿均为 word-template 类型，无业务联动逻辑，是最简单的 bundle 模式（与 GtA11Bundle 复杂度相当）。

## 术语表

- **A16_Bundle**：聚合组件，对外暴露为 componentType `a16-bundle`，内部通过 Tab 分发渲染 A16 各子底稿的 WorkpaperWordEditor
- **wp_code_overrides**：底稿编码到 componentType 的精确映射 JSON 配置（`backend/app/data/wp_code_overrides.json`）
- **htmlRendererRegistry**：前端 componentType → Vue 组件的单一来源注册表
- **WorkpaperWordEditor**：Word 模板（OnlyOffice）渲染组件
- **sheetName**：Tab 路由参数，用于外部跳转直接定位到指定子 Tab
- **wp_index**：底稿索引表，包含项目下所有底稿的 wp_code → wp_id 映射

## 需求

### 需求 1：聚合入口组件注册

**用户故事：** 作为审计助理，我希望在底稿目录点击 A16 时打开一个统一的聚合组件，在同一界面内通过 Tab 访问所有管理层声明书子底稿。

#### 验收标准

1. THE A16_Bundle SHALL 在 htmlRendererRegistry 中注册为 componentType `a16-bundle`，使用 defineAsyncComponent 延迟加载
2. THE A16_Bundle SHALL 接收 props：`wpId`（必填）、`sheetName`（可选）、`readonly`（可选）
3. THE A16_Bundle SHALL 使用 contextProps 策略 `standard`，由 GtWpRenderer 自动透传 wp-id、project-id、wp-code、year
4. THE 后端 VALID_COMPONENT_TYPES SHALL 包含 `a16-bundle`

### 需求 2：子底稿 skip 映射

**用户故事：** 作为现场经理，我不希望 A16 的子底稿在底稿目录中重复显示为独立条目，因为它们已被聚合到 A16 bundle 内部 Tab 中。

#### 验收标准

1. THE wp_code_overrides SHALL 将 A16 映射为 `a16-bundle`
2. THE wp_code_overrides SHALL 将 A16-1、A16-2、A16-3、A16-4、A16-5、A16-6、A16-7 全部映射为 `skip`

### 需求 3：Tab 结构与 Word 编辑器渲染

**用户故事：** 作为审计助理，我希望在 A16 聚合组件内通过 Tab 切换查看和编辑各管理层声明书子底稿。

#### 验收标准

1. THE A16_Bundle SHALL 渲染以下 Tab（按序）：A16-1（会计审核版）、A16-2（整合审核版）、A16-3（IPO补贴）、A16-4（IPO券商审阅）、A16-5（新三板申报）、A16-6（合营协议）、A16-7（关联交易合规说明）
2. WHEN 某 Tab 被选中时，THE A16_Bundle SHALL 渲染 WorkpaperWordEditor 并传入对应子底稿的 wp_id 和 readonly prop
3. THE A16_Bundle SHALL 仅显示当前项目 wp_index 中存在的子底稿 Tab（非所有项目都有全部 7 种声明书）

### 需求 4：Tab 路由与外部跳转

**用户故事：** 作为审计助理，我希望从底稿目录或 RefChip 跳转时能直接定位到 A16 聚合组件的特定子 Tab。

#### 验收标准

1. WHEN props.sheetName 或 route.query.sheet 指定合法 Tab id 时，THE A16_Bundle SHALL 激活对应 Tab
2. IF sheetName 指定的值不在可见 Tab 列表中，THEN THE A16_Bundle SHALL 保持默认 Tab（第一个可见 Tab）

### 需求 5：子底稿 wp_id 解析

**用户故事：** 作为审计助理，我希望每个子 Tab 能正确加载对应子底稿的数据。

#### 验收标准

1. THE A16_Bundle SHALL 通过 getWpIndex(projectId) 获取各子底稿的 wp_id 映射
2. THE A16_Bundle SHALL 将解析到的子底稿 wp_id 传递给 WorkpaperWordEditor
3. IF 某子底稿在当前项目中不存在（无 wp_id），THEN THE A16_Bundle SHALL 隐藏对应 Tab

### 需求 6：只读模式透传

**用户故事：** 作为质量控制复核合伙人，我希望在只读复核模式下打开 A16 聚合组件时，所有子 Tab 内容均不可编辑。

#### 验收标准

1. WHEN A16_Bundle 的 readonly prop 为 true 时，THE A16_Bundle SHALL 将 readonly 传递给所有 WorkpaperWordEditor 子组件
