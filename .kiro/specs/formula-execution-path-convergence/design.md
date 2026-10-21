# 设计：公式执行路径收敛

> spec: `formula-execution-path-convergence` · requirements R1~R5

## §1 现状三条路径

```
路径 A（报表/表间审核）:
  formula_text → evaluate_formula_result()
    → regex 预替换 SUM_TB/TB → Decimal
    → regex 预替换 PREV/AUX → 0
    → WP/NOTE → WPExecutor/NOTEExecutor 异步预载 → ctx
    → ADJ → adj_data 注入 → ctx
    → formula_engine.execute(expression, ctx)   ← L1 内核

路径 B（底稿预填充）:
  prefill_workpaper_real() → 扫描 Excel → 逐格循环
    → resolve_extended_formula(ft, raw_args)
      → _FORMULA_RESOLVERS[ft](db, project_id, year, args)  ← 各自查 DB
    → 写回 univer_snapshot

路径 C（公式管理页 API）:
  FormulaEngine.execute(db, project_id, year, ft, params)
    → 查 trial_balance → from_simple_map → execute(formula, ctx)  ← L1 内核
```

## §2 统一预载层（R1）

```python
# backend/app/services/formula_preloader.py

async def preload(
    db: AsyncSession,
    project_id: uuid.UUID,
    year: int,
    formulas: list[str],
    *,
    adj_exclude_origins: frozenset[str] = frozenset(),
    include_prior: bool = False,
) -> FormulaContext:
    """批量扫描公式文本 → 一次性查 DB → 构建 FormulaContext。"""
```

### 数据源扫描策略

从公式文本提取引用的数据源，按类型批量查：

| 函数 | 扫描正则 | 批量查的表/API | 填入 ctx 字段 |
|------|---------|--------------|-------------|
| TB / SUM_TB | `TB\('(\w+)'` | `trial_balance`（TrialBalanceResolver 口径） | `tb_data` |
| ADJ | `ADJ\('(\w+)'` | `adj_net_batch` | `adj_data` |
| AUX | `AUX\('(\w+)'` | `tb_aux_balance` | `aux_data` |
| WP | `WP\('([^']+)'` | `checklist_responses` + `prefill_anchor_map` | `wp_data` |
| NOTE | `NOTE\('([^']+)'` | `disclosure_notes.table_data.sub_table_data`（披露表，非旧 rows） | `note_data` |
| PREV | `PREV\('(\w+)'` | `trial_balance` (year-1) | `prior_tb_data` |
| LEDGER | `LEDGER\('(\w+)'` | `tb_ledger` | `ledger_data`（新字段） |
| LEDGER_DETAIL | `LEDGER_DETAIL\('(\w+)'` | `tb_ledger` | `ledger_detail_data`（新字段） |
| COUNT_LEDGER | `COUNT_LEDGER\('(\w+)'` | `tb_ledger` | `ledger_data` |
| TB_AUX | `TB_AUX\('(\w+)'` | `tb_aux_balance` | `aux_data` |
| ROW / SUM_ROW / REPORT | — | 不查 DB（从 `row_cache` 取） | `row_cache` |

### FormulaContext 扩展

```python
@dataclass
class FormulaContext:
    # 既有字段不变
    tb_data: dict[str, dict[str, Decimal]]
    row_cache: dict[str, Decimal]
    prior_tb_data: dict[str, dict[str, Decimal]]
    note_data: dict[str, dict[str, Decimal]]
    wp_data: dict[str, dict[str, Decimal]]
    aux_data: dict[str, dict[str, Decimal]]
    adj_data: dict[str, dict[str, Decimal]]
    default_column: str = "期末余额"
    # ── 新增（底稿预填充专用） ──
    ledger_data: dict[str, dict[str, Decimal]] = field(default_factory=dict)
    # key = "{account_code}:{direction}:{period}" → Decimal
    ledger_detail_data: dict[str, list[dict]] = field(default_factory=dict)
    # key = "{account_code}:{period}:{amount_filter}" → [{voucher_date, ...}]
```

### 批量查 DB 的实现

每种数据源只查一次，去重后按类型构建 WHERE IN：

```python
async def _load_tb(db, project_id, year, codes) -> dict[str, dict[str, Decimal]]:
    """复用 TrialBalanceResolver 口径（前缀聚合 + COLUMN_ALIASES）。"""

async def _load_ledger(db, project_id, year, specs) -> dict[str, dict[str, Decimal]]:
    """specs = [(account, direction, period), ...]"""

async def _load_aux(db, project_id, year, specs) -> dict[str, dict[str, Decimal]]:
    """specs = [(account, aux_type, aux_code, column), ...]"""
```

## §3 L1 handler 实装（R2）

从占位改为真实——从 `ctx` 的新字段取值：

```python
def _handle_ledger(args, ctx, trace):
    code, direction, period = _extract_string_args(args, ctx, trace)[:3]
    key = f"{code}:{direction}:{period}"
    val = ctx.ledger_data.get(key, Decimal("0"))
    trace.append(f"LEDGER('{code}','{direction}','{period}') = {val}")
    return val
```

## §4 prefill_engine 收敛（R3）

### Before

```python
for f in formulas_found:
    result = await engine.execute(db, project_id, year, ft, params)  # 旧 API，逐格查 DB
```

### After

```python
# 一次预载全部数据源
texts = [f["original"] for f in formulas_found]
ctx = await preload(db, project_id, year, texts, adj_exclude_origins=frozenset())
# 逐格求值（纯同步，无 DB 调用）
for f in formulas_found:
    result = execute(f["original"].lstrip("="), ctx)
```

### 性能收益

- 旧路径：N 个公式格 × 每格 1~3 次 DB 查询 = O(N) 次 DB round-trip
- 新路径：扫描→批量查（去重后约 10~20 次查询）→ N 次纯内存求值 = O(1) 次 DB round-trip

### 兼容性

- `resolve_extended_formula` 保留签名，内部改为 `preload([formula]) → execute`
- `_parse_args` / `_parse_period_range` / `scan_formulas` / `FormulaCell` 保留
- `prefill_workpaper_real` 的 openpyxl 扫描和结果写回逻辑不变

## §5 ADJ 口径显式化

```python
# 底稿预填充
ctx = await preload(..., adj_exclude_origins=frozenset())  # 不排 origin

# 报表生成
ctx = await preload(..., adj_exclude_origins=frozenset({"workpaper"}))  # 排 workpaper
```

参数名使用 `adj_exclude_origins` 而非 `adj_mode`，与 `adjustment_amount_source.adj_net_batch` 的签名一致。

## §6 渐进式路线

| Phase | 范围 | 风险 |
|-------|------|------|
| Phase 1 | FormulaContext 扩展 + preload service + L1 handler 实装 + 测试 | 低（新增代码，不改既有路径） |
| Phase 2 | prefill_engine 改走 preload → L1 + 删旧 resolver | 中（改底稿预填充主路径） |
| Phase 3 | report_engine 改走 preload（可选，收益有限——它已经走 L1 了） | 高（改报表生成主路径，合并路径 resolver 注入复杂） |

**本 spec 只做 Phase 1 + Phase 2**。Phase 3 留独立 spec（report_engine 的 regex 预替换虽然不优雅，但已经走 L1 内核，安全收益有限）。

## §7 不做的事

1. `FormulaEngine.execute`（旧 API 路由入口）—— 已废弃（无前端消费者），保留兼容但不改
2. report_engine 的 `ReportFormulaParser` —— 已走 L1，渐进式第三步
3. `PREV()` 的跨年度底稿取数 —— 数据模型缺 year 列，留独立 spec
4. `LEDGER_DETAIL` 返回列表而非 Decimal —— L1 handler 返回行数（Decimal），调用方如需明细走独立 API


## §8 与 note-data-from-disclosure-table 对齐（R4）

并发会话 `note-data-from-disclosure-table`（28/33 已完成）已将公式推送的附注取数从「直接查 TB」改为「从披露表 sub_table_data 读取」：

- `DisclosureSourceBinding`（`disclosure_source.py`）提供 `load_disclosure_sub_table_data()` + `note_rows_from_disclosure()`
- 80 个 binding 的 `note_rows()` 优先从披露表取数，TB 降级为兜底
- 公式推送引擎支持动态建行（`_push_note_disclosure_replace` 整表替换路径）

**对 preloader 的影响**：

`_load_note` 不能再像旧 `_resolve_note_formula` 那样直接查 `disclosure_notes.table_data.rows[row_key].values[col_key]`。需要：

1. 复用 `load_disclosure_sub_table_data()` 读 `sub_table_data`
2. 用 `note_rows_from_disclosure()` 按子表 + 列名取值
3. 构建 `ctx.note_data[section][field]` 时，key 须含行标签（动态行）

```python
async def _load_note(db, project_id, year, note_refs, template_type):
    """从披露表取附注值。"""
    from app.services.formula_push.bindings.disclosure_source import (
        load_disclosure_sub_table_data,
    )
    out = {}
    for section, field in note_refs:
        # 按 wp_code 查 sub_table_data → 按字段取值
        sub = await load_disclosure_sub_table_data(db, project_id, year, wp_code, template_type)
        if sub:
            rows = note_rows_from_disclosure(sub, table_name, wp_code, fields=(field,))
            for r in rows:
                key = f"{section}:{r['label']}:{field}"
                out.setdefault(section, {})[key] = Decimal(str(r.get(field, 0)))
    return out
```

**NOTE() handler 适配**：L1 的 `_handle_note` 需要按 `NOTE('section','field','row_label')` 三参形式从 `ctx.note_data` 取值，支持动态行标签匹配。
