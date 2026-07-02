# Requirements Document: F1 预付账款底稿专属HTML精美组件

## Introduction

F1预付账款底稿的专属HTML精美组件构建。将现有通用渲染升级为独立专属组件 `f1-prepayment`，覆盖源模板11个有效sheet（程序表F1A + 审定表F1-1 + 明细表F1-2 + 调整分录F1-3 + 实质性分析F1-4 + 长期挂款检查F1-5 + 关联方检查F1-6 + 综合检查F1-7 + 附注上市 + 附注国企 + 函证程序表G1A-修订前），合计约320个公式。科目编码1123预付账款（借方科目/资产类）。核心特色：审定表标准结构（期初/期末+变动分析）、11列明细表（含账龄/款项性质/函证结果）、实质性分析（余额变动/周转率/账龄分布）、长期挂款检查（账龄1年以上大额预付）、关联方交易检查、综合检查（合同/发票/入库/付款凭证核对）、附注披露（上市公司账龄表/国企简化版）、与F0存货循环函证联动。F循环中等复杂度底稿。结构简洁（11有效sheet），1级el-tabs 10个tab-pane：程序表/审定表/明细表/调整分录/实质性分析/长期挂款/关联方/综合检查/附注披露/函证程序。附注含上市+国企切换。

## Glossary

- **Adjudication_Table**: 审定表F1-1，标准结构（期初未审/期初调整/期初审定/期末未审/期末调整/期末审定/变动额/变动率/原因分析），93个公式
- **Detail_Table**: 明细表F1-2，11列（供应商名称/期初余额/本期增加/本期减少/期末余额/账龄/款项性质/审计调整/期末审定数/函证结果/备注），69个公式，核心数据源
- **Adjustment_Table**: 调整分录汇总表F1-3，6列标准格式动态行（调整事项说明/科目名称/借方金额/贷方金额/索引/备注）
- **Substantive_Analysis**: 实质性分析F1-4，余额变动分析/周转率分析/账龄分布分析，支撑审定表变动原因
- **Long_Term_Check**: 长期挂款检查表F1-5，账龄1年以上的大额预付账款检查（原因/可收回性/减值）
- **Related_Party_Check**: 关联关系及交易检查F1-6，14列（含坏账准备+账面价值），识别关联方预付
- **Comprehensive_Check**: 预付账款检查表F1-7，综合检查（合同/发票/入库/付款凭证核对），抽样参数区
- **Disclosure_Listed**: 附注披露信息（上市公司），账龄分析表，按1年以内/1-2年/2-3年/3年以上分组
- **Disclosure_SOE**: 附注披露信息（国企），简化版账龄表
- **Procedure_Table**: 实质性程序表F1A，审计程序+审计目标（复用a-program-console）
- **Confirmation_Procedure**: 函证程序表G1A-修订前，采购循环函证程序（来自F0存货循环函证）
- **Cross_Sheet_Engine**: 跨sheet公式引擎，F1-2→F1-1明细聚合、F1-3→F1-1调整聚合、F1-4→F1-1分析支撑、F0→F1-2/6/7函证联动
- **Formula_Engine**: 前端公式引擎composable，借方科目核心公式：期末=期初+借方-贷方；审定数=未审+AJE+RJE；变动额=期末审定-期初审定；变动率=(期末-期初)/期初
- **Dynamic_Row**: 动态行，用户可新增/删除的数据行
- **Summary_Row**: 合计行，自动SUM对应明细行（不可编辑）
- **Dual_Mode**: 双模式切换，HTML精美组件 ↔ OnlyOffice在线编辑
- **Import_Export_Three_Level**: 导入导出三级：导出空模板→离线填写→导入解析
- **EventBus**: 进程内事件总线，跨底稿联动通信
- **GtIndexChip**: 交叉索引跳转芯片，点击跳转到目标底稿/位置
- **Review_Dialog**: 通用复核对话组件，任意位置可发起复核线程
- **AI_Assistant**: AI辅助生成，审计说明/变动原因/长期挂款分析/关联方识别等文本自动生成
- **Trial_Balance_Writeback**: 审定数回写试算平衡表（科目1123，借方科目/资产类）
- **Aging_Analysis**: 账龄分析，按1年以内/1-2年/2-3年/3年以上分组统计
- **Confirmation_Integration**: 函证集成，与F0存货循环函证联动（预付账款函证）

## Requirements

### Requirement 1: 组件架构与Tab设计

**User Story:** As a 开发者, I want to F1预付账款底稿按sheet拆分为独立Tab, so that 11个sheet在一个统一入口中有序组织且代码可维护。

#### Acceptance Criteria

1. THE F1 组件 SHALL 注册新componentType: `f1-prepayment`，主入口为 GtF1Prepayment.vue（el-tabs容器，10个tab-pane：程序表/审定表/明细表/调整分录/实质性分析/长期挂款/关联方/综合检查/附注披露/函证程序）
2. THE F1 组件 SHALL 将每个sheet拆分为独立Vue子组件（F1TabProcedure.vue / F1TabAdjudication.vue / F1TabDetail.vue / F1TabAdjustment.vue / F1TabSubstantiveAnalysis.vue / F1TabLongTermCheck.vue / F1TabRelatedParty.vue / F1TabComprehensiveCheck.vue / F1TabDisclosure.vue / F1TabConfirmationProcedure.vue），每文件150-300行
3. THE F1 组件 SHALL 拆分为独立composable：useF1FormData.ts（基础数据加载/保存）+ useF1FormulaEngine.ts（纯函数公式引擎）+ useF1CrossSheet.ts（跨sheet联动逻辑）
4. THE useF1FormulaEngine.ts SHALL 为纯函数模块（无副作用），包含：借方科目期末=期初+借方-贷方、审定数=未审+AJE+RJE、变动额=期末审定-期初审定、变动率=(期末-期初)/期初、合计行SUM、变动率阈值判定、账龄计算、周转率计算
5. THE F1 组件 SHALL 在htmlRendererRegistry中注册'f1-prepayment'→GtF1Prepayment映射
6. THE F1 组件 SHALL 在wp_code_overrides.json中将F1/F1-1/F1-2/F1-3/F1-4/F1-5/F1-6/F1-7的componentType统一映射为'f1-prepayment'
7. THE F1 组件 SHALL 在VALID_COMPONENT_TYPES中注册'f1-prepayment'
8. THE GtF1Prepayment.vue SHALL 支持selfLoad（当htmlData prop为null时自行调render-config?force_component_type=f1-prepayment）

### Requirement 2: 审定表F1-1 HTML渲染（93公式）

**User Story:** As a 审计助理, I want to 在精美HTML表格中查看和编辑预付账款审定表, so that 我能清晰地看到期初期末数据、审计调整、变动分析。

#### Acceptance Criteria

1. THE Adjudication_Table SHALL 渲染为标准结构：动态行（按预付类型分类：预付货款/预付服务费/预付租金/其他预付款）→ 合计行 → 试算平衡表数行 → 差异数行
2. THE Adjudication_Table SHALL 显示以下列：项目 | 期初数(未审/账项调整/重分类调整/审定) | 期末数(未审/账项调整/重分类调整/审定) | 变动额 | 变动率 | 原因分析
3. WHEN 用户编辑未审数/AJE/RJE单元格时, THE Formula_Engine SHALL 自动计算审定数（=未审+AJE+RJE）
4. THE Formula_Engine SHALL 自动计算：合计=SUM(动态行)；变动额=期末审定-期初审定；变动率=(期末-期初)/期初（期初=0且期末=0→空,期初=0→'N/A'）
5. THE Adjudication_Table SHALL 在底部显示试算平衡表数行（自动取数科目1123）和差异行（=合计审定数-试算表数），差异不为零时红色高亮
6. WHEN 变动率绝对值超过30%时, THE Adjudication_Table SHALL 以红色高亮显示该比例单元格
7. THE Adjudication_Table SHALL 对原因分析列提供textarea编辑（支持AI生成按钮）
8. THE Adjudication_Table SHALL 支持动态行增删（在合计行上方新增/删除预付类型行）
9. THE Adjudication_Table SHALL 支持与明细表F1-2的数据联动（明细表合计→审定表未审数）
10. THE Adjudication_Table SHALL 支持与调整分录F1-3的数据联动（调整分录合计→审定表AJE/RJE列）

### Requirement 3: 审定表F1-1 跨Sheet联动与回写

**User Story:** As a 审计助理, I want to 审定表自动从明细表聚合数据、从调整分录聚合调整、自动计算变动, so that 各表间数据保持一致、减少手工复制错误。

#### Acceptance Criteria

1. THE Cross_Sheet_Engine SHALL 从 Detail_Table 按预付类型聚合期末审定数填入 Adjudication_Table 对应预付类型行的期末未审数列
2. THE Cross_Sheet_Engine SHALL 从 Detail_Table 按预付类型聚合期初审定数填入 Adjudication_Table 对应预付类型行的期初未审数列
3. THE Cross_Sheet_Engine SHALL 从 Adjustment_Table 自动获取预付账款相关调整分录的AJE借方/AJE贷方/RJE借方/RJE贷方合计填入对应列
4. THE Cross_Sheet_Engine SHALL 从 Substantive_Analysis 获取变动分析结论（余额变动原因/周转率异常/账龄集中）填入原因分析列（作为参考）
5. THE Cross_Sheet_Engine SHALL 监听 Detail_Table 数据变更（编辑/增删行）→ 自动重新聚合 → 更新 Adjudication_Table 未审数列
6. THE Cross_Sheet_Engine SHALL 监听 Adjustment_Table 数据变更（新增/修改/删除调整分录）→ 自动重新聚合 → 更新 Adjudication_Table AJE/RJE列
7. THE Adjudication_Table SHALL 提供手动覆盖功能（用户可手动编辑聚合值，覆盖标记为"手动"）
8. THE Adjudication_Table SHALL 实现 EventBus `publishAdjudicated`（发布 'substantive:adjudicated' 事件，payload含 wpCode='F1'/accountCode='1123'/auditedAmount/priorAmount/changeRate）
9. THE Adjudication_Table SHALL 实现 EventBus 监听 `adjustment:created`（AJE/RJE → 累加对应列）
10. THE Adjudication_Table SHALL 实现 `writebackTrialBalance`（回写 trial_balance.audited_amount 科目1123）

### Requirement 4: 明细表F1-2 HTML渲染（69公式）

**User Story:** As a 审计助理, I want to 在精美HTML表格中管理预付账款明细, so that 我能按供应商、账龄、款项性质跟踪预付账款的详细情况。

#### Acceptance Criteria

1. THE Detail_Table SHALL 显示以下列：供应商名称 | 期初余额 | 本期增加 | 本期减少 | 期末余额 | 账龄 | 款项性质 | 审计调整 | 期末审定数 | 函证结果 | 备注
2. THE Detail_Table SHALL 对账龄列应用下拉选择（1年以内/1-2年/2-3年/3年以上）
3. THE Detail_Table SHALL 对款项性质列应用下拉选择（预付货款/预付服务费/预付租金/保证金/其他）
4. THE Detail_Table SHALL 对函证结果列应用下拉选择（已发函/已回函/回函不符/未回函/替代程序）
5. THE Formula_Engine SHALL 自动计算期末余额（= 期初余额 + 本期增加 - 本期减少）
6. THE Formula_Engine SHALL 自动计算期末审定数（= 期末余额 + 审计调整）
7. THE Detail_Table SHALL 在底部显示合计行（= SUM所有行各金额列），不可编辑
8. THE Detail_Table SHALL 支持按供应商名称筛选行（搜索框在表头上方）
9. THE Detail_Table SHALL 支持按账龄筛选行（下拉选择器在表头上方）
10. THE Detail_Table SHALL 支持按款项性质筛选行（下拉选择器在表头上方）
11. THE Detail_Table SHALL 支持添加/删除行功能（在合计行上方新增空行）
12. WHEN 账龄为"3年以上"时, THE Detail_Table SHALL 以橙色背景高亮该行（长期挂款风险）
13. WHEN 函证结果为"回函不符"时, THE Detail_Table SHALL 以红色背景高亮该行（函证差异）
14. THE Detail_Table SHALL 支持导入银行对账单数据（Excel导入功能，可选）

### Requirement 5: 明细表F1-2 跨Sheet联动

**User Story:** As a 审计助理, I want to 明细表自动关联函证结果、关联到审定表, so that 函证信息和审定数据自动同步。

#### Acceptance Criteria

1. THE Cross_Sheet_Engine SHALL 从 F0函证结果汇总表F0-1 自动获取预付账款函证结果填入 Detail_Table 函证结果列（按供应商匹配）
2. THE Cross_Sheet_Engine SHALL 监听 F0函证结果变更 → 自动更新 Detail_Table 函证结果列
3. THE Detail_Table SHALL 支持手动覆盖函证结果（用户可手动修改，覆盖标记为"手动"）
4. THE Detail_Table SHALL 自动按预付类型聚合期末审定数 → Adjudication_Table 对应预付类型行（Requirement 3.1联动）
5. THE Detail_Table SHALL 支持 GtIndexChip 渲染备注列（可点击跳转到相关底稿，如采购合同）
6. THE Detail_Table SHALL 支持与关联方检查F1-6的数据联动（关联方供应商标记）
7. THE Detail_Table SHALL 支持与长期挂款检查F1-5的数据联动（账龄3年以上自动标记）
8. THE Detail_Table SHALL 实现 EventBus 监听 `confirmation:result_updated`（函证结果更新）
9. THE Detail_Table SHALL 实现 `updateCell`（编辑 → 公式重算 → debounce保存）
10. THE Detail_Table SHALL 实现序列化/反序列化（JSON.stringify rows → F1-detail-rows remark字段）

### Requirement 6: 调整分录汇总F1-3 HTML渲染

**User Story:** As a 审计助理, I want to 在精美HTML表格中录入和管理预付账款调整分录, so that 我能快速创建AJE/RJE并联动审定表。

#### Acceptance Criteria

1. THE Adjustment_Table SHALL 显示以下列：调整事项说明 | 科目名称 | 借方金额 | 贷方金额 | 索引 | 备注
2. THE Adjustment_Table SHALL 对科目名称列应用下拉选择（1123预付账款/相关科目）
3. THE Adjustment_Table SHALL 对索引列应用 GtIndexChip 渲染（支持跳转到相关底稿）
4. THE Formula_Engine SHALL 自动计算借方合计和贷方合计（= SUM对应列），显示在底部合计行
5. WHEN 借方合计≠贷方合计时, THE Adjustment_Table SHALL 以红色高亮显示合计行并提示"借贷不平衡"
6. THE Adjustment_Table SHALL 支持添加/删除行功能（在合计行上方新增空行）
7. THE Adjustment_Table SHALL 支持按科目编码筛选行（下拉选择器在表头上方）
8. THE Adjustment_Table SHALL 支持按分录编号模糊搜索筛选行（搜索框在表头上方）
9. THE Adjustment_Table SHALL 支持与A2调整分录总表的数据联动（同步调整分录）
10. THE Adjustment_Table SHALL 实现 EventBus 发布 `adjustment:created`（新增/修改调整分录时）

### Requirement 7: 实质性分析F1-4 HTML渲染

**User Story:** As a 审计助理, I want to 在精美HTML表格中查看预付账款实质性分析, so that 我能理解余额变动原因、识别异常波动。

#### Acceptance Criteria

1. THE Substantive_Analysis SHALL 分为三个区块：余额变动分析、周转率分析、账龄分布分析
2. THE 余额变动分析区块 SHALL 显示：本期余额变动（金额/比例）、主要变动原因（预付货款增加/预付服务费减少等）、与上年比较
3. THE 周转率分析区块 SHALL 显示：预付账款周转率（= 营业成本/平均预付账款余额）、周转天数、与行业标准比较
4. THE 账龄分布分析区块 SHALL 显示：各账龄段余额占比（1年以内/1-2年/2-3年/3年以上）、账龄集中度分析
5. THE Substantive_Analysis SHALL 提供图表可视化（余额变动趋势图、账龄分布饼图）
6. THE Substantive_Analysis SHALL 支持与审定表F1-1的数据联动（自动获取审定金额）
7. THE Substantive_Analysis SHALL 支持与明细表F1-2的数据联动（自动获取账龄分布）
8. THE Substantive_Analysis SHALL 提供异常波动说明textarea（支持AI生成）
9. THE Substantive_Analysis SHALL 支持年份切换功能（对比不同年度的数据）
10. THE Substantive_Analysis SHALL 自动生成分析结论（基于规则引擎，如"周转率下降/账龄集中/余额异常增长"）

### Requirement 8: 长期挂款检查F1-5 HTML渲染

**User Story:** As a 审计助理, I want to 在精美HTML表格中检查账龄1年以上的大额预付账款, so that 我能评估可收回性和减值风险。

#### Acceptance Criteria

1. THE Long_Term_Check SHALL 自动从 Detail_Table 筛选账龄为"3年以上"的行（长期挂款）
2. THE Long_Term_Check SHALL 显示以下列：供应商名称 | 预付金额 | 账龄 | 款项性质 | 预付日期 | 长期挂款原因 | 可收回性评估 | 减值准备 | 处理措施 | 备注
3. THE Long_Term_Check SHALL 对可收回性评估列应用下拉选择（可收回/部分收回/无法收回/待确认）
4. THE Long_Term_Check SHALL 对减值准备列应用金额输入（计算减值金额）
5. THE Long_Term_Check SHALL 对处理措施列应用下拉选择（继续跟踪/发函催收/法律追偿/全额减值/其他）
6. WHEN 可收回性评估为"无法收回"时, THE Long_Term_Check SHALL 自动建议全额减值（减值准备=预付金额）
7. THE Long_Term_Check SHALL 在底部显示合计行（= SUM预付金额/SUM减值准备）
8. THE Long_Term_Check SHALL 支持与审定表F1-1的数据联动（减值准备→坏账准备考虑）
9. THE Long_Term_Check SHALL 支持与明细表F1-2的数据联动（点击行跳转到对应明细行）
10. THE Long_Term_Check SHALL 提供长期挂款风险汇总报告（高风险供应商/金额占比/处理建议）

### Requirement 9: 关联方检查F1-6 HTML渲染

**User Story:** As a 审计助理, I want to 在精美HTML表格中检查预付账款关联方交易, so that 我能识别关联方预付并评估披露完整性。

#### Acceptance Criteria

1. THE Related_Party_Check SHALL 自动从 Detail_Table 筛选关联方供应商（通过关联方名录匹配）
2. THE Related_Party_Check SHALL 显示以下列：供应商名称 | 关联关系 | 预付金额 | 账龄 | 款项性质 | 关联交易类型 | 交易定价公允性 | 披露状态 | 坏账准备 | 账面价值 | 备注
3. THE Related_Party_Check SHALL 对关联关系列应用下拉选择（母公司/子公司/合营企业/联营企业/其他关联方）
4. THE Related_Party_Check SHALL 对关联交易类型列应用下拉选择（采购商品/接受服务/租赁/其他）
5. THE Related_Party_Check SHALL 对交易定价公允性列应用下拉选择（公允/不公允/无法判断）
6. THE Related_Party_Check SHALL 对披露状态列应用下拉选择（已披露/未披露/部分披露）
7. THE Related_Party_Check SHALL 自动计算账面价值（= 预付金额 - 坏账准备）
8. WHEN 披露状态为"未披露"时, THE Related_Party_Check SHALL 以黄色背景高亮该行（披露风险）
9. THE Related_Party_Check SHALL 支持与关联方名录的数据联动（自动匹配关联关系）
10. THE Related_Party_Check SHALL 提供关联方交易汇总报告（总金额/占比/披露完整性评估）

### Requirement 10: 综合检查F1-7 HTML渲染

**User Story:** As a 审计助理, I want to 在精美HTML表格中进行预付账款综合检查, so that 我能核对合同/发票/入库/付款凭证的完整性。

#### Acceptance Criteria

1. THE Comprehensive_Check SHALL 分为两个区块：抽样参数区、检查记录区
2. THE 抽样参数区 SHALL 显示：抽样总体（笔数/金额）、抽样方法（随机/金额比例/风险导向）、样本量、抽样比例
3. THE 检查记录区 SHALL 显示以下列：样本编号 | 供应商名称 | 预付金额 | 合同核对 | 发票核对 | 入库核对 | 付款凭证核对 | 检查结论 | 问题描述 | 处理措施
4. THE Comprehensive_Check SHALL 对合同核对/发票核对/入库核对/付款凭证核对列应用下拉选择（核对一致/核对不符/未提供）
5. THE Comprehensive_Check SHALL 对检查结论列应用下拉选择（通过/不通过/需补充资料）
6. WHEN 任一核对为"核对不符"时, THE Comprehensive_Check SHALL 自动设置检查结论为"不通过"
7. THE Comprehensive_Check SHALL 支持添加/删除样本行功能
8. THE Comprehensive_Check SHALL 在底部显示汇总统计（样本通过率/主要问题类型）
9. THE Comprehensive_Check SHALL 支持与明细表F1-2的数据联动（点击样本跳转到对应明细行）
10. THE Comprehensive_Check SHALL 提供检查结果汇总报告（通过率/主要风险/改进建议）

### Requirement 11: 附注披露F1 HTML渲染

**User Story:** As a 审计助理, I want to 在精美HTML表格中查看和编辑预付账款附注披露, so that 我能确保披露信息完整准确。

#### Acceptance Criteria

1. THE Disclosure SHALL 支持上市公司版和国企版切换（el-tabs切换或企业类型检测）
2. THE 上市公司版 SHALL 显示账龄分析表：账龄 | 期末数 | 占比 | 上年年末数 | 占比
3. THE 上市公司版 SHALL 按账龄分组：1年以内、1-2年、2-3年、3年以上
4. THE 上市公司版 SHALL 自动计算占比（= 该账龄期末数/总期末数×100%）
5. THE 上市公司版 SHALL 显示坏账准备情况：期初余额、本期计提、本期转回、本期核销、期末余额
6. THE 国企版 SHALL 显示简化版账龄表：账龄 | 期末数 | 上年年末数
7. THE Disclosure SHALL 支持与审定表F1-1的数据联动（自动获取审定金额）
8. THE Disclosure SHALL 支持与明细表F1-2的数据联动（自动获取账龄分布）
9. THE Disclosure SHALL 支持与减值准备的数据联动（如适用）
10. THE Disclosure SHALL 支持导出为审计报告附注格式

### Requirement 12: 函证程序表G1A-修订前 HTML渲染

**User Story:** As a 审计助理, I want to 在精美HTML表格中查看采购循环函证程序, so that 我能跟踪函证执行情况。

#### Acceptance Criteria

1. THE Confirmation_Procedure SHALL 复用F0存货循环函证程序表结构（来自F0函证模块）
2. THE Confirmation_Procedure SHALL 显示审计目标与认定对应关系、财务报表的认定、信赖/不信赖/不适用、索引号
3. THE Confirmation_Procedure SHALL 支持与F0函证结果汇总表F0-1的数据联动
4. THE Confirmation_Procedure SHALL 支持与预付账款明细表F1-2的数据联动（函证结果回填）
5. THE Confirmation_Procedure SHALL 提供函证程序完成度汇总
6. THE Confirmation_Procedure SHALL 支持程序裁剪功能（基于控制有效性）

### Requirement 13: 共享公式引擎

**User Story:** As a 开发者, I want to 纯函数公式引擎易于测试和维护, so that 公式逻辑清晰、无副作用、可复用。

#### Acceptance Criteria

1. THE Formula_Engine SHALL 实现为纯函数模块（无状态、无副作用）
2. THE Formula_Engine SHALL 实现 `parseNum`（安全数值解析：null/undefined/空串/NaN/Infinity → 0）
3. THE Formula_Engine SHALL 实现 `calcEndUnadjustedDebit`（借方科目期末未审 = 期初审定 + 借方发生 - 贷方发生）
4. THE Formula_Engine SHALL 实现 `calcAuditedAmount`（审定数 = 未审 + AJE + RJE）
5. THE Formula_Engine SHALL 实现 `calcChangeAmount`（变动额 = 期末审定 - 期初审定）
6. THE Formula_Engine SHALL 实现 `calcChangeRate`（变动率：期初=0且期末=0→''/期初=0→'N/A'/其他→(期末-期初)/期初）
7. THE Formula_Engine SHALL 实现 `isChangeRateExceeding`（变动率绝对值超阈值判定，默认30%）
8. THE Formula_Engine SHALL 实现 `calcSubtotal`（合计 = SUM数组）
9. THE Formula_Engine SHALL 实现 `calcBookValue`（账面价值 = 期末余额 - 坏账准备）
10. THE Formula_Engine SHALL 实现 `calcTurnoverRate`（周转率 = 营业成本/平均预付账款余额）
11. THE Formula_Engine SHALL 实现 `calcTurnoverDays`（周转天数 = 365/周转率）
12. THE Formula_Engine SHALL 实现 `calcPercentage`（比例% = 该类别金额/合计金额×100）

### Requirement 14: 跨Sheet数据流响应式更新

**User Story:** As a 审计助理, I want to 明细表或调整分录变更时审定表自动更新, so that 我不需要手动在各表间复制数据，降低出错风险。

#### Acceptance Criteria

1. THE Cross_Sheet_Engine SHALL 使用同一 allResponses Map 的 computed 响应式链（不走API）
2. THE Cross_Sheet_Engine SHALL 实现明细表→审定表聚合（F1-2→F1-1未审数）
3. THE Cross_Sheet_Engine SHALL 实现调整分录→审定表聚合（F1-3→F1-1 AJE/RJE）
4. THE Cross_Sheet_Engine SHALL 实现实质性分析→审定表支撑（F1-4→F1-1原因分析）
5. THE Cross_Sheet_Engine SHALL 实现函证→明细表联动（F0→F1-2函证结果）
6. THE Cross_Sheet_Engine SHALL 实现长期挂款→明细表标记（F1-5→F1-2长期挂款标记）
7. THE Cross_Sheet_Engine SHALL 实现关联方→明细表标记（F1-6→F1-2关联方标记）
8. THE Cross_Sheet_Engine SHALL 自动触发公式重算（任一源数据变更→自动重算所有依赖）
9. THE Cross_Sheet_Engine SHALL 支持手动刷新按钮（用户可强制刷新跨sheet数据）
10. THE Cross_Sheet_Engine SHALL 提供数据流向可视化（显示当前sheet的数据来源和去向）

### Requirement 15: 导入导出功能

**User Story:** As a 审计助理, I want to 支持Excel导入导出, so that 我能离线填写底稿后导入系统。

#### Acceptance Criteria

1. THE Import_Export_Three_Level SHALL 支持导出空模板（Excel格式，包含表头和示例数据）
2. THE Import_Export_Three_Level SHALL 支持离线填写后导入解析（Excel文件解析，校验数据格式）
3. THE Import_Export_Three_Level SHALL 支持导入预览（显示解析结果，用户确认后再保存）
4. THE Import_Export_Three_Level SHALL 支持导出当前数据（Excel格式，包含所有数据）
5. THE Import_Export_Three_Level SHALL 导入时进行数据验证（日期格式、金额格式、必填字段）
6. THE Import_Export_Three_Level SHALL 导入失败时显示详细错误信息（行号、字段、错误原因）

### Requirement 16: 双模式切换

**User Story:** As a 审计助理, I want to 支持HTML模式和OnlyOffice模式切换, so that 我能根据需要选择更适合的编辑方式。

#### Acceptance Criteria

1. THE Dual_Mode_Engine SHALL 在页面右上角显示"切换到OnlyOffice"按钮
2. WHEN 用户点击切换按钮时, THE Dual_Mode_Engine SHALL 切换当前sheet到OnlyOffice编辑器
3. THE Dual_Mode_Engine SHALL 切换时隐藏其他sheet（OnlyOffice API只支持单sheet显示）
4. THE Dual_Mode_Engine SHALL OnlyOffice模式显示"返回HTML模式"按钮
5. THE Dual_Mode_Engine SHALL 切换回HTML模式时重新渲染Vue组件并同步数据
6. THE Dual_Mode_Engine SHALL 记住用户上次选择的模式（localStorage持久化）
7. WHEN OnlyOffice加载失败时, THE Dual_Mode_Engine SHALL 自动降级到HTML模式并显示错误提示

### Requirement 17: AI生成审计说明

**User Story:** As a 审计助理, I want to 点击AI按钮自动生成审计说明, so that 我能快速完成变动原因说明和分析结论。

#### Acceptance Criteria

1. THE AI_Assistant SHALL 在审定表原因分析列旁显示"AI生成"按钮
2. WHEN 用户点击"AI生成"按钮时, THE AI_Assistant SHALL 基于审定表数据（变动额/变动率/明细结构）生成变动原因说明
3. THE AI_Assistant SHALL 在长期挂款检查表提供"AI分析"按钮（基于长期挂款原因/可收回性生成处理建议）
4. THE AI_Assistant SHALL 在实质性分析表提供"AI生成结论"按钮（基于余额变动/周转率/账龄分布生成分析结论）
5. THE AI_Assistant SHALL 在关联方检查表提供"AI识别"按钮（基于供应商名称自动识别关联方）
6. THE AI_Assistant SHALL 支持用户编辑AI生成的内容（生成的文本可手动修改）
7. THE AI_Assistant SHALL 提供AI生成历史记录（显示之前的AI生成内容）
8. THE AI_Assistant SHALL 支持重新生成（用户可点击重新生成，获得不同版本）

### Requirement 18: 金额格式化与显示

**User Story:** As a 审计助理, I want to 金额字段按审计标准格式化显示, so that 我能快速识别大额数据和异常值。

#### Acceptance Criteria

1. THE Display SHALL 对所有金额列应用千分位分隔符（如：1,234,567.89）
2. THE Display SHALL 对负数显示红色（如：-1,234.56显示为红色）
3. THE Display SHALL 对零值显示"-"或"0.00"（可配置）
4. THE Display SHALL 对大额金额（>100万）加粗显示
5. THE Display SHALL 支持金额单位切换（元/万元/亿元）
6. THE Display SHALL 对百分比列显示两位小数（如：12.34%）
7. THE Display SHALL 对变动率列显示符号（正数显示"+"，如：+12.34%）

### Requirement 19: 权限控制与只读模式

**User Story:** As a 审计助理, I want to 根据用户权限控制编辑权限, so that 已审定的数据不被误修改。

#### Acceptance Criteria

1. THE Permission_Control SHALL 支持只读模式切换（当底稿状态为"已审定"时自动启用只读）
2. THE Permission_Control SHALL 在只读模式下禁用所有编辑功能（添加/删除行、编辑单元格）
3. THE Permission_Control SHALL 在只读模式下隐藏"切换到OnlyOffice"按钮
4. THE Permission_Control SHALL 支持手动启用只读模式（用户可手动切换）
5. THE Permission_Control SHALL 对不同sheet设置不同权限（如程序表可编辑、审定表部分只读）
6. THE Permission_Control SHALL 在只读模式下显示"只读模式"标识

### Requirement 20: 审计复核对话集成

**User Story:** As a 审计项目经理, I want to 在任意位置发起复核对话, so that 我能对异常数据进行复核讨论。

#### Acceptance Criteria

1. THE Review_Dialog SHALL 在每个金额单元格提供"复核"按钮（右键菜单或hover显示）
2. WHEN 用户点击"复核"按钮时, THE Review_Dialog SHALL 打开复核对话弹窗
3. THE Review_Dialog SHALL 自动携带上下文信息（底稿代码、sheet名称、单元格位置、当前值）
4. THE Review_Dialog SHALL 支持添加复核意见（文本输入）
5. THE Review_Dialog SHALL 支持@提及其他用户（通知相关人员参与复核）
6. THE Review_Dialog SHALL 支持复核状态跟踪（待复核/复核中/已复核/需修改）
7. THE Review_Dialog SHALL 在复核完成后显示复核标识（单元格上显示小图标）
8. THE Review_Dialog SHALL 支持复核历史查看（显示该单元格的所有复核记录）

### Requirement 21: 性能优化

**User Story:** As a 审计助理, I want to 大数据量底稿响应流畅, so that 我能高效完成审计工作。

#### Acceptance Criteria

1. THE Performance SHALL 对明细表启用虚拟滚动（当行数超过100行时）
2. THE Performance SHALL 对跨sheet计算启用debounce（用户停止编辑2秒后才触发重算）
3. THE Performance SHALL 对大数据量查询启用分页（每页显示50行，支持翻页）
4. THE Performance SHALL 对公式计算启用缓存（相同输入不重复计算）
5. THE Performance SHALL 对图表渲染启用懒加载（滚动到可视区域才渲染）
6. THE Performance SHALL 对导入导出启用进度条（显示处理进度）
7. THE Performance SHALL 对AI生成启用超时控制（30秒超时自动取消）
