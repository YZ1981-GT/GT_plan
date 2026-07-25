# Implementation Plan

## Overview

补齐既有 `NoteValidationEngine`：先补 `ValidationContext` 数据装配（report/tb/prior），再逐个落地 6 个 stub executor（完整性/账龄衔接/交叉/跨科目/二级明细/LLM 审核），最后全量测试门。纯后端、只读不写、Skip 优于误报、fail-open。每波先补三态测试（pass/fail/skip）再改主代码；不动框架/派发/持久化/前端面板。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 0, "tasks": ["1", "2"], "desc": "安全网 characterization + 数据装配" },
    { "wave": 1, "tasks": ["3", "4"], "desc": "完整性 + 账龄衔接 executor" },
    { "wave": 2, "tasks": ["5", "6"], "desc": "交叉 + 跨科目 executor" },
    { "wave": 3, "tasks": ["7", "8"], "desc": "二级明细 + LLM 审核 executor" },
    { "wave": 4, "tasks": ["9"], "desc": "集成 + 全量测试门 + 回归" }
  ]
}
```

## Tasks

- [x] 1. 零回归安全网 + 数据源核实
  - 为现有 4 个真 executor（balance/wide_table/vertical/sub_item）+ `validate_all` 现状补 characterization 测试，锁定接入前行为
  - readCode 核实 report_data 权威源（report snapshot / FinancialReport 行次审定金额，与 useReportCrossCheck 的 getReport 同源）+ tb_data 审定字段（trial_balance.audited_amount + get_active_filter）+ 科目↔note_section 映射真源（mapping_service / note_section catalog）；结论写入报告
  - _需求：9.5_ _属性：Property 12_

- [x] 2. ValidationContext 数据装配
  - `note_validation_engine.validate_all` 增 `_load_report_data`(row_code→审定金额) / `_load_tb_data`(account_code→审定余额) / `_load_prior_notes`(year-1 附注)；每源独立 try/except fail-open 置 `{}`
  - `ValidationContext` 增可选字段 `prior_note_data`（dataclass 向后兼容）
  - 复用现有查询不新建表；只读
  - _需求：1.1, 1.2, 1.3, 1.4_ _属性：Property 1, 2_
  - 测试：装配非空(P1)、单源异常 fail-open(P2)、已实现 balance 装 report_data 后用真实行金额比对(P12)

- [x] 3. 完整性校验 executor
  - 落地 `_execute_completeness`：Completeness_Scope 内有 TB 审定余额非零且映射到应披露章节的科目 → 检查对应 note_section 存在且非空；缺则 finding；`tb_data` 空 → Skip_On_Missing；映射复用现有真源
  - _需求：2.1, 2.2, 2.3, 2.4, 8.1, 8.2_ _属性：Property 3, 4, 10_
  - 测试：漏披露出 finding(P3)、缺 TB skip(P4)、只读(P10)

- [x] 4. 账龄衔接校验 executor
  - 落地 `_execute_aging_progression`：Σ账龄分桶 = 总额（容差内）；有 prior_note_data 则本年期初 = 上年期末；无账龄表/无上年/字段缺 → skip；段尊重 aging_config
  - _需求：3.1, 3.2, 3.3, 3.4, 8.2_ _属性：Property 5, 6_
  - 测试：分桶合计不平出 finding(P5)、期初≠上年期末出 finding/无上年 skip(P6)、无账龄表 skip

- [x] 5. 交叉勾稽 executor（附注↔报表 / 附注↔附注）
  - 落地 `_execute_cross`：按 rule.expression 取附注章节合计 vs report_data 报表行（或关联章节值）比对，超容差 finding；引用缺失 skip；跨表口径复用 REPORT()/NOTE() 惯例
  - _需求：4.1, 4.2, 4.3, 4.4, 8.2_ _属性：Property 7_
  - 测试：附注↔报表不平出 finding(P7)、引用缺失 skip

- [x] 6. 跨科目勾稽 executor
  - 落地 `_execute_cross_account`：按 rule.expression 取不同科目章节值做勾稽，超容差 finding；任一科目缺 skip
  - _需求：5.1, 5.2, 5.3, 8.2_ _属性：Property 8_
  - 测试：跨科目不平出 finding、缺科目 skip

- [x] 7. 二级明细汇总 executor
  - 落地 `_execute_secondary_detail`：识别二级明细结构（父/子行或分组），Σ二级 = 一级（容差内），超容差 finding；无结构 skip
  - _需求：6.1, 6.2, 6.3, 8.2_ _属性：Property 8_
  - 测试：二级汇总不平出 finding、无结构 skip

- [x] 8. LLM 文本合理性审核 executor
  - 落地 `_execute_llm_review`：取章节 text_content 调 `chat_completion` 审合理性（占位符残留/数字与表格矛盾/空泛）产 warning finding；占位串/异常/无正文 → skip(`passed=True`)；context 值转 str；标为 AI 提示不改数据
  - _需求：7.1, 7.2, 7.3, 7.4, 8.1_ _属性：Property 9, 10_
  - 测试：fail-open 不误报不抛(P9)、只读(P10)、有正文调 LLM 产 warning

- [x] 9. 集成 + 全量测试门 + 契约/回归
  - 集成测试：validate_all 端到端（mock report/tb 查询 + mock chat_completion）产 findings、缺数据源全 skip 不误报、异常源 fail-open
  - 契约：EXECUTORS 覆盖全 11 类型、ValidationType 枚举不变
  - 回归：现有 note validation 测试全绿；executor 异常不阻断(P11)
  - get_diagnostics 全清；断言 Property 1-12 有覆盖
  - _需求：8.3, 9.1, 9.2, 9.3, 9.4, 9.5_ _属性：Property 1-12_

## Notes

- **边界**：仅补 `NoteValidationEngine` 数据装配 + 6 stub executor。不改校验框架/派发（execute_rule/EXECUTORS）/持久化（_persist_results）/findings/confirm/preset 加载/互斥逻辑/前端校验面板（均已存在且工作）。不改 4 个已实现 executor 语义。不碰维度 2（知识库+AI，已完成）/维度 3（resolve_formula 表内公式）/`_sub_table_columns`。
- **不改数据表**：ValidationContext 仅进程内加 `prior_note_data` 可选字段；数据全来自现有表只读查询。
- **复用**：report 检索（getReport 同源）/trial_balance 审定/aging_config/mapping_service/note_section catalog/`chat_completion`/`_resolve_tolerance`（均不新建）。
- **审计铁律**：executor 只读不写；Skip 优于误报（缺数据 passed=True+details.skipped，不产 false fail）；LLM fail-open；容差自适应不硬编码。
- **前端零改动**：DisclosureEditor 校验面板已消费 findings，后端产真实 findings 后自动显示。
- **PBT**：fast profile（max_examples=5）。
