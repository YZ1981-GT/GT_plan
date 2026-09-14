# Design Document

## Overview

在**不改动底稿→审定表→TB 既有链路**的前提下，新增一条**底稿级调整 → 集中式登记**的汇聚通道（strangler，opt-in、逐循环、可回退），并建立集中登记复核状态回流到底稿的只读展示；同时通过 `origin` 过滤消除试算表双写重复计算。

核心策略：
- **前端显式汇聚**（非后端猜键）：底稿调整 tab 已知自身行 schema 与科目上下文，由共享 composable `useAdjustmentCentralSync` 把当前分录组映射为标准 `line_items` 调用新端点。避免后端维护 ~30 种底稿调整键 schema。
- **幂等 by `source_ref`**（`{wp_id}:{item_id}`）：重存更新、删除清理。
- **口径唯一**：`origin='workpaper'` 条目**不进 recalc 路径**（已由审定表 writeback 体现在 `audited_amount`），只作集中审阅/导出/溯源。`origin='manual'`（含旧数据 NULL）维持既有 recalc 行为不变。

## Architecture

```
底稿调整 tab (useXAdjustment)
   │  保存 rows → checklist_responses (既有,不变)
   │  X-1-aje-total/rje-total → 审定表 → TB.audited_amount (既有,不变)
   │
   │  [新增] "同步到集中登记" 动作
   ▼
useAdjustmentCentralSync (前端共享 composable)
   │  映射 rows → line_items(standard_account_code/debit/credit)
   │  借贷平衡预校验
   ▼
POST /api/projects/{pid}/adjustments/sync-from-workpaper   [新增端点]
   ▼
AdjustmentSyncService.sync_from_workpaper                  [新增服务]
   │  幂等 source_ref = {wp_id}:{item_id}
   │  balance 校验 / 科目解析 / origin='workpaper'
   │  写 adjustments + adjustment_entry (复用现有表)
   │  NOT publish ADJUSTMENT_CREATED (不触发 recalc)  ← Req4.2
   ▼
adjustments 表 (origin='workpaper', source_ref, source_wp_code)
   │
   ├─→ Adjustments.vue 集中管理页 (origin 筛选 + 来源底稿列 + 跳转)  ← Req3.1/5
   ├─→ 调整导出 (含 workpaper 来源)                                  ← Req5.2
   └─→ GET .../adjustments/by-source-ref → 底稿侧只读复核状态回流    ← Req3.2/3.3

recalc_adjustments (既有服务)
   └─ [改] WHERE origin != 'workpaper' (NULL 视为 manual)  ← Req4.2 消除双计
```

## Data Models

### Adjustment 扩列（迁移 V124）

`adjustments` 表新增两列（幂等 `information_schema` 守护）：

| 列 | 类型 | 说明 |
|----|------|------|
| `origin` | `VARCHAR(20)` DEFAULT `'manual'` NOT NULL | 来源：`manual`（手工录入）/ `workpaper`（底稿汇聚） |
| `source_ref` | `VARCHAR(120)` NULL | 底稿溯源键 `{wp_id}:{item_id}`，`origin='workpaper'` 时非空 |

索引：`CREATE UNIQUE INDEX idx_adjustments_source_ref ON adjustments(source_ref) WHERE source_ref IS NOT NULL AND is_deleted = false`（同 source_ref 至多一个活跃分录组，支撑幂等）。ORM `Adjustment` 同步声明（drift=0）。`adjustment_entry` 表不变（复用既有明细行结构）。

### AdjustmentSyncRequest（新增请求 schema）

```
year: int
wp_id: UUID
item_id: str                    # 底稿分录组 checklist item_id
source_wp_code: str             # 来源底稿编码（展示/溯源）
description: str
adjustment_type: 'aje' | 'rje'  # 由 category 映射
line_items: [{ standard_account_code?: str, account_name: str,
               debit_amount: Decimal, credit_amount: Decimal,
               report_line_code?: str }]
```

派生 `source_ref = f"{wp_id}:{item_id}"`（幂等键）。

## Components and Interfaces

### 1. 数据模型落地（迁移 V124 + ORM 同步）

见上 §Data Models。迁移文件 `V124__adjustment_origin_source_ref.sql`（幂等）+ `R124` 回滚。

| 列 | 类型 | 说明 |
|----|------|------|
| `origin` | `VARCHAR(20)` DEFAULT `'manual'` NOT NULL | 来源：`manual`（手工录入）/ `workpaper`（底稿汇聚） |
| `source_ref` | `VARCHAR(120)` NULL | 底稿溯源键 `{wp_id}:{item_id}`，`origin='workpaper'` 时非空 |

（`source_wp_code` 复用：`adjustments` 无该列，溯源底稿编码由 `source_ref` 前缀经 wp 反查，或在 sync 时冗余存入既有可用列；MVP 用 `source_ref` + join `wp_index` 反查 wp_code。若查询频繁再冗余列。）

索引：`CREATE UNIQUE INDEX idx_adjustments_source_ref ON adjustments(source_ref) WHERE source_ref IS NOT NULL AND is_deleted = false`（保证同 source_ref 至多一个活跃分录组）。

ORM `Adjustment` 同步声明 `origin` / `source_ref`（drift=0）。

### 2. `AdjustmentSyncService`（新增，`app/services/adjustment_sync_service.py`）

```python
async def sync_from_workpaper(
    self, project_id, *, year, wp_id, item_id, source_wp_code,
    description, adjustment_type, line_items, user_id,
) -> AdjustmentGroupResponse:
    """底稿调整组 → 集中登记（幂等 by source_ref）。

    1. source_ref = f"{wp_id}:{item_id}"
    2. 借贷平衡校验（∑debit==∑credit），不平衡 raise ValueError("UNBALANCED")
    3. 科目解析：line_item.standard_account_code 缺失时按 account_name 解析；
       全部失败 raise ValueError with unresolved 列表
    4. 幂等：查 source_ref 活跃组
         - 不存在 → 新建（origin='workpaper', source_ref, review_status=draft）
         - 存在且 review_status != approved → 软删旧组 + 新建
         - 存在且 approved → raise ValueError("APPROVED_LOCKED")
    5. 复用 AdjustmentService 的写入/编号逻辑；**不发 ADJUSTMENT_CREATED 事件**
    """

async def remove_by_source_ref(self, project_id, source_ref) -> int:
    """底稿删除该分录组时软删对应集中条目。"""

async def get_status_by_source_ref(self, project_id, source_ref) -> dict | None:
    """回流：返回集中条目的 review_status/rejection_reason/adjustment_no。"""
```

### 3. 路由（新增，挂 `adjustments` router 或新 `adjustment_sync.py`）

- `POST /api/projects/{project_id}/adjustments/sync-from-workpaper` — body `AdjustmentSyncRequest`；`APPROVED_LOCKED`→409，`UNBALANCED`/解析失败→400 带 unresolved。
- `GET /api/projects/{project_id}/adjustments/by-source-ref?source_ref=` — 回流状态。
- 既有 `list_entries` 加可选 `origin` 过滤参数（默认全部）。

### 4. `recalc_adjustments` 改动（`trial_balance_service`）

在聚合 `adjustments` 时增加 `WHERE (origin IS NULL OR origin != 'workpaper')`。旧数据 origin=NULL→计入（零回归）；workpaper origin→排除（避免与审定表 writeback 双计）。

### 5. 前端 `useAdjustmentCentralSync`（新增共享 composable）

```ts
useAdjustmentCentralSync(opts: {
  projectId, year, wpId, wpCode,
  itemId: string,                 // 该 tab 分录组的 checklist item_id
  buildLineItems: () => LineItem[], // tab 把自身 rows 映射为标准行
  buildMeta: () => { description, adjustmentType },
})
→ {
  syncToCentral(): Promise<void>   // 调 sync 端点 + toast
  centralStatus: Ref<{review_status, rejection_reason, adjustment_no} | null>
  refreshStatus(): Promise<void>   // 回流展示
}
```

底稿 tab：工具栏加"同步到集中登记"按钮 + 展示 `centralStatus`（复核状态 tag / 驳回原因）。逐循环接入（试点 D4-4 / K9-3 / L1）。

### 6. `Adjustments.vue` 集中管理页

- 列表加"来源"列（manual/底稿 wp_code tag）+ 顶部 origin 筛选（全部/手工/底稿）。
- `origin='workpaper'` 行提供"跳转底稿"入口（解析 source_ref 的 wp_id → 路由 WorkpaperEditor）。
- 导出含 workpaper 来源 + 来源列。

## Correctness Properties

### Property 1: 汇聚幂等
**Validates: Requirements 2.1, 7.1**
对同一 `source_ref` 连续 sync N 次（内容相同或变化），活跃集中分录组数恒为 1。

### Property 2: 借贷平衡守卫
**Validates: Requirements 1.3, 7.1**
∑debit ≠ ∑credit 的 line_items 永不写入集中登记，返回 UNBALANCED。

### Property 3: 类别→类型映射
**Validates: Requirements 1.2**
`category='报表调整'`→`rje`；`账项调整`/`其他`→`aje`（与 K/D 循环既有映射一致）。

### Property 4: TB 不双计（origin 过滤）
**Validates: Requirements 4.1, 4.2, 7.1**
recalc 聚合结果对 `origin='workpaper'` 条目金额贡献为 0；对 `origin='manual'` 与 NULL 条目贡献与改动前逐位一致。

### Property 5: 软删除清理
**Validates: Requirements 2.2, 7.1**
`remove_by_source_ref` 后该 source_ref 无活跃分录组；再 sync 可重建。

### Property 6: approved 锁定
**Validates: Requirements 2.3**
`source_ref` 对应组为 approved 时 sync 返回 APPROVED_LOCKED（409），不覆盖。

### Property 7: 溯源可跳转
**Validates: Requirements 3.1**
`origin='workpaper'` 条目 source_ref 可解析出合法 wp_id，跳转路由参数正确。

### Property 8: 回流状态一致
**Validates: Requirements 3.2, 3.3**
`get_status_by_source_ref` 返回的 review_status 与集中登记该组实际状态一致；rejected 时带 rejection_reason。

### Property 9: 零回归（手工路径）
**Validates: Requirements 6.1, 6.2**
`origin='manual'` 的 CRUD/复核/recalc/导出与改动前行为一致（除新增 origin 列/筛选）。

### Property 10: 增量可回退
**Validates: Requirements 6.3**
未接入 sync 的循环底稿行为完全不变；单循环 sync 失败不影响其他循环与既有链路。

## Error Handling

- `UNBALANCED` → 400，前端提示借贷差额。
- 科目解析失败 → 400 带 `unresolved` 行列表，前端标红待补。
- `APPROVED_LOCKED` → 409，前端提示"已复核通过，需先撤回"。
- sync 端点整体失败 → 前端 toast，**不阻断**底稿保存（Req6.1 底稿链路独立）。

## Testing Strategy

- **后端 pytest**：`AdjustmentSyncService` 幂等/平衡/类别映射/approved 锁定/软删清理（Property 1/2/3/5/6）；`recalc_adjustments` origin 过滤零回归（Property 4/9，含 NULL 兼容基线对比）；`get_status_by_source_ref` 回流一致（Property 8）。
- **属性测试（hypothesis, max_examples=5）**：同 source_ref sync N 次条目数恒 1（幂等）；随机 line_items 平衡守卫；random origin 混合下 recalc 只计 manual/NULL。
- **前端 vitest**：`useAdjustmentCentralSync` 的 rows→line_items 映射纯函数 + 类别→类型映射 + source_ref 解析出合法 wp_id（Property 3/7）。
- **零回归门**：既有 adjustment/misstatement/trial_balance 测试全绿；改动前端文件 Vite transform 200；get_diagnostics 全清。
- **Playwright（optional）**：底稿 AJE → 同步 → 集中页可见 → approved → 回流 → TB 仅计一次。

## Migration & Rollout

- **V124**：`adjustments` 加 `origin`/`source_ref` + 部分唯一索引（幂等）。ORM 同步。
- 逐循环接入 `useAdjustmentCentralSync`（试点 D4-4 → K9-3 → L1 → 其余）。
- 回退：移除 tab 按钮即停用汇聚；`origin` 过滤对 NULL 兼容，历史数据无影响。
