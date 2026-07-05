# Requirements Document

> S34 首发审核（IPO）特项底稿聚合组件

## Introduction

S34 首发审核特项底稿是 IPO（首次公开发行并上市）审计项目的核心专项核查工具，共 **41 个底稿**（S34-0 核查事项清单 + S34-1~S34-41 各专项核查程序表）。它们针对证监会《监管规则适用指引-发行类第 4/5/9 号》、上交所/深交所发行上市审核业务指南、北交所业务规则适用指引提出的核查要求逐项厘定，覆盖股份支付、关联交易、研发资本化、资金流水、收入核查、对赌协议、涉农企业等 IPO 高频审核关注点。

当前这 41 个底稿在底稿目录中以独立条目零散呈现，缺乏统一入口和法规溯源导航。本需求将其聚合为单一 `s34-ipo-bundle` 组件（IPO 大组件），内部以**一行页签**（分组 + 可滚动 Tab）切换渲染各专项核查底稿，并以 S34-0 核查事项清单作为总览导航面板，驱动各专项底稿的适用性判断与法规溯源。

本组件遵循已验证的 `a17-bundle` 聚合模式（el-tabs 分发 + wp_index 解析子底稿 wp_id + 轻量 composable 管理跨 Tab 状态 + PBT），并复用 `GtAProgramConsole` 渲染各专项程序表、`GtIndexChip` 呈现跨底稿引用（D4/B23/C2 等）。

## Glossary

- **S34_Bundle**：聚合组件，对外暴露为单一 componentType `s34-ipo-bundle`，内部通过分组 Tab 分发渲染 S34-0 核查清单及 S34-1~41 各专项核查底稿
- **核查事项清单（S34-0）**：IPO 核查底稿总览表，将每个 S34-x 底稿映射到证监会/上交所/深交所/北交所对应监管条目，作为导航入口与适用性/法规溯源数据源
- **专项核查程序表**：S34-1~S34-41 中每个底稿的主 sheet（如 `S34-3程序表`），结构为「序号/程序/取得证据凭证/证据索引号/核查方式/审计程序索引」，以 `GtAProgramConsole` 渲染
- **专项子检查表**：部分 S34 底稿附带的带公式明细检查表（如 S34-16-1 第三方回款情况检查表、S34-2-1/2、S34-8-1/2、S34-25-1~3、S34-34-1/2、S34-4-1、S34-9-1、S34-11-1、S34-18-1、S34-20-1、S34-30-1），含 SUM/占比等公式与合理性/真实性核查列
- **wp_code_overrides**：底稿编码到 componentType 的精确映射 JSON（`backend/app/data/wp_code_overrides.json`）
- **htmlRendererRegistry**：前端 componentType → Vue 组件的单一来源注册表
- **GtAProgramConsole**：审计程序表通用渲染中控台组件（embedded 模式内嵌）
- **GtIndexChip**：跨底稿引用跳转 chip 组件（prop 名为 `value`）
- **GtGridSheet**：程序行为空时用于原样渲染只读表格的兜底组件
- **sheetName**：Tab 路由参数，用于外部 RefChip / URL query 直接定位到指定子 Tab
- **适用性**：某专项底稿是否在当前 IPO 项目中适用，由 wp_index 是否存在对应 wp_code + S34-0 清单勾选共同决定
- **useS34BundleState**：轻量 composable，管理子底稿 wp_id 映射、适用性、完成状态、法规溯源引用
- **完成状态（CompletionStatus）**：`completed`（已完成）/ `in_progress`（进行中）/ `not_started`（未开始）
- **法规溯源（RegRef）**：某 S34-x 底稿对应的证监会/上交所/深交所/北交所监管条目编号与名称
- **交易所类型（ExchangeType）**：项目上市板块（主板/科创板/创业板/北交所），决定适用的监管指引组合

## Requirements

### Requirement 1: 聚合入口组件注册

**User Story:** 作为审计助理，我希望在底稿目录点击 S34 时打开一个统一的 IPO 聚合组件，而非零散的 41 个独立条目，这样我可以在同一界面内访问所有首发审核专项底稿。

#### Acceptance Criteria

1. THE S34_Bundle SHALL 在 htmlRendererRegistry 中注册为 componentType `s34-ipo-bundle`，使用 defineAsyncComponent 延迟加载
2. WHEN wp_code_overrides 中 S34 的映射为 `s34-ipo-bundle` 时，THE 底稿渲染器 SHALL 加载并渲染 S34_Bundle 组件
3. THE S34_Bundle SHALL 接收 props：`wpId`（必填）、`sheetName`（可选，用于 Tab 路由）、`readonly`（可选）
4. THE S34_Bundle SHALL 使用 contextProps 策略 `standard`，由 GtWpRenderer 自动透传 wp-id、project-id、wp-code、year
5. THE 系统 SHALL 在 `VALID_COMPONENT_TYPES`（wp_classification_service.py）中注册 `s34-ipo-bundle`，且后端启动 `validate_overrides` 校验通过

### Requirement 2: 子底稿映射为 skip

**User Story:** 作为现场经理，我不希望 S34 的 41 个子底稿在底稿目录中重复显示为独立条目，因为它们已被聚合到 S34 bundle 内部 Tab 中。

#### Acceptance Criteria

1. WHEN S34_Bundle 启用后，THE wp_code_overrides SHALL 将 S34-0 及 S34-1~S34-41 全部编码映射为 `skip`
2. THE wp_code_overrides SHALL 将 S34 映射为 `s34-ipo-bundle`
3. WHEN 底稿目录加载时，THE 系统 SHALL 对 componentType 为 `skip` 的底稿不渲染为独立条目
4. THE skip 映射 SHALL 覆盖带子表的底稿的子 sheet 编码（如 S34-16-1、S34-2-1、S34-2-2、S34-8-1、S34-8-2、S34-25-1~3、S34-34-1、S34-34-2 等），避免其作为独立目录条目出现

### Requirement 3: 核查事项清单总览面板（S34-0）

**User Story:** 作为现场经理，我希望进入 S34 组件时首先看到核查事项清单总览，一屏掌握 41 个专项底稿的法规来源、适用状态与完成进度，快速决定本项目需执行哪些专项核查。

#### Acceptance Criteria

1. THE S34_Bundle SHALL 默认展示 `overview` 面板，渲染 S34-0 核查事项清单
2. THE overview 面板 SHALL 以表格呈现每个专项底稿的：底稿编号、名称、对应监管条目（证监会发行类 4/5/9 号 / 上交所 / 深交所 / 北交所）、适用状态、完成状态
3. WHEN 用户点击 overview 面板中某行的底稿名称时，THE S34_Bundle SHALL 切换到对应专项底稿的 Tab
4. THE overview 面板 SHALL 显示整体完成进度（已完成 / 进行中 / 未开始 / 不适用 的底稿数量统计）
5. WHERE 项目已设置交易所类型（主板/科创板/创业板/北交所），THE overview 面板 SHALL 高亮该板块适用的监管条目列

### Requirement 4: 分组页签结构与内部渲染分发

**User Story:** 作为审计助理，我希望 41 个专项底稿以一行分组页签清晰组织，可横向滚动切换，每个 Tab 渲染对应的专属程序表与子表，而不是拥挤到无法阅读。

#### Acceptance Criteria

1. THE S34_Bundle SHALL 以一行页签展示，含固定的 `overview`（核查清单）Tab 与各专项底稿 Tab
2. WHERE Tab 数量超过单行可视宽度，THE S34_Bundle SHALL 提供可滚动 / 分组下拉切换机制（el-tabs 的可滚动模式或按主题分组）
3. THE S34_Bundle SHALL 按业务主题对专项底稿分组（示例分组：股权与激励 [S34-2/3]、关联与共同投资 [S34-4/9]、收入与经销 [S34-16/19/20/21/35]、成本费用与研发 [S34-27/28/29/32]、资产与减值 [S34-5/6/8/31/33/40]、财务规范与内控 [S34-14/15/17/22/24/23]、资金与投资 [S34-10/25/36/37/39]、特殊事项 [S34-1/7/11/12/13/26/30/34/38/41]）
4. WHEN 某专项底稿 Tab 被选中时，THE S34_Bundle SHALL 渲染 GtAProgramConsole 并传入 `wp-id`（对应子底稿）和 `embedded=true`
5. WHEN 专项底稿的程序行为空但存在网格数据（非标准程序行结构）时，THE GtAProgramConsole SHALL 以 GtGridSheet 原样只读渲染兜底
6. THE 分组顺序 SHALL 以 S34-0 核查清单的底稿序号为基准可追溯

### Requirement 5: 专项子检查表渲染

**User Story:** 作为审计助理，我希望带明细检查表的专项底稿（如第三方回款、股份支付、涉农企业自然人客户）能在同一 Tab 内既看到核查程序、也能填写并自动汇总带公式的明细检查表。

#### Acceptance Criteria

1. WHERE 某专项底稿含子检查表 sheet（如 S34-16-1、S34-2-1/2、S34-8-1/2、S34-25-1~3、S34-34-1/2、S34-4-1、S34-9-1、S34-11-1、S34-18-1、S34-20-1、S34-30-1），THE S34_Bundle SHALL 在该底稿 Tab 内以内部子 sheet 切换（v-if 分发）同时提供「核查程序表」与「明细检查表」视图
2. THE 明细检查表 SHALL 保留源模板的公式语义（如 S34-16-1 的 `=SUM(E8:E18)`、第三方回款占营业收入比例 `=C24/C23`）并在前端实时重算
3. THE 明细检查表 SHALL 保留源模板的合理性/真实性核查列（如「代付原因是否合理/是否存在合规风险/交易实质是否一致」等判断列）
4. WHERE 明细检查表为动态明细行（可增删行），THE 子检查表 SHALL 提供导入导出（导出模板/导出数据/导入数据）
5. WHEN 明细检查表数据变更时，THE 汇总公式单元格 SHALL 自动重算且不可手工覆盖

### Requirement 6: 跨底稿引用 chip

**User Story:** 作为审计助理，我希望专项核查程序中引用的其他循环底稿（如 D4-24 收入、B23-1 控制、C2、S34-16-1）能以可点击 chip 呈现并跳转，减少手工查找。

#### Acceptance Criteria

1. WHERE 专项程序表的「取得证据凭证索引号」或「审计程序索引」列包含其他底稿编码（如 D4-24、B23-1/C2、S34-16-1），THE S34_Bundle SHALL 以 GtIndexChip 呈现该引用（prop 名为 `value`）
2. WHEN 用户点击指向 S34 内部底稿的 chip（如 S34-16-1）时，THE S34_Bundle SHALL 切换到对应 Tab / 子 sheet
3. WHEN 用户点击指向 S34 外部底稿的 chip（如 D4-24、B23-1）时，THE S34_Bundle SHALL 触发全局底稿跳转导航
4. IF 引用的底稿在当前项目 wp_index 中不存在，THEN THE GtIndexChip SHALL 显示为不可跳转的灰态并提示「底稿不存在」

### Requirement 7: Tab 路由与外部跳转

**User Story:** 作为审计助理，我希望从底稿目录或其他底稿的 RefChip 跳转时能直接定位到 S34 组件的特定专项底稿 Tab，而不是每次从核查清单开始。

#### Acceptance Criteria

1. WHEN 外部通过 `navigate('S34', { sheet: 'S34-3' })` 跳转时，THE S34_Bundle SHALL 直接激活 `S34-3` Tab
2. WHEN URL query 参数包含 `?sheet=S34-16` 时，THE S34_Bundle SHALL 解析该参数并激活对应 Tab
3. WHEN props.sheetName 变更时，THE S34_Bundle SHALL 响应并切换到对应 Tab
4. IF sheetName 指定的值不在可见 Tab 列表中，THEN THE S34_Bundle SHALL 保持当前 Tab 不变（默认为 overview）

### Requirement 8: 子底稿 wp_id 解析

**User Story:** 作为审计助理，我希望每个专项底稿 Tab 能正确加载对应子底稿的数据，而不是加载父底稿 S34 的数据。

#### Acceptance Criteria

1. THE S34_Bundle SHALL 通过项目 wp_index 查询获取各专项底稿（S34-0~S34-41）的 wp_id 映射
2. WHEN 组件挂载时，THE useS34BundleState SHALL 调用 API 获取当前项目下所有 S34 系列底稿的 wp_id 映射
3. IF 某专项底稿在当前项目中不存在（无 wp_id），THEN THE S34_Bundle SHALL 隐藏或禁用对应 Tab
4. THE S34_Bundle SHALL 将解析到的子底稿 wp_id 传递给对应的 GtAProgramConsole 及子检查表渲染

### Requirement 9: 适用性控制

**User Story:** 作为现场经理，我希望 S34 组件只突出显示本 IPO 项目实际适用的专项底稿，避免审计助理误填不相关的核查（如涉农企业底稿仅涉农项目适用）。

#### Acceptance Criteria

1. THE S34_Bundle SHALL 通过 wp_index 中是否存在对应 wp_code 的底稿判断某专项底稿是否适用（有 wp_id 即适用）
2. WHERE S34-0 核查清单中某底稿被标记为「不适用」，THE overview 面板 SHALL 在对应行呈现「不适用」状态并允许用户填写不适用理由
3. THE overview 面板 SHALL 支持按「仅显示适用」筛选，隐藏不适用的专项底稿 Tab
4. WHEN 项目无任何 S34 专项底稿存在时，THE S34_Bundle SHALL 仅显示 overview 面板并提示「本项目未启用首发审核专项底稿」

### Requirement 10: 完成进度追踪与仪表盘

**User Story:** 作为现场经理，我希望在 S34 组件顶部看到 41 个专项底稿的整体完成进度，快速了解 IPO 专项核查的推进情况。

#### Acceptance Criteria

1. THE useS34BundleState SHALL 通过读取各专项底稿的程序完成状态 / checklist_responses 推导每个底稿的完成状态（completed/in_progress/not_started）
2. THE S34_Bundle SHALL 在页签栏上方显示完成进度仪表盘，统计：已完成 / 进行中 / 未开始 / 不适用 的底稿数量
3. THE 仪表盘 SHALL 使用三色状态指示（绿=已完成、黄=进行中、灰=未开始）并联动 overview 面板各行状态
4. WHEN 某专项底稿完成状态发生变化时，THE 仪表盘 SHALL 实时更新对应统计
5. WHEN 用户从某 Tab 切走时，THE useS34BundleState SHALL 刷新该底稿完成状态（关键联动触发点）

### Requirement 11: 只读模式透传

**User Story:** 作为质量控制复核合伙人，我希望在只读复核模式下打开 S34 组件时，所有专项底稿与子检查表均不可编辑。

#### Acceptance Criteria

1. WHEN S34_Bundle 的 readonly prop 为 true 时，THE S34_Bundle SHALL 将 readonly 传递给所有 GtAProgramConsole 与子检查表渲染
2. WHILE 处于只读模式时，THE 专项程序表 SHALL 禁止程序裁剪、结论填写与附件上传
3. WHILE 处于只读模式时，THE 明细子检查表 SHALL 禁止增删行与单元格编辑
4. THE overview 面板 SHALL 在只读模式下仍可浏览与跳转，仅禁止不适用理由等填写

### Requirement 12: 法规溯源展示

**User Story:** 作为业务合伙人，我希望每个专项底稿能清晰展示其对应的监管条目来源（证监会/沪深北），便于向监管与复核方证明核查依据的完整覆盖。

#### Acceptance Criteria

1. THE useS34BundleState SHALL 从 S34-0 核查清单解析每个专项底稿的法规溯源（RegRef：证监会发行类 4/5/9 号 / 上交所指南 / 深交所指南 / 北交所指引 的条目编号与名称）
2. WHEN 某专项底稿 Tab 被选中时，THE S34_Bundle SHALL 在该底稿顶部以「方法论上下文」样式（琥珀色左边线区块）展示其法规溯源与核查目标
3. THE overview 面板 SHALL 支持按监管来源（证监会 / 上交所 / 深交所 / 北交所）分列展示条目覆盖情况
4. IF 某专项底稿在某交易所无对应条目，THEN THE overview 面板 SHALL 在该列显示空值而非报错
