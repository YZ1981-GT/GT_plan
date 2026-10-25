/**
 * useD4PriceWriteback — D4 价格分析异常回标接收端（方案 C 的"回写"侧）
 *
 * spec: .kiro/specs/d4-price-analysis-writeback-linkage/ Req 4 / Property 3
 *
 * 🔴 修复"回写又成死代码"：D4-10/D4-11 识别的价格异常客户/产品经 eventBus
 * `d4:price-abnormal` 发出，本 composable 是**真实接收端**——把异常标记写回
 * D4-2 主营明细（D4-2-rows）对应行的 `priceAbnormal` 结构，形成审计追溯闭环。
 *
 * D4-9 客户结构 name / D4-11 产品品种均派生自 D4-2 的 `product` 字段，故两来源
 * 都按 `product === name` 匹配 D4-2-rows 行；用 wpCode 区分标记来源，互不覆盖。
 *
 * 幂等（Property 3）：payload.items 为该来源**当前全部**异常项，接收端按 wpCode
 * 覆盖该来源标记集（非追加）；items 为空 = 清除该来源全部标记。目标行缺失静默跳过。
 */
import { onBeforeUnmount, type Ref } from 'vue'
import { eventBus } from '@/utils/eventBus'
import type { ChecklistResponse } from './useD4FormData'

const D4_2_ROWS_KEY = 'D4-2-rows'

/** D4-2 行上的价格异常标记：{ 'D4-10': 差异率, 'D4-11': 差异率 } */
export type PriceAbnormalMark = Record<string, number>

interface D4PriceAbnormalPayload {
  wpCode: 'D4-10' | 'D4-11'
  targetKey: 'customer' | 'product'
  items: Array<{ name: string; diffPct: number }>
  timestamp?: number
}

export interface UseD4PriceWritebackOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  /** 保存回调（宿主 flushSave / d4:save-items）；不传则仅更新内存 Map */
  onPersist?: (item: ChecklistResponse) => void
}

/** 纯函数：把某来源(wpCode)的异常项集合写回行数组，返回是否有变化（供守卫直接测） */
export function applyPriceAbnormal(
  rows: Array<Record<string, any>>,
  wpCode: string,
  items: Array<{ name: string; diffPct: number }>,
): boolean {
  const byName = new Map(items.map(i => [String(i.name || '').trim(), i.diffPct]))
  let changed = false
  for (const row of rows) {
    const name = String(row.product ?? '').trim()
    const mark: PriceAbnormalMark = (row.priceAbnormal && typeof row.priceAbnormal === 'object')
      ? { ...row.priceAbnormal }
      : {}
    const had = wpCode in mark
    if (byName.has(name)) {
      const pct = byName.get(name)!
      if (mark[wpCode] !== pct) { mark[wpCode] = pct; changed = true }
    } else if (had) {
      // 该行不再异常（本来源）→ 清除本来源标记（幂等：空集清除）
      delete mark[wpCode]
      changed = true
    }
    if (Object.keys(mark).length > 0) row.priceAbnormal = mark
    else if ('priceAbnormal' in row) { delete row.priceAbnormal; }
  }
  return changed
}

export function useD4PriceWriteback(options: UseD4PriceWritebackOptions) {
  const { allResponses, onPersist } = options

  function handler(payload: D4PriceAbnormalPayload | undefined): void {
    if (!payload || (payload.wpCode !== 'D4-10' && payload.wpCode !== 'D4-11')) return
    const resp = allResponses.value.get(D4_2_ROWS_KEY)
    if (!resp?.remark) return // D4-2 未编制 → 无目标行，静默跳过（Req 4.4）
    let rows: Array<Record<string, any>>
    try {
      const parsed = JSON.parse(resp.remark)
      if (!Array.isArray(parsed)) return
      rows = parsed
    } catch {
      return
    }
    const items = Array.isArray(payload.items) ? payload.items : []
    const changed = applyPriceAbnormal(rows, payload.wpCode, items)
    if (!changed) return
    const next: ChecklistResponse = { item_id: D4_2_ROWS_KEY, conclusion: resp.conclusion ?? null, remark: JSON.stringify(rows) }
    allResponses.value.set(D4_2_ROWS_KEY, next)
    onPersist?.(next)
  }

  eventBus.on('d4:price-abnormal', handler as any)
  onBeforeUnmount(() => {
    eventBus.off('d4:price-abnormal', handler as any)
  })

  return { handler }
}

export default useD4PriceWriteback
