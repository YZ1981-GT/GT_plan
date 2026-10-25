# M2/M3/M4/M7/M10 双向回写管线 · 设计

## 总体策略

以 `m-cycle-bidirectional-pipeline`（M1/M5/M8/M9）为参照，为 M2/M3/M4/M7/M10 五条 entry 走通 `template → instrumentation → contract → bundle → representation → evidence → bidirectional` 的完整 DAG。

**核心决策**：
- authority model = `projection_contract`（与 D/M1/M5 同型）
- 受管 sheet：只覆盖明细表（`xx-2`），审定表全公式不做 instrumentation
- M2 特殊：两张同码明细表各自有独立 sheet_key 和字段映射
- M4 特殊：明细表有两级分组结构（分组合计行 = SUM 公式，子项行 editable）
- M10 特殊：明细表 30 列宽表，三段式结构（优先股/永续债/转股特征）
- 共享内核：`phase5_m_cycle_common.py`（与 M1/M5/M8/M9 同一骨架）

## 五条 entry 的受管 sheet 设计

### M2（实收资本，4001 权益类）

🔴 **两张同码明细表**（BP-8 已修的 sheet_key 判别位）：

| sheet | 受管 | sheet_key | 字段 | 说明 |
|---|---|---|---|---|
| 明细表（非上市公司）M2-2 | ✅ | m201-unlisted-managed | 15e+9f=24 | 审定表引用此表 |
| 明细表（上市公司）M2-2 | ✅ | m202-listed-managed | 21e+15f=36 | M 全域最宽 sheet |
| 审定表M2-1 | ❌ | — | 0e+11f | 全公式引用非上市明细表 |
| 其余 8 sheet | ❌ | — | — | 程序表/附注/AJE/检查表/GT_Custom |

### M3（库存股，4102 权益类）

| sheet | 受管 | sheet_key | 字段 |
|---|---|---|---|
| **明细表M3-2** | ✅ | m301-managed | 14e+5f=19 |
| 审定表M3-1 | ❌ | — | 0e+11f（全公式） |
| 其余 8 sheet | ❌ | — | 程序表/附注/AJE/汇率/检查表/参考/GT_Custom |

### M4（资本公积，4002 权益类）

🔴 两级分组结构：R10/R15 一级分组（SUM），R11~R14/R16~R19 子项。

| sheet | 受管 | sheet_key | 字段 |
|---|---|---|---|
| **明细表M4-2** | ✅ | m401-managed | 12e+5f=17 |
| 审定表M4-1 | ❌ | — | 1e+10f |
| 其余 7 sheet | ❌ | — | 程序表/附注/AJE/检查表/GT_Custom |

### M7（专项储备，4301 权益类）

| sheet | 受管 | sheet_key | 字段 |
|---|---|---|---|
| **明细表M7-2** | ✅ | m701-managed | 13e+5f=18 |
| 审定表M7-1 | ❌ | — | 1e+10f |
| 其余 8 sheet | ❌ | — | 程序表/附注/AJE/计提/检查表/GT_Custom |

### M10（其他权益工具，4001 权益类）

🔴 30 列宽表，三段式结构。

| sheet | 受管 | sheet_key | 字段 |
|---|---|---|---|
| **明细表M10-2** | ✅ | m1001-managed | 24e+6f=30 |
| 审定表M10-1 | ❌ | — | 1e+10f |
| 其余 9 sheet | ❌ | — | 程序表(含Q10A修订前)/附注/AJE/检查表/GT_Custom |

## Contract JSON 概览

| entry | contract_id | sheets | 字段总数 | editable | formula |
|---|---|---|---|---|---|
| M2 | m2.paid_in_capital | 2 | 60 | 36 | 24 |
| M3 | m3.treasury_stock | 1 | 19 | 14 | 5 |
| M4 | m4.capital_reserve | 1 | 17 | 12 | 5 |
| M7 | m7.special_reserve | 1 | 18 | 13 | 5 |
| M10 | m10.other_equity_instruments | 1 | 30 | 24 | 6 |
| **合计** | — | **6** | **144** | **99** | **45** |

## BP 解除路径

```
Phase 1 ✅ : contract JSON × 5 + provider × 5 + adapter 注册
              ↓
Phase 2 [ ]*: DAG 发布（template → instrumentation → contract → bundle）× 5
              阻塞：真库无 M 循环底稿 working_paper 记录
              ↓
Phase 3 [ ]*: finalize_candidate × 5 → published representation
              阻塞：需 Phase 2 产物
              ↓
Phase 4 [ ]*: OO 9.4 探针 × 5 → evidence verified
              阻塞：需真实 OO 环境
              ↓
Phase 5 [ ]*: 端到端闭环 + slice 更新 → migration_state = bidirectional
              阻塞：真库无业务载荷
```

## 与前置 spec 的关系

| 前置 spec | 本 spec 消费的产物 |
|---|---|
| `m2-m3-m4-m7-m10-sheet-map-drift-and-collapse` | BP-4 修后的 SHEET_MAP 真名、BP-8 的 sheet_key 判别位、BP-12 修后的 M10 附注 sheet 名 |
| `m-cycle-sync-foundation-and-first-canary` | MC-1~29 共同裁决、M6 canary 的正面样板 |
| `m-cycle-bidirectional-pipeline` | M1/M5/M8/M9 的 contract 格式参照、phase5_m_cycle_common 共享内核 |

## 风险与降级

| 风险 | 影响 | 降级方案 |
|---|---|---|
| 真库无 M 循环底稿 | Phase 2~5 无法执行 | Phase 1 先行，后续阶段标 `[ ]*` |
| OO 9.4 环境不可用 | Phase 4 无法执行 | 标 `[ ]*` |
| M2 两张明细表结构差异 | contract 复杂度高 | 已各给独立字段映射（60 字段） |
| M10 宽表 30 列 | contract 撰写工作量大 | 已覆盖全部 30 列 |
