# voucher-attach-account-mapping-closure — 设计文档

## 一、架构概览

```
render-config 请求
       ↓
底稿主组件（GtD3.vue 等）
  ├─ provide('tbSourceCodes', tbSourceCodes)
  └─ 凭证检查子组件（D3TabVoucherCheck.vue 等）
       ├─ inject('tbSourceCodes', null)
       ├─ const prefixes = dSlotQueryCodes('D3', injectedSrc)
       └─ pullSamplesForWorkpaper(pid, year, wpId, prefixes)
            或 <GtVoucherSamplingEngine :account-code="prefixes" />
```

### 数据流

1. 后端 `get_render_config` 返回 `tb_source_codes`（经 `account_mapping` 映射后的科目码）
2. 底稿主组件解析 `html_data.tb_source_codes` 或 `html_data.project_context.tb_source_codes`
3. `provide('tbSourceCodes', tbSourceCodes)` 注入到组件树
4. 凭证检查子组件 `inject` 后传给 AccountScope 的 `queryCodes(src)`
5. AccountScope 优先取 `src.gross_raw` → `src.gross_standard` → 兜底码

### 向后兼容

- `inject('tbSourceCodes', null)` 返回 `null` 时，AccountScope 退到兜底码
- 不破坏任何已有行为：兜底码覆盖标准科目表的企业仍然正常工作
- 仅在企业科目编码与标准不同时，映射码能提供更精确的匹配

### 两种消费路径

- **路径 A（pullSamplesForWorkpaper）**：F1/F3/F4/D3~D7/E1 — JS 函数参数
- **路径 B（GtVoucherSamplingEngine）**：F2/F5 — Vue prop `:account-code`

## 二、实施分组

按循环分组逐批实施，每批一个 PR：

### 批次 1：D 循环（7 个底稿主组件 + 5 个已接入的凭证检查子组件）
- `GtD3.vue` / `GtD4.vue` / `GtD5.vue` / `GtD6.vue` / `GtD7.vue` 加 provide
- `D3TabVoucherCheck.vue` ~ `D7TabVoucherCheck.vue` 改用 inject
- D 循环已有 `pickDTbSourceCodes(htmlData)` 工具函数，底稿主组件直接调用

### 批次 2：E 循环（1 个底稿主组件 + 1 个凭证检查子组件）
- `GtE1.vue` 加 provide
- `E1TabLargeCheck.vue` 改用 inject

### 批次 3a：F1/F3/F4（路径 A — pullSamplesForWorkpaper）
- `GtF1Prepayment.vue` / `GtF3NotesPayable.vue` / `GtF4AccountsPayable.vue` 加 provide
- `F1TabComprehensiveCheck` / `F3TabVoucherCheck` / `F4TabVoucherCheck` 改用 inject

### 批次 3b：F2（路径 B — GtVoucherSamplingEngine，4 个宿主 + 5 个子组件）

| 宿主（provide 端） | 抽凭子组件（inject 端） | 当前科目来源 | 改造方式 |
|---|---|---|---|
| `GtF2InventoryMain` | `F2CutoffSheet` | `getF2CutoffAccountCodes()` 常量 | 新建 `f2InventoryAccountScope.ts` → inject 驱动 |
| `GtF2InventoryValuation` | `F2TabPurchaseInboundCheck`、`F2TabMaterialUsageCheck`、`F2ValuationTestSheet` | `F2_INVENTORY_ACCOUNT_CODES` 常量 | 同上 |
| `GtF2InventorySpecial` | `F2TabContractCostCheck` | `f2ContractCostQueryCodes()` 无参 | 改传 inject src |
| `GtF2StocktakeBundle` | （无抽凭子组件） | — | 只加 provide 不改子组件 |

🔴 F2 存货族需新建 `f2InventoryAccountScope.ts`：接受 `TbSourceCodes`，有 `gross_raw` → 返映射码，无 → 退兜底 `['1401'..'1412']`

🔴 F2 合同履约成本已有 `f2ContractCostAccountScope.ts`，只需把无参调用改为传入 inject 值

### 批次 3c：F5（路径 B — GtVoucherSamplingEngine，1 + 1）
- `GtF5CostOfSales.vue` 加 provide
- `F5TabMajorAdjustment` 的 `f5GrossQueryCodes()` 改为 `f5GrossQueryCodes(injected)`

### 批次 4：G 循环（12 个底稿主组件 + 11 个凭证检查子组件）

### 批次 5：H 循环（10 个底稿主组件 + 12 个凭证检查子组件）

### 批次 6：I/J/K/M/N 循环（剩余）

## 三、provide 注入点选择

### D 循环示例

D 循环底稿主组件（如 `GtD3.vue`）的 `onMounted` 或 `watch(htmlData)` 中：

```ts
import { provide } from 'vue'
import { pickDTbSourceCodes } from '../composables/dCycleAccountScope'

// render-config 返回后
const tbSourceCodes = computed(() => pickDTbSourceCodes(props.htmlData))
provide('tbSourceCodes', tbSourceCodes)
```

### inject 端

```ts
import { inject } from 'vue'
import { dSlotQueryCodes } from '../composables/dCycleAccountScope'

const tbSourceCodes = inject('tbSourceCodes', null)
const D3_ACCOUNT_PREFIXES = computed(() =>
  dSlotQueryCodes('D3', tbSourceCodes?.value ?? null)
)
```

### 路径 B 示例（GtVoucherSamplingEngine）

```ts
const tbSourceCodes = inject('tbSourceCodes', null)
const F2_PREFIXES = computed(() => f2InventoryQueryCodes(tbSourceCodes?.value ?? null))
// template: <GtVoucherSamplingEngine :account-code="F2_PREFIXES.value.join(',')" />
```

## 四、守卫设计

### 4.1 AccountScope 口径一致性守卫

扫描所有凭证检查组件的 `importFromAttached` 函数体及 `GtVoucherSamplingEngine` 的 `:account-code` prop，断言其 `pullSamplesForWorkpaper` 的第四参数（accountPrefixes）或 `:account-code` 绑定值来自 AccountScope 函数调用，而非硬编码数组字面量。

### 4.2 映射码优先级守卫

对每个 AccountScope 的 `queryCodes(src)` 验证：
- `src` 有 `gross_raw` → 返回 `gross_raw`（客户原始码）
- `src` 有 `gross_standard` → 返回 `gross_standard`（标准码）
- `src` 为 null → 返回兜底码
