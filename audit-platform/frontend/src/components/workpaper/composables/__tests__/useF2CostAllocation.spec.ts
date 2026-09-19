import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref } from 'vue'
import { useF2CostAllocation } from '../useF2CostAllocation'
import type { ChecklistResponse } from '../useF2ValuationFormData'

describe('useF2CostAllocation', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('addProduct 不被 persist→load 回声裁掉空行', () => {
    const allResponses = ref(new Map<string, ChecklistResponse>())
    const ca = useF2CostAllocation({ allResponses })

    expect(ca.sheet.value.products).toHaveLength(1)
    ca.addProduct()
    expect(ca.sheet.value.products).toHaveLength(2)
    ca.addProduct()
    expect(ca.sheet.value.products).toHaveLength(3)
  })

  it('删除末行时清空内容并立即触发保存', () => {
    const allResponses = ref(new Map<string, ChecklistResponse>())
    const ca = useF2CostAllocation({ allResponses })
    const id = ca.sheet.value.products[0].id
    ca.updateProduct(id, { productName: 'A', outputQty: 10, allocationBase: 5 })

    const events: CustomEvent[] = []
    const handler = (e: Event) => events.push(e as CustomEvent)
    window.addEventListener('f2-val:save-items', handler)
    try {
      ca.removeProduct(id)
      expect(ca.sheet.value.products).toHaveLength(1)
      expect(ca.sheet.value.products[0].productName).toBe('')
      expect(ca.sheet.value.products[0].id).not.toBe(id)
      // 立即 flush，无需等 debounce
      expect(events).toHaveLength(1)
      expect(events[0].detail.items[0].item_id).toBe('F2-44-rows')
    } finally {
      window.removeEventListener('f2-val:save-items', handler)
    }
  })

  it('多行时删除指定行并立即保存', () => {
    const allResponses = ref(new Map<string, ChecklistResponse>())
    const ca = useF2CostAllocation({ allResponses })
    ca.addProduct()
    const [a, b] = ca.sheet.value.products
    ca.updateProduct(a.id, { productName: 'A' })
    ca.updateProduct(b.id, { productName: 'B' })

    const events: CustomEvent[] = []
    const handler = (e: Event) => events.push(e as CustomEvent)
    window.addEventListener('f2-val:save-items', handler)
    try {
      ca.removeProduct(a.id)
      expect(ca.sheet.value.products).toHaveLength(1)
      expect(ca.sheet.value.products[0].productName).toBe('B')
      expect(events.length).toBeGreaterThanOrEqual(1)
    } finally {
      window.removeEventListener('f2-val:save-items', handler)
    }
  })

  it('内容未变时 updateProduct 不重复写库', () => {
    const allResponses = ref(new Map<string, ChecklistResponse>())
    const ca = useF2CostAllocation({ allResponses })
    const id = ca.sheet.value.products[0].id
    ca.updateProduct(id, { productName: 'A', outputQty: 1 })
    const remarkAfterFirst = allResponses.value.get('F2-44-rows')?.remark

    ca.updateProduct(id, { productName: 'A', outputQty: 1 })
    expect(allResponses.value.get('F2-44-rows')?.remark).toBe(remarkAfterFirst)
  })
})
