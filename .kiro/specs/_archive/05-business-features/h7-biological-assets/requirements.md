# Requirements Document: H7 生产性生物资产底稿专属HTML精美组件

## 开发方法论（可复制到后续D~N循环spec）

### 双源输入流程

本spec的需求来源于两个权威数据源的交叉验证：

1. **源xlsx实读**（openpyxl脚本）：获取真实sheet结构（sheet名/列头/行数/公式/合并单元格/数据类型），产出结构化摘要。这是列头命名和公式逻辑的权威来源。
2. **底稿模板库md**（`BCD类底稿md/H固定资产循环底稿模板库.md`）：获取业务语义（审计目标/程序清单/联动关系/认定对应/交叉引用/适用性条件/核心必做清单）。这是业务逻辑和联动设计的权威来源。

冲突解决：列名/公式以xlsx为准；联动方向/认定映射/适用性规则以md为准。

### 功能方向

- **联动性**：跨sheet computed链 + 跨底稿EventBus + TB回写 + 折旧分摊
- **美观性**：分组配色 + 统计仪表板 + 进度条
- **跳转溯源**：GtIndexChip跳转 + tooltip数据来源 + 公式列虚线下划线
- **易操作**：引导步骤 + 方法论上下文 + 编制提示折叠
- **导入导出**：el-dropdown三级 + useH7ImportExport composable
- **AI辅助**：多section AI生成
- **双/三模式**：el-segmented + OO降级
- **行业适用性**：applicable_when industry IN ['agriculture','forestry','livestock','fishery']
- **双计量模式**：成本模式/公允价值模式 measurement_model切换（类似H3）

### 三件套产出规范

- requirements.md / design.md / tasks.md 按Phase0~7

## Introduction

H7生产性生物资产底稿的专属HTML精美组件构建。将现有通用渲染升级为独立专属组件 `h7-biological-assets`，覆盖来自 `H7 生产性生物资产.xlsx` 的26个有效sheet。科目覆盖1621生产性生物资产（借方/资产类）+ 累计折旧（贷方/备抵类）。

**H7核心特殊**：①行业特殊底稿（农林牧渔行业适用）②双计量模式（成本/公允价值，类似H3）③H7-14产量记录表（H7独有）④监盘三阶段（实物盘点）⑤折旧测算双分支 ⑥公允价值复核表 ⑦互转审核表。关键公式总数约250+。

## Glossary

- **Tab_Index**: 底稿目录，28行8列
- **Procedure_Table_H7A**: 生物资产实质性程序表H7A，35行12列
- **Adjudication_Cost_H7_1**: 审定表（成本模式）H7-1，76行10列51公式
- **Adjudication_Fair_H7_1**: 审定表（公允价值模式）H7-1，78行10列51公式
- **Disclosure_Listed**: 附注披露信息（上市公司），64行257列
- **Disclosure_SOE**: 附注披露信息（国有企业），40行256列
- **Detail_Cost_H7_2**: 明细表（成本模式）H7-2，61行51列10公式
- **Detail_Fair_H7_2**: 明细表（公允价值模式）H7-2，57行47列21公式
- **Adjustment_H7_3**: 调整分录汇总H7-3，24行10列
- **Policy_Check_H7_4**: 会计政策估计检查表H7-4，53行16列
- **Analysis_H7_5**: 分析表H7-5，38行20列9公式
- **Addition_Cost_H7_6**: 增加检查表（成本模式）H7-6，51行22列
- **Addition_Fair_H7_6**: 增加检查表（公允价值模式）H7-6，40行21列
- **Disposal_Cost_H7_7**: 减少检查表（成本模式）H7-7，42行24列
- **Disposal_Fair_H7_7**: 减少检查表（公允价值模式）H7-7，33行25列
- **Stocktake_Plan_H7_8**: 监盘计划H7-8，64行15列
- **Stocktake_Check_H7_9**: 盘点检查表H7-9，66行17列
- **Stocktake_Summary_H7_10**: 监盘小结H7-10，100行10列
- **Depreciation_NoImpair_H7_11**: 折旧测算表（不含减值）-直线法H7-11，67行28列42公式
- **Depreciation_WithImpair_H7_11**: 折旧测算表（含减值）H7-11，54行28列62公式
- **Depreciation_Alloc_H7_12**: 折旧分配分析表H7-12，26行10列11公式
- **FairValue_Review_H7_13**: 公允价值复核表H7-13，61行13列12公式
- **Transfer_Review_H7_14**: 互转审核表H7-14，54行21列（生产性↔消耗性↔公益性）
- **Impairment_H7_15**: 减值测算表H7-15，54行34列15公式
- **Recoverable_H7_16**: 可收回金额测试表H7-16，99行28列12公式
- **Related_Party_H7_17**: 关联交易检查表H7-17，50行15列
- **Cross_Sheet_Engine**: 跨sheet引擎
- **Formula_Engine**: 前端公式引擎composable
- **Measurement_Model_Filter**: 计量模式过滤器（cost/fair_value）
- **Depreciation_Engine**: 折旧引擎（成本模式直线法为主）
- **Transfer_Engine**: 互转引擎（生产性↔消耗性↔公益性三方向）
- **Production_Record**: 产量记录（H7独有，产蛋/产奶/收割等）
- **Industry_Guard**: 行业适用性守卫
- **Branch_Selector**: H7-11折旧分支选择器
- **Dynamic_Row**: 动态行
- **Summary_Row**: 合计行
- **Dual_Mode**: 双模式切换
- **EventBus**: 进程内事件总线
- **GtIndexChip**: 交叉索引跳转
- **Review_Dialog**: 通用复核对话
- **AI_Assistant**: AI辅助生成
- **Trial_Balance_Writeback**: 审定数回写（科目1621+累计折旧）

## Requirements

### Requirement 1: 组件架构与sheetName分发（含行业守卫+measurement_model）

**User Story:** As a 开发者, I want to H7生产性生物资产底稿按sheetName prop分发且具有行业适用性和双计量模式控制, so that 26个sheet仅在农林牧渔项目中可用且成本/公允模式各自显隐。

#### Acceptance Criteria

1. THE H7 组件 SHALL 注册新componentType: `h7-biological-assets`，主入口为 GtH7BiologicalAssets.vue
2. THE GtH7BiologicalAssets.vue SHALL 接收 `sheetName` prop，用正则提取编码(H7-1/H7-2/...)，v-if分发+双模式选择
3. THE H7 组件 SHALL 使用 defineAsyncComponent 懒加载
4. THE H7 组件 SHALL 将子组件拆为：h7/core/、h7/inspection/、h7/stocktake/、h7/depreciation/、h7/impairment/、h7/production/
5. THE H7 组件 SHALL composable分层：useH7FormData + useH7FormulaEngine + useH7DepreciationEngine + useH7TransferEngine + useH7CrossSheet + useH7MeasurementModel + useH7DualMode + useH7ImportExport + useH7IndustryGuard
6. THE H7 组件 SHALL 在htmlRendererRegistry中注册'h7-biological-assets'→GtH7BiologicalAssets映射
7. THE H7 组件 SHALL 在wp_code_overrides.json中将H7/H7-1~H7-17/H7A映射为'h7-biological-assets'
8. THE H7 组件 SHALL 在VALID_COMPONENT_TYPES中注册'h7-biological-assets'
9. THE GtH7BiologicalAssets.vue SHALL 支持selfLoad
10. THE H7 组件 SHALL 使用 checklist_responses 表存储，item_id前缀"H7-{sheet}-{field}"
11. THE H7 组件 SHALL 实现measurement_model切换：el-segmented("成本模式"/"公允价值模式")控制H7-1/H7-2/H7-6/H7-7双版本显隐
12. THE measurement_model切换 SHALL 幂等：两套数据独立存储，切换不丢失
13. THE H7 组件 SHALL 实现行业适用性守卫：applicable_when industry IN ['agriculture','forestry','livestock','fishery']
14. THE 行业不匹配时 SHALL 显示el-empty("本底稿仅适用于农林牧渔行业项目")

### Requirement 2: 审定表H7-1（双计量模式×双区块）

**User Story:** As a 审计助理, I want to 在精美HTML审定表中查看和编辑生物资产数据, so that 我能根据企业计量模式看到对应的审定表。

#### Acceptance Criteria

1. THE Adjudication_Cost_H7_1 SHALL 渲染为双区块：生产性生物资产-原值(分类+小计) + 累计折旧(分类+小计) + 净值合计
2. THE Adjudication_Fair_H7_1 SHALL 渲染为单区块：生产性生物资产(公允价值，无折旧)
3. THE Formula_Engine SHALL 计算审定数=未审+AJE+RJE
4. THE Formula_Engine SHALL 校验成本模式：原值期末=期初+借方-贷方；折旧期末=期初+贷方-借方
5. THE Formula_Engine SHALL 校验公允模式：期末=期初+增加-减少+公允变动
6. THE Adjudication_H7_1 SHALL 与H7-2合计交叉验证
7. WHEN 审定数变化时 SHALL 回写TB(1621+累计折旧)并发布'substantive:adjudicated'
8. THE Adjudication_H7_1 SHALL 显示审计说明+结论+复核入口

### Requirement 3: 明细表H7-2（双模式×宽表）

**User Story:** As a 审计助理, I want to 管理生物资产明细, so that 我能按成本/公允模式查看不同维度的资产变动。

#### Acceptance Criteria

1. THE Detail_Cost_H7_2 SHALL 将51列拆为3区段Tab：基础(分类/名称/数量/龄期) | 原值变动(期初/增加/减少/期末) | 折旧(期初/计提/转回/期末/净值)
2. THE Detail_Fair_H7_2 SHALL 将47列拆为3区段Tab：基础(分类/名称/数量) | 账面变动(期初/增加/减少) | 公允(期初公允/变动/期末公允)
3. THE 两套明细表 SHALL 独立存储，measurement_model切换后各自保留数据
4. THE Detail_H7_2 SHALL 支持动态行新增+导入导出+合计行

### Requirement 4: 调整分录H7-3 + 会计政策H7-4 + 分析表H7-5

**User Story:** As a 审计助理, I want to 管理调整分录、评估政策合规、分析变动, so that 审计调整和政策评价有据可循。

#### Acceptance Criteria

1. THE Adjustment_H7_3 SHALL 显示10列+借贷平衡+EventBus+双向同步H7-1
2. THE Policy_Check_H7_4 SHALL 以段落型渲染（CAS5生物资产准则条款）+ 逐项合规勾选
3. THE Analysis_H7_5 SHALL 以OO渲染（38行20列9公式）+ HTML摘要视图
4. THE Policy_Check_H7_4 SHALL 包含计量模式选择合理性评价section

### Requirement 5: 增减检查表H7-6/H7-7（双模式）

**User Story:** As a 审计助理, I want to 检查本期生物资产的增减变动, so that 我能验证新增购入/繁殖和处置/死亡的合规性。

#### Acceptance Criteria

1. THE Addition_Cost_H7_6 SHALL 显示22列含：资产名/数量/金额/来源(购入/繁殖/成熟转入)/凭证/抽凭结果
2. THE Addition_Fair_H7_6 SHALL 显示21列含：资产名/数量/公允价值/来源/评估依据
3. THE Disposal_Cost_H7_7 SHALL 显示24列含：资产名/处置原因(出售/死亡/淘汰/转出)/金额/审批
4. THE Disposal_Fair_H7_7 SHALL 显示25列含：资产名/处置原因/公允价值/变动损益
5. THE 增减检查表 SHALL 支持行级抽凭+OCR+动态行+与H7-2联动

### Requirement 6: 监盘三阶段H7-8/H7-9/H7-10

**User Story:** As a 审计助理, I want to 完成生物资产实物监盘, so that 我能确认活体资产的存在性和数量。

#### Acceptance Criteria

1. THE Stocktake_Plan_H7_8 SHALL 显示15列：盘点对象/种类/预计数量/盘点方式(逐头/抽样)/位置/日期/负责人
2. THE Stocktake_Check_H7_9 SHALL 显示17列含：盘点对象/账面数/实盘数/差异/健康状况/照片/备注
3. THE Stocktake_Summary_H7_10 SHALL 叙述式：盘点概况+差异分析+生物资产特殊说明(死亡/繁殖)+结论
4. THE 监盘 SHALL 数据流联动：H7-8样本→H7-9盘点→H7-10汇总

### Requirement 7: 折旧测算H7-11（双分支）+ 折旧分配H7-12

**User Story:** As a 审计助理, I want to 测算生物资产折旧并验证分配, so that 我能确认折旧计算正确且分配到对应成本。

#### Acceptance Criteria

1. THE H7-11 SHALL 提供分支选择器：el-segmented("不含减值-直线法"/"含减值")
2. THE Depreciation_NoImpair_H7_11 SHALL OO渲染（67行28列42公式）
3. THE Depreciation_WithImpair_H7_11 SHALL OO渲染（54行28列62公式）
4. THE Depreciation_Alloc_H7_12 SHALL OO渲染（26行10列11公式，分配到农业成本）
5. THE 折旧 SHALL 仅在成本模式下可见，公允模式显示提示"公允价值模式不计提折旧"
6. THE 折旧测算 SHALL 与H7-1累计折旧本期计提交叉验证

### Requirement 8: 公允价值复核H7-13 + 互转审核H7-14

**User Story:** As a 审计助理, I want to 复核公允价值评估和生物资产分类互转, so that 我能验证公允价值合理性和互转会计处理正确性。

#### Acceptance Criteria

1. THE FairValue_Review_H7_13 SHALL 显示13列：资产名/评估机构/评估方法/评估值/账面值/差异/差异率/复核结论
2. THE FairValue_Review_H7_13 SHALL 自动计算差异率=(评估值-账面值)/账面值×100%
3. THE Transfer_Review_H7_14 SHALL 显示21列含：资产名/转换方向(生产性→消耗性/公益性)/转出金额/转入金额/差额/审批
4. THE Transfer_Engine SHALL 计算三方向互转差额：转出金额-转入金额（应为0）
5. WHEN 互转差额≠0时 SHALL 红色高亮

### Requirement 9: 产量记录表（H7独有）

**User Story:** As a 审计助理, I want to 记录和验证生物资产的产出情况, so that 我能评估资产的生产能力和经济效益。

#### Acceptance Criteria

1. THE Production_Record SHALL 集成在H7-14互转审核表中或作为独立section
2. THE Production_Record SHALL 记录：资产名/产品类型(蛋/奶/果实/木材等)/计量单位/本期产量/上期产量/变动率/备注
3. THE Production_Record SHALL 自动计算变动率=(本期-上期)/上期×100%
4. WHEN 变动率绝对值>30%时 SHALL 黄色高亮提示需关注
5. THE Production_Record SHALL 支持动态行新增

### Requirement 10: 减值H7-15/H7-16 + 关联交易H7-17

**User Story:** As a 审计助理, I want to 完成减值测试和关联交易检查, so that 资产减值和关联交易得到充分审计。

#### Acceptance Criteria

1. THE Impairment_H7_15 SHALL OO渲染（54行34列15公式，仅成本模式）
2. THE Recoverable_H7_16 SHALL OO渲染（99行28列12公式，DCF）
3. THE Related_Party_H7_17 SHALL 显示15列+价差率自动计算+异常高亮
4. THE Related_Party_H7_17 SHALL 支持动态行+统计摘要

### Requirement 11: 折旧引擎（成本模式直线法）

**User Story:** As a 开发者, I want to 实现生物资产折旧的纯函数引擎, so that 折旧公式可PBT验证。

#### Acceptance Criteria

1. THE Depreciation_Engine SHALL calcStraightLine(cost, salvageRate, usefulLife): 年折旧
2. THE Depreciation_Engine SHALL calcMonthlyDep(annualDep): 月折旧
3. THE Depreciation_Engine SHALL calcDepAfterImpairment(netValue, salvageRate, remainLife): 减值后折旧
4. THE Depreciation_Engine SHALL calcAccDep(monthlyDep, months): 累计折旧

### Requirement 12: 跨底稿联动

**User Story:** As a 审计助理, I want to H7与其他底稿正确联动, so that 折旧分摊和附注自动同步。

#### Acceptance Criteria

1. THE H7 SHALL 通过EventBus将折旧分配通知D5营业成本
2. THE H7 SHALL subscribe TB更新刷新H7-1
3. THE H7 SHALL publish 'substantive:adjudicated'供附注订阅
4. THE H7 SHALL 处置项通过GtIndexChip联动H10

### Requirement 13: 行业适用性控制

**User Story:** As a 项目经理, I want to 非适用行业不能使用H7底稿, so that 审计程序与行业匹配。

#### Acceptance Criteria

1. THE Industry_Guard SHALL 检查project.industry IN ['agriculture','forestry','livestock','fishery']
2. WHEN 行业不匹配时 SHALL el-empty提示
3. THE 后端 SHALL 创建H7时校验行业，不匹配返回400

### Requirement 14: 双计量模式切换

**User Story:** As a 审计助理, I want to 在成本模式和公允价值模式间切换, so that 我能根据企业实际采用的计量模式查看对应sheet。

#### Acceptance Criteria

1. THE measurement_model切换 SHALL 控制H7-1/H7-2/H7-6/H7-7的双版本显隐
2. THE 成本模式 SHALL 可见：H7-1(成本)/H7-2(成本)/H7-6(成本)/H7-7(成本)/H7-11/H7-12/H7-15/H7-16
3. THE 公允模式 SHALL 可见：H7-1(公允)/H7-2(公允)/H7-6(公允)/H7-7(公允)/H7-13
4. THE 共用sheet SHALL 不受模式影响：H7-3/H7-4/H7-5/H7-8/H7-9/H7-10/H7-14/H7-17/附注
