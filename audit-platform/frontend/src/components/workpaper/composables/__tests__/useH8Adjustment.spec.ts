/**
 * useH8Adjustment — H8-3 调整分录汇总单测
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import {
  useH8Adjustment,
  categoryFromLegacy,
  entryTypeFromCategory,
} from '../useH8Adjustment'

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

function makeMap(rows?: unknown[]) {
  const m = new Map<string, { item_id: string; conclusion: null; remark: string | null }>()
  if (rows) {
    m.set('H8-3-rows', {
      item_id: 'H8-3-rows',
      conclusion: null,
      remark: JSON.stringify(rows),
    })
  }
  return ref(m)
}

describe('categoryFromLegacy / entryTypeFromCategory', () => {
  it('maps Excel categories', () => {
    expect(categoryFromLegacy({ category: '账项调整' })).toBe('账项调整')
    expect(categoryFromLegacy({ category: '报表调整' })).toBe('报表调整')
    expect(categoryFromLegacy({ category: '其他' })).toBe('其他')
  })

  it('maps legacy AJE/RJE / adjustType', () => {
    expect(categoryFromLegacy({ entryType: 'AJE' })).toBe('账项调整')
    expect(categoryFromLegacy({ adjustType: 'RJE' })).toBe('报表调整')
    expect(categoryFromLegacy({ category: '重分类调整' })).toBe('报表调整')
  })

  it('derives entryType from category', () => {
    expect(entryTypeFromCategory('账项调整')).toBe('AJE')
    expect(entryTypeFromCategory('其他')).toBe('AJE')
    expect(entryTypeFromCategory('报表调整')).toBe('RJE')
  })
})

describe('useH8Adjustment', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('loads and normalizes legacy summary/adjustType/debit fields', () => {
    const allResponses = makeMap([
      {
        rowId: 'r1',
        summary: '补记使用权资产',
        adjustType: 'AJE',
        debit: 1000,
        credit: 0,
        indexRef: 'H8-6',
        accountCode: '1901',
      },
      {
        rowId: 'r2',
        summary: '补记使用权资产',
        adjustType: 'AJE',
        debit: 0,
        credit: 1000,
        accountCode: '2205',
        accountName: '租赁负债',
      },
    ])
    const state = useH8Adjustment({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses: allResponses as any,
      isReadonly: ref(false),
    })

    expect(state.rows.value).toHaveLength(2)
    expect(state.rows.value[0].category).toBe('账项调整')
    expect(state.rows.value[0].description).toBe('补记使用权资产')
    expect(state.rows.value[0].debitAmount).toBe(1000)
    expect(state.rows.value[0].accountName).toBe('使用权资产')
    expect(state.isBalanced.value).toBe(true)
    expect(state.rouCostAjeNet.value).toBe(1000)
  })

  it('addRow defaults to 账项调整 + 1901 and persists', () => {
    const allResponses = makeMap()
    const saves: { id: string; val: unknown }[] = []
    const state = useH8Adjustment({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses: allResponses as any,
      isReadonly: ref(false),
      onSave: (id, val) => saves.push({ id, val }),
    })
    state.addRow()
    expect(state.rows.value).toHaveLength(1)
    expect(state.rows.value[0].category).toBe('账项调整')
    expect(state.rows.value[0].accountCode).toBe('1901')
    expect(saves.some((s) => s.id === 'H8-3-rows')).toBe(true)
    const persisted = saves.find((s) => s.id === 'H8-3-rows')!.val as any[]
    expect(persisted[0].debitAmount).toBe(0)
    expect(persisted[0].category).toBe('账项调整')
  })

  it('isBalanced and rouCost/rouDep nets', () => {
    const allResponses = makeMap([
      {
        category: '账项调整',
        accountCode: '1901',
        debitAmount: 500,
        creditAmount: 0,
      },
      {
        category: '账项调整',
        accountCode: '2205',
        debitAmount: 0,
        creditAmount: 500,
      },
      {
        category: '账项调整',
        accountCode: '1902',
        debitAmount: 0,
        creditAmount: 80,
      },
      {
        category: '账项调整',
        accountCode: '6603',
        debitAmount: 80,
        creditAmount: 0,
      },
      {
        category: '报表调整',
        accountCode: '1901',
        debitAmount: 100,
        creditAmount: 0,
      },
      {
        category: '报表调整',
        accountCode: '1601',
        debitAmount: 0,
        creditAmount: 100,
      },
    ])
    const state = useH8Adjustment({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses: allResponses as any,
      isReadonly: ref(false),
    })
    expect(state.isBalanced.value).toBe(true)
    expect(state.rouCostAjeNet.value).toBe(500)
    expect(state.rouCostRjeNet.value).toBe(100)
    expect(state.rouDepAjeNet.value).toBe(-80)
  })

  it('syncFromAdjustmentModule imports full groups containing 1901', async () => {
    const { api } = await import('@/services/apiProxy')
    ;(api.get as any).mockResolvedValue({
      data: {
        items: [
          {
            entry_group_id: 'g1',
            adjustment_type: 'aje',
            description: '[H8] 补记ROU',
            line_items: [
              { standard_account_code: '1901', account_name: '使用权资产', debit_amount: 200, credit_amount: 0 },
              { standard_account_code: '2205', account_name: '租赁负债', debit_amount: 0, credit_amount: 200 },
            ],
          },
          {
            entry_group_id: 'g2',
            adjustment_type: 'aje',
            description: '无关分录',
            line_items: [
              { standard_account_code: '1002', debit_amount: 1, credit_amount: 0 },
              { standard_account_code: '2202', debit_amount: 0, credit_amount: 1 },
            ],
          },
          {
            entry_group_id: 'g3',
            adjustment_type: 'aje',
            description: '纯租赁负债（无1901）',
            line_items: [
              { standard_account_code: '2205', debit_amount: 50, credit_amount: 0 },
              { standard_account_code: '1002', debit_amount: 0, credit_amount: 50 },
            ],
          },
        ],
      },
    })

    const allResponses = makeMap([
      { rowId: 'manual-1', category: '账项调整', accountCode: '1901', debitAmount: 10, creditAmount: 0 },
    ])
    const state = useH8Adjustment({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses: allResponses as any,
      isReadonly: ref(false),
      auditYear: ref(2024),
      onSave: (id, val) => {
        allResponses.value.set(id, {
          item_id: id,
          conclusion: null,
          remark: typeof val === 'string' ? val : JSON.stringify(val),
        })
      },
    })

    const n = await state.syncFromAdjustmentModule()
    expect(n).toBe(2)
    expect(state.rows.value.some((r) => r.rowId === 'manual-1')).toBe(true)
    expect(state.rows.value.filter((r) => r.sourceGroupId === 'g1')).toHaveLength(2)
    expect(state.rows.value.some((r) => r.sourceGroupId === 'g3')).toBe(false)
    expect(state.rouCostAjeNet.value).toBe(10 + 200)
  })

  it('pushToAdjustmentModule groups balanced lines and stores sourceGroupId', async () => {
    const { api } = await import('@/services/apiProxy')
    ;(api.post as any).mockResolvedValue({ entry_group_id: 'new-g1' })

    const allResponses = makeMap([
      {
        rowId: 'a1',
        category: '账项调整',
        description: '补记使用权资产',
        accountCode: '1901',
        debitAmount: 300,
        creditAmount: 0,
      },
      {
        rowId: 'a2',
        category: '账项调整',
        description: '补记使用权资产',
        accountCode: '2205',
        debitAmount: 0,
        creditAmount: 300,
      },
    ])
    const state = useH8Adjustment({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses: allResponses as any,
      isReadonly: ref(false),
      auditYear: ref(2024),
      onSave: (id, val) => {
        allResponses.value.set(id, {
          item_id: id,
          conclusion: null,
          remark: typeof val === 'string' ? val : JSON.stringify(val),
        })
      },
    })

    const pushed = await state.pushToAdjustmentModule()
    expect(pushed).toBe(1)
    expect(api.post).toHaveBeenCalled()
    expect(state.rows.value.every((r) => r.sourceGroupId === 'new-g1')).toBe(true)
  })
})
