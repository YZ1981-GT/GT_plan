# Design Document

## Overview

在调整分录明细行（`adjustment_entries`）新增一个可空列 `detail_account_code`，作为审计师原始选定的**明细/二级科目码**的载体。`standard_account_code`（一级标准码）语义、约束、所有下游（科目校验、试算表 recalc、报表、审定表带入）**完全不变**。明细码仅用于把调整分录**精确推送到底稿明细表**（前端 `useAdjustmentDetailPropagation` 匹配时优先用明细码，NULL 时回退现有一级前缀上卷 → 历史零回归）。

关键零影响事实（已核验代码）：`trial_balance_service` 的调整聚合从 **`adjustments` 头表**的 `account_code`（一级）`group_by` 得到（`recalc` 三处 `group_by(adj.c.account_code, adj.c.adjustment_type)`），**从不读 `adjustment_entries` 明细行**。因此在明细行表加列对 recalc/报表/审定是天然零影响。

本设计为纯增量（additive），无破坏性改动，灰度安全（列可空 + 迁移幂等 + schema 字段可选 + 前端 NULL 回退）。

## Architecture

```
导入模板(export-template, 已带二级明细909行)
        │ 审计师下拉选二级明细科目名称 → 填写导入
        ▼
_import_adjustments 解析每行
        ├─ standard_account_code = 归一到一级(不变，校验/recalc/报表用)   ← Req2.1
        └─ detail_account_code   = 原始二级明细码(新增，明细码≠一级时保留) ← Req2.2/2.3
        ▼
AdjustmentCreate.line_items[].detail_account_code (schema 可选)  ← Req1.2
        ▼
create_entry / update_entry → AdjustmentEntry.detail_account_code (新列) ← Req3
        ▼
_build_group_response / listAdjustments → line_items[].detail_account_code ← Req4
        ▼
前端 useAdjustmentDetailPropagation
        ├─ 有 detail_account_code → 精确匹配底稿明细行(精准推送)          ← Req5.2
        └─ NULL → 回退 standard_account_code 前缀上卷(历史零回归)          ← Req5.3

不受影响(读 adjustments 头表 account_code 或 standard_account_code 一级)：
  trial_balance recalc / report 生成 / 审定表带入(useAdjudicationAdjustmentPull) ← Req6
```

## Design Decisions

### 决策 1：新增列而非改 standard_account_code
`standard_account_code` 被科目校验（`_validate_account_codes` 只认 standard 一级）、recalc（按一级聚合）、报表取数硬依赖，必须保持一级。故新增独立可空列 `detail_account_code` 承载明细，一级码零变更 → 满足 Req6「不影响功能」的红线。备选（改 standard 为二级）会连锁破坏校验/recalc/报表，否决。

### 决策 2：明细码仅在「≠一级码」时存，否则 NULL
避免为「本就选一级科目」的行冗余存重复值。`detail_account_code IS NULL` 语义 = 「无更细的明细，按一级处理」，前端回退现有逻辑 → 历史数据（全 NULL）零回归（Req2.3/5.3/7.1）。

### 决策 3：前端匹配「优先明细码、回退一级」单点收敛
`accountMatches(rowStdCode, adjStdCode)` 保持不变（纯函数，仍供回退用）。在 `matchByAccount` 内新增：对每条调整明细行，`effectiveCode = detail_account_code || standard_account_code`，用 `accountMatches(rowStdCode, effectiveCode)` 判定。这样有明细码时精确匹配（`112201` 只配 `112201`/其子），无明细码时等价现状（Req5）。

### 决策 4：recalc 不读明细行 = 天然零影响，用契约测试锁定
不需要在 recalc 加任何 `origin`/明细过滤；只需 characterization 测试断言「加列前后 recalc 结果一致」+ 契约测试断言「recalc 聚合 SQL 仍 group_by adjustments.account_code，不引用 detail_account_code」（Req6.1/9）。

### 决策 5：导出汇总 additive
`_write_adj_sheet` 现有 7 列（编号/摘要/科目编码/科目名称/借方/贷方/来源）保持列顺序不变；`科目编码` 列可在有明细码时显示明细码（更贴近审计师所选），但**导入解析对该列的解析逻辑不变**（导入按「二级科目编码/科目编码」列 + 名称反查，已容错）。为最小风险，本 spec 导出汇总仅在 `_adj_to_dict`/line 序列化补 `detail_account_code` 供前端用，Excel 列不新增（Req4.2 additive）。

## Data Models

### adjustment_entries（新增列）
```
detail_account_code  VARCHAR  NULL   -- 审计师原始明细/二级科目码；NULL=按一级处理
```
- 迁移：`VNNN__add_adjustment_entry_detail_account_code.sql`（执行前 migration_status 复核最高号，当前最高 V125 → 用 V126）+ 幂等 `information_schema` 守护 + 回滚 `RNNN`。
- ORM：`AdjustmentEntry.detail_account_code: Mapped[str | None] = mapped_column(String, nullable=True)`。

### AdjustmentLineItem（schema，audit_platform_schemas.py）
```python
class AdjustmentLineItem(BaseModel):
    standard_account_code: str
    detail_account_code: str | None = None   # 新增，可选
    account_name: str | None = None
    report_line_code: str | None = None
    debit_amount: AmountDecimal = Decimal("0")
    credit_amount: AmountDecimal = Decimal("0")
```

## Components and Interfaces

### 后端
- `models/audit_platform_models.py::AdjustmentEntry` — 加列。
- `models/audit_platform_schemas.py::AdjustmentLineItem` — 加可选字段。
- `services/adjustment_service.py::create_entry`（~line 142）/`update_entry`（~line 284）— 写 `detail_account_code=li.detail_account_code`。
- `services/adjustment_service.py::_build_group_response`（~line 932）— 序列化 `detail_account_code`。
- `routers/import_templates.py::_import_adjustments` — 解析出原始明细码 `sub_code`（或名称反查的 client 二级码），当 `≠ 归一后一级码` 时放入 line_item `detail_account_code`；`standard_account_code` 归一逻辑不变。
- `routers/adjustments.py::export_adjustment_template` — 关注事项说明补明细码语义（Req8）；`_adj_to_dict` line 序列化补 `detail_account_code`（Req4）。

### 前端
- `composables/useAdjustmentDetailPropagation.ts` — `AdjustmentLineMatch` 加 `detail_account_code?`；`load()` 从 `li.detail_account_code` 读；`matchByAccount` 用 `effectiveCode = detail_account_code || standard_account_code`。
- `views/adjustments/handbooks/adjustments-module-handbook.md` — 补明细码说明（Req8）。
- （可选）各底稿 `syncToCentral` 的 `buildLineItems` 可在有明细科目上下文时带 `detail_account_code`；本 spec 不强制改各底稿（默认 NULL 回退，零回归），仅在 E1 等已知带明细的入口试点。

## Correctness Properties

### Property 1: 列可空默认 NULL
新建/导入不提供明细码 → `detail_account_code IS NULL`。
**Validates: Requirements 1.3, 2.3, 7.1**

### Property 2: 一级归一不变
对同一输入，`standard_account_code` 归一结果与加字段前逐字节一致。
**Validates: Requirements 2.1, 1.4**

### Property 3: 明细码保留
导入二级明细科目（明细码≠一级）→ `detail_account_code` = 原始明细码，`standard_account_code` = 一级码。
**Validates: Requirements 2.2**

### Property 4: 明细=一级时不冗余
选一级科目 → `detail_account_code IS NULL`。
**Validates: Requirements 2.3**

### Property 5: 校验只认一级
明细码非标准码不导致导入/创建失败；校验仅对 `standard_account_code`。
**Validates: Requirements 2.4, 6.4**

### Property 6: recalc 零影响
同批分录 recalc 前后 `aje_adjustment/rje_adjustment/audited_amount` 逐字节一致。
**Validates: Requirements 6.1, 6.2**

### Property 7: recalc 不读明细码
调整聚合 SQL 仅 `group_by adjustments.account_code`，不引用 `detail_account_code`（契约/源码断言）。
**Validates: Requirements 6.1**

### Property 8: 序列化含字段
分录组响应 line_items 含 `detail_account_code`（NULL→null）。
**Validates: Requirements 4.1, 4.3**

### Property 9: 前端优先明细码
调整行有明细码 → 明细表按明细码精确匹配（不再前缀上卷到全部同一级明细）。
**Validates: Requirements 5.2**

### Property 10: 前端 NULL 回退
调整行明细码 NULL → 匹配等价现有 `standard_account_code` 前缀上卷。
**Validates: Requirements 5.3, 5.4**

### Property 11: 迁移幂等
迁移重复应用不报错（列存在跳过）。
**Validates: Requirements 7.3**

### Property 12: 报表/审定不变
报表取数与审定表带入（按 standard 聚合）结果不变。
**Validates: Requirements 6.3**

## Error Handling
- 迁移用 `information_schema.columns` 守护（列已存在→跳过），幂等。
- 导入解析明细码提取失败/异常 → fallback 存 NULL（不阻断导入，退化为现有行为）。
- schema 字段可选，旧客户端不发 → NULL。
- 前端 `accountMatches` 空值仍返回 false（既有安全行为不变）。

## Testing Strategy
- **后端 characterization（Wave0）**：锁定「不提供明细码时」import 解析结果、recalc 结果、group_response 序列化的基线，防回归。
- **后端属性/单元**：P1-P8/P11/P12（import 明细码保留与归一不变、create/update 持久化、序列化、recalc parity、迁移幂等）。真实 PG16 或 SQLite 兼容夹具。
- **前端 vitest**：P9/P10（`matchByAccount` 优先明细码 + NULL 回退，`accountMatches` 空值安全）。
- **零回归门**：既有 `test_adjustments` / `test_adjustment_sync` / `test_trial_balance` 全绿。
- **Playwright（可选\*）**：导入带二级明细模板 → 分录 line_item 落 `detail_account_code` → 底稿明细表精确标注「受 N 笔调整影响」。需实例化项目，条件不满足则以 PBT + HTTP round-trip 覆盖。
