# Requirements Document

## Introduction

D2-7 应收账款凭证检查表全面重构升级。当前实现为单区 flat 表格 + 基础抽样参数区 + GtVoucherSamplingEngine collapse，需对照源模板五大区段结构完成升级：双区检查表（本期增减变动 + 期后收款调整）、方法学参数区 AI 辅助、卡片+矩阵双视图、行级附件 OCR+AI 核对+确认回填、审计说明统计区自动化，以及抽凭引擎方法学深度增强。

## Glossary

- **Voucher_Check_System**: D2-7 凭证检查表前端组件及其 composable 层，负责凭证抽查数据录入、AI 核对、统计汇总与持久化
- **Sampling_Engine**: GtVoucherSamplingEngine 抽凭引擎组件，负责方法学参数配置、凭证抽取、结果回填
- **OCR_Service**: 后端 `/d4/contract-ocr` 端点，负责附件文件 OCR 识别并返回结构化文本
- **AI_Service**: 后端 `/api/workpapers/{wpId}/ai/generate-text` 通用 AI 文本生成端点
- **Dual_Zone_Table**: 双区检查表结构，包含区(1)本期增减变动检查和区(2)期后收款调整检查
- **Card_View**: 卡片视图，每笔凭证一张卡片展示关键信息与核对状态
- **Matrix_View**: 矩阵视图，el-table 宽表 17 列完整展示
- **Methodology_Panel**: 方法学参数区，展示测试总体/特定样本/抽样总体/抽样方法/抽样程序等参数
- **Check_Column**: 核对内容列（核对内容1~5），对应支持性文件与凭证数据的交叉验证结果
- **Audit_Summary**: 审计说明统计区，包含发生额合计/检查金额/检查比例/异常统计/AI 说明文字
- **B15_Materiality**: B15 重要性水平底稿，提供可容忍错报与整体重要性数据
- **B50_Risk**: B50 风险评估底稿，提供科目风险等级（高/中/低）
- **PostFill_Review**: 回写后 AI 复核弹窗（PostFillAiReviewDialog），用于抽凭回填后发起 AI 异常识别

## Requirements

### Requirement 1: 双区检查表结构

**User Story:** As a 审计助理, I want 凭证检查表按源模板划分为"(1)本期增减变动检查"和"(2)期后收款调整检查"两个独立区块, so that 我能分别记录应收账款本期发生额核查与期后回款核查的结果。

#### Acceptance Criteria

1. THE Voucher_Check_System SHALL 在界面中呈现两个独立检查区块：区(1)"本期增减变动检查"和区(2)"期后收款调整检查"
2. WHEN 用户切换区块时, THE Voucher_Check_System SHALL 保持另一区块的数据不变并在视图切换后恢复原有编辑状态
3. THE Voucher_Check_System SHALL 为每个区块提供完整的 17 列结构：客户名称/日期/凭证编号/业务内容/对方科目/对方明细科目/借方金额/贷方金额/支持性文件/核对内容1/核对内容2/核对内容3/核对内容4/核对内容5/索引号/是否异常/备注说明
4. THE Voucher_Check_System SHALL 将两个区块的数据独立存储（使用不同的 item_id 前缀：`D2-vc-current-` 和 `D2-vc-post-`）
5. WHEN 从 Sampling_Engine 接收抽凭结果时, THE Voucher_Check_System SHALL 根据凭证日期与资产负债表日的关系自动分配到对应区块（本期凭证→区1，期后凭证→区2）

### Requirement 2: 源模板五区段对齐

**User Story:** As a 现场经理, I want 凭证检查表的整体结构严格对照源模板五大区段, so that 底稿格式符合致同审计底稿规范且便于复核。

#### Acceptance Criteria

1. THE Voucher_Check_System SHALL 按以下顺序呈现五大区段：一、审计目标 → 二、样本选取标准与规模（Methodology_Panel）→ 三、测试（Dual_Zone_Table）→ 四、审计说明（Audit_Summary）→ 五、审计结论
2. THE Voucher_Check_System SHALL 在"一、审计目标"区段显示 el-alert 展示审计目标描述文字
3. THE Voucher_Check_System SHALL 在"二、样本选取标准与规模"区段呈现方法学参数（测试总体/特定样本/抽样总体/抽样方法/抽样程序），每个参数可编辑
4. THE Voucher_Check_System SHALL 在"五、审计结论"区段提供带 AI 辅助按钮的 textarea 用于填写审计师最终结论

### Requirement 3: 卡片+矩阵双视图

**User Story:** As a 现场经理, I want 在卡片视图和矩阵视图之间自由切换, so that 我在快速复核时使用卡片概览、在逐笔编辑时使用矩阵宽表。

#### Acceptance Criteria

1. THE Voucher_Check_System SHALL 在检查表区域顶部提供 el-segmented 视图切换控件，包含"矩阵视图"和"卡片视图"两个选项
2. WHEN 用户选择"矩阵视图"时, THE Voucher_Check_System SHALL 以 el-table 宽表形式展示 17 列完整数据
3. WHEN 用户选择"卡片视图"时, THE Voucher_Check_System SHALL 以卡片列表形式展示每笔凭证，每张卡片包含：客户名称、凭证日期、凭证编号、借方/贷方金额、核对状态（5项核对的完成率进度条）、附件缩略图、是否异常标记
4. THE Voucher_Check_System SHALL 在两种视图之间共享同一数据源，视图切换后数据保持一致
5. THE Voucher_Check_System SHALL 默认展示矩阵视图

### Requirement 4: 行级附件上传与 OCR 识别

**User Story:** As a 审计助理, I want 在每笔凭证行上传发票/合同/发货单等证据文件并自动 OCR 识别提取关键信息, so that 我无需手动抄录证据文件内容。

#### Acceptance Criteria

1. THE Voucher_Check_System SHALL 在每行凭证的"支持性文件"列提供📎附件上传按钮
2. WHEN 用户上传文件后, THE Voucher_Check_System SHALL 调用 OCR_Service（`POST /d4/contract-ocr`）对文件执行 OCR 识别
3. WHEN OCR_Service 返回结果后, THE Voucher_Check_System SHALL 从识别文本中提取关键信息（金额、日期、对方单位、合同编号）
4. IF OCR_Service 调用失败, THEN THE Voucher_Check_System SHALL 显示降级提示"OCR 服务暂不可用，请手动录入"并保留已上传的附件记录
5. THE Voucher_Check_System SHALL 在卡片视图中展示已上传附件的缩略图预览

### Requirement 5: AI 核对与确认回填

**User Story:** As a 审计助理, I want OCR 识别后系统自动比对证据文件信息与凭证数据并将核对结果回填, so that 我只需确认 AI 核对结果而无需逐项手动比对。

#### Acceptance Criteria

1. WHEN OCR 识别完成后, THE Voucher_Check_System SHALL 自动将 OCR 提取的金额与凭证行的借方/贷方金额进行比对
2. WHEN OCR 识别完成后, THE Voucher_Check_System SHALL 自动将 OCR 提取的日期与凭证行的日期进行比对
3. WHEN OCR 识别完成后, THE Voucher_Check_System SHALL 自动将 OCR 提取的对方单位与凭证行的对方科目/对方明细科目进行比对
4. WHEN AI 核对完成后, THE Voucher_Check_System SHALL 弹出 ElMessageBox 确认弹窗，展示核对结果摘要（各项一致/不一致/无法判定），用户可逐项确认或修改
5. WHEN 用户确认 AI 核对结果后, THE Voucher_Check_System SHALL 将确认结果自动填入核对内容1~5列（核对内容1=金额一致性, 核对内容2=日期一致性, 核对内容3=对方科目匹配, 核对内容4=业务内容相符, 核对内容5=附件完整性）
6. IF 用户取消确认弹窗, THEN THE Voucher_Check_System SHALL 不修改核对内容列的现有值

### Requirement 6: 抽凭引擎方法学 AI 辅助

**User Story:** As a 审计助理, I want 抽凭引擎根据科目特征和风险等级自动推荐抽样方法与样本量, so that 我的抽样决策有科学依据且符合审计准则要求。

#### Acceptance Criteria

1. WHEN 用户打开抽凭引擎配置时, THE Sampling_Engine SHALL 联动 B15_Materiality 和 B50_Risk 数据，基于科目1122（应收账款）的风险等级和可容忍错报推荐抽样方法（随机/分层/MUS/特定项目）
2. WHEN Sampling_Engine 推荐抽样方法后, THE Sampling_Engine SHALL 显示 AI 推荐标签并说明推荐理由（如"科目风险=高 → 建议MUS，间隔=可容忍错报÷风险系数"）
3. THE Sampling_Engine SHALL 基于 B15_Materiality 的可容忍错报和 B50_Risk 的风险等级自动计算推荐样本量（MUS 间隔=可容忍错报÷可靠性系数；随机=基于总体规模×置信度查表）
4. THE Sampling_Engine SHALL 允许用户覆盖 AI 推荐值并手动设置抽样方法与样本量

### Requirement 7: 测试总体描述 AI 生成

**User Story:** As a 审计助理, I want 方法学参数区的"测试总体"描述由 AI 基于试算表数据自动生成, so that 我无需手动统计和编写总体描述。

#### Acceptance Criteria

1. WHEN 方法学参数区加载时, THE Voucher_Check_System SHALL 从试算表(trial_balance)获取科目1122的本期借方发生额合计和交易笔数
2. THE Voucher_Check_System SHALL 基于试算表数据 AI 生成测试总体描述文字（格式示例："本期应收账款借方发生额合计 XX 元，涉及 XX 笔交易"）
3. WHEN 用户点击"AI 生成"按钮时, THE Voucher_Check_System SHALL 调用 AI_Service 生成测试总体描述并回填到测试总体输入框
4. THE Voucher_Check_System SHALL 允许用户编辑 AI 生成的测试总体描述文字

### Requirement 8: 特定样本 AI 筛选与抽样总体计算

**User Story:** As a 审计助理, I want AI 自动从测试总体中标记大额/关联方/异常日期交易为特定样本, so that 高风险交易被优先纳入检查范围且抽样总体自动更新。

#### Acceptance Criteria

1. WHEN 用户点击"AI 筛选特定样本"按钮时, THE Sampling_Engine SHALL 基于以下规则自动标记特定样本：金额≥可容忍错报的交易、关联方交易、异常日期（非营业日/期末集中）交易
2. THE Sampling_Engine SHALL 在方法学参数区展示特定样本列表（客户名称/金额/标记原因），用户可逐项确认或取消标记
3. THE Voucher_Check_System SHALL 自动计算抽样总体 = 测试总体 - 特定样本（金额和笔数同步扣除）
4. WHEN 特定样本列表变更时, THE Voucher_Check_System SHALL 实时更新抽样总体数值并重新计算推荐样本量

### Requirement 9: 审计说明统计区自动化

**User Story:** As a 现场经理, I want 审计说明区自动统计检查金额、覆盖比例和异常情况, so that 我能一目了然地了解细节测试的覆盖度和结果。

#### Acceptance Criteria

1. THE Audit_Summary SHALL 自动计算并展示以下统计指标：本期发生额合计（从试算表获取）、已检查金额合计（双区检查表借方+贷方金额加总）、检查覆盖比例（已检查金额÷本期发生额×100%）
2. THE Audit_Summary SHALL 自动计算并展示异常统计：异常笔数、异常金额合计、异常率（异常笔数÷已检查笔数×100%）
3. WHEN 用户点击"AI 生成审计说明"按钮时, THE Audit_Summary SHALL 调用 AI_Service 基于统计数据和异常明细生成审计说明文字
4. THE Audit_Summary SHALL 将统计指标以只读计算字段展示（灰底虚线下划线 + cursor:help + tooltip 显示计算来源）
5. WHEN 检查表数据发生变更时, THE Audit_Summary SHALL 在 2 秒内重新计算并更新统计指标

### Requirement 10: 抽凭结果双区回填

**User Story:** As a 审计助理, I want 抽凭引擎的抽样结果自动按凭证属性分配到双区检查表的对应区块, so that 我无需手动将凭证分类填入。

#### Acceptance Criteria

1. WHEN Sampling_Engine 完成抽样并触发 @filled 事件时, THE Voucher_Check_System SHALL 将抽样凭证按日期分类：凭证日期≤资产负债表日 → 区(1)本期增减变动检查；凭证日期>资产负债表日 → 区(2)期后收款调整检查
2. THE Voucher_Check_System SHALL 将 SampledVoucher 字段映射到 17 列结构：voucherNo→凭证编号, voucherDate→日期, debitAmount→借方金额, creditAmount→贷方金额, summary→业务内容, counterpartAccount→对方科目, accountCode→对方明细科目
3. WHEN 以合并模式(merge)回填时, THE Voucher_Check_System SHALL 按凭证编号去重，已存在的凭证保持原有核对结果不覆盖
4. THE Voucher_Check_System SHALL 在回填完成后自动触发 PostFill_Review 弹窗，供用户选择是否发起 AI 异常识别复核

### Requirement 11: 方法学参数区样本量 AI 联动

**User Story:** As a 审计助理, I want 样本量确定自动联动重要性水平和风险评估, so that 样本量设定有科学依据并符合 CAS 1314 要求。

#### Acceptance Criteria

1. THE Sampling_Engine SHALL 从 B15_Materiality 获取可容忍错报值，从 B50_Risk 获取科目1122的综合风险等级
2. WHEN 抽样方法为 MUS 时, THE Sampling_Engine SHALL 自动计算 MUS 间隔（可容忍错报 ÷ 可靠性系数，可靠性系数根据风险等级查 CAS 1314 泊松表）
3. WHEN 抽样方法为随机抽样时, THE Sampling_Engine SHALL 基于总体规模、置信水平（风险等级映射：高→95%/中→90%/低→80%）和预期错报率计算推荐样本量
4. THE Sampling_Engine SHALL 在方法学参数区展示 AI 推荐标签："🤖 建议样本量: N 笔（基于 B15 可容忍错报 X 元 + B50 风险等级=高）"
5. THE Sampling_Engine SHALL 允许用户手动调整样本量，调整后显示偏离标记"⚠️ 样本量低于建议值"或"✓ 样本量满足要求"

### Requirement 12: 导入导出增强

**User Story:** As a 审计助理, I want 双区检查表支持按区分 sheet 导入导出, so that 我能在 Excel 中批量编辑并导入检查结果。

#### Acceptance Criteria

1. THE Voucher_Check_System SHALL 提供 el-dropdown "导入导出▾" 按钮，包含三项：导出模板/导出数据/导入数据
2. WHEN 用户选择"导出模板"时, THE Voucher_Check_System SHALL 生成包含两个 sheet 的 xlsx 文件："本期增减变动检查"sheet 和"期后收款调整检查"sheet，每 sheet 含 17 列表头
3. WHEN 用户选择"导出数据"时, THE Voucher_Check_System SHALL 将双区数据导出为两个 sheet，包含已填入的全部数据
4. WHEN 用户选择"导入数据"时, THE Voucher_Check_System SHALL 读取 xlsx 文件的两个 sheet 并分别导入到对应区块，按凭证编号合并或追加
5. IF 导入文件缺少某个 sheet, THEN THE Voucher_Check_System SHALL 仅导入存在的 sheet 数据并提示用户"未找到'{sheet名}'sheet，已跳过"
