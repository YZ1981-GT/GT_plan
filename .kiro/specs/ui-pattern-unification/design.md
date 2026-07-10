# Design Document: UI Pattern Unification

## Overview

本设计文档描述审计平台前端两个基础设施组件（抽凭引擎、版本链）集成模式的统一迁移方案。涉及 7 个目标组件的纯前端改造，将残留的旧模式（el-collapse 内嵌抽凭 + useVersionTrail 底层直调）统一到新标准模式（dialog-mode 工具栏按钮 + useWorkpaperVersionToolbar 高层封装）。

迁移为纯前端 Template/Script 层改造，不涉及后端、数据库、API 变更。

## Architecture

### 抽凭引擎模式对比

```
旧模式（Collapse）:
  <el-collapse>
    <GtVoucherSamplingEngine :account-code="xxx" @filled="handler" />
  </el-collapse>

新模式（Dialog）:
  <div class="head-actions">
    <GtVoucherSamplingEngine :project-id="projectId" :account-codes="[xxx]" dialog-mode @filled="handler" />
  </div>
```

### 版本链模式对比

```
旧模式（直调 useVersionTrail）:
  const { autoSnapshot } = useVersionTrail(computed(() => props.wpId))
  versionTrailRef.value?.open?.()

新模式（useWorkpaperVersionToolbar 封装）:
  const versionToolbar = useWorkpaperVersionToolbar({ wpId, projectId })
  versionToolbar.openVersionHistory()
  versionToolbar.scheduleAutoSnapshot()
```

### 迁移范围

| 迁移类型 | 目标组件 | 参考标准 |
|---------|---------|---------|
| 抽凭 Collapse → Dialog | D2TabVoucherCheck, F2ValuationTestSheet, F2TabPurchaseInboundCheck, F2TabMaterialUsageCheck, F5TabMajorAdjustment | G5TabVoucherCheck.vue |
| 版本链直调 → Toolbar | GtG5LongTermReceivable, GtConfirmationAlternativeL05 | GtG4BondInvestmentMain.vue |

## Components and Interfaces

### 抽凭迁移组件详情

| 组件 | 旧 CSS Class | accountCode | phase | 特殊参数 |
|------|-------------|-------------|-------|---------|
| D2TabVoucherCheck | sampling-engine-collapse | 1122 | — | — |
| F2ValuationTestSheet | sampling-collapse | 组件原有值 | — | — |
| F2TabPurchaseInboundCheck | — | 组件原有值 | — | — |
| F2TabMaterialUsageCheck | — | 组件原有值 | — | — |
| F5TabMajorAdjustment | f5-sampling | 6401 | final | — |

### GtVoucherSamplingEngine Props（不修改）

```typescript
interface Props {
  accountCode?: string          // 单科目（旧 API 兼容）
  accountCodes?: string[]       // 多科目（推荐）
  phase?: Phase
  defaultMethod?: SamplingMethod
  workpaperId?: string
  projectId: string
  year?: number
  dialogMode?: boolean          // dialog-mode = true 时以按钮+弹窗呈现
}
```

### GtVoucherSamplingEngine Emits（不修改）

```typescript
interface Emits {
  (e: 'filled', payload: {
    samples: SampledVoucher[]
    phase: Phase
    fillMode: FillMode
    method?: SamplingMethod
  }): void
  (e: 'phase-changed', payload: { phase: Phase }): void
}
```

### useWorkpaperVersionToolbar（不修改）

```typescript
interface UseWorkpaperVersionToolbarOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  debounceMs?: number  // 默认 3000ms
}

interface UseWorkpaperVersionToolbarReturn {
  versionTrailRef: Ref<{ openDrawer: () => void } | null>
  openVersionHistory: () => void
  scheduleAutoSnapshot: () => void
  wrapSaveImmediate: <T>(fn: T) => T
}
```

### 抽凭迁移 Template 模式

```vue
<!-- ═══ Before: el-collapse 内嵌 ═══ -->
<el-collapse class="sampling-engine-collapse">
  <el-collapse-item title="抽凭引擎">
    <GtVoucherSamplingEngine
      :account-code="accountCode"
      :phase="phase"
      :workpaper-id="wpId"
      :project-id="projectId"
      :year="year"
      @filled="handleSamplingFilled"
    />
  </el-collapse-item>
</el-collapse>

<!-- ═══ After: 工具栏按钮 + dialog-mode ═══ -->
<div class="section-head">
  <h3>检查表标题</h3>
  <div class="head-actions">
    <GtVoucherSamplingEngine
      :project-id="projectId"
      :account-codes="[accountCode]"
      dialog-mode
      @filled="handleSamplingFilled"
    />
    <!-- 其他工具栏按钮 -->
  </div>
</div>
```

### 版本链迁移 Script 模式

```typescript
// ═══ Before (GtG5LongTermReceivable) ═══
import { useVersionTrail } from './composables/useVersionTrail'
const { autoSnapshot } = useVersionTrail(computed(() => props.wpId))
const versionTrailRef = ref()
function showVersionHistory() {
  versionTrailRef.value?.open?.()
}

// ═══ After ═══
import { useWorkpaperVersionToolbar } from './composables/useWorkpaperVersionToolbar'
const versionToolbar = useWorkpaperVersionToolbar({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})
const { versionTrailRef } = versionToolbar
// 工具栏按钮: versionToolbar.openVersionHistory()
// 保存后自动快照: versionToolbar.scheduleAutoSnapshot()
```

## Data Models

本次迁移不涉及数据模型变更。以下为迁移中需保持不变的数据结构：

### SampledVoucher（@filled payload 中的样本项）

```typescript
interface SampledVoucher {
  voucherNo?: string
  voucherDate?: string
  summary?: string
  amount?: number
  debitAmount?: string
  creditAmount?: string
  counterAccount?: string
}
```

### 各组件 @filled handler 映射规则（保持不变）

- **D2TabVoucherCheck**: `{ summary, amount, voucherDate, voucherNo }` → 检查表行
- **F2ValuationTestSheet**: 样本 → 估值测试行
- **F2TabPurchaseInboundCheck**: 样本 → 购入检查行
- **F2TabMaterialUsageCheck**: 样本 → 领用检查行
- **F5TabMajorAdjustment**: `{ summary, amount, voucherDate, voucherNo }` → 重大调整行

## Error Handling

- 迁移不引入新的错误路径，所有错误处理沿用原有逻辑
- `GtVoucherSamplingEngine` dialog-mode 内部处理抽凭失败提示
- `useWorkpaperVersionToolbar` 的 autoSnapshot 失败静默（`_silent: true`），不阻塞编辑
- 版本历史 drawer 打开失败由 `GtWpVersionTrail` 内部处理

## Migration Strategy

### 逐组件独立迁移原则

1. 每个组件独立完成迁移，互不影响
2. 不引入新的共享状态或跨组件依赖
3. 不修改 `GtVoucherSamplingEngine` / `useWorkpaperVersionToolbar` 本身的 API
4. 迁移后已有 PBT 测试必须全部通过

### 迁移检查清单（每组件通用）

- [ ] 删除 `<el-collapse>` 包裹结构
- [ ] 在工具栏区域放置 `<GtVoucherSamplingEngine dialog-mode />`
- [ ] 保留原有 `@filled` handler 函数体不变
- [ ] 保留 accountCode / phase / defaultMethod 等业务参数值
- [ ] 确认 import 路径正确
- [ ] 版本链：替换 useVersionTrail → useWorkpaperVersionToolbar
- [ ] 版本链：删除手动 autoSnapshot 调用与 versionTrailRef.open() 逻辑
- [ ] 版本链：更新版本历史按钮调用方式

## Testing Strategy

### 已有测试保障

- `voucherSampling.property.spec.ts` — 抽凭引擎 PBT，验证 sampling 逻辑正确性
- `versionTrail.spec.ts` — 版本链单元测试

迁移后这些测试必须全量通过，不修改断言逻辑。

### 迁移验证方式

由于本次是纯 UI 集成模式变更（不修改底层逻辑），验证策略以 example-based 为主：

1. **组件渲染验证**：各迁移组件加载后工具栏区域有抽凭按钮、无 el-collapse
2. **@filled 回调验证**：触发 @filled 后数据正确映射到表格行
3. **版本链功能验证**：版本历史按钮可打开 drawer、保存触发 autoSnapshot
4. **回归验证**：已有 PBT + 单元测试全量通过

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: @filled 样本到行映射保持等价

*For any* valid `@filled` payload（包含 0~N 个 SampledVoucher，每个 voucher 的字段为任意合法字符串/数字组合），经过 handleSamplingFilled 处理后，插入表格的行数据应与迁移前的映射逻辑产生完全相同的结果——字段名、字段值、行数一一对应。

**Validates: Requirements 1.3, 1.6, 2.3, 3.5, 4.4, 7.1**

### Property 2: useWorkpaperVersionToolbar API 调用路径与 useVersionTrail 直调等价

*For any* wpId 和 projectId 组合，通过 useWorkpaperVersionToolbar 的 `openVersionHistory()` 和 `scheduleAutoSnapshot()` 触发的 HTTP 请求路径（endpoint + method + body schema）应与直接使用 useVersionTrail 的 `openDrawer()` + `createSnapshot()` 产生的 HTTP 请求完全一致。

**Validates: Requirements 5.5, 7.2**
