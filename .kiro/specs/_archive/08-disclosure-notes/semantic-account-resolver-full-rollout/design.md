# Design Document

## Overview

将 70 个 render 策略从「硬编码前缀 / `report_line_accounts`」迁移到「`semantic_account_resolver` 语义驱动逐项目定位」。核心设计 = **per-cycle `_specs.py` 声明式规格 + render 薄壳委托 + 统一输出契约**。

## Architecture

### 分层结构

```
                    ┌──────────────────────────────────────────┐
                    │  四表取数共享件 (four_table/)             │
                    │  ├─ semantic_account_resolver.py (核心)   │
                    │  ├─ leaf_aggregation.py (叶子聚合)        │
                    │  ├─ pl_occurrence.py (损益类发生额)        │
                    │  ├─ g_cycle_specs.py (G1~G14, ✅已建)     │
                    │  ├─ d_cycle_specs.py (D1~D7, 新建)       │
                    │  ├─ f_cycle_specs.py (F1~F5, 新建)       │
                    │  ├─ h_cycle_specs.py (H1~H10, 新建)      │
                    │  ├─ i_cycle_specs.py (I1~I6, 新建)       │
                    │  ├─ k_cycle_specs.py (K1~K13, 新建)      │
                    │  ├─ l_cycle_specs.py (L1~L8, 新建)       │
                    │  ├─ m_cycle_specs.py (M1~M10, 新建)      │
                    │  └─ n_cycle_specs.py (N1~N5, 新建)       │
                    └──────────────────────────┬───────────────┘
                                               │ import
                    ┌──────────────────────────┴───────────────┐
                    │  render 策略 (_xx_yyy.py)                 │
                    │  _fetch_tb_data(ctx) →                    │
                    │    accounts = await resolve_semantic_...  │
                    │    leaves = select_leaves(filter_by_...)  │
                    │    → tb_values / tb_source_codes /        │
                    │      adjudication_prefill                 │
                    └──────────────────────────────────────────┘
```

### 迁移模式（模板化变更）

**资产类（D/F/G-资产/H/I/K1~K2）**：

```python
# Before
_XX_ACCOUNT_PREFIX = "1234"
async def _fetch_tb_data(ctx):
    rows = await ctx.db.execute(...)  # 硬编码 LIKE '1234%'
    # 自造 _is_leaf / _row_depth ...
    result["tb_values"] = {...}

# After
from app.services.four_table.x_cycle_specs import XX_SPEC
from app.services.four_table import (
    resolve_semantic_accounts, select_leaves, filter_by_prefixes,
    to_leaf_rows, aggregate_leaves, parent_totals,
)

async def _fetch_tb_data(ctx):
    accounts = await resolve_semantic_accounts(ctx, XX_SPEC)
    prefixes = accounts.codes_of("gross")
    if not prefixes:
        result["tb_source_codes"] = accounts.as_dict()
        return result
    # ... 标准叶子聚合流程
    result["tb_source_codes"] = accounts.as_dict()
    result["adjudication_prefill"] = build_adjudication_prefill(leaves)
```

**负债/权益类（J/K3~K7/L/M）** — 同上但 spec 声明 `is_liability=True`。

**损益类（G11~G14/K8~K13/N4/N5/I6/H10/L8）** — 额外引用 `pl_occurrence`：

```python
from app.services.four_table.pl_occurrence import fetch_pl_occurrence, PL_POSITIVE_SIDE

async def _fetch_tb_data(ctx):
    accounts = await resolve_semantic_accounts(ctx, XX_SPEC)
    prefixes = accounts.codes_of("gross")
    occurrence = await fetch_pl_occurrence(ctx, prefixes, PL_POSITIVE_SIDE["XX"])
```

### per-cycle `_specs.py` 结构

```python
"""X 循环语义科目定位规格 — 跨 X1~Xn 单一真源。"""
from .semantic_account_resolver import SemanticAccountSlot, SemanticAccountSpec

# 通用否决词（跨循环复用，从 g_cycle_specs 提升）
_PROVISION_WORDS = ("减值准备", "坏账准备", "跌价准备", "累计折旧", "累计摊销", "减值损失")

X1_SPEC = SemanticAccountSpec(
    row_code="BS-xxx",
    slots=(
        SemanticAccountSlot(
            key="gross", names=("科目名",), exclude_names=_PROVISION_WORDS,
            fallback_standard_codes=("1xxx",), label="中文名",
        ),
    ),
)

X_CYCLE_SPECS: dict[str, SemanticAccountSpec] = {"X1": X1_SPEC, ...}
X_PL_CYCLES = frozenset({...})  # 仅损益类循环有

def spec_of(wp_code: str) -> SemanticAccountSpec | None:
    return X_CYCLE_SPECS.get(str(wp_code or "").strip().upper())
```

### 七个优化的设计决策

| # | 优化 | 设计 |
|---|------|------|
| 4.1 | 统一 `adjudication_prefill` | 纯函数 `build_standard_adjudication_prefill(leaves: list[LeafRow]) -> list[dict]`，输出 `[{code,name,opening,closing}]`，禁桶预聚合 |
| 4.2 | `pl_occurrence` 接入 | 各损益 _specs.py 声明 `PL_POSITIVE_SIDE`（credit/debit），render 调 `fetch_pl_occurrence` |
| 4.3 | `is_liability` 声明 | L/M 全部 + J1/J2 + K3~K7 的 spec 里 `is_liability=True` |
| 4.4 | per-cycle 守卫 | 参数化 `@pytest.mark.parametrize("wp_code,spec", CYCLE_SPECS.items())` 检查 row_code 存在/兜底码存在/互斥 |
| 4.5 | 前端溯源面板 | `WpFourTableSourcePanel.vue` 已支持 `slots`，无需改组件；各循环宿主确保 `:html-data` 传递即可 |
| 4.6 | CI job | `governance-checks.yml` 加 `semantic-resolver-batch-{1..6}` |
| 4.7 | 降级守卫 | `test_no_new_report_line_accounts_import.py` 扫 render 目录新增文件禁 import |

## Components and Interfaces

### 输入接口

| 组件 | 输入 | 来源 |
|------|------|------|
| `resolve_semantic_accounts` | `ctx: RenderContext`, `spec: SemanticAccountSpec` | render 策略 |
| `select_leaves` | `rows: list[LeafRow]` | `to_leaf_rows(db_rows)` |
| `filter_by_prefixes` | `rows, prefixes: list[str]` | `accounts.codes_of("gross")` |
| `fetch_pl_occurrence` | `ctx, prefixes, side: str` | 损益类 render |

### 输出接口（render → 前端）

```python
project_context = {
    "tb_source_codes": accounts.as_dict(),  # SemanticAccountResult 序列化
    # 含扁平投影 gross/provision/resolved_from（向后兼容）
    # + slots/conflicts/unmapped_candidates/chart_available（新消费点）
}
html_data = {
    "project_context": project_context,
    "tb_values": {...},                     # 聚合后金额
    "adjudication_prefill": [...],          # 逐叶子明细
}
```

## Data Models

### SemanticAccountSpec 实例化约束

- `names` 里的科目名必须与 `account_chart source='standard'` 的一级科目名逐字一致
- `exclude_names` 不得为空元组（显式填 `()` 时 lint 告警）
- `fallback_standard_codes` 可为空（= 该科目按准则不存在一级标准科目，如 E1 的 `finance_co`/`digital`）
- 同一 `_specs.py` 内不得有两个 spec 的兜底码相同（跨循环互斥由 per-cycle 守卫钉死）

### 迁移判定矩阵

| 现状 | 目标 | 条件 |
|------|------|------|
| `report_line_accounts` + 正确兜底 | `semantic_account_resolver` | 直接迁 |
| `report_line_accounts` + 错误兜底 | `semantic_account_resolver` + 修 spec 兜底 | 核对 `report_config` |
| 硬编码前缀 + 正确 | `semantic_account_resolver` | 直接迁 |
| 硬编码前缀 + 错误 | `semantic_account_resolver` + 修 spec names | 核对 `account_chart` |
| 独立子模块（D1/D4/F2） | 子模块改引 semantic resolver | 只改最外层 |

## Correctness Properties

### Property 1: 扁平投影兼容
**Validates: Requirements 5.1**

迁移后 `tb_source_codes` 的 `gross`/`gross_standard`/`provision`/`provision_standard` 与迁移前**值等价**（在「本项目科目表可用 + report_config 无错码」的项目上完全相等；在有错码项目上允许正确值替代错误值）。

### Property 2: 叶子聚合等价
**Validates: Requirements 2.4**

`select_leaves` + `filter_by_prefixes` 的输出 ⊇ 旧实现的输出（旧实现可能因 `_row_depth` 丢叶子，新实现不丢），且 `Σleaves == parent_amount`。

### Property 3: 损益类取发生额非零
**Validates: Requirements 8.2, 8.3**

对有真实余额的项目，损益类循环的 `pl_occurrence` 输出 ≠ 0（旧 `debit - credit` 结构性 = 0）。

### Property 4: 跨循环互斥
**Validates: Requirements 4.4**

所有 `_specs.py` 的 `fallback_standard_codes` 无交集（同一标准码不得出现在两个循环的 gross 槽，备抵可与原值循环的 provision 重合）。

### Property 5: 负债/权益类不误判备抵
**Validates: Requirements 4.3**

声明 `is_liability=True` 的 spec，其 `resolve_semantic_accounts` 结果的 `gross.codes` 不为空（旧实现因 `direction='credit'` 被判成备抵而导致 gross 为空）。

### Property 6: 新文件禁引旧模块
**Validates: Requirements 4.7**

迁移完成后 render 策略目录内**新增文件**（`git diff --diff-filter=A`）不得含 `from app.services.four_table.report_line_accounts import`。

### Property 7: render 输出完整
**Validates: Requirements 2.5, 2.6**

每个迁移后的策略的 `_fetch_tb_data` 返回值必须含 `tb_source_codes`（dict）+ `adjudication_prefill`（list，可为空）两个键。

## Notes

- G 循环 `g_cycle_specs.py` **已完成不需新建**，批 1 只是让 10 个策略改引它
- K 循环 K1/K2 有独立的 `k1_account_scope.py`/`k2_account_scope.py`（`ReportLineAccountSpec`），迁移时收敛到 `k_cycle_specs.py` 的 `SemanticAccountSpec` 并让旧文件 re-export
- D 循环 D1 有 `d1_account_resolver.py` + D2~D7 走 `d_cycle_extraction/` 子模块，迁移只改最外层 `_fetch_tb_data`
- `_g6_other_bond_investment_main_service.py` 是子策略（被 main 调用），须一并迁移
- `_g7_long_term_equity_main_service.py` 同理
