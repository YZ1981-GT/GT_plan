# Design Document

## Overview

把 H1 四表取数从"审定表 H1-1 分类预填一层"扩展到**明细表 H1-2（分类级）+ 折旧账面数（H1-12/H1-13）+ 项目上下文（H1-18/H1-17）+ 审定表报表行映射（H1-1）**，全部走灰度 `H1_FOUR_TABLE_EXTRACTION_ENABLED`（默认 False，关闭时逐字节等价）。

设计遵循平台既有 pilot 范式，不新造机制：

- 取数装配在 **render 策略**内（对齐 E1 `_build_four_table_prefill` / D 循环 Tier B `build_d_adjudication_prefill`），输出 `html_data.h1_four_table_prefill`。
- 前端由**纯函数 helper** 把载荷映射为各 composable 的行模型，主入口 `onMounted` 以 Persist_First 种子填充（对齐 E1 `e1FourTablePrefill.ts`）。
- 折旧总额与月度复用**已有 resolver** `h1_depreciation_monthly`（本轮 P0 已修：字段名 `voucher_date` + `get_active_filter`），只新增按对方科目的可用性探测与可选归集。
- 审定表试算核对复用 `report_account_mapping.resolve_report_line_account_codes`（对齐 E1 §七）。

## Wave 0 数据条件核实结论（真实库实证，作为设计硬约束）

| 维度 | 实证结果 | 设计结论 |
|---|---|---|
| `tb_balance` 1601/1602/1603 子科目 | 父级 + 5~7 个二级子科目齐全（房屋建筑物/机器设备/运输设备/电子设备/办公设备/家具用具/其他），1602 与 1601 一一对应 | 支撑 **Category_Level_Seed**（Req1） |
| `tb_aux_balance` 160% 维度 | 仅 87 行，`aux_type` = `FFLEX10`（3 个 name）与「项目名称」（3 行，落在 1604 在建工程） | **无资产卡片维度** → 不做 Card_Level_Detail（Req8.1） |
| `tb_ledger` 1602 `counterpart_account` | 1519 行中仅 135 行非空（≈9%） | 不作为折旧归属主源（Req3.4） |
| 按 `voucher_no` 归集同凭证借方 | 抽样凭证内混入银行存款 3.2 亿 / 应付账款 1.1 亿等无关业务（合并记账），远超当年折旧 344 万 | 凭证粒度不支持费用归属归集 → 默认**不提供**自动归集 |
| `tb_ledger` 1602 贷方合计 | 可靠（实测 3,443,913） | 支撑总额层取数与核对（Req3.1-3.3） |

## Architecture

```
四表库                     render 策略（后端，灰度门控）             前端
────────────────────────────────────────────────────────────────────────────
tb_balance 1601/1602/1603 ─► _build_h1_detail_prefill()            ─► h1FourTablePrefill.ts
  （Leaf_Account 过滤）        · 叶子过滤 + 发生额归一                  （纯函数映射 DetailRow）
                              · 分类归类 + Provenance 公式             │
                                                                      ├─► H1-2 Persist_First seed
tb_ledger 1601 借/贷合计  ─► _build_h1_ledger_movement()            ─► 明细增减 vs 序时账核对
tb_ledger 1602 贷方合计   ─► h1_depreciation_monthly (已存在)        ─► H1-12 账面折旧带入
  + counterpart 探测        _probe_counterpart_availability()          ─► H1-13 分配合计核对
related_party_registry    ─► project_context.related_parties        ─► H1-18 漏项告警
projects.audit_period_end ─► project_context.bs_date                ─► H1-17 年检过期判定
report_config             ─► resolve_report_line_account_codes()    ─► H1-1 试算核对科目溯源
```

数据流单向：四表库 → render → html_data → 前端 helper → composable 行模型。前端不新增任何直查四表库的通道。

## Components and Interfaces

### 后端

**`_h1_fixed_assets.py`（扩展，非重写）**

```python
async def _build_h1_detail_prefill(ctx: RenderContext) -> dict:
    """tb_balance 叶子 → 明细级取数载荷（Req1），**按分类聚合一行**。

    returns {
      "rows": [ { "category": "房屋及建筑物",
                  "source_codes": ["1601.01","1602.01"],
                  "cost": {"begin","debit","credit","end"},
                  "dep":  {...}, "impair": {...},
                  "needs_review": false,
                  "formula": "TB('1601.01','期末余额') + TB('1602.01','期末余额')" } ],
      "totals": {"cost":…, "dep":…, "impair":…},
      "source": "tb_balance",
    }
    """

async def _build_h1_ledger_movement(ctx: RenderContext) -> dict:
    """tb_ledger 1601 借/贷合计（Req2）。取不到返回 {"available": False}。"""

async def _probe_counterpart_availability(ctx: RenderContext) -> dict:
    """折旧对方科目可用性探测（Req3.4）。

    returns {"available": bool, "fill_rate": float, "reason": str}
    判定：1602 分录 counterpart_account 填充率 ≥ 阈值(0.8) 视为可用；
    否则 available=False 并给出中文 reason（供页面如实提示）。
    """
```

`render()` 在 Extraction_Flag 为 True 时追加 `h1_four_table_prefill`（含 detail / ledger_movement / counterpart 三段）；为 False 时输出与现状逐字节一致。所有取数各自 try/except fail-open。

`project_context` 追加 `related_parties`（查 `related_party_registry`，`is_deleted=false`）、`bs_date`、`tb_source_codes`（Report_Line_Mapping 解析结果）。

**`auto_data_resolvers/_h1_fixed_assets.py`（扩展）**

- `h1_depreciation_monthly`：已修（`voucher_date` + `get_active_filter`），本 spec 仅复用。
- 新增 `h1_depreciation_by_counterpart`：**仅在** Counterpart_Availability 满足时返回分布，否则返回 `{"available": False, "reason": …}`，不做凭证级推断。

### 前端

**`composables/h1FourTablePrefill.ts`（新建，纯函数，可单测）**

```ts
export interface H1DetailPrefillRow { /* 后端载荷结构 */ }

/** 载荷 → useH1Detail 的 DetailRow[]（Card_Level 字段一律留空） */
export function buildDetailSeedRows(payload: H1FourTablePrefill | null): DetailRow[]

/** 明细增减合计 vs 序时账发生额（Req2） */
export function buildMovementReconcile(
  rows: DetailRow[], ledger: { debitTotal: number; creditTotal: number; available: boolean },
): { increaseDiff: number | null; decreaseDiff: number | null; hasWarning: boolean; note: string }
```

**`h1/core/H1FourTableSourcePanel.vue`（新建）**：来源面板（科目码 / 公式 / 期初增减期末 / 🔄 重新取数），对齐 `E1FourTableSourcePanel.vue`。

**改动点（最小侵入）**

| 文件 | 改动 |
|---|---|
| `GtH1FixedAssets.vue` | `onMounted` Persist_First seed `H1-2-rows`；provide 取数载荷与 `bs_date`/`related_parties` |
| `H1TabDetail.vue` | 顶部挂来源面板 + 增减核对告警 + 「重新取数」 |
| `H1TabDepreciationStraight/Impair/Multi.vue` | 账面折旧「从序时账带入」（Persist_First） |
| `H1TabDepreciationAlloc.vue` | 分配合计 vs 序时账折旧合计核对；对方科目归集仅在 available 时展示 |
| `H1TabRelatedParty.vue` | 关联方登记表漏项告警 + 一键补充 |
| `H1TabTitleVehicle.vue` | 年检过期判定优先用注入 `bs_date` |
| `H1TabAdjudication.vue` | 试算核对来源科目码溯源展示 |

## Data Models

**取数载荷（`html_data.h1_four_table_prefill`）**

```jsonc
{
  "enabled": true,
  "detail": { "rows": [ { "category": "房屋及建筑物",
                          "source_codes": ["1601.01", "1602.01"],
                          "cost":  { "begin": 0, "debit": 0, "credit": 0, "end": 41049967.97 },
                          "dep":   { "begin": 0, "debit": 0, "credit": 0, "end": 19168421.47 },
                          "impair":{ "begin": 0, "debit": 0, "credit": 0, "end": 0 },
                          "needs_review": false,
                          "formula": "TB('1601.01','期末余额') + TB('1602.01','期末余额')" } ],
               "totals": { "cost": 51188971.32, "dep": 28063493.29, "impair": 0 } },
  "ledger_movement": { "available": true, "debit_total": 0, "credit_total": 0 },
  "counterpart": { "available": false, "fill_rate": 0.089,
                   "reason": "序时账未记录对方科目（填充率 9%），且凭证为合并记账，无法按费用归属自动归集" }
}
```

**H1-2 seed 行**：复用 `useH1Detail.DetailRow`（不新增字段）。取数只填 `category`/`name`/未审期初增减期末三段与 `remark`（来源标注）；`assetNo`/`acquisitionDate`/`usefulLife`/`salvageRate`/`location`/`department` 等 Card_Level 字段留空。

**存储键**：沿用 `H1-2-rows`（不新增键，避免第二真源）。取数是否已执行由行 `remark` 的来源标注判定，不引入新状态键。

## Correctness Properties

### Property 1: 叶子过滤不双算
从 `tb_balance` 汇总时父级科目被排除，取数合计等于叶子之和。
**Validates: Requirements 1.2, 6.4**

### Property 2: Persist_First 不覆盖
`H1-2-rows` 非空时 seed 不改变任何既有行；仅显式「重新取数」才覆盖取数行且保留手工新增行。
**Validates: Requirements 1.3, 7.2**

### Property 3: 发生额非负归一
无论账套把贷方类发生额存正数或负数，输出 debit/credit 均为非负，且备抵段满足 期末 = 期初 − 借 + 贷。
**Validates: Requirements 1.1, 1.2**

### Property 4: 卡片级字段不编造
seed 行的 Card_Level 字段恒为空字符串或 0 的初值，不从科目级数字派生。
**Validates: Requirements 1.5, 8.1**

### Property 5: 空数据不产行
`tb_balance` 无 160% 数据时 `detail.rows` 为空数组，前端不生成任何行。
**Validates: Requirements 1.6, 8.3**

### Property 6: 灰度关闭逐字节等价
Extraction_Flag 为 False 时 render 输出与实现前完全一致（无 `h1_four_table_prefill` 键），前端无取数入口。
**Validates: Requirements 6.1, 6.2**

### Property 7: fail-open 不阻断
任一取数环节抛错时该段返回空/`available:false`，render 与页面正常返回。
**Validates: Requirements 6.3**

### Property 8: 序时账核对区分"无数据"与"一致"
`ledger_movement.available` 为 false 时核对显示未取到，不显示差异 0 或"一致"。
**Validates: Requirements 2.3**

### Property 9: 核对只读
增减核对与折旧合计核对不修改任何明细/折旧行数据。
**Validates: Requirements 2.4**

### Property 10: 对方科目归集按可用性门控
`counterpart.available` 为 false 时不提供任何按对方科目的自动归集数字，只输出中文原因。
**Validates: Requirements 3.4**

### Property 11: 数据集隔离
所有四表查询经数据集有效过滤入口，多数据集项目取数结果不随 staged/superseded 数量变化。
**Validates: Requirements 3.1, 9.2**

### Property 12: 报表行映射回退零回归
项目未配置报表行公式时试算核对科目码等于硬编码 1601/1602/1603。
**Validates: Requirements 5.2**

### Property 13: 关联方空清单不产告警
关联方登记表为空时漏项告警计数为 0 且显示空态提示。
**Validates: Requirements 4.3**

## Error Handling

- 取数每段独立 try/except，异常记 `logger.warning` 并返回空/`available:false`（Property 7）。
- 前端 seed 包在 try/catch 内，失败不影响 H1-2 手工编辑。
- 「重新取数」失败给 `ElMessage.warning`，不清空既有行。
- 分类归类兜底为「其他设备」并标 `needs_review`，绝不丢弃金额（Req8.2）。

## Testing Strategy

- **后端单测**：叶子过滤 / 发生额归一 / 空数据 / fail-open / 灰度等价（characterization 基线对比开关两态）/ counterpart 探测阈值 / Report_Line_Mapping 回退。
- **前端单测**：`h1FourTablePrefill.ts` 纯函数（行映射、Card_Level 留空、核对差异与 available 语义）；Persist_First 行为。
- **契约守卫**：断言 H1 后端四表查询全部经 `get_active_filter`；断言未新增第二套取数口径（`_build_h1_detail_prefill` 为唯一明细取数入口）。
- **live 验证**：对已导入余额表的真实项目跑进程内脚本，核对 detail totals 与 `trial_balance` 1601/1602 一致（不重启共享后端）。
- **Playwright**（可选）：灰度开启的实例化项目上验证 H1-2 seed → 来源面板 → 重新取数 → 增减核对告警链路。
