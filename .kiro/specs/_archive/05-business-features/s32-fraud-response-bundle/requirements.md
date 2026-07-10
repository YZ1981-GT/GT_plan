# Requirements Document

> S32 应对 551 文提示风险核查程序聚合组件（财务造假/舞弊专项）

## Introduction

S32 系列是应对证监会《首发企业现场检查规定》相关 551 文所提示的财务造假、粉饰业绩风险的专项核查程序，共 **13 个底稿**（S32-1~S32-13），逐一针对 13 种典型舞弊情形：自我交易虚增利润、恶意串通提前确认收入、关联方代付成本费用、保荐机构/PE 利益输送、体外资金支付货款、互联网造假虚增收入、成本费用资本化、压缩员工薪金、延迟成本费用、资产减值估计不足、延迟资产转固减少折旧、其他粉饰业绩、期后业绩下滑。

每个底稿由「核查程序表（IC 程序表）」+「导引表（IC-0）」+「披露格式参考（IC-X）」+「提示」构成。当前零散呈现于底稿目录，缺乏统一的舞弊情形导航。本需求将其聚合为 `s32-fraud-bundle` 组件，内部以一行页签切换各舞弊情形核查底稿，遵循 `s34-ipo-bundle` / `a17-bundle` 已验证的聚合模式。

## Glossary

- **S32_Bundle**：聚合组件，componentType `s32-fraud-bundle`，内部分发渲染 S32-1~13 各舞弊情形核查底稿
- **舞弊情形（FraudScenario）**：13 种 551 文提示的财务造假/粉饰业绩情形，每种对应一个 S32-x 底稿
- **核查程序表（IC 程序表）**：S32-x 主 sheet，以 GtAProgramConsole 渲染的舞弊核查程序清单
- **导引表（IC-0）**：部分底稿的核查导引 sheet（如 IC6-0、IC9-0、IC10-0），指引核查思路
- **披露格式参考（IC-X）**：部分底稿附带的信息披露格式参考 sheet（如 IC6-X、IC9-X、IC10-X）
- **提示**：底稿内的核查要点长文本提示 sheet
- **wp_code_overrides**：底稿编码 → componentType 精确映射 JSON
- **htmlRendererRegistry**：前端 componentType → Vue 组件单一来源注册表
- **GtAProgramConsole**：审计程序表通用渲染中控台组件
- **GtIndexChip**：跨底稿引用跳转 chip（prop 名 `value`）
- **sheetName**：Tab 路由参数
- **useS32BundleState**：轻量 composable，管理子底稿 wp_id、适用性、完成状态
- **CompletionStatus**：`completed` / `in_progress` / `not_started`

## Requirements

### Requirement 1: 聚合入口组件注册

**User Story:** 作为审计助理，我希望点击 S32 打开统一的舞弊核查聚合组件，在同一界面按舞弊情形访问全部 13 个专项核查底稿。

#### Acceptance Criteria

1. THE S32_Bundle SHALL 在 htmlRendererRegistry 中注册为 componentType `s32-fraud-bundle`，使用 defineAsyncComponent 延迟加载
2. WHEN wp_code_overrides 中 S32 的映射为 `s32-fraud-bundle` 时，THE 底稿渲染器 SHALL 加载并渲染 S32_Bundle
3. THE S32_Bundle SHALL 接收 props：`wpId`（必填）、`sheetName`（可选）、`readonly`（可选）
4. THE 系统 SHALL 在 VALID_COMPONENT_TYPES 中注册 `s32-fraud-bundle`，且后端启动 validate_overrides 校验通过

### Requirement 2: 子底稿映射为 skip

**User Story:** 作为现场经理，我不希望 13 个舞弊核查底稿在目录中重复显示为独立条目。

#### Acceptance Criteria

1. WHEN S32_Bundle 启用后，THE wp_code_overrides SHALL 将 S32-1~S32-13 全部编码映射为 `skip`
2. THE wp_code_overrides SHALL 将 S32 映射为 `s32-fraud-bundle`
3. WHEN 底稿目录加载时，THE 系统 SHALL 对 componentType 为 `skip` 的底稿不渲染为独立条目

### Requirement 3: 舞弊情形一行页签结构与渲染分发

**User Story:** 作为审计助理，我希望 13 种舞弊情形以一行页签清晰组织，每个 Tab 渲染对应的核查程序表。

#### Acceptance Criteria

1. THE S32_Bundle SHALL 以一行可滚动页签展示 13 个舞弊情形 Tab，Tab 标签为舞弊情形简称
2. WHEN 某舞弊情形 Tab 被选中时，THE S32_Bundle SHALL 渲染 GtAProgramConsole 并传入对应子底稿 wp-id 与 `embedded=true`
3. WHERE 某底稿含导引表（IC-0）或披露格式参考（IC-X）sheet，THE S32_Bundle SHALL 在该 Tab 内以子 sheet 切换（v-if 分发）提供「核查程序 / 导引 / 披露格式参考」视图
4. WHERE 某底稿含「提示」长文本 sheet，THE S32_Bundle SHALL 以顶部可折叠区块（details）嵌入呈现，不单独成 Tab
5. WHEN 程序行为空但存在网格数据时，THE GtAProgramConsole SHALL 以 GtGridSheet 只读兜底渲染

### Requirement 4: Tab 路由与外部跳转

**User Story:** 作为审计助理，我希望从外部 RefChip / URL 直接定位到指定舞弊情形 Tab。

#### Acceptance Criteria

1. WHEN 外部通过 `navigate('S32', { sheet: 'S32-6' })` 跳转时，THE S32_Bundle SHALL 直接激活 `S32-6` Tab
2. WHEN URL query 含 `?sheet=S32-6` 时，THE S32_Bundle SHALL 解析并激活对应 Tab
3. WHEN props.sheetName 变更时，THE S32_Bundle SHALL 响应切换 Tab
4. IF sheetName 不在可见 Tab 列表中，THEN THE S32_Bundle SHALL 保持当前 Tab 不变

### Requirement 5: 子底稿 wp_id 解析与适用性

**User Story:** 作为现场经理，我希望仅项目实际适用的舞弊情形底稿显示为可用 Tab，避免无关情形干扰。

#### Acceptance Criteria

1. THE useS32BundleState SHALL 通过 wp_index 查询获取 S32-1~13 的 wp_id 映射
2. IF 某舞弊情形底稿在当前项目 wp_index 中不存在，THEN THE S32_Bundle SHALL 隐藏或禁用对应 Tab
3. THE S32_Bundle SHALL 将解析到的 wp_id 传递给对应 GtAProgramConsole
4. WHEN 项目无任何 S32 底稿时，THE S32_Bundle SHALL 显示空状态提示「本项目未启用 551 文舞弊核查程序」

### Requirement 6: 跨底稿引用 chip

**User Story:** 作为审计助理，我希望舞弊核查程序中引用的其他循环底稿以可点击 chip 呈现并跳转。

#### Acceptance Criteria

1. WHERE 核查程序表的证据索引列包含其他底稿编码，THE S32_Bundle SHALL 以 GtIndexChip 呈现（prop 名 `value`）
2. WHEN 用户点击外部底稿 chip 时，THE S32_Bundle SHALL 触发全局底稿跳转导航
3. IF 引用底稿在 wp_index 中不存在，THEN THE GtIndexChip SHALL 显示灰态并提示「底稿不存在」

### Requirement 7: 完成进度追踪

**User Story:** 作为现场经理，我希望在组件顶部看到 13 个舞弊核查底稿的整体完成进度。

#### Acceptance Criteria

1. THE useS32BundleState SHALL 通过读取各底稿程序完成状态推导每个底稿的 CompletionStatus
2. THE S32_Bundle SHALL 在页签栏上方显示完成进度仪表盘（已完成/进行中/未开始 数量，三色指示）
3. WHEN 某底稿完成状态变化时，THE 仪表盘 SHALL 实时更新
4. WHEN 用户从某 Tab 切走时，THE useS32BundleState SHALL 刷新该底稿完成状态

### Requirement 8: 只读模式透传

**User Story:** 作为质量控制复核合伙人，我希望只读复核模式下所有舞弊核查底稿不可编辑。

#### Acceptance Criteria

1. WHEN S32_Bundle 的 readonly 为 true 时，THE S32_Bundle SHALL 将 readonly 传递给所有 GtAProgramConsole
2. WHILE 只读模式时，THE 核查程序表 SHALL 禁止程序裁剪、结论填写与附件上传
3. THE 导引表 / 披露格式参考 / 提示 区块 SHALL 在只读模式下仍可浏览
