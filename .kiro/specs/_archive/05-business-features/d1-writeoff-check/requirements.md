# Requirements Document

## Introduction

D1 应收票据底稿的坏账准备转回/核销检查表专属组件——覆盖"坏账准备转回、核销检查表D1-16"单个sheet。从现有 `useD1NotesReceivable.ts`（1237行）中拆出转回/核销检查相关逻辑为独立子组件+子composable。1个Vue组件（含4个区域：Section 1转回检查8列 + Section 2核销检查5列 + Section 3审计说明 + Section 4审计结论）+ 1个独立composable（~200行），全部做HTML精美组件（el-table + 金额格式化 + 动态行 + SUM公式），OnlyOffice仅作降级模式。

核心业务逻辑：D1-16是一张双段表格的检查表。Section 1"本期重要的坏账准备转回检查"（8列：单位名称/转回原因/收回方式/原确定坏账准备的依据/收回或转回金额/收回或转回前累计已计提坏账准备金额/合理性分析/索引号），逐笔审核本期转回的坏账准备是否合理。Section 2"本期重要的核销应收票据检查"（5列：单位名称/应收票据的性质/核销金额/核销原因/履行的核销程序），逐笔审核本期核销的应收票据是否合规。两段表各自有SUM合计行。Section 3/4为审计说明和审计结论文本区。转回/核销金额应与D1-4坏账准备明细表变动列一致（跨Spec数据验证）。

## Glossary

- **Writeoff_Check_Table**: 坏账准备转回、核销检查表D1-16（component_type: d-form-table, class_code: D-检查表），双段检查表
- **Reversal_Section**: Section 1"本期重要的坏账准备转回检查"（rows 10-15），8列宽表，检查转回合理性
- **Writeoff_Section**: Section 2"本期重要的核销应收票据检查"（rows 16-21），5列表，检查核销合规性
- **Reversal_Amount**: 收回或转回金额（Section 1 E列），逐笔记录本期转回的坏账准备金额
- **Prior_Provision_Amount**: 收回或转回前累计已计提坏账准备金额（Section 1 F列），转回前已计提的坏账准备余额
- **Writeoff_Amount**: 核销金额（Section 2 C列），逐笔记录本期核销的应收票据金额
- **Reversal_Sum_Row**: 转回合计行（Row 15），E15=SUM(E12:E14)、F15=SUM(F12:F14)
- **Writeoff_Sum_Row**: 核销合计行（Row 21），C21=SUM(C18:C20)
- **Audit_Note_Section**: Section 3"审计说明"（Row 22起），textarea记录审计发现
- **Audit_Conclusion_Section**: Section 4"审计结论"（Row 26起），textarea记录审计结论
- **Cross_Sheet_Ref**: 跨sheet引用，从allResponses Map读取D1-4坏账准备明细表的转回/核销变动数据（纯computed响应式）
- **Formula_Engine**: 前端公式引擎composable，实现SUM合计+跨Spec差异校验
- **Dual_Mode**: 双模式切换，HTML精美组件 ↔ OnlyOffice在线编辑
- **GtIndexChip**: 跨底稿索引跳转芯片，点击可跳转到关联底稿对应位置
- **Dynamic_Row**: 动态行，用户可新增/删除的数据行
- **Summary_Row**: 合计行，自动SUM对应明细行（不可编辑）

## Requirements

### Requirement 1: Section 1 坏账准备转回检查 — 8列明细表

**User Story:** As a 审计助理, I want to 逐笔登记本期重要的坏账准备转回项目并记录转回原因和合理性分析, so that 我能完整文档化转回检查过程并评估转回的合理性。

#### Acceptance Criteria

1. THE Reversal_Section SHALL 在顶部显示区段标题"(一)本期重要的坏账准备转回检查"（只读静态文本，对应源模板Row 10）
2. THE Reversal_Section SHALL 渲染8列el-table（对应源模板header_row 11列A-H）：
   - A: 单位名称（el-input）
   - B: 转回原因（el-input textarea模式）
   - C: 收回方式（el-select: 现金收回/银行转账/票据兑现/以物抵债/债务重组/其他）
   - D: 原确定坏账准备的依据（el-input textarea模式）
   - E: 收回或转回金额（数字输入 + displayPrefs.fmtAmount）
   - F: 收回或转回前累计已计提坏账准备金额（数字输入 + displayPrefs.fmtAmount）
   - G: 合理性分析（el-input textarea模式）
   - H: 索引号（GtIndexChip，支持跳转到关联底稿）
3. THE Reversal_Section SHALL 支持动态行增删（点击"添加转回项"在合计行上方新增空行）
4. THE Reversal_Section SHALL 对金额列（E/F）右对齐，文本列左对齐
5. THE Reversal_Section SHALL 对"转回原因"和"合理性分析"列使用textarea模式并设置最小行高（min-height: 60px）以容纳多行文本

### Requirement 2: Section 1 坏账准备转回检查 — 合计行与跨Spec校验

**User Story:** As a 审计助理, I want to 自动计算转回金额合计并与D1-4坏账准备明细表的转回变动列核对, so that 我能验证检查表登记的转回金额与明细表一致。

#### Acceptance Criteria

1. THE Formula_Engine SHALL 自动计算 Reversal_Sum_Row：E15=SUM(所有动态行的E列)，F15=SUM(所有动态行的F列)
2. THE Reversal_Sum_Row SHALL 以灰色背景显示且不可编辑（自动计算行）
3. THE Cross_Sheet_Ref SHALL 从同一allResponses Map中读取D1-adj-bad-debt-*前缀数据（D1-4坏账准备明细表的转回变动列，纯computed响应式跨Spec取数）
4. THE Reversal_Section SHALL 在合计行下方渲染核对区：本表转回合计(E15) vs D1-4转回变动合计 → 差异
5. WHEN 差异≠0时, THE Reversal_Section SHALL 以红色高亮显示差异金额并提示"转回金额与D1-4坏账准备明细表不一致"
6. IF D1-4数据未加载, THEN THE Cross_Sheet_Ref SHALL 在核对区D1-4列显示"-"占位符+黄色三角警告图标

### Requirement 3: Section 1 坏账准备转回检查 — 转回合理性预警

**User Story:** As a 审计助理, I want to 系统自动标记可能不合理的转回项目, so that 我能重点关注高风险的转回事项。

#### Acceptance Criteria

1. WHEN 某行的"收回或转回金额"(E列) 大于 "收回或转回前累计已计提坏账准备金额"(F列)时, THE Reversal_Section SHALL 在该行E列以橙色边框高亮并显示tooltip"转回金额超过原计提金额，请核实"
2. WHEN 某行的"转回原因"(B列)为空且"收回或转回金额"(E列)>0时, THE Reversal_Section SHALL 在B列显示红色星号必填提示
3. WHEN 某行的"合理性分析"(G列)为空且"收回或转回金额"(E列)>0时, THE Reversal_Section SHALL 在G列显示红色星号必填提示
4. THE Reversal_Section SHALL 在表格上方显示转回项计数标签（"共N笔转回，合计金额XXX元"）

### Requirement 4: Section 2 核销应收票据检查 — 5列明细表

**User Story:** As a 审计助理, I want to 逐笔登记本期重要的核销应收票据项目并记录核销原因和程序, so that 我能完整文档化核销检查过程并评估核销的合规性。

#### Acceptance Criteria

1. THE Writeoff_Section SHALL 在Section 1下方显示区段标题"(二)本期重要的核销应收票据检查"（只读静态文本，对应源模板Row 16）
2. THE Writeoff_Section SHALL 渲染5列el-table（对应源模板header_row 17）：
   - A: 单位名称（el-input）
   - B: 应收票据的性质（el-select: 银行承兑汇票/商业承兑汇票/其他）
   - C: 核销金额（数字输入 + displayPrefs.fmtAmount）
   - D: 核销原因（el-input textarea模式）
   - E: 履行的核销程序（el-input textarea模式）
3. THE Writeoff_Section SHALL 支持动态行增删（点击"添加核销项"在合计行上方新增空行）
4. THE Writeoff_Section SHALL 对金额列（C）右对齐，文本列左对齐
5. THE Writeoff_Section SHALL 对"核销原因"和"履行的核销程序"列使用textarea模式并设置最小行高（min-height: 60px）

### Requirement 5: Section 2 核销应收票据检查 — 合计行与跨Spec校验

**User Story:** As a 审计助理, I want to 自动计算核销金额合计并与D1-4坏账准备明细表的核销变动列核对, so that 我能验证检查表登记的核销金额与明细表一致。

#### Acceptance Criteria

1. THE Formula_Engine SHALL 自动计算 Writeoff_Sum_Row：C21=SUM(所有动态行的C列)
2. THE Writeoff_Sum_Row SHALL 以灰色背景显示且不可编辑（自动计算行）
3. THE Cross_Sheet_Ref SHALL 从同一allResponses Map中读取D1-adj-bad-debt-*前缀数据（D1-4坏账准备明细表的核销变动列，纯computed响应式跨Spec取数）
4. THE Writeoff_Section SHALL 在合计行下方渲染核对区：本表核销合计(C21) vs D1-4核销变动合计 → 差异
5. WHEN 差异≠0时, THE Writeoff_Section SHALL 以红色高亮显示差异金额并提示"核销金额与D1-4坏账准备明细表不一致"
6. IF D1-4数据未加载, THEN THE Cross_Sheet_Ref SHALL 在核对区D1-4列显示"-"占位符+黄色三角警告图标

### Requirement 6: Section 2 核销应收票据检查 — 核销程序完整性检查

**User Story:** As a 审计助理, I want to 系统自动检查核销程序的完整性, so that 我能确认每笔核销都经过了适当的审批程序。

#### Acceptance Criteria

1. WHEN 某行的"核销金额"(C列)>0 且 "履行的核销程序"(E列)为空时, THE Writeoff_Section SHALL 在E列显示红色星号必填提示
2. WHEN 某行的"核销金额"(C列)>0 且 "核销原因"(D列)为空时, THE Writeoff_Section SHALL 在D列显示红色星号必填提示
3. THE Writeoff_Section SHALL 在表格上方显示核销项计数标签（"共N笔核销，合计金额XXX元"）
4. WHEN 核销金额合计超过ECL组件(D1-ecl-*)计算的本期计提总额时, THE Writeoff_Section SHALL 在合计区显示橙色预警标签"⚠️ 核销金额超过本期计提总额，请关注坏账准备充足性"

### Requirement 7: Section 3 审计说明

**User Story:** As a 审计助理, I want to 在检查表中记录审计说明, so that 我能文档化转回和核销检查的发现和分析过程。

#### Acceptance Criteria

1. THE Audit_Note_Section SHALL 在Section 2下方显示区段标题"三、审计说明"（只读静态文本，对应源模板Row 22）
2. THE Audit_Note_Section SHALL 渲染textarea编辑区（item_id="D1-writeoff-audit-note"，remark字段，min-height: 120px）
3. THE Audit_Note_Section SHALL 在textarea右上方显示🤖AI生成按钮
4. WHEN 用户点击🤖AI按钮时, THE Audit_Note_Section SHALL 基于Section 1/2的转回笔数、核销笔数、金额合计和跨Spec校验结果生成审计说明文本
5. THE Audit_Note_Section SHALL 通过 inject openReviewDialog 放置💬固定复核对话入口按钮

### Requirement 8: Section 4 审计结论

**User Story:** As a 审计助理, I want to 在检查表中记录审计结论, so that 我能归纳转回和核销检查的最终判断。

#### Acceptance Criteria

1. THE Audit_Conclusion_Section SHALL 在Section 3下方显示区段标题"四、审计结论"（只读静态文本，对应源模板Row 26）
2. THE Audit_Conclusion_Section SHALL 渲染textarea编辑区（item_id="D1-writeoff-audit-conclusion"，remark字段，min-height: 120px）
3. THE Audit_Conclusion_Section SHALL 在textarea右上方显示🤖AI生成按钮
4. WHEN 用户点击🤖AI按钮时, THE Audit_Conclusion_Section SHALL 基于审计说明内容和跨Spec校验结果生成审计结论文本
5. THE Audit_Conclusion_Section SHALL 通过 inject openReviewDialog 放置💬固定复核对话入口按钮
6. THE Audit_Conclusion_Section SHALL 在审计结论后显示"编制提示"折叠区（`<details>` 蓝色左边线+浅蓝背景，默认收起），内容包含：
   - 坏账准备转回条件（CAS 22：以前减记的金额后续恢复时转回）
   - 核销审批程序要求（股东大会/董事会/总经理办公会审批权限划分）
   - 关联方核销的额外披露要求
   - 转回/核销对损益影响的分析要点

### Requirement 9: 双模式切换与持久化

**User Story:** As a 审计助理, I want to 在HTML结构化视图和OnlyOffice在线编辑之间切换且所有编辑自动保存, so that 我不会丢失数据且能灵活选择编辑方式。

#### Acceptance Criteria

1. THE Dual_Mode SHALL 在组件顶部显示 el-segmented 切换控件（"结构化视图" | "在线编辑"）
2. WHEN 用户切换到OnlyOffice模式时, THE Dual_Mode SHALL 打开完整xlsx文件并通过OnlyOffice API隐藏非当前sheet（SetVisible(false)），只显示D1-16对应的sheet
3. WHEN 用户从OnlyOffice模式切回HTML模式时, THE Dual_Mode SHALL 重新加载 checklist_responses 数据以反映在OO中的编辑
4. WHILE OnlyOffice服务不可用时, THE Dual_Mode SHALL 禁用"在线编辑"选项并显示 tooltip"OnlyOffice服务不可用"
5. THE Writeoff_Check_Table SHALL 使用 checklist_responses 表存储数据，item_id前缀为"D1-writeoff-"：
   - 转回明细行JSON: "D1-writeoff-reversal-rows"（remark字段存JSON数组）
   - 核销明细行JSON: "D1-writeoff-writeoff-rows"（remark字段存JSON数组）
   - 审计说明: "D1-writeoff-audit-note"（remark字段）
   - 审计结论: "D1-writeoff-audit-conclusion"（remark字段）
6. WHEN 用户编辑任意金额/文本字段后2秒无操作时, THE Formula_Engine SHALL 触发 debounce 自动保存
7. WHEN 用户切换下拉选择类字段时, THE Formula_Engine SHALL 立即保存该字段

### Requirement 10: 跨Spec数据契约

**User Story:** As a 开发者, I want to 明确D1-16与其他Spec的数据契约, so that 跨组件数据流清晰且不会因重构而断裂。

#### Acceptance Criteria

1. THE Cross_Sheet_Ref SHALL 从同一allResponses Map中读取 Spec1(d1-adjudication-table) 的坏账准备变动数据：
   - D1-4转回变动合计：item_id含"D1-adj-bad-debt-reversal"前缀
   - D1-4核销变动合计：item_id含"D1-adj-bad-debt-writeoff"前缀
2. THE Cross_Sheet_Ref SHALL 从同一allResponses Map中读取 d1-ecl-provision 的计提数据（item_id含"D1-ecl-total-current"前缀），用于核销金额与计提总额的对比预警
3. THE Writeoff_Check_Table SHALL 将转回合计写入 item_id="D1-writeoff-reversal-total"（remark字段存金额数值），供D1-4审定表引用
4. THE Writeoff_Check_Table SHALL 将核销合计写入 item_id="D1-writeoff-writeoff-total"（remark字段存金额数值），供D1-4审定表引用
5. WHEN 转回合计或核销合计变更时, THE Formula_Engine SHALL 通过 debounce 自动更新汇总item_id的值（不使用EventBus，纯save回调）

### Requirement 11: 组件拆分与代码架构

**User Story:** As a 开发者, I want to 将转回/核销检查逻辑拆分为独立子组件和子composable, so that 代码可维护性好且每个文件控制在合理行数。

#### Acceptance Criteria

1. THE Writeoff_Check_Table SHALL 拆分为独立Vue子组件 D1TabWriteoffCheck.vue（~300行），包含4个区域（Section 1转回8列 + Section 2核销5列 + Section 3审计说明 + Section 4审计结论）
2. THE Writeoff_Check_Table SHALL 有独立composable useD1WriteoffCheck.ts（~200行），包含：
   - 转回明细行CRUD（addReversalRow/removeReversalRow/reversalRows）
   - 核销明细行CRUD（addWriteoffRow/removeWriteoffRow/writeoffRows）
   - 转回合计SUM公式（reversalTotalE/reversalTotalF）
   - 核销合计SUM公式（writeoffTotalC）
   - 跨Spec校验逻辑（reversalDiff/writeoffDiff）
   - 预警判断（reversalExceedsProvision/writeoffExceedsProvision/missingFields）
   - 持久化（save回调 + debounce）
3. THE useD1WriteoffCheck SHALL 接收 allResponses Map 和 save 回调作为参数（与现有composable模式一致）
4. THE useD1WriteoffCheck SHALL 导出以下接口：reversalRows / addReversalRow / removeReversalRow / reversalTotalE / reversalTotalF / writeoffRows / addWriteoffRow / removeWriteoffRow / writeoffTotalC / reversalDiff / writeoffDiff / auditNote / auditConclusion

### Requirement 12: 金额格式化与UI美化

**User Story:** As a 审计助理, I want to 所有金额数据以标准格式显示且检查表可读性好, so that 我能快速准确地阅读和核对数据。

#### Acceptance Criteria

1. THE Formula_Engine SHALL 对所有金额单元格应用 displayPrefs.fmtAmount 格式化（千分位分隔、保留2位小数）
2. WHEN 金额为负数时, THE Formula_Engine SHALL 以红色字体和括号格式显示（如 (1,234.56)）
3. WHEN 金额为零时, THE Formula_Engine SHALL 显示"-"而非"0.00"
4. THE Reversal_Section SHALL 对8列表使用合理列宽（单位名称150px/转回原因auto min-120px/收回方式100px/原依据auto min-120px/金额列110px/合理性分析auto min-120px/索引号80px）
5. THE Writeoff_Section SHALL 对5列表使用合理列宽（单位名称150px/性质120px/核销金额120px/核销原因auto min-150px/核销程序auto min-150px）
6. WHILE 数据正在加载时, THE Formula_Engine SHALL 在表格区域显示 el-skeleton 占位动画
7. THE Writeoff_Check_Table SHALL 对两段表格之间使用 el-divider 分隔（附带Section标题）


### Requirement 13: 差异不一致时"同步到D1-4"能力（P1联动）

**User Story:** As a 审计助理, I want to 当D1-16转回/核销合计与D1-4不一致时能一键同步到D1-4, so that 我能快速修正两表之间的数据差异。

#### Acceptance Criteria

1. WHEN reversalDiff≠0时, THE Reversal_Section SHALL 在核对区差异旁显示"同步到D1-4"按钮
2. WHEN 用户点击"同步到D1-4"按钮时, THE Cross_Sheet_Ref SHALL 将本表转回合计(reversalTotalE)写入allResponses Map的D1-4对应转回变动item_id（D1-adj-bad-debt-reversal相关前缀），并调用saveImmediate持久化
3. WHEN writeoffDiff≠0时, THE Writeoff_Section SHALL 在核对区差异旁显示"同步到D1-4"按钮
4. WHEN 用户点击"同步到D1-4"按钮时, THE Cross_Sheet_Ref SHALL 将本表核销合计(writeoffTotalC)写入D1-4对应核销变动item_id，并调用saveImmediate持久化
5. THE "同步到D1-4" 按钮 SHALL 弹出确认弹窗"将以本表合计覆盖D1-4坏账明细表的转回/核销变动列，是否继续？"
6. WHEN 同步成功后, THE Cross_Sheet_Ref SHALL 通过computed响应式自动刷新核对区差异值（预期差异变为0）+ ElMessage.success提示"已同步到D1-4"

### Requirement 14: AI辅助生成审计说明/结论（P1启用）

**User Story:** As a 审计助理, I want to 🤖AI按钮能根据转回/核销数据自动生成审计说明和结论文本, so that 我能快速获得标准化的审计说明草稿。

#### Acceptance Criteria

1. WHEN 用户点击Section 3审计说明的🤖AI按钮时, THE Audit_Note_Section SHALL 将以下context传给AI端点：转回笔数/转回金额合计/核销笔数/核销金额合计/是否与D1-4一致/是否有E>F异常行/是否核销超计提
2. WHEN 用户点击Section 4审计结论的🤖AI按钮时, THE Audit_Conclusion_Section SHALL 将以下context传给AI端点：审计说明内容 + 跨Spec校验结果 + 预警状态
3. THE AI端点 SHALL 复用已有的 `/api/workpapers/{wp_id}/a171/ai-generate` 模式
4. THE AI生成结果 SHALL 填入对应textarea（追加或替换由用户确认）
5. WHILE AI服务不可用时, THE AI按钮 SHALL 显示disabled状态 + tooltip"AI服务暂不可用"
