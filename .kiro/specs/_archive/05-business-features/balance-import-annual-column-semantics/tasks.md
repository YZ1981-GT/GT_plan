# Implementation Plan

## Overview

按依赖分 6 波：Wave0 建安全网（锁定当前行为，防回归漂移）→ Wave1 识别层区分年度/月度 → Wave2 分类层+替代守卫 → Wave3 转换层年度优先 → Wave4 SubmitGate 变体 → Wave5 全量回归+验证。每个实现任务配对应属性/单测。改动的是全平台余额表落库金额与识别，故先安全网、后逐层、最后全量回归。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 0, "tasks": ["1.1", "1.2"], "depends_on": [] },
    { "wave": 1, "tasks": ["2.1", "2.2", "2.3"], "depends_on": [0] },
    { "wave": 2, "tasks": ["3.1", "3.2", "3.3"], "depends_on": [0] },
    { "wave": 3, "tasks": ["4.1", "4.2"], "depends_on": [0] },
    { "wave": 4, "tasks": ["5.1", "5.2"], "depends_on": [0] },
    { "wave": 5, "tasks": ["6.1", "6.2"], "depends_on": [1, 2, 3, 4] }
  ]
}
```

## Tasks

- [x] 1. Wave0 — 安全网与基线
- [x] 1.1 建立 converter 当前行为 characterization 基线
  - 在 `backend/tests/ledger_import/test_balance_annual_semantics.py` 新建测试文件，记录变更前 `convert_balance_rows` 对"仅月度列"输入的输出（opening_balance/debit_amount/credit_amount/closing_balance），作为 Wave3 月度兜底等价的对照锚点
  - 记录当前 `_match_merged_header` 对 年初余额.借方金额 / 本年累计.借方金额 的输出（现为 opening_debit / debit_amount），标注"变更后应变为 year_*"
  - _Requirements: 5.1, 5.3_
- [x] 1.2 冻结映射/分类真源清单
  - 在测试文件中以常量列出：三个映射点（A identifier `_MERGED_HEADER_MAPPING` / B JSON `column_aliases` / C legacy `_MERGED_HEADER_MAP` 参照）、KEY/RECOMMENDED 期望集合、SubmitGate 期望 critical 组合，供后续波次断言引用
  - _Requirements: 1.1, 2.1, 2.5_

- [x] 2. Wave1 — 识别层区分年度/月度
- [x] 2.1 修 identifier `_MERGED_HEADER_MAPPING`（点号合并表头）
  - `年初余额` → year_opening_debit/year_opening_credit（_default 保 opening_balance）；`本年累计`/`累计发生额` → year_debit/year_credit；期初/本期/期末保持不变
  - 对齐 `smart_import_engine._MERGED_HEADER_MAP` 的年度映射
  - _Requirements: 1.6, 1.7, 1.8_
- [x] 2.2 拆分 JSON `column_aliases`（单行表头）
  - 新增 year_opening_debit/credit、year_debit/credit 别名；从 opening_debit/credit/opening_balance 移除「年初*」；debit_amount/credit_amount 收窄为本期/发生额语义
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_
- [x] 2.3 映射层单测（Property 8、9、13）
  - `_match_merged_header` 点号用例（Property 8）；`reload_rules`/`_rebuild_aliases` 后 `_match_header` 单行别名用例（Property 9）——年初/期初/本年累计/本期/期末各自映射正确
  - `_match_merged_header("年初余额.金额")`（点号形式 + sub 非借贷子列，命中 `_default`）返回 `opening_balance`（Property 13，锁定 R1.8 边界；裸 `年初余额` 无 `.` 返回 None）
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.7, 1.8, 6.4_

- [x] 3. Wave2 — 分类层 + 替代守卫
- [x] 3.1 修 `detection_types.py` KEY_COLUMNS/RECOMMENDED_COLUMNS["balance"]
  - KEY = {account_code, year_opening_debit, year_opening_credit, year_debit, year_credit, closing_balance}；RECOMMENDED 增 opening_balance/opening_debit/opening_credit/debit_amount/credit_amount（期末分列 closing_debit/credit 留 RECOMMENDED，由 3.2 组合替代提升）
  - _Requirements: 2.1, 2.2_
- [x] 3.2 修 identifier `_BUILTIN_ALTERNATIVES` + `_alt_to_key` 提升守卫
  - 加年度→月度单字段替代（year_opening_debit←opening_debit 等）；`_alt_to_key` 构建加 `if "+" not in alt_group: continue`，仅组合型（closing_debit+closing_credit）提升为 key
  - _Requirements: 3.1, 3.2, 3.4_
- [x] 3.3 分类/识别单测（Property 5、6、7）
  - 同时含年度+月度列时 tier 正确（年度=key、月度=recommended，Property 5）；仅月度列仍识别为 balance + key 覆盖满足（Property 6）；单字段替代不提升 opening_debit、组合型提升 closing 分列（Property 7）
  - _Requirements: 2.3, 2.4, 3.2, 3.3, 3.4, 6.4, 6.5_

- [x] 4. Wave3 — 转换层年度优先
- [x] 4.1 修 `converter.py::convert_balance_rows` + legacy `smart_import_engine.py::convert_balance_rows`
  - 期初：year_opening_debit/credit 优先（显式 `is None` 判断保 Decimal(0)），缺失用 opening_debit/credit，再用 opening_balance 净额；发生额：year_debit/credit 优先，缺失用 debit_amount/credit_amount；期末不变。两处同步改。
  - **穿透断言**：加测试确认 `year_debit`/`year_credit`/`year_opening_debit`/`year_opening_credit` 标准字段键能穿过映射管线（prepare_rows_with_raw_extra 按 column_mapping 落键）进入 converter 的 row dict（现有 converter 已 `row.get("year_opening_debit")` 作兜底，证明 year_opening_* 到达；本任务补断言 year_debit 同样到达）
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_
- [x] 4.2 转换器 PBT（Property 1-4、11）+ 等价性
  - hypothesis（max_examples=5）：年初=期初&本年累计=本期→与月度-only 等价（Property 1、对齐 1.1 基线）；年初≠期初→opening 由年初派生（Property 2）；本年累计≠本期→发生额由本年累计派生（Property 3）；仅月度→月度兜底（Property 4）；期末不变（Property 11）
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 5.1, 6.1, 6.2, 6.3_

- [x] 5. Wave4 — SubmitGate 变体
- [x] 5.1 修 `submit_gate.py::CRITICAL_COLUMNS["balance"]`
  - 补 {account_code, year_opening_debit, year_opening_credit} / {account_code, closing_debit, closing_credit} / {account_code, year_debit, year_credit}；保留原三组合
  - _Requirements: 2.5, 5.2_
- [x] 5.2 SubmitGate 单测（Property 10）
  - 年度分列/期末分列/本年累计分列文件各通过（不抛 missing_critical_columns）；原三组合仍通过
  - _Requirements: 2.5, 5.2_

- [x] 6. Wave5 — 全量回归与验证
- [x] 6.1 全量回归 `backend/tests/ledger_import/`
  - `python -m pytest backend/tests/ledger_import/` = 707 passed / 22 skipped / 0 failed（含新增 test_balance_annual_semantics.py 62 项）。对因新语义需更新断言的用例逐一核实并更新（test_validator/test_identifier/test_finding_explanation/test_column_mapping_history_reuse，均为 debit_amount/opening_balance 月度列 key→recommended 的合法语义变更，非放宽/跳过）。`test_import_engine.py` 18 项失败经 git stash 验证为 pre-existing（BasicInfoSchema 项目设置 schema drift，与本 spec 无关）。`py_compile` 全部改动 .py OK。
  - _Requirements: 5.3, 5.4, 6.5_
- [x] 6.2 契约守卫与文档收尾
  - 契约守卫 `test_three_mapping_sources_year_month_consistent`：identifier `_MERGED_HEADER_MAPPING` / JSON `column_aliases`（经 `_match_header`）/ legacy `_MERGED_HEADER_MAP` 三源对年初→year_opening、本年累计→year_debit 口径一致；更新 INDEX.md + memory 记录范式
  - _Requirements: 1.6, 5.4_

- [x] 6.3* Wave5 可选 — 前端 AccountImportStep.vue 分类标签对齐（组件 G）
  - `_KEY_FIELDS_BY_TYPE["balance"]` 增 year_debit/year_credit；`_IMPORTANT_FIELDS_BY_TYPE["balance"]` 增 opening_balance/opening_debit/opening_credit/debit_amount/credit_amount；`hasDebit`/`hasCredit` 发生额校验扩为也认 year_debit/year_credit
  - 不改硬性 required（保持 account_code），不影响落库；仅前端标签/提示一致性。改后 `curl.exe` 验 Vite transform 200
  - 不做无数据风险（后端落库已由 4.1 覆盖），故列为可选
  - _Requirements: 2.6_

- [ ]* 7. Wave5 可选 — Playwright 端到端（需实例化项目 + 含年度列的余额表样本）—— 诚实留待
  - 账套导入上传含 年初/本年累计/期末 的余额表 → 列映射「关键列（必填）」显示年度列、期初/本期在「次关键列」→ 确认导入 → trial_balance 期初=年初、发生额=本年累计
  - 条件（含年度/月度双列的真实余额表样本 + 实例化项目 + 浏览器流）不满足，故按其定义如实留待；等价覆盖已由 4.2 PBT（等价性/年度优先/月度兜底）+ Wave1-4 单测 + 6.1 全量回归提供
  - _Requirements: 6.1, 6.2, 6.4_

## Notes

- 波次内任务可并行；Wave1/2/3/4 互不依赖（都只依赖 Wave0 安全网），Wave5 依赖全部实现完成。
- Decimal(0) 与 None 必须显式区分（取数优先级不用 `or`）——0 是合法余额/发生额。
- 前端 `ColumnMappingEditor.vue::availableStandardFields`（year_*/company_code）本轮已补，不在本 spec 任务内。
- Legacy `smart_import_engine.convert_balance_rows` 必须与 v2 同步改（4.1），避免 feature flag 两路径口径分叉。
- 零回归红线：整年单期导出落库数值不变；仅月度列文件不被误阻断；不改 trial_balance 表结构/序时账/下游契约。
