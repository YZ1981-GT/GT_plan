# Requirements Document

> C25/C26 专项控制测试专属组件（C25 利用内审工作 + C26 信息处理控制测试）

## Introduction

本 spec 覆盖两个 C 类专项控制底稿，各开发为专属组件（对齐 D4 标准）：

- **C25 利用内部审计工作**（2 sheets，219 命名区域下拉）：叙述式评估程序表（10 步评估内审工作的性质范围、胜任能力、可利用程度、重新执行程度），判断能否利用及利用程度
- **C26 信息处理控制测试**（1 sheet）：信息处理控制矩阵（按循环列示 IT 应用控制：控制类别 / 信息处理控制索引号 IT-R&R-xx / 测试目的 / 计划测试过程 / 穿行测试 / 控制测试 / 测试结果 / 客户反馈 / 结论 / 证据索引），关注信息处理四要素（完整性/准确性/授权/访问限制）

当前以通用渲染缺乏专属交互。本需求将两者升级为专属精美组件。

## Glossary

- **C25_Component**：利用内审工作组件，componentType `c25-internal-audit-reliance`
- **C26_Component**：信息处理控制测试组件，componentType `c26-info-processing-control`
- **内审利用评估**：C25 的 10 步评估（性质范围/胜任能力/客观性/工作质量/重新执行程度/利用结论）
- **信息处理控制矩阵**：C26 的应用控制清单，每条含穿行测试 + 控制测试 + 结论
- **信息处理四要素**：完整性 / 准确性 / 经过授权 / 访问限制
- **命名区域下拉**：源模板用命名区域作数据验证下拉（C25 达 219 个）
- **componentType**：本 spec 新增 2 个 —— `c25-internal-audit-reliance` / `c26-info-processing-control`
- **GtIndexChip**：跨底稿引用跳转 chip（prop 名 `value`）
- **checklist_responses**：数据持久化表，item_id 前缀 `C25-`/`C26-`

## Requirements

### Requirement 1: 组件注册

**User Story:** 作为开发者，我希望 C25/C26 打开时渲染各自专属组件。

#### Acceptance Criteria

1. THE 系统 SHALL 在 htmlRendererRegistry 注册 `c25-internal-audit-reliance` 与 `c26-info-processing-control`（defineAsyncComponent, contextProps standard）
2. THE wp_code_overrides SHALL 将 C25→`c25-internal-audit-reliance`、C26→`c26-info-processing-control`
3. THE 系统 SHALL 在 VALID_COMPONENT_TYPES 注册两类，后端 validate_overrides 校验通过
4. THE 两组件 SHALL 具备后端 RENDERER_DISPATCH 注册
5. THE 两组件 SHALL 接收标准 props（wpId/projectId/wpCode/year/readonly）

### Requirement 2: C25 内审利用评估程序

**User Story:** 作为审计助理，我希望 C25 以清晰的分步评估程序记录利用内审工作的判断。

#### Acceptance Criteria

1. THE C25_Component SHALL 呈现 10 步评估程序（序号/审计程序/是否适用/执行人/执行情况说明/索引号）
2. THE C25_Component SHALL 保留源模板命名区域下拉选项（是否适用/结论等）
3. THE C25_Component SHALL 为每步提供适用性标记与执行情况说明文本区
4. THE C25_Component SHALL 提供整体「能否利用内审工作及利用程度」结论区
5. THE 执行情况说明区 SHALL 提供 AI 辅助生成（section 标题右侧按钮）

### Requirement 3: C26 信息处理控制矩阵

**User Story:** 作为审计助理，我希望 C26 以矩阵记录各信息处理控制的穿行测试与控制测试。

#### Acceptance Criteria

1. THE C26_Component SHALL 以矩阵呈现信息处理控制：控制类别 / 信息处理控制索引号（IT-R&R-xx）/ 测试目的 / 计划测试过程 / 穿行测试 / 控制测试 / 测试结果 / 客户反馈 / 结论 / 证据索引
2. THE C26_Component SHALL 支持按循环（销售/采购/收入确认等）分组或筛选控制条目
3. THE C26_Component SHALL 支持动态增删控制条目行
4. THE C26_Component SHALL 标注每条控制对应的信息处理四要素（完整性/准确性/授权/访问限制）
5. THE 测试结果/结论文本区 SHALL 提供 AI 辅助生成

### Requirement 4: 方法论上下文提示

**User Story:** 作为审计助理，我希望 C26 顶部展示信息处理控制的填写说明与四要素方法论。

#### Acceptance Criteria

1. THE C26_Component SHALL 在顶部以「方法论上下文」样式（琥珀色左边线区块）展示源模板的填写说明（信息处理控制的性质、四要素含义）
2. THE C25_Component SHALL 在顶部展示利用内审工作的适用条件与判断要点

### Requirement 5: 跨底稿引用 chip

**User Story:** 作为审计助理，我希望证据索引/程序索引引用的其他底稿以可点击 chip 呈现并跳转。

#### Acceptance Criteria

1. WHERE 索引列包含其他底稿编码，THE 组件 SHALL 以 GtIndexChip 呈现（prop 名 `value`）
2. WHEN 用户点击 chip 时，THE 组件 SHALL 触发全局底稿跳转导航
3. IF 引用底稿在 wp_index 中不存在，THEN THE GtIndexChip SHALL 显示灰态并提示「底稿不存在」

### Requirement 6: 数据持久化

**User Story:** 作为审计助理，我希望所有数据自动保存。

#### Acceptance Criteria

1. THE 两组件 SHALL 将数据存储到 checklist_responses，使用 item_id 前缀 `C25-`/`C26-`（如 `C25-step-{n}-result`、`C26-ctrl-{m}-conclusion`）
2. WHEN 文本字段编辑停止 2 秒时，THE 组件 SHALL debounce 保存
3. WHEN 适用性/结论/四要素标记变更时，THE 组件 SHALL 立即保存
4. THE 组件 SHALL 通过 GET/PUT `/api/workpapers/{wp_id}/checklist-responses` 加载/保存
5. WHEN 保存失败时，THE 组件 SHALL 提示错误并保留本地编辑内容

### Requirement 7: 只读模式与 UI 规范

**User Story:** 作为复核合伙人，只读模式不可编辑；作为审计助理，UI 统一美观。

#### Acceptance Criteria

1. WHEN readonly 为 true 时，THE 组件 SHALL 禁止所有输入编辑与行增删，仅浏览与跳转
2. THE 表格 SHALL 使用 13px 字体
3. THE 说明/结论区 SHALL 以 el-card 包裹，编制提示以 details 折叠置于底部
4. THE 叙述式文本区 SHALL 使用 autosize textarea

### Requirement 8: 点选交互与操作提示

**User Story:** 作为审计助理，我希望 C25/C26 尽量点选完成，减少手工输入，并有操作提示。

#### Acceptance Criteria

1. THE C25_Component 与 C26_Component SHALL 将判断/枚举字段（是否适用、测试结论、信息处理四要素、控制类别）实现为下拉/单选/多选 tag 点选控件
2. WHERE 字段为长文本（执行情况说明、测试过程、结论），THE 组件 SHALL 使用 autosize textarea + AI 辅助按钮
3. THE 两组件 SHALL 在顶部提供操作引导区与源模板方法论上下文（琥珀色区块）
4. THE C26_Component SHALL 为信息处理控制索引号（IT-R&R-xx）提供 tooltip 展示控制目的
5. WHEN C26 控制条目按循环筛选时，THE C26_Component SHALL 通过点选循环标签切换视图而非手动过滤

### Requirement 9: 附件上传与 OCR

**User Story:** 作为审计助理，我希望在证据处上传附件，必要时 OCR 辅助识别。

#### Acceptance Criteria

1. THE C26_Component SHALL 在每条信息处理控制的证据索引处提供 📎 附件上传（穿行测试/控制测试证据）
2. THE C25_Component SHALL 在执行情况说明处提供 📎 附件上传（内审报告/底稿）
3. WHEN 上传可识别文档时，THE 组件 SHALL 调用 OCR 提取关键信息并经确认弹窗 merge，不直接覆盖
4. IF OCR 失败，THEN THE 组件 SHALL 提示手动填写并保留附件
5. THE 附件 SHALL 与对应 item_id 关联持久化，只读模式仅可查看

### Requirement 10: 联动跳转与回写

**User Story:** 作为现场经理，我希望 C25/C26 的结论与发现能联动相关底稿。

#### Acceptance Criteria

1. WHERE C26 信息处理控制识别缺陷，THE C26_Component SHALL 提供 GtIndexChip 一键跳转 A14/C21-1 并带入缺陷摘要
2. WHERE C25 利用内审工作结论影响审计范围，THE C25_Component SHALL 提供 GtIndexChip 跳转相关计划/风险底稿
3. THE 组件 SHALL 在证据索引/程序索引列以 GtIndexChip 支持一键跳转，引用不存在时灰态提示
