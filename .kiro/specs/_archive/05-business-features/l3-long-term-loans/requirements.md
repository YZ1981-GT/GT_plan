# Requirements Document: L3 长期借款底稿专属HTML精美组件

## 开发方法论（可复制到后续循环spec）

### 双源输入流程

1. **源xlsx实读**（openpyxl脚本）：获取真实sheet结构。列头命名和公式逻辑权威来源。
2. **底稿模板库md**（`BCD类底稿md/L筹资循环底稿模板库.md`）：获取业务语义。业务逻辑和联动设计权威来源。

冲突解决：列名/公式以xlsx为准；联动方向/认定映射以md为准。

### 功能方向

- **联动性**：跨sheet computed链 + **L3利息测算→L2应付利息/L8财务费用** + **一年内到期重分类→流动负债** + TB回写
- **美观性**：分组配色 + 统计仪表板 + 进度条
- **跳转溯源**：GtIndexChip + tooltip + 公式列虚线
- **易操作**：引导步骤 + 方法论上下文 + 编制提示
- **导入导出**：el-dropdown三级 + useL3ImportExport
- **AI辅助**：多section AI
- **双模式**：el-segmented + OO降级

### 三件套产出规范

- requirements.md / design.md / tasks.md 按Phase0~7

## Introduction

L3长期借款底稿的专属HTML精美组件构建。将现有通用渲染升级为独立专属组件 `l3-long-term-loans`，覆盖来自 `L3 长期借款.xlsx` 的14个有效sheet。科目覆盖2501长期借款（**贷方/负债类！**）。所有sheet合并到一个大Tab页签下（sheetName prop v-if分发）。

**L3核心特殊**：①**贷方负债类科目**（期末=期初+贷方-借方）②利息测算表（联动L2/L8）③征信报告核对④逾期贷款检查⑤抵质押资产检查⑥**一年内到期的长期借款重分类**（RJE重分类至流动负债）。关键公式总数约200+。整体同L1，增加长期分类逻辑。

## Glossary

- **Tab_Index**: 底稿目录
- **Procedure_Table_L3A**: 长期借款实质性程序表L3A（复用a-program-console）
- **Adjudication_L3_1**: 审定表L3-1，41×18，87公式，科目2501长期借款(贷方/负债)
- **Disclosure_Listed**: 附注披露信息（上市公司），25×12
- **Disclosure_SOE**: 附注披露信息（国有企业），26×8
- **Detail_L3_2**: 明细表L3-2，35×32，32公式，按借款/合同列示（含一年内到期标记）
- **Adjustment_L3_3**: 调整分录汇总L3-3（含重分类RJE）
- **Credit_Check_L3_4**: 征信报告核对表L3-4
- **Interest_Calc_L3_5**: 利息测算表L3-5，29×20，21公式（核心！联动L2/L8）
- **Contract_Check_L3_6**: 贷款合同检查L3-6
- **Overdue_Check_L3_7**: 逾期贷款检查表L3-7
- **Pledge_Check_L3_8**: 抵质押资产检查表L3-8
- **LTLoan_Check_L3_9**: 长期借款检查表L3-9
- **Cross_Sheet_Engine**: 跨sheet引擎 + L2/L8联动 + 重分类
- **Formula_Engine**: 前端公式引擎composable（负债类！贷方科目）
- **Interest_Engine**: 利息测算引擎（本金×利率×天数/365，核心纯函数）
- **Reclass_Engine**: 一年内到期重分类引擎（纯函数）
- **Trial_Balance_Writeback**: 审定数回写（科目2501）
- **EventBus**: 进程内事件总线
- **GtIndexChip**: 交叉索引跳转

## Requirements

### Requirement 1: 组件架构与sheetName分发

**User Story:** As a 开发者, I want to L3长期借款底稿按sheetName分发, so that 14个sheet在统一入口有序组织。

#### Acceptance Criteria

1. THE L3 组件 SHALL 注册新componentType: `l3-long-term-loans`，主入口为 GtL3LongTermLoans.vue
2. THE GtL3LongTermLoans.vue SHALL 接收 `sheetName` prop，正则提取编码(L3-1)，v-if分发
3. THE L3 组件 SHALL 使用 defineAsyncComponent 懒加载
4. THE L3 组件 SHALL 拆为：l3/core/（审定+明细+调整+附注）、l3/interest/（利息测算）、l3/inspection/（征信+合同+逾期+抵质押+检查表）
5. THE L3 组件 SHALL composable分层：useL3FormData + useL3FormulaEngine + useL3InterestEngine(纯函数) + useL3ReclassEngine(纯函数) + useL3CrossSheet + useL3DualMode + useL3ImportExport
6. THE L3 组件 SHALL 在htmlRendererRegistry中注册'l3-long-term-loans'
7. THE L3 组件 SHALL 在wp_code_overrides.json中将L3/L3-1~L3-9/L3A映射为'l3-long-term-loans'
8. THE L3 组件 SHALL 在VALID_COMPONENT_TYPES中注册'l3-long-term-loans'
9. THE GtL3LongTermLoans.vue SHALL 支持selfLoad
10. THE L3 组件 SHALL 使用 checklist_responses 表存储，item_id前缀"L3-{sheet}-{field}"
11. THE 未迁移sheet SHALL 走 OnlyOffice fallback

### Requirement 2: 审定表L3-1（负债类贷方科目）

**User Story:** As a 审计助理, I want to 在精美审定表中查看长期借款数据, so that 我能验证负债类科目的期末余额。

#### Acceptance Criteria

1. THE Adjudication_L3_1 SHALL 渲染为单区块：长期借款(贷方/负债，按借款类型分类+小计)，并单列显示"其中：一年内到期"
2. THE Adjudication_L3_1 SHALL 显示列：项目 | 期初 | 贷方发生(借入) | 借方发生(归还) | 期末 | 一年内到期 | 未审 | AJE | RJE | 审定
3. THE Formula_Engine SHALL 计算审定数=未审+AJE+RJE
4. THE Formula_Engine SHALL 校验负债类：**期末=期初+贷方-借方**
5. THE Adjudication_L3_1 SHALL 与L3-2明细合计交叉验证
6. WHEN 审定数变化时 SHALL 回写TB(2501)+发布'substantive:adjudicated'
7. THE Adjudication_L3_1 SHALL subscribe附注EventBus刷新

### Requirement 3: 明细表L3-2（按借款列示+一年内到期标记）

**User Story:** As a 审计助理, I want to 管理长期借款明细, so that 每笔借款可追溯且到期分类清晰。

#### Acceptance Criteria

1. THE Detail_L3_2 SHALL 显示列：借款银行 | 合同号 | 借款类型 | 起始日 | 到期日 | 年利率 | 期初余额 | 本期借入 | 本期归还 | 期末余额 | 一年内到期金额
2. THE Detail_L3_2 SHALL 自动计算：期末余额=期初+本期借入-本期归还（负债类）
3. THE Reclass_Engine SHALL 根据到期日与报告日判定一年内到期金额
4. THE Detail_L3_2 SHALL 32列宽表拆分：基础信息/金额变动/到期分类/担保信息区段Tab（行同步）
5. THE Detail_L3_2 SHALL 支持动态行新增+导入导出
6. THE Detail_L3_2 SHALL 与L3-5利息测算每笔借款一一对应

### Requirement 4: 利息测算表L3-5（核心！联动L2/L8）

**User Story:** As a 审计助理, I want to 验证长期借款利息测算, so that 我能确认应付利息和财务费用的准确性。

#### Acceptance Criteria

1. THE Interest_Calc_L3_5 SHALL 显示列：借款合同号 | 本金 | 年利率 | 计息起始日 | 计息天数 | 测算利息 | 账载利息 | 差异
2. THE Interest_Engine SHALL 实现：测算利息=本金×年利率×计息天数/365
3. THE Interest_Engine SHALL 实现差异=测算利息-账载利息
4. WHEN |差异|>阈值时 SHALL 红色高亮
5. THE Interest_Calc_L3_5 SHALL 合计测算利息 → EventBus publish 'l3:interest-calculated'（供L2/L8订阅）
6. THE Interest_Calc_L3_5 SHALL 通过cross_wp_ref关联L2应付利息、L8财务费用

### Requirement 5: 一年内到期重分类

**User Story:** As a 审计助理, I want to 系统自动识别一年内到期的长期借款并重分类, so that 流动/非流动分类正确。

#### Acceptance Criteria

1. THE Reclass_Engine SHALL calcCurrentPortion(dueDate, reportDate, amount): 判定一年内到期金额
2. THE L3 SHALL 生成重分类RJE：借长期借款/贷一年内到期的非流动负债
3. THE L3 SHALL 在审定表单列显示一年内到期合计
4. WHEN 存在一年内到期借款时 SHALL 提示生成重分类分录

### Requirement 6: 征信报告核对表L3-4

**User Story:** As a 审计助理, I want to 核对征信报告与账面长期借款, so that 银行借款完整性得到验证。

#### Acceptance Criteria

1. THE Credit_Check_L3_4 SHALL 显示列：授信银行 | 授信额度 | 已用额度 | 征信借款余额 | 账面借款余额 | 差异 | 差异说明
2. THE Credit_Check_L3_4 SHALL 自动计算差异=征信余额-账面余额
3. WHEN 差异≠0时 SHALL 红色高亮并要求填写差异说明
4. THE Credit_Check_L3_4 SHALL 与L3-2明细合计交叉验证
5. THE Credit_Check_L3_4 SHALL 叙述式结论区（textarea autosize + AI辅助）

### Requirement 7: 逾期贷款检查表L3-7 + 抵质押资产检查表L3-8

**User Story:** As a 审计助理, I want to 检查逾期贷款和抵质押资产, so that 借款风险和担保情况得到评价。

#### Acceptance Criteria

1. THE Overdue_Check_L3_7 SHALL 显示：借款合同号 | 到期日 | 报告日 | 逾期天数 | 逾期金额 | 是否展期 | 风险评价
2. THE Overdue_Check_L3_7 SHALL 自动计算逾期天数=报告日-到期日（>0为逾期）
3. WHEN 逾期天数>0时 SHALL 橙色/红色分级高亮
4. THE Pledge_Check_L3_8 SHALL 显示：抵质押资产 | 账面价值 | 担保借款 | 担保比例 | 权属核验
5. THE Pledge_Check_L3_8 SHALL 自动计算担保比例=担保借款/账面价值×100%

### Requirement 8: 贷款合同检查L3-6 + 检查表L3-9

**User Story:** As a 审计助理, I want to 检查贷款合同要素并完成长期借款检查表, so that 借款条款和整体审计结论完整。

#### Acceptance Criteria

1. THE Contract_Check_L3_6 SHALL 宽表按合同要素分区段Tab（基础/利率条款/担保条款/违约条款）
2. THE Contract_Check_L3_6 SHALL 支持行级OCR（📎列上传合同→POST contract-ocr→ElMessageBox确认→merge）
3. THE LTLoan_Check_L3_9 SHALL 提供核对清单+审计结论区（el-card包裹）
4. THE 检查表 SHALL 每个文本section标题行右侧放AI辅助按钮

### Requirement 9: 调整分录L3-3 + 附注

**User Story:** As a 审计助理, I want to 管理长期借款调整并生成附注, so that 审计调整有据可循且披露完整。

#### Acceptance Criteria

1. THE Adjustment_L3_3 SHALL 借贷平衡校验+EventBus+双向同步L3-1（含重分类RJE）
2. THE Disclosure_Listed/SOE SHALL 根据企业类型自动切换附注模板
3. THE 附注 SHALL subscribe 'substantive:adjudicated'刷新

### Requirement 10: 利息测算引擎+重分类引擎（纯函数）

**User Story:** As a 开发者, I want to 实现纯函数引擎, so that 利息计算和重分类可PBT验证。

#### Acceptance Criteria

1. THE Interest_Engine SHALL calcInterest(principal, annualRate, days): 利息=本金×年利率×天数/365
2. THE Interest_Engine SHALL calcOverdueDays / calcPledgeRatio
3. THE Reclass_Engine SHALL calcCurrentPortion(dueDate, reportDate, amount): 一年内到期金额
4. THE 引擎 SHALL 处理边界：天数为0利息=0；到期日在一年外时一年内到期=0

### Requirement 11: 跨底稿联动+集成能力

**User Story:** As a 项目经理, I want to L3联动L2/L8并集成标准能力, so that 与D~N底稿一致。

#### Acceptance Criteria

1. THE L3 SHALL 在L3-5利息测算完成后 publish 'l3:interest-calculated'
2. THE L3 SHALL 通过cross_wp_references关联L2、L8，ref_index chip可跳转
3. THE L3 SHALL 支持双模式 + 导入导出三级（useL3ImportExport，http带Authorization）
4. THE L3 SHALL 集成useVersionTrail(autoSnapshot) + provide openReviewDialog
