# createChecklistFormData 迁移示例

## 现有同构 composable（~250 行重复代码）

```ts
// useM1FormData.ts — 250+ 行
import { ref, onScopeDispose, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { eventBus } from '@/utils/eventBus'

const DEBOUNCE_MS = 2000
const ITEM_PREFIX = 'M1-'
const ACCOUNT_CODE = '2232'

export function useM1FormData(options) {
  // ... selfLoad, loadResponses, loadData, _doSave, saveField,
  //     saveBatch, debouncedSave, writebackTB, _flushPending, onScopeDispose
  // 250+ 行完全同构代码，仅 prefix/account/componentType 不同
}
```

## 迁移后（~15 行工厂调用）

```ts
// useM1FormData.ts — 15 行
import { type Ref } from 'vue'
import { createChecklistFormData } from './factories'

export function useM1FormData(opts: { wpId: Ref<string>; projectId: Ref<string>; year?: Ref<number> }) {
  return createChecklistFormData({
    wpId: opts.wpId,
    projectId: opts.projectId,
    year: opts.year,
    itemPrefix: 'M1-',
    label: 'M1',
    forceComponentType: 'm1-dividends-payable',
    accountCodes: ['2232'],
  })
}
```

## 有业务钩子的迁移示例（K1 双科目 + normalizeResponse）

```ts
// useK1FormData.ts
import { type Ref } from 'vue'
import { createChecklistFormData } from './factories'
import { decodeRemark } from '@/composables/workpaper/remarkCodec'

export function useK1FormData(opts: { wpId: Ref<string>; projectId: Ref<string>; year?: Ref<number> }) {
  return createChecklistFormData({
    wpId: opts.wpId,
    projectId: opts.projectId,
    year: opts.year,
    itemPrefix: 'K1-',
    label: 'K1',
    forceComponentType: 'k1-other-receivables',
    accountCodes: ['1221', '1231'],
    normalizeResponse: (resp) => {
      // 兼容历史双层 JSON 包装
      if (resp.remark) {
        try {
          const decoded = decodeRemark(resp.remark)
          return { ...resp, remark: typeof decoded === 'string' ? decoded : JSON.stringify(decoded) }
        } catch { /* keep original */ }
      }
      return resp
    },
    afterSave: (saved) => {
      // 保存成功后触发版本快照
      console.debug(`[K1] saved ${saved.item_id}`)
    },
  })
}
```

## 迁移清单（94 个文件，按批次）

### Wave A: 最简同构（M1-M10, N1-N5）
- 无业务差异，纯参数替换
- 预计每个文件 5 分钟

### Wave B: 标准同构（K1-K13, H1-H10, I1-I6）
- 可能需要 normalizeResponse（历史双层 JSON 兼容）
- K/H 有 writebackTB 多科目场景

### Wave C: 带扩展的同构（G10-G14, L1-L8）
- G10 等有 localStorage 草稿恢复（可通过 afterSave 和 Persistence Adapter 的错误恢复替代）
- L 系列有 formula engine 耦合（保留业务 composable，仅迁移 I/O 层）

### 不迁移（有显著业务差异）
- useD2FormData（已手工迁移 useChecklistPersistence，有子底稿读取）
- useD4-D7FormData（复杂 htmlData 分派）
- useG4EclFormData / useG6EclFormData（ECL 状态机）
- useG5FormData（长期股权复合逻辑）
- useG7EquityMethodFormData / useG7SubFormData（权益法复杂计算）
- useF2FormData（估值 + 盘点特殊分支）
- useK5FormData（已迁移 useChecklistPersistence）
