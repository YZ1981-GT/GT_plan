# Requirements Document

## 变更记录

| 版本 | 日期 | 摘要 | 触发原因 |
|------|------|------|----------|
| v1.0 | 2026-05-17 | 初始版本 | D 收入循环底稿内容预设立项 |

## 依赖矩阵

| 上游 Spec | 关键产出 | Fallback 策略 |
|-----------|----------|---------------|
| workpaper-completion-foundation | 预填充视觉指示器 / 一键填充按钮 / 跨模块跳转标签 / 覆盖保护 | 本 spec 只产出数据（JSON），不依赖 foundation UI 就绪即可独立实施 |
| workpaper-deep-optimization | prefill_engine.py / prefill_formula_mapping.json 消费机制 | prefill_engine 已就绪，本 spec 仅扩展数据条目 |
| audit-chain-generation | init_workpaper_from_template / prefill_workpaper_xlsx | 底稿生成+预填充链路已完成，本 spec 在其基础上补充 D 循环数据 |

## Introduction

本 spec 为 D 收入循环（D0-D7）8 个底稿模板定义具体的内容预设数据——公式映射、跨模块引用、校验规则和审计程序清单。

当前状态：
- `prefill_formula_mapping.json` 已有 D0-D7 审定表级公式（共 37 个 cell 映射），覆盖期初/未审数/AJE/RJE/上年 5 行
- `cross_wp_references.json` 已有 CW-07（D2 坏账→信用减值损失）1 条 D 循环引用
- D2 模板已验证（20 sheets / 13024 cells），陕西华氏项目有真实数据（1122 应收账款期末 6,290,044,665.30）

本 spec 需要补充的内容：
1. **分析程序 sheet 公式**——上年对比/变动率/重要性判断（当前 mapping 只覆盖审定表，缺分析程序）
2. **明细表 sheet 公式**——按客户/账龄/币种分类汇总（当前完全缺失）
3. **D 循环内部跨底稿引用**——D2 审定数→D0 函证金额、D4 收入→D2 应收周转率等
4. **D 循环→附注/报表引用**——D2→附注 5.7、D4→附注 5.14、D1→附注 5.3 等
5. **校验规则**——借贷平衡/与 TB 一致/与附注一致/账龄合计=余额等
6. **审计程序清单**——每个 D 底稿的标准审计步骤

本 spec 聚焦 DATA 内容（JSON 配置文件），不涉及 prefill_engine 代码改动或前端 UI 变更。

## Glossary

- **Prefill_Engine**: 后端预填充引擎（`backend/app/services/prefill_engine.py`），读取 prefill_formula_mapping.json 执行取数
- **D_Cycle**: 收入循环，包含 D0（函证）、D1（应收票据）、D2（应收账款）、D3（预收款项）、D4（营业收入）、D5（应收款项融资）、D6（合同资产）、D7（合同负债）
- **Validation_Rule**: 校验规则，定义底稿数据必须满足的一致性条件
- **Procedure_Step**: 审计程序步骤，定义审计师对每个底稿应执行的标准操作序列
- **Cross_Reference**: 跨模块引用，定义底稿单元格数据流向附注/报表/其他底稿的关系
- **Analysis_Sheet**: 分析程序工作表，包含上年对比、变动率计算、重要性判断
- **Detail_Sheet**: 明细表工作表，按客户/账龄/币种等维度分类汇总

## Requirements

### Requirement 1: D 循环分析程序公式映射

**User Story:** As a 审计师, I want D0-D7 每个底稿的分析程序 sheet 自动预填上年数据和变动率计算基础值, so that 我打开分析程序时已有对比数据，只需关注异常变动的解释。

#### Acceptance Criteria

1. WHEN prefill is triggered for a D-cycle workpaper, THE Prefill_Engine SHALL populate the Analysis_Sheet "上年审定数" column with values from =PREV formula for each line item
2. WHEN prefill is triggered for a D-cycle workpaper, THE Prefill_Engine SHALL populate the Analysis_Sheet "本年未审数" column with values from =TB formula matching the same account codes as the 审定表
3. THE prefill_formula_mapping.json SHALL contain Analysis_Sheet entries for all 8 D-cycle workpapers (D0-D7), each with at least "上年审定数" and "本年未审数" formula cells
4. WHEN a D-cycle workpaper has multiple sub-accounts (e.g. D4 covers 6001+6051), THE Analysis_Sheet formulas SHALL use =TB_SUM to aggregate across the same account range as the 审定表
5. IF the prior year data is unavailable (first-year engagement), THEN THE Prefill_Engine SHALL leave the "上年审定数" cell empty and set prefill_source to "PREV_UNAVAILABLE"

### Requirement 2: D 循环明细表公式映射

**User Story:** As a 审计师, I want D2 应收账款明细表自动从辅助余额表取数按客户/账龄分类汇总, so that 我不需要手工从序时账逐笔统计每个客户的应收余额。

#### Acceptance Criteria

1. THE prefill_formula_mapping.json SHALL contain Detail_Sheet entries for D2 (应收账款) covering at least: 客户明细表、账龄分析表、坏账准备计算表
2. WHEN prefill is triggered for D2 Detail_Sheet "客户明细表", THE Prefill_Engine SHALL use =TB_AUX('1122','客户','期末余额') formula type to populate per-customer balances
3. WHEN prefill is triggered for D2 Detail_Sheet "账龄分析表", THE Prefill_Engine SHALL use =TB_AUX('1122','账龄','期末余额') formula type to populate per-aging-bucket balances
4. THE prefill_formula_mapping.json SHALL contain Detail_Sheet entries for D1 (应收票据) covering: 票据明细表（按类型/到期日分类）
5. THE prefill_formula_mapping.json SHALL contain Detail_Sheet entries for D4 (营业收入) covering: 收入明细表（按产品/客户/地区分类）
6. IF auxiliary balance data is unavailable for a dimension, THEN THE Prefill_Engine SHALL leave the detail cells empty and log a warning "辅助余额数据缺失: {dimension}"

### Requirement 3: D 循环内部跨底稿引用

**User Story:** As a 审计师, I want D 循环内部底稿之间的数据引用关系自动建立, so that 修改 D2 审定数时系统能提示 D0 函证金额需要同步更新。

#### Acceptance Criteria

1. THE cross_wp_references.json SHALL contain references from D2 审定数 to D0 函证确认金额 (D2→D0)
2. THE cross_wp_references.json SHALL contain references from D4 营业收入审定数 to D2 应收账款周转率分析 (D4→D2 分析程序)
3. THE cross_wp_references.json SHALL contain references from D3 预收款项变动 to D4 收入确认分析 (D3→D4)
4. THE cross_wp_references.json SHALL contain references from D2 坏账准备 to D5 应收款项融资减值 (D2→D5)
5. WHEN a source cell value changes, THE system SHALL mark all target cells as stale via the existing stale propagation mechanism
6. THE cross_wp_references.json D-cycle internal references SHALL use category "revenue_cycle" and severity "warning"

### Requirement 4: D 循环→附注跨模块引用

**User Story:** As a 审计师, I want 在 D2 审定数单元格上看到"→ 附注 5.7 应收账款"标签, so that 我能快速确认底稿数据与附注披露一致。

#### Acceptance Criteria

1. THE cross_wp_references.json SHALL contain a reference from D2 审定数 to 附注 5.7 应收账款 (note_section target)
2. THE cross_wp_references.json SHALL contain a reference from D4 营业收入审定数 to 附注 5.14 营业收入 (note_section target)
3. THE cross_wp_references.json SHALL contain a reference from D1 应收票据审定数 to 附注 5.3 应收票据 (note_section target)
4. THE cross_wp_references.json SHALL contain a reference from D3 预收款项审定数 to 附注 5.15 合同负债/预收款项 (note_section target)
5. THE cross_wp_references.json SHALL contain a reference from D5 应收款项融资审定数 to 附注 5.5 应收款项融资 (note_section target)
6. THE cross_wp_references.json SHALL contain a reference from D6 合同资产审定数 to 附注 5.6 合同资产 (note_section target)
7. THE cross_wp_references.json SHALL contain a reference from D7 合同负债审定数 to 附注 5.15 合同负债 (note_section target)
8. WHEN a cross-module reference target is defined, THE reference entry SHALL include target_type "note_section" and a valid target_route for navigation

### Requirement 5: D 循环→报表跨模块引用

**User Story:** As a 审计师, I want 在 D2 审定数单元格上看到"→ 报表 BS-005"标签, so that 我能确认底稿审定数已正确流入资产负债表对应行次。

#### Acceptance Criteria

1. THE cross_wp_references.json SHALL contain a reference from D2 审定数 to 报表 BS-005 应收账款行 (report_row target)
2. THE cross_wp_references.json SHALL contain a reference from D4 营业收入审定数 to 报表 IS-001 营业收入行 (report_row target)
3. THE cross_wp_references.json SHALL contain a reference from D1 应收票据审定数 to 报表 BS-003 应收票据行 (report_row target)
4. THE cross_wp_references.json SHALL contain a reference from D3 预收款项审定数 to 报表 BS-034 预收款项行 (report_row target)
5. THE cross_wp_references.json SHALL contain a reference from D5 应收款项融资审定数 to 报表 BS-006 应收款项融资行 (report_row target)
6. THE cross_wp_references.json SHALL contain a reference from D6 合同资产审定数 to 报表 BS-007 合同资产行 (report_row target)
7. THE cross_wp_references.json SHALL contain a reference from D7 合同负债审定数 to 报表 BS-035 合同负债行 (report_row target)
8. WHEN a cross-module reference target is defined, THE reference entry SHALL include target_type "report_row" and the corresponding report_row_code

### Requirement 6: D 循环校验规则——借贷平衡

**User Story:** As a 复核人, I want 系统自动检查每个 D 底稿审定表的"审定数 = 未审数 + AJE + RJE"等式是否成立, so that 我能快速发现计算错误。

#### Acceptance Criteria

1. THE d_cycle_validation_rules.json SHALL define a "balance_check" rule for each D-cycle workpaper (D0-D7) verifying: 审定数 = 未审数 + AJE调整 + RJE调整
2. WHEN the balance_check rule is evaluated, THE Validation_Rule SHALL compare the computed sum against the 审定数 cell value with a tolerance of 0.01 (rounding)
3. IF the balance_check fails, THEN THE Validation_Rule SHALL produce a finding with severity "blocking" and message "借贷不平衡: 审定数({actual}) ≠ 未审数({unaudited}) + AJE({aje}) + RJE({rje}), 差异={diff}"
4. THE balance_check rule SHALL apply to every account line in the 审定表 (not just the total row)

### Requirement 7: D 循环校验规则——与试算表一致

**User Story:** As a 复核人, I want 系统自动检查 D 底稿审定数与试算平衡表对应科目期末余额是否一致, so that 我能确认底稿数据与全局试算表同步。

#### Acceptance Criteria

1. THE d_cycle_validation_rules.json SHALL define a "tb_consistency" rule for each D-cycle workpaper verifying: 审定数 = TB(account_code, '审定数')
2. WHEN the tb_consistency rule is evaluated, THE Validation_Rule SHALL query the trial_balance for the matching standard_account_code and compare with the workpaper 审定数
3. IF the tb_consistency check fails, THEN THE Validation_Rule SHALL produce a finding with severity "blocking" and message "与试算表不一致: 底稿审定数({wp_amount}) ≠ TB审定数({tb_amount}), 差异={diff}"
4. THE tb_consistency rule SHALL use the same account_codes defined in prefill_formula_mapping.json for each D workpaper

### Requirement 8: D 循环校验规则——与附注一致

**User Story:** As a 复核人, I want 系统自动检查 D 底稿审定数与对应附注章节合计金额是否一致, so that 我能确认底稿数据与附注披露同步。

#### Acceptance Criteria

1. THE d_cycle_validation_rules.json SHALL define a "note_consistency" rule for D2 verifying: D2 审定数 = 附注 5.7 应收账款合计
2. THE d_cycle_validation_rules.json SHALL define a "note_consistency" rule for D4 verifying: D4 审定数 = 附注 5.14 营业收入合计
3. THE d_cycle_validation_rules.json SHALL define a "note_consistency" rule for D1 verifying: D1 审定数 = 附注 5.3 应收票据合计
4. IF the note_consistency check fails, THEN THE Validation_Rule SHALL produce a finding with severity "warning" and message "与附注不一致: 底稿审定数({wp_amount}) ≠ 附注合计({note_amount}), 差异={diff}"
5. IF the target note section does not exist (not yet generated), THEN THE Validation_Rule SHALL skip the check and produce an info-level finding "附注章节未生成，跳过一致性校验"

### Requirement 9: D 循环校验规则——明细表合计校验

**User Story:** As a 复核人, I want 系统自动检查 D2 客户明细表合计是否等于审定表余额, so that 我能确认明细表没有遗漏或重复。

#### Acceptance Criteria

1. THE d_cycle_validation_rules.json SHALL define a "detail_total_check" rule for D2 verifying: SUM(客户明细表各行) = 审定表审定数
2. THE d_cycle_validation_rules.json SHALL define a "aging_total_check" rule for D2 verifying: SUM(账龄分析表各段) = 审定表审定数
3. IF the detail_total_check fails, THEN THE Validation_Rule SHALL produce a finding with severity "blocking" and message "明细表合计({detail_sum}) ≠ 审定数({audited}), 差异={diff}"
4. THE detail_total_check and aging_total_check rules SHALL allow a tolerance of 0.01 for rounding differences

### Requirement 10: D 循环审计程序清单

**User Story:** As a 审计师, I want 打开 D2 底稿时看到预定义的审计程序步骤清单, so that 我能按标准流程逐步执行审计工作并记录完成状态。

#### Acceptance Criteria

1. THE d_cycle_procedures.json SHALL define procedure steps for D2 (应收账款) including at minimum: 获取明细→核对总账→函证→替代程序→坏账准备→截止测试→结论
2. THE d_cycle_procedures.json SHALL define procedure steps for D4 (营业收入) including at minimum: 获取收入明细→分析程序→截止测试→收入确认→关联方交易→结论
3. THE d_cycle_procedures.json SHALL define procedure steps for D0 (函证) including at minimum: 确定函证范围→编制函证→发函→回函统计→替代程序→差异调查→结论
4. THE d_cycle_procedures.json SHALL define procedure steps for each remaining D-cycle workpaper (D1/D3/D5/D6/D7) with at least 5 steps each
5. WHEN a procedure step is defined, THE entry SHALL include: step_order, step_name, description, is_required (boolean), and related_sheet (optional link to workpaper sheet)
6. THE procedure steps SHALL follow the order defined in 致同 2025 修订版审计程序模板

### Requirement 11: D5 应收款项融资特殊公式

**User Story:** As a 审计师, I want D5 应收款项融资底稿自动区分"以公允价值计量"和"以摊余成本计量"两类, so that 分类汇总与附注披露口径一致。

#### Acceptance Criteria

1. THE prefill_formula_mapping.json D5 entry SHALL include sub-account level formulas for 1124 (应收款项融资) split by measurement basis where applicable
2. WHEN the client's chart of accounts has sub-accounts under 1124 (e.g. 112401 公允价值 / 112402 摊余成本), THE Prefill_Engine SHALL populate separate lines using =TB('112401',...) and =TB('112402',...)
3. IF no sub-accounts exist under 1124, THEN THE Prefill_Engine SHALL use the single =TB('1124',...) formula as currently defined

### Requirement 12: D0 函证特殊公式——函证覆盖率

**User Story:** As a 审计师, I want D0 函证底稿自动计算函证覆盖率（函证金额/应收账款审定数）, so that 我能快速判断函证范围是否充分。

#### Acceptance Criteria

1. THE prefill_formula_mapping.json D0 entry SHALL include a "函证覆盖率" formula cell referencing D2 审定数: =WP('D2','审定表D2-1','审定数')
2. THE prefill_formula_mapping.json D0 entry SHALL include a "函证金额合计" cell that sums all confirmed amounts from the 函证明细 sheet
3. WHEN both values are available, THE Univer workbook SHALL compute 覆盖率 = 函证金额合计 / D2审定数 via an internal Excel formula (not prefill)

