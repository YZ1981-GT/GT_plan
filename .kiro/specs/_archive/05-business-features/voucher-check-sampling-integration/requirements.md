# Requirements Document

## Introduction

本特性为 D3-7 预收账款凭证检查表补齐"行级附件上传 + OCR 识别 + AI 辅助 + 用户确认 + 回写字段"的完整证据闭环，并将检查表与既有抽凭引擎（`GtVoucherSamplingEngine`）以弹窗方式深度联动，使审计师能够在检查表内自定义抽凭方法、勾选凭证、查看与使用凭证版本链。当前 D3-7 仅有异常点选，缺失上述全部能力，本特性以 D3-7 为**样板与本次主目标**，交付一套可被其他循环凭证检查表复用的标准范式。

本特性同时融入审计抽凭专家视角的方法学改进项（科学样本量推导、MUS 完整方法学、错报推断与总体结论、总体完整性校验、重抽治理等，见分组三），并明确抽凭与四表库凭证库的联动口径、将同一联动扩展至截止性测试底稿、在两类回写后统一提供 AI 复核弹窗闭环（见分组四）；以**可选/后续需求项**形式界定其他循环同类凭证检查表（D2-7/G4-13/G5-12/G6/G7-18/G8-6/G9-6/G10-7/G12-6/G2/G3/F2 等）的横向统一改造范围（见分组二）。

**能力边界声明**：本特性以"凭证检查表全闭环"为中心，复用既有抽凭引擎、OCR 端点、AI 端点、版本链服务，不重复实现 `ui-pattern-unification` spec 负责的通用工具栏迁移与 collapse→dialog 的全局模式统一；两者重叠处以本特性对凭证检查表的具体验收标准为准。

本文档聚焦"能力与验收标准"，不描述实现代码。

## Glossary

- **Voucher_Check_Sheet（凭证检查表）**：以 D3-7 预收账款凭证检查表为样板的检查表组件，含"本期增减变动"与"期后结转"两区块，每行包含客户名称、日期、凭证号、金额、原始凭证、核对项、异常标记等字段。
- **Sampling_Engine（抽凭引擎）**：既有通用组件 `GtVoucherSamplingEngine`，支持随机、分层、特定项目、系统、货币单元（MUS/PPS）五种抽样方法，并输出覆盖率统计与合规提示。
- **Sampling_Dialog（抽凭弹窗）**：在 Voucher_Check_Sheet 内以弹窗形式承载 Sampling_Engine 的交互界面。
- **Sample_Result（抽样结果）**：Sampling_Engine 经 `filled` 回调返回的样本集合，含样本列表（samples）、审计阶段（phase）、填充模式（fillMode）、抽样方法（method）。
- **Fill_Mode（填充模式）**：抽样结果回填 Voucher_Check_Sheet 的方式，取值为追加（append）、替换（replace）、合并去重（merge）。
- **OCR_Service（OCR 识别服务）**：既有端点 `POST /api/workpapers/{wpId}/d4/contract-ocr`，接收附件返回识别字段。
- **OCR_Field_Map（OCR 字段映射）**：OCR 识别字段名到 Voucher_Check_Sheet 行字段的映射表。
- **AI_Assist_Service（AI 辅助服务）**：既有端点 `POST /api/workpapers/{wp_id}/ai/generate-text`，按 section 白名单生成建议文本。
- **Version_Trail_Service（版本链服务）**：既有 `useVersionTrail` 能力，支持自动快照与历史追溯。
- **Coverage_Feedback（覆盖率反馈）**：基于抽样结果计算的笔数覆盖率、金额覆盖率、异常率及未覆盖大额提示。
- **Auditor（审计师）**：使用 Voucher_Check_Sheet 编制底稿的用户角色。
- **Readonly_State（只读状态）**：底稿处于不可编辑状态（如复核锁定或权限受限）。
- **Confidence_Threshold（置信度阈值）**：OCR 识别结果判定为"低置信度需人工复核"的分界值。
- **Tolerable_Misstatement（可容忍错报）**：审计师就某一总体确定的、可接受的最大错报金额，通常取实际执行的重要性（Performance Materiality）。
- **Expected_Misstatement（预期错报）**：审计师基于以往经验或初步评估对总体中可能存在错报的预计金额。
- **Confidence_Level（置信度/信赖水平）**：抽样结论的可信程度，与可接受的抽样风险（误受风险）互补；用于推导可信赖度系数。
- **Reliability_Factor（可信赖度系数）**：由置信度与预期错报确定的泊松系数，用于 MUS 样本量与抽样间隔计算。
- **Sampling_Interval（抽样间隔）**：货币单元抽样中相邻样本货币单元之间的距离，等于总体金额 ÷ 样本量。
- **High_Value_Item（高值必选项/顶层）**：单笔金额大于等于抽样间隔的凭证，货币单元抽样中应 100% 选取。
- **Projected_Misstatement（推断错报）**：将样本中发现的错报按抽样方法外推到总体的错报估计。
- **Upper_Misstatement_Limit（错报上限）**：推断错报叠加抽样风险余量后的总体错报上界，用于与可容忍错报比较得出总体结论。
- **Sampling_Conclusion（抽样结论）**：比较错报上限与可容忍错报后对总体是否可接受作出的判断。
- **Population_Reconciliation（总体完整性校验）**：将抽样总体金额/笔数合计与账面（序时账/明细表/审定数）核对，确认抽样总体完整。
- **Materiality_Workpaper（重要性水平底稿）**：既有重要性模块/B15 底稿，提供整体重要性与实际执行重要性。
- **Attribute_Sampling（属性抽样）**：用于控制测试的抽样，基于预计偏差率、可容忍偏差率与置信度确定样本量并评估偏差率上限。
- **Sampling_Memo（抽样计划与结论备忘）**：记录抽样方法、参数、样本量依据、覆盖率、错报推断与结论的归档文档。
- **Voucher_Library（四表库凭证库）**：项目四表库中存储凭证级分录数据的凭证库（序时账/凭证明细），是抽凭与截止测试检索的总体来源，可按会计科目、方向、金额、日期检索。
- **Cutoff_Test（截止性测试底稿）**：检验交易是否记录于正确会计期间的底稿，围绕基准日前后天数检查凭证是否跨期。
- **Cutoff_Date（基准日）**：资产负债表日/期末日，截止性测试以其前后天数界定检索窗口。
- **Post_Fill_AI_Review（回写后 AI 复核）**：抽凭或截止凭证回写到底稿后触发的 AI 复核，识别异常与跨期问题并给出意见，经审计师确认后填入审计说明。

---

## Requirements

**分组一 · 本次必做（D3-7 样板全闭环 + 抽凭弹窗联动）**

### Requirement 1: 行级附件上传

**User Story:** 作为审计师，我希望在凭证检查表每一行上传合同、发票、收款凭据等附件，以便为该凭证的检查留存审计证据。

#### Acceptance Criteria

1. THE Voucher_Check_Sheet SHALL 在"本期增减变动"与"期后结转"两区块的每一行提供附件上传入口。
2. WHEN Auditor 在某行选择一个附件文件，THE Voucher_Check_Sheet SHALL 接受图片格式与 PDF 格式的文件。
3. WHEN 某行已成功关联附件，THE Voucher_Check_Sheet SHALL 在该行显示已关联附件的可视标识。
4. WHILE Readonly_State 为真，THE Voucher_Check_Sheet SHALL 禁用附件上传入口。
5. IF 上传的文件类型不在允许范围内，THEN THE Voucher_Check_Sheet SHALL 拒绝该文件并向 Auditor 显示文件类型不被支持的提示。

### Requirement 2: 附件 OCR 识别与字段回写确认

**User Story:** 作为审计师，我希望上传附件后系统自动识别关键字段并在我确认后填入当前行，以便减少手工录入并保证以人工确认为准。

#### Acceptance Criteria

1. WHEN Auditor 在某行上传附件，THE OCR_Service SHALL 接收该附件并返回识别字段集合。
2. WHEN OCR_Service 返回识别字段，THE Voucher_Check_Sheet SHALL 依据 OCR_Field_Map 将识别字段映射为该行的客户名称、日期、凭证号、金额、摘要字段。
3. WHEN 映射后存在可填充字段，THE Voucher_Check_Sheet SHALL 在填入前向 Auditor 展示识别结果确认弹窗。
4. WHEN Auditor 在确认弹窗中确认填入，THE Voucher_Check_Sheet SHALL 将映射字段合并写入当前行并保留 Auditor 已手工录入且未被识别覆盖的字段值。
5. WHEN Auditor 在确认弹窗中取消，THE Voucher_Check_Sheet SHALL 保持当前行字段不变。
6. IF OCR_Service 未返回任何可填充字段，THEN THE Voucher_Check_Sheet SHALL 向 Auditor 提示未识别到可填充字段且不弹出确认弹窗。
7. IF OCR_Service 调用失败，THEN THE Voucher_Check_Sheet SHALL 向 Auditor 提示识别失败且保持当前行字段不变。
8. WHERE OCR_Service 返回的字段置信度低于 Confidence_Threshold，THE Voucher_Check_Sheet SHALL 在确认弹窗中标注该字段需人工复核。

### Requirement 3: AI 辅助生成建议文本

**User Story:** 作为审计师，我希望对检查结论或审计说明获得 AI 生成的建议文本，以便更快完成叙述性内容的编制。

#### Acceptance Criteria

1. THE Voucher_Check_Sheet SHALL 在检查结论文本区提供 AI 辅助生成入口。
2. WHEN Auditor 触发 AI 辅助生成，THE AI_Assist_Service SHALL 接收当前 section 标识、上下文与已有内容并返回建议文本。
3. WHEN AI_Assist_Service 返回建议文本，THE Voucher_Check_Sheet SHALL 向 Auditor 展示建议文本供确认后再写入。
4. WHEN Auditor 确认采用建议文本，THE Voucher_Check_Sheet SHALL 将该文本写入对应文本区。
5. IF AI_Assist_Service 不可用，THEN THE Voucher_Check_Sheet SHALL 向 Auditor 提示 AI 服务暂不可用并保持文本区内容不变。
6. WHILE Readonly_State 为真，THE Voucher_Check_Sheet SHALL 禁用 AI 辅助生成入口。

### Requirement 4: 抽凭弹窗联动打开

**User Story:** 作为审计师，我希望在凭证检查表内以弹窗方式打开抽凭功能界面，以便在不离开检查表的情况下完成抽凭。

#### Acceptance Criteria

1. THE Voucher_Check_Sheet SHALL 提供打开 Sampling_Dialog 的入口。
2. WHEN Auditor 打开 Sampling_Dialog，THE Sampling_Dialog SHALL 以弹窗方式承载 Sampling_Engine 并传入当前项目标识、预收账款科目编码 2203 与审计阶段。
3. THE Voucher_Check_Sheet SHALL 复用既有 Sampling_Engine 组件承载抽凭交互。
4. WHEN Auditor 关闭 Sampling_Dialog，THE Voucher_Check_Sheet SHALL 保留 Sampling_Dialog 打开前已存在的检查表数据。
5. WHILE Readonly_State 为真，THE Voucher_Check_Sheet SHALL 禁用打开 Sampling_Dialog 的入口。

### Requirement 5: 抽凭方法自定义与总体范围设定

**User Story:** 作为审计师，我希望在抽凭弹窗内自定义抽样方法与总体范围，以便按审计判断选择合适的抽样策略。

#### Acceptance Criteria

1. THE Sampling_Engine SHALL 向 Auditor 提供随机抽样、分层抽样、特定项目抽样、系统抽样与货币单元抽样五种可选方法。
2. WHERE Auditor 选择货币单元抽样，THE Sampling_Engine SHALL 允许 Auditor 设定样本量参数。
3. WHERE Auditor 选择特定项目抽样，THE Sampling_Engine SHALL 允许 Auditor 设定重要性金额阈值。
4. WHERE Auditor 选择分层抽样，THE Sampling_Engine SHALL 允许 Auditor 设定每一层的金额边界与该层样本量。
5. THE Sampling_Engine SHALL 允许 Auditor 设定总体范围条件，包含借贷方向、日期区间与科目范围。
6. IF Auditor 提交的抽样配置缺少所选方法的必填参数，THEN THE Sampling_Engine SHALL 阻止执行抽样并提示缺失的参数项。

### Requirement 6: 凭证勾选的人工增删与特定选取原因

**User Story:** 作为审计师，我希望对系统抽样结果进行人工增删勾选并标注特定选取原因，以便体现审计判断并覆盖系统抽样。

#### Acceptance Criteria

1. WHEN Sampling_Engine 完成一次抽样，THE Sampling_Engine SHALL 以样本列表形式向 Auditor 展示抽样结果。
2. WHEN Auditor 主动新增勾选系统抽样未选中的凭证，THE Sampling_Engine SHALL 将该凭证纳入已勾选样本集合；在 Auditor 主动新增之前，THE Sampling_Engine SHALL 不将该凭证纳入已勾选样本集合。
3. WHEN Auditor 主动取消勾选某凭证，THE Sampling_Engine SHALL 将该凭证移出已勾选样本集合；在 Auditor 主动取消之前，THE Sampling_Engine SHALL 保持该凭证的已勾选状态。
4. WHEN Auditor 对同一凭证号重复勾选，THE Sampling_Engine SHALL 对该凭证号去重后仅保留一条。
5. WHERE Auditor 对某条凭证标注特定选取原因，THE Sampling_Engine SHALL 保存该原因并随样本一并回填。

### Requirement 7: 抽样结果回填检查表并标注来源

**User Story:** 作为审计师，我希望将确认后的抽样结果按指定填充模式回填到检查表并标注来源为抽凭，以便区分自动抽凭样本与手工录入样本。

#### Acceptance Criteria

1. WHEN Auditor 在 Sampling_Dialog 中确认填充，THE Sampling_Engine SHALL 通过 Sample_Result 回调向 Voucher_Check_Sheet 返回样本列表、审计阶段与填充模式。
2. WHEN Voucher_Check_Sheet 收到 Sample_Result，THE Voucher_Check_Sheet SHALL 将每条样本的凭证号、日期、金额、摘要、对方科目映射为检查表行字段。
3. WHERE Fill_Mode 为替换，THE Voucher_Check_Sheet SHALL 以样本集合替换目标区块的现有行。
4. WHERE Fill_Mode 为合并，THE Voucher_Check_Sheet SHALL 按凭证号去重后将新增样本追加到目标区块。
5. WHERE Fill_Mode 为追加，THE Voucher_Check_Sheet SHALL 将样本集合追加到目标区块末尾。
6. WHEN 一条来自抽样结果的行被写入检查表，THE Voucher_Check_Sheet SHALL 将该行来源标注为抽凭。

### Requirement 8: 覆盖率与代表性反馈

**User Story:** 作为审计师，我希望查看抽样的覆盖率与代表性反馈，以便评估样本是否充分并识别未覆盖的大额凭证。

#### Acceptance Criteria

1. WHEN Sampling_Engine 完成一次抽样，THE Coverage_Feedback SHALL 显示样本相对总体的笔数覆盖率与金额覆盖率。
2. WHEN Sampling_Engine 完成一次抽样，THE Coverage_Feedback SHALL 显示样本数量与总体数量的对比。
3. WHERE 金额覆盖率低于合规阈值，THE Coverage_Feedback SHALL 向 Auditor 显示覆盖率偏低并建议增大样本量或调整抽样条件的提示。
4. WHERE 存在未被样本覆盖的大额凭证，THE Coverage_Feedback SHALL 向 Auditor 提示存在未覆盖的大额凭证。
5. THE Coverage_Feedback SHALL 显示当前样本的异常率。

### Requirement 9: 凭证版本链快照与重抽可追溯

**User Story:** 作为审计师，我希望每次抽样与勾选形成可追溯的版本快照并在重抽时保留历史批次，以便追溯谁在何时用何方法抽样并对比不同批次。

#### Acceptance Criteria

1. WHEN Auditor 确认一次抽样填充，THE Version_Trail_Service SHALL 生成一条包含抽样方法、执行时间与执行人的快照记录。
2. WHEN Auditor 执行重抽，THE Sampling_Engine SHALL 保留此前的历史批次记录。
3. WHEN Auditor 请求对比两个历史批次，THE Sampling_Engine SHALL 显示两批次间新增、移除与保留的凭证号。
4. THE Sampling_Engine SHALL 允许 Auditor 撤销最近一次抽样批次。

### Requirement 10: 人工确认优先的立场约束

**User Story:** 作为审计师，我希望系统始终以人工确认为准且点选优先于手打，以便符合审计职业判断的立场铁律。

#### Acceptance Criteria

1. WHEN AI_Assist_Service 或 OCR_Service 返回结果，THE Voucher_Check_Sheet SHALL 在 Auditor 确认前不将该结果作为最终值写入检查表。
2. THE Voucher_Check_Sheet SHALL 对异常标记等枚举字段提供点选方式录入。
3. WHERE 某字段同时提供点选与手工输入，THE Voucher_Check_Sheet SHALL 允许 Auditor 在点选值基础上进行手工修改。
4. THE Voucher_Check_Sheet SHALL 复用同一 Sampling_Engine 承载抽凭交互而不为本检查表单独实现抽凭逻辑。

### Requirement 11: 异常标记与跨底稿联动回写

**User Story:** 作为审计师，我希望对检查出的异常进行标记并保留与收入截止测试及错报汇总的可追溯钩子，以便异常能够传导至相关底稿。

#### Acceptance Criteria

1. THE Voucher_Check_Sheet SHALL 允许 Auditor 通过点选方式为每行标注异常类型，且异常类型至少包含跨期疑点、金额异常、无原始凭证、对方科目异常、重复入账。
2. WHERE 某行标注为跨期疑点，THE Voucher_Check_Sheet SHALL 保留该行与收入截止测试底稿 D4 的可追溯关联标识。
3. WHEN 检查表存在被标注为异常的行，THE Voucher_Check_Sheet SHALL 在汇总区显示异常笔数与异常率。
4. WHERE 某异常需汇总至错报，THE Voucher_Check_Sheet SHALL 保留该异常与错报汇总底稿 A13 的可追溯关联标识。

### Requirement 12: 只读与权限约束

**User Story:** 作为审计师，我希望在底稿被复核锁定或无编辑权限时相关编辑能力被禁用，以便保护已复核数据的完整性。

#### Acceptance Criteria

1. WHILE Readonly_State 为真，THE Voucher_Check_Sheet SHALL 禁用行的新增与删除操作。
2. WHILE Readonly_State 为真，THE Voucher_Check_Sheet SHALL 禁用行字段的编辑。
3. WHILE Readonly_State 为真，THE Voucher_Check_Sheet SHALL 禁用抽样结果回填。

---

**分组二 · 横向推广（其他循环凭证检查表统一改造，可选/后续）**

> 以下需求项为本次样板交付之后的横向推广范围，作为**可选/后续**实施项，按"与 D3-7 样板同款范式对齐"的原则纳入，各底稿成熟度不一，可分批推进。

### Requirement 13: 同类凭证检查表按样板范式对齐

**User Story:** 作为审计师，我希望其他循环的同类凭证检查表获得与 D3-7 样板一致的证据闭环与抽凭联动能力，以便跨循环使用统一的操作范式。

#### Acceptance Criteria

1. WHERE 某循环的凭证检查表被纳入统一改造，THE Voucher_Check_Sheet SHALL 提供与 D3-7 样板一致的行级附件上传与 OCR 识别回写能力。
2. THE Voucher_Check_Sheet SHALL 复用同一 Sampling_Engine 承载抽凭交互，无论该循环的凭证检查表是否已被纳入统一改造。
3. WHERE 某循环的凭证检查表被纳入统一改造，THE Voucher_Check_Sheet SHALL 使用该循环对应的科目编码作为抽凭总体范围。
4. WHERE 某循环的凭证检查表已集成抽凭引擎，THE Voucher_Check_Sheet SHALL 在不破坏其现有抽凭能力的前提下补齐缺失的证据闭环能力。

### Requirement 14: 改造范围与优先级界定

**User Story:** 作为现场经理，我希望明确横向改造的候选底稿清单与优先级，以便分批安排改造工作。

#### Acceptance Criteria

1. THE 横向改造候选清单 SHALL 包含 D2-7、G4-13、G5-12、G6、G7-18、G8-6、G9-6、G10-7、G12-6、G2、G3 与 F2 存货抽凭。
2. WHERE 某候选底稿当前为占位或待接入状态，THE 横向改造清单 SHALL 将该底稿标注为待接入优先级。
3. THE 横向改造范围 SHALL 排除 `ui-pattern-unification` spec 已覆盖的通用工具栏迁移与全局 collapse→dialog 模式统一工作。

---

**分组三 · 抽凭引擎方法学增强（审计抽样专家改进）**

> 现有抽凭引擎已具备五种抽样方法、覆盖率统计、CAS 1314 三条合规校验、版本 diff/历史/撤销、字段级留痕与随机种子。以下为审计抽样专家视角识别的方法学缺口改进：现有引擎以"覆盖率/异常标记"为终点，缺少**科学样本量推导、MUS 完整方法学、错报推断与总体结论、总体完整性校验、与重要性联动**这一实质性抽样的核心闭环。本组作为对既有 `voucher-sampling-engine` 的增强需求，与 D3-7 样板改造并行推进；实现时优先保证不破坏既有五方法与回填/历史能力。

### Requirement 15: 科学样本量推导

**User Story:** 作为审计师，我希望系统根据可容忍错报、预期错报与置信度自动推导建议样本量，以便样本量的确定有可辩护的方法学依据而非凭经验拍脑袋。

#### Acceptance Criteria

1. WHERE Auditor 选择货币单元抽样或随机抽样，THE Sampling_Engine SHALL 依据 Confidence_Level、Tolerable_Misstatement、Expected_Misstatement 与总体金额推导建议样本量。
2. WHEN Sampling_Engine 推导货币单元抽样的样本量，THE Sampling_Engine SHALL 依据 Reliability_Factor 与可容忍错报计算 Sampling_Interval 并据此得出样本量。
3. THE Sampling_Engine SHALL 允许 Auditor 在建议样本量基础上手工覆盖为其他值。
4. WHEN Auditor 手工覆盖建议样本量，THE Sampling_Engine SHALL 保留系统建议值与覆盖值二者以备留痕。
5. IF 缺少 Tolerable_Misstatement 或 Confidence_Level，THEN THE Sampling_Engine SHALL 阻止样本量推导并提示需补充的参数。

### Requirement 16: 与重要性水平底稿联动

**User Story:** 作为审计师，我希望可容忍错报默认从重要性水平底稿带入，以便抽样参数与项目整体重要性保持一致。

#### Acceptance Criteria

1. WHERE 项目已编制 Materiality_Workpaper，THE Sampling_Engine SHALL 默认以其实际执行重要性作为 Tolerable_Misstatement 的初始值。
2. THE Sampling_Engine SHALL 允许 Auditor 覆盖由重要性底稿带入的 Tolerable_Misstatement。
3. IF 未能从 Materiality_Workpaper 取得重要性数据，THEN THE Sampling_Engine SHALL 允许 Auditor 手工录入 Tolerable_Misstatement。

### Requirement 17: 货币单元抽样完整方法学

**User Story:** 作为审计师，我希望货币单元抽样按规范同时处理高值必选项与抽样间隔，以便大额凭证被充分覆盖。

#### Acceptance Criteria

1. WHEN Auditor 执行货币单元抽样，THE Sampling_Engine SHALL 显示本次使用的 Sampling_Interval。
2. WHEN Auditor 执行货币单元抽样，THE Sampling_Engine SHALL 将单笔金额大于等于 Sampling_Interval 的 High_Value_Item 全部选取。
3. THE Sampling_Engine SHALL 对低于 Sampling_Interval 的凭证按货币单元系统抽样选取。
4. THE Sampling_Engine SHALL 在抽样结果中区分标识 High_Value_Item 与常规抽样样本。

### Requirement 18: 错报推断与总体结论

**User Story:** 作为审计师，我希望录入样本实际错报后系统推断总体错报并给出总体是否可接受的结论建议，以便完成实质性抽样的评价环节。

#### Acceptance Criteria

1. THE Sampling_Engine SHALL 允许 Auditor 对每条已检查样本录入实际错报金额。
2. WHEN Auditor 录入样本错报，THE Sampling_Engine SHALL 按当前抽样方法推断总体 Projected_Misstatement。
3. WHERE 抽样方法为货币单元抽样，THE Sampling_Engine SHALL 以样本污染率乘以 Sampling_Interval 汇总推断错报，并叠加 High_Value_Item 层的已知错报。
4. WHEN Sampling_Engine 得出 Projected_Misstatement，THE Sampling_Engine SHALL 计算叠加抽样风险余量后的 Upper_Misstatement_Limit。
5. WHEN Upper_Misstatement_Limit 小于等于 Tolerable_Misstatement，THE Sampling_Engine SHALL 给出总体可接受的 Sampling_Conclusion。
6. WHEN Upper_Misstatement_Limit 大于 Tolerable_Misstatement，THE Sampling_Engine SHALL 给出总体可能存在重大错报并建议扩大样本、执行替代程序或提请调整的 Sampling_Conclusion。
7. THE Sampling_Engine SHALL 在 Auditor 确认前不将 Sampling_Conclusion 作为最终审计结论写入底稿。

### Requirement 19: 总体完整性校验

**User Story:** 作为审计师，我希望抽样前系统将抽样总体与账面核对，以便确认从完整的总体中抽样，避免抽样结论失效。

#### Acceptance Criteria

1. WHEN Auditor 打开 Sampling_Dialog，THE Population_Reconciliation SHALL 显示抽样总体的金额合计与笔数合计。
2. THE Population_Reconciliation SHALL 将抽样总体金额合计与账面来源（序时账、明细表或审定数）进行核对并显示差异。
3. WHERE 抽样总体与账面差异超过可容忍阈值，THE Population_Reconciliation SHALL 向 Auditor 提示总体可能不完整且抽样结论受限。

### Requirement 20: 统计抽样参数录入

**User Story:** 作为审计师，我希望在抽样配置中录入置信度、可容忍错报与预期错报，以便驱动科学样本量推导与错报评价。

#### Acceptance Criteria

1. THE Sampling_Engine SHALL 在抽样配置中提供 Confidence_Level、Tolerable_Misstatement 与 Expected_Misstatement 的录入项。
2. WHERE Auditor 采用统计抽样方法，THE Sampling_Engine SHALL 校验 Confidence_Level 与 Tolerable_Misstatement 为必填。
3. IF Expected_Misstatement 大于等于 Tolerable_Misstatement，THEN THE Sampling_Engine SHALL 提示参数不合理并阻止样本量推导。

### Requirement 21: 抽样计划与结论备忘导出

**User Story:** 作为审计师，我希望导出记录抽样方法、参数、样本量依据、覆盖率、错报推断与结论的备忘，以便归档并支持复核与可辩护性。

#### Acceptance Criteria

1. THE Sampling_Engine SHALL 支持导出 Sampling_Memo，内容包含抽样方法、抽样参数、样本量推导依据、覆盖率统计、错报推断与 Sampling_Conclusion。
2. WHEN Auditor 请求导出 Sampling_Memo，THE Sampling_Engine SHALL 以当前抽样批次的实际数据生成备忘内容。

### Requirement 22: 重抽治理与可复现

**User Story:** 作为质量控制复核人，我希望重抽必须记录原因且随机种子可复现，以便防止择优抽样并支持独立重演。

#### Acceptance Criteria

1. WHEN Auditor 执行重抽，THE Sampling_Engine SHALL 要求 Auditor 录入重抽原因。
2. THE Sampling_Engine SHALL 保存每次抽样使用的随机种子并在抽凭历史与版本链中展示。
3. THE Sampling_Engine SHALL 不得静默覆盖已存在的历史抽样批次。

### Requirement 23: 属性抽样（控制测试）扩展 — 可选/后续

**User Story:** 作为审计师，我希望在控制测试场景下使用属性抽样，以便按偏差率而非金额评价控制运行有效性。

#### Acceptance Criteria

1. WHERE Sampling_Engine 用于控制测试，THE Sampling_Engine SHALL 支持 Attribute_Sampling，依据预计偏差率、可容忍偏差率与 Confidence_Level 推导样本量。
2. WHEN Auditor 录入样本中的偏差数量，THE Attribute_Sampling SHALL 计算偏差率上限并与可容忍偏差率比较给出控制是否有效的结论建议。
3. THE Attribute_Sampling SHALL 作为可选/后续能力，不影响实质性抽样（金额法）的既有流程。

---

**分组四 · 四表库凭证库联动 + 截止性测试 + 回写后 AI 复核**

> 本组明确抽凭与四表库凭证库的联动口径，并将同一联动范式扩展至截止性测试底稿；两类回写完成后统一提供回写后 AI 复核弹窗闭环。

### Requirement 24: 凭证库（四表库）联动与按科目单/多回写

**User Story:** 作为审计师，我希望抽凭直接调用四表库凭证库并按当前底稿对应的会计科目检索凭证，选定单条或多条后一次性回写到底稿，以便高效获取与本底稿相关的凭证。

#### Acceptance Criteria

1. WHEN Auditor 在 Sampling_Dialog 执行抽样，THE Sampling_Engine SHALL 从 Voucher_Library 按所选抽样方法与总体范围（含会计科目、方向、金额、日期）检索候选凭证。
2. WHERE 当前底稿绑定特定会计科目，THE Sampling_Engine SHALL 默认以该科目作为 Voucher_Library 检索的科目范围。
3. WHEN Auditor 选定单条或多条凭证并确认回写，THE Voucher_Check_Sheet SHALL 一次性将选定凭证的凭证号与对应会计科目回写到当前底稿。
4. THE Sampling_Engine SHALL 支持随机、分层、特定项目、系统、货币单元多种方法从 Voucher_Library 检索。
5. WHEN 回写完成，THE Voucher_Check_Sheet SHALL 将回写行来源标注为抽凭。

### Requirement 25: 截止性测试凭证联动

**User Story:** 作为审计师，我希望在截止性测试底稿按基准日前后天数一键从四表库获取符合条件的凭证并回写，以便快速完成期末截止测试的取数。

#### Acceptance Criteria

1. THE Cutoff_Test SHALL 允许 Auditor 设定 Cutoff_Date 与其前后天数窗口。
2. THE Cutoff_Test SHALL 允许 Auditor 设定检索条件，包含会计科目范围、借贷方向与金额条件。
3. WHEN Auditor 触发一键取数，THE Cutoff_Test SHALL 从 Voucher_Library 检索 Cutoff_Date 前后指定天数内符合条件的凭证。
4. WHEN 检索完成，THE Cutoff_Test SHALL 将符合条件的凭证回写到截止性测试底稿。
5. WHERE 凭证的记账日期与业务发生期间跨越 Cutoff_Date，THE Cutoff_Test SHALL 将该凭证标注为跨期疑点。
6. WHILE Readonly_State 为真，THE Cutoff_Test SHALL 禁用一键取数与回写。

### Requirement 26: 回写后 AI 复核弹窗闭环

**User Story:** 作为审计师，我希望抽凭或截止凭证回写完成后系统提示我发起 AI 复核以识别异常与跨期问题，AI 给出意见并经我确认后填入审计说明，以便快速形成有依据的审计说明且以人工确认为准。

#### Acceptance Criteria

1. WHEN 抽凭结果回写到 Voucher_Check_Sheet 完成，THE Voucher_Check_Sheet SHALL 弹出提示询问 Auditor 是否发起 Post_Fill_AI_Review。
2. WHEN 截止凭证回写到 Cutoff_Test 完成，THE Cutoff_Test SHALL 弹出提示询问 Auditor 是否发起 Post_Fill_AI_Review。
3. WHEN Auditor 发起 Post_Fill_AI_Review，THE AI_Assist_Service SHALL 基于回写凭证识别潜在异常与跨期问题并返回复核意见。
4. WHEN AI_Assist_Service 返回复核意见，THE Post_Fill_AI_Review 弹窗 SHALL 向 Auditor 展示该意见供确认。
5. WHEN Auditor 确认采用复核意见，THE 系统 SHALL 将该意见填入对应底稿的审计说明。
6. WHEN Auditor 取消，THE 系统 SHALL 不将复核意见写入审计说明。
7. IF AI_Assist_Service 不可用，THEN THE Post_Fill_AI_Review 弹窗 SHALL 提示不可用且不影响已回写的凭证数据。
8. THE 系统 SHALL 在 Auditor 确认前不将 AI 复核意见作为最终结论写入底稿。
