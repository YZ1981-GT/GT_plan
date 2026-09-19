# Requirements Document

## Introduction

D1 应收票据底稿的坏账准备专属组件——覆盖"应收票据坏账准备会计政策检查D1-14"和"应收票据坏账准备测算表D1-15"两个sheet。从现有 `useD1NotesReceivable.ts`（1237行）中拆出坏账准备相关逻辑为独立子组件+子composable。2个独立Vue组件 + 2个独立composable（每文件200-400行），全部做HTML精美组件，OnlyOffice仅作降级模式。

核心业务逻辑：D1-14为段落式政策检查表（d-form-paragraph, class_code: D-政策检查），采用左右分栏布局（A-I列为政策描述区 / J-R列为审计师核查意见区），包含审计目标、公司坏账准备会计政策概述、预期信用损失模型描述（组合评估方法/单项评估标准/迁徙率法参数）、会计政策变更说明、审计结论共5个段落section，无动态表格；D1-15为univer类计量测算表（8列, class_code: G-测算），分两个section：Section 1（rows 13-18）为按组合计提（账龄/信用风险组合分类），Section 2（rows 20-24）为按单项计提（单项金额重大+个别认定），每section各有sub-header和SUM合计行。公式模式简单：D=B×C（应计提=余额×损失率），F=E-D（差异=账面余额-应计提）。两表共同完成应收票据坏账准备的审计程序。

## Glossary

- **Policy_Check_Form**: 应收票据坏账准备会计政策检查D1-14（component_type: d-form-paragraph, class_code: D-政策检查），段落式左右分栏布局
- **ECL_Calc_Table**: 应收票据坏账准备测算表D1-15（component_type: univer, class_code: G-测算），8列计算表分2个section
- **Left_Panel**: 政策描述区（A-I列），包含政策正文内容（只读或可编辑textarea），对应D1-14左侧9列
- **Right_Panel**: 审计师核查意见区（J-R列），审计师填写核查意见和评价，对应D1-14右侧9列（J22:R22 / J31:R31合并区域）
- **Section_AuditObjective**: 审计目标段落（D1-14 rows 5-8），只读静态文本描述审计程序目的
- **Section_PolicyOverview**: 公司坏账准备会计政策概述段落（D1-14 rows ~9-22），左侧描述政策内容，右侧审计师核查意见
- **Section_ECLModel**: 预期信用损失模型描述段落（D1-14 rows ~23-35），包含组合评估方法/单项评估标准/迁徙率法参数
- **Section_PolicyChange**: 会计政策变更说明段落（D1-14 rows ~36-39，B38:I38/B39:I39大段文本区）
- **Section_Conclusion**: 审计结论段落（D1-14末尾），审计师对政策合理性的最终评价
- **Portfolio_Section**: 按组合计提区（D1-15 rows 13-18, A12:A13合并sub-header），按账龄/信用风险组合分类的坏账准备测算
- **Individual_Section**: 按单项计提区（D1-15 rows 20-24, A20:A21合并sub-header），单项金额重大+个别认定的坏账准备测算
- **Col_A_Debtor**: 债务人名称列（D1-15 A列），文本输入
- **Col_B_Balance**: 审定应收票据账面余额列（D1-15 B列），金额输入
- **Col_C_LossRate**: 预期信用损失率列（D1-15 C列），百分比输入（用户直接填写，非模板内计算）
- **Col_D_ShouldProvision**: 期末应计提坏账准备列（D1-15 D列），公式自动计算 D=B×C
- **Col_E_ActualProvision**: 期末坏账准备账面余额列（D1-15 E列），金额输入
- **Col_F_Difference**: 差异列（D1-15 F列），公式自动计算 F=E-D
- **Col_G_Basis**: 坏账准备计提依据及文件列（D1-15 G列），文本输入
- **Col_H_IndexRef**: 索引号列（D1-15 H列），GtIndexChip跳转
- **SUM_Row_Portfolio**: 组合计提合计行（D1-15 row 18），B18/D18/E18/F18为SUM公式
- **SUM_Row_Individual**: 单项计提合计行（D1-15 row ~24），类似SUM公式
- **Cross_Sheet_Ref**: 跨sheet引用，从allResponses Map读取其他spec的数据（纯computed响应式）
- **Formula_Engine**: 前端公式引擎composable，实现D=B×C / F=E-D / SUM合计
- **Dual_Mode**: 双模式切换，HTML精美组件 ↔ OnlyOffice在线编辑
- **GtIndexChip**: 跨底稿索引跳转芯片，点击可跳转到关联底稿对应位置

## Requirements

### Requirement 1: 坏账准备会计政策检查D1-14 — 审计目标段落

**User Story:** As a 审计助理, I want to 查看坏账准备政策检查的审计目标, so that 我能明确本底稿的程序目的和工作范围。

#### Acceptance Criteria

1. THE Policy_Check_Form SHALL 在顶部渲染审计目标段落区域（只读静态文本，对应源模板rows 5-8的固定文本内容）
2. THE Section_AuditObjective SHALL 使用全宽卡片布局（不分左右栏），文本以el-alert info样式展示
3. THE Policy_Check_Form SHALL 在审计目标上方渲染底稿抬头信息（致同会计师事务所 / 应收票据坏账准备会计政策检查 / entity_name / period_end / index_no / page_no），对应源模板rows 1-4的fixed_cells

### Requirement 2: 坏账准备会计政策检查D1-14 — 左右分栏政策概述

**User Story:** As a 审计助理, I want to 在左侧查看公司坏账准备会计政策内容并在右侧填写核查意见, so that 我能对照政策逐项评价其合理性。

#### Acceptance Criteria

1. THE Section_PolicyOverview SHALL 使用左右分栏布局（左侧A-I列占60%宽度 / 右侧J-R列占40%宽度），对应源模板J22:R22合并区域
2. THE Left_Panel SHALL 渲染公司坏账准备会计政策描述文本区域（多个段落，包含：ECL方法概述 / 组合评估范围 / 账龄划分标准 / 损失率确定依据），每段为独立textarea可编辑
3. THE Right_Panel SHALL 渲染审计师核查意见textarea（对应J22:R22合并区域），供审计师填写对左侧政策内容的评价意见
4. THE Policy_Check_Form SHALL 对Left_Panel各段落文本使用浅灰底色（区分于右侧可编辑区），审计师已填写的段落显示蓝色左边线
5. WHEN 审计师在Right_Panel填写核查意见后, THE Policy_Check_Form SHALL 以debounce 2s自动保存到checklist_responses

### Requirement 3: 坏账准备会计政策检查D1-14 — 预期信用损失模型描述

**User Story:** As a 审计助理, I want to 记录公司ECL模型的具体方法参数（组合评估/单项评估/迁徙率法）, so that 我能评价公司ECL模型的适当性和一致性。

#### Acceptance Criteria

1. THE Section_ECLModel SHALL 使用左右分栏布局（左侧政策内容 / 右侧审计师核查意见，对应J31:R31合并区域）
2. THE Left_Panel SHALL 渲染ECL模型描述，分3个子区域：
   - 组合评估方法（textarea：描述按账龄/信用风险特征分组的方法和分组标准）
   - 单项评估标准（textarea：描述何时对单项应收款进行个别减值评估的条件）
   - 迁徙率法参数（textarea：描述迁徙率计算的历史期间选择、数据来源、调整因素）
3. THE Right_Panel SHALL 渲染审计师对ECL模型的核查意见textarea（对应J31:R31合并区域）
4. THE Policy_Check_Form SHALL 对每个子区域设置独立的item_id前缀（D1-policy-ecl-portfolio / D1-policy-ecl-individual / D1-policy-ecl-migration）
5. WHEN 审计师在Right_Panel填写核查意见后, THE Policy_Check_Form SHALL 以debounce 2s自动保存

### Requirement 4: 坏账准备会计政策检查D1-14 — 会计政策变更说明

**User Story:** As a 审计助理, I want to 记录本期坏账准备会计政策是否发生变更及变更内容, so that 我能评估政策变更的合理性和披露充分性。

#### Acceptance Criteria

1. THE Section_PolicyChange SHALL 渲染会计政策变更段落区域（对应源模板rows 36-39，A36:I36 / B38:I38 / B39:I39合并区域）
2. THE Section_PolicyChange SHALL 包含以下可编辑字段：
   - 是否发生政策变更（el-radio-group: 是 / 否）
   - 变更内容描述（textarea，对应B38:I38大段文本区，仅当"是"时可编辑）
   - 变更原因及合理性说明（textarea，对应B39:I39大段文本区，仅当"是"时可编辑）
3. WHEN 用户选择"否"时, THE Section_PolicyChange SHALL 折叠变更内容和原因textarea（灰色文字显示"本期无政策变更"）
4. WHEN 用户选择"是"时, THE Section_PolicyChange SHALL 展开并聚焦变更内容textarea
5. THE Policy_Check_Form SHALL 将政策变更数据持久化（item_id: D1-policy-change-flag / D1-policy-change-content / D1-policy-change-reason）

### Requirement 5: 坏账准备会计政策检查D1-14 — 审计结论

**User Story:** As a 审计助理, I want to 在政策检查底部记录审计结论, so that 我能归纳对公司坏账准备会计政策合理性的最终判断。

#### Acceptance Criteria

1. THE Section_Conclusion SHALL 渲染审计结论区域，包含：
   - 政策合理性评价（el-radio-group: 合理 / 基本合理但需关注 / 不合理）
   - 审计结论文本（textarea + 🤖AI生成按钮 + 💬复核对话入口）
2. WHEN 用户切换合理性评价时, THE Policy_Check_Form SHALL 立即保存该字段到 item_id="D1-policy-conclusion"（conclusion字段）
3. WHEN 用户点击🤖AI按钮时, THE Policy_Check_Form SHALL 基于各section已填写的政策描述和核查意见生成审计结论文本
4. THE Policy_Check_Form SHALL 通过 inject openReviewDialog 在审计结论区域放置💬固定复核对话入口按钮
5. THE Policy_Check_Form SHALL 在审计结论后显示"编制提示"折叠区（`<details>` 蓝色左边线+浅蓝背景，默认收起），内容包含：
   - CAS 22 金融工具确认与计量中ECL三阶段模型说明
   - 组合评估vs单项评估的选择标准
   - 政策变更需关注的会计估计变更披露要求（CAS 28）
   - 预期信用损失率合理性判断标准（同行业比较、历史趋势）

### Requirement 6: 坏账准备测算表D1-15 — 按组合计提Section

**User Story:** As a 审计助理, I want to 填写按组合计提（账龄/信用风险组合）的坏账准备测算数据, so that 我能验证组合评估部分的坏账准备计提金额是否正确。

#### Acceptance Criteria

1. THE Portfolio_Section SHALL 渲染"按组合计提"sub-header区域（对应源模板A12:A13合并区域），以el-divider或加粗标题显示section名称
2. THE Portfolio_Section SHALL 渲染8列el-table，列对应源模板header_row 12：
   - A: 债务人名称（el-input文本）
   - B: 审定应收票据账面余额（数字输入 + displayPrefs.fmtAmount）
   - C: 预期信用损失率（百分比输入，保留2位小数，范围0-100%）
   - D: 期末应计提坏账准备（公式只读: D=B×C，灰色背景）
   - E: 期末坏账准备账面余额（数字输入 + fmtAmount）
   - F: 差异（公式只读: F=E-D，灰色背景）
   - G: 坏账准备计提依据及文件（el-input textarea模式）
   - H: 索引号（GtIndexChip）
3. THE Portfolio_Section SHALL 支持动态行增删（预设5行对应rows 13-17，点击"添加组合"在合计行上方新增空行）
4. THE Formula_Engine SHALL 自动计算每行D列: shouldProvision = balance × lossRate（D=B×C）
5. THE Formula_Engine SHALL 自动计算每行F列: difference = actualProvision - shouldProvision（F=E-D）
6. THE Formula_Engine SHALL 自动计算Row 18合计行: B18=SUM(B13:B17) / D18=SUM(D13:D17) / E18=SUM(E13:E17) / F18=SUM(F13:F17)
7. WHEN 某行F列差异≠0时, THE ECL_Calc_Table SHALL 以红色字体显示该行差异值

### Requirement 7: 坏账准备测算表D1-15 — 按单项计提Section

**User Story:** As a 审计助理, I want to 填写按单项计提（金额重大+个别认定）的坏账准备测算数据, so that 我能验证单项评估部分的坏账准备计提金额是否正确。

#### Acceptance Criteria

1. THE Individual_Section SHALL 渲染"按单项计提"sub-header区域（对应源模板A20:A21合并区域），以el-divider或加粗标题显示section名称
2. THE Individual_Section SHALL 渲染与Portfolio_Section相同的8列el-table结构（A-H列定义完全一致）
3. THE Individual_Section SHALL 支持动态行增删（预设3行对应rows 22-24，点击"添加单项"在合计行上方新增空行）
4. THE Formula_Engine SHALL 自动计算每行D列和F列（公式与组合section一致: D=B×C, F=E-D）
5. THE Formula_Engine SHALL 自动计算单项合计行: SUM各动态行的B/D/E/F列
6. WHEN 某行F列差异≠0时, THE ECL_Calc_Table SHALL 以红色字体显示该行差异值
7. THE Individual_Section SHALL 在单项合计行下方显示分隔区，渲染组合+单项总合计行（= 组合合计 + 单项合计的B/D/E/F列之和）

### Requirement 8: 坏账准备测算表D1-15 — 差异分析与重要性判断

**User Story:** As a 审计助理, I want to 将坏账准备差异总额与重要性水平比较, so that 我能判断差异是否需要建议调整。

#### Acceptance Criteria

1. THE ECL_Calc_Table SHALL 在总合计行下方渲染"差异分析"卡片，包含：组合差异合计 | 单项差异合计 | 差异总额 | 重要性水平 | 是否超重要性
2. THE Formula_Engine SHALL 从同一 allResponses Map 中读取B15重要性水平数据（item_id含materiality前缀，纯computed响应式跨Spec取数）
3. THE Formula_Engine SHALL 自动判断: exceedsMateriality = |差异总额(组合F合计+单项F合计)| > materialityThreshold AND materialityThreshold > 0
4. WHEN 差异超重要性时, THE ECL_Calc_Table SHALL 以红色背景+⚠️图标显示"超重要性水平，建议调整"
5. WHEN 差异未超重要性时, THE ECL_Calc_Table SHALL 以绿色背景+✓图标显示"未超重要性水平"
6. IF B15重要性数据未加载, THEN THE ECL_Calc_Table SHALL 在重要性水平位置显示"-"占位符+黄色三角警告图标

### Requirement 9: 坏账准备测算表D1-15 — 审计说明与结论

**User Story:** As a 审计助理, I want to 在测算表底部记录审计说明和结论, so that 我能文档化坏账准备计量测试的整体结果。

#### Acceptance Criteria

1. THE ECL_Calc_Table SHALL 在差异分析卡片后显示"审计说明"区域（textarea + 🤖AI生成按钮 + 💬复核对话入口）
2. THE ECL_Calc_Table SHALL 在审计说明后显示"审计结论"区域（textarea + 🤖AI生成按钮 + 💬复核对话入口）
3. THE ECL_Calc_Table SHALL 在审计结论后显示"编制提示"折叠区（`<details>` 蓝色左边线+浅蓝背景，默认收起），内容包含：
   - D=B×C公式含义说明（应计提=审定余额×预期信用损失率）
   - F=E-D差异含义（正数=多提/负数=少提，差异追查方向）
   - 组合评估与单项评估不得重复覆盖同一笔应收款
   - 超重要性差异建议AJE/RJE或告知管理层调整
4. WHEN 用户点击🤖AI按钮时, THE ECL_Calc_Table SHALL 基于差异汇总和重要性判断结果生成审计说明/结论文本
5. THE ECL_Calc_Table SHALL 通过 inject openReviewDialog 在审计说明和结论区域各放置💬固定复核对话入口按钮

### Requirement 10: 跨Spec数据读写契约

**User Story:** As a 开发者, I want to 明确ECL组件与其他Spec的数据契约, so that 跨组件数据流清晰且不会因重构而断裂。

#### Acceptance Criteria

1. THE ECL_Calc_Table SHALL 从同一 allResponses Map 中读取 Spec1(d1-adjudication-table) 的审定表数据（item_id前缀"D1-adj-*"，纯computed响应式跨Spec取数），用于核对坏账准备期末余额
2. THE ECL_Calc_Table SHALL 将坏账准备测算汇总结果写入 item_id="D1-ecl-total-should-provision"（应计提合计）和"D1-ecl-total-actual-provision"（账面余额合计）和"D1-ecl-total-difference"（差异合计），供Spec1审定表和附注模块引用
3. THE Policy_Check_Form SHALL 将D1-14的政策合理性评价结论写入 item_id="D1-policy-conclusion"，供审计报告引用
4. WHEN ECL测算结果变更时, THE Formula_Engine SHALL 通过 debounce 自动更新汇总item_id的值（不使用EventBus，纯save回调）
5. THE Formula_Engine SHALL 从 allResponses 读取重要性水平（跨Spec从B15取数，item_id含materiality前缀）

### Requirement 11: 双模式切换（两表通用）

**User Story:** As a 审计助理, I want to 在HTML精美组件和OnlyOffice编辑模式之间切换, so that 我能根据需要选择最适合的编辑方式。

#### Acceptance Criteria

1. THE Dual_Mode SHALL 在每个sheet的Tab页头部显示 el-segmented 切换控件（"结构化视图" | "在线编辑"）
2. WHEN 用户切换到OnlyOffice模式时, THE Dual_Mode SHALL 打开完整xlsx文件并通过OnlyOffice API隐藏非当前sheet（SetVisible(false)），只显示D1-14/D1-15对应的sheet
3. WHEN 用户从OnlyOffice模式切回HTML模式时, THE Dual_Mode SHALL 重新加载 checklist_responses 数据以反映在OO中的编辑
4. WHILE OnlyOffice服务不可用时, THE Dual_Mode SHALL 禁用"在线编辑"选项并显示 tooltip"OnlyOffice服务不可用"
5. THE Dual_Mode SHALL 保留跨sheet公式完整性（不拆分文件）

### Requirement 12: 持久化与数据存储（两表通用）

**User Story:** As a 审计助理, I want to 所有编辑内容自动保存, so that 我不会因为意外关闭页面而丢失数据。

#### Acceptance Criteria

1. THE Policy_Check_Form SHALL 使用 checklist_responses 表存储数据，item_id 前缀为"D1-policy-"（政策概述各段: D1-policy-overview-* / ECL模型描述: D1-policy-ecl-* / 变更说明: D1-policy-change-* / 审计师核查意见: D1-policy-auditor-* / 结论: D1-policy-conclusion）
2. THE ECL_Calc_Table SHALL 使用 checklist_responses 表存储数据，item_id 前缀为"D1-ecl-"（组合行JSON: D1-ecl-portfolio-rows / 单项行JSON: D1-ecl-individual-rows / 审计说明: D1-ecl-audit-note / 审计结论: D1-ecl-audit-conclusion / 汇总: D1-ecl-total-*）
3. WHEN 用户编辑任意金额/百分比/文本字段后2秒无操作时, THE Formula_Engine SHALL 触发 debounce 自动保存
4. WHEN 用户切换radio/select类字段时, THE Formula_Engine SHALL 立即保存该字段
5. THE ECL_Calc_Table SHALL 将组合计提动态行以JSON数组格式存储于 remark 字段（item_id="D1-ecl-portfolio-rows"，每行含8列对应字段）
6. THE ECL_Calc_Table SHALL 将单项计提动态行以JSON数组格式存储于 remark 字段（item_id="D1-ecl-individual-rows"，每行含8列对应字段）

### Requirement 13: 导入导出三级（两表通用）

**User Story:** As a 审计助理, I want to 支持从Excel导入数据和导出模板, so that 我能利用已有的离线填写的数据批量录入。

#### Acceptance Criteria

1. WHEN 用户点击"导出模板"按钮时, THE Import_Export SHALL 生成D1-15对应的空白xlsx模板（含8列表头+组合/单项两section+格式，无数据行）
2. WHEN 用户点击"导出数据"按钮时, THE Import_Export SHALL 生成包含当前组合+单项两section数据的xlsx文件
3. WHEN 用户上传已填写的xlsx文件时, THE Import_Export SHALL 解析文件内容并按section分隔符识别组合行与单项行，回写到 checklist_responses
4. IF 导入的xlsx格式不符合模板结构（列数≠8或缺少section header）, THEN THE Import_Export SHALL 显示错误提示并列出不匹配的列名
5. WHEN 导入xlsx行数超过当前行数时, THE Import_Export SHALL 自动扩展动态行以容纳全部数据
6. THE Import_Export SHALL 在导入完成后显示摘要（"成功导入N行数据，M个字段已更新"）
7. THE Import_Export SHALL 对D1-14（段落式政策检查）不提供导入导出功能（纯文本段落无批量导入场景）

### Requirement 14: 组件拆分与代码架构

**User Story:** As a 开发者, I want to 将坏账准备逻辑拆分为独立子组件和子composable, so that 代码可维护性好、每个文件控制在200-400行。

#### Acceptance Criteria

1. THE Policy_Check_Form SHALL 拆分为独立Vue子组件 D1TabPolicyCheck.vue（~350行），左右分栏段落式布局 + 5个section + 审计结论
2. THE ECL_Calc_Table SHALL 拆分为独立Vue子组件 D1TabEclCalc.vue（~300行），8列表×2 section + 差异分析 + 审计说明/结论
3. THE Policy_Check_Form SHALL 有独立composable useD1PolicyCheck.ts（~200行），包含各section文本段落CRUD + 政策变更条件展开逻辑 + 合理性评价 + 持久化
4. THE ECL_Calc_Table SHALL 有独立composable useD1EclCalc.ts（~300行），包含组合/单项两section的动态行CRUD + D=B×C / F=E-D公式引擎 + SUM合计 + 重要性判断 + 跨Spec取数 + 汇总写出
5. THE useD1EclCalc SHALL 接收 allResponses Map 和 save 回调作为参数（与现有composable模式一致）
6. THE useD1EclCalc SHALL 导出以下接口：portfolioRows / individualRows / addPortfolioRow / removePortfolioRow / addIndividualRow / removeIndividualRow / portfolioSumRow / individualSumRow / grandTotalRow / exceedsMateriality / materialityThreshold

### Requirement 15: 金额格式化与UI美化（两表通用）

**User Story:** As a 审计助理, I want to 所有金额和百分比数据以标准格式显示, so that 我能快速准确地阅读和核对数据。

#### Acceptance Criteria

1. THE Formula_Engine SHALL 对所有金额单元格（B/D/E/F列）应用 displayPrefs.fmtAmount 格式化（千分位分隔、保留2位小数）
2. WHEN 金额为负数时, THE Formula_Engine SHALL 以红色字体和括号格式显示（如 (1,234.56)）
3. WHEN 金额为零时, THE Formula_Engine SHALL 显示"-"而非"0.00"
4. THE Formula_Engine SHALL 对预期信用损失率C列应用百分比格式（保留2位小数，如 12.34%）
5. THE ECL_Calc_Table SHALL 对金额列（B/D/E/F）右对齐，文本列（A/G）左对齐，百分比列（C）居中
6. THE Policy_Check_Form SHALL 对左右分栏使用el-row/el-col响应式布局（lg: 14/10, md: 12/12），窄屏时右侧Panel堆叠到下方
7. WHILE 数据正在加载时, THE Formula_Engine SHALL 在表格区域显示 el-skeleton 占位动画

### Requirement 16: 损失率输入校验

**User Story:** As a 审计助理, I want to 系统自动校验输入的损失率在合理范围内, so that 我能避免录入错误导致计算结果偏差。

#### Acceptance Criteria

1. THE Formula_Engine SHALL 对C列（预期信用损失率）输入值强制约束在 [0, 100] 区间（百分比显示，内部存储为小数0-1）
2. WHEN 用户输入超出范围的值时, THE Formula_Engine SHALL 自动截断至边界值（<0截为0，>100截为100）并显示黄色边框1.5s提示
3. THE Formula_Engine SHALL 对D列计算结果验证为非负数（shouldProvision = balance × rate ≥ 0，当balance为负时显示警告tooltip"余额为负，请核实"）
4. WHEN B列（余额）输入非数字字符时, THE Formula_Engine SHALL 忽略非数字输入并保留原值


### Requirement 17: D1-15 E列从D1-4坏账明细自动取数（P1联动）

**User Story:** As a 审计助理, I want to D1-15的"期末坏账准备账面余额"列自动从D1-4坏账准备明细表取数, so that 我不需要手动查看D1-4再逐行抄录到D1-15。

#### Acceptance Criteria

1. THE ECL_Calc_Table SHALL 对E列（期末坏账准备账面余额）提供"从D1-4取数"按钮（在表格工具栏）
2. WHEN 用户点击该按钮时, THE Cross_Sheet_Ref SHALL 从同一allResponses Map中读取D1-adj-bad-debt-*前缀数据（D1-4坏账准备各行的期末审定数）
3. THE ECL_Calc_Table SHALL 按债务人名称/类别匹配将D1-4数据填入D1-15对应行的E列（组合section：按账龄段匹配；单项section：按债务人名称匹配）
4. WHEN E列已有用户手填值时, THE ECL_Calc_Table SHALL 以浅蓝背景标记自动取数单元格 + tooltip"取自D1-4坏账准备明细表，可手动覆盖"
5. THE ECL_Calc_Table SHALL 保留用户手动覆盖能力（auto_pull填充后用户可直接编辑修改，修改后移除浅蓝背景标记）
6. IF D1-4数据未填写, THEN THE ECL_Calc_Table SHALL 在按钮旁显示黄色提示"D1-4坏账准备明细表尚未填写"

### Requirement 18: AI辅助生成审计说明/结论（P1启用）

**User Story:** As a 审计助理, I want to 🤖AI按钮能根据当前表格数据自动生成审计说明和结论文本, so that 我能快速获得标准化的审计结论草稿。

#### Acceptance Criteria

1. WHEN 用户点击D1-14审计结论区的🤖AI按钮时, THE Policy_Check_Form SHALL 将以下context传给AI端点：各section已填写的政策描述 + 核查意见 + 政策变更flag + 合理性评价radio值
2. WHEN 用户点击D1-15审计说明区的🤖AI按钮时, THE ECL_Calc_Table SHALL 将以下context传给AI端点：组合差异合计/单项差异合计/差异总额/重要性水平/exceedsMateriality/各行最大差异债务人
3. THE AI端点 SHALL 复用已有的 `/api/workpapers/{wp_id}/a171/ai-generate` 模式：加载CPA专属system prompt + 编制提示注入 + context数据作为user消息
4. THE AI生成结果 SHALL 填入对应textarea（不覆盖已有内容，追加或替换由用户在弹窗中确认）
5. WHILE AI服务不可用时(vLLM offline), THE AI按钮 SHALL 显示disabled状态 + tooltip"AI服务暂不可用"
