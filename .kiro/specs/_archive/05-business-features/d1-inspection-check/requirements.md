# Requirements Document

## Introduction

D1 应收票据底稿的监盘核查组专属组件——覆盖"应收票据监盘表D1-10"、"关联方关系及交易检查表D1-11"、"应收票据质押检查表D1-12"、"应收票据检查表D1-13"四个sheet。从现有 `useD1NotesReceivable.ts`（1237行）中拆出监盘核查相关逻辑为独立子组件+子composable。4个独立Vue组件 + 4个独立composable（每文件200-400行），全部做HTML精美组件（el-table + 金额格式化 + 动态行 + 公式自动计算），OnlyOffice仅作降级模式。

核心业务逻辑：D1-10为应收票据实物监盘表（d-form-confirmation类，15列宽表），逐笔记录监盘日结存票据的完整信息并核对是否存在差异；D1-11为关联方关系及交易检查表（13列），登记关联方票据往来的期初/期末余额变动+坏账准备+账龄+性质+期后回收情况；D1-12为应收票据质押检查表（16列），逐笔登记已质押票据的完整票据信息+质押详情（质权人/原因/条件/期限/协议）；D1-13为应收票据检查表（抽样/凭证核对form），定义抽样总体和样本量→逐笔核查票据的存在性/准确性/记录恰当性→汇总例外并得出结论。四表共同完成应收票据监盘核查组的审计程序。

## Glossary

- **Inventory_Count_Table**: 应收票据监盘表D1-10（component_type: d-form-confirmation, class_code: D-盘点），15列宽表逐笔记录监盘日票据结存
- **Related_Party_Check_Table**: 应收票据关联方关系及交易检查表D1-11（component_type: d-form-table, class_code: D-检查表），13列登记关联方票据余额变动
- **Pledge_Check_Table**: 应收票据质押情况检查表D1-12（component_type: d-form-table, class_code: D-检查表），16列逐笔登记质押票据详情
- **Sampling_Vouching_Table**: 应收票据检查表D1-13（component_type: d-form-table, class_code: D-检查表），抽样凭证核对表
- **Inventory_Detail_Area**: 监盘日结存区（D1-10列A-L合并表头），包含票据类型/票据号/出票日/出票人/承兑人/金额/到期日/前手/收到日期等12列票据基本信息
- **Difference_Column**: 是否存在差异列（D1-10列M），记录每笔票据监盘核对结果
- **Difference_Reason_Column**: 差异原因列（D1-10列N），说明差异原因
- **Balance_Formula_Area**: D1-10核对区（H21合计行 + A25/D25/F25/I25/L25/N25），对监盘结果进行汇总核对
- **RP_Balance_Change**: 关联方余额变动区（D1-11列C-H），期初余额→借方发生→贷方发生→期末余额(C+D-E)→减坏账准备→账面价值(F-G)
- **RP_Detail_Area**: 关联方详情区（D1-11列I-M），发生时间及账龄/发生原因(款项性质)/期后已兑现或已贴现/索引号/备注
- **Pledge_Note_Info**: 质押票据基本信息（D1-12列A-I），票据类型/号码/收到日期/前手/出票日/出票人/承兑人/金额/到期日
- **Pledge_Detail_Area**: 质押详情区（D1-12列J-P），质押金额/质权人/质押原因/质押条件/质押期限/质押协议/索引号
- **Sample_Population_Area**: 抽样总体定义区（D1-13），定义测试总体和样本量
- **Vouching_Detail_Area**: 凭证核对明细区（D1-13），逐笔核查抽样票据的存在性/准确性/记录恰当性
- **Exception_Summary_Area**: 例外汇总区（D1-13 E48-G50），汇总核查例外和测试结论
- **Cross_Sheet_Ref**: 跨sheet引用，从allResponses Map读取其他spec的数据（纯computed响应式）
- **Dynamic_Row**: 动态行，用户可新增/删除的数据行
- **Summary_Row**: 合计行，自动SUM对应明细行（不可编辑）
- **Formula_Engine**: 前端公式引擎composable，实现期末余额(C+D-E)/账面价值(F-G)/质押合计/核对差异等计算
- **Dual_Mode**: 双模式切换，HTML精美组件 ↔ OnlyOffice在线编辑
- **GtIndexChip**: 跨底稿索引跳转芯片，点击可跳转到关联底稿对应位置

## Requirements

### Requirement 1: 应收票据监盘表D1-10 — 监盘日结存15列宽表

**User Story:** As a 审计助理, I want to 在监盘表中逐笔记录监盘日实际结存的应收票据信息, so that 我能完整文档化票据实物盘点结果。

#### Acceptance Criteria

1. THE Inventory_Count_Table SHALL 在顶部显示审计目标区域（只读静态文本，对应源模板rows 5-9的审计目标和程序描述）
2. THE Inventory_Count_Table SHALL 渲染15列宽表（A-O），使用el-table横向滚动模式，列按两组分区显示：
   - 监盘日结存区（A-L合并表头，12列）：票据类型 | 票据号 | 出票日 | 出票人 | 承兑人 | 金额 | 到期日 | 前手 | 收到日期 | 背书/贴现日 | 被背书人/贴现行 | 票据状态
   - 核查结果区（M-O，3列）：是否存在差异 | 差异原因 | 索引号
3. THE Inventory_Count_Table SHALL 使用el-table-column嵌套分组表头（A-L共用"监盘日结存"二级表头）
4. THE Inventory_Count_Table SHALL 支持动态行增删（点击"添加票据"在合计行上方新增空行）
5. THE Inventory_Count_Table SHALL 对列应用语义化编辑控件：
   - 日期列（出票日/到期日/收到日期/背书贴现日）：el-date-picker
   - 金额列：数字输入 + displayPrefs.fmtAmount 格式化
   - 票据类型列：el-select（银行承兑汇票/商业承兑汇票）
   - 票据状态列：el-select（在库/已背书/已贴现/已到期/已质押）
   - 是否存在差异列：el-select（是/否）
   - 差异原因列：el-input（textarea模式，仅当差异="是"时可编辑）
   - 索引号列：GtIndexChip（支持跳转到关联底稿）
   - 其他文本列（票据号/出票人/承兑人/前手/被背书人）：el-input
6. THE Inventory_Count_Table SHALL 对"是否存在差异"为"是"的行以红色背景高亮

### Requirement 2: 应收票据监盘表D1-10 — 合计行与核对区

**User Story:** As a 审计助理, I want to 将监盘日票据金额合计与账面余额自动核对, so that 我能发现监盘结果与账面记录的差异。

#### Acceptance Criteria

1. THE Formula_Engine SHALL 自动计算H21合计行（= SUM所有动态行的"金额"列）
2. THE Balance_Formula_Area SHALL 在明细表下方渲染核对区（对应源模板A25/D25/F25/I25/L25/N25），包含以下核对项目：
   - A25: 监盘日票据结存合计（从H21取数）
   - D25: 账面应收票据余额（从D1审定表跨sheet取数）
   - F25: 差异金额（= A25 - D25）
   - I25: 监盘差异说明（textarea可编辑）
   - L25: 审计结论（el-select: 无差异/差异已获合理解释/存在未解决差异）
   - N25: 索引号（GtIndexChip）
3. THE Cross_Sheet_Ref SHALL 从同一allResponses Map中读取D1-memo-rows前缀数据（纯computed响应式跨Spec取数，用于核对区账面余额）
4. WHEN 差异金额F25≠0时, THE Balance_Formula_Area SHALL 以红色高亮显示差异金额
5. IF D1审定表数据未加载, THEN THE Cross_Sheet_Ref SHALL 在账面余额位置显示"-"占位符+黄色三角警告图标

### Requirement 3: 应收票据监盘表D1-10 — 审计说明与结论

**User Story:** As a 审计助理, I want to 在监盘表底部记录审计说明和结论, so that 我能文档化监盘验证过程和发现。

#### Acceptance Criteria

1. THE Inventory_Count_Table SHALL 在核对区后显示"审计说明"区域（textarea + 🤖AI生成按钮 + 💬复核对话入口）
2. THE Inventory_Count_Table SHALL 在审计说明后显示"审计结论"区域（textarea + 🤖AI生成按钮 + 💬复核对话入口）
3. THE Inventory_Count_Table SHALL 在审计结论后显示"编制提示"折叠区（`<details>` 蓝色左边线+浅蓝背景，默认收起），内容包含：
   - 票据监盘程序说明（核实票据实物/银行回函/到期兑付记录）
   - 监盘日与资产负债表日不一致时的倒推说明
   - 差异追查要求说明（逐笔说明差异原因并取得证据）
4. WHEN 用户点击🤖AI按钮时, THE Inventory_Count_Table SHALL 基于差异笔数和金额生成审计说明/结论文本
5. THE Inventory_Count_Table SHALL 通过 inject openReviewDialog 在审计说明和结论区域各放置💬固定复核对话入口按钮

### Requirement 4: 关联方关系及交易检查表D1-11 — 13列关联方明细表

**User Story:** As a 审计助理, I want to 逐笔登记关联方票据余额变动和详细信息, so that 我能完整记录关联方票据交易并评估披露充分性。

#### Acceptance Criteria

1. THE Related_Party_Check_Table SHALL 在顶部显示审计目标区域（只读静态文本，对应源模板rows 5-8）
2. THE Related_Party_Check_Table SHALL 渲染13列el-table，列对应源模板header_row 10：
   - A: 关联方名称（el-input）
   - B: 关联关系（el-select: 母公司/子公司/联营企业/合营企业/关键管理人员/其他关联方）
   - C: 期初余额（数字输入 + fmtAmount）
   - D: 借方发生（数字输入 + fmtAmount）
   - E: 贷方发生（数字输入 + fmtAmount）
   - F: 期末余额（公式自动计算: C+D-E，只读）
   - G: 减：坏账准备（数字输入 + fmtAmount）
   - H: 账面价值（公式自动计算: F-G，只读）
   - I: 发生时间及账龄（el-input）
   - J: 发生原因（款项性质）（el-input textarea模式）
   - K: 期后已兑现或已贴现（数字输入 + fmtAmount）
   - L: 索引号（GtIndexChip）
   - M: 备注（el-input）
3. THE Related_Party_Check_Table SHALL 支持动态行增删（点击"添加关联方"在合计行上方新增空行）
4. THE Formula_Engine SHALL 自动计算每行的期末余额F列（= C + D - E）
5. THE Formula_Engine SHALL 自动计算每行的账面价值H列（= F - G）
6. THE Related_Party_Check_Table SHALL 对金额列（C/D/E/F/G/H/K）右对齐，文本列左对齐

### Requirement 5: 关联方关系及交易检查表D1-11 — 合计行与跨Spec取数

**User Story:** As a 审计助理, I want to 自动计算关联方余额合计并与审定表数据核对, so that 我能验证关联方汇总与总账一致。

#### Acceptance Criteria

1. THE Formula_Engine SHALL 自动计算Row 14合计行（= SUM动态行的C/D/E/F/G/H/K列，对应源模板C14/D14/E14/F14/G14/H14/K14公式）
2. THE Cross_Sheet_Ref SHALL 从同一allResponses Map中读取D1-adj-*前缀数据（审定表期初/期末余额，纯computed响应式跨Spec取数）
3. THE Related_Party_Check_Table SHALL 在合计行下方渲染核对区：关联方期末余额合计 vs 审定表期末余额 → 差异
4. WHEN 差异≠0时, THE Related_Party_Check_Table SHALL 以红色高亮显示差异金额
5. IF 审定表数据未加载, THEN THE Cross_Sheet_Ref SHALL 在核对区显示"-"占位符+黄色三角警告图标

### Requirement 6: 关联方关系及交易检查表D1-11 — 审计说明与结论

**User Story:** As a 审计助理, I want to 在关联方检查表底部记录审计说明和结论, so that 我能文档化关联方交易检查过程和发现。

#### Acceptance Criteria

1. THE Related_Party_Check_Table SHALL 在核对区后显示"审计说明"区域（textarea + 🤖AI生成按钮 + 💬复核对话入口）
2. THE Related_Party_Check_Table SHALL 在审计说明后显示"审计结论"区域（textarea + 🤖AI生成按钮 + 💬复核对话入口）
3. THE Related_Party_Check_Table SHALL 在审计结论后显示"编制提示"折叠区（`<details>` 蓝色左边线+浅蓝背景，默认收起），内容包含：
   - CAS 36 关联方披露准则要求（关联方关系/交易金额/余额/承诺）
   - 关联方票据交易公允性判断标准
   - 期后回收情况对坏账准备的影响评估
4. WHEN 用户点击🤖AI按钮时, THE Related_Party_Check_Table SHALL 基于关联方交易金额、坏账准备和期后回收情况生成审计说明/结论
5. THE Related_Party_Check_Table SHALL 通过 inject openReviewDialog 在审计说明和结论区域各放置💬固定复核对话入口按钮

### Requirement 7: 应收票据质押检查表D1-12 — 16列质押明细宽表

**User Story:** As a 审计助理, I want to 逐笔登记已质押票据的完整信息和质押详情, so that 我能完整记录受限资产并评估质押风险和披露充分性。

#### Acceptance Criteria

1. THE Pledge_Check_Table SHALL 在顶部显示审计目标区域（只读静态文本，对应源模板rows 5-8）
2. THE Pledge_Check_Table SHALL 渲染16列el-table（A-P），使用横向滚动模式，列按两组分区：
   - 票据基本信息区（A-I，9列）：票据类型 | 票据号码 | 收到票据日期 | 票据前手名称 | 出票日期 | 出票人名称 | 承兑人名称 | 票据金额 | 票据到期日
   - 质押详情区（J-P，7列）：质押金额 | 质权人 | 质押原因 | 质押条件 | 质押期限 | 质押协议 | 索引号
3. THE Pledge_Check_Table SHALL 使用el-table-column嵌套分组表头（A-I"票据基本信息" / J-P"质押详情"）
4. THE Pledge_Check_Table SHALL 支持动态行增删（点击"添加质押票据"在合计行上方新增空行）
5. THE Pledge_Check_Table SHALL 对列应用语义化编辑控件：
   - 日期列（收到票据日期/出票日期/票据到期日）：el-date-picker
   - 金额列（票据金额/质押金额）：数字输入 + displayPrefs.fmtAmount 格式化
   - 票据类型列：el-select（银行承兑汇票/商业承兑汇票）
   - 质押期限列：el-date-picker range（起止日期）
   - 质押协议列：el-input（可输入协议编号或描述）
   - 索引号列：GtIndexChip（支持跳转）
   - 其他文本列（票据号码/前手/出票人/承兑人/质权人/质押原因/质押条件）：el-input
6. THE Pledge_Check_Table SHALL 对左侧票据类型+票据号码列使用fixed定位（横向滚动时保持可见）

### Requirement 8: 应收票据质押检查表D1-12 — 合计行与质押比例预警

**User Story:** As a 审计助理, I want to 自动计算票据金额和质押金额合计并进行质押比例预警, so that 我能及时关注高质押率的审计风险。

#### Acceptance Criteria

1. THE Formula_Engine SHALL 自动计算Row 18合计行：H18=SUM(票据金额列) / J18=SUM(质押金额列)（对应源模板H18/J18公式）
2. THE Formula_Engine SHALL 从同一allResponses Map中读取审定表净值（D1-adj-book-value-*前缀，纯computed响应式跨Spec取数）
3. THE Formula_Engine SHALL 自动计算质押比例（= J18质押金额合计 / 审定表净值）
4. WHEN 审定表净值为零或未加载时, THE Formula_Engine SHALL 将质押比例显示为"N/A"
5. WHEN 质押比例超过50%时, THE Pledge_Check_Table SHALL 在合计区旁显示橙色预警标签（"⚠️ 质押比例超过50%，请关注受限资产披露"）
6. THE Pledge_Check_Table SHALL 在合计行下方渲染质押汇总区：票据金额合计(H18) | 质押金额合计(J18) | 审定表净值 | 质押比例（百分比格式）

### Requirement 9: 应收票据质押检查表D1-12 — 审计说明与结论

**User Story:** As a 审计助理, I want to 在质押检查表底部记录审计说明和结论, so that 我能文档化质押检查发现和受限资产评估。

#### Acceptance Criteria

1. THE Pledge_Check_Table SHALL 在汇总区后显示"审计说明"区域（textarea + 🤖AI生成按钮 + 💬复核对话入口）
2. THE Pledge_Check_Table SHALL 在审计说明后显示"审计结论"区域（textarea + 🤖AI生成按钮 + 💬复核对话入口）
3. THE Pledge_Check_Table SHALL 在审计结论后显示"编制提示"折叠区（`<details>` 蓝色左边线+浅蓝背景，默认收起），内容包含：
   - 质押票据作为受限资产的披露要求（CAS 36第六十六条）
   - 质权设立的合法性审核要点（质押协议/登记/生效条件）
   - 质押比例对持续经营假设的影响评估
   - 质押期限与票据到期日匹配性检查
4. WHEN 用户点击🤖AI按钮时, THE Pledge_Check_Table SHALL 基于质押比例和受限资产详情生成审计说明/结论
5. THE Pledge_Check_Table SHALL 通过 inject openReviewDialog 在审计说明和结论区域各放置💬固定复核对话入口按钮

### Requirement 10: 应收票据检查表D1-13 — 抽样总体与样本量定义

**User Story:** As a 审计助理, I want to 定义测试总体和确定抽样样本量, so that 我能按照审计抽样准则(CAS 1314)设计实质性细节测试。

#### Acceptance Criteria

1. THE Sampling_Vouching_Table SHALL 在顶部显示审计目标区域（只读静态文本，对应源模板rows 5-7）
2. THE Sample_Population_Area SHALL 渲染抽样总体定义区，包含以下字段：
   - A列"抽样总体"：描述本次测试的票据总体范围（el-input textarea）
   - B列"测试总体扣除特定样本以外的样本，共XX笔、金额XX"：总体笔数（数字输入）+ 总体金额（数字输入 + fmtAmount）
   - H列"确定的抽样样本量"：样本量（数字输入）
   - I列"抽取XX笔（如果使用了样本计算器计算样本量，样本量计算过程见..."：抽取笔数 + 索引号（GtIndexChip跳转到样本计算器底稿）
3. THE Sample_Population_Area SHALL 支持特定样本区域：列出从总体中单独抽出的大额/异常项目（动态行：项目描述 | 金额 | 抽出原因）
4. THE Sampling_Vouching_Table SHALL 在抽样定义区下方显示分隔线和"凭证核对明细"标题

### Requirement 11: 应收票据检查表D1-13 — 凭证核对明细表

**User Story:** As a 审计助理, I want to 对每笔抽样票据逐项核查存在性、准确性和记录恰当性, so that 我能通过细节测试获取充分适当的审计证据。

#### Acceptance Criteria

1. THE Vouching_Detail_Area SHALL 渲染凭证核对明细el-table，包含以下列：
   - 序号（自动编号，只读）
   - 票据类型（el-select）
   - 票据号码（el-input）
   - 出票人（el-input）
   - 承兑人（el-input）
   - 金额（数字输入 + fmtAmount）
   - 到期日（el-date-picker）
   - 存在性验证（el-select: 已核实/未核实/不适用，tooltip"追踪至实物/银行回函/到期兑付记录"）
   - 准确性验证（el-select: 金额一致/金额不一致/不适用，tooltip"核对原始凭证金额"）
   - 记录恰当性（el-select: 恰当/不恰当/不适用，tooltip"验证入账期间和科目"）
   - 备注（el-input）
   - 索引号（GtIndexChip）
2. THE Vouching_Detail_Area SHALL 支持动态行增删（点击"添加核查项"新增空行，预设行数=Requirement 10中确定的样本量）
3. THE Vouching_Detail_Area SHALL 对验证结果列使用颜色编码：已核实/金额一致/恰当=绿色文字；未核实/金额不一致/不恰当=红色文字
4. THE Vouching_Detail_Area SHALL 对"未核实"或"金额不一致"或"不恰当"的行以浅红色背景标记（例外项）

### Requirement 12: 应收票据检查表D1-13 — 核对结果与例外汇总

**User Story:** As a 审计助理, I want to 自动汇总核查结果和例外情况, so that 我能快速得出测试结论并评估是否需要扩大样本。

#### Acceptance Criteria

1. THE Formula_Engine SHALL 自动计算G32/H32核对结果区（对应源模板公式）：
   - G32: 核查笔数合计（= COUNT已填写的动态行）
   - H32: 核查金额合计（= SUM动态行的金额列）
2. THE Formula_Engine SHALL 自动计算G45合计（= SUM凭证核对明细的金额列）
3. THE Exception_Summary_Area SHALL 在明细表下方渲染例外汇总区（对应源模板E48-G50公式区），包含：
   - E48/F48/G48: 存在性例外（笔数/金额/占比）
   - E49/F49/G49: 准确性例外（笔数/金额/占比）
   - E50/F50/G50: 记录恰当性例外（笔数/金额/占比）
4. THE Formula_Engine SHALL 自动计算各类例外占比（= 例外金额 / 核查金额合计 × 100%）
5. WHEN 任何例外占比超过可容忍误差率时, THE Exception_Summary_Area SHALL 以红色高亮并显示提示"例外率超标，请考虑扩大样本量"
6. THE Sampling_Vouching_Table SHALL 在例外汇总后渲染"测试结论"区域（el-select: 未发现重大例外/发现例外已获合理解释/发现例外需扩大测试/发现重大错报）

### Requirement 13: 应收票据检查表D1-13 — 审计说明与结论

**User Story:** As a 审计助理, I want to 在检查表底部记录审计说明和结论, so that 我能文档化凭证核对测试的整体结果。

#### Acceptance Criteria

1. THE Sampling_Vouching_Table SHALL 在测试结论后显示"审计说明"区域（textarea + 🤖AI生成按钮 + 💬复核对话入口）
2. THE Sampling_Vouching_Table SHALL 在审计说明后显示"审计结论"区域（textarea + 🤖AI生成按钮 + 💬复核对话入口）
3. THE Sampling_Vouching_Table SHALL 在审计结论后显示"编制提示"折叠区（`<details>` 蓝色左边线+浅蓝背景，默认收起），内容包含：
   - CAS 1314审计抽样准则关于实质性细节测试的要求
   - 抽样方法选择说明（随机/系统/货币单位抽样）
   - 例外项追查和评价程序
   - 样本结果推断总体的方法
4. WHEN 用户点击🤖AI按钮时, THE Sampling_Vouching_Table SHALL 基于例外汇总数据和测试结论生成审计说明/结论
5. THE Sampling_Vouching_Table SHALL 通过 inject openReviewDialog 在审计说明和结论区域各放置💬固定复核对话入口按钮

### Requirement 14: 双模式切换（四表通用）

**User Story:** As a 审计助理, I want to 在HTML精美组件和OnlyOffice编辑模式之间切换, so that 我能根据需要选择最适合的编辑方式。

#### Acceptance Criteria

1. THE Dual_Mode SHALL 在每个sheet的Tab页头部显示 el-segmented 切换控件（"结构化视图" | "在线编辑"）
2. WHEN 用户切换到OnlyOffice模式时, THE Dual_Mode SHALL 打开完整xlsx文件并通过OnlyOffice API隐藏非当前sheet（SetVisible(false)），只显示当前Tab对应的sheet
3. WHEN 用户从OnlyOffice模式切回HTML模式时, THE Dual_Mode SHALL 重新加载 checklist_responses 数据以反映在OO中的编辑
4. WHILE OnlyOffice服务不可用时, THE Dual_Mode SHALL 禁用"在线编辑"选项并显示 tooltip"OnlyOffice服务不可用"
5. THE Dual_Mode SHALL 保留跨sheet公式完整性（不拆分文件）

### Requirement 15: 持久化与数据存储（四表通用）

**User Story:** As a 审计助理, I want to 所有编辑内容自动保存, so that 我不会因为意外关闭页面而丢失数据。

#### Acceptance Criteria

1. THE Inventory_Count_Table SHALL 使用 checklist_responses 表存储数据，item_id 前缀为"D1-inventory-"（监盘明细行JSON: "D1-inventory-rows"，核对区: "D1-inventory-recon-*"）
2. THE Related_Party_Check_Table SHALL 使用 checklist_responses 表存储数据，item_id 前缀为"D1-rp-"（关联方行JSON: "D1-rp-rows"）
3. THE Pledge_Check_Table SHALL 使用 checklist_responses 表存储数据，item_id 前缀为"D1-pledge-"（质押行JSON: "D1-pledge-rows"）
4. THE Sampling_Vouching_Table SHALL 使用 checklist_responses 表存储数据，item_id 前缀为"D1-sampling-"（抽样定义: "D1-sampling-population-*"，核查行JSON: "D1-sampling-vouching-rows"，例外汇总: "D1-sampling-exception-*"）
5. WHEN 用户编辑任意金额/文本/日期字段后2秒无操作时, THE Formula_Engine SHALL 触发 debounce 自动保存
6. WHEN 用户切换下拉选择类字段时, THE Formula_Engine SHALL 立即保存该字段
7. THE Inventory_Count_Table SHALL 将15列监盘动态行以JSON数组格式存储于 remark 字段（item_id="D1-inventory-rows"）
8. THE Related_Party_Check_Table SHALL 将13列关联方动态行以JSON数组格式存储于 remark 字段（item_id="D1-rp-rows"）
9. THE Pledge_Check_Table SHALL 将16列质押动态行以JSON数组格式存储于 remark 字段（item_id="D1-pledge-rows"）
10. THE Sampling_Vouching_Table SHALL 将核查明细动态行以JSON数组格式存储于 remark 字段（item_id="D1-sampling-vouching-rows"）

### Requirement 16: 导入导出三级（四表通用）

**User Story:** As a 审计助理, I want to 支持从Excel导入数据和导出模板, so that 我能利用已有的离线填写的数据批量录入宽表。

#### Acceptance Criteria

1. WHEN 用户点击"导出模板"按钮时, THE Import_Export SHALL 生成当前sheet对应的空白xlsx模板（含表头+格式，无数据行）
2. WHEN 用户点击"导出数据"按钮时, THE Import_Export SHALL 生成包含当前数据的xlsx文件
3. WHEN 用户上传已填写的xlsx文件时, THE Import_Export SHALL 解析文件内容并将数据回写到 checklist_responses
4. IF 导入的xlsx格式不符合模板结构, THEN THE Import_Export SHALL 显示错误提示并列出不匹配的列名
5. WHEN 导入D1-10（15列监盘表）或D1-12（16列质押表）xlsx且行数超过当前行数时, THE Import_Export SHALL 自动扩展动态行以容纳全部数据
6. THE Import_Export SHALL 在导入完成后显示摘要（"成功导入N行数据，M个字段已更新"）
7. THE Import_Export SHALL 对D1-13（抽样表）的导入仅解析凭证核对明细区域行，跳过抽样定义和例外汇总区（这些由公式自动计算）

### Requirement 17: 组件拆分与代码架构

**User Story:** As a 开发者, I want to 将监盘核查组逻辑拆分为独立子组件和子composable, so that 代码可维护性好、每个文件控制在200-400行。

#### Acceptance Criteria

1. THE Inventory_Count_Table SHALL 拆分为独立Vue子组件 D1TabInventoryCount.vue（~400行），15列宽表+核对区+审计说明
2. THE Related_Party_Check_Table SHALL 拆分为独立Vue子组件 D1TabRelatedPartyCheck.vue（~350行），13列表+合计+核对区
3. THE Pledge_Check_Table SHALL 拆分为独立Vue子组件 D1TabPledgeCheck.vue（~350行），16列宽表+合计+质押比例
4. THE Sampling_Vouching_Table SHALL 拆分为独立Vue子组件 D1TabSamplingVouching.vue（~400行），抽样定义+核查明细+例外汇总
5. THE Inventory_Count_Table SHALL 有独立composable useD1InventoryCount.ts（~300行），包含15列CRUD+核对区公式+跨Spec取数
6. THE Related_Party_Check_Table SHALL 有独立composable useD1RelatedPartyCheck.ts（~250行），包含13列CRUD+期末余额(C+D-E)/账面价值(F-G)公式+合计行SUM+跨Spec取数
7. THE Pledge_Check_Table SHALL 有独立composable useD1PledgeCheck.ts（~250行），包含16列CRUD+H18/J18合计+质押比例计算+预警逻辑
8. THE Sampling_Vouching_Table SHALL 有独立composable useD1SamplingVouching.ts（~350行），包含抽样定义+核查明细CRUD+例外统计公式引擎+结论判定

### Requirement 18: 金额格式化与UI美化（四表通用）

**User Story:** As a 审计助理, I want to 所有金额数据以标准格式显示且宽表可读性好, so that 我能快速准确地阅读和核对数据。

#### Acceptance Criteria

1. THE Formula_Engine SHALL 对所有金额单元格应用 displayPrefs.fmtAmount 格式化（千分位分隔、保留2位小数）
2. WHEN 金额为负数时, THE Formula_Engine SHALL 以红色字体和括号格式显示（如 (1,234.56)）
3. WHEN 金额为零时, THE Formula_Engine SHALL 显示"-"而非"0.00"
4. THE Formula_Engine SHALL 对质押比例和例外占比应用百分比格式（保留2位小数）
5. THE Pledge_Check_Table SHALL 对金额列（票据金额/质押金额）右对齐，文本列左对齐
6. THE Inventory_Count_Table SHALL 对15列宽表使用紧凑列宽（日期列120px/金额列110px/文本列auto，最小80px）
7. WHILE 数据正在加载时, THE Formula_Engine SHALL 在表格区域显示 el-skeleton 占位动画


### Requirement 19: D1-12从备查簿D1-7自动导入已质押票据（P1联动）

**User Story:** As a 审计助理, I want to 从备查簿D1-7自动筛选已质押票据填入D1-12质押检查表, so that 我不需要手动在两个宽表间逐笔复制16列数据。

#### Acceptance Criteria

1. THE Pledge_Check_Table SHALL 提供"从备查簿导入已质押票据"按钮（在"添加质押票据"按钮旁）
2. WHEN 用户点击该按钮时, THE Cross_Sheet_Ref SHALL 从同一allResponses Map中读取D1-memo-rows JSON数据（来自Spec③ d1-endorsement-discount），筛选"是否质押"字段为"是"的行
3. THE Pledge_Check_Table SHALL 将筛选结果自动映射到D1-12的16列：D1-7的票据类型→A / 票据号→B / 收到日期→C / 前手→D / 出票日→E / 出票人→F / 承兑人→G / 金额→H / 到期日→I（基本信息9列自动填充，质押详情J-P列留空供用户手填）
4. WHEN 导入前已有数据行时, THE Pledge_Check_Table SHALL 弹出确认弹窗"将新增N行质押票据（不会覆盖已有行），是否继续？"
5. IF D1-7备查簿中无"已质押"票据, THEN THE Pledge_Check_Table SHALL 显示ElMessage.info提示"备查簿中未发现已质押票据"
6. THE Pledge_Check_Table SHALL 在导入后允许用户编辑修改所有列（非只读引用）

### Requirement 20: 共享基础设施抽取（P0架构优化）

**User Story:** As a 开发者, I want to 将四个composable中重复的纯函数、导入导出逻辑、双模式切换逻辑抽取为共享模块, so that 减少代码重复并统一行为。

#### Acceptance Criteria

1. THE Shared_Infrastructure SHALL 创建 `composables/d1SharedFormulas.ts`（~80行），导出所有共享纯函数：parseNum/sumColumn/computeClosingBalance/computeBookValue/computePledgeRatio/computeExceptionRate/formatNegativeAmount
2. THE Shared_Infrastructure SHALL 创建 `composables/useD1ImportExport.ts`（~150行），通用导入导出composable：接收(columnDefs/rowsRef/sheetName/wpId)参数，提供exportTemplate/exportData/importData方法
3. THE Shared_Infrastructure SHALL 创建 `composables/useD1DualMode.ts`（~80行），通用双模式切换composable：接收(wpId/sheetName)参数，提供viewMode/isOOMode/ooHealthy/checkOOHealth方法
4. THE Shared_Infrastructure SHALL 创建 `d1/D1AuditNoteSection.vue`（~100行），通用审计说明/结论子组件：props(sectionId/noteText/conclusionText/guidanceHtml/openReviewDialog)，emit(update:note/update:conclusion)
5. THE 四个 composable(useD1InventoryCount/useD1RelatedPartyCheck/useD1PledgeCheck/useD1SamplingVouching) SHALL 引用共享模块而非各自实现重复函数
