# Requirements Document

> S 类交易/专家/检查型专项底稿专属组件（S1/S2/S4/S5/S6/S8/S9/S10/S11/S12/S13/S14/S16/S17）

## Introduction

本 spec 覆盖 S 类特定项目程序中 **14 个交易/专家/检查型专项底稿**，它们含审定表、内控调查表、判断性子表（商业实质/损益确认时点）、专家利用多分支及附注披露，需参照 D4 标准开发为**专属组件**（sheetName v-if 分发 + composable + TB 回写 + 附注联动 + GtIndexChip）：

- **S1 违反法规行为**：程序表 + S1-1 对法律法规的考虑记录表 + S1-2 沟通记录
- **S2 首次接受委托时对期初余额的审计**：程序表（首次承接场景）
- **S4 非货币性资产交换**：审定表（换入/换出/损益）+ S4-2 商业实质的判断（IF 公式）+ 附注（非经常性损益）
- **S5 债务重组**：审定表（债权人/债务人损益公式）+ S5-2 损益确认时点的判断 + 附注（非经常性损益）
- **S6 大股东及关联方资金占用和违规担保**：审定表 + 大型程序表 + 会计监管风险提示第 9 号参考
- **S8 租赁**：审定表 + 租赁核查程序
- **S9 对电子商务的考虑**：审定表 + 内部控制调查表 + 程序说明 + 法律法规
- **S10 对环境事项的考虑**：审定表 + 内控调查表 + 环境法规
- **S11 利用服务机构活动**：使用服务机构的考虑程序表
- **S12 利用专家（CPA 的专家）的工作**：程序表 + S12-1~3 多分支（通用/股份支付/金融工具公允价值）
- **S13 利用管理层的专家编制信息**：程序表 + S13-1~3 多分支（与 S12 对应）
- **S14 会计估计和相关披露**：程序表 + S14-1 了解环境 + S14-2 了解控制 + S14-3 应对风险 + S14-4 管理层偏向迹象
- **S16 套期活动**：套期活动核查程序
- **S17 非经常性损益**：非经常性损益明细（⚠️ 源模板为旧版 `.xls` 格式，需先转换为 `.xlsx` 或以 xlrd 读取）

## Glossary

- **专属组件**：以 sheetName prop 用 v-if 分发内部各 sheet 的 Vue 组件，不含内部 el-tabs（对齐 D4 标准）
- **审定表回写**：将审定金额写回 trial_balance（audited_amount，v2 正数口径）
- **内控调查表**：了解相关内部控制的检查表（S9-2/S10-2 等）
- **商业实质判断**：S4-2 以准则适用 + 现金流量显著不同的 IF 逻辑判断非货币性资产交换是否具有商业实质
- **损益确认时点**：S5-2 债务重组损益在破产重整/协议执行完毕等时点的确认判断
- **专家利用多分支**：S12/S13 的评价子表按被评价对象分为通用/股份支付/金融工具公允价值三类
- **非经常性损益**：非货币性资产交换损益、债务重组损益等需在附注标注的项目
- **componentType**：本 spec 为交易型底稿新增专属类型（如 `s4-nonmonetary-exchange`、`s5-debt-restructuring`、`s6-fund-occupation`、`s12-cpa-expert`、`s13-mgmt-expert`、`s14-accounting-estimate`），检查表型较简的底稿（S1/S2/S8/S9/S10/S11/S16/S17）以 `a-program-console` + 审定表渲染
- **GtIndexChip**：跨底稿引用跳转 chip（prop 名 `value`）
- **GtAProgramConsole**：审计程序表通用渲染中控台组件
- **导入导出三级**：导出模板 / 导出数据 / 导入数据

## Requirements

### Requirement 1: 专属组件与渲染分发注册

**User Story:** 作为审计助理，我希望交易型 S 类底稿打开各自专属组件、检查表型底稿以程序表中控台渲染，而非通用 univer/onlyoffice。

#### Acceptance Criteria

1. THE 系统 SHALL 为含审定表/判断子表/多分支的交易型底稿注册专属 componentType：`s4-nonmonetary-exchange`、`s5-debt-restructuring`、`s6-fund-occupation`、`s12-cpa-expert`、`s13-mgmt-expert`、`s14-accounting-estimate`
2. THE 系统 SHALL 将检查表型底稿（S1/S2/S8/S9/S10/S11/S16/S17）映射为 `a-program-console`，其审定表/内控调查表 sheet 通过内部子 sheet 渲染
3. THE 系统 SHALL 在 htmlRendererRegistry 与 VALID_COMPONENT_TYPES 注册上述专属 componentType，后端 validate_overrides 校验通过
4. THE 各专属组件 SHALL 具备 RENDERER_DISPATCH 后端注册，避免被 onlyoffice-sheet 兜底吞掉
5. THE 各专属组件 SHALL 接收 sheetName prop 并以 v-if 分发内部各 sheet（不含内部 el-tabs）

### Requirement 2: S4 非货币性资产交换审定与商业实质判断

**User Story:** 作为审计助理，我希望 S4 审定表按准则计算交换损益、S4-2 自动判断商业实质。

#### Acceptance Criteria

1. THE S4 审定表 SHALL 记录换入资产（成本确定方式/公允价值）、换出资产（账面价值/公允价值）与确认的损益
2. THE useS4FormulaEngine SHALL 按以公允价值计量的口径计算换出资产损益 = 换出公允价值 - 换出账面价值
3. THE S4-2 商业实质判断 SHALL 以 IF 逻辑判定是否适用非货币性资产交换准则（6 项排除情形全为「不属于」→ 适用）
4. THE S4-2 SHALL 判断是否具有商业实质（未来现金流量风险/时间/金额显著不同）
5. THE S4 组件 SHALL 在附注披露中标注该损益属于非经常性损益

### Requirement 3: S5 债务重组审定与损益确认时点

**User Story:** 作为审计助理，我希望 S5 审定表按债权人/债务人两视角计算债务重组损益、S5-2 判断损益确认时点。

#### Acceptance Criteria

1. THE S5 审定表 SHALL 分「作为债权人」与「作为债务人」两部分记录并计算债务重组利得（损失）
2. THE useS5FormulaEngine SHALL 按源模板公式计算债权人/债务人视角的重组损益
3. THE S5-2 损益确认时点判断 SHALL 记录审批日/协议生效日/债务豁免条件/是否可撤销/破产重整完成日等关键时点
4. THE S5-2 SHALL 提示不得在破产重整或债务重组方案实施的重大不确定性消除前提前确认债务重组收益
5. THE S5 组件 SHALL 在附注披露中标注该损益属于非经常性损益

### Requirement 4: S12/S13 专家利用多分支

**User Story:** 作为审计助理，我希望 S12/S13 的专家评价子表按被评价对象（通用/股份支付/金融工具公允价值）分支呈现。

#### Acceptance Criteria

1. THE S12 组件 SHALL 以 sheetName v-if 分发程序表 + S12-1 胜任能力评价 + S12-1-1 客观性评价 + S12-2 专长领域 + S12-3 工作恰当性 + S12-3-1~4 各分支子表
2. THE S13 组件 SHALL 以对应结构分发 S13 程序表 + S13-1~3 及 S13-3-1~4 各分支子表
3. WHERE 被评价领域为股份支付，THE 组件 SHALL 渲染股份支付专用评价子表（S12-3-3 / S13-3-3）
4. WHERE 被评价领域为金融工具公允价值，THE 组件 SHALL 渲染金融工具公允价值专用评价子表（S12-3-4 / S13-3-4）
5. THE 程序表 SHALL 保留「是否适用/执行人/执行情况说明/索引号」列结构

### Requirement 5: S14 会计估计程序与子表

**User Story:** 作为审计助理，我希望 S14 会计估计程序表与其 4 张子表（了解环境/了解控制/应对风险/管理层偏向迹象）联动呈现。

#### Acceptance Criteria

1. THE S14 组件 SHALL 以 sheetName v-if 分发 S14 程序表 + S14-1 了解环境 + S14-2 了解控制 + S14-3 应对风险 + S14-4 管理层偏向迹象
2. THE S14 程序表 SHALL 保留「是否适用/核查方式/执行人/执行情况说明/审计程序索引」列结构
3. THE S14 组件 SHALL 在程序步骤中以 GtIndexChip 呈现对 B10/B22/B40 等风险评估底稿的引用

### Requirement 6: S6 资金占用与违规担保审定

**User Story:** 作为审计助理，我希望 S6 审定表汇总大股东及关联方资金占用与违规担保情况，并可参考会计监管风险提示第 9 号。

#### Acceptance Criteria

1. THE S6 组件 SHALL 以 sheetName v-if 分发 S6-1 审定表 + S6 大型核查程序表
2. THE S6 组件 SHALL 将会计监管风险提示第 9 号内容以「方法论上下文」样式（琥珀色左边线区块）嵌入呈现
3. THE S6 审定表 SHALL 汇总资金占用/违规担保金额并支持回写试算表相关科目

### Requirement 7: 内控调查表型底稿（S9/S10）

**User Story:** 作为审计助理，我希望 S9/S10 的内控调查表与核查程序、审定表在同一组件内切换。

#### Acceptance Criteria

1. THE S9 组件 SHALL 以内部子 sheet 分发 对电子商务的考虑程序 + S9-1 审定表 + S9-2 内部控制调查表 + 程序说明 + 电子商务法律法规
2. THE S10 组件 SHALL 以内部子 sheet 分发 对环境事项的考虑程序 + S10-1 审定表 + S10-2 内控调查表 + 环境法规
3. WHERE 底稿含法律法规长文本 sheet，THE 组件 SHALL 以可折叠区块（details）或「方法论上下文」样式呈现，不占主视图

### Requirement 8: S17 旧格式转换

**User Story:** 作为开发者，我希望 S17 非经常性损益的旧版 `.xls` 源模板被正确读取并渲染，不因格式导致失败。

#### Acceptance Criteria

1. THE Phase0 分析 SHALL 将 S17 `.xls` 转换为 `.xlsx` 或以 xlrd 读取源结构
2. THE S17 组件 SHALL 呈现非经常性损益明细，并可与 S15/S20 等引用非经常性损益的底稿交叉勾稽
3. IF 源模板读取失败，THEN THE 系统 SHALL 给出明确错误而非静默兜底空数据

### Requirement 9: 审定表回写与附注联动

**User Story:** 作为审计助理，我希望含审定表的底稿能回写试算表、含附注的底稿能联动附注模块。

#### Acceptance Criteria

1. WHERE 底稿含审定表 sheet（S4/S5/S6/S8/S9/S10 等），THE 组件 SHALL 支持将审定金额回写 trial_balance 的 audited_amount（v2 正数口径）
2. THE 审定表 SHALL 通过 auto_data_source/resolver 自动取数，用户可 field_overrides 覆盖
3. WHEN 审定表保存时，THE 系统 SHALL 通过 EventBus 发布 WORKPAPER_SAVED 触发一致性检查，且 service 层仅 flush 不 commit
4. WHERE 底稿含附注披露（S4/S5 非经常性损益等），THE 组件 SHALL 提供披露文本区 + AI 辅助生成，并发布 `disclosure:note-text-updated`

### Requirement 10: 跨底稿引用 chip

**User Story:** 作为审计助理，我希望核查程序引用的其他底稿以可点击 chip 呈现并跳转。

#### Acceptance Criteria

1. WHERE 程序表/子表的索引列包含其他底稿编码，THE 组件 SHALL 以 GtIndexChip 呈现（prop 名 `value`）
2. WHEN 用户点击 chip 时，THE 组件 SHALL 触发全局底稿跳转导航
3. IF 引用底稿在 wp_index 中不存在，THEN THE GtIndexChip SHALL 显示灰态并提示「底稿不存在」

### Requirement 11: UI 规范、导入导出与只读

**User Story:** 作为审计助理，我希望这些底稿 UI 统一、判断列可溯源、动态明细可导入导出；作为复核合伙人，我希望只读模式下不可编辑。

#### Acceptance Criteria

1. THE 表格 SHALL 使用 13px 字体；判断/公式列以虚线下划线 + cursor:help + tooltip 展示来源或准则依据
2. THE 审计说明/结论区 SHALL 以 el-card 包裹，编制提示以 details 折叠置于底部；section 标题行右侧提供 AI 辅助按钮
3. WHERE 底稿含动态明细行，THE 组件 SHALL 提供 el-dropdown「导入导出▾」（复用 useXImportExport + 后端三端点 + http/axios）
4. WHEN readonly 为 true 时，THE 组件 SHALL 禁止所有输入编辑与明细行增删，仅允许浏览与跳转
5. THE 金额显示 SHALL 默认以「元」为单位并经统一格式化出口（fmt）
