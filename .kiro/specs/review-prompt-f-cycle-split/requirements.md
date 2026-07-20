# Requirements Document

## Introduction

参照 D2 应收账款试点和 E1 货币资金试点，为 F 循环（F1 预付账款 / F2 存货 / F3 应付票据 / F4 应付账款 / F5 营业成本）创建底稿级复核提示词拆分三件套。

F 循环共 5 个科目约 85 张底稿，是所有审计循环中底稿数量最多的一个循环（F2 存货独占约 45 张）。复用 D2 试点已建立的全部基础设施（ReviewPromptService / BatchReviewService / LlmResponseParser / ReviewPanel / HTTP 端点），不新建服务层，仅新增提示词数据文件与验证脚本。

F 循环底稿分布：
- **F1 预付账款**（~10 sheets）：F1-1 审定/F1-2 明细/F1-3 调整/F1-4 实质性分析/F1-5 长期挂款/F1-6 关联方/F1-7 凭证检查/F1-note-listed 附注上市/F1-note-soe 附注国企
- **F2 存货**（~45 sheets，最复杂）：核心审定明细+计价+盘点+检查+截止+IPO+减值+成本分析+合同成本
- **F3 应付票据**（~9 sheets）：F3-1 审定/F3-2 明细/F3-3 调整/F3-4 利息测算/F3-5 逾期/F3-6 关联方/F3-7 凭证/F3-note-listed/F3-note-soe
- **F4 应付账款**（~11 sheets）：F4-1 审定/F4-2 明细/F4-3 调整/F4-4 分析/F4-5 长期挂账/F4-6 关联方/F4-7 未入账/F4-8 凭证/F4-9 供应商融资/F4-note-listed/F4-note-soe
- **F5 营业成本**（~10 sheets）：F5-1 审定/F5-2 月度明细/F5-3 其他业务成本/F5-4 调整/F5-5 比较分析/F5-6 数量核对/F5-7 成本倒轧/F5-8 重大调整/F5-note-listed/F5-note-soe

源文件映射：
- `存货审计复核提示词.md` → F2 各 sheet
- `预付账款审计复核提示词.md` → F1 各 sheet
- `应付票据审计复核提示词.md` → F3 各 sheet
- `应付账款审计复核提示词.md` → F4 各 sheet
- `成本审计复核提示词.md` → F5 各 sheet

## Glossary

- **Review_Prompt_Service**: 底稿级提示词加载服务（D2 试点已建），按 wp_code + sheet_suffix 匹配加载对应提示词 Markdown 文件，支持三级降级（sheet-level → subject-level → generic）
- **Batch_Review_Service**: 批量复核服务（D2 试点已建），对指定 wp_code_prefix 下的所有底稿逐份调用 LLM 复核并汇总结果
- **LLM_Response_Parser**: LLM 响应解析器（D2 试点已建），将 LLM 原始输出解析为结构化 Review_Finding 列表并判定 pass/fail
- **Review_Panel**: 前端复核结果展示面板组件（D2 试点已建），展示每张底稿复核发现清单
- **Sheet_Level_Prompt**: 底稿级复核提示词 Markdown 文件，针对特定底稿类型的专属审计复核指引
- **Prompt_Skeleton**: 提示词骨架模板，同组底稿共用的结构化框架（如盘点程序骨架/截止测试骨架/计价测试骨架），每张底稿在此基础上按具体业务细化
- **Source_Prompt**: 源提示词文件（5 个科目各一个），拆分内容的原始来源
- **F_Cycle**: F 循环（采购与存货循环），包含预付账款/存货/应付票据/应付账款/营业成本五个科目
- **Three_Level_Fallback**: 三级降级机制——优先加载 sheet-level 文件，不存在则回退 subject-level（源科目提示词），再不存在则回退 generic 通用提示词
- **F2_Subgroup**: F2 存货按审计逻辑分为 7 个子分组：核心/盘点/计价/截止/减值/成本分析/IPO
- **Lint_Script**: 验证脚本 `check_f_review_prompts.py`，执行格式检查（lint）与覆盖率检测（coverage）

## Requirements

### Requirement 1: F 循环提示词文件创建与目录结构

**User Story:** As a 现场经理, I want F 循环的 5 个科目 80+ 张底稿都有专属复核提示词文件, so that AI 复核能聚焦于每张底稿特有的审计要点而非整个科目的通用内容。

#### Acceptance Criteria

1. THE system SHALL provide sheet-level prompt files stored at directory `backend/data/tsj_review_prompts/F/` with naming pattern `{wp_code}-{sheet_suffix}.md`
2. WHEN the Review_Prompt_Service initializes, THE Review_Prompt_Service SHALL discover and load all F-cycle prompt files from `backend/data/tsj_review_prompts/F/` without code changes
3. THE F-cycle prompts directory SHALL contain files for all 5 subjects: F1(预付账款, ~10 files), F2(存货, ~45 files), F3(应付票据, ~9 files), F4(应付账款, ~11 files), F5(营业成本, ~10 files), totaling 80+ files
4. IF a sheet-level prompt file does not exist for a requested F-cycle wp_code + sheet_suffix, THEN THE Review_Prompt_Service SHALL fall back to the subject-level prompt file (Three_Level_Fallback preserved)

### Requirement 2: F1 预付账款提示词拆分

**User Story:** As a QC合伙人, I want F1 预付账款的每张底稿有针对性的复核提示词, so that LLM 复核能覆盖预付账款特有的风险点（虚构预付/关联方占用/长期挂账不转销等）。

#### Acceptance Criteria

1. THE system SHALL provide prompt files for F1 sheets: F1-1(审定表), F1-2(明细表), F1-3(调整分录), F1-4(实质性分析), F1-5(长期挂款), F1-6(关联方), F1-7(凭证检查), F1-note-listed(附注上市), F1-note-soe(附注国企)
2. THE F1-1(审定表) prompt SHALL focus on: 预付账款期初期末勾稽、试算平衡表核对、长短期分类准确性（一年内到期 vs 长期预付）、审计调整完整性
3. THE F1-5(长期挂款) prompt SHALL focus on: 超 1 年预付合理性验证、长期挂账是否转资产减值或费用/重分类其他应收、与明细表余额交叉核对、拟调整闭环至 F1-3
4. THE F1-7(凭证检查) prompt SHALL focus on: 样本选取合理性（覆盖大额/关联方/期末突增）、真实交易验证（合同/发票/验收单三匹配）、预付款发出审批合规性
5. THE F1-4(实质性分析) prompt SHALL focus on: 预付账款周转天数分析、前五大供应商集中度、同比变动合理性、与应付账款/存货联动分析
6. THE F1-6(关联方) prompt SHALL focus on: 关联方识别完整、商业实质、定价公允、资金占用与披露

### Requirement 3: F2 存货提示词拆分（核心分组）

**User Story:** As a 业务合伙人, I want F2 存货的核心底稿（审定/明细汇总/分类明细/调整）有高质量的专属复核提示词, so that 存货审定数的准确性和完整性能被严格复核。

#### Acceptance Criteria

1. THE system SHALL provide prompt files for F2 core sheets aligned to live codes: F2-1(审定表), F2-2(明细汇总), F2-3~F2-13(分类明细：原材料/在途/周转材料/半成品/委托加工/库存商品/发出商品/开发产品/开发成本/合同履约/消耗性生物资产), F2-14(调整分录), F2-16(会计政策), F2-18~F2-20(分析类)
2. THE F2-1(审定表) prompt SHALL focus on: 原材料/在产品/库存商品/周转材料等分类余额勾稽、试算平衡表核对、存货跌价准备对冲列示（科目 1471）、进销差价（科目 1412）、在途物资/发出商品单独列报完整性
3. THE F2-2(明细汇总) prompt SHALL focus on: F2-3~13 分类合计勾稽、数量与金额逻辑一致性、负数库存识别、呆滞品标记覆盖
4. THE F2-14(调整分录) prompt SHALL focus on: 调整事项与盘点差异/跌价准备/截止调整的对应关系、AJE/RJE 金额正确性、科目对照准确性（跌价准备=1471，进销差价=1412）
5. WHEN creating detail prompts F2-3~F2-13, THE prompts SHALL specialize in each inventory category's movement completeness and aging

### Requirement 4: F2 存货提示词拆分（盘点分组）

**User Story:** As a 现场经理, I want F2 存货盘点类底稿（F2-21~F2-26）共用"盘点程序"骨架但各有侧重, so that 监盘程序的执行质量能被针对性复核。

#### Acceptance Criteria

1. THE system SHALL provide prompt files for F2 stocktake sheets aligned to live codes: F2-21A(监盘程序), F2-21(问卷), F2-22(盘点计划), F2-23(盘点汇总), F2-24(账实核对), F2-25(抽盘结果), F2-26(倒轧)
2. THE F2 stocktake prompts SHALL share a common "盘点程序" skeleton focusing on: 盘点日期与资产负债表日关系、盘前准备充分性、实地监盘程序执行记录、账实差异处理、截止信息记录
3. WHEN creating F2-25(抽盘结果) prompt, THE prompt SHALL specialize in: 抽盘比例达标性、抽盘样本代表性、盘点标签序号连续性
4. WHEN creating F2-24(账实核对) prompt, THE prompt SHALL specialize in: 差异金额与重要性水平对比、差异原因合理性、调整建议是否已转 AJE
5. WHEN creating F2-26(倒轧) prompt, THE prompt SHALL specialize in: 盘点日至资产负债表日收发存倒轧完整性

### Requirement 5: F2 存货提示词拆分（计价分组）

**User Story:** As a QC合伙人, I want F2 存货计价类底稿有专门的计价测试复核要点, so that 存货成本归集和计价方法的合理性能被深入复核。

#### Acceptance Criteria

1. THE system SHALL provide prompt files for implemented F2 valuation sheets only: F2-33(采购入库检查), F2-34(材料领用检查), F2-35(委外加工检查), F2-38(加权平均), F2-39(先进先出), F2-40(标准成本), F2-41~F2-44(生产成本/人工/制造费用/分配), F2-52(关联方采购). Reserved/unimplemented sheet numbers F2-36/37/45/46/50/51 SHALL NOT receive prompt files until implemented
2. THE F2 valuation prompts SHALL share a common "计价测试" skeleton focusing on: 成本归集完整性、成本计算方法一致性、成本还原与倒轧验证
3. THE F2-33(采购入库检查) prompt SHALL focus on: 采购单价与合同/发票一致性、入库数量与验收单核对、运费/保险费/税费归集正确性、大额采购审批链
4. THE F2-35(委外加工检查) prompt SHALL focus on: 发出材料成本+加工费=收回材料成本恒等验证、与 F2-7 期末勾稽、三表加工费交叉校验
5. THE F2-38/F2-39 prompts SHALL focus on: 加权平均/先进先出计算正确性与方法一贯性

### Requirement 6: F2 存货提示词拆分（截止分组）

**User Story:** As a 业务合伙人, I want F2 截止测试底稿（F2-29~F2-32）有针对采购/发出双向截止的复核要点, so that 期末存货截止的准确性能被系统性验证。

#### Acceptance Criteria

1. THE system SHALL provide prompt files for F2 cutoff sheets: F2-29(入库×账→单), F2-30(入库×单→账), F2-31(出库×账→单), F2-32(出库×单→账)
2. THE F2 cutoff prompts SHALL share a common "截止测试" skeleton focusing on: 基准日前后 N 天交易的期间归属、跨期金额与重要性水平对比、实物流转与单据流转时间差
3. THE F2-29 prompt SHALL focus on: 期末最后若干张入库单是否入账、暂估入库的及时性与准确性
4. THE F2-31 prompt SHALL focus on: 期末出库与收入确认截止一致性、发出商品与收入同期性

### Requirement 7: F2 存货提示词拆分（减值分组）

**User Story:** As a QC合伙人, I want F2 减值类底稿（F2-47~F2-49）有 NRV 测试和减值转回的专项复核, so that 存货跌价准备的计提/转回/核销符合 CAS1 要求。

#### Acceptance Criteria

1. THE system SHALL provide prompt files for F2 impairment sheets: F2-47(NRV 测试), F2-48(长库龄/呆滞), F2-49(跌价转回核对)
2. THE F2-47 prompt SHALL focus on: 可变现净值=估计售价-估计销售费用-估计税金、售价取数来源合理性、库龄>1年品种是否逐项测试、科目 1471 与审定表勾稽
3. THE F2-48 prompt SHALL focus on: 长库龄/呆滞/超保质期识别、与跌价准备充分性勾稽
4. THE F2-49 prompt SHALL focus on: 期初/计提/转回/核销/期末勾稽、转回条件（CAS1 第 21 条）、核销审批

### Requirement 8: F2 存货提示词拆分（成本分析与 IPO 分组）

**User Story:** As a QC合伙人, I want F2 IPO/合同成本与附注底稿有专属复核提示词, so that 特殊程序与披露质量可复核。

#### Acceptance Criteria

1. THE system SHALL provide prompt files for F2-55A/F2-55~58(合同成本系列) and F2-61A/F2-61~72(IPO 系列) that exist in `wp_code_overrides.json`
2. THE F2 IPO prompts SHALL focus on: 采购价格公允性、产能利用率、单耗、关联方采购、供应商访谈等各 sheet 特有点
3. THE F2-note-listed / F2-note-soe prompts SHALL focus on: 分类/跌价准备披露与 F2-1 勾稽
4. Reserved sheet numbers (F2-15/17/27/28/36/37/45/46/50/51) SHALL be documented as not-implemented and excluded from prompt coverage targets

### Requirement 9: F3 应付票据提示词拆分

**User Story:** As a 现场经理, I want F3 应付票据的每张底稿有专属复核提示词, so that 票据的真实性、利息计算和逾期风险能被针对性验证。

#### Acceptance Criteria

1. THE system SHALL provide prompt files for F3 sheets: F3-1(审定表), F3-2(明细表), F3-3(调整分录), F3-4(利息测算), F3-5(逾期分析), F3-6(关联方票据), F3-7(凭证检查), F3-note-listed(附注上市), F3-note-soe(附注国企)
2. THE F3-4(利息测算) prompt SHALL focus on: 应付票据利息=面值×票面利率×持有天数/360（或365）、贴现利息计算正确性、实际利率法 vs 直线法的一致性
3. THE F3-5(逾期分析) prompt SHALL focus on: 逾期票据的到期日确认、逾期原因合理性、是否已转应付账款/其他应付款重分类、逾期违约金计提充分性
4. THE F3-6(关联方票据) prompt SHALL focus on: 关联方票据背书/贴现的终止确认判断、融资性票据识别、CAS36 披露完整性

### Requirement 10: F4 应付账款提示词拆分

**User Story:** As a QC合伙人, I want F4 应付账款的每张底稿有专属复核提示词, so that 应付账款的完整性、长期挂账和未入账负债能被重点关注。

#### Acceptance Criteria

1. THE system SHALL provide prompt files for F4 sheets: F4-1(审定表), F4-2(明细表), F4-3(调整分录), F4-4(分析表), F4-5(长期挂账), F4-6(关联方), F4-7(未入账检查), F4-8(凭证检查), F4-9(供应商融资安排), F4-note-listed(附注上市), F4-note-soe(附注国企)
2. THE F4-5(长期挂账) prompt SHALL focus on: 超 1 年未付原因验证、是否存在无需支付的应付款（应转营业外收入）、与供应商对账确认结果
3. THE F4-7(未入账检查) prompt SHALL focus on: 期后付款中属于本期负债的识别、暂估入库金额准确性、货物已收发票未到的完整统计、函证差异中的未入账部分
4. THE F4-9(供应商融资安排) prompt SHALL focus on: 反向保理/应付账款融资的识别与披露、是否改变负债分类（贸易应付 vs 借款）、IFRS实务公告影响评估

### Requirement 11: F5 营业成本提示词拆分

**User Story:** As a 业务合伙人, I want F5 营业成本的每张底稿有专属复核提示词, so that 成本结转的完整性和准确性以及毛利率合理性能被系统性验证。

#### Acceptance Criteria

1. THE system SHALL provide prompt files for F5 sheets: F5-1(审定表), F5-2(月度明细), F5-3(其他业务成本), F5-4(调整分录), F5-5(比较分析), F5-6(数量核对), F5-7(成本倒轧), F5-8(重大调整检查), F5-note-listed(附注上市), F5-note-soe(附注国企)
2. THE F5-7(成本倒轧) prompt SHALL focus on: 期初存货+本期采购（入库）-期末存货=营业成本恒等验证、倒轧差异金额与重要性水平对比、差异原因分类（盘亏/报废/样品/跌价）
3. THE F5-5(比较分析) prompt SHALL focus on: 各产品线毛利率同比变动（波动>5%需解释）、月度成本变动趋势与产量/销量匹配、行业平均毛利率对标
4. THE F5-6(数量核对) prompt SHALL focus on: 产量×单位成本=结转成本金额核对、产销量差异与存货变动勾稽、各品种投入产出比合理性

### Requirement 12: 复用已有基础设施（零代码修改）

**User Story:** As a 开发者, I want F 循环提示词文件复用 D2/E1 试点建立的全部服务层基础设施, so that 无需修改任何后端/前端服务代码即可支持 F 循环 5 个科目的批量复核。

#### Acceptance Criteria

1. THE Review_Prompt_Service SHALL require zero code changes to support F-cycle prompt loading — only the addition of prompt files in the directory `backend/data/tsj_review_prompts/F/`
2. WHEN a POST request is sent to `/api/projects/{project_id}/batch-review` with body `{wp_code_prefix: "F1"}` or `"F2"` or `"F3"` or `"F4"` or `"F5"`, THE Batch_Review_Service SHALL identify all matching workpapers and sequentially invoke LLM review using matched sheet-level prompts
3. THE ReviewPanel frontend component SHALL render F-cycle review results with zero code changes — dynamic rendering based on batch review API response data
4. THE LLM_Response_Parser SHALL parse F-cycle review outputs using the same structured parsing logic as D2/E1 without modifications

### Requirement 13: 验证脚本 check_f_review_prompts.py

**User Story:** As a 开发者, I want a validation script that checks F-cycle prompt files for format compliance and coverage completeness, so that newly added or modified prompt files are automatically validated before deployment.

#### Acceptance Criteria

1. THE Lint_Script SHALL be located at `backend/scripts/check/check_f_review_prompts.py` and executable via `python backend/scripts/check/check_f_review_prompts.py`
2. WHEN the Lint_Script executes lint checks, THE Lint_Script SHALL verify each prompt file contains: a title line (# heading), at least one checklist section (## or ### heading with items), and a minimum of 5 checklist items per file
3. WHEN the Lint_Script executes coverage checks, THE Lint_Script SHALL verify that the expected sheet list for each F-cycle subject (F1: 9+, F2: 45+, F3: 9+, F4: 11+, F5: 10+) has corresponding prompt files present in the F/ directory
4. WHEN the Lint_Script detects missing or malformed files, THE Lint_Script SHALL output a clear report listing: missing files (expected but not found), malformed files (present but failing lint), and coverage percentage per subject (files found / files expected)
5. THE Lint_Script SHALL exit with code 0 when all checks pass, and exit with code 1 when any check fails (CI-compatible)

### Requirement 14: F2 存货分组展示与验证

**User Story:** As a 现场经理, I want F2 存货的 45+ 张底稿在批量复核时按逻辑分组展示, so that 复核结果便于按审计程序类型逐组审阅。

#### Acceptance Criteria

1. WHEN batch-review is triggered with wp_code_prefix="F2", THE Batch_Review_Service SHALL process all F2 sheets and the ReviewPanel SHALL display results grouped by: 核心(F2-1/F2-2/F2-3), 盘点(F2-4~F2-12), 计价(F2-33~F2-40), 截止(F2-29~F2-32), 减值(F2-47~F2-49), 成本分析(F2-41~F2-44), IPO(F2-61~F2-68)
2. THE Lint_Script SHALL validate that all F2 subgroups have at least the minimum expected file count: 核心≥3, 盘点≥9, 计价≥8, 截止≥4, 减值≥3, 成本分析≥4, IPO≥8
3. THE batch-review response for wp_code_prefix="F2" SHALL include subgroup metadata in the coverage section: subgroup_name, sheets_in_subgroup, sheets_reviewed, sheets_passed


