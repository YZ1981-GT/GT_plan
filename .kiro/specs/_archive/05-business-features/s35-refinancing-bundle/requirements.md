# Requirements Document

> S35 再融资审核特项底稿聚合组件

## Introduction

S35 系列是上市公司再融资（增发、配股、可转债等）审核阶段的专项核查底稿，共 **5 个底稿**（S35-1~S35-5），覆盖关联交易、财务性投资核查、现金分红核查、商誉减值、募集资金涉及收购核查要点。每个底稿由「核查程序表」+「明细核查子表」（S35-1-1、S35-2-1、S35-3-1 等）构成，结构与 S34 首发审核底稿高度相似。

当前零散呈现于目录。本需求将其聚合为 `s35-refinance-bundle` 组件，内部以一行页签切换各再融资专项底稿，遵循 `s34-ipo-bundle` / `a17-bundle` 已验证的聚合模式，并复用带子表 Tab 的内部子 sheet 分发机制。

## Glossary

- **S35_Bundle**：聚合组件，componentType `s35-refinance-bundle`，内部分发渲染 S35-1~5 各再融资核查底稿
- **核查程序表**：S35-x 主 sheet，以 GtAProgramConsole 渲染的核查程序清单
- **明细核查子表**：S35-x-1 明细核查 sheet（如 S35-1-1 关联交易核查、S35-2-1 财务性投资核查）
- **wp_code_overrides**：底稿编码 → componentType 精确映射 JSON
- **htmlRendererRegistry**：前端 componentType → Vue 组件单一来源注册表
- **GtAProgramConsole**：审计程序表通用渲染中控台组件
- **GtIndexChip**：跨底稿引用跳转 chip（prop 名 `value`）
- **sheetName**：Tab 路由参数
- **useS35BundleState**：轻量 composable，管理子底稿 wp_id、适用性、完成状态
- **CompletionStatus**：`completed` / `in_progress` / `not_started`

## Requirements

### Requirement 1: 聚合入口组件注册

**User Story:** 作为审计助理，我希望点击 S35 打开统一聚合组件，在同一界面访问全部 5 个再融资核查底稿。

#### Acceptance Criteria

1. THE S35_Bundle SHALL 在 htmlRendererRegistry 中注册为 componentType `s35-refinance-bundle`，defineAsyncComponent 延迟加载
2. WHEN wp_code_overrides 中 S35 映射为 `s35-refinance-bundle` 时，THE 底稿渲染器 SHALL 加载并渲染 S35_Bundle
3. THE S35_Bundle SHALL 接收 props：`wpId`（必填）、`sheetName`（可选）、`readonly`（可选）
4. THE 系统 SHALL 在 VALID_COMPONENT_TYPES 中注册 `s35-refinance-bundle`，后端 validate_overrides 校验通过

### Requirement 2: 子底稿映射为 skip

**User Story:** 作为现场经理，我不希望 5 个再融资核查底稿及其子表在目录中重复显示为独立条目。

#### Acceptance Criteria

1. WHEN S35_Bundle 启用后，THE wp_code_overrides SHALL 将 S35-1~S35-5 及其子表编码（S35-1-1、S35-2-1、S35-3-1 等）全部映射为 `skip`
2. THE wp_code_overrides SHALL 将 S35 映射为 `s35-refinance-bundle`
3. WHEN 底稿目录加载时，THE 系统 SHALL 对 componentType 为 `skip` 的底稿不渲染为独立条目

### Requirement 3: 一行页签结构与渲染分发

**User Story:** 作为审计助理，我希望 5 个再融资核查底稿以一行页签组织，每个 Tab 内可切换核查程序表与明细核查子表。

#### Acceptance Criteria

1. THE S35_Bundle SHALL 以一行页签展示 5 个再融资核查底稿 Tab
2. WHEN 某底稿 Tab 被选中时，THE S35_Bundle SHALL 渲染 GtAProgramConsole 并传入对应子底稿 wp-id 与 `embedded=true`
3. WHERE 某底稿含明细核查子表 sheet（S35-x-1），THE S35_Bundle SHALL 在该 Tab 内以内部子 sheet 切换（v-if 分发）提供「核查程序表 / 明细核查表」视图
4. WHEN 程序行为空但存在网格数据时，THE GtAProgramConsole SHALL 以 GtGridSheet 只读兜底渲染

### Requirement 4: 明细核查子表渲染

**User Story:** 作为审计助理，我希望明细核查子表能填写并（如含公式）自动汇总，保留源模板的核查判断列。

#### Acceptance Criteria

1. THE 明细核查子表 SHALL 保留源模板的字段结构与核查判断列
2. WHERE 明细核查子表含公式，THE 子表 SHALL 保留公式语义并在前端实时重算，汇总单元格不可手工覆盖
3. WHERE 明细核查子表为动态明细行，THE 子表 SHALL 提供导入导出（导出模板/导出数据/导入数据）

### Requirement 5: Tab 路由与外部跳转

**User Story:** 作为审计助理，我希望从外部 RefChip / URL 直接定位到指定再融资核查底稿 Tab。

#### Acceptance Criteria

1. WHEN 外部通过 `navigate('S35', { sheet: 'S35-3' })` 跳转时，THE S35_Bundle SHALL 直接激活 `S35-3` Tab
2. WHEN URL query 含 `?sheet=S35-3` 时，THE S35_Bundle SHALL 解析并激活对应 Tab
3. WHEN props.sheetName 变更时，THE S35_Bundle SHALL 响应切换 Tab
4. IF sheetName 不在可见 Tab 列表中，THEN THE S35_Bundle SHALL 保持当前 Tab 不变

### Requirement 6: 子底稿 wp_id 解析与适用性

**User Story:** 作为现场经理，我希望仅项目实际适用的再融资核查底稿显示为可用 Tab。

#### Acceptance Criteria

1. THE useS35BundleState SHALL 通过 wp_index 查询获取 S35-1~5（及子表）的 wp_id 映射
2. IF 某核查底稿在当前项目 wp_index 中不存在，THEN THE S35_Bundle SHALL 隐藏或禁用对应 Tab
3. THE S35_Bundle SHALL 将解析到的 wp_id 传递给对应 GtAProgramConsole 与子表渲染
4. WHEN 项目无任何 S35 底稿时，THE S35_Bundle SHALL 显示空状态提示「本项目未启用再融资审核专项底稿」

### Requirement 7: 跨底稿引用 chip

**User Story:** 作为审计助理，我希望核查程序中引用的其他循环底稿以可点击 chip 呈现并跳转。

#### Acceptance Criteria

1. WHERE 核查程序表 / 子表的索引列包含其他底稿编码，THE S35_Bundle SHALL 以 GtIndexChip 呈现（prop 名 `value`）
2. WHEN 用户点击 S35 内部底稿 chip 时，THE S35_Bundle SHALL 切换到对应 Tab / 子 sheet
3. WHEN 用户点击外部底稿 chip 时，THE S35_Bundle SHALL 触发全局底稿跳转导航
4. IF 引用底稿在 wp_index 中不存在，THEN THE GtIndexChip SHALL 显示灰态并提示「底稿不存在」

### Requirement 8: 完成进度追踪与只读透传

**User Story:** 作为现场经理，我希望看到 5 个再融资核查底稿的整体完成进度；作为复核合伙人，我希望只读模式下全部不可编辑。

#### Acceptance Criteria

1. THE useS35BundleState SHALL 通过读取各底稿程序完成状态推导每个底稿的 CompletionStatus
2. THE S35_Bundle SHALL 在页签栏上方显示完成进度仪表盘（已完成/进行中/未开始 数量，三色指示）
3. WHEN 某底稿完成状态变化时，THE 仪表盘 SHALL 实时更新
4. WHEN S35_Bundle 的 readonly 为 true 时，THE S35_Bundle SHALL 将 readonly 传递给所有 GtAProgramConsole 与子表渲染
5. WHILE 只读模式时，THE 核查程序表与明细子表 SHALL 禁止编辑
