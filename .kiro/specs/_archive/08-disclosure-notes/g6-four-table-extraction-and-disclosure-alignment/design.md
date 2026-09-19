# Design Document

## Overview

G6 其他债权投资的四表取数与披露对齐，核心是把科目映射从三处互相矛盾的硬编码（1503/1510/1531）统一到 `report_config` 权威真源 `BS-022 = TB('1505','期末余额')`，接入共享四表库提取架构，重写公式预设，并确保披露表→附注同步链路的列结构与源模板一致。

## Architecture

### 科目映射单一真源链路

```
report_config (BS-022, 四准则: TB('1505','期末余额'))
  → resolve_report_line_account_codes(row_code='BS-022', applicable_standards)
  → ['1505'] (无备抵，G6 减值在 OCI 不冲减账面价值)
  → account_mapping 反解 ('1505' → 客户原始码 '1505'/'1505.xx')
  → tb_balance (1505% 叶子: opening/closing)
  → render 输出 {tb_values, adjudication_prefill, tb_source_codes}
  → 前端 g6AccountScope.ts 消费
```

### 共享件复用

| 共享件 | 作用 | G6 消费方式 |
|--------|------|-------------|
| `four_table/report_line_accounts.py` | 解析报表行公式到科目码 | `ReportLineAccountSpec(row_code='BS-022')` 无 provision（G6 无备抵行） |
| `four_table/leaf_aggregation.py` | 叶子口径聚合 | `select_leaves` + `aggregate_leaves` 按 1505 前缀 |
| `g6AccountScope.ts` (新建) | 前端科目单一真源 | 运行态取 render `tb_source_codes`，常量兜底 |

### G6 特殊性

- **无备抵科目**：CAS22 对 FVOCI-Debt 类金融资产的减值在 OCI 确认，不冲减资产负债表列示的账面价值 → `report_config` 只有 `BS-022 = TB('1505')`，无 `IMP-xxx`。
- **公允价值口径**：审定表 block1 是公允价值（主列），block2~5 是摊余成本分析口径 → 四表预填只做 block1。
- **全库余额为 0**：9 个项目 `1505` / `1503` 均为 0 → 四表取数不会产出数据，但链路必须正确（有新项目导入数据后即生效）。

## Components and Interfaces

### 后端改动

**文件**：`backend/app/routers/wp_render_strategies/_g6_other_bond_investment_main.py`

```python
# 改动点 1：科目常量
_G6_ACCOUNT_PREFIX = "1505"  # was "1503"

# 改动点 2：_fetch_tb_values 改用共享件
from app.services.four_table.leaf_aggregation import select_leaves, aggregate_leaves
from app.services.four_table.report_line_accounts import (
    ReportLineAccountSpec,
    resolve_report_line_account_codes,
)

_G6_ACCOUNT_SPEC = ReportLineAccountSpec(
    row_code="BS-022",
    fallback_standard_codes=("1505",),
    # 无 provision_row_code（G6 无备抵行）
)

async def _fetch_tb_values(ctx: RenderContext) -> dict:
    codes = await resolve_report_line_account_codes(
        ctx.db, _G6_ACCOUNT_SPEC, ctx.project_id, ctx.year, ctx.applicable_standards
    )
    if not codes:
        codes = list(_G6_ACCOUNT_SPEC.fallback_standard_codes)
    leaves = await select_leaves(ctx.db, ctx.project_id, ctx.year, codes)
    agg = aggregate_leaves(leaves)
    return {"opening": agg.opening, "closing": agg.closing}

# 改动点 3：新增 tb_source_codes 输出
async def _build_tb_source_codes(ctx, codes, resolved_from):
    return {
        "gross_standard": codes,
        "resolved_from": resolved_from,
    }
```

**文件**：`backend/data/prefill_formula_mapping.json`

审定表 G6-1 块 `account_codes: ["1505"]`，公式 `TB('1505',...)` / `ADJ('1505',...)` / `PREV('G6','审定表G6-1','审定数')`。

明细表 G6-2 块 `account_codes: ["1505"]`，删 2 条 AUX 硬编码，保留 `TB('1505','期初余额')` / `TB('1505','期末余额')` / `ADJ('1505',...)` / `PREV`。

### 前端新建

**文件**：`frontend/src/components/workpaper/composables/g6AccountScope.ts`

```typescript
export const G6_REPORT_ROW_CODE = 'BS-022'
export const G6_GROSS_FALLBACK_STANDARD = '1505'

export function g6GrossQueryCodes(tbSourceCodes?: { gross_standard?: string[] }): string[] {
  return tbSourceCodes?.gross_standard?.length
    ? tbSourceCodes.gross_standard
    : [G6_GROSS_FALLBACK_STANDARD]
}

export function g6AccountCode(tbSourceCodes?: { gross_standard?: string[] }): string {
  const codes = g6GrossQueryCodes(tbSourceCodes)
  return codes[0] || G6_GROSS_FALLBACK_STANDARD
}
```

### 附注模板修复

**幂等脚本**：`backend/scripts/fix/fix_note_g6_structure.py`

仅在 `--check` 发现欠账时修复：
- 上市 §五、15：14 表已有 columns/guidance，只验证不重建
- 国企 §八、16：2 表核查 columns 列数/key 是否匹配源模板

### 公式预设修正

**幂等脚本**：`backend/scripts/fix/fix_g6_prefill_presets.py`

- 审定表块 `account_codes` 改 `["1505"]`
- 明细表块 `account_codes` 改 `["1505"]`，删 AUX 硬编码
- 新增两个披露块（上市/国企）

## Data Models

### render 输出新增字段

```python
{
    "tb_values": {"opening": float, "closing": float},
    "tb_source_codes": {
        "gross_standard": ["1505"],
        "resolved_from": "report_config" | "fallback"
    },
    "adjudication_prefill": [  # 仅灰度开时 + block1 无用户数据时
        {"code": "1505.01", "name": "xxx", "opening_balance": 0.0, "closing_balance": 0.0, "block": "block1", "source": "four-table"}
    ] | None
}
```

### g6AccountScope.ts 接口

```typescript
interface G6TbSourceCodes {
  gross_standard: string[]
  resolved_from: 'report_config' | 'fallback'
}
```

## Correctness Properties

### Property 1: 科目单一真源
**Validates: Requirements 1.1, 1.2, 1.3**
后端 render 与前端 g6AccountScope 最终取数科目必须与 `report_config` BS-022 的 `TB('1505',...)` 一致。

### Property 2: 公式预设科目一致
**Validates: Requirements 3.1, 3.2**
`prefill_formula_mapping.json` 中 wp_code=G6 的所有条目，`account_codes` 只许含 1505 族（不许 1503/1510/1531）。

### Property 3: 叶子口径勾稽
**Validates: Requirements 2.1**
`aggregate_leaves(select_leaves(..., ['1505']))` 的 opening+closing 之和 == `tb_balance` 父科目 `1505` 的 opening+closing（叶子和等于父额）。

### Property 4: 附注表名对齐
**Validates: Requirements 4.1, 4.2**
上市 14 张表名与 `G6_LISTED_SUBTABLE` + `G6_LISTED_STAGE_SUBTABLE` 逐字一致；国企 2 张表名与 `G6_SOE_SUBTABLE` 逐字一致。

### Property 5: 国企不推三阶段
**Validates: Requirements 4.3, 5.2**
国企 Tab `syncToDisclosureNotes` 的 `sub_table_data` 键集 ⊆ `{'其他债权投资情况', '期末重要的其他债权投资'}` + `_note_texts`。

### Property 6: 零回归
**Validates: Requirements 2.2**
`adjudication_prefill` 仅在灰度开 + block1 无数据时返回；灰度关闭时 render 输出逐字节等价当前（除 `_G6_ACCOUNT_PREFIX` 字面量外）。

### Property 7: 溯源面板消费
**Validates: Requirements 5.4, 6.2**
前端 `tb_source_codes` 非 dead output —— 至少被溯源面板或审定表 TB 核对行消费。
