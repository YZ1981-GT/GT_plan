# Requirements Document

## Introduction

附注复盘"维度 4（公式管理校验公式）"的精确落地。**关键纠偏**：复盘初判"附注专属校验很少"是调查不全——实测 `NoteValidationEngine`（`note_validation_engine.py` + `note_validation_executors.py`）已有完整校验框架：11 种校验类型枚举、preset.md 规则加载（国企版/上市版）、内联 `_validation_rules`/`check_presets` 触发、`validate_all`→`execute_all`→`_persist_results`→findings→`confirm_finding`、互斥逻辑、容差解析；前端 `DisclosureEditor` 已有"校验结果"面板消费 findings（`validateDisclosureNotes`/`getValidationResults`）。

**真实缺口（实测确认，两层）**：

1. **数据装配缺口**：`validate_all` 只把 `note_data`（附注表格）装进 `ValidationContext`，**不加载 `report_data`（报表行金额）/`tb_data`（试算表审定余额）/`wp_data`（底稿）**。→ 连已实现的余额校验 `_execute_balance`（读 `ctx.report_data`）都在跟空 dict 比、恒 `expected=0`、形同虚设。
2. **6 个 executor 是 stub**（返回 `passed=True` 假通过、不做实际校验）：
   - `_execute_cross`（交叉勾稽：附注↔报表 / 附注↔附注）
   - `_execute_cross_account`（跨科目勾稽）
   - `_execute_secondary_detail`（二级明细汇总）
   - `_execute_completeness`（完整性：有 TB 审定余额的科目必须有对应附注章节）
   - `_execute_aging_progression`（账龄衔接：分桶合计=总额 / 本年期初=上年期末）
   - `_execute_llm_review`（LLM 文本合理性审核，当前 "LLM not invoked"）
   - `_execute_description`（描述类兜底 skip，合理，非缺口）

**已实现的 4 个真 executor**（本 spec 不重写，仅确保数据装配后生效）：`_execute_balance` / `_execute_wide_table`（期初+增−减=期末）/ `_execute_vertical`（明细之和=合计）/ `_execute_sub_item`（其中项）。

本 spec 目标：补齐 `ValidationContext` 数据装配 + 落地 6 个 stub executor 的真实审计校验逻辑，让附注校验从"框架空转"变为"真正勾稽出错报"。**审计严谨铁律**：数据源缺失时 skip（不产生 false fail），仅在有可比数据且确实不平时报 finding。

**范围边界**：不改校验框架/派发/持久化/findings/confirm/preset 加载/前端面板（均已存在且工作）；不改 4 个已实现 executor 的语义；不碰知识库+AI 增强（维度 2，另一 spec 已做）、`resolve_formula` 表内公式（维度 3，后续 spec）、`_sub_table_columns` 覆盖率。纯后端（前端面板已消费 findings，产出真实 findings 后自动显示）。

## Glossary

| 术语 | 含义 |
|------|------|
| ValidationContext | 校验上下文 dataclass：`note_data`(section→table_data) / `tb_data`(account_code→审定余额) / `report_data`(row_code→金额) / `wp_data`(wp_code→parsed_data) |
| Executor | `(ValidationRule, ValidationContext) → ValidationResult` 纯函数，经 `EXECUTORS[rule_type]` 派发（`note_validation_executors.py`）|
| Stub_Executor | 当前返回 `passed=True` 假通过、无实际校验的 executor（6 个）|
| Skip_On_Missing | 审计严谨原则：所需数据源缺失时 executor 返回 `passed=True` 且 `details.skipped=true`（不产生 false fail），区别于"确有数据且不平"的真 finding |
| Prior_Year_Note | 上年（year-1）附注表格数据，账龄衔接校验"本年期初=上年期末"所需 |
| Completeness_Scope | 完整性校验的科目范围：有 TB 审定余额（非零）且业务上应披露的科目 → 必须有非空对应附注章节 |
| Aging_Buckets | 账龄分桶（1年以内/1-2年/2-3年/3-5年/5年以上，随项目 aging_config 可配）|
| Report_Data_Source | `report_data` 的来源：已生成的报表快照 / FinancialReport 的行次审定金额（design 定权威源）|

## Requirements

### Requirement 1: ValidationContext 完整数据装配

**User Story:** 作为质量控制复核合伙人，我要求附注校验运行时能拿到报表、试算表、上年附注数据，否则勾稽校验只是空跑。

#### Acceptance Criteria

1. WHEN `validate_all` 构造 `ValidationContext` THEN 系统 SHALL 在加载 `note_data` 之外，装配 `report_data`（报表行次金额，来自 Report_Data_Source）与 `tb_data`（试算表科目审定余额）。
2. WHERE 账龄衔接校验需要上年数据 THE 系统 SHALL 装配 Prior_Year_Note（year-1 附注表格）供比对。
3. WHEN 某数据源加载失败（DB 异常/报表未生成）THEN 系统 SHALL fail-open（该源置空 + 日志），不阻断整体校验，依赖该源的 executor 走 Skip_On_Missing。
4. THE 数据装配 SHALL 复用现有查询（trial_balance 审定 / report snapshot / DisclosureNote），不新建数据表。

### Requirement 2: 完整性校验（附注↔底稿/TB）

**User Story:** 作为审计助理，我希望系统提示"有余额但漏披露"的科目，避免附注遗漏。

#### Acceptance Criteria

1. WHEN 执行 `_execute_completeness` THEN 系统 SHALL 对 Completeness_Scope 内每个有 TB 审定余额（非零）的科目，检查是否存在对应且非空的附注章节。
2. WHEN 某应披露科目有余额但无对应附注章节（或章节存在但表格/正文皆空）THEN 系统 SHALL 产生 finding（漏披露）。
3. WHERE `tb_data` 为空（未装配/试算表缺失）THE 系统 SHALL Skip_On_Missing，不误报。
4. THE 科目↔附注章节映射 SHALL 复用现有映射（mapping_service / account_package / note_section catalog），不臆造映射。

### Requirement 3: 账龄衔接校验

**User Story:** 作为审计助理，我希望账龄表的分桶合计与总额一致、且本年期初等于上年期末。

#### Acceptance Criteria

1. WHEN 执行 `_execute_aging_progression` 且章节含账龄分桶表 THEN 系统 SHALL 校验各 Aging_Buckets 金额之和 = 该行/该表总额（容差内）。
2. WHERE 存在 Prior_Year_Note THE 系统 SHALL 校验本年账龄表"期初"值 = 上年"期末"值（衔接一致）。
3. WHERE 无账龄表 / 无上年数据 / aging 字段缺失 THE 系统 SHALL Skip_On_Missing，不误报。
4. THE Aging_Buckets 段 SHALL 尊重项目 aging_config（段可配），不硬编码固定 5 段。

### Requirement 4: 交叉勾稽（附注↔报表 / 附注↔附注）

**User Story:** 作为审计助理，我希望附注明细表合计与报表对应行、及相关附注章节间数据一致。

#### Acceptance Criteria

1. WHEN 执行 `_execute_cross` THEN 系统 SHALL 按规则表达式校验附注章节合计与 `report_data` 对应报表行次金额一致（容差内），或两个关联附注章节间的勾稽关系。
2. WHEN 存在差异超容差 THEN 系统 SHALL 产生 finding（含 expected/actual/diff）。
3. WHERE 引用的报表行/关联章节数据缺失 THE 系统 SHALL Skip_On_Missing。
4. THE 跨表引用 SHALL 复用现有 REPORT/NOTE 寻址口径（与 `execute_note_formulas` 的 REPORT()/NOTE() 一致），不新建寻址。

### Requirement 5: 跨科目勾稽

**User Story:** 作为审计助理，我希望不同科目附注间的勾稽关系（如往来对冲、关联方一致）被校验。

#### Acceptance Criteria

1. WHEN 执行 `_execute_cross_account` THEN 系统 SHALL 按规则表达式校验不同科目附注章节间的金额勾稽关系（容差内）。
2. WHERE 规则引用的任一科目附注数据缺失 THE 系统 SHALL Skip_On_Missing。
3. WHEN 勾稽不平超容差 THEN 系统 SHALL 产生 finding。

### Requirement 6: 二级明细汇总校验

**User Story:** 作为审计助理，我希望附注二级明细行汇总等于对应一级项目金额。

#### Acceptance Criteria

1. WHEN 执行 `_execute_secondary_detail` 且章节含二级明细结构 THEN 系统 SHALL 校验各二级明细汇总 = 对应一级项目金额（容差内）。
2. WHERE 章节无二级明细结构 THE 系统 SHALL Skip_On_Missing。
3. WHEN 二级明细汇总与一级不平超容差 THEN 系统 SHALL 产生 finding。

### Requirement 7: LLM 文本合理性审核

**User Story:** 作为现场经理，我希望对附注文字做一次 AI 合理性初审（如数字与表格明显矛盾、表述空泛/占位符残留），但不因 AI 不可用而阻断。

#### Acceptance Criteria

1. WHEN 执行 `_execute_llm_review` 且章节有正文文本 THEN 系统 SHALL 调用 LLM 对文本做合理性审核，产出 warning 级 finding（提示性，非阻断）。
2. WHEN LLM 不可用/超时/返回占位串 THEN 系统 SHALL fail-open（`passed=True` + Skip_On_Missing 标注），不产生误报、不抛异常。
3. THE LLM 审核 SHALL 复用现有 `chat_completion`（返回 str，占位串判降级），context 传值转字符串。
4. THE LLM finding SHALL 明确标为 AI 提示（非权威），不改任何附注数据。

### Requirement 8: 审计严谨 — Skip 优于误报 + 不改数据

**User Story:** 作为质量控制复核合伙人，我要求校验只读不写、且宁可漏报（skip）不可误报（false fail），避免审计师被噪声淹没。

#### Acceptance Criteria

1. THE 所有 executor SHALL 只读 `ValidationContext`，绝不修改任何附注/报表/试算表数据。
2. WHEN 所需数据源缺失或结构不匹配 THEN executor SHALL Skip_On_Missing（`passed=True` + `details.skipped=true`），不产生 finding。
3. WHEN executor 内部异常 THEN 系统 SHALL 捕获并 `passed=True`（不阻断，沿用现有 `execute_rule` try/except 语义）。
4. THE 容差 SHALL 复用现有 `_resolve_tolerance`（按金额规模自适应），不硬编码绝对阈值。

### Requirement 9: 正确性属性与可测

**User Story:** 作为质量控制复核合伙人，我要求每个新校验有 pass/fail/skip 三态测试守卫，防回归。

#### Acceptance Criteria

1. THE 每个新落地 executor SHALL 有 pass（平衡）/ fail（不平出 finding）/ skip（缺数据不误报）三态测试。
2. THE ValidationContext 数据装配（report_data/tb_data/prior_year）SHALL 有测试守卫。
3. THE LLM 审核 fail-open（不可用不误报不抛）SHALL 有测试守卫。
4. THE "executor 只读不改数据" SHALL 有测试守卫。
5. THE 已实现 4 executor（balance/wide_table/vertical/sub_item）装配数据后仍正确 SHALL 有回归测试。
