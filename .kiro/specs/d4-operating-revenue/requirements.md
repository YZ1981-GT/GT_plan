# Requirements Document: D4 营业收入底稿专属HTML精美组件

## Introduction

D4营业收入底稿的专属HTML精美组件构建。将现有 `d-form-table`/`audit-sheet` 通用渲染升级为独立专属组件 `d4-operating-revenue`，覆盖来自8个xlsx源模板的42个有效sheet（含5个底稿目录合并为1个统一目录Tab）。科目覆盖6001主营业务收入+6051其他业务收入（损益类/贷方科目）。所有sheet合并到一个大Tab页签下（采用分组嵌套Tab设计：一级Tab按功能域分7组，二级Tab为各组内sheet），目录也合并到一起。核心关注：CAS14五步法收入确认、月度收入波动分析、截止测试跨期判断、关联方销售价格公允性、IPO/舞弊应对条件可见性、跨底稿联动（D2应收/D3预收/A13错报/B50风险）。关键公式总数约280+。

## Glossary

- **Adjudication_Table**: 审定表D4-1，主营+其他双区块结构（48公式），列：项目|本期(未审/AJE/RJE/审定)|上期(未审/AJE/RJE/审定)
- **Revenue_Detail**: 主营业务收入明细表D4-2，22列月度宽表（99公式），按产品/服务分行×12月+汇总+调整+审定+变动
- **Other_Revenue_Detail**: 其他业务收入明细表D4-3，按项目分行（60公式），列含本期/上期/变动金额/变动比例
- **Adjustment_Table**: 营业收入调整分录汇总D4-4，10列动态行（6公式）
- **Disclosure_Listed**: 附注披露信息（上市公司），85行3子节（34公式）：营业收入+成本/合同收入分解/Top5客户
- **Disclosure_SOE**: 附注披露信息（国企），72行3子节（32公式）：营业收入+成本/分产品/Top5客户
- **Policy_Check**: 营业收入会计政策检查D4-5，CAS14五步法段落型59行
- **Indicator_Analysis**: 重要指标分析D4-6，收入增长率/毛利率/周转率/应收占比等
- **Margin_Analysis**: 毛利率分析表D4-7，月度毛利率趋势+同比
- **Product_Margin**: 重要产品毛利分析D4-8，分产品/服务毛利率对比
- **Customer_Structure**: 重要客户结构分析D4-9，客户集中度+Top5/Top10
- **Customer_Price**: 重要客户销售价格分析D4-10，主要客户单价变动
- **Product_Price**: 产品销售价格分析D4-11，产品单价趋势
- **Contract_Check**: 合同检查表D4-12，合同要素逐项检查（6公式）
- **ERP_Check**: ERP系统核对D4-13，账面金额vs系统
- **Occurrence_Check**: 营业收入发生检查表D4-14，凭证抽查（抽样参数+明细表）
- **Completeness_Check**: 营业收入完整性检查表D4-15，从单据追到账
- **Export_Check**: 出口收入电子口岸核对D4-16，海关系统
- **Cutoff_Forward**: 截止测试（账到单据）D4-17，账上记录→找原始单据
- **Cutoff_Backward**: 截止测试（单据到账）D4-18，原始单据→找账上记录
- **Discount_Check**: 销售折扣与折让检查D4-19，折扣政策+明细
- **Return_Check**: 销售退货检查表D4-20，退货政策+退货明细+期后退货
- **Related_Party_Price**: 关联方销售价格分析D4-21，关联销售vs非关联价格对比
- **IPO_Procedure**: IPO程序表D4-22A，IPO/上市/舞弊应对专属程序表
- **IPO_Indicator**: 重要指标分析（IPO版）D4-22，IPO增强版指标
- **Invoice_Compare**: 收入与开具发票金额比较D4-23，月度收入vs发票差异
- **Third_Party_Payment**: 第三方回款检查D4-24，代付协议+资金流向
- **Dealer_Check**: 经销商检查D4-25，经销商背景+销售匹配
- **Overseas_Check**: 境外销售收入检查D4-26，贸易条款+海关验证
- **Undisclosed_RP**: 识别未披露的关联方D4-27，客户背景穿透
- **Customer_Info_Checklist**: 客户信息核查清单D4-28，工商核查要点
- **Customer_Info_Detail**: 客户信息检查表D4-29，逐客户详细检查
- **Interview_Summary**: 客户访谈记录汇总表D4-30，多客户对比
- **Interview_Detail**: 客户访谈记录D4-31，单客户详细记录
- **Fund_Flow_Check**: 客户/供应商资金流水检查D4-32，资金回流
- **Other_Margin**: 其他业务毛利率分析表D4-33，其他业务毛利率
- **Other_Contract**: 其他业务收入合同测算表D4-34，合同测算
- **Other_Check**: 其他业务收入检查表D4-35，抽样+凭证
- **Other_Cutoff**: 其他业务收入截止测试D4-36，截止性
- **Procedure_Table**: 实质性程序表D4A，审计程序+5项认定（复用a-program-console）
- **Cross_Sheet_Engine**: 跨sheet公式引擎，D4-2→D4-1按产品聚合+D4-3→D4-1+D4-4→D4-1 AJE/RJE同步
- **Formula_Engine**: 前端公式引擎composable，损益类贷方科目公式（本期审定=未审+AJE+RJE；变动率=(本期-上期)/上期）
- **Dynamic_Row**: 动态行，用户可新增/删除的数据行
- **Summary_Row**: 合计行，自动SUM对应明细行（不可编辑）
- **Dual_Mode**: 双模式切换，HTML精美组件 ↔ OnlyOffice在线编辑
- **EventBus**: 进程内事件总线，跨底稿联动通信
- **GtIndexChip**: 交叉索引跳转芯片，点击跳转到目标底稿/位置
- **Review_Dialog**: 通用复核对话组件，任意位置可发起复核线程
- **AI_Assistant**: AI辅助生成，审计说明/变动分析/政策评价等文本自动生成
- **Trial_Balance_Writeback**: 审定数回写试算平衡表（科目6001+6051，损益类/贷方科目）
- **Visibility_Control**: 适用性分组Tab可见性控制，根据项目business_category控制IPO/舞弊组显隐

## Requirements

### Requirement 1: 组件架构与分组嵌套Tab设计

**User Story:** As a 开发者, I want to D4营业收入底稿按功能域分组为嵌套Tab结构, so that 36个sheet在一个统一入口中有序组织且代码可维护。

#### Acceptance Criteria

1. THE D4 组件 SHALL 注册新componentType: `d4-operating-revenue`，主入口为 GtD4OperatingRevenue.vue（el-tabs容器）
2. THE D4 组件 SHALL 采用分组嵌套Tab设计：一级Tab分7组（核心|政策|分析程序|检查程序|关联方|IPO/舞弊|其他收入），二级Tab为各组内sheet独立子组件
3. THE D4 组件 SHALL 将每个功能域拆分为独立Vue子组件目录（d4/core/、d4/policy/、d4/analysis/、d4/inspection/、d4/related/、d4/ipo/、d4/other/），每文件200-400行
4. THE D4 组件 SHALL 拆分为独立composable：useD4FormData.ts（基础数据加载/保存）+ useD4FormulaEngine.ts（纯函数公式引擎）+ useD4CrossSheet.ts（跨sheet联动逻辑）
5. THE useD4FormulaEngine.ts SHALL 为纯函数模块（无副作用），包含：损益类审定数=未审+AJE+RJE、变动率计算、合计行SUM、月度合计SUM(1~12月)、毛利率=(收入-成本)/收入等全部公式
6. THE D4 组件 SHALL 在htmlRendererRegistry中注册'd4-operating-revenue'→GtD4OperatingRevenue映射
7. THE D4 组件 SHALL 在wp_code_overrides.json中将D4/D4-1~D4-36的componentType统一映射为'd4-operating-revenue'
8. THE D4 组件 SHALL 在VALID_COMPONENT_TYPES中注册'd4-operating-revenue'
9. THE GtD4OperatingRevenue.vue SHALL 支持selfLoad（当htmlData prop为null时自行调render-config?force_component_type=d4-operating-revenue）
10. THE D4 组件 SHALL 使用 checklist_responses 表存储数据，item_id前缀为"D4-{sheet编号}-{field}"格式

### Requirement 2: 审定表D4-1 HTML渲染（双区块48公式）

**User Story:** As a 审计助理, I want to 在精美HTML表格中查看和编辑营业收入审定表, so that 我能清晰地看到主营业务收入和其他业务收入两个区块的审定数据。

#### Acceptance Criteria

1. THE Adjudication_Table SHALL 渲染为双区块固定结构：一、主营业务收入（产品A/B/C/.../小计）→ 二、其他业务收入（项目A/B/.../小计）→ 营业收入合计
2. THE Adjudication_Table SHALL 显示以下列：项目 | 本期数(未审/账项调整/重分类调整/审定) | 上期数(未审/账项调整/重分类调整/审定)
3. WHEN 用户编辑本期未审数/AJE/RJE单元格时, THE Formula_Engine SHALL 自动计算本期审定数（=未审+AJE+RJE）
4. THE Adjudication_Table SHALL 自动计算各区块小计行（=SUM对应产品/项目明细行）和营业收入合计行（=主营小计+其他小计），合计行不可手动编辑
5. THE Adjudication_Table SHALL 在底部显示试算平衡表数行（自动从TB取数科目6001+6051）和差异行（=审定数合计-试算表数），差异不为零时红色高亮
6. WHEN 主营小计的审定数与D4-2合计行不一致时, THE Adjudication_Table SHALL 显示黄色警告"主营审定数≠D4-2合计，差额：±xxx元"
7. WHEN 其他小计的审定数与D4-3合计行不一致时, THE Adjudication_Table SHALL 显示黄色警告"其他审定数≠D4-3合计，差额：±xxx元"
8. THE Adjudication_Table SHALL 在底部显示"审计说明"区域（textarea + AI生成按钮 + GtIndexChip跳转D4-6/D4-7分析结果）和"审计结论"区域（textarea + AI生成按钮）
9. THE Adjudication_Table SHALL 在审计说明/结论区域放置复核对话入口（💬图标）
10. WHEN 审定数计算完成且发生变化时, THE Adjudication_Table SHALL 调用writebackTrialBalance将最新审定数回写trial_balance.audited_amount（科目6001+6051）并通过EventBus发布'substantive:adjudicated'事件

### Requirement 3: 主营业务收入明细表D4-2 HTML渲染（22列月度宽表99公式）

**User Story:** As a 审计助理, I want to 在精美HTML宽表中管理主营业务收入月度明细, so that 我能追踪每个产品/服务类别的12个月收入波动和年度变动。

#### Acceptance Criteria

1. THE Revenue_Detail SHALL 以el-table横向滚动渲染22列：项目(A)|1月~12月(B~M)|本期未审合计(N)|本期审计调整(O)|本期审定数(P)|上期未审数(Q)|上期审计调整(R)|上期审定数(S)|未审变动比例(T)|审定变动比例(U)|备注(V)
2. THE Formula_Engine SHALL 自动计算每行：本期未审合计=SUM(1月~12月)；本期审定数=未审合计+审计调整；上期审定数=上期未审+上期审计调整；未审变动比例=(本期未审-上期未审)/上期未审；审定变动比例=(本期审定-上期审定)/上期审定
3. THE Revenue_Detail SHALL 在底部显示合计行（=SUM所有产品行各金额列）和核对行（=合计-试算平衡表数科目6001），合计行不可编辑
4. WHEN 用户点击"添加产品行"按钮时, THE Revenue_Detail SHALL 在合计行上方新增一个可编辑空行
5. THE Revenue_Detail SHALL 固定前1列（项目）使横向滚动时仍可辨识行
6. WHEN 变动比例绝对值超过30%时, THE Revenue_Detail SHALL 以红色高亮显示该比例单元格
7. THE Revenue_Detail SHALL 在底部显示"审计说明"区域（textarea + AI生成按钮，基于各产品变动情况+月度波动趋势生成说明）和"审计结论"区域
8. THE Revenue_Detail SHALL 对所有金额列应用右对齐+金额格式化（千分位/负数红色括号/零值"-"）
9. THE Revenue_Detail SHALL 支持按产品名称模糊搜索筛选行（搜索框在表头上方）
10. WHEN 动态行超过30行时, THE Revenue_Detail SHALL 启用虚拟滚动以保证渲染性能

### Requirement 4: 其他业务收入明细表D4-3 HTML渲染（60公式）

**User Story:** As a 审计助理, I want to 在精美HTML表格中管理其他业务收入明细, so that 我能追踪各项其他业务收入的本期/上期变动。

#### Acceptance Criteria

1. THE Other_Revenue_Detail SHALL 显示以下列：项目 | 本期数(未审/调整/审定/占比) | 上期数(未审/调整/审定/占比) | 变动(金额/比例) | 备注
2. THE Formula_Engine SHALL 自动计算每行：审定数=未审+调整；占比=本行审定/合计审定×100%；变动金额=本期审定-上期审定；变动比例=(本期-上期)/上期
3. THE Other_Revenue_Detail SHALL 在底部显示合计行（=SUM所有项目行）和核对行（=合计-试算平衡表数科目6051）
4. WHEN 用户点击"添加项目行"按钮时, THE Other_Revenue_Detail SHALL 在合计行上方新增一个可编辑空行
5. WHEN 变动比例绝对值超过30%时, THE Other_Revenue_Detail SHALL 以红色高亮显示该比例单元格
6. THE Other_Revenue_Detail SHALL 在底部显示"审计说明"textarea（AI生成按钮）和"审计结论"textarea
7. THE Other_Revenue_Detail SHALL 在审计说明/结论区域放置复核对话入口（💬图标）

### Requirement 5: 调整分录汇总D4-4 HTML渲染与联动

**User Story:** As a 审计助理, I want to 在精美HTML表格中录入和管理营业收入调整分录, so that 我能快速创建AJE/RJE并联动审定表和A13错报汇总。

#### Acceptance Criteria

1. THE Adjustment_Table SHALL 显示10列：调整事项说明 | 类别(报表调整/账项调整/其他) | 报表项目 | 科目名称 | 附注项目 | … | 借方调整金额 | 贷方调整金额 | 索引 | 备注
2. WHEN 用户点击"新增调整分录"按钮时, THE Adjustment_Table SHALL 新增一行可编辑空行
3. THE Adjustment_Table SHALL 在底部显示借贷合计行，借方合计=贷方合计时显示绿色"✓平衡"，否则红色"✗不平衡：差额xxx"
4. WHEN 调整分录保存成功时, THE Adjustment_Table SHALL 通过EventBus发布'adjustment:created'事件（payload含wpCode='D4'/entryType/amount）
5. THE Adjustment_Table SHALL 双向同步AJE/RJE合计到 Adjudication_Table 对应列
6. WHEN 用户点击"推送至A13"按钮时, THE Adjustment_Table SHALL 将选中分录通过EventBus发布至A13错报汇总
7. THE Adjustment_Table SHALL 在底部显示编制提示（`<details>`折叠，蓝色左边线+浅蓝背景，默认收起）

### Requirement 6: 附注披露信息（上市公司+国企）HTML渲染

**User Story:** As a 审计助理, I want to 在精美HTML组件中编辑营业收入附注披露信息, so that 我能按子节结构核对附注数据并与审定表自动取数对齐。

#### Acceptance Criteria

1. THE Disclosure_Listed SHALL 渲染为3子节卡片结构：(1)营业收入和营业成本（分产品/服务+合计，列：项目/本期收入/本期成本/上期收入/上期成本）→ (2)合同收入分解（分产品维度+分地区维度两张子表）→ (3)前五大客户收入情况（客户名称/收入金额/占比）
2. THE Disclosure_SOE SHALL 渲染为3子节卡片结构：(1)营业收入和营业成本（列同上市版）→ (2)分产品/分地区 → (3)前五大客户
3. THE Cross_Sheet_Engine SHALL 从 Adjudication_Table 审定数自动取数填入附注第(1)子节收入合计行
4. THE Cross_Sheet_Engine SHALL 从 Revenue_Detail 按产品聚合自动取数填入附注第(2)子节分产品维度对应行
5. WHILE 跨sheet引用值生效时, THE Disclosure_Listed SHALL 以浅蓝色背景标记自动取数单元格，tooltip显示数据来源
6. THE Disclosure_Listed 和 Disclosure_SOE SHALL 对动态行支持添加/删除（Top5客户行、分产品行等）
7. THE Disclosure_Listed 和 Disclosure_SOE SHALL 自动计算各子节合计行
8. THE Disclosure_Listed SHALL 根据项目applicable_standards（listed_standalone/listed_consolidated）自动显示；THE Disclosure_SOE SHALL 根据项目applicable_standards（soe_standalone/soe_consolidated）自动显示
9. WHEN 两种标准均不适用时, THE Disclosure_Listed 和 Disclosure_SOE SHALL 隐藏对应二级Tab
10. THE Disclosure_Listed 和 Disclosure_SOE SHALL 在每个子节底部放置"说明"textarea（可编辑，双向回写附注模块，EventBus `disclosure:note-text-updated`）和编制提示折叠区（`<details>`默认收起）

### Requirement 7: 营业收入会计政策检查D4-5 HTML渲染

**User Story:** As a 审计助理, I want to 在精美HTML组件中完成CAS14五步法会计政策检查, so that 我能逐步评价被审计单位收入确认政策的恰当性。

#### Acceptance Criteria

1. THE Policy_Check SHALL 渲染为CAS14五步法卡片结构：步骤1识别合同→步骤2识别履约义务→步骤3确定交易价格→步骤4分摊交易价格→步骤5确认收入（时点/时段）
2. THE Policy_Check SHALL 在每步骤卡片内显示3个区域：(a)政策条款（只读引用区，蓝色背景）(b)被审计单位实际情况（textarea可编辑）(c)审计师评价（textarea + AI生成按钮）
3. THE Policy_Check SHALL 在每步骤卡片底部显示结论选择：Y(适当) / N(不适当) / NA(不适用)，结论为N时强制填写说明
4. THE Policy_Check SHALL 在政策条款引用区显示CAS14对应准则条文（只读折叠`<details>`，蓝色左边线+浅蓝背景）
5. THE Policy_Check SHALL 在"审计师评价"textarea旁显示🤖AI生成按钮，结合被审计单位实际情况+行业特征生成评价建议
6. THE Policy_Check SHALL 在页面顶部显示整体完成进度（5步中已完成N步，以进度条展示）
7. THE Policy_Check SHALL 在每步骤评价区域放置复核对话入口（💬图标）

### Requirement 8: 分析程序组D4-6~D4-11 HTML渲染（6 sheet）

**User Story:** As a 审计助理, I want to 在精美HTML组件中查看营业收入分析程序结果, so that 我能直观判断收入变动是否合理、毛利率趋势是否异常、客户集中度是否过高。

#### Acceptance Criteria

1. THE Indicator_Analysis SHALL 渲染为指标卡片网格（2列×N行），每个指标含：指标名称/本期值/上期值/变动/行业参考/结论（正常/异常/需关注），指标包括收入增长率/毛利率/应收周转率/应收占收入比等
2. THE Margin_Analysis SHALL 渲染为月度毛利率趋势表（1~12月×产品行+合计行），支持查看同比上期数据，毛利率波动>5个百分点的单元格黄色高亮
3. THE Product_Margin SHALL 渲染为分产品/服务毛利率对比表（产品名/收入/成本/毛利/毛利率/上期毛利率/变动），毛利率变动>10个百分点红色高亮
4. THE Customer_Structure SHALL 渲染为客户集中度分析卡片：Top5客户表（名称/金额/占比）+ Top10客户表 + 集中度指标（HHI/Top5占比），Top5占比>50%时黄色警告
5. THE Customer_Price SHALL 渲染为主要客户单价变动表（客户名/产品/本期单价/上期单价/变动率），单价变动>20%红色高亮
6. THE Product_Price SHALL 渲染为产品单价趋势表（产品名/本期均价/上期均价/变动/行业均价参考），含价格波动异常判定
7. THE Cross_Sheet_Engine SHALL 从 Revenue_Detail (D4-2)各产品行自动取数用于D4-8产品毛利计算和D4-9客户结构排名
8. THE Indicator_Analysis SHALL 从TB自动获取计算所需的科目余额（6001/6051/1122/6401等）
9. THE 分析程序组各sheet SHALL 在底部显示"审计说明"textarea（AI生成按钮，基于分析结果异常项自动生成说明）和"审计结论"textarea
10. WHEN 分析发现显著变动（指标变动超阈值）时, THE Indicator_Analysis SHALL 通过EventBus发布'analytical:significant-change'事件，联动A1-13分析性复核

### Requirement 9: 合同检查表D4-12 HTML渲染

**User Story:** As a 审计助理, I want to 在精美HTML表格中逐份检查销售合同要素, so that 我能系统性地评价合同条款完整性和收入确认时点合理性。

#### Acceptance Criteria

1. THE Contract_Check SHALL 显示为动态行表格，每行代表一份合同，列包括：索引号 | 合同名称 | 客户名称 | 合同金额 | 合同日期 | 履约义务 | 交易价格 | 收入确认时点/时段 | 可变对价 | 合同变更 | 结论 | 备注
2. WHEN 用户点击"添加合同"按钮时, THE Contract_Check SHALL 新增一行可编辑空行
3. THE Contract_Check SHALL 在"收入确认时点/时段"列提供下拉选择（时点/时段/混合），选择"时段"时展开子字段（产出法/投入法/其他）
4. THE Contract_Check SHALL 在底部显示汇总：已检查合同数/合同金额合计/覆盖率（=已检查金额/主营收入合计×100%）
5. THE Contract_Check SHALL 在每行提供GtIndexChip，跳转至D4-14/D4-15对应凭证检查
6. THE Contract_Check SHALL 在底部显示"审计说明"textarea + AI生成按钮 + "审计结论"textarea
7. THE Contract_Check SHALL 对所有金额列应用金额格式化（千分位/负数红色括号/零值"-"）

### Requirement 10: 凭证检查组D4-13~D4-15 HTML渲染（ERP核对+发生+完整性）

**User Story:** As a 审计助理, I want to 在精美HTML表格中执行营业收入凭证抽样检查, so that 我能记录抽样参数和逐笔核对ERP、凭证发生及完整性。

#### Acceptance Criteria

1. THE ERP_Check SHALL 显示为对比表结构：列包括 科目/ERP系统金额/账面金额/差异/说明，自动计算差异行（=账面-ERP），差异不为零时红色高亮
2. THE Occurrence_Check SHALL 分为2区域：抽样参数区（测试总体/特定样本/抽样总体/抽样方法+抽样过程）+ 凭证明细检查表（客户名称|日期|凭证编号|业务内容|金额|支持性文件|核对内容(1-5)|是否异常|备注）
3. THE Completeness_Check SHALL 分为2区域：抽样参数区 + 从单据追查到账明细表（单据编号|单据日期|客户|金额|对应凭证编号|入账日期|差异|是否异常|备注）
4. WHEN 用户点击"添加样本"按钮时, THE Occurrence_Check 和 Completeness_Check SHALL 在对应区块新增一行凭证抽样明细
5. THE Occurrence_Check 和 Completeness_Check SHALL 在底部显示汇总：已检查笔数/发现异常笔数/异常率（=异常/已检查×100%）
6. THE Occurrence_Check 和 Completeness_Check SHALL 集成抽凭引擎（voucher-sampling-engine），支持自动抽样后填充样本行
7. THE 凭证检查组各sheet SHALL 在抽样参数区显示进度条：已抽取样本数/目标样本量
8. THE 凭证检查组各sheet SHALL 在审计说明/结论区域放置复核对话入口（💬图标）

### Requirement 11: 截止测试D4-17~D4-18 HTML渲染（双向截止）

**User Story:** As a 审计助理, I want to 在精美HTML表格中执行营业收入截止测试, so that 我能从两个方向验证收入是否记录在正确的会计期间。

#### Acceptance Criteria

1. THE Cutoff_Forward SHALL 渲染为"账到单据"方向检查表：列包括 凭证编号|凭证日期|客户名称|收入金额|对方科目|发货单日期|签收日期|验收日期|是否跨期|跨期天数|调整建议|备注
2. THE Cutoff_Backward SHALL 渲染为"单据到账"方向检查表：列包括 单据编号|单据日期|客户名称|金额|对应凭证|入账日期|是否跨期|跨期天数|调整建议|备注
3. THE Formula_Engine SHALL 自动判断跨期：WHEN 凭证日期与发货/签收/验收日期跨越资产负债表日时，自动标记"是否跨期"=Y并计算跨期天数
4. WHEN "是否跨期"为Y时, THE Cutoff_Forward 和 Cutoff_Backward SHALL 以红色背景高亮该行
5. THE Cutoff_Forward 和 Cutoff_Backward SHALL 在底部显示汇总：总检查笔数/跨期笔数/跨期金额合计/建议调整金额
6. THE Cutoff_Forward 和 Cutoff_Backward SHALL 提供GtIndexChip跳转D2应收账款截止测试（交叉验证收入确认日vs应收入账日）
7. THE Cutoff_Forward 和 Cutoff_Backward SHALL 集成cutoff-test-auto-sampling组件，支持自动从tb_ledger按期末前后N天窗口提取样本
8. THE 截止测试sheet SHALL 在审计说明/结论区域放置复核对话入口（💬图标），特别关注跨期异常行

### Requirement 12: 出口收入核对+折扣折让+退货检查（D4-16/D4-19/D4-20）

**User Story:** As a 审计助理, I want to 在精美HTML组件中检查出口收入、销售折扣和退货情况, so that 我能验证收入的真实性和完整性。

#### Acceptance Criteria

1. THE Export_Check SHALL 渲染为对比表：列包括 月份/账面出口收入/电子口岸金额/汇率/折算金额/差异/说明，底部合计+差异率
2. THE Discount_Check SHALL 分为2区域：折扣政策说明区（textarea描述折扣政策+AI评价按钮）+ 折扣明细检查表（客户名|合同金额|折扣率|折扣金额|是否符合政策|备注），底部合计
3. THE Return_Check SHALL 分为3区域：退货政策说明区（textarea）+ 本期退货明细表（客户名|退货日期|金额|原因|是否重新确认收入|备注）+ 期后退货检查表（退货日期|金额|原因|是否需调整|备注），期后退货金额超重要性水平时红色高亮
4. WHEN 折扣明细"是否符合政策"为N时, THE Discount_Check SHALL 以红色高亮该行并强制填写备注
5. THE Return_Check SHALL 在"退货原因"列提供🤖AI分析按钮，基于退货模式（客户集中度/时间集中度/金额趋势）生成分析建议
6. THE Discount_Check SHALL 在每行提供GtIndexChip跳转D4-12对应合同条款
7. THE Return_Check SHALL 提供GtIndexChip跳转D4-17/D4-18截止测试（退货日期vs收入确认日期交叉验证）
8. THE 各检查sheet SHALL 在审计说明/结论区域放置复核对话入口（💬图标）

### Requirement 13: 关联方销售价格分析D4-21 HTML渲染

**User Story:** As a 审计助理, I want to 在精美HTML表格中分析关联方销售价格的公允性, so that 我能对比关联方与非关联方交易价格判断是否存在利益输送。

#### Acceptance Criteria

1. THE Related_Party_Price SHALL 渲染为对比分析表：列包括 产品/服务|关联方客户|关联方单价|非关联方客户|非关联方单价|价格差异率|差异原因|结论(公允/存疑/不公允)|备注
2. THE Formula_Engine SHALL 自动计算价格差异率=（关联方单价-非关联方单价）/非关联方单价×100%
3. WHEN 价格差异率绝对值超过10%时, THE Related_Party_Price SHALL 以黄色高亮该行；超过20%时红色高亮
4. WHEN 用户点击"添加对比项"按钮时, THE Related_Party_Price SHALL 新增一行可编辑空行
5. THE Related_Party_Price SHALL 在底部显示"关联方销售金额合计"和"占营业收入比例"（=关联方销售/D4-1审定合计×100%）
6. THE Related_Party_Price SHALL 在"差异原因"列提供🤖AI评价按钮，结合产品特性/交易量/市场价格生成公允性评价建议
7. THE Related_Party_Price SHALL 提供GtIndexChip跳转A17重大事项（关联方交易披露）
8. THE Related_Party_Price SHALL 在审计说明/结论区域放置复核对话入口（💬图标），复核对话sectionId为"D4-21-related-price"

### Requirement 14: IPO/舞弊应对程序组D4-22A~D4-32 HTML渲染（11 sheet条件可见）

**User Story:** As a 审计助理, I want to 在IPO/上市/舞弊应对场景下执行增强审计程序, so that 我能满足监管要求完成额外的收入真实性验证。

#### Acceptance Criteria

1. THE Visibility_Control SHALL 根据项目business_category字段控制IPO/舞弊组一级Tab的可见性：仅当business_category包含'ipo'/'listed'/'neeq'/'restructuring'/'fraud_risk'时显示该Tab组
2. THE IPO_Procedure SHALL 复用`a-program-console` componentType渲染IPO增强程序表，在每步程序的索引号列提供GtIndexChip跳转D4-22~D4-32各子sheet
3. THE IPO_Indicator SHALL 渲染为IPO版重要指标分析（同D4-6结构但增加IPO特有指标：收入确认政策变更/非经常性损益/异常客户等）
4. THE Invoice_Compare SHALL 渲染为月度对比表（月份|确认收入|开具发票金额|差异|差异率|说明），差异率>10%黄色高亮，底部合计+年度差异
5. THE Third_Party_Payment SHALL 渲染为检查表：代付协议检查区（是否存在/协议条款textarea）+ 资金流向明细（付款方|收款方|金额|日期|与销售关联|备注），资金回流模式识别
6. THE Dealer_Check SHALL 渲染为经销商检查表（经销商名称|注册资本|成立时间|主营业务|本期采购额|库存周转|终端销售|差异|是否异常）
7. THE Overseas_Check SHALL 渲染为境外销售检查表（客户|国家|贸易条款|报关金额|账面金额|差异|海关核验结果|备注）
8. THE Undisclosed_RP SHALL 渲染为客户背景穿透表（客户名称|股东信息|实控人|与被审计单位关联|穿透结论），穿透发现关联关系时红色高亮
9. THE Customer_Info_Checklist 和 Customer_Info_Detail SHALL 渲染为工商核查清单（固定检查项Y/N）和逐客户详细检查表（动态行多列）
10. THE Interview_Summary 和 Interview_Detail SHALL 渲染为访谈汇总对比表（多客户横向对比核心问答）和单客户详细记录（问答对卡片结构，AI建议访谈问题）
11. THE Fund_Flow_Check SHALL 渲染为资金流水检查表（交易对手|流入金额|流出金额|净额|时间匹配度|备注），自动标记资金回流可疑项（同一对手短期内入+出且金额接近）
12. THE IPO/舞弊组各sheet SHALL 在审计说明/结论区域放置复核对话入口（💬图标），特别关注D4-24第三方回款和D4-32资金流水异常行

### Requirement 15: 其他业务收入组D4-33~D4-36 HTML渲染（4 sheet）

**User Story:** As a 审计助理, I want to 在精美HTML组件中检查其他业务收入的毛利、合同、凭证和截止, so that 我能对其他业务收入执行完整的实质性程序。

#### Acceptance Criteria

1. THE Other_Margin SHALL 渲染为其他业务毛利率分析表（项目名/收入/成本/毛利/毛利率/上期毛利率/变动），结构同D4-8但数据来源为D4-3其他业务收入
2. THE Other_Contract SHALL 渲染为合同测算表（合同名称|合同金额|合同期限|本期应确认收入|实际确认收入|差异|说明），自动计算差异=实际-应确认
3. THE Other_Check SHALL 分为2区域：抽样参数区 + 凭证明细检查表（同D4-14结构），集成抽凭引擎
4. THE Other_Cutoff SHALL 渲染为截止测试表（同D4-17/D4-18结构但针对其他业务收入），支持双向截止检查
5. THE Other_Margin SHALL 从D4-3自动取数计算各项目毛利率
6. THE Other_Contract SHALL 在差异不为零时黄色高亮，差异金额超重要性水平时红色高亮
7. THE Other_Check 和 Other_Cutoff SHALL 在底部显示汇总公式：已检查笔数/异常笔数/异常率
8. THE 其他收入组各sheet SHALL 在审计说明/结论区域放置复核对话入口（💬图标）

### Requirement 16: 实质性程序表D4A 集成

**User Story:** As a 审计助理, I want to 程序表D4A集成到统一入口并联动各子sheet索引, so that 我能从程序表出发逐步执行审计步骤并跳转到对应底稿。

#### Acceptance Criteria

1. THE Procedure_Table SHALL 复用`a-program-console` componentType渲染审计程序步骤（含5项认定：存在/完整性/准确性计价/截止/列报）
2. THE Procedure_Table SHALL 在每步程序的"底稿索引号"列提供GtIndexChip，点击跳转至对应子sheet（D4-1~D4-36各sheet）
3. WHEN B50风险评估更新时, THE Procedure_Table SHALL 通过EventBus接收'risk:updated'事件并更新程序步骤状态标记
4. THE Procedure_Table SHALL selfLoad渲染数据（当htmlData prop为null时自行调render-config?force_component_type=a-program-console）
5. THE Procedure_Table SHALL 在程序表与D4-22A IPO程序表之间通过GtIndexChip建立交叉引用（D4A常规程序引用IPO增强程序）

### Requirement 17: 跨Sheet数据流与公式联动

**User Story:** As a 审计助理, I want to 各sheet之间的数据自动联动和公式重算, so that 数据在36个sheet间保持一致、减少手工复制错误。

#### Acceptance Criteria

1. THE Cross_Sheet_Engine SHALL 从 Revenue_Detail (D4-2) 按产品汇总本期审定数填入 Adjudication_Table "主营业务收入"各行
2. THE Cross_Sheet_Engine SHALL 从 Other_Revenue_Detail (D4-3) 按项目汇总填入 Adjudication_Table "其他业务收入"各行
3. THE Cross_Sheet_Engine SHALL 从 Adjustment_Table (D4-4) 同步AJE/RJE合计到 Adjudication_Table 对应列
4. WHEN Revenue_Detail 数据变更时, THE Cross_Sheet_Engine SHALL 在2秒内刷新 Adjudication_Table 中的聚合值（通过allResponses computed链响应式刷新，无需API调用）
5. THE Cross_Sheet_Engine SHALL 从 Revenue_Detail 按产品行取数供 Product_Margin (D4-8) 毛利计算
6. THE Cross_Sheet_Engine SHALL 从 Revenue_Detail Top5产品取数供 Customer_Structure (D4-9) 客户排名
7. THE Cross_Sheet_Engine SHALL 从TB/tb_ledger自动获取D4-6~D4-11分析指标所需的科目余额和发生额
8. WHILE 跨sheet引用值生效时, THE 各目标sheet SHALL 以浅蓝色背景标记自动取数单元格，tooltip显示数据来源（如"取自D4-2按产品汇总"）
9. IF 跨sheet数据加载失败, THEN THE Cross_Sheet_Engine SHALL 显示"-"占位符并在单元格右上角标注黄色三角警告图标

### Requirement 18: 跨底稿EventBus联动

**User Story:** As a 审计助理, I want to D4营业收入底稿与其他底稿自动联动, so that 审定数变化、调整分录、分析异常等信息能实时传递到相关底稿。

#### Acceptance Criteria

1. WHEN D4-1审定数变化时, THE Cross_Sheet_Engine SHALL 通过EventBus发布'substantive:adjudicated'事件回写trial_balance科目6001+6051（payload含wpCode='D4'/accountCode='6001,6051'/auditedAmount）
2. WHEN D4-4调整分录创建时, THE Adjustment_Table SHALL 通过EventBus发布'adjustment:created'事件联动A13错报汇总
3. WHEN D4-6~D4-11分析发现显著变动时, THE Indicator_Analysis SHALL 通过EventBus发布'analytical:significant-change'事件联动A1-13分析性复核
4. WHEN EventBus收到'risk:updated'事件时（B50风险评估更新）, THE Procedure_Table SHALL 更新程序步骤状态标记
5. THE Cutoff_Forward 和 Cutoff_Backward SHALL 与D2应收账款底稿进行截止交叉验证（收入确认日vs应收入账日），通过GtIndexChip跳转D2相关sheet
6. THE Cross_Sheet_Engine SHALL 监听D3预收账款期后结转事件，在D4收入确认时点进行交叉验证（GtIndexChip跳转D3-7）

### Requirement 19: GtIndexChip交叉索引（10+处）

**User Story:** As a 审计助理, I want to 底稿各处有可点击的交叉索引芯片, so that 我能快速跳转到相关底稿查看关联信息。

#### Acceptance Criteria

1. THE Adjudication_Table SHALL 在审计说明区域提供GtIndexChip跳转：D4-6/D4-7（分析结果）、D4-2（产品明细）
2. THE Adjudication_Table SHALL WHEN 变动率>30%时，在对应行提供GtIndexChip跳转D4-2对应产品明细
3. THE Revenue_Detail SHALL 在产品行提供GtIndexChip跳转D4-8对应产品毛利分析
4. THE Customer_Structure SHALL 在Top5客户行提供GtIndexChip跳转D4-21关联方价格分析
5. THE Contract_Check SHALL 在每行提供GtIndexChip跳转D4-14/D4-15凭证检查
6. THE Cutoff_Forward 和 Cutoff_Backward SHALL 提供GtIndexChip跳转D2应收账款截止测试
7. THE Discount_Check SHALL 在每行提供GtIndexChip跳转D4-12合同条款
8. THE Return_Check SHALL 提供GtIndexChip跳转D4-17/D4-18截止测试
9. THE Related_Party_Price SHALL 提供GtIndexChip跳转A17重大事项（关联方交易）
10. THE Procedure_Table SHALL 在每步程序索引号列提供GtIndexChip跳转各子sheet
11. THE IPO_Procedure SHALL 在每步程序索引号列提供GtIndexChip跳转D4-22~D4-32各子sheet
12. WHEN 用户点击GtIndexChip时, THE Cross_Sheet_Engine SHALL 切换到目标Tab（含一级+二级Tab定位）并高亮定位到目标行

### Requirement 20: 自动提取填充（TB/tb_ledger取数）

**User Story:** As a 审计助理, I want to 审定表和分析表从试算平衡表和序时账自动获取数据, so that 期初/期末未审数和月度发生额不需要手工录入。

#### Acceptance Criteria

1. THE Adjudication_Table SHALL 通过auto_data_source resolver从trial_balance（科目6001+6051）自动获取本期/上期未审数
2. THE Revenue_Detail SHALL 支持从tb_ledger（科目6001，按月汇总）自动获取各产品各月发生额（"从序时账导入"按钮）
3. THE Indicator_Analysis SHALL 通过auto_data_source resolver从trial_balance自动获取计算指标所需科目余额（6001/6051/1122/6401/6402等）
4. WHEN TB数据更新时, THE Cross_Sheet_Engine SHALL 自动刷新依赖TB的单元格值
5. WHILE TB数据尚未导入时, THE Adjudication_Table SHALL 在未审数单元格显示"待导入TB"灰色占位文字
6. THE Revenue_Detail SHALL 支持"导出空模板"（含表头+格式+公式，无数据行）和"导出数据"（含当前数据的xlsx文件）和"导入数据"（解析上传xlsx回写checklist_responses）
7. IF 导入的xlsx格式不符合模板结构, THEN THE Revenue_Detail SHALL 显示错误提示并列出不匹配的列名

### Requirement 21: AI辅助生成

**User Story:** As a 审计助理, I want to 各sheet的审计说明和专业评价区域支持AI生成, so that 我能快速获得基于数据的专业审计文本建议。

#### Acceptance Criteria

1. THE Adjudication_Table SHALL 在审计说明/结论textarea旁提供🤖AI生成按钮，基于当前数据变动情况+D4-6~D4-11分析结果作为context生成审计说明
2. THE Revenue_Detail 和 Other_Revenue_Detail SHALL 在审计说明textarea旁提供🤖AI生成按钮，基于各产品/项目变动百分比+月度波动趋势生成变动原因分析
3. THE Policy_Check SHALL 在每步骤"审计师评价"textarea旁提供🤖AI生成按钮，结合被审计单位实际情况+CAS14准则条文+行业特征生成评价建议
4. THE Return_Check SHALL 在退货原因区域提供🤖AI分析按钮，基于退货模式（客户集中度/时间集中度/金额趋势）生成退货风险分析
5. THE Related_Party_Price SHALL 在差异原因列提供🤖AI评价按钮，结合产品特性/交易量/市场价格生成关联方交易公允性评价
6. THE Interview_Detail SHALL 提供🤖AI建议按钮，基于项目背景和客户信息生成访谈问题清单建议
7. THE 各分析程序sheet(D4-6~D4-11) SHALL 在审计说明textarea旁提供🤖AI生成按钮，基于分析结果异常项（超阈值指标）自动生成审计说明文本
8. THE AI生成按钮 SHALL 调用POST /api/workpapers/{wp_id}/d4/ai-generate端点，传入sectionId+existingContent+relatedContext

### Requirement 22: 复核对话集成

**User Story:** As a 现场经理, I want to 在D4底稿任意位置发起和查看复核对话, so that 我能针对具体数据点与审计助理进行复核讨论。

#### Acceptance Criteria

1. THE 各sheet审计说明/结论区域 SHALL 固定放置复核对话入口按钮（💬图标），点击调用openReviewDialog（sectionId自动生成为`D4-{sheetCode}-note`）
2. THE 各sheet表格 SHALL 支持单元格右键菜单"发起复核对话"（@cell-contextmenu → openReviewDialog，sectionId自动生成为`D4-{sheetCode}-{rowKey}-{field}`）
3. WHEN 有活跃复核线程时, THE 各sheet SHALL 在对应位置显示蓝色圆点（待回复）或红色圆点（有新回复）标记
4. THE 复核对话 SHALL 特别关注以下高风险区域（红色圆点优先级更高）：D4-17/D4-18截止测试跨期行、D4-20大额退货行、D4-24第三方回款行、D4-32资金回流可疑行
5. THE 各sheet SHALL 通过inject方式获取openReviewDialog函数（由GtD4OperatingRevenue.vue在provide层统一注入）

### Requirement 23: 双模式切换

**User Story:** As a 审计助理, I want to 在HTML精美组件和OnlyOffice编辑模式之间切换, so that 我能根据需要选择最适合的编辑方式。

#### Acceptance Criteria

1. THE Dual_Mode SHALL 在每个二级Tab页头部显示el-segmented切换控件（"结构化视图" | "在线编辑"）
2. WHEN 用户切换到OnlyOffice模式时, THE Dual_Mode SHALL 打开完整xlsx文件并通过OnlyOffice API隐藏非当前sheet（SetVisible(false)），只显示当前Tab对应的sheet
3. WHEN 用户从OnlyOffice模式切回HTML模式时, THE Dual_Mode SHALL 重新加载checklist_responses数据以反映在OO中的编辑
4. WHILE OnlyOffice服务不可用时, THE Dual_Mode SHALL 禁用"在线编辑"选项并显示tooltip"OnlyOffice服务不可用"
5. THE Dual_Mode SHALL 保留跨sheet公式完整性（不拆分文件），OO模式下用户仍可查看跨sheet公式计算结果
6. THE Dual_Mode SHALL 对8个源xlsx文件分别管理OO配置，根据当前二级Tab确定打开哪个xlsx文件的哪个sheet

### Requirement 24: 持久化与数据存储

**User Story:** As a 审计助理, I want to 所有编辑内容自动保存, so that 我不会因为意外关闭页面而丢失数据。

#### Acceptance Criteria

1. THE D4 组件 SHALL 使用 checklist_responses 表存储所有sheet数据，item_id前缀统一为"D4-{sheetCode}-{field}"格式（如D4-1-adj-row1-current-unadj, D4-2-rows, D4-5-step1-conclusion）
2. THE Dynamic_Row 类型sheet（D4-2/D4-3/D4-4/D4-12/D4-14~D4-20/D4-21~D4-32/D4-33~D4-36）SHALL 以JSON数组格式存储动态行于remark字段
3. WHEN 用户编辑任意金额/文本字段后2秒无操作时, THE Formula_Engine SHALL 触发debounce自动保存
4. WHEN 用户切换结论/选择类字段（Y/N/NA/下拉）时, THE Formula_Engine SHALL 立即保存该字段
5. THE D4 组件 SHALL 在保存成功后以淡绿色闪烁反馈，保存失败时ElMessage.warning提示
6. THE D4 组件 SHALL 在数据加载期间显示el-skeleton占位动画

### Requirement 25: 金额格式化与UI美化

**User Story:** As a 审计助理, I want to 所有金额数据以标准格式显示, so that 我能快速准确地阅读和核对数据。

#### Acceptance Criteria

1. THE Formula_Engine SHALL 对所有金额单元格应用 displayPrefs.fmtAmount 格式化（千分位分隔、保留2位小数）
2. WHEN 金额为负数时, THE Formula_Engine SHALL 以红色字体和括号格式显示（如 (1,234.56)）
3. WHEN 金额为零时, THE Formula_Engine SHALL 显示"-"而非"0.00"
4. THE 各分析表 SHALL 对比例列应用百分比格式（保留2位小数，如 12.34%）
5. THE Revenue_Detail SHALL 对"项目"列左对齐、对金额列右对齐
6. WHILE 数据正在加载时, THE D4 组件 SHALL 在表格区域显示el-skeleton占位动画
7. THE D4 组件 SHALL 统一使用displayPrefs.fmtDateTime格式化所有时间戳显示
8. THE D4 组件 SHALL 对变动比例超阈值的单元格应用红色高亮（>30%）、黄色高亮（>20%）的分级预警色

### Requirement 26: 后端Render策略与Resolver注册

**User Story:** As a 开发者, I want to D4底稿的后端渲染策略和auto_data resolver正确注册, so that render-config API能返回正确数据且TB自动取数功能正常工作。

#### Acceptance Criteria

1. THE RENDERER_DISPATCH SHALL 注册'd4-operating-revenue' componentType对应的render策略函数`_render_d4_operating_revenue`
2. THE render策略函数 SHALL 返回包含审定表双区块结构+明细表行数据+各sheet配置+分组信息的完整html_data
3. THE auto_data_resolvers._REGISTRY SHALL 注册`d4_tb_unadjusted` resolver（从trial_balance科目6001+6051取本期/上期未审数）
4. THE auto_data_resolvers._REGISTRY SHALL 注册`d4_ledger_monthly` resolver（从tb_ledger科目6001按月汇总各产品发生额）
5. THE auto_data_resolvers._REGISTRY SHALL 注册`d4_analysis_indicators` resolver（从trial_balance取多科目余额计算指标：毛利率/周转率/应收占比等）
6. THE account_package_registry.json SHALL 包含D4_operating_revenue工作包定义（sheets清单对齐36个有效sheet+source_wp_code映射8个xlsx来源）
7. THE render策略函数 SHALL 根据项目business_category字段在html_data中标记IPO/舞弊组的可见性（visible_groups字段）

### Requirement 27: D4-2产品行与D4-1审定表行结构同步

**User Story:** As a 审计助理, I want to D4-2明细表产品行增减时D4-1审定表对应行自动同步, so that 两张表的产品行始终保持一致不需手工对齐。

#### Acceptance Criteria

1. WHEN D4-2 Revenue_Detail 新增一个产品行时, THE Cross_Sheet_Engine SHALL 自动在D4-1 Adjudication_Table "主营业务收入"区块同步新增对应产品行（label取D4-2的product字段值）
2. WHEN D4-2 Revenue_Detail 删除一个产品行时, THE Cross_Sheet_Engine SHALL 自动在D4-1 Adjudication_Table 同步删除对应行（前提：该行AJE/RJE为零，否则弹出确认对话）
3. WHEN D4-3 Other_Revenue_Detail 新增/删除一个项目行时, THE Cross_Sheet_Engine SHALL 同步在D4-1"其他业务收入"区块执行相同操作
4. THE Adjudication_Table SHALL 标识哪些行来自D4-2/D4-3同步（isFromCrossSheet=true），这些行的"项目"列不可在D4-1直接编辑（需回D4-2/D4-3修改产品/项目名称）

### Requirement 28: 附注成本数据跨循环取数

**User Story:** As a 审计助理, I want to 附注披露的"营业成本"列自动从M循环(主营业务成本)取数, so that 我不需要手工复制成本数据到附注表。

#### Acceptance Criteria

1. THE Disclosure_Listed 和 Disclosure_SOE 第(1)子节"营业成本"列 SHALL 通过auto_data_source resolver从trial_balance（科目6401主营业务成本+6402其他业务成本）自动获取本期/上期审定发生额
2. WHILE 成本数据从TB取数成功时, THE Disclosure_Listed SHALL 以浅蓝色背景标记成本单元格并tooltip"取自TB科目6401/6402"
3. WHILE TB中尚无成本科目数据时, THE Disclosure_Listed SHALL 在成本列显示"待M循环审定"灰色占位文字
4. THE Formula_Engine SHALL 自动计算每行毛利=收入-成本、毛利率=(收入-成本)/收入×100%

### Requirement 29: 修订前程序表Skip与出口/境外适用性

**User Story:** As a 开发者, I want to 旧版程序表跳过渲染且出口/境外sheet有适用性控制, so that 不相关的sheet不干扰用户。

#### Acceptance Criteria

1. THE "主营业务收入审计程序表D4A（修订前）" sheet SHALL 在wp_code_overrides中映射为skip，不渲染为任何Tab
2. THE Export_Check (D4-16) SHALL 根据项目是否有出口业务（project_context.has_export_business）控制二级Tab可见性，无出口业务时隐藏该Tab
3. THE Overseas_Check (D4-26) SHALL 根据同一has_export_business字段控制可见性
4. WHEN 隐藏的Tab被访问时（通过GtIndexChip或URL参数）, THE D4 组件 SHALL 显示提示"该检查表不适用于当前项目（无出口业务）"

### Requirement 30: 访谈记录与核对示例D4-31B HTML渲染

**User Story:** As a 审计助理, I want to 在精美HTML组件中按模板格式记录客户走访与核对, so that 我能结构化记录走访公司基本信息、交易核实和现场观察。

#### Acceptance Criteria

1. THE "访谈记录与核对示例" sheet SHALL 渲染为卡片式QA结构：走访公司基本信息区（工商信息+经营场所+人员规模）+ 交易核实区（交易金额/品种/定价/回款确认）+ 现场观察区（经营场地/库存/生产能力）+ 结论区
2. WHEN 用户点击"新建走访记录"按钮时, THE Interview_Detail SHALL 基于此模板sheet创建一份新的走访记录实例（支持多客户多次走访）
3. THE "访谈记录与核对示例" sheet SHALL 在IPO/舞弊组Tab内显示，与D4-31共同服务于客户走访场景
4. THE "访谈记录与核对示例" sheet SHALL 在每个区域的textarea旁提供🤖AI按钮，基于走访公司工商信息自动预填基本情况+生成建议问题

### Requirement 31: 统一底稿目录Tab

**User Story:** As a 审计助理, I want to 8个源文件的底稿目录合并为一个统一目录, so that 我能在一个位置看到D4全部42个sheet的索引和编制进度。

#### Acceptance Criteria

1. THE D4 组件 SHALL 在一级Tab"核心"组的第一个二级Tab位置渲染统一底稿目录（合并8个源文件的底稿目录sheet内容）
2. THE 统一底稿目录 SHALL 显示完整sheet清单（42行）：序号|底稿名称|编码|编制人|编制日期|复核人|复核日期|页次|适用性标记
3. THE 统一底稿目录 SHALL 在每行底稿名称处提供GtIndexChip，点击跳转至对应二级Tab
4. THE 统一底稿目录 SHALL 自动标记不适用的sheet行为灰色（如D4-16出口核对在无出口业务项目中灰显）
5. THE 统一底稿目录 SHALL 显示整体编制进度（已完成sheet数/适用sheet总数，进度条可视化）
