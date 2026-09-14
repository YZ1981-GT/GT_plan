/**
 * useG10Disclosure — 合计 / 勾稽 / 分项带入
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import type { ChecklistResponse } from '../useF1FormData'

vi.mock('@/services/apiProxy', () => ({
  api: { post: vi.fn(async () => ({ data: { content: 'AI文案' } })) },
}))

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), warning: vi.fn(), info: vi.fn(), error: vi.fn() },
  ElMessageBox: { confirm: vi.fn().mockResolvedValue(true) },
}))

vi.mock('@/utils/eventBus', () => ({
  eventBus: { on: vi.fn(), off: vi.fn(), emit: vi.fn() },
}))

vi.mock('../workpaperAuditYear', () => ({
  useWorkpaperAuditYear: () => ref(2025),
}))

import { useG10Disclosure } from '../useG10Disclosure'
import { G10_DISCLOSURE_TOTAL_LABEL } from '../g10SchemaRows'

function makeMap(entries: Record<string, Partial<ChecklistResponse>> = {}) {
  const m = new Map<string, ChecklistResponse>()
  for (const [k, v] of Object.entries(entries)) {
    m.set(k, { item_id: k, conclusion: null, remark: null, ...v } as ChecklistResponse)
  }
  return m
}

describe('useG10Disclosure', () => {
  let allResponses: ReturnType<typeof ref<Map<string, ChecklistResponse>>>
  let saves: Array<{ id: string; data: Partial<ChecklistResponse> }>

  beforeEach(() => {
    saves = []
    allResponses = ref(makeMap())
  })

  function setup(variant: 'listed' | 'soe' = 'listed', extra: Record<string, Partial<ChecklistResponse>> = {}) {
    allResponses.value = makeMap(extra)
    const debouncedSave = (id: string, d: Partial<ChecklistResponse>) => {
      saves.push({ id, data: d })
      const prev = allResponses.value.get(id) ?? ({ item_id: id } as ChecklistResponse)
      allResponses.value = new Map(allResponses.value).set(id, { ...prev, ...d } as ChecklistResponse)
    }
    return useG10Disclosure({
      variant,
      wpId: ref('wp-1'),
      allResponses,
      debouncedSave,
      isReadonly: ref(false),
    })
  }

  it('上市口径列头 + 变动表含合计行', () => {
    const disc = setup('listed')
    expect(disc.colLabels.value.movement.opening).toBe('期初余额')
    expect(disc.colLabels.value.movement.closing).toBe('期末余额')
    const total = disc.listedMovementDisplay.value.find((r) => r.isTotal)
    expect(total?.label).toBe(G10_DISCLOSURE_TOTAL_LABEL)
  })

  it('勾稽差异：附注合计 vs G10-1 审定', () => {
    const disc = setup('listed', {
      'G10-disclosure-listed': {
        remark: JSON.stringify({
          version: 2,
          movement: {
            mv_trading_bond: { openingAmount: 0, increaseAmount: 0, decreaseAmount: 0, closingAmount: 60 },
            mv_derivative: { openingAmount: 0, increaseAmount: 0, decreaseAmount: 0, closingAmount: 40 },
          },
        }),
      },
      'G10-1-adjudicated-amount': { conclusion: '90' },
    })
    expect(disc.disclosureClosingSum.value).toBe(100)
    expect(disc.hasAdjCrossMismatch.value).toBe(true)
    expect(disc.adjCrossVariance.value).toBe(10)
  })

  it('国企余额表合计与审定一致时无勾稽差异', () => {
    const disc = setup('soe', {
      'G10-disclosure-soe': {
        remark: JSON.stringify({
          version: 2,
          balance: {
            soe_trading_bond: { currentAmount: 90, priorAmount: 0 },
          },
        }),
      },
      'G10-1-adjudicated-amount': { conclusion: '90' },
    })
    expect(disc.disclosureClosingSum.value).toBe(90)
    expect(disc.hasAdjCrossMismatch.value).toBe(false)
  })
})
