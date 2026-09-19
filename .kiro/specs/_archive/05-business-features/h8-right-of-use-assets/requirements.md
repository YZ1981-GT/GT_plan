# Requirements Document: H8 使用权资产底稿专属HTML精美组件

## 开发方法论（可复制到后续D~N循环spec）

### 双源输入流程

本spec的需求来源于两个权威数据源的交叉验证：

1. **源xlsx实读**（openpyxl脚本）：获取真实sheet结构。
2. **底稿模板库md**（`BCD类底稿md/H固定资产循环底稿模板库.md`）：获取业务语义。

冲突解决：列名/公式以xlsx为准；联动方向/认定映射以md为准。

### 功能方向

- **联动性**：跨sheet computed链 + 跨底稿EventBus + TB回写 + **H9租赁负债强联动**
- **美观性**：分组配色 + 统计仪表板 + 进度条
- **跳转溯源**：GtIndexChip跳转 + tooltip + 公式列虚线
- **易操作**：引导步骤 + 方法论上下文 + 编制提示
- **导入导出**：el-dropdown三级 + useH8ImportExport
- **AI辅助**：多section AI
- **双模式**：el-segmented + OO降级
- **CAS21**：新租赁准则核心，与H9配对

### 三件套产出规范

- requirements.md / design.md / tasks.md 按Phase0~7

## Introduction

H8使用权资产底稿的专属HTML精美组件构建。将现有通用渲染升级为独立专属组件 `h8-right-of-use-assets`，覆盖来自 `H8 使用权资产.xlsx` 的20个有效sheet。科目覆盖1901使用权资产（借方/资产类）+ 累计折旧（贷方/备抵类）。

**H8核心特殊**：①CAS21新租赁准则核心底稿 ②与H9租赁负债强联动（H8=H9初始计量+初始直接费用-租赁激励）③H8-6初始及后续计量有2个分支（按年/按月）④折旧测算双分支（不含/含减值）⑤租赁识别+租赁期确定+租赁变更三个判断性检查表 ⑥简化处理检查表（短期/低价值租赁豁免）。关键公式总数约250+。

## Glossary

- **Tab_Index**: 底稿目录，26行8列
- **Procedure_Table_H8A**: 使用权资产实质性程序表H8A，59行12列
- **Adjudication_H8_1**: 审定表H8-1，65行9列51公式，科目1901+累计折旧
- **Disclosure_Listed**: 附注披露信息（上市公司），48行7列
- **Disclosure_SOE**: 附注披露信息（国企），32行255列
- **Detail_H8_2**: 明细表H8-2，79行58列14公式
- **Adjustment_H8_3**: 调整分录汇总H8-3，24行10列
- **Lease_Identification_H8_4**: 租赁的识别H8-4，90行10列（判断是否为租赁）
- **Lease_Term_H8_5**: 租赁期的确定H8-5，52行8列（合理确定期限）
- **Measurement_Annual_H8_6**: 使用权资产初始及后续计量（按年）H8-6，59行13列9公式
- **Measurement_Monthly_H8_6**: 使用权资产初始及后续计量（按月）H8-6，361行16列
- **Lease_Modification_H8_7**: 租赁变更H8-7，100行11列（变更会计处理）
- **Depreciation_NoImpair_H8_8**: 折旧测算表（不含减值）H8-8，51行25列62公式
- **Depreciation_WithImpair_H8_8**: 折旧测算表（含减值）H8-8，49行27列86公式
- **Depreciation_Alloc_H8_9**: 折旧分配分析表H8-9，24行10列11公式
- **Impairment_H8_10**: 减值测算表H8-10，35行32列15公式
- **Recoverable_H8_11**: 可收回金额测试表H8-11，90行28列12公式
- **Disposal_Check_H8_12**: 减少检查表H8-12，39行28列（租赁终止/提前退租）
- **Simplified_Check_H8_13**: 简化处理的租赁检查表H8-13，99行18列12公式
- **Related_Party_H8_14**: 关联交易检查表H8-14，45行15列
- **Cross_Sheet_Engine**: 跨sheet引擎 + 跨底稿H9联动
- **Formula_Engine**: 前端公式引擎composable
- **CAS21_Engine**: CAS21租赁计量引擎（初始计量=H9+直接费用-激励）
- **Branch_Selector_H8_6**: H8-6计量分支（按年/按月）
- **Branch_Selector_H8_8**: H8-8折旧分支（不含/含减值）
- **Dynamic_Row**: 动态行
- **Summary_Row**: 合计行
- **Dual_Mode**: 双模式切换
- **EventBus**: 进程内事件总线
- **GtIndexChip**: 交叉索引跳转
- **Review_Dialog**: 通用复核对话
- **AI_Assistant**: AI辅助生成
- **Trial_Balance_Writeback**: 审定数回写（科目1901+累计折旧）
- **H9_Linkage**: H9租赁负债联动（初始计量核心公式）

## Requirements

### Requirement 1: 组件架构与sheetName分发（含H8-6/H8-8双分支）

**User Story:** As a 开发者, I want to H8使用权资产底稿按sheetName分发且支持两处分支选择, so that 20个sheet有序组织且H8-6/H8-8各有2个分支版本。

#### Acceptance Criteria

1. THE H8 组件 SHALL 注册新componentType: `h8-right-of-use-assets`，主入口为 GtH8RightOfUseAssets.vue
2. THE GtH8RightOfUseAssets.vue SHALL 接收 `sheetName` prop，v-if分发；H8-6和H8-8各有分支选择器
3. THE H8 组件 SHALL 使用 defineAsyncComponent 懒加载
4. THE H8 组件 SHALL 拆为：h8/core/、h8/lease-judgment/、h8/measurement/、h8/depreciation/、h8/impairment/、h8/inspection/
5. THE H8 组件 SHALL composable分层：useH8FormData + useH8FormulaEngine + useH8CAS21Engine(纯函数) + useH8CrossSheet + useH8DualMode + useH8ImportExport
6. THE H8 组件 SHALL 在htmlRendererRegistry中注册'h8-right-of-use-assets'
7. THE H8 组件 SHALL 在wp_code_overrides.json中将H8/H8-1~H8-14/H8A映射为'h8-right-of-use-assets'
8. THE H8 组件 SHALL 在VALID_COMPONENT_TYPES中注册'h8-right-of-use-assets'
9. THE GtH8RightOfUseAssets.vue SHALL 支持selfLoad
10. THE H8 组件 SHALL 使用 checklist_responses 表存储，item_id前缀"H8-{sheet}-{field}"

### Requirement 2: 审定表H8-1（使用权资产+累计折旧双区块）

**User Story:** As a 审计助理, I want to 在精美审定表中查看使用权资产数据, so that 我能验证CAS21下的使用权资产计量正确。

#### Acceptance Criteria

1. THE Adjudication_H8_1 SHALL 渲染双区块：使用权资产-原值(按租赁类型+小计) + 累计折旧(+小计) + 净值合计
2. THE Adjudication_H8_1 SHALL 显示列：项目 | 期初 | 借方 | 贷方 | 期末 | 未审 | AJE | RJE | 审定
3. THE Formula_Engine SHALL 计算审定数=未审+AJE+RJE
4. THE Formula_Engine SHALL 校验：原值期末=期初+借方-贷方；折旧期末=期初+贷方-借方
5. THE Adjudication_H8_1 SHALL 与H8-2合计交叉验证
6. THE Adjudication_H8_1 SHALL 与H9-1租赁负债审定表交叉验证（H8初始=H9+直接费用-激励）
7. WHEN 审定数变化时 SHALL 回写TB(1901+累计折旧)+发布'substantive:adjudicated'
8. THE Adjudication_H8_1 SHALL 显示审计说明+结论+复核入口

### Requirement 3: 明细表H8-2 + 调整分录H8-3

**User Story:** As a 审计助理, I want to 管理使用权资产明细和调整分录, so that 每笔租赁合同对应的使用权资产可追溯。

#### Acceptance Criteria

1. THE Detail_H8_2 SHALL 将58列拆为4区段Tab：基础(租赁合同号/承租资产/出租方/起始日/到期日) | 初始(H9初始+直接费用-激励=入账值) | 折旧(累计折旧/本期计提/期末净值) | 变更(租赁变更调整/终止日)
2. THE Detail_H8_2 SHALL 自动计算：入账值=H9初始计量+初始直接费用-租赁激励
3. THE Detail_H8_2 SHALL 支持动态行新增（ElMessageBox.prompt输入合同号）+导入导出
4. THE Adjustment_H8_3 SHALL 10列+借贷平衡+EventBus+双向同步H8-1

### Requirement 4: 租赁判断三检查表（H8-4识别/H8-5租赁期/H8-7变更）

**User Story:** As a 审计助理, I want to 完成租赁识别、租赁期确定和租赁变更的判断, so that CAS21下的租赁认定和期限确定有据可循。

#### Acceptance Criteria

1. THE Lease_Identification_H8_4 SHALL 以段落型渲染（90行10列）：逐项判断是否满足CAS21租赁定义（已识别资产+控制权+实质替换权）
2. THE Lease_Term_H8_5 SHALL 以段落型渲染（52行8列）：租赁期=不可撤销期+合理确定续租期-合理确定终止期
3. THE Lease_Modification_H8_7 SHALL 以表格型渲染（100行11列）：变更类型/原租赁条款/新条款/重新计量/会计处理
4. THE 三检查表 SHALL 每项结论为"是/否/不适用"+说明文本
5. THE Lease_Identification_H8_4 SHALL 与H8-2明细行联动：每份合同一次租赁识别判断

### Requirement 5: 初始及后续计量H8-6（按年/按月双分支）

**User Story:** As a 审计助理, I want to 验证使用权资产的初始和后续计量, so that 我能确认CAS21计量公式正确（H8=H9+直接费用-激励）。

#### Acceptance Criteria

1. THE H8-6 SHALL 提供分支选择器：el-segmented("按年计量"/"按月计量")
2. THE Measurement_Annual_H8_6 SHALL OO渲染（59行13列9公式，按年汇总）
3. THE Measurement_Monthly_H8_6 SHALL OO渲染（361行16列，按月逐期）
4. THE CAS21_Engine SHALL 实现核心公式：初始计量=租赁负债初始(H9)+初始直接费用-租赁激励
5. THE H8-6 SHALL 与H9摊销表交叉验证：H8初始计量中的租赁负债部分=H9-1初始确认金额
6. THE H8-6 SHALL 在顶部显示公式说明："使用权资产=租赁负债初始确认+初始直接费用-租赁激励"

### Requirement 6: 折旧测算H8-8（双分支）+ 折旧分配H8-9

**User Story:** As a 审计助理, I want to 测算使用权资产折旧, so that 我能确认折旧在租赁期内系统分摊。

#### Acceptance Criteria

1. THE H8-8 SHALL 提供分支选择器：el-segmented("不含减值"/"含减值")
2. THE Depreciation_NoImpair_H8_8 SHALL OO渲染（51行25列62公式）
3. THE Depreciation_WithImpair_H8_8 SHALL OO渲染（49行27列86公式）
4. THE Depreciation_Alloc_H8_9 SHALL OO渲染（24行10列11公式）
5. THE 折旧期 SHALL 为min(租赁期, 使用寿命)（CAS21规定）
6. THE 折旧测算 SHALL 与H8-1累计折旧本期计提交叉验证

### Requirement 7: 减值H8-10/H8-11 + 减少检查H8-12

**User Story:** As a 审计助理, I want to 完成使用权资产减值测试和租赁终止检查, so that 减值充分确认且提前退租正确处理。

#### Acceptance Criteria

1. THE Impairment_H8_10 SHALL OO渲染（35行32列15公式）
2. THE Recoverable_H8_11 SHALL OO渲染（90行28列12公式，DCF）
3. THE Disposal_Check_H8_12 SHALL 显示28列含：合同号/终止原因/终止日/剩余期/使用权净值/租赁负债余额/终止损益/审批
4. THE Disposal_Check_H8_12 SHALL 计算：终止损益=租赁负债余额-使用权资产净值
5. THE Disposal_Check_H8_12 SHALL 与H9同步：终止时租赁负债也应终止确认

### Requirement 8: 简化处理检查表H8-13（短期/低价值租赁）

**User Story:** As a 审计助理, I want to 检查简化处理的租赁是否符合CAS21豁免条件, so that 短期/低价值租赁的简化处理有据可查。

#### Acceptance Criteria

1. THE Simplified_Check_H8_13 SHALL 显示18列含：合同号/资产/出租方/租赁期/年租金/资产全新价值/是否短期(≤12月)/是否低价值(≤4万)/简化处理类型/费用确认/核查结论
2. THE Simplified_Check_H8_13 SHALL 自动判断：租赁期≤12月→短期租赁；资产全新价值≤40000→低价值
3. WHEN 既不满足短期又不满足低价值时 SHALL 红色高亮"不符合简化条件，应确认使用权资产"
4. THE Simplified_Check_H8_13 SHALL 在底部统计：简化处理笔数/总年租金/应转为使用权资产笔数

### Requirement 9: 关联交易H8-14 + 跨底稿联动

**User Story:** As a 审计助理, I want to 检查关联租赁并确保H8与H9正确联动, so that 关联租赁公允性和租赁配对完整性得到验证。

#### Acceptance Criteria

1. THE Related_Party_H8_14 SHALL 显示15列+关联租赁公允性评价+价差率
2. THE H8 SHALL 通过EventBus+GtIndexChip与H9租赁负债双向联动
3. THE H8 SHALL subscribe TB更新+publish adjudicated
4. THE H8-2每笔租赁 SHALL 可通过GtIndexChip跳转到H9对应摊销行

### Requirement 10: CAS21计量引擎

**User Story:** As a 开发者, I want to 实现CAS21使用权资产计量的纯函数引擎, so that 核心公式可PBT验证。

#### Acceptance Criteria

1. THE CAS21_Engine SHALL calcInitialMeasurement(leaseliability, directCost, incentive): H8=H9+直接-激励
2. THE CAS21_Engine SHALL calcDepreciationPeriod(leaseTerm, usefulLife): min(租赁期,寿命)
3. THE CAS21_Engine SHALL calcTerminationGainLoss(leaseliabilityBalance, rouNetValue): 终止损益
4. THE CAS21_Engine SHALL calcRemeasurement(oldROU, adjustment): 重新计量后使用权资产

### Requirement 11: H8-H9联动校验

**User Story:** As a 项目经理, I want to 系统自动验证H8使用权资产与H9租赁负债的一致性, so that CAS21配对底稿数据不出偏差。

#### Acceptance Criteria

1. THE H8 SHALL 在审定表底部显示"H8-H9联动校验"区域
2. THE 联动校验 SHALL 验证：H8初始-直接费用+激励 ≈ H9初始确认（允许尾差±1元）
3. WHEN 联动不一致时 SHALL 红色警告"H8与H9不一致，差额：xxx元，请检查"
4. THE H8-2每笔租赁合同 SHALL 与H9-2租赁负债明细一一对应
