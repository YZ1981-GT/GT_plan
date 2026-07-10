# Requirements Document: H10 资产处置损益底稿专属HTML精美组件

## 开发方法论（可复制到后续D~N循环spec）

### 双源输入流程

本spec的需求来源于两个权威数据源的交叉验证：

1. **源xlsx实读**（openpyxl脚本）：获取真实sheet结构。
2. **底稿模板库md**（`BCD类底稿md/H固定资产循环底稿模板库.md`）：获取业务语义。

冲突解决：列名/公式以xlsx为准；联动方向/认定映射以md为准。

### 功能方向

- **联动性**：跨sheet computed链 + **H1~H8减少检查联动** + **H6固定资产清理联动** + TB取数
- **美观性**：分组配色 + 统计仪表板 + 进度条
- **跳转溯源**：GtIndexChip跳转 + tooltip + 公式列虚线
- **易操作**：引导步骤 + 方法论上下文 + 编制提示
- **导入导出**：el-dropdown三级 + useH10ImportExport
- **AI辅助**：多section AI
- **双模式**：el-segmented + OO降级

### 三件套产出规范

- requirements.md / design.md / tasks.md 按Phase0~7

## Introduction

H10资产处置损益底稿的专属HTML精美组件构建。将现有通用渲染升级为独立专属组件 `h10-asset-disposal-income`，覆盖来自 `H10 资产处置损益.xlsx` 的8个有效sheet。科目覆盖6115资产处置损益（**损益类/贷方科目**）。

**H10核心特殊**：①**损益类科目**！不是资产类！取发生额非余额 ②公式：审定=未审+AJE+RJE（相同）；但取数逻辑不同（发生额=借方发生+贷方发生的净额）③处置损益=处置收入-净值-处置费用 ④联动H1~H8所有底稿的减少检查 + H6固定资产清理 ⑤审定表69公式、明细表36列26公式。关键公式总数约100+。

## Glossary

- **Tab_Index**: 底稿目录，20行8列
- **Procedure_Table_H10A**: 资产处置损益实质性程序表H10A，21行21列
- **Adjudication_H10_1**: 审定表H10-1，20行11列69公式（！密度极高）
- **Disclosure_Listed**: 附注披露信息（上市公司），30行17列
- **Disclosure_SOE**: 附注披露信息（国企），22行5列
- **Detail_H10_2**: 明细表H10-2，36行26列26公式
- **Adjustment_H10_3**: 调整分录汇总H10-3，22行10列
- **Check_H10_4**: 检查表H10-4，80行20列（资产处置过程逐项检查）
- **Cross_Sheet_Engine**: 跨sheet引擎 + H1~H8跨底稿联动
- **Formula_Engine**: 前端公式引擎composable（**损益类！取发生额**）
- **Disposal_Calc_Engine**: 处置损益计算引擎（处置损益=收入-净值-费用）
- **Income_Statement_Rule**: 损益类取数规则：取发生额非余额
- **Dynamic_Row**: 动态行
- **Summary_Row**: 合计行
- **Dual_Mode**: 双模式切换
- **EventBus**: 进程内事件总线
- **GtIndexChip**: 交叉索引跳转
- **Review_Dialog**: 通用复核对话
- **AI_Assistant**: AI辅助生成
- **Trial_Balance_Writeback**: 审定数回写（科目6115，取发生额）

## Requirements

### Requirement 1: 组件架构与sheetName分发

**User Story:** As a 开发者, I want to H10资产处置损益底稿按sheetName分发, so that 8个sheet在统一入口有序组织。

#### Acceptance Criteria

1. THE H10 组件 SHALL 注册新componentType: `h10-asset-disposal-income`，主入口为 GtH10AssetDisposalIncome.vue
2. THE GtH10AssetDisposalIncome.vue SHALL 接收 `sheetName` prop，v-if分发
3. THE H10 组件 SHALL 使用 defineAsyncComponent 懒加载
4. THE H10 组件 SHALL 拆为：h10/core/（审定+明细+调整+附注）、h10/inspection/（检查表）
5. THE H10 组件 SHALL composable分层：useH10FormData + useH10FormulaEngine(纯函数) + useH10DisposalCalcEngine(纯函数) + useH10CrossSheet + useH10DualMode + useH10ImportExport
6. THE H10 组件 SHALL 在htmlRendererRegistry中注册'h10-asset-disposal-income'
7. THE H10 组件 SHALL 在wp_code_overrides.json中将H10/H10-1~H10-4/H10A映射为'h10-asset-disposal-income'
8. THE H10 组件 SHALL 在VALID_COMPONENT_TYPES中注册'h10-asset-disposal-income'
9. THE GtH10AssetDisposalIncome.vue SHALL 支持selfLoad
10. THE H10 组件 SHALL 使用 checklist_responses 存储，item_id前缀"H10-{sheet}-{field}"

### Requirement 2: 审定表H10-1（损益类！69公式，取发生额）

**User Story:** As a 审计助理, I want to 在精美审定表中查看资产处置损益, so that 我能验证各类资产处置损益的发生额和审定数。

#### Acceptance Criteria

1. THE Adjudication_H10_1 SHALL 渲染为：按资产类型分行（固定资产/无形资产/投资性房地产/使用权资产/生物资产/其他）+ 处置收入/处置成本(净值)/处置费用/处置损益
2. THE Adjudication_H10_1 SHALL 显示列：项目 | 本期借方发生 | 本期贷方发生 | 发生净额 | 未审数 | AJE | RJE | 审定数
3. THE Formula_Engine SHALL 计算：审定数=未审+AJE+RJE
4. THE Formula_Engine SHALL 使用**损益类取数规则**：取发生额（贷方发生-借方发生=净收益；借方发生-贷方发生=净损失），不取期末余额
5. THE Adjudication_H10_1 SHALL 计算处置损益=处置收入-资产净值-处置费用（汇总级）
6. THE Adjudication_H10_1 SHALL 与H10-2明细合计交叉验证
7. THE Adjudication_H10_1 SHALL 与H6固定资产清理净损益交叉验证（固定资产部分）
8. WHEN 审定数变化时 SHALL 回写trial_balance（科目6115，**注意取发生额**）+发布'substantive:adjudicated'
9. THE Adjudication_H10_1 SHALL 在底部显示审计说明+结论+复核入口
10. THE 审定表 SHALL 与H1-8/H2-9/H3-5/H5-8/H7-7/H8-12各减少检查的处置项金额交叉验证

### Requirement 3: 明细表H10-2（36列26公式）

**User Story:** As a 审计助理, I want to 管理资产处置损益明细, so that 每笔处置的收入/成本/损益可逐项核对。

#### Acceptance Criteria

1. THE Detail_H10_2 SHALL 将36列拆为3区段Tab：基础(序号/资产名称/资产类型/来源底稿/原值/累计折旧/净值) | 处置(处置原因/处置方式/处置收入/处置费用/税费/处置净损益) | 证据(审批文件/评估报告/合同/发票/核查结论/联动编号/备注)
2. THE Disposal_Calc_Engine SHALL 自动计算每行：净值=原值-累计折旧；处置净损益=处置收入-净值-处置费用-税费
3. THE Detail_H10_2 SHALL 对"来源底稿"列提供下拉（H1/H2/H3/H5/H7/H8/其他）+GtIndexChip跳转
4. THE Detail_H10_2 SHALL 合计行与H10-1审定表交叉验证
5. THE Detail_H10_2 SHALL 支持动态行新增（ElMessageBox.prompt输入资产名称）+导入导出
6. THE Detail_H10_2 SHALL 对处置净损益为负数(损失)的行标记红色背景
7. THE Detail_H10_2 SHALL 在底部统计：处置笔数/总收入/总损益/盈利笔数/亏损笔数

### Requirement 4: 调整分录H10-3 + 检查表H10-4

**User Story:** As a 审计助理, I want to 录入调整分录和完成处置过程检查, so that 审计调整和合规验证有据可循。

#### Acceptance Criteria

1. THE Adjustment_H10_3 SHALL 10列+借贷平衡+EventBus+双向同步H10-1
2. THE Check_H10_4 SHALL 显示20列含：处置项目/审批流程/评估依据/定价合理性/税务处理/会计处理时点/收入确认/费用归集/关联交易/核查结论
3. THE Check_H10_4 SHALL 对每项提供"合规/不合规/不适用"
4. WHEN 存在"不合规"项时 SHALL 红色摘要提示
5. THE Check_H10_4 SHALL 与H10-2明细行联动（每个检查对应一个处置项目）
6. THE Check_H10_4 SHALL 支持行级抽凭

### Requirement 5: 跨底稿联动（H1~H8减少检查+H6清理）

**User Story:** As a 审计助理, I want to H10与其他H循环底稿的处置项正确联动, so that 资产处置的全流程可从源头追溯。

#### Acceptance Criteria

1. THE H10 SHALL 通过GtIndexChip双向链接：H10-2每行↔来源底稿对应减少检查行
2. THE H10 SHALL subscribe H6的'disposal:completed'事件自动创建H10明细行
3. THE H10 SHALL subscribe H1/H2/H3/H5/H7/H8的处置事件更新来源数据
4. THE H10-2 SHALL 对每笔处置显示来源追溯链：源底稿→H6清理(如适用)→H10确认
5. THE H10-1审定表 SHALL 按资产类型汇总与各源底稿减少合计交叉验证

### Requirement 6: 损益类科目特殊处理

**User Story:** As a 开发者, I want to 正确实现损益类科目的取数和计算逻辑, so that H10不会错误地取期末余额（应取发生额）。

#### Acceptance Criteria

1. THE Formula_Engine SHALL 实现损益类发生额公式：净发生额=贷方发生-借方发生（6115为贷方科目，贷方=收益/借方=损失）
2. THE TB取数 SHALL 从tb_ledger取发生额（非tb_balance期末余额），使用损益类专用取数逻辑
3. THE 审定数回写 SHALL 回写trial_balance.audited_amount为发生额（非余额）
4. THE Formula_Engine SHALL 区分：期末余额（资产/负债用）vs 发生额（损益用）

### Requirement 7: 处置损益计算引擎

**User Story:** As a 开发者, I want to 实现处置损益计算的纯函数引擎, so that 核心公式可PBT验证。

#### Acceptance Criteria

1. THE Disposal_Calc_Engine SHALL calcDisposalGainLoss(income, netValue, expenses, tax): 处置净损益
2. THE Disposal_Calc_Engine SHALL calcNetBookValue(cost, accDep): 净账面值
3. THE Disposal_Calc_Engine SHALL calcIncomeStatementNet(credit, debit): 损益净发生额(贷-借)
4. THE Disposal_Calc_Engine SHALL calcAuditedAmount(unadj, aje, rje): 审定=未审+AJE+RJE
5. THE Disposal_Calc_Engine SHALL calcSubtotal(arr): 合计
6. THE Disposal_Calc_Engine SHALL calcGainLossRate(gainLoss, cost): 处置损益率
