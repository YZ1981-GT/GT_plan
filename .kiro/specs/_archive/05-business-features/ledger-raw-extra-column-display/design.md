# Design Document

## Overview

让 `tb_ledger` / `tb_aux_ledger` 的 `raw_extra` JSONB 中的**业务额外字段**（导入时的非关键列）在凭证/序时账查询时透出并显示，过滤 `_` 前缀系统标记，additive 零回归。

改动分三层：
1. **后端序列化**：`ledger_penetration_service.py` 6 个查询方法在 `sa.select(...)` 补 `raw_extra` 列，`items` 构造后统一经**单一 helper** 展开为 `extra_fields`（过滤 `_` 前缀）并移除原始 `raw_extra` 键。
2. **前端数据**：查询响应每条分录多一个 `extra_fields` 对象。
3. **前端显示**：`LedgerPenetration.vue` 明细表格在固定列后按**当前结果集 `extra_fields` 键并集**动态追加列。

不改数据库结构、不改导入写入逻辑。

## Architecture

```
凭证查询请求
  → ledger_penetration_service.{get_ledger_entries|_cursor|get_all_ledger_entries
                                  |get_voucher_entries|get_aux_ledger_entries|_cursor}
      sa.select(...固定列..., tbl.c.raw_extra)          # 各方法补 raw_extra
      items = [dict(r._mapping) ...]
      items = attach_extra_fields(items)                # 单一 helper（新增）
        · extra = {k:v for k,v in (raw_extra or {}).items() if not k.startswith('_')}
        · row['extra_fields'] = extra
        · del row['raw_extra']                          # 不透出整个 JSONB
  → 响应 {items:[{...固定列, extra_fields:{...}}], ...}
      ↓
前端 LedgerPenetration.vue
  · buildExtraColumns(items) → string[]                 # 纯函数：本批 extra_fields 键并集（保序）
  · <el-table-column v-for="k in extraColumns" :prop="`extra_fields.${k}`" :label="k">
```

## Components and Interfaces

### 后端

#### 新增：`_attach_extra_fields`（模块级纯函数，`ledger_penetration_service.py`）

```python
_SYSTEM_KEY_PREFIX = "_"  # 系统标记统一 _ 前缀

def _attach_extra_fields(rows: list[dict]) -> list[dict]:
    """将每行 dict 的 raw_extra 展开为 extra_fields（过滤 _ 前缀系统标记），
    并移除原始 raw_extra 键。就地修改并返回同一列表。

    - raw_extra 为 None / 空 / 仅含 _ 前缀键 → extra_fields = {}
    - 业务键值原样保留、保持 dict 迭代顺序（Python3.7+ 插入序 = 导入列序）
    """
    for row in rows:
        raw = row.pop("raw_extra", None)
        if isinstance(raw, dict):
            row["extra_fields"] = {
                k: v for k, v in raw.items() if not k.startswith(_SYSTEM_KEY_PREFIX)
            }
        else:
            row["extra_fields"] = {}
    return rows
```

单一真源，6 个方法共用，保证过滤/空值口径一致（Req4.1）。

#### 改动：6 个查询方法

| 方法 | select 补列位置 | items 后处理 |
|------|----------------|-------------|
| `get_all_ledger_entries` (TbLedger) | `base` select 加 `tbl.c.raw_extra` | `items = _attach_extra_fields(items)` |
| `get_ledger_entries` (TbLedger) | `base` select 加 `tbl.c.raw_extra` | 同上 |
| `get_ledger_entries_cursor` (TbLedger) | **`ledger_sq` subquery** select 加 `tbl.c.raw_extra`（作 passthrough 列，不参与 window/游标）| `items = _attach_extra_fields(items)`（在 `items = rows[:limit]` 后）|
| `get_voucher_entries` (TbLedger) | `stmt` select 加 `tbl.c.raw_extra` | `return _attach_extra_fields([dict...])` |
| `get_aux_ledger_entries` (TbAuxLedger) | `base` select 加 `tbl.c.raw_extra` | `items = _attach_extra_fields(items)` |
| `get_aux_ledger_entries_cursor` (TbAuxLedger) | `stmt` select 加 `tbl.c.raw_extra` | `items = _attach_extra_fields(items)`（在 `items = rows[:limit]` 后）|

**游标方法注意**：`next_cursor` 仍从 `last['voucher_date']`/`last['id']` 计算，`_attach_extra_fields` 在 `items = rows[:limit]` 切片后调用即可（不影响游标）。`has_more` 用 `len(rows) > limit` 判断，raw_extra 不影响。

**不改动**：`get_balance_summary` / `get_aux_balance*` / `penetrate`（余额类，非凭证行，raw_extra 的聚合标记不作业务字段显示）；`get_all_aux_balance` / `aux-balance-paged` / `aux-balance-detail`（余额类，透出 `aux_dimensions_raw` 已够，不在本 spec 范围）。

### 前端

#### 新增：`buildExtraColumns`（纯函数，抽到 `LedgerPenetration.vue` 内或就近 utils）

```ts
/** 本批分录 extra_fields 键并集，保持首次出现顺序。 */
export function buildExtraColumns(items: Array<{ extra_fields?: Record<string, unknown> }>): string[] {
  const seen = new Set<string>()
  const cols: string[] = []
  for (const it of items) {
    const ef = it?.extra_fields
    if (!ef) continue
    for (const k of Object.keys(ef)) {
      if (!seen.has(k)) { seen.add(k); cols.push(k) }
    }
  }
  return cols
}
```

#### 改动：`LedgerPenetration.vue` 明细表格

- `const extraColumns = computed(() => buildExtraColumns(<当前明细 items>))`
- 序时账明细表格 + 凭证明细（穿透第三层）表格，在既有固定 `<el-table-column>` 之后追加：
  ```html
  <el-table-column v-for="k in extraColumns" :key="`ef-${k}`"
    :label="k" :prop="`extra_fields.${k}`" min-width="120" show-overflow-tooltip>
    <template #default="{ row }">{{ row.extra_fields?.[k] ?? '' }}</template>
  </el-table-column>
  ```
- `extraColumns` 为空 → 无追加列（视觉与当前一致，Req3.3）。
- 数据源作用域 = 当前已加载/展示的明细数组（序时账全量拉取后累积、凭证明细一次性全量）→ 键并集随数据自然稳定，不闪烁（决策见下）。

## Data Models

不新增/修改任何数据库表或列。`raw_extra` JSONB 已存在于四表。

响应契约变化（additive）：每条分录 dict：
- **移除**：`raw_extra`（原始 JSONB，本就未透出，现明确不透）
- **新增**：`extra_fields: Record<string, string>`（过滤 `_` 前缀后的业务键值）
- 其余固定字段名/值不变。

## 关键设计决策

1. **单一 helper 而非各方法内联**：`_attach_extra_fields` 集中过滤/空值口径，杜绝 6 处分叉（Req4.1）。
2. **只透 `extra_fields` 不透 `raw_extra`**：`del raw_extra` 避免把整个 JSONB（含系统标记）暴露给前端，也减小 payload。
3. **保序**：Python dict 保插入序（导入时按原始列序写入），前端 `buildExtraColumns` 保首次出现序，列顺序稳定可预期。
4. **动态列作用域 = 当前结果集键并集**（非全库扫描）：
   - 序时账明细前端是全量拉取后本地展示（`fetchAllLedgerEntries` 累积 items），键并集在完整数据上算 → 稳定不闪烁。
   - 凭证明细是按凭证号一次性全量 → 键集固定。
   - 不做"预扫描全表列名"（避免额外查询 + 大表开销）。
5. **游标 passthrough**：cursor 方法把 raw_extra 放进含 window 的 subquery 作 passthrough 列，不参与 keyset 排序/游标，`next_cursor` 逻辑不变。
6. **范围仅凭证行**：余额类查询（balance/aux-balance）不在本 spec；tb_balance 的 `_aggregated_from_aux` 等聚合标记本就是 `_` 前缀系统标记，即便未来扩展也会被同一 helper 过滤。

## Correctness Properties

### Property 1: 系统标记被过滤
`_attach_extra_fields` 产出的 `extra_fields` 不含任何以 `_` 开头的键。
**Validates: Requirements 2.1, 2.2**

### Property 2: 业务键值保序透出
`extra_fields` 保留 raw_extra 中全部非 `_` 前缀键，值不变，顺序为 raw_extra 迭代序。
**Validates: Requirements 1.1, 2.2**

### Property 3: 空/NULL 安全
raw_extra 为 None、空 dict、非 dict、或仅含 `_` 前缀键时，`extra_fields` 为 `{}`，且该行其余字段不受影响、不报错。
**Validates: Requirements 1.5, 5.3**

### Property 4: 不透出原始 raw_extra
`_attach_extra_fields` 处理后的行不含 `raw_extra` 键。
**Validates: Requirements 2.1**

### Property 5: 既有固定字段零回归
经 `_attach_extra_fields` 后，每行的既有固定字段（id/voucher_date/voucher_no/account_code/account_name/debit_amount/credit_amount/summary/counterpart_account/preparer/running_balance/accounting_period/voucher_type 等，按各方法 select 集合）字段名与取值完全不变。
**Validates: Requirements 5.1, 5.4**

### Property 6: 前端动态列 = 本批键并集
`buildExtraColumns(items)` 返回本批所有分录 `extra_fields` 键的并集，保持首次出现顺序，无重复；全部为空时返回 `[]`。
**Validates: Requirements 3.1, 3.3**

### Property 7: 全端点口径一致
6 个查询方法均经同一 `_attach_extra_fields`，对同一 raw_extra 输入产出同一 `extra_fields`。
**Validates: Requirements 4.1, 4.2**

## Error Handling

- `raw_extra` 非 dict（历史脏数据/被序列化成字符串）→ `_attach_extra_fields` 走 `else` 分支置 `{}`，不抛。
- 前端 `row.extra_fields?.[k] ?? ''` 兜底缺失单元格（Req3.2）。
- 后端 select 补列失败可能性极低（列已存在）；helper 是纯字典操作无 IO。

## Testing Strategy

- **后端单元（纯函数）**：`_attach_extra_fields` 覆盖 Property 1-5、7（`_` 过滤 / 保序 / None·空·非dict·仅系统键 / 移除 raw_extra / 固定字段不变）。
- **后端集成**：对含 raw_extra 的 tb_ledger 行，验证 `get_ledger_entries` / `get_voucher_entries` / cursor 返回 `extra_fields`（真实 PG16 或既有 fixture）；零回归锚定既有固定字段集合不变。
- **前端 vitest**：`buildExtraColumns` 覆盖 Property 6（并集/保序/去重/空→[]）。
- **前端组件（可选）**：`LedgerPenetration.vue` 明细表格在有 extra_fields 时渲染追加列、无时不追加。
- **Playwright（可选）**：导入含非关键列的账套 → 序时账/凭证明细表格显示额外列（需实例化项目 + 含 raw_extra 数据）。
