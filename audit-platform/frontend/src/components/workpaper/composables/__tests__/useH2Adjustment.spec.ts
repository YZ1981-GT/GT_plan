/**
 * useH2Adjustment — H2-3 调整分录汇总单测
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import {
  useH2Adjustment,
  categoryFromLegacy,
  entryTypeFromCategory,
} from '../useH2Adjustment'

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
    m.set('H2-3-rows', {
      item_id: 'H2-3-rows',
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

  it('maps legacy AJE/RJE', () => {
    expect(categoryFromLegacy({ entryType: 'AJE' })).toBe('账项调整')
    expect(categoryFromLegacy({ entryType: 'RJE' })).toBe('报表调整')
    expect(categoryFromLegacy({ category: '重分类调整' })).toBe('报表调整')
  })

  it('derives entryType from category', () => {
    expect(entryTypeFromCategory('账项调整')).toBe('AJE')
    expect(entryTypeFromCategory('其他')).toBe('AJE')
    expect(entryTypeFromCategory('报表调整')).toBe('RJE')
  })
})

describe('useH2Adjustment', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('loads and normalizes legacy debit/credit/entryType fields', () => {
    const allResponses = makeMap([
      {
        rowId: 'r1',
        description: '补提减值',
        entryType: 'AJE',
        debit: 1000,
        credit: 0,
        indexRef: 'H2-15',
        accountCode: '6701',
      },
      {
        rowId: 'r2',
        summary: '补提减值',
        entryType: 'AJE',
        debit: 0,
        credit: 1000,
        accountCode: '1604',
        accountName: '在建工程减值准备',
      },
    ])
    const state = useH2Adjustment({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses: allResponses as any,
      isReadonly: ref(false),
    })

    expect(state.rows.value).toHaveLength(2)
    expect(state.rows.value[0].category).toBe('账项调整')
    expect(state.rows.value[0].debitAmount).toBe(1000)
    expect(state.rows.value[0].accountName).toBe('资产减值损失')
    expect(state.rows.value[1].description).toBe('补提减值')
    expect(state.isBalanced.value).toBe(true)
    expect(state.cipAjeNet.value).toBe(-1000)
  })

  it('addRow defaults to 账项调整 + 1604 and persists', () => {
    const allResponses = makeMap()
    const saves: { id: string; val: unknown }[] = []
    const state = useH2Adjustment({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses: allResponses as any,
      isReadonly: ref(false),
      onSave: (id, val) => saves.push({ id, val }),
    })
    state.addRow()
    expect(state.rows.value).toHaveLength(1)
    expect(state.rows.value[0].category).toBe('账项调整')
    expect(state.rows.value[0].accountCode).toBe('1604')
    expect(saves.some((s) => s.id === 'H2-3-rows')).toBe(true)
    const persisted = saves.find((s) => s.id === 'H2-3-rows')!.val as any[]
    expect(persisted[0].debit).toBe(0)
    expect(persisted[0].debitAmount).toBe(0)
    expect(persisted[0].category).toBe('账项调整')
  })

  it('isBalanced and cipAjeNet/cipRjeNet', () => {
    const allResponses = makeMap([
      {
        category: '账项调整',
        accountCode: '1604',
        debitAmount: 500,
        creditAmount: 0,
      },
      {
        category: '账项调整',
        accountCode: '2202',
        debitAmount: 0,
        creditAmount: 500,
      },
      {
        category: '报表调整',
        accountCode: '1604',
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
    const state = useH2Adjustment({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses: allResponses as any,
      isReadonly: ref(false),
    })
    expect(state.isBalanced.value).toBe(true)
    expect(state.cipAjeNet.value).toBe(500)
    expect(state.cipRjeNet.value).toBe(100)
    expect(state.ajeNet.value).toBe(0)
  })

  it('syncFromAdjustmentModule imports full groups containing 1604', async () => {
    const { api } = await import('@/services/apiProxy')
    ;(api.get as any).mockResolvedValue({
      data: {
        items: [
          {
            entry_group_id: 'g1',
            adjustment_type: 'aje',
            description: '[H2] 减值补提',
            line_items: [
              { standard_account_code: '6701', account_name: '资产减值损失', debit_amount: 200, credit_amount: 0 },
              { standard_account_code: '1604', account_name: '在建工程', debit_amount: 0, credit_amount: 200 },
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
        ],
      },
    })

    const allResponses = makeMap([
      { rowId: 'manual-1', category: '账项调整', accountCode: '1604', debitAmount: 10, creditAmount: 0 },
    ])
    const state = useH2Adjustment({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses: allResponses as any,
      isReadonly: ref(false),
      auditYear: ref(2024),
      onSave: (id, val) => {
        allResponses.value.set(id, { item_id: id, conclusion: null, remark: JSON.stringify(val) })
      },
    })

    const n = await state.syncFromAdjustmentModule()
    expect(n).toBe(2)
    expect(state.rows.value.some((r) => r.rowId === 'manual-1')).toBe(true)
    expect(state.rows.value.filter((r) => r.sourceGroupId === 'g1')).toHaveLength(2)
    expect(state.rows.value.every((r) => r.sourceGroupId !== 'g2')).toBe(true)
  })
})
