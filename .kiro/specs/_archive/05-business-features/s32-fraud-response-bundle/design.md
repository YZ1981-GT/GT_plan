# Design Document

> S32 应对 551 文提示风险核查程序聚合组件（财务造假/舞弊专项）

## Overview

将 S32 系列 13 个舞弊情形核查底稿（S32-1~S32-13）聚合为单一 `s32-fraud-bundle` 组件，内部以一行可滚动页签切换各舞弊情形核查底稿。遵循 `GtS34Bundle` / `GtA17Bundle` 已验证模式：静态 Tab 配置 + el-tabs 分发 + wp_index 查询子底稿 wp_id + 轻量 composable。

核心特征：每个 Tab 主体为 GtAProgramConsole 渲染的舞弊核查程序表；部分底稿含导引表（IC-0）与披露格式参考（IC-X）子 sheet，及「提示」长文本折叠区块。

## Architecture

```mermaid
graph TD
  A[GtWpRenderer] -->|componentType=s32-fraud-bundle| B[GtS32Bundle]
  B --> BS[useS32BundleState]
  BS -->|wpIdMap / completionMap| B
  B --> TABS[el-tabs 可滚动，13 舞弊情形]
  TABS --> P[GtAProgramConsole embedded]
  P --> SUB{含 IC-0/IC-X?}
  SUB -->|是| SS[子 sheet 分发: 导引表/披露格式参考]
  P --> TIP[提示 details 折叠区块]
  P --> CHIP[GtIndexChip]
```

## Components and Interfaces

### GtS32Bundle.vue

```typescript
interface Props {
  wpId: string
  sheetName?: string   // 'S32-6' ...
  readonly?: boolean
}

interface TabDef {
  id: string           // 'S32-1'...'S32-13'
  label: string        // 舞弊情形简称
  wpCode: string
  subSheets?: string[] // ['IC6-0','IC6-X'] 等导引/披露格式参考
  tipSheet?: string    // '提示'
}
```

13 舞弊情形（对齐 requirements 简介）：自我交易虚增利润 / 恶意串通提前确认收入 / 关联方代付成本费用 / 保荐机构PE利益输送 / 体外资金支付货款 / 互联网造假虚增收入 / 成本费用资本化 / 压缩员工薪金 / 延迟成本费用 / 资产减值估计不足 / 延迟资产转固减少折旧 / 其他粉饰业绩 / 期后业绩下滑。

### useS32BundleState composable

```typescript
export type CompletionStatus = 'completed' | 'in_progress' | 'not_started'
export interface UseS32BundleStateReturn {
  wpIdMap: ComputedRef<Record<string, string>>       // S32-x → wp_id
  completionMap: ComputedRef<Record<string, CompletionStatus>>
  progressSummary: ComputedRef<{ completed: number; inProgress: number; notStarted: number }>
  refreshCompletion: (wpCode?: string) => Promise<void>
}
```

### 后端

- **wp_code_overrides.json**：`"S32": "s32-fraud-bundle"`；`S32-1`~`S32-13` → `"skip"`
- **VALID_COMPONENT_TYPES**：新增 `"s32-fraud-bundle"`
- **htmlRendererRegistry.ts**：新增成员 `'s32-fraud-bundle'` + defineAsyncComponent + contextProps `standard`

## Data Models

```
点击 S32 → GtWpRenderer(componentType=s32-fraud-bundle) → GtS32Bundle
  onMounted:
    1. getWpIndex(projectId) → wpIdMap（S32-x → wp_id）
    2. 计算 visibleTabs（wpIdMap 有值的舞弊情形）
    3. 渲染可滚动 el-tabs
    4. 选中 Tab → GtAProgramConsole(embedded, wp-id)；含 IC-0/IC-X → 子 sheet 切换；提示 → 折叠区块
联动：完成程序 → refreshCompletion(wpCode) → completionMap → 仪表盘刷新
```

## Correctness Properties

*属性是系统在所有合法执行路径下都应保持为真的行为声明。*

### Property 1: 子底稿 skip 映射完整性

*For any* wp_code 属于 {S32-1..S32-13}，其映射值应为 `skip`；`S32` 映射为 `s32-fraud-bundle`。

**Validates: Requirements 1.2, 2.1, 2.2**

### Property 2: wp_id 解析与传播

*For any* wp_index 数据集（含 S32-* 条目），wpIdMap 正确映射，且每个 Tab 的 GtAProgramConsole 接收 wp-id = wpIdMap[tab.wpCode]。

**Validates: Requirements 5.1, 5.3**

### Property 3: Tab 可见性由 wp_index 存在性驱动

*For any* wp_index 数据集，仅 wpIdMap 有值的舞弊情形显示为可见 Tab；无任何 S32 时显示空状态。

**Validates: Requirements 5.2, 5.4**

### Property 4: sheetName 路由正确激活 Tab

*For any* 合法 Tab id，经 sheetName / query 传入时 active 切换为该值；非法值时保持不变。

**Validates: Requirements 4.1, 4.2, 4.3, 4.4**

### Property 5: 完成进度统计一致性

*For any* completionMap，progressSummary 各计数之和等于可见底稿数，且各计数与状态一致。

**Validates: Requirements 7.1, 7.2**

### Property 6: readonly 透传

*For any* Tab 与任意 readonly 布尔值，GtAProgramConsole 接收的 readonly 与父 props.readonly 一致。

**Validates: Requirements 8.1, 8.2**

## Error Handling

| 场景 | 处理 |
|------|------|
| wp_index API 失败 | 提示错误，显示空状态 |
| 子底稿 wp_id 不存在 | 对应 Tab 隐藏 |
| sheetName 无效 | 保持当前 Tab |
| 子组件加载失败 | defineAsyncComponent errorComponent 兜底 |
| 程序行为空 | GtGridSheet 只读兜底 |
| 引用底稿不存在 | GtIndexChip 灰态 |

## Testing Strategy

### 属性测试（PBT）

fast-check，每 property ≥ 100 次。Tag：`Feature: s32-fraud-response-bundle, Property {N}: {title}`。

| Property | 生成器 |
|----------|--------|
| P1 skip 映射 | 固定 S32 编码集合遍历 overrides |
| P2 wp_id 解析 | `fc.array(fc.record({wp_code: fc.constantFrom(...S32_CODES), wp_id: fc.uuid()}))` |
| P3 Tab 可见性 | `fc.subsetOf(S32_CODES)` |
| P4 sheetName 路由 | `fc.oneof(fc.constantFrom(...VALID_IDS), fc.string())` |
| P5 进度统计 | `fc.array(fc.constantFrom('completed','in_progress','not_started'))` |
| P6 readonly 透传 | `fc.boolean()` |

### 单元/集成测试

- 注册表含 `s32-fraud-bundle`，VALID_COMPONENT_TYPES 含之
- 13 Tab 配置与舞弊情形一致
- 含 IC-0/IC-X 底稿的子 sheet 切换
- 提示折叠区块渲染
- 挂载 mock wp_index，验证子组件渲染 + 只读透传
