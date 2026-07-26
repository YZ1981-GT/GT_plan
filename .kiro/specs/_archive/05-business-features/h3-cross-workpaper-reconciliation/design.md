# Design Document

## Overview

为 H3 投资性房地产底稿补齐三组跨底稿勾稽面板（互转↔H1/H2、租金↔D4/TB6051、产权抵押↔L1/L3），复用已验证的 `wp-id-by-code` + `checklist-responses` pull 范式。

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  GtH3InvestmentProperty (主入口)                                  │
│  ├── H3TabTransferReview (H3-6) ← 勾稽面板①                      │
│  │   └── h3TransferReconcile.ts (纯函数 pull + reconcile)       │
│  ├── H3TabRentalIncome (H3-14) ← 勾稽面板②                      │
│  │   └── rentalForDisclosure (crossSheet 既有) + tb_6051       │
│  └── H3TabTitleCheck (H3-12) ← 勾稽面板③                        │
│      └── h3MortgageReconcile.ts (纯函数 pull + reconcile)       │
├─────────────────────────────────────────────────────────────────┤
│  后端 _h3_investment_property.py                                  │
│  └── project_context.tb_6051_audited (新增)                      │
└─────────────────────────────────────────────────────────────────┘
```

## Components and Interfaces

### 1. `h3TransferReconcile.ts`（新建，composables/）

纯函数模块（无 composable state，供 H3-6 组件调用）：

```typescript
interface TransferReconcileResult {
  h3FromH1: number          // H3 自用→投资合计
  h1DisposalToInvest: number | null  // H1 转出到投资性房地产合计
  h3ToH1: number            // H3 投资→自用合计
  h1AdditionFromInvest: number | null  // H1 从投资性房地产转入合计
  h3FromH2: number          // H3 在建→投资合计
  h2CipToInvest: number | null  // H2 转出到投资性房地产合计
  diffFromH1: number | null  // H3−H1 差额（null=H1数据不可用）
  diffToH1: number | null
  diffFromH2: number | null
  status: 'ok' | 'warning' | 'unavailable'
}

export async function pullH1TransferForH3(projectId: string): Promise<{...}>
export async function pullH2TransferForH3(projectId: string): Promise<{...}>
export function buildH3H1Reconcile(h3: TransferSummary, h1: {...}): TransferReconcileResult
```

### 2. `h3MortgageReconcile.ts`（新建，composables/）

```typescript
interface MortgageReconcileResult {
  h3RestrictedTotal: number   // H3 已抵押合计
  l1PledgeTotal: number | null  // L1 含投资性房地产质押
  l3PledgeTotal: number | null  // L3 含投资性房地产抵押
  lTotal: number | null       // L1+L3
  diff: number | null         // H3−(L1+L3)
  status: 'ok' | 'warning' | 'unavailable'
}

export async function pullL1PledgeForH3(projectId: string): Promise<number | null>
export async function pullL3PledgeForH3(projectId: string): Promise<number | null>
export function buildH3MortgageReconcile(h3Total: number, l1: number|null, l3: number|null): MortgageReconcileResult
```

### 3. 后端 `_h3_investment_property.py` 扩展

`_load_project_context` 新增 `tb_6051_audited`：
```python
# 6051 其他业务收入（损益贷方，audited_amount 正数）
result = await ctx.db.execute(sa.text("""
    SELECT SUM(audited_amount) AS total
    FROM trial_balance
    WHERE project_id = :pid AND year = :year AND is_deleted = false
      AND standard_account_code LIKE '6051%'
"""), {...})
project_ctx["tb_6051_audited"] = float(row.total) if row and row.total else None
```

### 4. UI 勾稽面板组件模式

三处面板统一用 el-card（复用 H1 CIP↔H2 勾稽面板范式）：
- 标题行：「勾稽 H1/H2 互转」/「勾稽 D4/TB 6051 租金」/「勾稽 L1/L3 抵押」
- 表格：左列=本方(H3)/右列=对方/差异列
- 状态 tag：success「一致」/ warning「存在差异」/ info「对方数据不可用」
- 「重新拉取」按钮（手动触发 pull）
- GtIndexChip 跳转

## Data Models

无新 DB 表/迁移。数据流纯前端 pull + 内存计算。

## Correctness Properties

### Property 1: 互转差额精度
`buildH3H1Reconcile` 的 `diffFromH1 = h3.fromH1 − h1DisposalToInvest`，容差1元。

**Validates: Requirement 1**

### Property 2: 在建转入差额
`buildH3H2Reconcile` 的 `diffFromH2 = h3.fromH2 − h2CipToInvest`，容差1元。

**Validates: Requirement 1**

### Property 3: 投资转出差额
`buildH3ToH1Reconcile` 的 `diffToH1 = h3.toH1 − h1AdditionFromInvest`，容差1元。

**Validates: Requirement 1**

### Property 4: 租金差异方向性
`buildH3RentalReconcile`: diff = TB6051 − H3.annualTotal。diff>0→info(其他来源)，diff<0→warning(H3>TB)。

**Validates: Requirements 3, 4**

### Property 5: 抵押差额
`buildH3MortgageReconcile`: diff = h3RestrictedTotal − (l1 + l3)。

**Validates: Requirement 5**

### Property 6: pull 失败降级
任何 pull 函数 catch → 返回 null + status='unavailable'，面板显 info 不告警。

**Validates: Requirements 2, 6, 8**

### Property 7: 空数据不误报
对方数据为 null 或 0 时 diff=null，面板不显示差异告警。

**Validates: Requirement 8**

### Property 8: TB6051 为空
`project_context.tb_6051_audited === null` 时租金勾稽面板显示 info「试算表 6051 数据不可用」。

**Validates: Requirements 4, 8**

## Error Handling

- pull 函数全部 try/catch + fail-open（返回 null）
- 后端 `tb_6051_audited` 查询失败返 null（不阻塞 render）
- 前端面板 v-if 守卫（reconcileResult === null → 不渲染/显 info）
- 容差使用 `Math.abs(diff) <= 1`（1元以内视为一致）

## Testing Strategy

- 纯函数单测 vitest（h3TransferReconcile.spec.ts / h3MortgageReconcile.spec.ts）覆盖 P1-P8
- 后端 tb_6051 查询由现有 render smoke test 隐式覆盖（additive 字段 null 零回归）
- Playwright：pull 成功路径需实例化 H1/H2/L1/L3 项目，标 `*` 可选
