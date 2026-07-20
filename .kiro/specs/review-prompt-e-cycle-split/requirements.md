# Requirements Document

## Introduction

将现有科目级审计复核提示词 `backend/data/tsj_review_prompts/货币资金提示词.md` 拆分为底稿级（sheet-level）提示词，为 E1 货币资金的 22+ 张底稿各自创建专属复核提示词文件。复用 D2 应收账款试点（`review-prompt-sheet-level-split` spec）已建立的全部基础设施（ReviewPromptService / BatchReviewService / LlmResponseParser / ReviewPanel / HTTP 端点），不新建服务层，仅新增提示词数据文件与验证。

E1 货币资金底稿按审计逻辑分为四大分组：
- **核心 sheet**（E1-1 审定表 / E1-6 余额调节 / E1-14 分析表）：需高质量专属复核
- **盘点类**（E1-7 库存现金盘点人民币 / E1-8 库存现金盘点外币 / E1-9 银行存单盘点）：共用"盘点程序"骨架，按币种/资产类型细化
- **截止类**（E1-21 银行存款截止 / E1-22 其他货币资金截止）：共用"截止测试"骨架，按业务类型细化
- **IPO/舞弊应对**（E1-26~32 共 7 张）：共用"舞弊应对"骨架

## Glossary

- **Review_Prompt_Service**: 底稿级提示词加载服务（D2 试点已建），按 wp_code + sheet_suffix 匹配加载对应提示词 Markdown 文件，支持三级降级（sheet-level → subject-level → generic）
- **Batch_Review_Service**: 批量复核服务（D2 试点已建），对指定 wp_code_prefix 下的所有底稿逐份调用 LLM 复核并汇总结果
- **LLM_Response_Parser**: LLM 响应解析器（D2 试点已建），将 LLM 原始输出解析为结构化 Review_Finding 列表并判定 pass/fail
- **Review_Panel**: 前端复核结果展示面板组件（D2 试点已建），展示每张底稿复核发现清单
- **Sheet_Level_Prompt**: 底稿级复核提示词 Markdown 文件，针对特定底稿类型的专属审计复核指引
- **Prompt_Skeleton**: 提示词骨架模板，同组底稿共用的结构化框架（如盘点程序骨架），每张底稿在此基础上按具体业务细化
- **Source_Prompt**: 源提示词文件 `backend/data/tsj_review_prompts/货币资金提示词.md`，拆分内容的原始来源
- **E1_Cycle**: E1 货币资金循环，包含现金、银行存款、其他货币资金、数字货币四类资产
- **Three_Level_Fallback**: 三级降级机制——优先加载 sheet-level 文件，不存在则回退 subject-level（源科目提示词），再不存在则回退 generic 通用提示词

## Requirements

### Requirement 1: E1 底稿级提示词文件创建与存储

**User Story:** As a 现场经理, I want E1 货币资金的每张底稿都有专属复核提示词文件, so that AI 复核能聚焦于该底稿特有的审计要点而非整个科目的通用内容。

#### Acceptance Criteria

1. THE system SHALL provide sheet-level prompt files stored at path `backend/data/tsj_review_prompts/E/E1-{suffix}.md` for all 22+ E1 sheets
2. WHEN the Review_Prompt_Service loads an E1 sheet-level prompt, THE Review_Prompt_Service SHALL find files for at minimum the following sheets: E1-1(审定表), E1-2(现金明细), E1-3(银行存款明细), E1-4(数字货币明细), E1-5(调整分录), E1-6(余额调节表), E1-7(库存现金盘点人民币), E1-8(库存现金盘点外币), E1-9(银行存单盘点), E1-10(银行账户核对), E1-11(承诺书), E1-14(分析表), E1-15(利息收入月度分析), E1-18(企业信用报告查询), E1-19(企业信用报告核对), E1-20(应计利息测算), E1-21(银行存款截止测试), E1-22(其他货币资金截止测试), E1-23(收支检查情况表), E1-26(IPO舞弊应对), E1-note-listed(附注上市), E1-note-soe(附注国企)
3. WHEN an E1 prompt file for a specific sheet does not exist, THE Review_Prompt_Service SHALL fall back to the subject-level prompt `货币资金提示词.md` (three-level fallback preserved)

### Requirement 2: 提示词内容从源文件章节抽取

**User Story:** As a QC合伙人, I want each E1 sheet-level prompt to contain focused and actionable review points extracted from the source prompt, so that LLM reviews produce relevant findings specific to each sheet type.

#### Acceptance Criteria

1. WHEN creating E1 sheet-level prompt files, THE system SHALL extract corresponding content sections from the Source_Prompt `货币资金提示词.md` and reorganize them to focus on the specific sheet
2. THE E1-1(审定表) prompt SHALL focus on: 期初期末余额勾稽、试算平衡表核对、现金/银行存款/其他货币资金分类准确性、审计调整完整性、受限资金列报
3. THE E1-6(余额调节表) prompt SHALL focus on: 未达账项合理性、银行对账单与账面差异分析、长期未清账项识别、调节后余额一致性确认
4. THE E1-14(分析表) prompt SHALL focus on: 月度余额波动合理性、异常大额变动解释充分性、与经营规模匹配性、银行存款利息收入合理性测算
5. THE E1-7/E1-8/E1-9(盘点类) prompts SHALL share a common "盘点程序" skeleton focusing on: 盘点日期与资产负债表日的关系、盘点程序执行人/监盘人、盘点差异处理、账实核对一致性，with E1-7 specializing in 人民币现金、E1-8 in 外币现金(含汇率折算)、E1-9 in 银行存单(含到期日/利率核对)
6. THE E1-21/E1-22(截止类) prompts SHALL share a common "截止测试" skeleton focusing on: 截止日前后交易的期间归属、跨期金额的重要性判断、银行收付款凭证截止验证，with E1-21 specializing in 银行存款收支截止、E1-22 in 其他货币资金(保证金/信用证/存出投资款等)截止

### Requirement 3: IPO/舞弊应对分组提示词

**User Story:** As a 业务合伙人, I want IPO/舞弊应对底稿(E1-26~32)有共用骨架但各有侧重的复核提示词, so that 针对上市审计和舞弊风险的特殊程序能被精准复核。

#### Acceptance Criteria

1. THE E1-26~32(IPO/舞弊应对) prompts SHALL share a common "舞弊应对" skeleton focusing on: 管理层舞弊动机识别、异常资金流转模式、资金体外循环风险、虚假银行函证识别
2. WHEN creating IPO/舞弊应对 prompts, THE system SHALL differentiate each sheet by its specific inspection scope (e.g., 大额定期存款异常到期/资金归集异常/频繁存取大额现金/跨行大额转账异常/关联方资金占用/银行账户异常开销户/信用报告异常)
3. THE IPO/舞弊应对 prompts SHALL include checklist items referencing: CAS1141(财务报表审计中与舞弊相关的责任), CAS1631(利用内部审计人员工作), 证监会IPO审核关注要点

### Requirement 4: 复用已有 ReviewPromptService 加载机制

**User Story:** As a 开发者, I want E1 提示词文件复用 D2 试点建立的 ReviewPromptService 按 wp_code + sheet_name 匹配机制, so that 无需修改服务层代码即可支持 E1 循环。

#### Acceptance Criteria

1. WHEN a review request is received with wp_code containing "E1" prefix, THE Review_Prompt_Service SHALL resolve the sheet_suffix and look up file at `backend/data/tsj_review_prompts/E/E1-{suffix}.md`
2. THE E1 prompt file naming convention SHALL follow the same pattern as D2: `{wp_code}-{sheet_suffix}.md` where sheet_suffix is the numeric or descriptive identifier (e.g., E1-1, E1-6, E1-note-listed)
3. THE Review_Prompt_Service SHALL require zero code changes to support E1 prompt loading — only the addition of prompt files in the correct directory path

### Requirement 5: 复用已有 BatchReviewService 批量复核

**User Story:** As a 业务合伙人, I want to trigger batch review for all E1 sheets with wp_code_prefix="E1", so that 货币资金全科目的复核报告可一键生成。

#### Acceptance Criteria

1. WHEN a POST request is sent to `/api/projects/{project_id}/batch-review` with body `{wp_code_prefix: "E1"}`, THE Batch_Review_Service SHALL identify all E1 workpapers in the project and sequentially invoke LLM review using matched sheet-level prompts
2. THE Batch_Review_Service SHALL correctly discover and process all 22+ E1 sheets without requiring code changes (only prompt file existence drives coverage)
3. IF a specific E1 sheet has no dedicated prompt file, THEN THE Batch_Review_Service SHALL use the subject-level fallback and continue processing remaining sheets

### Requirement 6: 复用已有 ReviewPanel 前端组件

**User Story:** As a 现场经理, I want to view E1 batch review results in the existing ReviewPanel component, so that 货币资金复核发现的展示方式与 D2 应收账款一致。

#### Acceptance Criteria

1. WHEN the ReviewPanel is rendered with wp_code_prefix="E1", THE ReviewPanel SHALL display a card for each E1 sheet showing pass/fail status, finding count, and risk distribution
2. THE ReviewPanel SHALL render E1 sheets in logical groups: 核心(E1-1/E1-6/E1-14), 盘点类(E1-7/E1-8/E1-9), 截止类(E1-21/E1-22), IPO/舞弊(E1-26~32), 其他
3. THE ReviewPanel SHALL require zero code changes to support E1 — it dynamically renders based on batch review API response data

### Requirement 7: 端到端验证

**User Story:** As a QC合伙人, I want end-to-end verification that batch-review with wp_code_prefix="E1" correctly discovers and reviews all E1 sheets, so that I can trust the review coverage is complete.

#### Acceptance Criteria

1. WHEN batch-review is triggered with wp_code_prefix="E1" for a project containing E1 workpapers, THE system SHALL return results for all discovered E1 sheets (22+ items)
2. THE system SHALL verify each E1 sheet's review result contains: sheet_name, pass_status (pass/fail/manual_review_required), findings list, and risk_summary
3. IF any E1 sheet fails to load its prompt (file not found and subject-level also missing), THEN THE system SHALL report that sheet as "prompt_missing" in the batch result without aborting
4. THE batch-review response SHALL include coverage metadata: total_e1_sheets_in_project, sheets_with_dedicated_prompt, sheets_using_fallback, sheets_with_prompt_missing

### Requirement 8: 提示词内容质量 — 核心 sheet 专属复核

**User Story:** As a QC合伙人, I want the three core E1 sheets (审定表/余额调节/分析表) to have high-quality dedicated prompts with comprehensive checklists, so that these critical workpapers receive thorough AI review.

#### Acceptance Criteria

1. THE E1-1(审定表) prompt SHALL contain checklist items covering: 现金/银行存款/其他货币资金三大类余额完整性、期初数与上期审定数一致性、调整分录(AJE/RJE)金额正确性、受限货币资金单独列示、合计数与试算表勾稽
2. THE E1-6(余额调节表) prompt SHALL contain checklist items covering: 全部银行账户均编制调节表、银行对账单期末余额正确取得、每笔未达账项有充分凭据支持、长期(>6个月)未达账项的合理解释、调节后余额=账面余额+银行已收未入-银行已付未出+企业已收未入-企业已付未出
3. THE E1-14(分析表) prompt SHALL contain checklist items covering: 12月月度余额趋势与经营活动匹配、大额存取款与收入/支出联动分析、银行存款利率合理性(年化利息/日均余额)、定期存款计息正确性、与同行业可比公司货币资金占比对比

### Requirement 9: 提示词内容质量 — 辅助 sheet 检查

**User Story:** As a 现场经理, I want auxiliary E1 sheets (明细/银行核对/信用报告/利息测算等) to have targeted prompts, so that LLM review covers the specific verification objectives of each sheet.

#### Acceptance Criteria

1. THE E1-2(现金明细) prompt SHALL focus on: 现金日记账与总账核对、现金收支审批合规性、大额现金交易合理性(>5万)
2. THE E1-3(银行存款明细) prompt SHALL focus on: 各银行账户余额与对账单/函证核对、账户用途描述完整性、休眠账户识别
3. THE E1-10(银行账户核对) prompt SHALL focus on: 全部银行账户的函证覆盖率、函证发函/收函程序合规性、函证金额与账面差异解释
4. THE E1-15(利息收入月度分析) prompt SHALL focus on: 月度利息收入波动合理性、利息收入与银行存款余额匹配度、各账户利率是否处于合理区间
5. THE E1-18/E1-19(信用报告) prompt SHALL focus on: 企业信用报告查询完整性(央行征信+商业征信)、信用报告中贷款余额与账面核对、对外担保披露完整性、信用报告异常项(逾期/不良)的跟进处理
6. THE E1-20(应计利息测算) prompt SHALL focus on: 定期存款应计利息计算准确性(本金×利率×实际天数/360或365)、测算金额与账面差异分析、利息确认截止正确性

