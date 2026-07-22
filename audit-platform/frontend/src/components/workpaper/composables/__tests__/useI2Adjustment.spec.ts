/**
 * useI2Adjustment — I2-3 调整分录汇总单测
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import {
  useI2Adjustment,
  categoryFromLegacy,
  entryTypeFromCategory,
  resolveI2AuditYear,
} from '../useI2Adjustment'
import { api } from '@/services/apiProxy'
import { eventBus } from '@/utils/eventBus'

vi.mock('@/utils/eventBus', () => ({
  eventBus: { emit: vi.fn(), on: vi.fn(), off: vi.fn() },
}))

vi.mock('@/services/apiProxy', () => ({
  api: { get: vi.fn(), post: vi.fn() },
}))

vi.mock('@/services/apiPaths/accounting', () => ({
  adjustments: {
    list: (pid: string) => `/api/projects/${pid}/adjustments`,
    create: (pid: string) => `/api/projects/${pid}/adjustments`,
  },
}))

function makeMap(rows?: unknown[], legacy = false) {
  const m = new Map<string, { item_id: string; conclusion: null; remark: string | null }>()
  if (rows) {
    const key = legacy ? 'I2-3-entries' : 'I2-3-rows'
    m.set(key, {
      item_id: key,
      conclusion: null,
      remark: JSON.stringify(rows),
    })
  }
  return ref(m)
}

describe('categoryFromLegacy / entryTypeFromCategory', () => {
  it('maps Excel categories and legacy AJE/RJE', () => {
    expect(categoryFromLegacy({ category: '账项调整' })).toBe('账项调整')
    expect(categoryFromLegacy({ category: '报表调整' })).toBe('报表调整')
    expect(categoryFromLegacy({ entryType: 'RJE' })).toBe('报表调整')
    expect(entryTypeFromCategory('报表调整')).toBe('RJE')
    expect(entryTypeFromCategory('账项调整')).toBe('AJE')
  })
})

describe('resolveI2AuditYear', () => {
  it('prefers prop year', () => {
    expect(resolveI2AuditYear({ propYear: 2024 })).toBe(2024)
  })
})

describe('useI2Adjustment', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('loads and normalizes legacy I2-3-entries', () => {
    const allResponses = makeMap(
      [
        {
          date: '2025-12-31',
          account: '开发支出',
          debit: 5000,
          credit: 0,
          summary: '补记资本化',
          entryType: 'AJE',
        },
        {
          date: '2025-12-31',
          account: '研发费用',
          debit: 0,
          credit: 5000,
          summary: '补记资本化',
          entryType: 'AJE',
        },
      ],
      true,
    )
    const onSave = vi.fn()
    const api_ = useI2Adjustment({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses,
      isReadonly: ref(false),
      auditYear: ref(2025),
      onSave,
    })
    expect(api_.rows.value).toHaveLength(2)
    expect(api_.rows.value[0].description).toBe('补记资本化')
    expect(api_.rows.value[0].category).toBe('账项调整')
    expect(api_.rows.value[0].accountCode).toBe('1717')
    expect(api_.isBalanced.value).toBe(true)
    expect(api_.ajeNet.value).toBe(5000)
  })

  it('pushToAdjustmentModule groups by description and marks sourceGroupId', async () => {
    const allResponses = makeMap()
    const onSave = vi.fn()
    ;(api.post as any).mockResolvedValue({ entry_group_id: 'g-100' })

    const state = useI2Adjustment({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses,
      isReadonly: ref(false),
      auditYear: ref(2025),
      onSave,
    })
    state.addRow('AJE')
    state.updateCell(state.rows.value[0].rowId, 'description', '费用化转出')
    state.updateCell(state.rows.value[0].rowId, 'debitAmount', 0)
    state.updateCell(state.rows.value[0].rowId, 'creditAmount', 8000)
    state.addRow('AJE')
    state.updateCell(state.rows.value[1].rowId, 'description', '费用化转出')
    state.updateCell(state.rows.value[1].rowId, 'accountCode', '5301')
    state.updateCell(state.rows.value[1].rowId, 'debitAmount', 8000)
    state.updateCell(state.rows.value[1].rowId, 'creditAmount', 0)

    expect(state.isBalanced.value).toBe(true)
    const n = await state.pushToAdjustmentModule()
    expect(n).toBe(1)
    expect(api.post).toHaveBeenCalled()
    expect(state.rows.value.every((r) => r.sourceGroupId === 'g-100')).toBe(true)
    expect(eventBus.emit).toHaveBeenCalledWith('adjustment:updated')
  })

  it('syncFromAdjustmentModule imports groups containing 1717', async () => {
    const allResponses = makeMap()
    const onSave = vi.fn()
    ;(api.get as any).mockResolvedValue({
      data: {
        items: [
          {
            entry_group_id: 'mod-1',
            adjustment_type: 'aje',
            description: '[I2] 资本化补记',
            line_items: [
              { standard_account_code: '1717', account_name: '开发支出', debit_amount: 1000, credit_amount: 0 },
              { standard_account_code: '1002', account_name: '银行存款', debit_amount: 0, credit_amount: 1000 },
            ],
          },
          {
            entry_group_id: 'mod-skip',
            adjustment_type: 'aje',
            description: '无关',
            line_items: [
              { standard_account_code: '1001', debit_amount: 1, credit_amount: 0 },
              { standard_account_code: '1002', debit_amount: 0, credit_amount: 1 },
            ],
          },
        ],
      },
    })

    const state = useI2Adjustment({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses,
      isReadonly: ref(false),
      auditYear: ref(2025),
      onSave,
    })
    const n = await state.syncFromAdjustmentModule()
    expect(n).toBe(2)
    expect(state.rows.value.every((r) => r.sourceGroupId === 'mod-1')).toBe(true)
    expect(state.rows.value[0].description).toBe('资本化补记')
  })

  it('pushToA13 emits a13:push-misstatement for 账项调整', () => {
    const allResponses = makeMap([
      {
        rowId: 'a',
        description: '补记',
        category: '账项调整',
        accountCode: '1717',
        debitAmount: 100,
        creditAmount: 0,
      },
      {
        rowId: 'b',
        description: '重分类',
        category: '报表调整',
        accountCode: '1717',
        debitAmount: 50,
        creditAmount: 0,
      },
    ])
    const state = useI2Adjustment({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses,
      isReadonly: ref(false),
      onSave: vi.fn(),
    })
    state.pushToA13()
    expect(eventBus.emit).toHaveBeenCalledWith(
      'a13:push-misstatement',
      expect.objectContaining({
        wpCode: 'I2',
        source: 'I2-3',
      }),
    )
    const payload = (eventBus.emit as any).mock.calls.find((c: any[]) => c[0] === 'a13:push-misstatement')?.[1]
    expect(payload.items).toHaveLength(1)
    expect(payload.items[0].description).toBe('补记')
    expect(payload.items[0].debitAmount).toBe(100)
  })
})
