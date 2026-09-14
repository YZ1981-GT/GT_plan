# Design Document

## Overview

补齐既有 `NoteValidationEngine` 的两层缺口：①`validate_all` 完整装配 `ValidationContext`（report_data / tb_data / prior_year note）；②落地 6 个 stub executor 的真实审计校验。**加法式、只读不写、Skip 优于误报、fail-open**。框架/派发/持久化/findings/confirm/preset 加载/前端面板均已存在且工作，本 spec 只填 executor 与数据源。

## Architecture

```
NoteValidationEngine.validate_all(project_id, year, template_type)   ← 已存在，本 spec 增强数据装配
   │
   ├─ 装配 ValidationContext（本 spec 新增 report_data/tb_data/prior_year 加载）
   │     note_data      ← DisclosureNote(year)         [已有]
   │     report_data    ← report snapshot / FinancialReport 行次审定金额  [新增]
   │     tb_data        ← trial_balance audited_amount  [新增]
   │     prior_note_data← DisclosureNote(year-1)         [新增, 账龄衔接用]
   │     wp_data        ← 可选, 暂不装配（Skip_On_Missing 兼容）
   │
   └─ execute_all → 逐 rule → execute_rule → EXECUTORS[rule_type](rule, ctx)  [派发已有]
         ├─ balance / wide_table / vertical / sub_item   ← 已实现（装数据后生效）
         └─ cross / cross_account / secondary_detail /
            completeness / aging_progression / llm_review ← 本 spec 落地（当前 stub）
   │
   └─ _persist_results → findings → 前端 DisclosureEditor 校验面板  [已有, 自动显示]
```

### 架构决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 改动位置 | `note_validation_executors.py`（6 executor）+ `note_validation_engine.validate_all`（数据装配）| 最小侵入，不动框架/派发/持久化 |
| report_data 源 | 复用报表检索（report snapshot / FinancialReport 行次 current_period_amount，与 `useReportCrossCheck` 的 getReport 同源）| Req1.4 不新建 |
| tb_data 源 | `trial_balance.audited_amount` keyed by standard_account_code | 审定口径，与审定表回写一致 |
| 缺数据行为 | Skip_On_Missing（`passed=True`+`details.skipped=true`）| Req8.2 审计严谨，宁漏报不误报 |
| LLM 审核 | 复用 `chat_completion`（str+占位串判降级），fail-open | Req7.2/7.3 不阻断 |
| 容差 | 复用 `_resolve_tolerance`（金额规模自适应）| Req8.4 不硬编码 |
| 只读 | executor 绝不写 DB/ctx | Req8.1 校验不改数据 |

## Components and Interfaces

### 数据装配（`note_validation_engine.validate_all` 增强）

```python
context = ValidationContext(project_id=project_id, year=year)
# note_data（已有）
context.note_data = {n.note_section: n.table_data for n in current_notes ...}
# 新增：report_data — 报表行次审定金额（fail-open 缺失置空）
context.report_data = await self._load_report_data(project_id, year)   # {row_code: Decimal}
# 新增：tb_data — 试算表科目审定余额（fail-open）
context.tb_data = await self._load_tb_data(project_id, year)           # {account_code: Decimal}
# 新增：prior_note_data — 上年附注（账龄衔接用；挂 context 或独立字段）
context.prior_note_data = await self._load_prior_notes(project_id, year - 1)  # {section: table_data}
```

- `_load_report_data`：查报表快照/FinancialReport，行次 → current_period_amount（审定）。异常 → `{}`。
- `_load_tb_data`：`get_active_filter(TrialBalance)` 查审定余额，standard_account_code → audited_amount。异常 → `{}`。
- `_load_prior_notes`：DisclosureNote(year-1)。异常 → `{}`。
- `ValidationContext` 若无 `prior_note_data` 字段则新增（dataclass 加一个可选字段，向后兼容）。

### 6 个 executor 落地（`note_validation_executors.py`）

统一签名 `(rule: ValidationRule, ctx: ValidationContext) -> ValidationResult`，统一模式：取数 → 缺则 Skip_On_Missing → 比对 → 超容差产 finding。

1. **`_execute_completeness`**（Req2）：遍历 Completeness_Scope（有 TB 审定余额非零、且映射到应披露章节的科目），检查对应 note_section 是否存在且非空（table_data 有 rows/值 或 text_content 非空）。缺失 → finding「科目 X 有余额 N 但附注未披露」。`tb_data` 空 → skip。科目↔章节映射复用现有（mapping_service / note_section catalog）。
2. **`_execute_aging_progression`**（Req3）：定位账龄分桶表（按 aging_config 段）；校验 Σ分桶 = 总额；有 prior_note_data 则校验本年期初 = 上年期末。无账龄表/无上年/字段缺 → skip。
3. **`_execute_cross`**（Req4）：按 rule.expression 取附注章节合计 vs `report_data` 报表行（或另一 note 章节值）比对；引用缺失 → skip。
4. **`_execute_cross_account`**（Req5）：按 rule.expression 取两个科目章节值做勾稽比对；任一缺 → skip。
5. **`_execute_secondary_detail`**（Req6）：识别二级明细结构（父/子行或分组），Σ二级 = 一级；无结构 → skip。
6. **`_execute_llm_review`**（Req7）：取章节 text_content，构 prompt 调 `chat_completion` 审合理性（占位符残留/数字与表格矛盾/空泛），产 warning finding；LLM 占位串/异常 → skip（`passed=True`），context 值转 str。

规则来源：executor 实现 TYPE 级通用逻辑，具体 section/表达式由 preset.md（国企版/上市版校验公式预设.md）与内联 `_validation_rules` 提供（已有加载路径）。表达式解析若需要，复用 `execute_note_formulas` 的 REPORT()/NOTE()/cell 取数惯例。

### ValidationResult 与 findings（已有，不改）

executor 产出 `ValidationResult(passed, expected_value, actual_value, diff_amount, details)`；`validate_all` 把 `not passed` 转 findings（severity 按 diff）。`details.skipped=true` 时 `passed=True` 不进 findings。

## Data Models

不新增/不修改数据库表。

- `ValidationContext` 增加可选字段 `prior_note_data: dict[str, Any] = field(default_factory=dict)`（进程内 dataclass，向后兼容）。
- report_data/tb_data 为进程内 dict，来自现有表只读查询。
- 校验结果持久化沿用现有 `_persist_results`（NoteValidation 记录），不改 schema。

## Correctness Properties

### Property 1: 数据装配非空
WHEN 报表已生成且试算表有审定数 THEN validate_all 构造的 ctx.report_data 与 ctx.tb_data 非空（键为 row_code / account_code）。
**Validates: Requirements 1.1**

### Property 2: 数据源 fail-open
WHEN report/tb/prior 任一加载抛异常 THEN 对应源置 `{}` 且 validate_all 不抛、其余校验照常。
**Validates: Requirements 1.3**

### Property 3: 完整性 — 漏披露出 finding
GIVEN 科目有 TB 审定余额非零且映射到应披露章节 AND 该章节缺失/空 THEN _execute_completeness 产生 finding。
**Validates: Requirements 2.1, 2.2**

### Property 4: 完整性 — 缺 TB 数据 skip
WHEN ctx.tb_data 为空 THEN _execute_completeness `passed=True` 且 `details.skipped=true`，不产 finding。
**Validates: Requirements 2.3, 8.2**

### Property 5: 账龄分桶合计校验
GIVEN 账龄表 Σ分桶 ≠ 总额（超容差）THEN _execute_aging_progression 产生 finding；相等则 pass。
**Validates: Requirements 3.1**

### Property 6: 账龄期初=上年期末
GIVEN 有 prior_note_data AND 本年期初 ≠ 上年期末（超容差）THEN 产生 finding；无上年数据则该子校验 skip。
**Validates: Requirements 3.2, 3.3**

### Property 7: 交叉勾稽 — 附注↔报表
GIVEN 附注章节合计 ≠ report_data 对应行（超容差）THEN _execute_cross 产生 finding；引用缺失则 skip。
**Validates: Requirements 4.1, 4.2, 4.3**

### Property 8: 跨科目 / 二级明细缺结构 skip
WHEN 规则引用科目缺失（cross_account）或章节无二级明细结构（secondary_detail）THEN 对应 executor skip，不误报。
**Validates: Requirements 5.2, 6.2**

### Property 9: LLM 审核 fail-open
WHEN chat_completion 返回占位串/抛异常 THEN _execute_llm_review `passed=True`+skip 标注，不产误报、不抛。
**Validates: Requirements 7.2**

### Property 10: 只读不改数据
THE 任一 executor 执行前后 ctx.note_data / DB 附注数据不变（无写操作）。
**Validates: Requirements 8.1**

### Property 11: 异常不阻断
WHEN executor 内部抛异常 THEN execute_rule 捕获返回 `passed=True`，不阻断其余规则。
**Validates: Requirements 8.3**

### Property 12: 已实现 executor 装数据后回归
WHEN report_data 装配后 THEN _execute_balance 用真实报表行金额比对（非恒 0），4 个已实现 executor 行为回归正确。
**Validates: Requirements 9.5**

## Testing Strategy

- **单元/PBT**（`backend/tests/`）：6 executor 各 pass/fail/skip 三态；数据装配（report/tb/prior）；LLM fail-open；只读断言（执行前后 ctx 深比不变）；已实现 4 executor 装数据回归。`hypothesis` fast profile（max_examples=5）覆盖账龄分桶求和 / 完整性阈值 / 容差边界。
- **集成**（mock report/tb 查询 + mock chat_completion）：validate_all 端到端产 findings；缺数据源全 skip 不误报；异常源 fail-open。
- **契约**：`EXECUTORS` 仍覆盖全部 11 类型；`ValidationType` 枚举不变。
- **回归**：现有 note validation 测试全绿（`test_note_validation*`）。

## Error Handling

- 数据装配每源独立 try/except → 置 `{}` + 日志，不阻断。
- executor 内部异常由 `execute_rule` 现有 try/except 兜底（`passed=True`）。
- LLM 审核占位串（`[LLM.../⚠️...`）/异常 → skip。
- 缺数据源 → Skip_On_Missing（passed=True + details.skipped）。
- 只读：executor 不得调用任何写/flush/commit。
