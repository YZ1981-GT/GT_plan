# Requirements Document

## Introduction

D1 应收票据底稿的背书贴现组专属组件——覆盖"业务模式分析D1-6"、"备查簿核对D1-7"、"贴现背书明细D1-8"、"贴息检查D1-9"四个sheet。从现有 `useD1NotesReceivable.ts`（1237行）中拆出背书贴现相关逻辑为独立子组件+子composable。4个独立Vue组件 + 4个独立composable（每文件200-400行），全部做HTML精美组件（el-table + 金额格式化 + 动态行），OnlyOffice仅作降级模式。

核心业务逻辑：D1-6通过QA矩阵判定票据业务模式→影响列报分类（应收票据vs应收款项融资）；D1-7为31列宽表逐笔登记票据备查簿+与D1-2对账；D1-8为已贴现/已背书未到期票据检查明细；D1-9为贴息计算验证（P×R×D/360）。四表紧密关联，共同完成背书贴现业务的审计程序。

## Glossary

- **Business_Mode_Table**: 业务模式分析D1-6，通过QA矩阵判定票据组合的业务模式和列报项目
- **Memo_Reconciliation_Table**: 备查簿核对D1-7，逐笔票据备查簿明细+与明细账D1-2核对
- **Endorsement_Detail_Table**: 贴现背书明细D1-8，已贴现/已背书尚未到期票据的检查表
- **Interest_Check_Table**: 贴息检查D1-9，验证贴现利息计算的正确性
- **QA_Matrix**: 分类判断问答矩阵，4个问题×3组合列，每格Y/N，IF公式自动判定业务模式
- **Business_Mode_Result**: 业务模式判定结果，由QA矩阵IF公式自动计算（收取合同现金流量/出售/两者兼有）
- **Report_Item_Result**: 列报项目判定结果，由业务模式结果决定（应收票据/应收款项融资/两者）
- **Column_Group**: 列分组，D1-7的31列按语义分为基本信息区|流转区|金额区|审定区四组
- **Reconciliation_Area**: 核对区，备查簿合计与明细账D1-2数据的差异对比
- **Discount_Interest_Formula**: 贴息公式，应计贴现利息 = 票面金额 × 贴现率 × 贴息天数 / 360
- **Cross_Sheet_Ref**: 跨sheet引用，从D1-2原值明细表取数进行核对
- **Dynamic_Row**: 动态行，用户可新增/删除的数据行（逐笔票据行）
- **Summary_Row**: 合计行，自动SUM对应明细行（不可编辑）
- **Formula_Engine**: 前端公式引擎composable，实现QA判定IF公式+贴息P×R×D/360等计算
- **Dual_Mode**: 双模式切换，HTML精美组件 ↔ OnlyOffice在线编辑

## Requirements

### Requirement 1: 业务模式分析D1-6 — 审计目标与业务模式依据表

**User Story:** As a 审计助理, I want to 记录各票据组合的业务模式和具体依据, so that 我能在底稿中文档化业务模式判定过程。

#### Acceptance Criteria

1. THE Business_Mode_Table SHALL 在顶部显示审计目标区域（只读固定文本："了解公司应收票据的业务模式，判断其列报分类是否正确"）
2. THE Business_Mode_Table SHALL 渲染"(一)业务模式及依据"表，包含以下列：组合名称 | 业务模式 | 具体依据 | 索引号 | 备注
3. THE Business_Mode_Table SHALL 预设3个固定行：高信用银行承兑汇票 / 低信用银行承兑汇票 / 商业承兑汇票（行类型=fixed，不可删除）
4. THE Business_Mode_Table SHALL 对"业务模式"列提供下拉选择（"以收取合同现金流量为目标" / "以收取合同现金流量和出售金融资产为目标" / "其他"）
5. THE Business_Mode_Table SHALL 对"索引号"列渲染为 GtIndexChip（支持跳转到关联底稿）
6. THE Business_Mode_Table SHALL 对"具体依据"和"备注"列渲染为可编辑textarea

### Requirement 2: 业务模式分析D1-6 — 分类判断QA矩阵

**User Story:** As a 审计助理, I want to 通过问答矩阵自动判定票据业务模式和列报项目, so that 判定过程标准化且结论自动生成。

#### Acceptance Criteria

1. THE QA_Matrix SHALL 渲染"(二)分类判断"表，结构为4问题行×3组合列，表头为：问题 | 高信用银行承兑 | 低信用银行承兑 | 商业承兑
2. THE QA_Matrix SHALL 包含以下4个问题行（固定行不可删除）：
   - Q1: "是否以收取合同现金流量为目标（持有至到期为主）？"
   - Q2: "是否存在较频繁的贴现或背书转让行为？"
   - Q3: "贴现/背书转让是否占该组合总额的重要比例？"
   - Q4: "是否同时以收取合同现金流量和出售金融资产为目标？"
3. THE QA_Matrix SHALL 对每个答案单元格提供"是/否"下拉选择
4. WHEN Q1答"是"且Q2答"否"时, THE Formula_Engine SHALL 自动判定该组合业务模式为"以收取合同现金流量为目标的业务模式"
5. WHEN Q1答"是"且Q2答"是"且Q4答"是"时, THE Formula_Engine SHALL 自动判定该组合业务模式为"以收取合同现金流量和出售金融资产为目标的业务模式"
6. THE Formula_Engine SHALL 在QA矩阵下方自动显示判定结果行：业务模式结果（文字描述）
7. THE Formula_Engine SHALL 在业务模式结果行下方自动显示列报项目判定行：
   - "以收取合同现金流量为目标" → 列报项目="应收票据"
   - "以收取合同现金流量和出售金融资产为目标" → 列报项目="应收款项融资"
   - 其他组合 → 列报项目="以公允价值计量且其变动计入当期损益的金融资产"
8. THE Business_Mode_Table SHALL 将判定结果（业务模式+列报项目）持久化到 checklist_responses，供审定表D1-1引用

### Requirement 3: 业务模式分析D1-6 — 审计说明与结论

**User Story:** As a 审计助理, I want to 在业务模式分析底部记录审计说明和结论, so that 我能文档化审计判断过程。

#### Acceptance Criteria

1. THE Business_Mode_Table SHALL 在QA矩阵和判定结果后显示"审计说明"区域（textarea + 🤖AI生成按钮 + 💬复核对话入口）
2. THE Business_Mode_Table SHALL 在审计说明后显示"审计结论"区域（textarea + 🤖AI生成按钮 + 💬复核对话入口）
3. THE Business_Mode_Table SHALL 在审计结论后显示"编制提示"折叠区（`<details>` 蓝色左边线+浅蓝背景，默认收起），内容包含：
   - 中国证监会《监管规则适用指引——会计类第1号》相关规定
   - CAS 22/CAS 23 相关准则参考
   - SPPI现金流量特征测试说明
   - 业务模式与列报分类对应关系说明
   - 评估业务模式时应考虑的因素
4. WHEN 用户点击🤖AI按钮时, THE Business_Mode_Table SHALL 基于QA矩阵填写情况和判定结果生成审计说明/结论文本
5. THE Business_Mode_Table SHALL 通过 inject openReviewDialog 在审计说明和结论区域各放置💬固定复核对话入口按钮

### Requirement 4: 备查簿核对D1-7 — 票据备查簿明细宽表

**User Story:** As a 审计助理, I want to 在备查簿中逐笔登记所有票据的全生命周期信息, so that 我能完整追踪每笔票据从收到到到期/转让的全过程。

#### Acceptance Criteria

1. THE Memo_Reconciliation_Table SHALL 在顶部显示审计目标区域（只读固定文本）和审计过程描述
2. THE Memo_Reconciliation_Table SHALL 显示截止日期字段（el-date-picker，格式YYYY-MM-DD）
3. THE Memo_Reconciliation_Table SHALL 渲染31列宽表，列按四组分区显示：
   - 基本信息区（8列）：票据类型 | 票据号 | 收到日期 | 前手 | 出票日 | 出票人 | 承兑人 | 金额
   - 流转区（6列）：到期日 | 流转日 | 状态 | 被背书人 | 贴现银行 | 贴现息
   - 金额区（9列）：是否质押 | 审计日已贴现背书 | 年初余额 | 本期收到 | 本期背书 | 本期到期承兑 | 本期贴现 | 年末余额 | 期末未到期背书贴现
   - 审定区（8列）：是否终止确认 | 信用评级 | 审定应收款项融资 | 审定应收票据 | 关联关系 | 是否逾期 | 逾期转应收金额 | 备注
4. THE Memo_Reconciliation_Table SHALL 使用 el-table 横向滚动模式（fixed 左侧票据类型+票据号列）
5. THE Memo_Reconciliation_Table SHALL 对列分组显示表头二级分组（el-table-column 嵌套分组表头）
6. THE Memo_Reconciliation_Table SHALL 对不同列类型应用语义化编辑控件：
   - 日期列（收到日期/出票日/到期日/流转日）：el-date-picker
   - 金额列（金额/贴现息/各期余额）：数字输入 + displayPrefs.fmtAmount 格式化
   - 下拉列（票据类型/状态/是否质押/是否终止确认/信用评级/关联关系/是否逾期）：el-select
   - 文本列（票据号/前手/出票人/承兑人/被背书人/贴现银行/备注）：el-input
7. THE Memo_Reconciliation_Table SHALL 预设分类行结构：银行承兑汇票区（动态行）+ 银行承兑小计行（SUM） + 商业承兑汇票区（动态行）+ 商业承兑小计行（SUM） + 合计行（SUM）
8. WHEN 用户点击"添加票据"按钮时, THE Memo_Reconciliation_Table SHALL 在当前分类的小计行上方新增一个空行

### Requirement 5: 备查簿核对D1-7 — 核对区与跨Sheet取数

**User Story:** As a 审计助理, I want to 将备查簿合计与明细账D1-2自动核对, so that 我能发现两者之间的差异并追查原因。

#### Acceptance Criteria

1. THE Reconciliation_Area SHALL 在明细表下方渲染核对区表格，包含3行：
   - 备查簿合计行（从本表SUM自动计算：年初余额/本期收到/本期背书/本期到期/本期贴现/年末余额）
   - 明细账行（从D1-2跨sheet自动取数：期初审定/本期增加/本期减少/期末审定）
   - 差异行（= 备查簿 - 明细账，差异≠0时红色高亮）
2. THE Cross_Sheet_Ref SHALL 从同一个 allResponses Map 中读取 D1-cat-rows 前缀数据（纯 computed 响应式，不走 API）
3. WHEN D1-2数据变更时, THE Cross_Sheet_Ref SHALL 通过 computed 自动刷新核对区的明细账行数据
4. THE Reconciliation_Area SHALL 以浅蓝色背景标记跨sheet取数单元格，tooltip显示"取自原值明细表D1-2"
5. IF D1-2数据未加载, THEN THE Cross_Sheet_Ref SHALL 在明细账行显示"-"占位符+黄色三角警告图标
6. THE Memo_Reconciliation_Table SHALL 在核对区下方渲染"贴现背书统计区"（从本表SUMIFS计算已贴现/已背书的汇总金额）

### Requirement 6: 备查簿核对D1-7 — 审计说明与结论

**User Story:** As a 审计助理, I want to 在备查簿核对底部记录审计说明和结论, so that 我能文档化核对过程和发现。

#### Acceptance Criteria

1. THE Memo_Reconciliation_Table SHALL 在核对区后显示"审计说明"区域（textarea + 🤖AI生成按钮 + 💬复核对话入口）
2. THE Memo_Reconciliation_Table SHALL 在审计说明后显示"审计结论"区域（textarea + 🤖AI生成按钮 + 💬复核对话入口）
3. THE Memo_Reconciliation_Table SHALL 在审计结论后显示"编制提示"折叠区（`<details>` 蓝色左边线+浅蓝背景，默认收起）
4. WHEN 用户点击🤖AI按钮时, THE Memo_Reconciliation_Table SHALL 基于核对区差异数据和票据统计生成审计说明/结论文本
5. THE Memo_Reconciliation_Table SHALL 通过 inject openReviewDialog 在审计说明和结论区域各放置💬固定复核对话入口按钮

### Requirement 7: 贴现背书明细D1-8 — 已贴现未到期检查表

**User Story:** As a 审计助理, I want to 检查已贴现尚未到期的票据明细, so that 我能核实贴现业务的会计处理是否正确。

#### Acceptance Criteria

1. THE Endorsement_Detail_Table SHALL 渲染"(一)已贴现尚未到期票据检查表"，包含以下16列：票据种类 | 收到日期 | 出票人 | 票据号 | 汇票金额 | 已计利息 | 出票日 | 到期日 | 承兑银行 | 信用等级 | 贴现银行 | 贴现金额 | 贴现息 | 是否终止确认 | 会计处理是否正确 | 索引号
2. THE Endorsement_Detail_Table SHALL 支持动态行增删（用户点击"添加行"在合计行上方新增空行）
3. THE Formula_Engine SHALL 自动计算合计行（= SUM 动态行的汇票金额/贴现金额/贴现息列）
4. THE Endorsement_Detail_Table SHALL 对列应用语义化控件：
   - 日期列：el-date-picker
   - 金额列：数字输入 + fmtAmount
   - "是否终止确认"/"会计处理是否正确"列：el-select（是/否）
   - "信用等级"列：el-select（AAA/AA+/AA/AA-/A+/A/其他）
   - "索引号"列：GtIndexChip
5. THE Endorsement_Detail_Table SHALL 对"会计处理是否正确"为"否"的行以红色背景高亮

### Requirement 8: 贴现背书明细D1-8 — 已背书未到期检查表

**User Story:** As a 审计助理, I want to 检查已背书转让尚未到期的票据明细, so that 我能核实背书业务的会计处理是否正确。

#### Acceptance Criteria

1. THE Endorsement_Detail_Table SHALL 渲染"(二)已背书尚未到期票据检查表"，结构与贴现检查表相同（16列）
2. THE Endorsement_Detail_Table SHALL 支持动态行增删
3. THE Formula_Engine SHALL 自动计算合计行（= SUM 动态行的汇票金额列）
4. THE Endorsement_Detail_Table SHALL 对背书表同样应用语义化控件和格式化规则
5. THE Endorsement_Detail_Table SHALL 在两个检查表之间显示分隔标题（"(一)已贴现..." / "(二)已背书..."）

### Requirement 9: 贴现背书明细D1-8 — 审计说明与结论

**User Story:** As a 审计助理, I want to 在贴现背书明细底部记录审计说明和结论, so that 我能文档化检查过程。

#### Acceptance Criteria

1. THE Endorsement_Detail_Table SHALL 在两个检查表后显示"审计说明"区域（textarea + 🤖AI生成按钮 + 💬复核对话入口）
2. THE Endorsement_Detail_Table SHALL 在审计说明后显示"审计结论"区域（textarea + 🤖AI生成按钮 + 💬复核对话入口）
3. WHEN 用户点击🤖AI按钮时, THE Endorsement_Detail_Table SHALL 基于两表的终止确认判断结果和会计处理检查情况生成审计说明/结论
4. THE Endorsement_Detail_Table SHALL 通过 inject openReviewDialog 在审计说明和结论区域各放置💬固定复核对话入口按钮

### Requirement 10: 贴息检查D1-9 — 贴息计算表

**User Story:** As a 审计助理, I want to 验证每笔贴现交易的贴现利息计算是否正确, so that 我能发现贴息计算差异并追查原因。

#### Acceptance Criteria

1. THE Interest_Check_Table SHALL 在顶部显示审计目标区域（只读固定文本）和审计过程描述
2. THE Interest_Check_Table SHALL 渲染贴息计算表，包含以下13列：票据类型 | 票面金额 | 票面利率 | 出票日期 | 到期日 | 到期日票据价值 | 贴现日期 | 贴息天数 | 贴现率 | 应计贴现利息 | 账面贴现利息 | 差异 | 备注
3. THE Interest_Check_Table SHALL 支持动态行增删（用户点击"添加行"在合计行上方新增空行）
4. THE Formula_Engine SHALL 自动计算"贴息天数"列（= 到期日 - 贴现日期，单位：天）
5. THE Formula_Engine SHALL 自动计算"应计贴现利息"列（= 票面金额 × 贴现率 × 贴息天数 / 360）
6. THE Formula_Engine SHALL 自动计算"差异"列（= 应计贴现利息 - 账面贴现利息）
7. WHEN 差异列不为零时, THE Interest_Check_Table SHALL 以红色高亮显示差异单元格
8. THE Formula_Engine SHALL 自动计算合计行（= SUM 动态行的票面金额/应计贴现利息/账面贴现利息/差异列）
9. THE Interest_Check_Table SHALL 对列应用语义化控件：
   - 日期列（出票日期/到期日/贴现日期）：el-date-picker
   - 金额列（票面金额/到期日票据价值/应计利息/账面利息/差异）：数字输入 + fmtAmount
   - 利率列（票面利率/贴现率）：百分比输入（保留4位小数）
   - 票据类型列：el-select（银行承兑汇票/商业承兑汇票）
   - 备注列：el-input

### Requirement 11: 贴息检查D1-9 — 审计说明与结论

**User Story:** As a 审计助理, I want to 在贴息检查底部记录审计说明和结论, so that 我能文档化贴息验证过程和发现。

#### Acceptance Criteria

1. THE Interest_Check_Table SHALL 在贴息计算表后显示"审计说明"区域（textarea + 🤖AI生成按钮 + 💬复核对话入口）
2. THE Interest_Check_Table SHALL 在审计说明后显示"审计结论"区域（textarea + 🤖AI生成按钮 + 💬复核对话入口）
3. WHEN 用户点击🤖AI按钮时, THE Interest_Check_Table SHALL 基于贴息差异汇总情况（差异总额、差异笔数、最大单笔差异）生成审计说明/结论
4. THE Interest_Check_Table SHALL 通过 inject openReviewDialog 在审计说明和结论区域各放置💬固定复核对话入口按钮

### Requirement 12: 双模式切换（四表通用）

**User Story:** As a 审计助理, I want to 在HTML精美组件和OnlyOffice编辑模式之间切换, so that 我能根据需要选择最适合的编辑方式。

#### Acceptance Criteria

1. THE Dual_Mode SHALL 在每个sheet的Tab页头部显示 el-segmented 切换控件（"结构化视图" | "在线编辑"）
2. WHEN 用户切换到OnlyOffice模式时, THE Dual_Mode SHALL 打开完整xlsx文件并通过OnlyOffice API隐藏非当前sheet（SetVisible(false)），只显示当前Tab对应的sheet
3. WHEN 用户从OnlyOffice模式切回HTML模式时, THE Dual_Mode SHALL 重新加载 checklist_responses 数据以反映在OO中的编辑
4. WHILE OnlyOffice服务不可用时, THE Dual_Mode SHALL 禁用"在线编辑"选项并显示 tooltip"OnlyOffice服务不可用"
5. THE Dual_Mode SHALL 保留跨sheet公式完整性（不拆分文件）

### Requirement 13: 持久化与数据存储（四表通用）

**User Story:** As a 审计助理, I want to 所有编辑内容自动保存, so that 我不会因为意外关闭页面而丢失数据。

#### Acceptance Criteria

1. THE Business_Mode_Table SHALL 使用 checklist_responses 表存储数据，item_id 前缀为"D1-bm-"（business mode）
2. THE Memo_Reconciliation_Table SHALL 使用 checklist_responses 表存储数据，item_id 前缀为"D1-memo-"
3. THE Endorsement_Detail_Table SHALL 使用 checklist_responses 表存储数据，item_id 前缀为"D1-endorse-"
4. THE Interest_Check_Table SHALL 使用 checklist_responses 表存储数据，item_id 前缀为"D1-interest-"
5. WHEN 用户编辑任意金额/文本/日期字段后2秒无操作时, THE Formula_Engine SHALL 触发 debounce 自动保存
6. WHEN 用户切换下拉选择类字段时, THE Formula_Engine SHALL 立即保存该字段
7. THE Memo_Reconciliation_Table SHALL 将票据动态行以JSON数组格式存储于 remark 字段（item_id="D1-memo-rows"）
8. THE Endorsement_Detail_Table SHALL 将贴现/背书动态行分别存储（item_id="D1-endorse-discount-rows" / "D1-endorse-transfer-rows"）
9. THE Interest_Check_Table SHALL 将贴息行以JSON数组格式存储（item_id="D1-interest-rows"）

### Requirement 14: 导入导出三级（四表通用）

**User Story:** As a 审计助理, I want to 支持从Excel导入数据和导出模板, so that 我能利用已有的离线填写的数据批量录入。

#### Acceptance Criteria

1. WHEN 用户点击"导出模板"按钮时, THE Import_Export SHALL 生成当前sheet对应的空白xlsx模板（含表头+格式，无数据行）
2. WHEN 用户点击"导出数据"按钮时, THE Import_Export SHALL 生成包含当前数据的xlsx文件
3. WHEN 用户上传已填写的xlsx文件时, THE Import_Export SHALL 解析文件内容并将数据回写到 checklist_responses
4. IF 导入的xlsx格式不符合模板结构, THEN THE Import_Export SHALL 显示错误提示并列出不匹配的列名
5. WHEN 导入D1-7（备查簿）xlsx且行数超过模板预设时, THE Import_Export SHALL 自动扩展动态行以容纳全部数据
6. THE Import_Export SHALL 在导入完成后显示摘要（"成功导入N行数据，M个字段已更新"）

### Requirement 15: 组件拆分与代码架构

**User Story:** As a 开发者, I want to 将背书贴现组逻辑拆分为独立子组件和子composable, so that 代码可维护性好、每个文件控制在200-400行。

#### Acceptance Criteria

1. THE Business_Mode_Table SHALL 拆分为独立Vue子组件 D1TabBusinessMode.vue（~250行）
2. THE Memo_Reconciliation_Table SHALL 拆分为独立Vue子组件 D1TabMemoReconciliation.vue（~400行）
3. THE Endorsement_Detail_Table SHALL 拆分为独立Vue子组件 D1TabEndorsementDetail.vue（~350行）
4. THE Interest_Check_Table SHALL 拆分为独立Vue子组件 D1TabInterestCheck.vue（~300行）
5. THE Business_Mode_Table SHALL 有独立composable useD1BusinessMode.ts（~200行），包含QA矩阵+IF公式判定+持久化
6. THE Memo_Reconciliation_Table SHALL 有独立composable useD1MemoReconciliation.ts（~350行），包含31列宽表CRUD+核对区跨sheet取数+SUMIFS统计
7. THE Endorsement_Detail_Table SHALL 有独立composable useD1EndorsementDetail.ts（~250行），包含贴现/背书双表动态行CRUD+合计
8. THE Interest_Check_Table SHALL 有独立composable useD1InterestCheck.ts（~250行），包含贴息公式引擎+差异计算+持久化

### Requirement 16: 金额格式化与UI美化（四表通用）

**User Story:** As a 审计助理, I want to 所有金额数据以标准格式显示, so that 我能快速准确地阅读和核对数据。

#### Acceptance Criteria

1. THE Formula_Engine SHALL 对所有金额单元格应用 displayPrefs.fmtAmount 格式化（千分位分隔、保留2位小数）
2. WHEN 金额为负数时, THE Formula_Engine SHALL 以红色字体和括号格式显示（如 (1,234.56)）
3. WHEN 金额为零时, THE Formula_Engine SHALL 显示"-"而非"0.00"
4. THE Formula_Engine SHALL 对比例/利率列应用百分比格式（保留2-4位小数）
5. THE Memo_Reconciliation_Table SHALL 对票据号列等文本列左对齐、对金额列右对齐
6. WHILE 数据正在加载时, THE Formula_Engine SHALL 在表格区域显示 el-skeleton 占位动画

### Requirement 17: D1-7 备查簿与D1-8明细表数据联动

**User Story:** As a 审计助理, I want to D1-8的贴现背书明细能从D1-7备查簿自动筛选取数, so that 我不需要在两个表之间手动复制数据。

#### Acceptance Criteria

1. THE Endorsement_Detail_Table SHALL 提供"从备查簿导入"按钮，点击后自动从D1-7备查簿中筛选状态为"已贴现"的票据填入贴现检查表
2. THE Endorsement_Detail_Table SHALL 提供"从备查簿导入"按钮，点击后自动从D1-7备查簿中筛选状态为"已背书"的票据填入背书检查表
3. THE Cross_Sheet_Ref SHALL 从同一个 allResponses Map 中读取 D1-memo-rows 数据（纯 computed 响应式）
4. WHEN D1-7备查簿数据变更时, THE Endorsement_Detail_Table SHALL 在"从备查簿导入"时获取最新数据
5. THE Endorsement_Detail_Table SHALL 在导入后允许用户编辑修改（非只读引用）

### Requirement 18: 行类型规范与复核对话集成

**User Story:** As a 开发者, I want to 统一行类型规范并集成复核对话能力, so that 四个表格行为一致且支持审计复核流程。

#### Acceptance Criteria

1. THE Formula_Engine SHALL 对每个表格的行区分三种类型：
   - fixed: 固定行（不可删除，始终存在）
   - dynamic: 浮动行（用户动态添加，可删除）
   - summary: 合计行（自动计算，不可编辑）
2. THE Formula_Engine SHALL 在固定行左侧显示锁定图标，浮动行左侧显示删除按钮
3. THE Business_Mode_Table SHALL 通过 `useReviewDialogProvider`（inject）集成通用复核对话能力：表格单元格右键菜单"发起复核对话"
4. THE Memo_Reconciliation_Table SHALL 通过 inject openReviewDialog 集成复核对话能力
5. THE Endorsement_Detail_Table SHALL 通过 inject openReviewDialog 集成复核对话能力
6. THE Interest_Check_Table SHALL 通过 inject openReviewDialog 集成复核对话能力
7. WHEN 有活跃复核对话线程时, THE Formula_Engine SHALL 在对应位置显示蓝/红圆点标记
