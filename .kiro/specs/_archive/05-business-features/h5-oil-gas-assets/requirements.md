# Requirements Document: H5 油气资产底稿专属HTML精美组件

## 开发方法论（可复制到后续D~N循环spec）

### 双源输入流程

本spec的需求来源于两个权威数据源的交叉验证：

1. **源xlsx实读**（openpyxl脚本）：获取真实sheet结构（sheet名/列头/行数/公式/合并单元格/数据类型），产出结构化摘要。这是列头命名和公式逻辑的权威来源。
2. **底稿模板库md**（`BCD类底稿md/H固定资产循环底稿模板库.md`）：获取业务语义（审计目标/程序清单/联动关系/认定对应/交叉引用/适用性条件/核心必做清单）。这是业务逻辑和联动设计的权威来源。

冲突解决：列名/公式以xlsx为准（模板是最终交付物）；联动方向/认定映射/适用性规则以md为准（是方法论设计文档）。

### 功能方向（每个sheet组件必须考虑）

- **联动性**：跨sheet computed链 + 跨底稿EventBus + TB回写 + 折耗分摊联动
- **美观性**：分组配色(浅绿/浅蓝/浅紫) + 统计仪表板 + 进度条
- **跳转溯源**：GtIndexChip跳转 + tooltip显示数据来源 + 公式列虚线下划线
- **易操作**：引导步骤(蓝色渐变) + 方法论上下文(琥珀色左边线) + 编制提示折叠
- **导入导出**：el-dropdown三级(导出模板/导出数据/导入数据) + useH5ImportExport composable
- **AI辅助**：多section按区域(/ai-generate端点) + 弹确认预览再填入
- **双模式**：el-segmented(结构化视图/在线编辑) + OO健康检查降级
- **行业适用性**：applicable_when industry IN ['oil_gas','mining']

### 三件套产出规范

- requirements.md：每个功能域一个Requirement，Acceptance Criteria引用xlsx列头+md业务场景
- design.md：文件结构+composable接口+跨sheet数据流图+correctness properties
- tasks.md：按Phase0~7排序

## Introduction

H5油气资产底稿的专属HTML精美组件构建。将现有通用渲染升级为独立专属组件 `h5-oil-gas-assets`，覆盖来自 `H5 油气资产.xlsx` 的24个有效sheet。科目覆盖1611油气资产（借方/资产类）+ 累计折耗（贷方/备抵类）。

**H5核心特殊：行业特殊底稿**。仅石油/天然气/采矿行业适用（applicable_when控制）。折耗（非折旧）采用单位产量法为主（折耗=原值×当期产量÷预计总储量）。包含完整的资产监盘三阶段（H5-9计划/H5-10检查/H5-11小结）和折耗测算双分支（不含减值H5-12/含减值H5-12）。关键公式总数约200+。

## Glossary

- **Tab_Index**: 底稿目录，25行8列，sheet导航+进度统计
- **Procedure_Table_H5A**: 油气资产实质性程序表H5A，35行12列，审计程序清单（复用a-program-console）
- **Adjudication_H5_1**: 审定表H5-1，75行10列51公式，科目1611+累计折耗双区块
- **Disclosure_Listed**: 附注披露信息（上市公司），38行257列
- **Disclosure_SOE**: 附注披露信息（国有企业），24行253列
- **Detail_H5_2**: 明细表H5-2，53行54列12公式，按油气资产分类
- **Adjustment_H5_3**: 调整分录汇总H5-3，23行10列
- **Idle_Check_H5_4**: 闲置检查表H5-4，36行11列
- **Policy_Check_H5_5**: 会计政策会计估计检查表H5-5，46行16列
- **Analysis_H5_6**: 分析表H5-6，26行23列9公式
- **Addition_Check_H5_7**: 增加检查表H5-7，40行24列
- **Disposal_Check_H5_8**: 减少检查表H5-8，41行24列
- **Stocktake_Plan_H5_9**: 监盘计划H5-9，62行15列
- **Stocktake_Check_H5_10**: 盘点检查表H5-10，64行14列
- **Stocktake_Summary_H5_11**: 监盘小结H5-11，96行10列
- **Depletion_NoImpair_H5_12**: 折耗测算表（不含减值）H5-12，46行28列42公式
- **Depletion_WithImpair_H5_12**: 折耗测算表（含减值）H5-12，50行28列62公式
- **Depletion_Alloc_H5_13**: 折耗分配分析表H5-13，27行10列11公式
- **Impairment_H5_14**: 减值测算表H5-14，34行32列15公式
- **Recoverable_H5_15**: 可收回金额测试表H5-15，64行28列12公式
- **Title_Check_H5_16**: 权属检查表H5-16，91行21列
- **Related_Party_H5_17**: 关联交易检查表H5-17，102行16列
- **Operating_Lease_H5_18**: 经营租出油气资产检查表H5-18，96行17列
- **Finance_Lease_H5_19**: 融资租出油气资产检查表H5-19，125行20列
- **Cross_Sheet_Engine**: 跨sheet公式引擎，H5-1→H5-2/H5-12/H5-13/H5-14联动
- **Formula_Engine**: 前端公式引擎composable，资产类+折耗公式
- **Depletion_Engine**: 折耗计算引擎，单位产量法为主（折耗=原值×当期产量÷总储量）
- **Branch_Selector**: 分支选择器，H5-12两版本切换（不含减值/含减值）
- **Industry_Guard**: 行业适用性守卫，非oil_gas/mining行业禁止创建此底稿
- **Dynamic_Row**: 动态行
- **Summary_Row**: 合计行
- **Dual_Mode**: 双模式切换
- **EventBus**: 进程内事件总线
- **GtIndexChip**: 交叉索引跳转芯片
- **Review_Dialog**: 通用复核对话组件
- **AI_Assistant**: AI辅助生成
- **Trial_Balance_Writeback**: 审定数回写（科目1611+累计折耗）

## Requirements

### Requirement 1: 组件架构与sheetName分发（含行业适用性守卫）

**User Story:** As a 开发者, I want to H5油气资产底稿按sheetName prop分发到独立子组件且具有行业适用性控制, so that 24个sheet仅在oil_gas/mining行业项目中可用。

#### Acceptance Criteria

1. THE H5 组件 SHALL 注册新componentType: `h5-oil-gas-assets`，主入口为 GtH5OilGasAssets.vue
2. THE GtH5OilGasAssets.vue SHALL 接收 `sheetName` prop，用正则提取末尾编码(H5-1/H5-2/...)，v-if 分发到对应子组件；未迁移sheet走OnlyOffice fallback
3. THE H5 组件 SHALL 使用 defineAsyncComponent 对所有子组件（除H5TabIndex外）进行懒加载
4. THE H5 组件 SHALL 将子组件按功能域拆分为独立子目录：h5/core/、h5/inspection/、h5/stocktake/、h5/depletion/、h5/impairment/、h5/lease/
5. THE H5 组件 SHALL 拆分为composable层：useH5FormData.ts + useH5FormulaEngine.ts(纯函数) + useH5DepletionEngine.ts(纯函数) + useH5CrossSheet.ts + useH5DualMode.ts + useH5ImportExport.ts + sheet-specific composables
6. THE H5 组件 SHALL 在htmlRendererRegistry中注册'h5-oil-gas-assets'→GtH5OilGasAssets映射
7. THE H5 组件 SHALL 在wp_code_overrides.json中将H5/H5-1~H5-19/H5A映射为'h5-oil-gas-assets'
8. THE H5 组件 SHALL 在VALID_COMPONENT_TYPES中注册'h5-oil-gas-assets'
9. THE GtH5OilGasAssets.vue SHALL 支持selfLoad
10. THE H5 组件 SHALL 使用 checklist_responses 表存储数据，item_id前缀为"H5-{sheet编号}-{field}"格式
11. THE H5 组件 SHALL 实现行业适用性守卫：applicable_when industry IN ['oil_gas','mining']，非适用行业显示el-empty提示"本底稿仅适用于石油天然气/采矿行业"
12. THE 行业适用性 SHALL 在账套/项目设置中配置industry字段，前端通过project context读取

### Requirement 2: 审定表H5-1（双区块油气资产+累计折耗51公式）

**User Story:** As a 审计助理, I want to 在精美HTML表格中查看和编辑油气资产审定表, so that 我能清晰地看到油气资产原值+累计折耗双区块的审定数据。

#### Acceptance Criteria

1. THE Adjudication_H5_1 SHALL 渲染为双区块固定结构：一、油气资产-原值（资产分类行+小计）→ 二、累计折耗（资产分类行+小计）→ 油气资产净值合计
2. THE Adjudication_H5_1 SHALL 显示列：项目 | 期初余额 | 本期借方发生 | 本期贷方发生 | 期末余额 | 未审数 | AJE | RJE | 审定数
3. WHEN 用户编辑未审数/AJE/RJE时, THE Formula_Engine SHALL 自动计算审定数（=未审+AJE+RJE）
4. THE Formula_Engine SHALL 对原值区块校验：期末=期初+借方-贷方（资产类借方1611）
5. THE Formula_Engine SHALL 对累计折耗区块校验：期末=期初+贷方-借方（备抵类贷方）
6. THE Adjudication_H5_1 SHALL 自动计算净值合计（=原值小计-累计折耗小计）
7. WHEN 审定数发生变化时, THE Adjudication_H5_1 SHALL 回写trial_balance（科目1611+累计折耗）并发布'substantive:adjudicated'事件
8. THE Adjudication_H5_1 SHALL 与H5-2合计行交叉验证，不一致时黄色警告

### Requirement 3: 明细表H5-2 + 调整分录H5-3

**User Story:** As a 审计助理, I want to 管理油气资产明细和调整分录, so that 我能按资产分类查看变动并录入审计调整。

#### Acceptance Criteria

1. THE Detail_H5_2 SHALL 将54列拆分为3区段Tab：基础(资产分类/名称/油田/区块) | 原值变动(期初/增加/减少/期末) | 折耗(累计折耗期初/本期计提/转回/期末/净值)
2. THE Detail_H5_2 SHALL 自动计算：期末=期初+增加-减少；折耗期末=期初+计提-转回；净值=原值期末-折耗期末
3. THE Detail_H5_2 SHALL 支持动态行新增（ElMessageBox.prompt输入资产名称）+ 导入导出
4. THE Adjustment_H5_3 SHALL 显示10列+借贷平衡校验+EventBus发布
5. THE Adjustment_H5_3 SHALL 双向同步AJE/RJE到H5-1审定表

### Requirement 4: 闲置检查H5-4 + 会计政策H5-5 + 分析表H5-6

**User Story:** As a 审计助理, I want to 完成油气资产的闲置检查、政策合规和变动分析, so that 我能识别闲置资产并评估政策适当性。

#### Acceptance Criteria

1. THE Idle_Check_H5_4 SHALL 显示11列：序号 | 资产名称 | 油田 | 原值 | 净值 | 闲置原因 | 闲置起始日 | 处置计划 | 减值迹象 | 核查结论 | 备注
2. THE Policy_Check_H5_5 SHALL 以段落型渲染（CAS27石油天然气开采准则条款）+ 逐项合规勾选
3. THE Analysis_H5_6 SHALL 以OnlyOffice渲染（26行23列9公式，含结构分析+变动分析）
4. THE Analysis_H5_6 SHALL 提供HTML摘要视图（折耗率变动/净值率变动图表）

### Requirement 5: 增加检查H5-7 + 减少检查H5-8

**User Story:** As a 审计助理, I want to 检查本期油气资产的增减变动, so that 我能验证勘探开发支出资本化和资产处置的合规性。

#### Acceptance Criteria

1. THE Addition_Check_H5_7 SHALL 显示24列含：资产名称/油田区块/金额/资本化依据/勘探阶段/开发阶段/审批文件/抽凭结果
2. THE Addition_Check_H5_7 SHALL 支持行级抽凭（GtVoucherSamplingEngine）+ OCR
3. THE Disposal_Check_H5_8 SHALL 显示24列含：资产名称/处置原因/处置收入/净值/损益/审批/联动H10
4. THE Disposal_Check_H5_8 SHALL 对"处置"类项提供GtIndexChip跳转到H10资产处置损益
5. THE Addition_Check_H5_7 / Disposal_Check_H5_8 SHALL 支持动态行新增

### Requirement 6: 监盘三阶段（H5-9计划/H5-10检查/H5-11小结）

**User Story:** As a 审计助理, I want to 完成油气资产实物监盘的全流程, so that 我能确认油气设施的存在性和完整性。

#### Acceptance Criteria

1. THE Stocktake_Plan_H5_9 SHALL 显示15列：序号 | 盘点项目 | 油田 | 位置 | 账面原值 | 账面净值 | 盘点方式 | 盘点日期 | 负责人 | 样本量 | 抽样方法 | 预计耗时 | 注意事项 | 状态 | 备注
2. THE Stocktake_Check_H5_10 SHALL 显示14列含：盘点项目/账面数/实盘数/差异/状态/照片/GPS坐标
3. THE Stocktake_Summary_H5_11 SHALL 以叙述式渲染（96行10列）：盘点概况+差异分析+结论+建议
4. THE 监盘三阶段 SHALL 数据流联动：H5-9的样本列表→H5-10的盘点项→H5-11的差异汇总

### Requirement 7: 折耗测算H5-12（双分支：不含/含减值）+ 折耗分配H5-13

**User Story:** As a 审计助理, I want to 测算油气资产折耗并验证分配合理性, so that 我能确认单位产量法折耗计算正确且分配到相应成本中心。

#### Acceptance Criteria

1. THE H5-12 SHALL 提供分支选择器：el-segmented("不含减值"/"含减值")切换两版本
2. THE Depletion_NoImpair_H5_12 SHALL 以OnlyOffice渲染（46行28列42公式）
3. THE Depletion_WithImpair_H5_12 SHALL 以OnlyOffice渲染（50行28列62公式）
4. THE Depletion_Engine SHALL 实现单位产量法核心公式：月折耗=（原值-残值）×当期产量÷预计可采储量
5. THE Depletion_Alloc_H5_13 SHALL 以OnlyOffice渲染（折耗分配到各成本中心11公式）
6. THE 折耗测算 SHALL 与H5-1累计折耗区块本期计提金额交叉验证

### Requirement 8: 减值H5-14/H5-15 + 权属H5-16 + 关联H5-17 + 租赁H5-18/H5-19

**User Story:** As a 审计助理, I want to 完成油气资产的减值测试、权属核验、关联交易和租赁检查, so that 我能全面评估油气资产的计价和权利。

#### Acceptance Criteria

1. THE Impairment_H5_14 SHALL 以OnlyOffice渲染（34行32列15公式，含储量评估）
2. THE Recoverable_H5_15 SHALL 以OnlyOffice渲染（64行28列12公式，DCF+储量折现）
3. THE Title_Check_H5_16 SHALL 显示21列含：资产名称/采矿权证号/有效期/面积/登记机关/核查结论
4. THE Related_Party_H5_17 SHALL 显示16列+价差率自动计算+异常高亮
5. THE Operating_Lease_H5_18 SHALL 显示17列含：租出资产/承租方/租金/期限/租赁收益率
6. THE Finance_Lease_H5_19 SHALL 显示20列含：租出资产/承租方/本金/利息/到期日
7. THE Title_Check_H5_16 SHALL 对采矿权到期日<1年的资产黄色高亮预警

### Requirement 9: 折耗引擎（单位产量法+储量参数）

**User Story:** As a 开发者, I want to 实现油气资产折耗计算的纯函数引擎, so that 所有折耗相关公式可被PBT验证且可复用。

#### Acceptance Criteria

1. THE Depletion_Engine SHALL 实现 calcUnitDepletion(cost, salvage, production, reserves): 单位产量法折耗
2. THE Depletion_Engine SHALL 实现 calcDepletionRate(accDepletion, cost): 折耗率
3. THE Depletion_Engine SHALL 实现 calcRemainingReserves(totalReserves, accProduction): 剩余储量
4. THE Depletion_Engine SHALL 实现 calcNetValue(cost, accDepletion, impairment): 净值
5. THE Depletion_Engine SHALL 处理边界：储量为0时返回0（不除零）；产量>储量时折耗封顶为可折耗余额

### Requirement 10: 跨底稿联动

**User Story:** As a 审计助理, I want to H5油气资产与其他底稿正确联动, so that 折耗分摊和处置损益能自动同步。

#### Acceptance Criteria

1. THE H5 组件 SHALL 通过EventBus将折耗分配结果通知D5营业成本
2. THE H5 组件 SHALL 通过GtIndexChip+EventBus将处置项联动H10资产处置损益
3. THE H5 组件 SHALL subscribe TB更新以刷新H5-1取数
4. THE H5 组件 SHALL publish 'substantive:adjudicated'事件供附注订阅

### Requirement 11: 经营租出/融资租出检查表

**User Story:** As a 审计助理, I want to 检查油气资产的租赁情况, so that 我能验证租出资产的收益合理性和合规性。

#### Acceptance Criteria

1. THE Operating_Lease_H5_18 SHALL 计算租赁收益率=年租金收入/资产净值×100%
2. THE Finance_Lease_H5_19 SHALL 显示融资租出的本金摊销和利息确认
3. THE 租赁检查表 SHALL 支持动态行新增+导入导出

### Requirement 12: 行业适用性控制

**User Story:** As a 项目经理, I want to 非适用行业的项目不能使用H5底稿, so that 审计程序与被审计单位行业匹配。

#### Acceptance Criteria

1. THE Industry_Guard SHALL 在组件mount时检查project.industry是否IN ['oil_gas','mining']
2. WHEN 行业不匹配时, THE H5 SHALL 显示el-empty("本底稿仅适用于石油天然气/采矿行业项目")
3. THE 后端 SHALL 在创建H5底稿时校验行业适用性，不匹配返回400
