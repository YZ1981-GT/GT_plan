# Requirements Document

> C2~C15 业务循环控制测试组件翻新（按真实模板结构重做）

## Introduction

已归档的 `c-control-test-component`（`c-control-test` componentType）以抽象「控制点卡片 + 偏差率计算」模型实现 C2~C15 控制测试，但与致同 2025 修订版源模板的真实结构不一致。经源模板实读，C2~C15 每个循环的真实结构为：

- **底稿目录**（导航 + 项目信息 F3~F8）
- **Cx 控制测试汇总表**（子流程 / 控制编号 / 控制名称 / 详细控制描述 / 受影响的交易账户余额和披露 / 认定 / 控制属性 / 控制频率 / 与控制相关的风险 / 测试方法 / 范围(样本量) / 是否识别出偏差 / 整改期间 / 识别出的缺陷 / 索引号；含下拉选择 + 样本规模区间提示）
- **Cx-1-X 控制测试**（单个控制的测试底稿：基本信息 + 控制测试程序 + 总体定义 + 总体来源 + 样本规模 + 抽样方法 + 抽样过程 + 偏差定义 + 实施测试）
- **选项清单列表（不归档）**：下拉数据源
- **Cx-2 评价控制偏差**（独立文件，232 命名区域）：6 步偏差评价决策树（IF 公式驱动：控制例外 → 是否偏差 → 偏差性质 → 应对措施 → 扩大样本 → 缺陷评价→A14 → 设计缺陷 → 评价结论）

本 spec 翻新 `c-control-test` 组件内部结构以匹配真实模板：汇总表（控制清单）+ 逐控制测试子页（抽样）+ Cx-2 偏差评价决策树 + 目录导航 + 样本规模自动建议 + 缺陷联动 A14。14 循环（C2~C15）共用组件，通过 wpCode 区分。本 spec 取代（supersede）已归档的 `c-control-test-component`。

## Glossary

- **C_Control_Test**：翻新后的控制测试组件，沿用 componentType `c-control-test`
- **控制测试汇总表**：Cx 主 sheet，本循环全部被测控制点清单（15 列）
- **控制测试子页**：Cx-1-X，单个控制点的抽样测试底稿
- **偏差评价决策树**：Cx-2 的 6 步 IF 驱动流程，从控制例外推导控制有效/缺陷
- **样本规模区间**：按控制运行频率/总次数确定的最小样本规模（源模板提示表）
- **命名区域下拉**：源模板用命名区域作数据验证（认定/控制属性/控制频率/测试方法等）
- **偏差性质**：系统性偏差 / 人为有意偏差 / 随机性偏差
- **A14 缺陷底稿**：内部控制缺陷评价底稿（Cx-2 步骤五联动目标）
- **wpCode**：C2~C15，区分循环上下文
- **checklist_responses**：数据持久化表，item_id 前缀 `C{n}-`（n=2~15）
- **GtIndexChip**：跨底稿引用跳转 chip（prop 名 `value`）

## Requirements

### Requirement 1: 组件翻新与注册保持

**User Story:** 作为开发者，我希望 C2~C15 沿用 `c-control-test` componentType，但内部结构按真实模板翻新。

#### Acceptance Criteria

1. THE C_Control_Test SHALL 保持 componentType `c-control-test` 注册于 htmlRendererRegistry（contextProps standard）
2. THE wp_code_overrides SHALL 保持 C2~C15 映射为 `c-control-test`
3. THE C_Control_Test SHALL 接收标准 props（wpId/projectId/wpCode/year/readonly）并从 wpCode 提取循环编号 n（2~15）
4. THE C_Control_Test SHALL 以 sheetName v-if 分发内部各视图（目录/汇总表/控制测试子页/偏差评价）
5. THE 翻新 SHALL 兼容已有 `C{n}-` 前缀 checklist_responses 数据（不破坏历史数据）

### Requirement 2: 控制测试汇总表

**User Story:** 作为审计助理，我希望汇总表列示本循环全部被测控制点及其属性、测试方法与偏差状态。

#### Acceptance Criteria

1. THE C_Control_Test SHALL 以汇总表呈现控制点：子流程 / 控制编号 / 控制名称 / 详细控制描述 / 受影响交易账户余额披露 / 认定 / 控制属性 / 控制频率 / 与控制相关的风险 / 测试方法 / 范围(样本量) / 是否识别出偏差 / 整改期间 / 识别出的缺陷 / 索引号
2. THE C_Control_Test SHALL 为下拉字段（认定/控制属性/控制频率/测试方法/是否偏差）提供命名区域来源的下拉选项
3. THE C_Control_Test SHALL 支持动态增删控制点行（新增需先命名控制点）
4. WHEN 用户点击某控制点的索引号时，THE C_Control_Test SHALL 跳转到对应 Cx-1-X 控制测试子页

### Requirement 3: 样本规模自动建议

**User Story:** 作为现场经理，我希望系统按控制运行频率与总次数自动建议最小样本规模。

#### Acceptance Criteria

1. THE C_Control_Test SHALL 内置样本规模区间表（控制运行频率 × 控制运行总次数 → 最小样本规模区间）
2. WHEN 用户选择控制频率并录入运行总次数时，THE C_Control_Test SHALL 自动建议最小样本规模
3. THE C_Control_Test SHALL 允许用户在建议基础上手动调整实际样本量
4. THE 样本规模区间表 SHALL 以「方法论上下文」样式展示来源提示

### Requirement 4: 单控制测试子页

**User Story:** 作为审计助理，我希望为每个控制点记录抽样测试过程与结果。

#### Acceptance Criteria

1. THE C_Control_Test SHALL 为每个控制点提供 Cx-1-X 测试子页：基本信息（控制属性/频率/相关风险/测试方法）+ 控制测试程序 + 总体定义 + 总体来源 + 样本规模 + 抽样方法 + 抽样过程 + 偏差定义 + 实施测试（逐笔样本结果）
2. THE C_Control_Test SHALL 支持逐笔样本录入与结果记录，标记偏差
3. THE C_Control_Test SHALL 统计该控制点的偏差数并回填汇总表「是否识别出偏差」
4. THE 抽样过程 SHALL 支持引用抽样工具（IDEA 等）底稿索引（GtIndexChip）

### Requirement 5: Cx-2 偏差评价决策树

**User Story:** 作为现场经理，我希望以分步决策树评价控制偏差，自动推导控制有效或缺陷。

#### Acceptance Criteria

1. THE C_Control_Test SHALL 实现 Cx-2 六步偏差评价决策树：
   - 步骤一：控制例外是否属于控制偏差
   - 步骤二：偏差性质（系统性/人为有意/随机性）
   - 步骤三：随机性偏差的应对（扩大样本/直接认定缺陷）
   - 步骤四：扩大样本后是否发现新偏差
   - 步骤五：评价控制缺陷（联动 A14 缺陷底稿）
   - 步骤六：非偏差例外是否表明设计缺陷
2. THE C_Control_Test SHALL 按源模板 IF 逻辑根据每步选择自动推导下一步指引与最终评价结论
3. WHEN 决策树推导至「进入内部控制缺陷评价底稿」时，THE C_Control_Test SHALL 提供 GtIndexChip 跳转 A14
4. THE C_Control_Test SHALL 展示评价结论（控制有效 / 构成控制缺陷）
5. THE 决策树各步选择 SHALL 即时保存

### Requirement 6: 目录导航与循环上下文

**User Story:** 作为审计助理，我希望通过底稿目录在汇总表、各控制测试子页、偏差评价间快速导航。

#### Acceptance Criteria

1. THE C_Control_Test SHALL 提供目录导航视图，列示本循环的汇总表 + 各 Cx-1-X 控制测试 + Cx-2 偏差评价
2. THE C_Control_Test SHALL 根据 wpCode 显示对应循环名称（C2 销售 / C3 货币资金 / … / C15 关联方）
3. WHEN 用户点击目录项时，THE C_Control_Test SHALL 切换到对应视图
4. THE C_Control_Test SHALL 在顶部显示项目信息（客户名称/会计期间/编制人/复核人）

### Requirement 7: B23/B50 联动

**User Story:** 作为现场经理，我希望控制测试与 B23 控制了解、B50 风险评估联动。

#### Acceptance Criteria

1. THE C_Control_Test SHALL 提供 GtIndexChip 跳转 B23（本循环控制了解）与 B50（控制风险）
2. WHEN 汇总表整体识别出控制缺陷时，THE C_Control_Test SHALL 通过 EventBus 发布 `control:test-concluded` 事件（wpCode/cycleName/结论/缺陷摘要）
3. THE C_Control_Test SHALL 仅在结论实际变更时发布事件

### Requirement 8: 数据持久化、只读与 UI

**User Story:** 作为审计助理，我希望数据自动保存、UI 统一；作为复核合伙人，只读模式不可编辑。

#### Acceptance Criteria

1. THE C_Control_Test SHALL 将数据存储到 checklist_responses，使用 item_id 前缀 `C{n}-`（兼容历史数据）
2. WHEN 下拉/结论/决策树选择变更时，THE C_Control_Test SHALL 立即保存；文本字段 debounce 2 秒保存
3. THE C_Control_Test SHALL 通过 GET/PUT `/api/workpapers/{wp_id}/checklist-responses` 加载/保存
4. WHEN readonly 为 true 时，THE C_Control_Test SHALL 禁止所有编辑与行增删，仅浏览与跳转
5. THE 表格 SHALL 使用 13px 字体；说明/结论区 el-card 包裹；编制提示 details 折叠
6. WHEN 保存失败时，THE C_Control_Test SHALL 提示错误并保留本地编辑内容

### Requirement 9: 点选交互与操作提示

**User Story:** 作为审计助理，我希望 C2~C15 控制测试尽量点选完成，偏差评价决策树点选自动推进，并有操作提示。

#### Acceptance Criteria

1. THE C_Control_Test SHALL 将汇总表判断/枚举字段（认定、控制属性、控制频率、测试方法、是否识别出偏差）实现为命名区域来源的下拉/点选控件
2. THE C_Control_Test SHALL 将 Cx-1-X 样本结果（有效/偏差/不适用）实现为点选按钮，不需手打
3. THE C_Control_Test SHALL 将 Cx-2 六步偏差评价的每步选项实现为单选点选，点选后自动推进到下一步并显示指引
4. WHERE 字段为长文本（控制描述、偏差描述、评价说明），THE C_Control_Test SHALL 使用 autosize textarea + AI 辅助按钮
5. THE C_Control_Test SHALL 在顶部提供操作引导区（目录 → 汇总表控制清单 → 逐控制抽样测试 → 偏差评价）与样本规模区间方法论上下文
6. THE C_Control_Test SHALL 为公式/建议列（样本规模建议、决策树指引）提供 tooltip 说明来源

### Requirement 10: 附件上传与 OCR

**User Story:** 作为审计助理，我希望在控制测试样本处上传证据并 OCR 自动填充。

#### Acceptance Criteria

1. THE C_Control_Test SHALL 在 Cx-1-X 逐笔样本行提供 📎 附件上传列
2. WHEN 用户上传凭证/单据图片或 PDF 时，THE C_Control_Test SHALL 调用 OCR 识别关键字段并经确认弹窗 merge 填入样本行
3. IF OCR 失败，THEN THE C_Control_Test SHALL 提示手动填写并保留附件
4. THE 抽样过程 SHALL 支持 GtIndexChip 引用抽样工具（IDEA 等）底稿
5. THE 附件 SHALL 与样本 item_id 关联持久化，只读模式仅可查看

### Requirement 11: 一键联动与回写强化

**User Story:** 作为现场经理，我希望控制测试各环节一键联动完成，结论与缺陷自动回写。

#### Acceptance Criteria

1. WHEN 用户点击汇总表控制点索引号时，THE C_Control_Test SHALL 一键跳转对应 Cx-1-X 子页
2. WHEN Cx-1-X 子页样本存在偏差时，THE C_Control_Test SHALL 自动回填汇总表「是否识别出偏差=是」并联动 Cx-2 偏差评价入口
3. WHEN Cx-2 决策树推导至控制缺陷时，THE C_Control_Test SHALL 提供 GtIndexChip 一键跳转 A14 并带入缺陷摘要，同时回填汇总表「识别出的缺陷」
4. THE C_Control_Test SHALL 支持从 B23 一键引用本循环控制点生成汇总表行（减少手工录入）
5. WHEN 循环整体结论变更时，THE C_Control_Test SHALL 通过 EventBus 发布 `control:test-concluded` 至 B50
