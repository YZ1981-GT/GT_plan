# M 权益循环底稿优化 — Design

> **Spec**: `workpaper-m-equity-cycle` | **版本**: v1.0 | **配套**: requirements.md v1.0

## ADR 索引

| ADR | 标题 | 决策摘要 |
|-----|------|---------|
| ADR-M1 | 合并+历史过滤 | 复用现有（4命中，0代码改动）|
| ADR-M2 | VR 规则 | 2 条 VR + consistency_gate |
| ADR-M3 | prefill 维度 | 4-arg AUX + 末尾空格 sheet |
| ADR-M4 | 权益变动引擎 | 6 列汇总 + apply_to_sheet |

---

## ADR-M1: 合并（Sprint 0 实测）

```python
N_m_raw_sheets = 102
N_m_historical_sheets = 4   # 3"修订前" + 1"-删除"（现行 regex 已覆盖）
N_m_dedup_sheets = 65       # 102 - 4 - 33 = 65
N_m_trailing_space = 3      # M6A / M7A / M8A
```
决策：复用 `_merge_sheets_dedup` + `_should_skip_historical_sheet`，0 代码改动。

---

## ADR-M2: VR 规则

```json
[
  {"rule_id": "VR-M6-01", "severity": "blocking", "tolerance": 1.0,
   "formula": "M6_closing = M6_opening + net_profit - surplus_reserve - dividends",
   "trigger": "M6-1 AND (PL OR M5 OR M1) saved",
   "net_profit_source": "=WP('PL','利润表','净利润') 或 =TB('4103','本年利润期末余额')"},
  {"rule_id": "VR-M2-01", "severity": "warning", "tolerance": 1.0,
   "formula": "M2_closing = M2_opening + capital_increase - capital_decrease",
   "trigger": "M2-1 saved"}
]
```
VR-M6-01 涉及利润表 → 汇总类规则时机铁律（至少 1 个来源已保存才触发）。

---

## ADR-M3: prefill 维度

**Sprint 0.X 实测结果（2026-05-20）**：
- 4001 实收资本：**有** aux（aux_type='客户'，3 子科目 9 distinct entries）→ M2 保留 =AUX(4-arg)
- 4002 资本公积：**无** aux → M4 用 =TB
- 4101 盈余公积：**无** aux → M5 用 =TB
- 4104 利润分配：**无** aux → M6 用 =TB+=WP
- **不降级**：M-F6 目标维持 ≥ 82 cells

| sheet | cells | 公式 | 备注 |
|-------|-------|------|------|
| M2 明细 | ≥6 | =AUX(4-arg) | 按股东维度 |
| M4 明细 | ≥6 | =TB | 4002.01/02 |
| M5 明细 | ≥4 | =TB | 法定/任意 |
| M6 变动 | ≥8 | =TB+=WP | 跨底稿引用利润表 |
| M9 明细 | ≥4 | =TB | OCI 分项 |
| M10 明细 | ≥2 | =TB | 优先股/永续债 |

**末尾空格铁律**：`'未分配利润实质性程序表 M6A '` / `' 专项储备实质性程序表 M7A '` / `'一般风险准备实质性程序表 M8A '`
**降级**：无 aux → 仅=TB/=PREV，≥20 cells

---

## ADR-M4: 权益变动引擎

```
POST /api/projects/{pid}/workpapers/{wid}/m6/equity-movement
Request: {opening_balances{}, net_profit, dividends, surplus_reserve, capital_reserve_changes, oci_changes}
Response: {closing_balances{}, movement_summary{}, is_llm_stub, applied_to_sheet}
```
写回：`parsed_data.equity_movement[sheet]`；RBAC：`require_project_access("edit")`

---

## Correctness Properties

| # | Property | 验证 |
|---|---------|------|
| CP-1 | VR-M6-01: drift∈[-2,2], passes↔|drift|<tol | PBT 200+9 |
| CP-2 | 8 类 sheet 分组完备（恰好 1 类）| PBT 200 |
| CP-3 | ref_id 全局唯一+闭区间 | PBT 50 |
| CP-4 | Sheet 名归一化幂等 | PBT 100 |

---

## 错误处理

| 场景 | 处理 |
|------|------|
| VR-M6-01 利润表未保存 | skip 不 blocking |
| 权益变动引擎 opening=空 | 400 |
| AUX 无匹配 | COALESCE→0 |
| IPO codes=[] | empty result |
