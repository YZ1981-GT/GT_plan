# Design Document

## Overview

H5-H10 / I1-I6 共 12 张审定表四表库取数公式预设 + render 分段 prefill + 🔄刷新入口。复用既有 `d_cycle_extraction` 通用模块（presets/anchor_registry/tier_a_seed/prefill），不新造。

## Architecture

本 spec 为 H5-H10 / I1-I6 共 12 张审定表新增 Tier A 四表库取数公式预设 + render 分段 prefill + 🔄刷新入口。

**关键架构差异（H/I vs D 循环）**：D 循环审定表有独立的 `D6-1-tb-amount` item_id 作为 TB 核对行持久锚点（Tier A seed 写入它）；H/I 循环审定表**无独立 TB 核对行锚点**——TB 核对是**运行时 computed**（`tbDifference = subtotals.audited - tbUnadjusted`），`tbUnadjusted` 来自 render 注入的 `tb_values` prop（非 checklist_responses 持久化）。

**设计决策**：

### Decision 1: Tier A 预设目标 = 审定合计聚合键（writeback 真源）

H/I 的 Tier A `TB()` 公式 target_cell 瞄准各底稿**审定合计聚合键**（如 `I5-adj-audited-total`、`I1-adj-audited-cost`），这些键由 writeback 持久化到 checklist_responses.remark、供跨底稿/审定 TB 核对消费。Tier A seed 求值后写入 render `responses_snapshot` 对应键的 remark 字段（transient 不落库，手工优先）。

对于无独立 TB 核对标量锚点的底稿（H6/I2 等），**新增标量锚点** `{X}-1-tb-amount`（remark 字段），前端 composable 读它做 TB 核对：`tbUnadjusted = parseFloat(allResponses.get('{X}-1-tb-amount')?.remark ?? '0')`。这使 Tier A seed 有确定性目标。

### Decision 2: 复用 `d_cycle_extraction` 模块，不新造

Tier A 预设注册到现有 `d_cycle_extraction_presets.json`（新增 H5-H10/I1-I6 条目）；锚点注册到 `d_cycle_anchor_registry.json`；Tier A render seed 复用 `tier_a_seed.seed_tier_a_reconciliation`（从 `resolve_effective` 读有效公式+`evaluate_wp_formula_expression` 求值）。seed_field 登记 remark（与全部 H/I FormData composable 的 `item?.remark ?? item?.conclusion` 一致）。

### Decision 3: Tier B 分段 prefill 复用 `build_d_adjudication_prefill`

各 H/I render 策略加分段 prefill（灰度门控），按各自科目前缀调用 `build_d_adjudication_prefill`：
- 资产原值段: mode='balance'，prefix=原值科目
- 备抵段: mode='balance'，prefix=备抵科目，结果 opening/closing 取 abs
- 损益段: mode='occurrence'，prefix=费用科目

### Decision 4: 前端复用 E1/H1 源面板范式

新建通用 `HiFourTableSourcePanel.vue`（参数化：`wpCode`/`accountSegments`/`refreshHandler`），审定表工具栏挂它（v-if 灰度 + htmlData.{x}_extraction_enabled）。每 H/I 底稿传自己的科目分段配置。

### Decision 5: 灰度 = 单一统一开关

`HI_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED: bool = False`（config.py，一个开关覆盖全部 12 张，简化运维）。各 render 策略在灰度开时才输出 `{x}_extraction_enabled`/`adjudication_segment_prefill` 字段。

### Decision 6: surfacing 补充（公式管理可查）

`wp_surfaced_h.py`/`wp_surfaced_i.py` 各底稿审定表 sheet（X-1）补「取数」分类条目，表达式为 `TB('科目','列')`，对齐既有「计算」/「逻辑审核」条目。

## Components and Interfaces

### 后端

| 组件 | 职责 |
|------|------|
| `config.py` | 新增 `HI_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED: bool = False` |
| `d_cycle_extraction_presets.json` | 新增 H5-H10/I1-I6 条目（每底稿 1-3 条 TB 核对标量预设） |
| `d_cycle_anchor_registry.json` | 新增 H5-H10/I1-I6 锚点段 |
| `d_cycle_extraction/presets.py::_TIER_B_PROVENANCE` | 新增 H5-H10/I1-I6 只读溯源描述 |
| 各 render 策略（`_h5_oil_gas_assets.py` … `_i6_research_development_expense.py`） | 灰度分支加 `adjudication_segment_prefill` + Tier A seed |
| `wp_surfaced_h.py` / `wp_surfaced_i.py` | 各底稿 X-1 sheet 补「取数」surfacing 条目 |

### 前端

| 组件 | 职责 |
|------|------|
| `HiFourTableSourcePanel.vue`（新建） | 通用四表取数源面板（参数化科目分段，🔄刷新+来源展示） |
| 各主入口 `GtH5`…`GtI6` | 审定表 tab 工具栏挂 HiFourTableSourcePanel（v-if 灰度） |

## Data Models

### Tier A 预设条目（per-底稿，注入 `d_cycle_extraction_presets.json`）

资产原值段：
```json
{ "anchor": "{X}-1-tb-amount", "expression": "TB('{科目}','期末余额')", "sheet_name": "{X}-1", "formula_type": "auto_calc", "description": "试算表{科目}{科目名}期末余额（审定数），供审定表 TB↔审定核对" }
```

备抵段（额外注册，如 I1 有 1702/1703）：
```json
{ "anchor": "{X}-1-tb-{contra}", "expression": "ABS(TB('{备抵科目}','期末余额'))", "sheet_name": "{X}-1", "formula_type": "auto_calc", "description": "试算表{备抵科目}累计摊销/减值期末绝对值" }
```

损益段（H10/I6）：
```json
{ "anchor": "{X}-1-tb-amount", "expression": "TB('{科目}','审定数')", "sheet_name": "{X}-1", "formula_type": "auto_calc", "description": "试算表{科目}{科目名}审定发生额" }
```

### Tier B prefill 输出结构（render response additive）

```python
html_data["adjudication_segment_prefill"] = {
    "segments": [
        {"segment": "cost", "account_prefix": "1701", "mode": "balance", "items": [...] },
        {"segment": "amort", "account_prefix": "1702", "mode": "balance", "items": [...] },
        ...
    ],
    "enabled": True
}
```

### 锚点注册（per-底稿，注入 `d_cycle_anchor_registry.json`）

```json
"H5": ["H5-1-tb-amount", "H5-1-tb-depletion", "H5-1-cost-rows", "H5-1-depletion-rows", "H5-1-impairment-rows", "H5-1-audit-note", "H5-1-audit-conclusion"],
"H6": ["H6-1-tb-amount", "H6-1-rows", "H6-1-audit-note", "H6-1-audit-conclusion"],
...
```

## Correctness Properties

### Property 1: 叶子科目防双算
WHEN `build_d_adjudication_prefill` 取某前缀子科目 THEN 只有叶子（code 不是任何其它 code 前缀）参与汇总。**Validates: Requirements 4.1**

### Property 2: 备抵科目方向正确
WHERE 科目为备抵（1632/190101/1702/1703/未确认融资费用） THEN 预设增加=`贷方发生额`、减少=`借方发生额`、余额取 ABS。**Validates: Requirements 1.3**

### Property 3: 损益取发生额非余额
WHERE 科目为损益类（6115/6602） THEN 预设用 `TB(科目,'审定数')` 取 `trial_balance.audited_amount`，不取 `tb_balance` 余额。**Validates: Requirements 1.4**

### Property 4: 手工优先不覆盖
WHERE 锚点在 `responses_snapshot` 已有非空 remark 值 THEN Tier A transient seed 跳过该锚点。**Validates: Requirements 3.3, 4.4**

### Property 5: 灰度关时零回归
WHEN `HI_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED=False` THEN render 输出与改前逐字节等价（不含 `adjudication_segment_prefill`/`{x}_extraction_enabled`）。**Validates: Requirements 6.1**

### Property 6: 预设读时收敛
WHEN 用户 wp_formula 覆盖同锚点预设 THEN `resolve_effective` 返回用户值（source=custom）；用户删除后回落预设（source=preset）。**Validates: Requirements 1.1, 2.3**

### Property 7: 锚点合法性校验
WHEN 预设库某条锚点不在 `d_cycle_anchor_registry.json` 的对应 wp_code 段 THEN 该条被丢弃+warning。**Validates: Requirements 6.4**

### Property 8: 评估器支持列名
WHEN 公式含 `借方发生额`/`贷方发生额` THEN `evaluate_wp_formula_expression` 的 `_resolve_tb._COLUMN_MAP` 正确映射到 `tb_balance.debit_amount`/`credit_amount`。**Validates: Requirements 5.2**

### Property 9: 无数据→空不报错
WHEN `tb_balance` 无该科目前缀子科目 THEN prefill 返回空列表、render 不抛异常。**Validates: Requirements 4.5**

### Property 10: 三处口径一致
WHEN 对同一科目/同一快照 THEN render prefill、公式管理 GET value、刷新求值三处结果一致（同 `get_active_filter`+同叶子判定）。**Validates: Requirements 5.1**

### Property 11: surfacing 按 sheet 过滤
WHEN 公式管理面板选中某 sheet THEN 只显示该 sheet 归属的 Tier A 预设（sheet_codes 过滤），不全显。**Validates: Requirements 2.5**

### Property 12: 刷新确认门控
WHEN 锚点已有手工值且用户点刷新 THEN 弹确认框后才覆盖；取消不动。**Validates: Requirements 3.3**

## Error Handling

- 所有四表库查询 fail-open：`try/except → logger.warning + return []`，不阻断 render。
- 公式求值失败/悬空引用 → 该锚点 seed 跳过，不产错值。
- 灰度开关关闭 → render 不输出任何预填/extraction 字段（逐字节等价，Property 5）。
- `ABS()` 评估器不支持 → Wave 0 核实后补入列名映射或改为代码侧取 abs（不在公式里用 ABS 函数），防保存 422。

## Testing Strategy

- **后端 PBT**：Property 1-5/7-10（hypothesis max_examples=5），含真实 tb_balance 模拟数据。
- **前端 vitest**：Property 6/11/12（useAcnr mock + el-segmented）。
- **契约守卫**：`check_hi_extraction_presets_contract.py`（预设 anchor ⊆ registry 锚点集 + 表达式仅 TB/SUM_TB/ABS）。
- **Playwright（可选*）**：需实例化项目+灰度开启+vLLM 在线。
