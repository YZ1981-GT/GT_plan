# Requirements Document: L1 短期借款底稿专属HTML精美组件

## 开发方法论（可复制到后续循环spec）

### 双源输入流程

本spec的需求来源于两个权威数据源的交叉验证：

1. **源xlsx实读**（openpyxl脚本）：获取真实sheet结构（sheet名/列头/行数/公式/合并单元格）。列头命名和公式逻辑的权威来源。
2. **底稿模板库md**（`BCD类底稿md/L筹资循环底稿模板库.md`）：获取业务语义（审计目标/程序清单/联动关系/认定对应）。业务逻辑和联动设计的权威来源。

冲突解决：列名/公式以xlsx为准；联动方向/认定映射/适用性规则以md为准。

### 功能方向（每个sheet组件必须考虑）

- **联动性**：跨sheet computed链 + 跨底稿EventBus（L1利息测算→L2应付利息/L8财务费用）+ TB回写
- **美观性**：分组配色(浅绿/浅蓝/浅紫) + 统计仪表板 + 进度条
- **跳转溯源**：GtIndexChip跳转 + tooltip显示数据来源 + 公式列虚线下划线
- **易操作**：引导步骤(蓝色渐变) + 方法论上下文(琥珀色左边线) + 编制提示折叠
- **导入导出**：el-dropdown三级(导出模板/导出数据/导入数据) + useL1ImportExport
- **AI辅助**：多section按区域(/ai-generate端点) + 弹确认预览再填入
- **双模式**：el-segmented(结构化视图/矩阵视图/在线编辑) + OO健康检查降级

### 三件套产出规范

- requirements.md：每个功能域一个Requirement，Acceptance Criteria引用xlsx列头+md业务场景
- design.md：文件结构+composable接口+跨sheet数据流图+ADR+correctness properties
- tasks.md：按Phase0(双源输入)~Phase7(测试)排序

## Introduction

L1短期借款底稿的专属HTML精美组件构建。将现有通用渲染升级为独立专属组件 `l1-short-term-loans`，覆盖来自 `L1 短期借款.xlsx` 的13个有效sheet。科目覆盖2001短期借款（**贷方/负债类！**）。所有sheet合并到一个大Tab页签下（sheetName prop v-if分发，外层GtWpRenderer提供目录行chips导航）。

**L1核心特殊**：①**贷方负债类科目**（期末=期初+贷方-借方，与资产类相反！与H9同款）②利息测算表（每笔借款利息=本金×利率×天数/365）③征信报告核对（银行借款与征信一致性）④逾期贷款检查⑤抵质押资产检查。关键公式总数约180+。L1利息测算结果联动L2应付利息、L8财务费用。

## Glossary

- **Tab_Index**: 底稿目录，sheet导航+进度统计
- **Procedure_Table_L1A**: 短期借款实质性程序表L1A（复用a-program-console）
- **Adjudication_L1_1**: 审定表L1-1，23×14，67公式，科目2001短期借款(贷方/负债)
- **Disclosure_Listed**: 附注披露信息（上市公司），24×12
- **Disclosure_SOE**: 附注披露信息（国有企业），24×8
- **Detail_L1_2**: 明细表L1-2，49×30，27公式，按借款银行/合同列示
- **Adjustment_L1_3**: 调整分录汇总L1-3，AJE/RJE管理
- **Credit_Check_L1_4**: 征信报告核对表L1-4，31×30，11公式
- **Interest_Calc_L1_5**: 利息测算表L1-5，29×20，21公式（核心！联动L2/L8）
- **Contract_Check_L1_6**: 贷款合同检查L1-6，23×32，14公式
- **Overdue_Check_L1_7**: 逾期贷款检查表L1-7，28×22，15公式
- **Pledge_Check_L1_8**: 抵质押资产检查表L1-8，19×17，11公式
- **STLoan_Check_L1_9**: 短期借款检查表L1-9
- **Cross_Sheet_Engine**: 跨sheet引擎 + L2/L8联动
- **Formula_Engine**: 前端公式引擎composable（负债类！贷方科目）
- **Interest_Engine**: 利息测算引擎（本金×利率×天数/365，核心纯函数）
- **Trial_Balance_Writeback**: 审定数回写（科目2001）
- **EventBus**: 进程内事件总线
- **GtIndexChip**: 交叉索引跳转

## Requirements

### Requirement 1: 组件架构与sheetName分发

**User Story:** As a 开发者, I want to L1短期借款底稿按sheetName分发, so that 13个sheet在统一入口有序组织。

#### Acceptance Criteria

1. THE L1 组件 SHALL 注册新componentType: `l1-short-term-loans`，主入口为 GtL1ShortTermLoans.vue
2. THE GtL1ShortTermLoans.vue SHALL 接收 `sheetName` prop，正则提取末尾编码(L1-1)，v-if分发到子组件
3. THE L1 组件 SHALL 使用 defineAsyncComponent 懒加载
4. THE L1 组件 SHALL 拆为：l1/core/（审定+明细+调整+附注）、l1/interest/（利息测算）、l1/inspection/（征信+合同+逾期+抵质押+检查表）
5. THE L1 组件 SHALL composable分层：useL1FormData + useL1FormulaEngine + useL1InterestEngine(纯函数) + useL1CrossSheet + useL1DualMode + useL1ImportExport
6. THE L1 组件 SHALL 在htmlRendererRegistry中注册'l1-short-term-loans'
7. THE L1 组件 SHALL 在wp_code_overrides.json中将L1/L1-1~L1-9/L1A映射为'l1-short-term-loans'
8. THE L1 组件 SHALL 在VALID_COMPONENT_TYPES中注册'l1-short-term-loans'
9. THE GtL1ShortTermLoans.vue SHALL 支持selfLoad（bundle内嵌htmlData为null场景）
10. THE L1 组件 SHALL 使用 checklist_responses 表存储，item_id前缀"L1-{sheet}-{field}"
11. THE 未迁移sheet SHALL 走 OnlyOffice fallback（GtOnlyOfficeSheet全高）

### Requirement 2: 审定表L1-1（负债类贷方科目）

**User Story:** As a 审计助理, I want to 在精美审定表中查看短期借款数据, so that 我能验证负债类科目的期末余额。

#### Acceptance Criteria

1. THE Adjudication_L1_1 SHALL 渲染为单区块：短期借款(贷方/负债，按借款类型：信用/保证/抵押/质押借款分类+小计)
2. THE Adjudication_L1_1 SHALL 显示列：项目 | 期初 | 贷方发生(借入) | 借方发生(归还) | 期末 | 未审 | AJE | RJE | 审定
3. THE Formula_Engine SHALL 计算审定数=未审+AJE+RJE
4. THE Formula_Engine SHALL 校验负债类：**期末=期初+贷方-借方**（注意！与资产类相反）
5. THE Adjudication_L1_1 SHALL 与L1-2明细合计交叉验证
6. WHEN 审定数变化时 SHALL 回写TB(2001)+发布'substantive:adjudicated'
7. THE Adjudication_L1_1 SHALL subscribe附注EventBus刷新+publish 'disclosure:note-text-updated'

### Requirement 3: 明细表L1-2（按借款列示）

**User Story:** As a 审计助理, I want to 管理短期借款明细, so that 每笔借款可追溯。

#### Acceptance Criteria

1. THE Detail_L1_2 SHALL 显示列：借款银行 | 借款合同号 | 借款类型 | 起始日 | 到期日 | 年利率 | 期初余额 | 本期借入 | 本期归还 | 期末余额 | 币种
2. THE Detail_L1_2 SHALL 自动计算：期末余额=期初+本期借入-本期归还（负债类）
3. THE Detail_L1_2 SHALL 30列宽表拆分：按借款基础信息/金额变动/担保信息区段Tab切换（行同步）
4. THE Detail_L1_2 SHALL 支持动态行新增（先弹ElMessageBox.prompt输入借款银行名称）+导入导出
5. THE Detail_L1_2 SHALL 与L1-5利息测算每笔借款一一对应（合同号关联）
6. THE Detail_L1_2 SHALL 合计行与审定表L1-1交叉验证

### Requirement 4: 利息测算表L1-5（核心！联动L2/L8）

**User Story:** As a 审计助理, I want to 验证短期借款利息测算, so that 我能确认应付利息和财务费用的准确性。

#### Acceptance Criteria

1. THE Interest_Calc_L1_5 SHALL 显示列：借款合同号 | 本金 | 年利率 | 计息起始日 | 计息天数 | 测算利息 | 账载利息 | 差异
2. THE Interest_Engine SHALL 实现：测算利息=本金×年利率×计息天数/365
3. THE Interest_Engine SHALL 实现差异=测算利息-账载利息
4. WHEN |差异|>阈值时 SHALL 红色高亮
5. THE Interest_Calc_L1_5 SHALL 合计测算利息 → EventBus publish 'l1:interest-calculated'（供L2应付利息/L8财务费用订阅）
6. THE Interest_Calc_L1_5 SHALL 通过cross_wp_ref关联L2应付利息、L8财务费用
7. THE Interest_Calc_L1_5 SHALL 支持按借款筛选查看

### Requirement 5: 征信报告核对表L1-4

**User Story:** As a 审计助理, I want to 核对征信报告与账面短期借款, so that 银行借款完整性得到验证。

#### Acceptance Criteria

1. THE Credit_Check_L1_4 SHALL 显示列：授信银行 | 授信额度 | 已用额度 | 征信借款余额 | 账面借款余额 | 差异 | 差异说明
2. THE Credit_Check_L1_4 SHALL 自动计算差异=征信余额-账面余额
3. WHEN 差异≠0时 SHALL 红色高亮并要求填写差异说明
4. THE Credit_Check_L1_4 SHALL 与L1-2明细合计交叉验证（账面完整性）
5. THE Credit_Check_L1_4 SHALL 叙述式结论区（textarea autosize + AI辅助）

### Requirement 6: 逾期贷款检查表L1-7 + 抵质押资产检查表L1-8

**User Story:** As a 审计助理, I want to 检查逾期贷款和抵质押资产, so that 借款风险和担保情况得到评价。

#### Acceptance Criteria

1. THE Overdue_Check_L1_7 SHALL 显示：借款合同号 | 到期日 | 报告日 | 逾期天数 | 逾期金额 | 是否展期 | 风险评价
2. THE Overdue_Check_L1_7 SHALL 自动计算逾期天数=报告日-到期日（>0为逾期）
3. WHEN 逾期天数>0时 SHALL 橙色/红色分级高亮
4. THE Pledge_Check_L1_8 SHALL 显示：抵质押资产 | 账面价值 | 担保借款 | 担保比例 | 权属核验
5. THE Pledge_Check_L1_8 SHALL 自动计算担保比例=担保借款/账面价值×100%

### Requirement 7: 贷款合同检查L1-6 + 检查表L1-9

**User Story:** As a 审计助理, I want to 检查贷款合同要素并完成短期借款检查表, so that 借款条款和整体审计结论完整。

#### Acceptance Criteria

1. THE Contract_Check_L1_6 SHALL 32列宽表按合同要素分区段Tab（基础/利率条款/担保条款/违约条款）
2. THE Contract_Check_L1_6 SHALL 支持行级OCR（📎列上传合同→POST contract-ocr→ElMessageBox确认→merge）
3. THE STLoan_Check_L1_9 SHALL 提供核对清单+审计结论区（el-card包裹）
4. THE 检查表 SHALL 每个文本section标题行右侧放AI辅助按钮

### Requirement 8: 调整分录L1-3 + 附注

**User Story:** As a 审计助理, I want to 管理短期借款调整并生成附注, so that 审计调整有据可循且披露完整。

#### Acceptance Criteria

1. THE Adjustment_L1_3 SHALL 借贷平衡校验+EventBus+双向同步L1-1
2. THE Disclosure_Listed/SOE SHALL 根据企业类型(上市/国企)自动切换附注模板
3. THE 附注 SHALL subscribe 'substantive:adjudicated'刷新数据

### Requirement 9: 利息测算引擎（纯函数）

**User Story:** As a 开发者, I want to 实现利息测算的纯函数引擎, so that 利息计算可PBT验证。

#### Acceptance Criteria

1. THE Interest_Engine SHALL calcInterest(principal, annualRate, days): 利息=本金×年利率×天数/365
2. THE Interest_Engine SHALL calcOverdueDays(dueDate, reportDate): 逾期天数
3. THE Interest_Engine SHALL calcPledgeRatio(guaranteedLoan, bookValue): 担保比例
4. THE Interest_Engine SHALL 处理边界：天数为0时利息=0；利率为0时利息=0

### Requirement 10: 跨底稿联动（L1→L2/L8）

**User Story:** As a 项目经理, I want to L1利息测算联动L2应付利息和L8财务费用, so that 筹资循环数据一致。

#### Acceptance Criteria

1. THE L1 SHALL 在L1-5利息测算完成后 publish 'l1:interest-calculated'（payload含合计利息+按合同明细）
2. THE L2应付利息 SHALL 订阅该事件用于计提核对
3. THE L8财务费用 SHALL 订阅该事件用于利息支出测算
4. THE 联动 SHALL 通过cross_wp_references建立ref_index chip可跳转

### Requirement 11: 双模式+导入导出+版本链+复核对话

**User Story:** As a 审计助理, I want to L1支持完整的集成能力, so that 与D~N底稿标准一致。

#### Acceptance Criteria

1. THE L1 SHALL 支持双模式（结构化视图 ↔ OnlyOffice在线编辑）+ OO健康检查降级
2. THE L1 SHALL 支持导入导出三级（useL1ImportExport，后端3端点，http带Authorization）
3. THE L1 SHALL 集成useVersionTrail（主入口+autoSnapshot）
4. THE L1 SHALL 主入口provide openReviewDialog，子组件inject（section标题栏右侧复核按钮）
