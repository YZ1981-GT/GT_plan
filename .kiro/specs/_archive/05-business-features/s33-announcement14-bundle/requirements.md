# Requirements Document

> S33 应对 14 号公告提示风险核查程序聚合组件

## Introduction

S33 系列是应对《监管规则适用指引-发行类第 14 号公告》所提示风险的专项核查程序，共 **9 个底稿**（S33-1~S33-9），覆盖财务报告内部控制制度、财务与非财务信息印证、盈利异常增长和异常交易、关联方关系及其交易、收入及毛利率、主要客户和供应商、存货及其他资产、现金收付交易、财务异常信息。核心是通过财务与非财务信息的相互印证识别财务舞弊迹象。

每个底稿由「核查程序表」+「提示」构成，部分含隐藏程序表变体（如 S33-4 含 `程序表-隐`）。当前零散呈现于目录。本需求将其聚合为 `s33-ann14-bundle` 组件，内部以一行页签切换各核查底稿，遵循 `s34-ipo-bundle` / `a17-bundle` 已验证的聚合模式。

## Glossary

- **S33_Bundle**：聚合组件，componentType `s33-ann14-bundle`，内部分发渲染 S33-1~9 各核查底稿
- **核查程序表**：S33-x 主 sheet，以 GtAProgramConsole 渲染的核查程序清单
- **提示**：核查要点长文本 sheet
- **隐藏程序表变体**：如 S33-4 的 `S33-4(IB4)程序表-隐`，为默认隐藏的完整版程序表
- **wp_code_overrides**：底稿编码 → componentType 精确映射 JSON
- **htmlRendererRegistry**：前端 componentType → Vue 组件单一来源注册表
- **GtAProgramConsole**：审计程序表通用渲染中控台组件
- **GtIndexChip**：跨底稿引用跳转 chip（prop 名 `value`）
- **sheetName**：Tab 路由参数
- **useS33BundleState**：轻量 composable，管理子底稿 wp_id、适用性、完成状态
- **CompletionStatus**：`completed` / `in_progress` / `not_started`

## Requirements

### Requirement 1: 聚合入口组件注册

**User Story:** 作为审计助理，我希望点击 S33 打开统一聚合组件，在同一界面访问全部 9 个 14 号公告核查底稿。

#### Acceptance Criteria

1. THE S33_Bundle SHALL 在 htmlRendererRegistry 中注册为 componentType `s33-ann14-bundle`，defineAsyncComponent 延迟加载
2. WHEN wp_code_overrides 中 S33 映射为 `s33-ann14-bundle` 时，THE 底稿渲染器 SHALL 加载并渲染 S33_Bundle
3. THE S33_Bundle SHALL 接收 props：`wpId`（必填）、`sheetName`（可选）、`readonly`（可选）
4. THE 系统 SHALL 在 VALID_COMPONENT_TYPES 中注册 `s33-ann14-bundle`，后端 validate_overrides 校验通过

### Requirement 2: 子底稿映射为 skip

**User Story:** 作为现场经理，我不希望 9 个核查底稿在目录中重复显示为独立条目。

#### Acceptance Criteria

1. WHEN S33_Bundle 启用后，THE wp_code_overrides SHALL 将 S33-1~S33-9 全部编码映射为 `skip`
2. THE wp_code_overrides SHALL 将 S33 映射为 `s33-ann14-bundle`
3. WHEN 底稿目录加载时，THE 系统 SHALL 对 componentType 为 `skip` 的底稿不渲染为独立条目

### Requirement 3: 一行页签结构与渲染分发

**User Story:** 作为审计助理，我希望 9 个核查底稿以一行页签组织，每个 Tab 渲染对应的核查程序表。

#### Acceptance Criteria

1. THE S33_Bundle SHALL 以一行可滚动页签展示 9 个核查底稿 Tab
2. WHEN 某核查底稿 Tab 被选中时，THE S33_Bundle SHALL 渲染 GtAProgramConsole 并传入对应子底稿 wp-id 与 `embedded=true`
3. WHERE 某底稿含「提示」长文本 sheet，THE S33_Bundle SHALL 以顶部可折叠区块（details）嵌入呈现，不单独成 Tab
4. WHERE 某底稿含隐藏程序表变体（如 S33-4 程序表-隐），THE S33_Bundle SHALL 默认渲染可见版程序表，并提供切换到完整版的入口
5. WHEN 程序行为空但存在网格数据时，THE GtAProgramConsole SHALL 以 GtGridSheet 只读兜底渲染

### Requirement 4: Tab 路由与外部跳转

**User Story:** 作为审计助理，我希望从外部 RefChip / URL 直接定位到指定核查底稿 Tab。

#### Acceptance Criteria

1. WHEN 外部通过 `navigate('S33', { sheet: 'S33-5' })` 跳转时，THE S33_Bundle SHALL 直接激活 `S33-5` Tab
2. WHEN URL query 含 `?sheet=S33-5` 时，THE S33_Bundle SHALL 解析并激活对应 Tab
3. WHEN props.sheetName 变更时，THE S33_Bundle SHALL 响应切换 Tab
4. IF sheetName 不在可见 Tab 列表中，THEN THE S33_Bundle SHALL 保持当前 Tab 不变

### Requirement 5: 子底稿 wp_id 解析与适用性

**User Story:** 作为现场经理，我希望仅项目实际适用的核查底稿显示为可用 Tab。

#### Acceptance Criteria

1. THE useS33BundleState SHALL 通过 wp_index 查询获取 S33-1~9 的 wp_id 映射
2. IF 某核查底稿在当前项目 wp_index 中不存在，THEN THE S33_Bundle SHALL 隐藏或禁用对应 Tab
3. THE S33_Bundle SHALL 将解析到的 wp_id 传递给对应 GtAProgramConsole
4. WHEN 项目无任何 S33 底稿时，THE S33_Bundle SHALL 显示空状态提示「本项目未启用 14 号公告核查程序」

### Requirement 6: 跨底稿引用 chip

**User Story:** 作为审计助理，我希望核查程序中引用的其他循环底稿以可点击 chip 呈现并跳转。

#### Acceptance Criteria

1. WHERE 核查程序表的证据索引列包含其他底稿编码，THE S33_Bundle SHALL 以 GtIndexChip 呈现（prop 名 `value`）
2. WHEN 用户点击外部底稿 chip 时，THE S33_Bundle SHALL 触发全局底稿跳转导航
3. IF 引用底稿在 wp_index 中不存在，THEN THE GtIndexChip SHALL 显示灰态并提示「底稿不存在」

### Requirement 7: 完成进度追踪

**User Story:** 作为现场经理，我希望在组件顶部看到 9 个核查底稿的整体完成进度。

#### Acceptance Criteria

1. THE useS33BundleState SHALL 通过读取各底稿程序完成状态推导每个底稿的 CompletionStatus
2. THE S33_Bundle SHALL 在页签栏上方显示完成进度仪表盘（已完成/进行中/未开始 数量，三色指示）
3. WHEN 某底稿完成状态变化时，THE 仪表盘 SHALL 实时更新
4. WHEN 用户从某 Tab 切走时，THE useS33BundleState SHALL 刷新该底稿完成状态

### Requirement 8: 只读模式透传

**User Story:** 作为质量控制复核合伙人，我希望只读复核模式下所有核查底稿不可编辑。

#### Acceptance Criteria

1. WHEN S33_Bundle 的 readonly 为 true 时，THE S33_Bundle SHALL 将 readonly 传递给所有 GtAProgramConsole
2. WHILE 只读模式时，THE 核查程序表 SHALL 禁止程序裁剪、结论填写与附件上传
3. THE 提示区块 SHALL 在只读模式下仍可浏览
