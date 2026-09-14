# Requirements Document: D3 预收账款底稿专属HTML精美组件

## Introduction

D3预收账款底稿的专属HTML精美组件构建。将现有 `d-form-table` 通用渲染升级为独立专属组件 `d3-prepaid-accounts`，覆盖源模板10个有效sheet（程序表D3A + 审定表D3-1 + 明细表D3-2 + 调整分录D3-3 + 分析表D3-4 + 长期检查D3-5 + 关联方D3-6 + 凭证检查D3-7 + 附注上市 + 附注国企），合计294个公式。所有sheet做HTML精美组件（el-table + 金额格式化 + 动态行 + 跨sheet联动），OnlyOffice仅作降级切换。核心关注点：期后结转检查、长期挂账追踪、款项性质分类、CAS14收入准则联动。

## Glossary

- **Adjudication_Table**: 审定表D3-1，双区块结构（按性质分类+按账龄分类），88个公式
- **Detail_Table**: 明细表D3-2，27列宽表（客户×性质×账龄×调整），核心数据源
- **Adjustment_Table**: 调整分录汇总表D3-3，10列动态行
- **Analysis_Table**: 分析表D3-4，4区块（借方/贷方发生额分析+Top5债务人+审计说明）
- **LongTerm_Check**: 账龄1年以上检查表D3-5，8列动态行
- **Related_Party_Check**: 关联关系及交易检查表D3-6，10列+关联关系下拉
- **Voucher_Check**: 预收账款检查表D3-7，双区块（本期增减变动+期后结转）+抽样参数区
- **Disclosure_Listed**: 附注披露信息（上市公司），3子节33公式
- **Disclosure_SOE**: 附注披露信息（国企），2子节22公式
- **Procedure_Table**: 实质性程序表D3A，12步审计程序+5项审计目标
- **Cross_Sheet_Engine**: 跨sheet公式引擎，D3-2→D3-1聚合+D3-2→D3-5/D3-6筛选导入+D3-3→D3-1 AJE/RJE同步
- **Formula_Engine**: 前端公式引擎，composable内行内公式自动计算（贷方科目：期末=期初+贷方-借方）
- **Dynamic_Row**: 动态行，用户可新增/删除的数据行
- **Summary_Row**: 合计行，自动SUM对应明细行（不可编辑）
- **Dual_Mode**: 双模式切换，HTML精美组件 ↔ OnlyOffice在线编辑
- **Import_Export_Three_Level**: 导入导出三级：导出空模板→离线填写→导入解析
- **EventBus**: 进程内事件总线，跨底稿联动通信
- **GtIndexChip**: 交叉索引跳转芯片，点击跳转到目标底稿/位置
- **Review_Dialog**: 通用复核对话组件，任意位置可发起复核线程
- **AI_Assistant**: AI辅助生成，审计说明/变动原因/长期挂账原因等文本自动生成
- **Trial_Balance_Writeback**: 审定数回写试算平衡表（科目2203，贷方科目/负债类）

## Requirements

### Requirement 1: 审定表D3-1 HTML渲染（双区块88公式）

**User Story:** As a 审计助理, I want to 在精美HTML表格中查看和编辑预收账款审定表, so that 我能清晰地看到按性质分类和按账龄分类两个维度的审定数据。

#### Acceptance Criteria

1. THE Adjudication_Table SHALL 渲染为双区块固定结构：一、按照性质分类（预收销售固定资产款/预收销售土地使用权款/合同不成立时已收取的对价/其他/合计）→ 二、按照账龄分类（1年以内/1至2年/2至3年/3年以上/合计/试算平衡表数/差异数）
2. THE Adjudication_Table SHALL 显示以下列：项目 | 期初数(未审/AJE/RJE/审定) | 期末数(未审/AJE/RJE/审定) | 变动额 | 变动率 | 原因分析
3. WHEN 用户编辑期末未审数/AJE/RJE单元格时, THE Formula_Engine SHALL 自动计算期末审定数（=未审+AJE+RJE）
4. WHEN 期初审定数和期末审定数均存在时, THE Formula_Engine SHALL 自动计算变动额（=期末审定-期初审定）和变动率（=(期末-期初)/期初，期初=0时显示"N/A"）
5. THE Adjudication_Table SHALL 自动计算各区块合计行（=SUM对应明细行），合计行不可手动编辑
6. WHEN 变动率绝对值超过30%时, THE Adjudication_Table SHALL 以红色高亮显示该比例单元格
7. THE Adjudication_Table SHALL 在"按账龄分类"区块底部显示试算平衡表数行（自动取数）和差异行（=审定数合计-试算表数），差异不为零时红色高亮
8. THE Adjudication_Table SHALL 对"按性质分类"区块的合计行与"按账龄分类"区块的合计行进行交叉验证，不一致时显示黄色警告"性质分类合计≠账龄分类合计，差额：±xxx元"

### Requirement 2: 审定表D3-1 跨Sheet联动与回写

**User Story:** As a 审计助理, I want to 审定表自动从明细表聚合取数并联动调整分录和试算表, so that 数据在各表间保持一致、减少手工复制错误。

#### Acceptance Criteria

1. THE Cross_Sheet_Engine SHALL 从 Detail_Table 按"款项性质"列聚合期末审定数填入 Adjudication_Table "按性质分类"区块对应行
2. THE Cross_Sheet_Engine SHALL 从 Detail_Table 按"审定账龄"(U~X列)聚合填入 Adjudication_Table "按账龄分类"区块对应行
3. WHEN Detail_Table 数据变更时, THE Cross_Sheet_Engine SHALL 在2秒内刷新 Adjudication_Table 中的聚合值
4. WHILE 跨sheet引用值生效时, THE Adjudication_Table SHALL 以浅蓝色背景标记自动取数单元格，并在tooltip显示数据来源（如"取自D3-2按款项性质聚合"）
5. WHEN EventBus发布'adjustment:created'事件时, THE Adjudication_Table SHALL 自动将对应AJE/RJE金额同步到审定表相应行
6. WHEN 审定数计算完成且发生变化时, THE Adjudication_Table SHALL 调用 writebackTrialBalance 将最新审定数回写 trial_balance.audited_amount（科目2203）
7. THE Adjudication_Table SHALL 在审定数回写成功后通过EventBus发布'substantive:adjudicated'事件（payload含wpCode='D3'/accountCode='2203'/auditedAmount）
8. IF 跨sheet数据加载失败, THEN THE Cross_Sheet_Engine SHALL 显示"-"占位符并在单元格右上角标注黄色三角警告图标

### Requirement 3: 审定表D3-1 审计说明与AI辅助

**User Story:** As a 审计助理, I want to 审定表底部有结构化的审计说明和结论区域并支持AI生成, so that 我能快速记录审计发现并获得AI辅助撰写建议。

#### Acceptance Criteria

1. THE Adjudication_Table SHALL 在表尾显示"审计说明"区域，包含：(1)账龄超过1年的预收账款原因说明（textarea + GtIndexChip跳转D3-5）(2)预收账款变动分析（自动生成变动百分比句子 + textarea手填/AI生成）
2. THE Adjudication_Table SHALL 在审计说明区域的每个textarea旁显示🤖AI生成按钮，点击调用AI生成审计说明文本（基于当前数据变动情况+D3-5长期挂账+D3-4分析结果作为context）
3. THE Adjudication_Table SHALL 在底部显示"审计结论"区域（textarea + AI生成按钮）
4. THE Adjudication_Table SHALL 显示CAS14号准则提示区域（只读折叠区，`<details>`蓝色左边线+浅蓝背景，默认收起，内容为"合同不成立时已收取的对价"vs"合同负债(D7)"的区分说明）
5. THE Adjudication_Table SHALL 在"审计说明"和"审计结论"区域各放置一个固定复核对话入口按钮（💬图标），点击调用openReviewDialog
6. THE Adjudication_Table SHALL 支持表格单元格右键菜单"发起复核对话"（@cell-contextmenu → openReviewDialog，sectionId自动生成为`D3-adj-{rowKey}-{field}`）
7. WHEN 有活跃复核线程时, THE Adjudication_Table SHALL 在对应位置显示蓝/红圆点标记

### Requirement 4: 明细表D3-2 HTML渲染（27列宽表）

**User Story:** As a 审计助理, I want to 在精美HTML宽表中管理预收账款客户明细, so that 我能在语义化的横向滚动表格中编辑27列数据，追踪每个客户的预收余额和账龄变动。

#### Acceptance Criteria

1. THE Detail_Table SHALL 以el-table横向滚动渲染27列：对方单位名称|公司代码|款项性质|关联方类型|期初未审余额|期初账项调整|期初重分类调整|期初审定余额|期初审定账龄(1年以下/1~2年/2~3年/3年以上)|借方发生|贷方发生|期末余额|被审计单位重分类调整|期末未审余额|期末账项调整|期末重分类调整|期末审定数|审定账龄(1年以下/1~2年/2~3年/3年以上)|是否发函|期后结转|备注
2. THE Detail_Table SHALL 对"款项性质"列应用下拉选择（预收销售固定资产款/预收销售土地使用权款/合同不成立时已收取的对价/其他）
3. THE Detail_Table SHALL 对"关联方类型"列应用下拉选择（非关联方/实际控制人/控股股东/控股股东附属企业/持有5%以上/联营/合营/董高监/其他关联方）
4. THE Formula_Engine SHALL 自动计算每行：期初审定余额=期初未审+账项调整+重分类调整；期末余额=期初审定+贷方发生-借方发生（贷方科目）；期末未审=期末余额+被审计单位重分类调整；期末审定数=期末未审+期末账项调整+期末重分类调整
5. THE Detail_Table SHALL 在底部显示合计行（=SUM所有客户行各金额列）和核对行（=合计-试算表数），合计行不可编辑
6. WHEN 用户点击"添加客户"按钮时, THE Detail_Table SHALL 在合计行上方新增一个可编辑空行
7. WHEN 用户输入对方单位名称时, THE Detail_Table SHALL 自动从related_parties表模糊匹配关联方信息并填充"关联方类型"列
8. WHEN 关联方类型列为非"非关联方"时, THE Detail_Table SHALL 以橙色背景高亮该行
9. THE Detail_Table SHALL 固定前2列（对方单位名称/公司代码）使横向滚动时仍可辨识行
10. WHEN 动态行超过30行时, THE Detail_Table SHALL 启用虚拟滚动以保证渲染性能
11. THE Detail_Table SHALL 支持按对方单位名称模糊搜索筛选行（搜索框在表头上方）
12. THE Detail_Table SHALL 对所有金额列应用右对齐+金额格式化（千分位/负数红色括号/零值"-"）

### Requirement 5: 明细表D3-2 自动提取与联动

**User Story:** As a 审计助理, I want to 明细表支持从辅助余额表批量导入和自动联动其他表, so that 我不需要逐行手工录入大量客户明细数据。

#### Acceptance Criteria

1. WHEN 用户点击"从余额表导入"按钮时, THE Detail_Table SHALL 从tb_aux_balance（科目2203，按客户维度）批量导入客户名称和期初/期末未审余额
2. WHEN 导入数据行数超过现有行时, THE Detail_Table SHALL 自动扩展动态行以容纳全部数据
3. THE Detail_Table SHALL 在导入完成后显示摘要（"成功导入N行数据，M个新客户"）
4. WHEN EventBus发布'confirmation:completed'事件时, THE Detail_Table SHALL 自动将对应客户行的"是否发函"列标记为"Y"
5. THE Detail_Table SHALL 支持"导出空模板"（含表头+格式+公式，无数据行）和"导出数据"（含当前数据的xlsx文件）
6. WHEN 用户上传已填写的xlsx文件时, THE Detail_Table SHALL 使用openpyxl解析文件内容并将数据回写到checklist_responses
7. IF 导入的xlsx格式不符合模板结构, THEN THE Detail_Table SHALL 显示错误提示并列出不匹配的列名

### Requirement 6: 明细表D3-2 审计说明与复核

**User Story:** As a 审计助理, I want to 明细表底部有结构化审计说明区域, so that 我能记录期末变动原因、预收与合同匹配情况、超1年原因等关键审计发现。

#### Acceptance Criteria

1. THE Detail_Table SHALL 在底部显示3条审计说明textarea：(1)期末变动原因分析 (2)预收账款与合同匹配情况说明 (3)超1年未结转原因说明（含GtIndexChip跳转D3-5）
2. THE Detail_Table SHALL 在每条审计说明textarea旁显示🤖AI生成按钮，基于当前明细数据变动自动生成说明文本
3. THE Detail_Table SHALL 在底部显示"审计结论"区域（textarea + AI生成按钮）
4. THE Detail_Table SHALL 在审计说明和结论区域放置复核对话入口（💬图标）
5. WHEN 有活跃复核线程时, THE Detail_Table SHALL 在对应区域显示蓝/红圆点标记

### Requirement 7: 调整分录汇总表D3-3 HTML渲染

**User Story:** As a 审计助理, I want to 在精美HTML表格中录入和管理预收账款调整分录, so that 我能快速创建AJE/RJE并联动审定表和A13错报汇总。

#### Acceptance Criteria

1. THE Adjustment_Table SHALL 显示10列：调整事项说明 | 类别(报表调整/账项调整/其他) | 报表项目 | 科目名称 | 附注项目 | … | 借方调整金额 | 贷方调整金额 | 索引 | 备注
2. WHEN 用户点击"新增调整分录"按钮时, THE Adjustment_Table SHALL 新增一行可编辑空行
3. THE Adjustment_Table SHALL 在底部显示借贷合计行，借方合计=贷方合计时显示绿色"✓平衡"，否则红色"✗不平衡：差额xxx"
4. WHEN 调整分录保存成功时, THE Adjustment_Table SHALL 通过EventBus发布'adjustment:created'事件（payload含wpCode='D3'/entryType/amount）
5. THE Adjustment_Table SHALL 双向同步AJE/RJE合计到 Adjudication_Table 对应列
6. WHEN 用户点击"推送至A13"按钮时, THE Adjustment_Table SHALL 将选中分录通过EventBus发布至A13错报汇总
7. THE Adjustment_Table SHALL 在Row21位置显示编制提示（`<details>`折叠，蓝色左边线+浅蓝背景，默认收起）

### Requirement 8: 分析表D3-4 HTML渲染（4区块22公式）

**User Story:** As a 审计助理, I want to 在精美HTML组件中查看预收账款借贷发生额分析和Top5债务人, so that 我能直观判断预收账款变动是否合理并追踪主要客户。

#### Acceptance Criteria

1. THE Analysis_Table SHALL 渲染为4区块卡片式布局：(一)借方发生额分析（项目/金额/数据来源/备注）→ (三)贷方发生额分析（项目/金额/数据来源/与对方科目核对/说明）→ (四)期末主要债务人分析（债务人名称/期末余额/期初余额/变动金额/变动比例/发生时间及账龄/发生原因/期后结账）→ 三、审计说明
2. THE Analysis_Table SHALL 从TB自动获取借方/贷方发生额总计（tb_ledger科目2203），并按对方科目分拆显示（资产处置损益/固定资产/增值税等）
3. THE Analysis_Table SHALL 在借方/贷方分析区块底部显示差异行（=TB总计-各项分拆合计），差异不为零时红色高亮
4. THE Analysis_Table SHALL 从 Detail_Table 按期末余额降序自动排列Top5债务人，并计算变动金额和变动比例
5. WHEN Top5债务人期末余额占合计超过50%时, THE Analysis_Table SHALL 以黄色高亮提示"前五大客户集中度较高"
6. THE Analysis_Table SHALL 在Top5每行提供GtIndexChip，点击跳转至D3-2对应客户明细行
7. THE Analysis_Table SHALL 在"审计说明"区域提供textarea + AI生成按钮（基于借贷分析+Top5变动情况生成说明）
8. WHEN 分析发现显著变动（变动比例>30%）时, THE Analysis_Table SHALL 通过EventBus发布'analytical:significant-change'事件，联动A1-13分析性复核

### Requirement 9: 账龄1年以上检查表D3-5 HTML渲染

**User Story:** As a 审计助理, I want to 在精美HTML表格中检查超过1年未结转的预收账款, so that 我能逐笔追踪长期挂账原因和处理计划。

#### Acceptance Criteria

1. THE LongTerm_Check SHALL 显示8列：对方单位名称 | 期末余额 | 账龄 | 经济业务说明 | 未结转或未偿还的原因 | 至审计日结转或偿还金额 | 处理计划 | 备注
2. WHEN 用户点击"从D3-2导入"按钮时, THE LongTerm_Check SHALL 自动从 Detail_Table 筛选审定账龄>1年的客户行导入（取对方单位名称/期末审定数/账龄分布）
3. WHEN 用户点击"添加行"按钮时, THE LongTerm_Check SHALL 新增一个可编辑空行
4. THE LongTerm_Check SHALL 在底部显示合计行（期末余额/至审计日结转金额列SUM）
5. THE LongTerm_Check SHALL 在底部显示"审计说明"textarea（AI生成按钮，基于长期挂账原因+项目背景生成建议文本）和"审计结论"textarea
6. THE LongTerm_Check SHALL 对"未结转或未偿还的原因"列提供🤖AI建议按钮，结合项目背景和客户交易历史生成原因建议
7. THE LongTerm_Check SHALL 在每行提供GtIndexChip，点击跳转至D3-2对应客户明细行
8. THE LongTerm_Check SHALL 对所有金额列应用金额格式化（千分位/负数红色括号/零值"-"）

### Requirement 10: 关联关系及交易检查表D3-6 HTML渲染

**User Story:** As a 审计助理, I want to 在精美HTML表格中记录预收账款关联方交易检查, so that 我能追踪每个关联方的期初/期末余额和交易合理性。

#### Acceptance Criteria

1. THE Related_Party_Check SHALL 显示10列：关联方名称 | 关联关系 | 期初余额 | 借方发生 | 贷方发生 | 期末余额 | 发生时间及账龄 | 发生原因（款项性质）| 索引号 | 备注
2. THE Related_Party_Check SHALL 对"关联关系"列应用下拉选择（实际控制人/控股股东/控股股东附属企业/持有5%以上/联营/合营/董高监/其他关联方）
3. THE Formula_Engine SHALL 自动计算每行：期末余额=期初余额+贷方发生-借方发生（预收为贷方科目，贷方增加）
4. WHEN 用户点击"从D3-2导入"按钮时, THE Related_Party_Check SHALL 自动从 Detail_Table 筛选"关联方类型≠非关联方"的客户行导入
5. WHEN 用户点击"添加关联方"按钮时, THE Related_Party_Check SHALL 新增一行，并自动从项目关联方清单下拉匹配
6. THE Related_Party_Check SHALL 在底部显示合计行（期初/借方/贷方/期末各列SUM）
7. THE Related_Party_Check SHALL 在底部显示"审计说明"textarea（AI生成按钮，结合关联方清单+交易性质评价合理性）和"审计结论"textarea
8. THE Related_Party_Check SHALL 在每行提供GtIndexChip，点击跳转至D3-2对应客户明细行
9. THE Related_Party_Check SHALL 在审计说明/结论区域放置复核对话入口（💬图标）

### Requirement 11: 预收账款检查表D3-7 HTML渲染（双区块+抽样参数）

**User Story:** As a 审计助理, I want to 在精美HTML组件中执行预收账款凭证抽样检查（含本期变动和期后结转两个维度）, so that 我能记录抽样参数和逐笔核对凭证信息。

#### Acceptance Criteria

1. THE Voucher_Check SHALL 分为3区域：抽样参数区（测试总体/特定样本/抽样总体/抽样方法+抽样过程）+ (1)本期增减变动检查表 + (2)期后结转检查表
2. THE Voucher_Check "(1)本期增减变动检查"区块 SHALL 显示17列：客户名称|日期|凭证编号|业务内容|对方科目|对方明细科目|借方金额|贷方金额|支持性文件|核对内容(1-5)|索引号|是否异常|备注说明
3. THE Voucher_Check "(2)期后结转检查"区块 SHALL 显示16列（无借方金额列）：客户名称|日期|凭证编号|业务内容|对方科目|对方明细科目|贷方金额|支持性文件|核对内容(1-5)|索引号|是否异常|备注说明
4. WHEN 用户点击"添加样本"按钮时, THE Voucher_Check SHALL 在对应区块新增一行凭证抽样明细
5. THE Voucher_Check SHALL 在底部显示汇总公式：已检查笔数/发现异常笔数/异常率（=异常/已检查×100%）
6. THE Voucher_Check SHALL 在抽样参数区显示进度条：已抽取样本数/目标样本量
7. WHEN 期后结转的凭证日期早于收入确认日期时, THE Voucher_Check SHALL 自动标记"是否异常"列为"跨期疑点"
8. THE Voucher_Check SHALL 集成抽凭引擎（voucher-sampling-engine），支持从D3-2选定客户后自动进入抽凭流程
9. THE Voucher_Check SHALL 在审计说明/结论区域放置复核对话入口（💬图标）

### Requirement 12: 附注披露信息（上市公司）HTML渲染

**User Story:** As a 审计助理, I want to 在精美HTML组件中编辑上市公司预收账款附注披露, so that 我能按三子节结构核对附注数据并与审定表自动取数对齐。

#### Acceptance Criteria

1. THE Disclosure_Listed SHALL 渲染为3子节卡片结构：(1)按性质分类（项目/期末余额/上年年末余额，4项+合计）→ (2)超1年重要预收（项目/期末余额/未偿还原因，动态行+合计）→ (3)重大变动（项目/变动金额/变动原因，动态行+合计）
2. THE Cross_Sheet_Engine SHALL 从 Adjudication_Table "按性质分类"区块自动取数填入Disclosure_Listed第(1)子节对应行
3. THE Cross_Sheet_Engine SHALL 从 LongTerm_Check 自动取数填入Disclosure_Listed第(2)子节对应行
4. WHILE 跨sheet引用值生效时, THE Disclosure_Listed SHALL 以浅蓝色背景标记自动取数单元格，tooltip显示数据来源
5. THE Disclosure_Listed SHALL 对第(2)(3)子节支持动态添加/删除行
6. THE Disclosure_Listed SHALL 自动计算各子节合计行
7. THE Disclosure_Listed SHALL 在每个子节底部放置"说明"textarea（可编辑，双向回写附注模块）
8. THE Disclosure_Listed SHALL 在说明textarea下方显示编制提示折叠区（`<details>`默认收起）

### Requirement 13: 附注披露信息（国企）HTML渲染

**User Story:** As a 审计助理, I want to 在精美HTML组件中编辑国企预收账款附注披露, so that 我能按账龄维度和重要预收两个子节核对附注数据。

#### Acceptance Criteria

1. THE Disclosure_SOE SHALL 渲染为2子节卡片结构：(1)按账龄（账龄/期末余额/期初余额，1年以内/1年以上/合计）→ (2)超1年重要预收（债权单位名称/期末余额/未偿还原因，动态行+合计）
2. THE Cross_Sheet_Engine SHALL 从 Adjudication_Table "按账龄分类"区块自动取数填入Disclosure_SOE第(1)子节对应行
3. THE Cross_Sheet_Engine SHALL 从 LongTerm_Check 自动取数填入Disclosure_SOE第(2)子节对应行
4. WHILE 跨sheet引用值生效时, THE Disclosure_SOE SHALL 以浅蓝色背景标记自动取数单元格
5. THE Disclosure_SOE SHALL 对第(2)子节支持动态添加/删除行
6. THE Disclosure_SOE SHALL 自动计算各子节合计行
7. THE Disclosure_SOE SHALL 根据项目applicable_standards自动判断显示上市版还是国企版（同一Tab内el-segmented切换）

### Requirement 14: 附注披露适用性切换与双向回写

**User Story:** As a 审计助理, I want to 附注披露根据项目类型自动适配并与附注模块双向同步, so that 我无需在两处重复维护相同数据。

#### Acceptance Criteria

1. THE Disclosure_Listed SHALL 根据项目applicable_standards（listed_standalone/listed_consolidated）自动显示
2. THE Disclosure_SOE SHALL 根据项目applicable_standards（soe_standalone/soe_consolidated）自动显示
3. WHEN 两种标准均不适用时, THE Disclosure_Listed 和 Disclosure_SOE SHALL 隐藏对应Tab
4. WHEN 附注"说明"textarea编辑后, THE Disclosure_Listed SHALL 通过EventBus发布'disclosure:note-text-updated'事件双向回写附注模块
5. WHEN EventBus收到'note:section-updated'事件时, THE Disclosure_Listed SHALL 同步更新对应子节文本（last-write-wins冲突策略）
6. THE Disclosure_Listed 和 Disclosure_SOE SHALL 在每个子节提供GtIndexChip，点击跳转至D3-1审定表对应数据来源行

### Requirement 15: 实质性程序表D3A 集成

**User Story:** As a 审计助理, I want to 程序表D3A集成到统一入口并联动各子sheet索引, so that 我能从程序表出发逐步执行审计步骤并跳转到对应底稿。

#### Acceptance Criteria

1. THE Procedure_Table SHALL 复用 `a-program-console` componentType渲染12步审计程序（常规★8+备选1+IPO/上市2+常规1）
2. THE Procedure_Table SHALL 显示5项审计目标（存在/完整性/权利和义务/准确性计价分摊/列报）
3. THE Procedure_Table SHALL 在每步程序的"底稿索引号"列提供GtIndexChip，点击跳转至对应子sheet（D3-1/D3-2/T1/D3-4/D0/D3-5/D3-6/D3-7/D4-28~31/A1-1/A1-15/A1-16）
4. WHEN B50风险评估更新时, THE Procedure_Table SHALL 通过EventBus接收'risk:updated'事件并更新程序步骤状态标记
5. THE Procedure_Table SHALL selfLoad渲染数据（当htmlData prop为null时自行调render-config?force_component_type=a-program-console）

### Requirement 16: 双模式切换

**User Story:** As a 审计助理, I want to 在HTML精美组件和OnlyOffice编辑模式之间切换, so that 我能根据需要选择最适合的编辑方式。

#### Acceptance Criteria

1. THE Dual_Mode SHALL 在每个Tab页头部显示el-segmented切换控件（"结构化视图" | "在线编辑"）
2. WHEN 用户切换到OnlyOffice模式时, THE Dual_Mode SHALL 打开完整xlsx文件并通过OnlyOffice API隐藏非当前sheet（SetVisible(false)），只显示当前Tab对应的sheet
3. WHEN 用户从OnlyOffice模式切回HTML模式时, THE Dual_Mode SHALL 重新加载checklist_responses数据以反映在OO中的编辑
4. WHILE OnlyOffice服务不可用时, THE Dual_Mode SHALL 禁用"在线编辑"选项并显示tooltip"OnlyOffice服务不可用"
5. THE Dual_Mode SHALL 保留跨sheet公式完整性（不拆分文件），OO模式下用户仍可查看跨sheet公式计算结果

### Requirement 17: 持久化与数据存储

**User Story:** As a 审计助理, I want to 所有编辑内容自动保存, so that 我不会因为意外关闭页面而丢失数据。

#### Acceptance Criteria

1. THE Adjudication_Table SHALL 使用 checklist_responses 表存储数据，item_id前缀为"D3-adj-"
2. THE Detail_Table SHALL 使用 checklist_responses 表存储数据，item_id前缀为"D3-det-"，动态行以JSON数组格式存储于remark字段（item_id="D3-det-rows"）
3. THE Adjustment_Table SHALL 使用 checklist_responses 表存储数据，item_id前缀为"D3-aje-"
4. THE Analysis_Table SHALL 使用 checklist_responses 表存储数据，item_id前缀为"D3-ana-"
5. THE LongTerm_Check SHALL 使用 checklist_responses 表存储数据，item_id前缀为"D3-lt-"
6. THE Related_Party_Check SHALL 使用 checklist_responses 表存储数据，item_id前缀为"D3-rp-"
7. THE Voucher_Check SHALL 使用 checklist_responses 表存储数据，item_id前缀为"D3-vc-"
8. THE Disclosure_Listed SHALL 使用 checklist_responses 表存储数据，item_id前缀为"D3-note-listed-"
9. THE Disclosure_SOE SHALL 使用 checklist_responses 表存储数据，item_id前缀为"D3-note-soe-"
10. WHEN 用户编辑任意金额/文本字段后2秒无操作时, THE Formula_Engine SHALL 触发debounce自动保存
11. WHEN 用户切换结论/选择类字段时, THE Formula_Engine SHALL 立即保存该字段

### Requirement 18: 跨底稿EventBus联动

**User Story:** As a 审计助理, I want to D3预收账款底稿与其他底稿自动联动, so that 审定数变化、调整分录、分析异常等信息能实时传递到相关底稿。

#### Acceptance Criteria

1. WHEN D3-1审定数变化时, THE Cross_Sheet_Engine SHALL 通过EventBus发布'substantive:adjudicated'事件回写trial_balance科目2203
2. WHEN D3-3调整分录创建时, THE Adjustment_Table SHALL 通过EventBus发布'adjustment:created'事件联动A13错报汇总
3. WHEN D3-4分析发现显著变动时, THE Analysis_Table SHALL 通过EventBus发布'analytical:significant-change'事件联动A1-13分析性复核
4. WHEN EventBus收到'confirmation:completed'事件时（D0函证完成）, THE Detail_Table SHALL 自动将对应客户的"是否发函"列标Y
5. THE Voucher_Check SHALL 与D4营业收入底稿进行期后结转交叉验证（收入确认日 vs 预收转销日），通过GtIndexChip跳转D4相关底稿
6. WHEN EventBus收到'risk:updated'事件时（B50风险评估更新）, THE Procedure_Table SHALL 更新程序步骤状态标记

### Requirement 19: GtIndexChip交叉索引

**User Story:** As a 审计助理, I want to 底稿各处有可点击的交叉索引芯片, so that 我能快速跳转到相关底稿查看关联信息。

#### Acceptance Criteria

1. THE Adjudication_Table SHALL 在审计说明区域提供GtIndexChip跳转：D3-5（超1年详情）、D3-2（明细表）
2. THE Analysis_Table SHALL 在Top5债务人每行提供GtIndexChip跳转：D3-2（客户明细定位）
3. THE Related_Party_Check SHALL 在每行提供GtIndexChip跳转：D3-2（明细行定位）
4. THE Voucher_Check SHALL 提供GtIndexChip跳转：抽凭引擎（voucher-sampling-engine集成）
5. THE Disclosure_Listed 和 Disclosure_SOE SHALL 在数据来源处提供GtIndexChip跳转：D3-1（审定数来源）
6. THE Procedure_Table SHALL 在每步程序索引号列提供GtIndexChip跳转：各子sheet（D3-1/D3-2/D3-4/D3-5/D3-6/D3-7/D0/D4/A1-1/A1-15/A1-16）
7. WHEN 用户点击GtIndexChip时, THE Cross_Sheet_Engine SHALL 切换到目标Tab并高亮定位到目标行（如从D3-5跳转到D3-2的特定客户行）

### Requirement 20: 组件架构与代码拆分

**User Story:** As a 开发者, I want to D3预收账款底稿按Tab拆分为独立子组件和子composable, so that 代码可维护性好、每个文件控制在200-400行。

#### Acceptance Criteria

1. THE D3 组件 SHALL 注册新componentType: `d3-prepaid-accounts`，主入口为 GtD3PrepaidAccounts.vue（el-tabs容器，9个tab-pane）
2. THE D3 组件 SHALL 将每个sheet拆分为独立Vue子组件（D3TabAdjudication.vue / D3TabDetail.vue / D3TabAdjustment.vue / D3TabAnalysis.vue / D3TabLongTerm.vue / D3TabRelatedParty.vue / D3TabVoucherCheck.vue / D3TabDisclosureListed.vue / D3TabDisclosureSoe.vue），每文件200-400行
3. THE D3 组件 SHALL 拆分为独立composable：useD3FormData.ts（基础数据加载/保存）+ useD3FormulaEngine.ts（纯函数公式引擎）+ useD3CrossSheet.ts（跨sheet联动逻辑）
4. THE useD3FormulaEngine.ts SHALL 为纯函数模块（无副作用），包含：贷方科目期末=期初+贷方-借方、审定数=未审+AJE+RJE、变动率计算、合计行SUM、账龄聚合等全部公式
5. THE D3 组件 SHALL 在htmlRendererRegistry中注册'd3-prepaid-accounts'→GtD3PrepaidAccounts映射
6. THE D3 组件 SHALL 在wp_code_overrides.json中将D3/D3-1/D3-2的componentType映射为'd3-prepaid-accounts'
7. THE D3 组件 SHALL 在VALID_COMPONENT_TYPES中注册'd3-prepaid-accounts'
8. THE GtD3PrepaidAccounts.vue SHALL 支持selfLoad（当htmlData prop为null时自行调render-config?force_component_type=d3-prepaid-accounts）

### Requirement 21: 金额格式化与UI美化

**User Story:** As a 审计助理, I want to 所有金额数据以标准格式显示, so that 我能快速准确地阅读和核对数据。

#### Acceptance Criteria

1. THE Formula_Engine SHALL 对所有金额单元格应用 displayPrefs.fmtAmount 格式化（千分位分隔、保留2位小数）
2. WHEN 金额为负数时, THE Formula_Engine SHALL 以红色字体和括号格式显示（如 (1,234.56)）
3. WHEN 金额为零时, THE Formula_Engine SHALL 显示"-"而非"0.00"
4. THE Adjudication_Table SHALL 对比例列应用百分比格式（保留2位小数，如 12.34%）
5. THE Detail_Table SHALL 对"对方单位名称"列左对齐、对金额列右对齐
6. WHILE 数据正在加载时, THE D3 组件 SHALL 在表格区域显示el-skeleton占位动画
7. THE D3 组件 SHALL 统一使用displayPrefs.fmtDateTime格式化所有时间戳显示

### Requirement 22: 自动提取填充（TB取数）

**User Story:** As a 审计助理, I want to 审定表和分析表从试算平衡表自动获取数据, so that 期初/期末未审数和发生额不需要手工录入。

#### Acceptance Criteria

1. THE Adjudication_Table SHALL 通过auto_data_source resolver从trial_balance（科目2203）自动获取期初/期末未审数
2. THE Analysis_Table SHALL 通过auto_data_source resolver从tb_ledger（科目2203）自动获取借方/贷方发生额合计
3. THE Detail_Table SHALL 支持从tb_aux_balance（科目2203，按客户维度）批量导入客户级明细数据
4. WHEN TB数据更新时, THE Cross_Sheet_Engine SHALL 自动刷新依赖TB的单元格值
5. WHILE TB数据尚未导入时, THE Adjudication_Table SHALL 在未审数单元格显示"待导入TB"灰色占位文字
6. THE Analysis_Table SHALL 在数据来源列自动标注"取自TB"以明确数据追溯路径

### Requirement 23: D3-2期后结转与D3-7联动

**User Story:** As a 审计助理, I want to D3-2明细表的"期后结转"列与D3-7凭证检查表自动联动, so that 期后结转金额在两处保持一致。

#### Acceptance Criteria

1. WHEN D3-7"(2)期后结转检查"区块有新增样本且客户名称匹配D3-2行时, THE Detail_Table SHALL 自动将对应行的"期后结转"(Z列)累加该笔贷方金额
2. WHEN D3-2"期后结转"(Z列)手动编辑时, THE Voucher_Check SHALL 在"(2)期后结转"区块显示黄色提示"D3-2已有期后结转金额xxx，请确认是否已录入对应凭证"
3. THE Detail_Table SHALL 在"期后结转"列的合计值与D3-7"(2)期后结转"贷方金额合计进行交叉验证，不一致时黄色el-alert显示差额

### Requirement 24: D3与D7合同负债区分逻辑

**User Story:** As a 审计助理, I want to D3预收账款与D7合同负债有明确的区分判断辅助, so that 我能准确分类"合同不成立时已收取的对价"和"合同负债"。

#### Acceptance Criteria

1. THE Adjudication_Table SHALL 在CAS14准则提示折叠区中包含：预收账款(2203) vs 合同负债(2205)的区分决策树（合同是否成立→是=合同负债D7/否=预收账款D3）
2. THE Detail_Table SHALL 在"款项性质"下拉为"合同不成立时已收取的对价"时，显示蓝色info提示"注意：若合同后续成立，需重分类至合同负债(D7)"
3. THE Adjudication_Table SHALL 在底部提供GtIndexChip跳转D7合同负债底稿，方便对照核查

### Requirement 25: 后端Render策略与Resolver注册

**User Story:** As a 开发者, I want to D3底稿的后端渲染策略和auto_data resolver正确注册, so that render-config API能返回正确数据且TB自动取数功能正常工作。

#### Acceptance Criteria

1. THE RENDERER_DISPATCH SHALL 注册'd3-prepaid-accounts' componentType对应的render策略函数`_render_d3_prepaid_accounts`
2. THE render策略函数 SHALL 返回包含审定表双区块结构+明细表行数据+各sheet配置的完整html_data
3. THE auto_data_resolvers._REGISTRY SHALL 注册`d3_tb_unadjusted` resolver（从trial_balance科目2203取期初/期末未审数）
4. THE auto_data_resolvers._REGISTRY SHALL 注册`d3_ledger_analysis` resolver（从tb_ledger科目2203取借方/贷方发生额+按对方科目分拆）
5. THE account_package_registry.json SHALL 包含D3_prepaid_accounts工作包定义（含sheets清单对齐源模板10个有效sheet）
