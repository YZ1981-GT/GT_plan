# Design Document

## Overview

把 N3 / N4 / N5 的四表取数链路补成闭环，沿用 N1 已验证并实测通过的范式。三个循环的
缺陷严重度差异很大，故设计上先分层再收敛：

| 循环 | 科目 | 口径 | 报表行 | 当前状态 |
|---|---|---|---|---|
| N3 递延所得税负债 | `2901` | 期末余额（负债贷方，`abs()` 归一） | `BS-067` | 取数能跑但**只认科目级精确单行**；预填全塞「其他」行；3 个输出键是 dead output |
| N4 税金及附加 | `6403` | **本期发生额**（`tb_ledger` 借−贷） | `IS-003` | 后端取数正确，但前端 seed 是**空 if 块** → dead output |
| N5 所得税费用 | `6801` | **本期发生额**（`tb_ledger` 借−贷） | `IS-023` | **两处 `get_active_filter` 签名错 → 运行期 `TypeError` 被 `except` 吞 → 取数恒 0** |

### 为什么 N5 的 28 个测试全绿却漏掉 P0

`test_n5_integration.py` 只做导入可用性、`RENDERER_DISPATCH` 指向、`N5_SHEETS` 完整性、
`_parse_num` 单测 —— **从不真实调用 `_fetch_tb_data`**。而生产代码写的是
`get_active_filter(ctx.project_id)`，真实签名是
`async def get_active_filter(db, table, project_id, year, *, ...)` →
调用即 `TypeError`，被 `except Exception` 捕获后 `logger.warning` 然后返回全 0 结果。
**这类缺陷只有真实签名调用的测试能拦。**

### 共享化决策

N1 已把 `2901` 的五语义槽分类做完并实测通过。N3 需要同样能力 →
**抽共享模块 `backend/app/services/deferred_tax_shared.py`**，N1 与 N3 同时引用，
而不是在 N3 里复制一份（平台已有「不新造第 3 套四表库读取」的收敛铁律）。

同理前端 `useLmnTbReconcile` 已存在且专为 L/M/N 审定表设计，只是**从未被引用** →
直接接入三个循环，不新写。

## Architecture

### 取数链路（改造后，三循环同构）

```
ledger 导入 → ledger_datasets(status=active) → tb_balance / tb_ledger / trial_balance
      │
      │  唯一查询入口（正确签名，四参 + await）
      ▼
dataset_query.get_active_filter(db, Table.__table__, project_id, year or 0)
      │
      │  科目映射（本次接入）
      ▼
report_account_mapping.resolve_report_line_account_codes(db, pid, row_code, fallback)
      ├── N3 'BS-067' → ['2901']   余额类 → tb_balance
      ├── N4 'IS-003' → ['6403']   损益类 → tb_ledger 发生额
      └── N5 'IS-023' → ['6801']   损益类 → tb_ledger 发生额
      │
      ▼
render(ctx) → html_data
      ├── trial_balance          （既有键，语义不动）
      ├── adjudication_prefill   （N3 新增分类版 / N5 修复后非 None / N4 沿用 tb_values）
      └── tb_source_codes        （三者新增）
      │
      ▼  GET /workpapers/{id}/render-config
前端 useNxFormData → 审定表 Tab
      ├── useLmnTbReconcile(htmlData, totalAudited, {isIncome})   TB 核对行
      ├── 「从四表库带入未审数」按钮 → 只填空不覆盖
      └── 取数溯源展示（消费 tb_source_codes）
```

### N3 的语义分类复用

```
backend/app/services/deferred_tax_shared.py        [新增，纯函数 + 查询 helper]
    ├── LIABILITY_SLOTS / LIABILITY_SLOT_ORDER
    ├── classify_liability_subaccount(name) -> slot
    ├── code_predicate(table_col, code)
    ├── leaf_rows(rows)
    └── aggregate_by_slot(rows, classify, *, absolute)
            ▲                          ▲
            │                          │
   _n1_deferred_tax_assets.py   _n3_deferred_tax_liabilities.py
   （改为 re-export / 委托）      （新接入，替代「全塞其他行」）
```

> **迁移安全**：N1 侧保留同名模块内函数（`_classify_n1_liability_subaccount` 等）作为
> 对共享模块的**薄壳委托**，因为 `test_n1_account_mapping.py` 直接按模块属性取用它们。

## Components and Interfaces

### 后端

#### `backend/app/services/deferred_tax_shared.py`（新增）

```python
LIABILITY_SLOT_OTHER = "other"
LIABILITY_SLOTS: list[str] = [
    "depreciation", "afs_fv", "investment_property_fv", "lease", LIABILITY_SLOT_OTHER,
]

def classify_liability_subaccount(name: str | None) -> str:
    """2901 子科目名 → 语义槽。
    🔴 判定顺序：`投资性房地产` 必须先于泛化 `公允价值`。
    """

def code_predicate(col, code: str):
    """单码前缀 / `start~end` 区间 → SQLAlchemy 谓词（列由调用方给，兼容
    tb_balance.account_code 与 tb_ledger.account_code）。"""

def leaf_rows(rows: Sequence[Any]) -> list[Any]:
    """只保留叶子行。🔴 不带点的 startswith —— 兼容点分（`2901.01`）与平铺（`290101`）两种层级。"""

def aggregate_by_slot(rows, classify, *, absolute=False) -> dict[str, dict[str, float]]:
    """叶子行 → {槽: {opening, closing}}；全零槽跳过。"""
```

#### `_n3_deferred_tax_liabilities.py`（改造）

```python
_LIABILITY_ROW_CODE = "BS-067"      # DB 实证，四准则一致

async def _resolve_account_codes(ctx, row_code, fallback) -> list[str]   # fail-open
async def _fetch_tb_data(ctx, codes) -> dict                            # 科目级优先 → 叶子聚合
async def _build_adjudication_prefill(ctx, codes) -> dict[str, dict[str, float]]
    """2901 叶子 → 语义槽（复用共享模块）。只有父级时返回 {}。"""
```

`render` 输出新增 `adjudication_prefill` + `tb_source_codes`；
`N3_SHEETS` 删除 `附注披露信息` 条目。

#### `_n4_taxes_and_surcharges.py`（改造）

```python
_N4_ROW_CODE = "IS-003"
async def _resolve_account_codes(...)     # 同款
# _fetch_tb_period_amount 改为接收 codes（tb_ledger 发生额口径不变）
```

`render` 输出新增 `tb_source_codes`（放 `html_data` 顶层，与既有 `tb_values` 并列）。

#### `_n5_income_tax_expense.py`（改造）

```python
_N5_ROW_CODE = "IS-023"

# 🔴 P0：两处签名修正
active_filter = await get_active_filter(ctx.db, TbLedger.__table__, ctx.project_id, ctx.year or 0)
active_filter = await get_active_filter(ctx.db, TbBalance.__table__, ctx.project_id, ctx.year or 0)
# 并删除多余的手写 `Table.project_id == str(ctx.project_id)`（get_active_filter 已含）

# 当期/递延拆分改用叶子聚合 + 共享 leaf_rows，排除父级防双算
```

`render` 输出新增 `tb_source_codes`。

### 前端

#### 三个审定表 Tab 的统一改造形状

```ts
// ① TB 核对（复用现成件）
const tbReconcile = useLmnTbReconcile(
  computed(() => props.htmlData),
  computed(() => total.value.endAudited),
  { isIncome: true },        // N4 / N5 传 true；N3 不传
)

// ② 从四表库带入（只填空不覆盖）
function pullFromTB(): { filled: number } { ... }

// ③ 取数溯源
const tbSourceSummary = computed(() => { /* 消费 tb_source_codes */ })
```

## Data Models

### `tb_source_codes`（三循环同形）

```ts
interface NxTbSourceCodes {
  row_code: string   // 'BS-067' | 'IS-003' | 'IS-023'
  codes: string[]    // 映射解析出的科目集
  basis: 'balance' | 'period'   // 余额类 / 损益发生额，供前端标注口径
}
```

> N1 因为同时取资产与负债两侧，用的是 `{asset, liability}` 嵌套形；N3/N4/N5 各只有一侧，
> 用扁平形并加 `basis` 标注口径（前端展示「本期发生额」vs「期末余额」）。

### N3 `adjudication_prefill`

```ts
type N3AdjudicationPrefill = Record<
  'depreciation' | 'afs_fv' | 'investment_property_fv' | 'lease' | 'other',
  { opening: number; closing: number }
>
```

前端 `useN3Adjudication` 的 `DEFAULT_CATEGORIES` 需与语义槽建立映射
（单一真源放前端 `n3LiabilitySlotLabel`，与 N1 的 `N1_LIABILITY_SLOT_LABEL` 同源口径）。

### N5 `adjudication_prefill`（既有形状不动，只修让它非 None）

```ts
{ current: {...}, deferred: {...}, total_period: number }
```

## Correctness Properties

### Property 1: `get_active_filter` 调用签名正确

N3 / N4 / N5 三个策略模块中对 `get_active_filter` 的每一次调用，
实参个数恒 ≥ 4 且首参为会话对象、次参为 `Table` 对象，且调用被 `await`。

**Validates: Requirements 1.1, 1.2, 1.5**

### Property 2: N5 取数在真实签名下返回非零

给定含 `6801` 发生额的 `tb_ledger` 数据，`_fetch_tb_data` 返回的 `period_amount`
恒等于 `Σ借方 − Σ贷方`；`_build_adjudication_prefill` 在有子科目时恒非 `None`。

**Validates: Requirements 1.3, 1.4, 1.6, 5.3**

### Property 3: 科目映射解析恒不阻断渲染

三循环的 `_resolve_account_codes` 对任意 DB 状态（抛错 / 无记录 / 公式为 null）
恒返回非空科目集：命中返回解析值，其余返回 `fallback`。

**Validates: Requirements 3.1, 3.2, 3.3, 3.4**

### Property 4: 叶子聚合不双算

对任意科目层级结构（点分或平铺），取出的行集中不存在任何两行 `a`、`b`
使 `b.account_code` 以 `a.account_code` 为真前缀；且存在科目级精确行时只用它。

**Validates: Requirements 4.1, 4.2, 5.4**

### Property 5: 负债槽分类全覆盖且互斥

`classify_liability_subaccount` 对任意字符串恒返回 `LIABILITY_SLOTS` 之一；
含「投资性房地产」的名称恒归 `investment_property_fv`（优先于泛化 `公允价值`）。

**Validates: Requirements 4.3, 4.4**

### Property 6: 共享模块与 N1 行为等价

对同一输入，共享模块的 `classify_liability_subaccount` / `leaf_rows` /
`aggregate_by_slot` 与迁移前 N1 模块内实现的输出恒相同（characterization）。

**Validates: Requirements 4.4**

### Property 7: 预填手工优先且不写 0

对任意预填输入与任意现有行状态，若目标字段已非零则不被修改；
预填值为 0 或缺失时不写入（避免 0 冒充「已核实为零」）。

**Validates: Requirements 2.1, 2.2, 4.3, 6.5**

### Property 8: 损益类恒取发生额

N4 / N5 的取数与公式预设中，涉及 `6403` / `6801` 的表达式恒使用 `本期发生额`，
不出现 `期末余额`。

**Validates: Requirements 8.3**

### Property 9: 预设科目白名单

`workpaper:N3` 表达式中的科目恒以 `2901` 开头；`workpaper:N4` 恒以 `6403` 开头；
`workpaper:N5` 恒以 `6801` / `1811` / `2901` 之一开头。
三者均不出现 `1812`（活体 0 命中）与 `6001`（营业收入，非利润总额）。

**Validates: Requirements 8.1, 8.2, 8.4, 8.6, 8.7**

### Property 10: 预设 `cell_ref` 在 wp_code 内唯一

因 `page_key = workpaper:{wp_code}` 忽略 sheet，同名 `cell_ref` 必互相遮蔽 →
每个 wp_code 内 `cell_ref` 恒唯一。

**Validates: Requirements 8.8, 8.9**

### Property 11: 四表输出无 dead output

N3 / N4 / N5 render 输出的四表相关键，每一个在前端源码中恒有至少一处消费，
或已在豁免清单登记且写明理由。

**Validates: Requirements 3.6, 4.6, 9.1**

### Property 12: `useLmnTbReconcile` 有真实消费方

该 composable 的引用点恒 ≥ 3（N3 / N4 / N5 审定表），防现成件再次闲置。

**Validates: Requirements 6.1, 6.2, 9.4**

### Property 13: N3 无披露 inert 残留

`N3_SHEETS` 不含任何名称含「附注」或「披露」的条目；
宿主的 sheet 分发与 `isHtmlSheet` 判定不含「附注」/「披露」分支。

**Validates: Requirements 7.1, 7.2, 7.3**

## Error Handling

| 失败点 | 策略 | 理由 |
|---|---|---|
| 映射解析抛错 / 无记录 | 回退 fallback + `logger.warning` | 取数是增强项，不得阻断底稿打开 |
| `tb_balance` / `tb_ledger` 查询抛错 | 返回零值结果 + `warning` | 同上；前端表现为「无预填」而非白屏 |
| 只有父级科目无子科目 | N3 返回 `{}`；N5 把总额落「当期」并标注需人工拆分 | N3 无法虚构分类；N5 有明确的合理归属 |
| 负债类符号约定不一致 | `abs()` 归一 | 活体实测两种约定并存 |
| 前端 render-config 缺新键 | `?? {}` 兜底，静默跳过 | 后端未重启时不能让审定表报错 |
| **`except Exception` 吞签名错** | **禁止**：签名类错误必须由真实调用测试拦住 | 这正是 N5 P0 长期存活的原因 |

## Testing Strategy

**后端**

| 文件 | 覆盖 |
|---|---|
| `backend/tests/test_deferred_tax_shared.py`（新增） | Property 4/5/6：共享模块纯函数 + 与 N1 行为等价 characterization |
| `backend/tests/test_n3_four_table_extraction.py`（新增） | Property 3/4/5/7 + Requirement 4/7：N3 映射、叶子聚合、语义分类预填、`N3_SHEETS` 无披露残留 |
| `backend/tests/test_n4_four_table_extraction.py`（新增） | Property 3/8：N4 映射、`tb_ledger` 发生额、`tb_source_codes` |
| `backend/tests/test_n5_four_table_extraction.py`（新增） | **Property 1/2**：以真实签名调用取数与预填，断言非零/非 None（拦 P0） |
| `backend/tests/formula_management/test_n345_preset_purity.py`（新增） | Property 9/10 + Requirement 8 全条 |

**前端**

| 文件 | 覆盖 |
|---|---|
| `composables/__tests__/n345TbSeedAndReconcile.spec.ts`（新增） | Property 7/12：手工优先、TB 核对接入点 ≥ 3 |
| `__tests__/fourTableOutputConsumption.spec.ts`（新增） | Property 11：扫 render 策略源码取键名 → 断言前端有消费点（带豁免清单 + 反向自检） |
| 扩展 `n3-integration` / `useN4Engines.unit` / `n5-unit` | 各自 seed 与核对行为回归 |

**实测**（chrome-devtools MCP + postgres 只读）

活体候选：项目 `2aa00f57`（`2901` 期末 233,512.19 非零；`6403` / `6801` 需先查 `tb_ledger`
是否有发生额）与 `0ec33ac9`。验证点：三个审定表打开即有 TB 核对行、点「从四表库带入」
未审数落值、取数溯源显示报表行。**验证后复原测试数据**。

**已知不可验风险**：若活体 `tb_ledger` 无 `6403` / `6801` 发生额，则 N4 / N5 的
带入按钮只能验「不写 0、不报错」而无法验真实金额 —— 此时以真实 DB 直跑 render 的
数值为准并在实测记录中说明。
