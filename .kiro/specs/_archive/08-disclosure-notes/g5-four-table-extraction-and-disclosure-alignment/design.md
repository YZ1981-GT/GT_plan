# Design Document

## Overview

G5 长期应收款四表取数链路修复 + 披露/附注结构对齐。整体范式沿用 K1/K2/G7 已验证的共享件模式，G5 是 `four_table/{report_line_accounts, leaf_aggregation}` 的第 N 个消费者。

**关键设计判断**：
1. G5 叶子子科目名天然对应性质分类桶（同 F1 的 1123→五性质桶）—— `.01` 系=融资租赁/押金、`.02` 系=借款/保证金、`.11`=分期收款销售、`.99`=一年内到期（扣减行不入桶）
2. 坏账准备无独立报表行（同 D3/D7），叶子聚合时直接用父前缀 `1531`
3. G5 的性质表有独特的「未实现融资收益」折现行，是 subrow 形态（在融资租赁款/分期收款下缩进）
4. 组合账龄块是**动态数量**的子表，每个组合一张独立附注子表（同 D1/D2 范式）

## Architecture

```
report_config (BS-023) ─→ resolve_report_line_account_codes ─→ ['1531']
                                           │
                        account_mapping ←──┘  反解 standard→original
                                           │
                        tb_balance ←───────┘  select_leaves + aggregate
                                           │
                        render output ─────→ tb_values / tb_source_codes / adjudication_prefill
                                           │
                        前端 ←─────────────┘
                          ├─ 审定表 seed (useG5Adjudication.pullFromTB)
                          ├─ 溯源面板 (WpFourTableSourcePanel)
                          └─ 披露表取数 (refreshFromSources)
                                           │
                        syncToDisclosureNotes ─→ sync_from_workpaper API
                                                  │
                        附注 disclosure_notes ←──┘
```

## Components and Interfaces

### C1. 后端 render 策略重写

`_g5_long_term_receivable.py` 的 `render` 函数改为：

```python
from app.services.four_table.report_line_accounts import (
    ReportLineAccountSpec, resolve_report_line_account_codes
)
from app.services.four_table.leaf_aggregation import select_leaves, aggregate_leaves

G5_ACCOUNT_SPEC = ReportLineAccountSpec(
    row_code='BS-023',
    fallback_standard_codes=('1531',),
)
```

纯函数：`build_g5_tb_values(leaves)` / `build_g5_leaf_categories(leaves)` / `build_g5_adjudication_prefill(categories)` / `build_g5_source_codes(spec, resolved)`

### C2. 性质分类桶

```python
@dataclass
class G5NatureBucket:
    key: str
    label: str
    keywords: tuple[str, ...]
    exclude_keywords: tuple[str, ...] = ()
    source_ref: str = ''  # 源 xlsx 单元格

G5_NATURE_BUCKETS = [
    G5NatureBucket('finance_lease', '融资租赁款', ('融资租赁',), source_ref='R9'),
    G5NatureBucket('installment_goods', '分期收款销售商品', ('分期收款销售',), source_ref='R11'),
    G5NatureBucket('installment_service', '分期收款提供劳务', ('分期收款提供劳务','分期收款劳务'), source_ref='R13'),
    G5NatureBucket('deposit', '押金保证金', ('押金','保证金'), exclude_keywords=('融资',), source_ref='R16:other'),
    G5NatureBucket('loan', '借款', ('借款',), exclude_keywords=('融资',), source_ref='R16:other'),
    G5NatureBucket('other', '其他', (), source_ref='R16'),  # 兜底
]
```

归类函数 `classify_g5_leaf(name, code)` 按名称关键词优先 + `exclude_keywords` 否决词 + 编码后缀兜底。

### C3. 公式预设修正

文件：`backend/data/prefill_formula_mapping.json`

- 现有 G5 块：科目 `1503`→`1531`，wp_name 修正
- 新增块：`附注披露信息（上市公司）` / `附注披露信息（国企）`

### C4. 附注模板结构脚本

`backend/scripts/fix/fix_note_g5_structure.py`（复用 `_note_structure_kit`）

**国企 §八、17**（3 表→补 columns+guidance）：
| # | 表名 | 列数 | group |
|---|------|------|-------|
| 1 | 长期应收款按性质披露 | 8 | 期末余额(1,3)/期初余额(4,3) |
| 2 | 终止确认的长期应收款 | 4 | flat |
| 3 | 转移长期应收款且继续涉入形成的资产、负债的金额 | 2 | flat |

**上市 §五、16**（0 表→8 表重建）：
| # | 表名 | 列数 | group |
|---|------|------|-------|
| 1 | 长期应收款按性质披露 | 8 | 期末余额(1,3)/上年年末余额(4,3) |
| 2 | 坏账准备计提情况 | 10 | 期末余额(1,5)/上年年末余额(6,5) |
| 3 | 按单项计提坏账准备 | 5 | flat |
| 4 | 按单项计提坏账准备（续：上年年末余额） | 5 | flat |
| 5 | 组合计提项目：XXX | 7 | 期末余额(1,3)/上年年末余额(4,3) |
| 6 | 本期计提、收回或转回的坏账准备情况 | 1 | flat |
| 7 | 本期实际核销的长期应收款 | 1 | flat |
| 8 | 重要的长期应收款核销情况（逐项披露） | 6 | flat |

### C5. 前端 `g5AccountScope.ts`

```typescript
export const G5_REPORT_ROW_CODE = 'BS-023'
export const G5_GROSS_FALLBACK_STANDARD = '1531'

export function g5GrossQueryCodes(tbSourceCodes?: TbSourceCodes): string[] {
  return tbSourceCodes?.gross_standard ? [tbSourceCodes.gross_standard] : [G5_GROSS_FALLBACK_STANDARD]
}
```

### C6. 共享溯源面板接入

复用 `shared/WpFourTableSourcePanel.vue`（原值中文名=长期应收款、无备抵科目故不传 `provisionLabel`）

## Data Models

### render output 新增字段

```json
{
  "tb_source_codes": {
    "gross_standard": "1531",
    "resolved_from": "report_config",
    "applicable_standard": "soe_standalone"
  },
  "adjudication_prefill": [
    {"bucket_key": "finance_lease", "label": "融资租赁款", "opening": 12345.67, "closing": 23456.78},
    ...
  ],
  "leaf_categories": {
    "finance_lease": {"codes": ["1531.01"], "opening": 12345.67, "closing": 23456.78},
    ...
  }
}
```

## Correctness Properties

### Property 1: 叶子聚合等于父科目
**Validates: Requirements 1.1, 1.4**
对任意有 `1531` 子科目的项目，`sum(leaf.closing for leaf in leaves) == tb_balance['1531'].closing`。

### Property 2: 公式预设科目正确
**Validates: Requirements 2.1, 2.2**
G5 块的 `account_codes` 全部为 `['1531']`，所有 `TB()`/`ADJ()` 公式引用的科目码 ∈ {`1531`, `1531.*`}。

### Property 3: 附注表名逐字一致
**Validates: Requirements 3.1, 3.2, 4.1, 4.2**
`G5_LISTED_SUBTABLE` / `G5_SOE_SUBTABLE` 每个值在对应 `note_template_*.json` 的 `tables[].name` 中能精确命中。

### Property 4: 性质桶无重叠
**Validates: Requirements 1.3**
对任意叶子科目名称，`classify_g5_leaf` 至多归入一个桶（兜底 `other` 除外）。

### Property 5: 溯源非死输出
**Validates: Requirements 5.1**
前端至少一个组件引用 `tb_source_codes`（grep 命中数 > 0）。

### Property 6: 组合表命名空间无撞键
**Validates: Requirements 4.3**
同一章节下不会出现两张同名子表（组合名去重 + 前缀统一）。
