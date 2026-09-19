# Design Document

## Overview

本设计将四表库（tb_balance/trial_balance）数据自动提取到 H4 底稿的明细表、审定表 TB 核对、盘点覆盖率分母、以及 H4-5↔H2 跨底稿勾稽。架构复用平台已验证的范式（E1 四表取数/D cycle Tier B/report_account_mapping/h1CipH2Pull），不新造机制。

## Architecture

```
tb_balance (1605 叶子)
    │ get_active_filter + _is_leaf
    ▼
_build_h4_detail_prefill()  ←── 后端 render 策略纯函数
    │ html_data.detail_prefill
    ▼
GtH4EngineeringMaterials.onMounted
    │ Persist-First: H4-2-rows 空才种子
    ▼
useH4Detail (rows ref 填充)

report_account_mapping (BS行→科目码)
    │ resolve_report_line_account_codes(db, pid, row_code, fallback=['1605'])
    ▼
project_context.tb_source_codes + tb_values.eng_mat_1605_audited
    │
    ▼
H4TabAdjudication (TB核对行)

useH4CrossSheet.detailTotal
    │ inject/computed
    ▼
H4TabStocktakeCheck (覆盖率分母)

h4DisposalH2Pull.ts (纯前端)
    │ wp-id-by-code → checklist-responses → H2-2-rows
    ▼
H4TabDisposalCheck (勾稽面板)
```

## Components and Interfaces

### Backend: `_h4_engineering_materials.py` 扩展

**`_build_h4_detail_prefill(ctx)`** — 纯函数，从 tb_balance 1605 叶子提取明细种子行。

输入：`ctx.db`, `ctx.project_id`, `ctx.year`
输出：`list[dict]`，每项 = `{category, beginAmount, purchaseAmount, usageAmount, endAmount, accountCode, source}`

逻辑：
1. `get_active_filter(db, TbBalance.__table__, pid, year)` 取 active 行
2. 过滤 `account_code LIKE '1605%'`
3. 收集所有匹配码 → `_is_leaf` 只留叶子
4. 排除全零行（opening/debit/credit/closing 四字段 abs < 0.005）
5. category = account_name 最后一段（按 `-`/`_`/`·` 分割取末段；无分隔符用全名去 "工程物资" 前缀）
6. beginAmount = abs(opening_balance)，purchaseAmount = abs(debit_amount)，usageAmount = abs(credit_amount)，endAmount = abs(closing_balance)
7. source = 'tb_balance'

**`_resolve_h4_tb_source_codes(ctx)`** — 复用 `report_account_mapping.resolve_report_line_account_codes`。

输入：`ctx.db`, `ctx.project_id`
输出：`list[str]` 科目码（如 `['1605']` 或项目自定义）

逻辑：调 `resolve_report_line_account_codes(db, pid, 'BS-XXX', fallback=['1605'])`（BS 行 code 待查 report_config 工程物资对应行）

**灰度开关**：`config.py` 新增 `H4_FOUR_TABLE_EXTRACTION_ENABLED: bool = False`；render 函数读该值决定是否输出 `detail_prefill` + `tb_source_codes` + `h4_extraction_enabled`。

### Frontend: `h4DetailPrefill.ts` (新建纯函数)

**`buildH4DetailSeedRows(prefill, existingRows)`** — Persist-First 种子映射。

- `prefill` = 后端 `detail_prefill` 数组
- `existingRows` = 已有 `H4-2-rows`
- 返回：existingRows 非空 → 返回 null（不种子）；否则映射 prefill → H4DetailRow schema

### Frontend: `h4DisposalH2Pull.ts` (新建纯函数)

**`pullH2MaterialConsumption(projectId)`** — 跨底稿拉 H2 物资消耗。

1. `GET /api/custom-query/wp-id-by-code?project_id=&wp_code=H2` 解析 wp_id
2. `GET /api/workpapers/{wp_id}/checklist-responses` 找 `H2-2-rows`
3. 遍历行，筛 `disposalMethod === '领用工程物资'` 或 `source === '工程物资'` 的 `transferAmount`
4. 返回 `{h2Total, rows[]}`

**`buildH4H2Reconcile(h4UsageTotal, h2Total)`** — 纯函数计算差异。

### Frontend: H4TabStocktakeCheck 改造

覆盖率分母 `populationAmount`：优先手工 → 回退 `inject('h4CrossSheet').detailTotal`。

## Data Models

无新表/无迁移。所有数据存 `checklist_responses`（`H4-2-rows` JSON / 各汇总键）。

后端输出新增字段（additive，flag off 时不输出）：
- `html_data.detail_prefill: list[dict] | null`
- `project_context.tb_source_codes: list[str]`
- `project_context.h4_extraction_enabled: bool`

## Correctness Properties

### Property 1: Leaf-Only Seeding
**Validates: Requirements 1.1**

Given tb_balance contains both 1605 (parent) and 1605.01 (child), when detail_prefill is built, then only 1605.01 appears (parent excluded).

### Property 2: Zero-Balance Exclusion
**Validates: Requirements 1.2**

Given a leaf account 1605.03 with opening=0, debit=0, credit=0, closing=0, when detail_prefill is built, then 1605.03 is excluded.

### Property 3: Persist-First Guard
**Validates: Requirements 1.3**

Given H4-2-rows already has ≥1 row, when the frontend attempts seeding, then no rows are modified/replaced.

### Property 4: Rule-Mapping Fallback
**Validates: Requirements 2.1**

Given no project-level mapping for BS工程物资行, when TB reconciliation resolves codes, then fallback=['1605'] is used and audited_amount is correctly summed.

### Property 5: Coverage Denominator
**Validates: Requirements 3.1**

Given H4-2 detail rows sum to X, when H4-6 calculates coverage, then denominator = X (unless manually overridden).

### Property 6: H2 Pull Accuracy
**Validates: Requirements 4.1**

Given H2-2-rows contains 3 rows with transferAmount [100, 200, 50] for 工程物资, when reconcile is computed, then h2Total = 350.

### Property 7: Flag-Off Equivalence
**Validates: Requirements 5.1**

Given H4_FOUR_TABLE_EXTRACTION_ENABLED=False, when render executes, then output contains no detail_prefill key and no tb_source_codes.

### Property 8: Provenance Marker
**Validates: Requirements 1.4**

Given detail rows are seeded from tb_balance, when rows are inspected, then each seeded row has source='tb_balance'.

## Error Handling

- `_build_h4_detail_prefill` 整体 try/except：失败返回空列表 + logger.warning（fail-open 不阻断 render）
- `_resolve_h4_tb_source_codes` 失败返回 fallback `['1605']`
- `pullH2MaterialConsumption` 网络失败 → ElMessage.warning + 返回 null
- 零分母除法 → 显示 "—" 非 Infinity
- 灰度关时三处新逻辑全跳过（逐字节等价当前）

## Testing Strategy

- 后端：pytest `test_h4_detail_prefill.py`（P1/P2/P7/P8）+ `test_h4_tb_source_codes.py`（P4）
- 前端：vitest `h4DetailPrefill.spec.ts`（P3）+ `h4DisposalH2Pull.spec.ts`（P6）+ `h4StocktakeCoverage.spec.ts`（P5）
