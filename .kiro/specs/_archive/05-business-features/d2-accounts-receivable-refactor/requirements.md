# Requirements Document: D2 应收账款底稿精细化组件拆分

## Introduction

D2应收账款底稿的精细化组件拆分升级。将现有 `useD2AccountsReceivable.ts`（1123行）巨型composable拆分为多个独立子组件+子composable，每文件200-400行。参照D1应收票据的6个spec拆分模式，D2来自3个源xlsx共22个有效sheet，合并到一个统一入口下，按功能域分为审定表组、检查组、ECL组、分析组、附注组和通用架构六个章节。所有sheet做HTML精美组件（el-table + 金额格式化 + 动态行），OnlyOffice仅作降级切换。

## Glossary

- **Adjudication_Table**: 审定表D2-1，汇总应收账款按三分类（单项计提/账龄组合/客户类型组合）的审定数据，311个公式
- **Detail_Table**: 明细表D2-2，39列宽表（客户×账龄×金额×调整×分类），核心数据源
- **Bad_Debt_Table**: 坏账准备明细表D2-3，14列（期初4+增加2+减少3+期末4+项目名）
- **Adjustment_Table**: 调整分录汇总表D2-4，10列（调整事项/类别/报表项目/科目/附注/借方/贷方/索引/备注）
- **Analysis_Table**: 应收账款分析表D2-5，63个公式（周转天数/比率等分析指标）
- **Related_Party_Check**: 关联方及交易检查表D2-6，12列
- **Voucher_Check**: 应收账款检查表D2-7，17列凭证抽查（含抽样参数区+凭证抽样明细表）
- **Policy_Check**: 坏账准备计提会计政策检查D2-8，46行×9列段落型（含ECL模型/减值迹象/同行比较）
- **ECL_Calculation**: 应收坏账准备测算D2-9，单项计提8列+57个公式
- **ECL_Measurement**: 预期信用损失计量测试D2-10，单项折现+组合迁徙率矩阵，198个公式
- **Writeoff_Check**: 坏账准备转回核销检查表D2-11，转回区8列+核销区8列双段结构
- **Pledge_Check**: 应收账款质押出售情况检查表D2-12，9列+保理终止确认区
- **BizModel_Check**: 应收账款业务模式分析D2-13，QA问答→业务模式判定→报表项目分类
- **Disclosure_Note**: 附注披露，4个版本（上市D2-1×2源文件 + 国企D2-1×2源文件），合计191+170+158+113=632个公式
- **Procedure_Table**: 程序表D2A，序号/审计程序/程序分类/审计目标/索引号
- **SUMIF_Engine**: SUMIF聚合引擎，从D2-2按"信用风险组合方式"(AI列)聚合到D2-1审定表
- **Cross_Sheet_Engine**: 跨sheet公式引擎，D2-2→D2-1/D2-3↔D2-9/D2-10→D2-9
- **Dynamic_Row**: 动态行，用户可新增/删除的数据行
- **Dual_Mode**: 双模式切换，HTML精美组件 ↔ OnlyOffice在线编辑
- **Import_Export_Three_Level**: 导入导出三级：导出空模板→离线填写→导入解析
- **Formula_Engine**: 前端公式引擎，composable内公式自动计算
- **Cutoff_Test**: 截止测试，跨期判定逻辑
- **Factoring_Analysis**: 保理分析，终止确认判定（CAS 23）

## Requirements

### Requirement 1: 审定表D2-1 HTML渲染与SUMIF联动

**User Story:** As a 审计助理, I want to 在精美HTML表格中查看审定表D2-1并自动从D2-2明细表SUMIF聚合, so that 三分类（单项计提/账龄组合/客户类型组合）的审定数据自动汇总无需手工复制。

#### Acceptance Criteria

1. THE Adjudication_Table SHALL 渲染为固定行结构：单项计提 | 账龄组合 | 客户类型组合 | 合计行，列为：项目 | 期初数(未审/AJE/RJE/审定) | 期末数(未审/AJE/RJE/审定) | 本期与上期比较(变动额/变动率) | 原因分析
2. THE SUMIF_Engine SHALL 从 Detail_Table 按"信用风险组合方式"(AI列)值进行SUMIF聚合，聚合S列(期末未审余额)、Z列(账项调整)、AA列(重分类调整)到 Adjudication_Table 对应分类行
3. WHEN Detail_Table 数据变更时, THE SUMIF_Engine SHALL 在2秒内重新聚合并刷新 Adjudication_Table 对应行的SUMIF值
4. THE Formula_Engine SHALL 自动计算每行审定数（= 未审 + AJE + RJE，源模板公式对应列B+C+D=E）
5. THE Formula_Engine SHALL 自动计算合计行（= SUM三分类行各列）
6. WHEN 期初审定数和期末审定数均存在时, THE Formula_Engine SHALL 自动计算变动额（=期末审定-期初审定）和变动率（=(期末-期初)/期初，期初=0特殊处理）
7. WHEN 变动率绝对值超过30%时, THE Adjudication_Table SHALL 以红色高亮显示该比例单元格
8. WHILE SUMIF引用值生效时, THE Adjudication_Table SHALL 以浅蓝色背景标记SUMIF自动取数单元格，并在tooltip显示"取自D2-2按信用风险组合方式聚合"
9. THE Adjudication_Table SHALL 在表尾显示试算平衡表差异行（=审定数 - 试算表数），差异不为零时红色高亮
10. WHEN 审定数计算完成且发生变化时, THE Adjudication_Table SHALL 调用 writebackTrialBalance 将最新审定数回写 trial_balance.audited_amount（科目1122）

### Requirement 2: 明细表D2-2 HTML渲染（39列宽表）

**User Story:** As a 审计助理, I want to 在精美HTML宽表中管理应收账款客户明细, so that 我能在横向滚动的语义化表格中编辑39列数据而非裸OnlyOffice。

#### Acceptance Criteria

1. THE Detail_Table SHALL 以el-table横向滚动渲染39列：序号|客户名称|公司代码|关联方类型|期初未审余额|期初AJE|期初RJE|期初审定余额|期初审定账龄(6档)|借方发生|贷方发生|期末余额|重分类|期末未审余额|期末未审账龄(6档)|AJE|RJE|期末审定余额|期末审定账龄(6档)|信用风险组合方式|组合名称|是否函证|期后回款|备注
2. THE Detail_Table SHALL 对金额列应用右对齐+金额格式化（千分位/负数红色括号/零值"-"），对日期列应用日期选择器，对"关联方类型"列应用下拉选择（非关联方/控股股东/实际控制人/其他关联方）
3. THE Detail_Table SHALL 对"信用风险组合方式"(AI列)应用下拉选择（单项计提/账龄组合/客户类型组合），此列为SUMIF聚合的key
4. WHEN 用户点击"添加客户"按钮时, THE Detail_Table SHALL 在合计行上方新增一个可编辑空行
5. WHEN 用户输入客户名称时, THE Detail_Table SHALL 自动从 related_parties 表模糊匹配关联方信息并填充"关联方类型"列
6. WHEN 关联方类型列为非"非关联方"时, THE Detail_Table SHALL 以橙色背景高亮该行
7. THE Formula_Engine SHALL 自动计算每行：期初审定=期初未审+AJE+RJE；期末余额=期初审定+借方-贷方；期末未审=期末余额+重分类；期末审定=期末未审+AJE+RJE
8. THE Detail_Table SHALL 在底部显示合计行（=SUM所有客户行各金额列），合计行不可编辑
9. THE Detail_Table SHALL 支持按客户名称模糊搜索筛选行（搜索框在表头上方）
10. WHEN 动态行超过30行时, THE Detail_Table SHALL 启用虚拟滚动以保证渲染性能
11. THE Detail_Table SHALL 固定前2列（序号/客户名称）使横向滚动时仍可辨识行

### Requirement 3: 坏账准备明细表D2-3 HTML渲染

**User Story:** As a 审计助理, I want to 在精美HTML表格中查看和编辑坏账准备变动明细, so that 我能清晰追踪坏账准备的计提、转入、收回、转回和核销变动。

#### Acceptance Criteria

1. THE Bad_Debt_Table SHALL 显示14列：项目 | 期初数(未审/AJE/RJE/审定) | 本期增加(计提/转入) | 本期减少(收回/转回/核销) | 期末数(未审/AJE/RJE/审定)
2. THE Bad_Debt_Table SHALL 预设固定行结构：按单项计提（可展开子行）+ 按账龄组合计提（可展开子行）+ 按客户类型组合计提（可展开子行）+ 合计行
3. THE Formula_Engine SHALL 自动计算期初审定数（=期初未审+AJE+RJE）和期末审定数（=期末未审+AJE+RJE）
4. THE Formula_Engine SHALL 自动计算期末未审数（=期初审定+本期计提+转入-收回-转回-核销）
5. THE Bad_Debt_Table SHALL 在底部显示合计行（=SUM全部子行），合计行不可编辑
6. WHEN 坏账准备合计数与 ECL_Calculation 测算结果不一致时, THE Bad_Debt_Table SHALL 在合计行旁显示黄色警告"与D2-9 ECL测算差异: ±xxx元"
7. WHEN 用户点击分类行的展开按钮时, THE Bad_Debt_Table SHALL 允许添加子行（明细债务人）

### Requirement 4: 调整分录汇总表D2-4 HTML渲染

**User Story:** As a 审计助理, I want to 在精美HTML表格中录入和管理调整分录, so that 我能快速创建AJE/RJE并联动审定表和A13错报汇总。

#### Acceptance Criteria

1. THE Adjustment_Table SHALL 显示10列：调整事项说明 | 类别(AJE/RJE) | 报表项目 | 科目名称 | 附注项目 | 借方调整金额 | 贷方调整金额 | 索引 | 备注
2. WHEN 用户点击"新增调整分录"按钮时, THE Adjustment_Table SHALL 新增一行可编辑空行
3. THE Adjustment_Table SHALL 在底部显示借贷合计行，借方合计=贷方合计时显示绿色"✓平衡"，否则红色"✗不平衡：差额xxx"
4. WHEN 调整分录保存成功时, THE Adjustment_Table SHALL 通过EventBus发布'adjustment:created'事件（payload含wpCode/entryType/amount）
5. THE Adjustment_Table SHALL 双向同步AJE/RJE合计到 Adjudication_Table 对应列
6. WHEN 用户点击"推送至A13"按钮时, THE Adjustment_Table SHALL 将选中分录通过EventBus发布至A13错报汇总

### Requirement 5: 分析程序D2-5 HTML渲染

**User Story:** As a 审计助理, I want to 在精美HTML组件中查看应收账款分析指标, so that 我能直观判断应收账款周转率、坏账率等指标是否异常。

#### Acceptance Criteria

1. THE Analysis_Table SHALL 显示为卡片式布局，含以下分析指标区块：应收账款周转率 | 周转天数 | 本期vs上期对比 | 坏账计提比率 | 账龄分布占比 | 前五大客户集中度
2. THE Formula_Engine SHALL 自动计算：周转率=营业收入/平均应收账款；周转天数=365/周转率；坏账率=坏账准备/应收账款余额
3. WHEN 周转天数较上期变动超过30%时, THE Analysis_Table SHALL 显示黄色警告标签"周转天数异常波动"
4. THE Analysis_Table SHALL 从试算平衡表自动获取营业收入和应收账款余额用于计算（通过auto_data_source resolver）
5. THE Analysis_Table SHALL 支持手动输入数据来源和备注说明

### Requirement 6: 关联方及交易检查表D2-6 HTML渲染

**User Story:** As a 审计助理, I want to 在精美HTML表格中记录关联方应收账款检查, so that 我能追踪每个关联方的期初/期末余额和期后回款情况。

#### Acceptance Criteria

1. THE Related_Party_Check SHALL 显示12列：关联方名称 | 关联关系 | 期初余额 | 借方发生 | 贷方发生 | 期末余额 | 减：坏账准备 | 账面价值 | 发生时间及账龄 | 发生原因（款项性质）| 期后回款 | 索引号
2. WHEN 用户点击"添加关联方"按钮时, THE Related_Party_Check SHALL 新增一行，并自动从项目关联方清单下拉匹配
3. THE Formula_Engine SHALL 自动计算：期末余额=期初+借方-贷方；账面价值=期末余额-坏账准备
4. THE Related_Party_Check SHALL 在底部显示合计行（期初/借方/贷方/期末/坏账/账面各列SUM）
5. THE Related_Party_Check SHALL 支持从D2-2明细表按"关联方类型≠非关联方"自动导入关联方行

### Requirement 7: 应收账款检查表D2-7（凭证抽查）HTML渲染

**User Story:** As a 审计助理, I want to 在精美HTML组件中执行凭证抽样检查, so that 我能记录抽样参数和逐笔核对凭证信息。

#### Acceptance Criteria

1. THE Voucher_Check SHALL 分为两区块：抽样参数区（抽样总体/特定样本/确定样本量/抽取方式）+ 凭证抽样明细表
2. THE Voucher_Check 凭证抽样明细表 SHALL 显示17列：序号 | 凭证号 | 凭证日期 | 摘要 | 借方金额 | 贷方金额 | 对方科目 | 发票号 | 发票日期 | 发票金额 | 合同编号 | 出库单号 | 客户确认 | 账龄核实 | 异常标记 | 结论 | 索引号
3. WHEN 用户点击"添加样本"按钮时, THE Voucher_Check SHALL 新增一行凭证抽样明细
4. THE Voucher_Check SHALL 在参数区显示：已抽取样本数/目标样本量，进度条可视化
5. WHEN 凭证日期与对应收入确认日期跨期时, THE Voucher_Check SHALL 自动标记"异常标记"列为"跨期"
6. THE Voucher_Check SHALL 在底部汇总：已检查笔数/发现异常笔数/异常率

### Requirement 8: 坏账准备计提会计政策检查D2-8（段落型）HTML渲染

**User Story:** As a 审计助理, I want to 在结构化段落组件中检查坏账准备政策合规性, so that 我能逐项确认ECL模型、减值迹象、同行比较等政策条款。

#### Acceptance Criteria

1. THE Policy_Check SHALL 渲染为段落型卡片布局（非el-table），按源模板46行×9列分为以下政策段落：ECL模型说明 | 信用风险显著增加判断标准 | 减值迹象识别 | 会计估计变更 | 同行业比较 | 预期信用损失率确定方法
2. THE Policy_Check 每个段落 SHALL 包含：政策条款描述（左栏只读）| 被审计单位实际情况（右栏可编辑textarea）| 审计师评价（下方可编辑textarea）| 结论（Y/N/NA radio）
3. WHEN 某段落结论为"N"（不符合）时, THE Policy_Check SHALL 以红色边框高亮该段落并显示"需关注"标签
4. THE Policy_Check SHALL 在顶部显示政策检查进度：已完成段数/总段数
5. THE Policy_Check SHALL 支持"编制提示"折叠区（`<details>`蓝色左边线+浅蓝背景，默认收起）展示源模板中的红色提示文字

### Requirement 9: 应收坏账准备测算D2-9（单项ECL）HTML渲染

**User Story:** As a 审计助理, I want to 在精美HTML表格中测算单项应收坏账准备, so that 我能逐笔比对应计提与实际计提的差异。

#### Acceptance Criteria

1. THE ECL_Calculation SHALL 显示8列：债务人名称 | 审定账面余额 | 预期信用损失率 | 期末应计提坏账准备 | 期末坏账准备账面余额 | 差异 | 计提依据及文件 | 索引号
2. THE Formula_Engine SHALL 自动计算：期末应计提=审定余额×损失率；差异=实际账面余额-应计提
3. WHEN 差异绝对值超过重要性水平时, THE ECL_Calculation SHALL 以红色高亮差异单元格
4. THE ECL_Calculation SHALL 在底部显示合计行（余额/应计提/实际/差异各列SUM）
5. THE ECL_Calculation SHALL 从D2-3坏账准备明细表自动获取"期末坏账准备账面余额"列数据（跨sheet引用）
6. WHEN 用户点击"添加债务人"按钮时, THE ECL_Calculation SHALL 新增一行单项计提明细
7. THE ECL_Calculation SHALL 支持从D2-2中筛选"信用风险组合方式=单项计提"的客户自动导入

### Requirement 10: 预期信用损失计量测试D2-10 HTML渲染

**User Story:** As a 审计助理, I want to 在精美HTML组件中执行ECL计量测试（含单项折现和组合迁徙率）, so that 我能验证被审计单位ECL率的合理性。

#### Acceptance Criteria

1. THE ECL_Measurement SHALL 分为两个区块：单项计量测试区 + 组合（迁徙率）计量测试区
2. THE ECL_Measurement 单项区 SHALL 显示：债务人名称 | 账面余额 | 不同情形下的未来现金流量 | 折现值 | 发生概率 | 概率加权(=折现值×概率) | 预期信用损失率 | 结论
3. THE Formula_Engine SHALL 自动计算单项区：概率加权=折现值×概率；损失率=1-ΣPV/余额
4. THE ECL_Measurement 组合区 SHALL 显示迁徙率矩阵：账龄段 | 年度1迁徙率 | 年度2迁徙率 | 年度3迁徙率 | 三年平均迁徙率 | 预期损失率（连乘）
5. THE Formula_Engine SHALL 自动计算组合区：三年平均=AVG(年1,年2,年3)；预期损失率=各段平均迁徙率连乘（calcExpectedLossRate）
6. THE ECL_Measurement SHALL 将计算出的预期损失率自动输出到D2-9的"预期信用损失率"列（跨sheet联动）
7. WHEN 组合迁徙率与上期相比变动超过20%时, THE ECL_Measurement SHALL 在对应单元格旁显示黄色变动提示

### Requirement 11: 坏账准备转回核销检查表D2-11 HTML渲染

**User Story:** As a 审计助理, I want to 在精美HTML组件中检查大额坏账准备转回和核销, so that 我能验证转回/核销的合理性依据。

#### Acceptance Criteria

1. THE Writeoff_Check SHALL 分为两个段表：转回区 + 核销区
2. THE Writeoff_Check 转回区 SHALL 显示8列：单位名称 | 转回原因 | 收回方式 | 原确定坏账准备的依据 | 收回或转回金额 | 收回前累计已计提坏账准备金额 | 合理性分析 | 索引号
3. THE Writeoff_Check 核销区 SHALL 显示类似8列：单位名称 | 核销原因 | 核销审批程序 | 原确定坏账准备的依据 | 核销金额 | 核销前累计已计提金额 | 合理性分析 | 索引号
4. WHEN 用户点击"添加转回/核销"按钮时, THE Writeoff_Check SHALL 在对应区域新增一行
5. THE Writeoff_Check SHALL 在每个区域底部显示合计行（金额列SUM）
6. THE Writeoff_Check 转回合计 SHALL 与D2-3"本期减少-转回"列数据保持一致，不一致时黄色警告

### Requirement 12: 应收账款质押出售情况检查表D2-12 HTML渲染

**User Story:** As a 审计助理, I want to 在精美HTML组件中检查应收账款质押和保理情况, so that 我能评估受限资产和终止确认的合规性。

#### Acceptance Criteria

1. THE Pledge_Check SHALL 分为两个区块：质押情况检查区 + 保理终止确认区
2. THE Pledge_Check 质押区 SHALL 显示9列：客户名称 | 期末余额 | 质押金额 | 质权人 | 质押原因 | 质押条件 | 质押期限 | 质押协议 | 索引号
3. THE Pledge_Check 保理区 SHALL 显示：客户名称 | 保理金额 | 保理商 | 合同号 | 是否转移风险(Y/N) | 是否保留控制(Y/N) | 终止确认结论 | 备注
4. THE Formula_Engine SHALL 按CAS 23自动判定终止确认：转移风险=Y→终止确认；转移风险=N且保留控制=N→终止确认；其余→不终止确认
5. THE Pledge_Check SHALL 计算质押比例（=质押总额/应收账款审定总额），超过50%时显示红色警告"质押比例过高"
6. WHEN 用户点击"添加质押/保理"按钮时, THE Pledge_Check SHALL 在对应区域新增一行

### Requirement 13: 应收账款业务模式分析D2-13 HTML渲染

**User Story:** As a 审计助理, I want to 在QA问答式组件中分析应收账款业务模式, so that 我能判定不同组合的管理模式并确定报表分类。

#### Acceptance Criteria

1. THE BizModel_Check SHALL 渲染为QA问答式卡片布局，包含4个判断题区 + 业务模式判定区 + 报表项目分类区
2. THE BizModel_Check 判断题区 SHALL 包含4个Y/N判断问题（是否存在收取合同现金流为目标/是否存在出售应收款/是否同时存在/是否存在SPPI不满足），每题含依据textarea
3. THE BizModel_Check 业务模式判定区 SHALL 显示5列：组合名称 | 管理业务模式 | 具体依据 | 索引号 | 备注
4. WHEN 4个判断题全部回答后, THE BizModel_Check SHALL 自动推荐业务模式分类（收取合同现金流/出售/两者兼有）
5. THE BizModel_Check 报表项目分类 SHALL 显示每个组合对应的报表项目（应收账款/应收款项融资/其他应收款）
6. THE BizModel_Check SHALL 将业务模式判定结果联动影响附注披露中的分类展示

### Requirement 14: 截止测试HTML渲染

**User Story:** As a 审计助理, I want to 在精美HTML组件中执行收入截止测试, so that 我能识别资产负债表日前后的跨期收入及对应应收账款。

#### Acceptance Criteria

1. THE Cutoff_Test SHALL 显示动态表格：序号 | 发票号 | 收入确认日期 | 应收账款入账日期 | 金额 | 跨期判定 | 结论 | 备注
2. THE Formula_Engine SHALL 自动判定跨期：WHEN 收入确认日期 > 资产负债表日(年度12月31日), determineCutoff返回"跨期"
3. WHEN 存在跨期样本时, THE Cutoff_Test SHALL 在表头显示红色警告"发现N笔跨期，合计金额xxx"
4. WHEN 用户点击"添加样本"按钮时, THE Cutoff_Test SHALL 新增一行截止测试样本
5. THE Cutoff_Test SHALL 在底部汇总：已检查笔数 | 跨期笔数 | 跨期金额合计

### Requirement 15: 附注披露HTML渲染（4版本动态切换）

**User Story:** As a 审计助理, I want to 在精美HTML组件中编辑附注披露信息并支持上市/国企双版本切换, so that 我能按企业类型选择对应的披露模板并逐项核对。

#### Acceptance Criteria

1. THE Disclosure_Note SHALL 支持4个版本动态切换：上市公司D2-1(191公式) | 国企D2-1(170公式) | 上市公司账龄(158公式) | 国企账龄(113公式)
2. THE Disclosure_Note SHALL 在顶部提供el-segmented切换控件（"上市公司" | "国企"），切换后渲染对应版本模板
3. THE Disclosure_Note 上市公司版 SHALL 显示：分类余额表（金额/比例%/坏账准备/计提比例%/净额）+ 账龄分析表（账龄/期末余额/上年年末余额）+ 坏账准备变动表 + 前五大 + 关联方
4. THE Disclosure_Note 国企版 SHALL 显示：分类余额表（账面余额/比例%/坏账准备/比例%）+ 账龄分析表（账龄/期末数/期初数）+ 坏账准备变动 + 受限资产
5. THE Formula_Engine SHALL 自动计算比例列（=单项金额/合计金额×100%）、净额列（=金额-坏账准备）
6. THE Disclosure_Note SHALL 从 Adjudication_Table 和 Bad_Debt_Table 自动获取审定数填入对应行（跨sheet引用）
7. WHEN 披露金额与审定表数据不一致时, THE Disclosure_Note SHALL 在差异单元格显示黄色警告tooltip

### Requirement 16: 程序表D2A HTML渲染

**User Story:** As a 审计助理, I want to 在卡片式程序表中跟踪审计步骤执行进度, so that 我能清晰看到每个审计程序的状态、执行人和关联底稿。

#### Acceptance Criteria

1. THE Procedure_Table SHALL 以卡片式布局渲染7个审计步骤，每步含：步骤序号 | 审计程序描述 | 程序分类 | 审计目标 | 状态(未开始/执行中/已完成/不适用) | 执行人 | 日期 | 发现 | 结论 | 索引号跳转
2. THE Procedure_Table SHALL 在顶部显示进度条（已完成步骤数/总步骤数）
3. WHEN B50风险评估事件'risk:assessed'接收时, THE Procedure_Table SHALL 在对应步骤旁显示风险等级标签（高H红/中M黄/低L绿）
4. WHEN C3控制测试事件'control:test-concluded'接收时, THE Procedure_Table SHALL 在控制测试相关步骤旁显示控制结论提示
5. WHEN 所有必要步骤均为"已完成"或"不适用"时, THE Procedure_Table SHALL 启用整体审计结论textarea
6. THE Procedure_Table SHALL 每步的索引号跳转可点击（GtIndexChip）定位到关联的子Tab

### Requirement 17: 双模式切换

**User Story:** As a 审计助理, I want to 在HTML精美组件和OnlyOffice编辑模式之间切换, so that 我能根据需要选择最适合的编辑方式。

#### Acceptance Criteria

1. THE Dual_Mode SHALL 在每个sheet的Tab页头部显示el-segmented切换控件（"结构化视图" | "在线编辑"）
2. WHEN 用户切换到OnlyOffice模式时, THE Dual_Mode SHALL 打开完整xlsx文件并通过OnlyOffice API隐藏非当前sheet（SetVisible(false)），只显示当前Tab对应的sheet
3. WHEN 用户从OnlyOffice模式切回HTML模式时, THE Dual_Mode SHALL 重新加载checklist_responses数据以反映在OO中的编辑
4. WHILE OnlyOffice服务不可用时, THE Dual_Mode SHALL 禁用"在线编辑"选项并显示tooltip"OnlyOffice服务不可用"
5. THE Dual_Mode SHALL 保留跨sheet公式完整性（不拆分文件），OO模式下用户仍可查看跨sheet公式计算结果

### Requirement 18: 持久化与数据存储

**User Story:** As a 审计助理, I want to 所有编辑内容自动保存, so that 我不会因为意外关闭页面而丢失数据。

#### Acceptance Criteria

1. THE Formula_Engine SHALL 使用 checklist_responses 表存储数据，各sheet使用独立item_id前缀：D2-adj-/D2-detail-/D2-bd-/D2-entry-/D2-cutoff-/D2-factoring-/D2-analysis-/D2-rp-/D2-check7-/D2-policy-/D2-ecl9-/D2-ecl10-/D2-writeoff-/D2-pledge-/D2-bizmodel-/D2-disc-
2. WHEN 用户编辑任意金额/文本字段后2秒无操作时, THE Formula_Engine SHALL 触发debounce自动保存
3. WHEN 用户切换结论/选择类字段时, THE Formula_Engine SHALL 立即保存该字段
4. THE Detail_Table SHALL 将动态行数据以JSON数组格式存储于单个remark字段（item_id="D2-detail-rows"），每行含所有39列值
5. THE Bad_Debt_Table SHALL 将动态行以JSON存储于remark字段（item_id="D2-bd-individual-rows"/"D2-bd-aging-rows"/"D2-bd-customer-rows"）
6. THE Formula_Engine SHALL 保证Tab切换时localStorage持久化当前activeTab（key含wpId避免冲突）

### Requirement 19: 导入导出三级

**User Story:** As a 审计助理, I want to 支持从Excel导入数据和导出模板, so that 我能利用已有的离线填写的数据批量录入（特别是D2-2的39列宽表）。

#### Acceptance Criteria

1. WHEN 用户点击"导出模板"按钮时, THE Import_Export_Three_Level SHALL 生成当前sheet对应的空白xlsx模板（含表头+格式+公式，无数据行）
2. WHEN 用户点击"导出数据"按钮时, THE Import_Export_Three_Level SHALL 生成包含当前数据的xlsx文件
3. WHEN 用户上传已填写的xlsx文件时, THE Import_Export_Three_Level SHALL 使用openpyxl解析文件内容，识别动态行数量，并将数据回写到checklist_responses
4. IF 导入的xlsx格式不符合模板结构, THEN THE Import_Export_Three_Level SHALL 显示错误提示并列出不匹配的列名
5. WHEN 导入D2-2（39列宽表）xlsx且行数超过模板预设行时, THE Import_Export_Three_Level SHALL 自动扩展动态行以容纳全部数据
6. THE Import_Export_Three_Level SHALL 在导入完成后显示摘要（"成功导入N行数据，M个字段已更新"）
7. THE Import_Export_Three_Level SHALL 支持D2-2/D2-3/D2-4/D2-6/D2-7/D2-9/D2-11/D2-12五个动态行sheet的导入导出

### Requirement 20: 组件拆分与代码架构

**User Story:** As a 开发者, I want to 将D2应收账款底稿逻辑拆分为独立子组件和子composable, so that 代码可维护性好、每个文件控制在200-400行、主composable降至~300行。

#### Acceptance Criteria

1. THE Adjudication_Table SHALL 拆分为独立Vue子组件 D2TabAdjudication.vue（200-400行）+ 独立composable useD2Adjudication.ts
2. THE Detail_Table SHALL 拆分为独立Vue子组件 D2TabDetail.vue（300-400行）+ 独立composable useD2Detail.ts
3. THE Bad_Debt_Table SHALL 拆分为独立Vue子组件 D2TabBadDebt.vue（200-400行）+ 独立composable useD2BadDebt.ts
4. THE Adjustment_Table SHALL 拆分为独立Vue子组件 D2TabAdjustment.vue（200-300行）+ 独立composable useD2Adjustment.ts
5. THE Analysis_Table SHALL 拆分为独立Vue子组件 D2TabAnalysis.vue（200-300行）+ 独立composable useD2Analysis.ts
6. THE ECL_Calculation 与 ECL_Measurement SHALL 合并拆分为独立Vue子组件 D2TabEcl.vue（300-400行）+ 独立composable useD2Ecl.ts
7. THE Related_Party_Check/Voucher_Check/Policy_Check/Writeoff_Check/Pledge_Check/BizModel_Check SHALL 各拆分为独立Vue子组件 D2TabXxx.vue + 独立composable useD2Xxx.ts
8. THE Cutoff_Test SHALL 拆分为独立Vue子组件 D2TabCutoff.vue + 独立composable useD2Cutoff.ts
9. THE Disclosure_Note SHALL 拆分为独立Vue子组件 D2TabDisclosure.vue（300-400行）+ 独立composable useD2Disclosure.ts
10. THE 拆分后主入口 useD2AccountsReceivable.ts SHALL 降至约300行，仅保留Tab管理+联动协调+EventBus监听
11. THE 共享公式 SHALL 提取为独立模块 useD2FormulaEngine.ts（~150行），含全部纯函数（getAuditedAmount/getChangeRate/calculateProvision/calculateDifference/calculatePledgeRatio/determineCutoff/sumif/calculateExpectedLossRate/parseNum）
12. THE 导入导出 SHALL 提取为独立模块 useD2ImportExport.ts（~200行），被各子组件复用

### Requirement 21: 联动与EventBus集成

**User Story:** As a 审计助理, I want to D2底稿与其他底稿自动联动, so that 审定数据在各模块间保持一致性。

#### Acceptance Criteria

1. WHEN 审定数计算完成且发生变化时, THE Adjudication_Table SHALL 通过EventBus发布'substantive:adjudicated'事件（payload含wpCode='D2'/accountCode='1122'/auditedAmount/priorAmount/changeRate）
2. WHEN EventBus接收'adjustment:created'事件时, THE Adjudication_Table SHALL 自动将对应AJE/RJE金额同步到审定表合计行
3. WHEN EventBus接收'risk:assessed'(B50)事件时, THE Procedure_Table SHALL 更新对应步骤的风险等级
4. WHEN EventBus接收'control:test-concluded'(C3)事件时, THE Procedure_Table SHALL 更新控制测试提示
5. WHEN D0函证完成事件接收时, THE Adjudication_Table SHALL 更新函证汇总面板数据
6. THE Adjudication_Table SHALL 在审定数回写成功后联动5个ref_chip（试算平衡表/D0函证/B50风险评估/C3控制测试/A13错报汇总）的状态刷新

### Requirement 22: 金额格式化与UI美化

**User Story:** As a 审计助理, I want to 所有金额数据以标准格式显示, so that 我能快速准确地阅读和核对数据。

#### Acceptance Criteria

1. THE Formula_Engine SHALL 对所有金额单元格应用 displayPrefs.fmtAmount 格式化（千分位分隔、保留2位小数、单位"元"）
2. WHEN 金额为负数时, THE Formula_Engine SHALL 以红色字体和括号格式显示（如 (1,234.56)）
3. WHEN 金额为零时, THE Formula_Engine SHALL 显示"-"而非"0.00"
4. THE Formula_Engine SHALL 对比例列应用百分比格式（保留2位小数，如 12.34%）
5. THE Detail_Table SHALL 对"客户名称"列左对齐、对金额列右对齐、对日期列居中
6. WHILE 数据正在加载时, THE Adjudication_Table SHALL 在表格区域显示el-skeleton占位动画
7. THE 所有子组件 SHALL 在表头工具栏统一显示：导出模板|导出数据|导入数据 三按钮 + 双模式切换el-segmented

### Requirement 23: D0函证→D2-2联动（函证完成自动标记）

**User Story:** As a 审计助理, I want to D0函证完成后自动标记D2-2明细表中对应客户的"是否函证"列, so that 我无需手工逐行核对哪些客户已完成函证。

#### Acceptance Criteria

1. WHEN EventBus接收'confirmation:completed'事件（payload含customerName/confirmationResult）时, THE Detail_Table SHALL 自动将D2-2中匹配客户名的行的"是否函证"(AK列)标记为"Y"
2. THE Detail_Table SHALL 使用客户名称模糊匹配（contains）来定位D2-2中的目标行，匹配到多行时全部标记
3. WHEN 函证标记更新后, THE Detail_Table SHALL 触发debounce自动保存
4. THE Detail_Table SHALL 在"是否函证"列被自动标记时以浅绿色背景高亮该单元格（区分手动标记）

### Requirement 24: D2-2从辅助余额表直接导入客户明细

**User Story:** As a 审计助理, I want to 从辅助余额表按科目1122+客户维度直接导入客户明细到D2-2, so that 我无需通过Excel中转即可快速获得客户级余额数据。

#### Acceptance Criteria

1. THE Detail_Table SHALL 在工具栏提供"从余额表导入"按钮，点击后调用 `GET /api/projects/{pid}/ledger/aux-balance-detail?account_code=1122&aux_type=customer`
2. THE Detail_Table SHALL 将辅助余额表返回的客户名称/期初余额/期末余额映射到D2-2的客户名称/期初未审余额/期末余额列
3. WHEN 导入数据中存在D2-2已有的客户名时, THE Detail_Table SHALL 以merge模式合并（按客户名去重，仅更新余额字段不覆盖已填的AJE/RJE/账龄等手工字段）
4. THE Detail_Table SHALL 在导入完成后显示摘要（"成功导入N个客户，更新M个余额字段，新增K个客户"）
5. WHEN 辅助余额表无1122科目客户维度数据时, THE Detail_Table SHALL 显示ElMessage.info"未找到应收账款客户辅助余额数据"

### Requirement 25: D2-5分析异常→A1-13分析性复核联动

**User Story:** As a 审计助理, I want to D2-5分析程序发现异常指标时自动推送到A1-13分析性复核底稿, so that 显著变动项能自动汇总到分析性复核总表。

#### Acceptance Criteria

1. WHEN D2-5周转天数变动率绝对值超过30%时, THE Analysis_Table SHALL 通过EventBus发布'analytical:significant-change'事件（payload含wpCode='D2'/indicator='turnover_days'/changeRate/currentValue/priorValue）
2. WHEN D2-5坏账计提比率变动率绝对值超过30%时, THE Analysis_Table SHALL 通过EventBus发布同样的'analytical:significant-change'事件
3. THE Analysis_Table SHALL 支持从 analytical_review_service 自动获取"本期vs上期"对比数据（复用A1-13/A1-14的resolver `analytical_review`），无需手动输入上期数

### Requirement 26: 复核对话通用集成

**User Story:** As a 现场经理, I want to 在D2底稿各Tab中随时发起复核对话, so that 我能对任何存疑的数据点直接与编制人沟通。

#### Acceptance Criteria

1. THE 所有D2子组件 SHALL 通过 `inject('openReviewDialog')` 集成通用复核对话能力（useReviewDialogProvider）
2. THE D2TabAdjudication SHALL 在"审计说明"和"审计结论"区域各放置一个💬固定入口按钮
3. THE D2TabPolicyCheck SHALL 在结论为"N"（不符合）的段落旁放置💬固定入口按钮
4. THE D2TabEcl SHALL 在差异超重要性水平的行旁放置💬固定入口按钮
5. THE D2TabVoucherCheck SHALL 在异常标记行的"结论"列支持右键"发起复核对话"
6. THE 所有el-table类子组件 SHALL 支持表格单元格右键菜单"发起复核对话"（@cell-contextmenu → openReviewDialog，sectionId自动生成为`D2-{tab}-{rowKey}-{field}`）
7. THE 所有子组件 SHALL 查询并显示有活跃对话线程的位置蓝/红圆点标记（从 `/api/review-threads/active?wp_id=` 获取）

### Requirement 27: 交叉索引GtIndexChip增强

**User Story:** As a 审计助理, I want to 在D2底稿各关键位置点击索引号可直接跳转到关联底稿, so that 我能快速追溯数据来源和关联依据。

#### Acceptance Criteria

1. THE D2TabAdjudication SHALL 在变动率>30%的"原因分析"列旁显示GtIndexChip跳转到D2-5分析程序Tab
2. THE D2TabBadDebt SHALL 在坏账准备"计提"列旁显示GtIndexChip跳转到D2-9 ECL测算对应债务人
3. THE D2TabRelatedParty SHALL 在"索引号"列显示GtIndexChip跳转到A17-1重大事项（关联方交易通常需汇报）
4. THE D2TabPledgeCheck SHALL 在"质押协议"列支持GtIndexChip跳转到对应合同（若有合同管理模块）
5. THE D2TabVoucherCheck SHALL 在"对方科目"列支持GtIndexChip跳转到对方科目对应底稿（如6001→D4收入底稿）
6. THE D2TabProcedure SHALL 每步的索引号列使用GtIndexChip可跳转到关联子Tab（如步骤3→D2-7凭证抽查Tab）
