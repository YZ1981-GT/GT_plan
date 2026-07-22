/**
 * useH1Adjustment — H1-3 调整分录汇总单测
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import {
  useH1Adjustment,
  categoryFromLegacy,
  entryTypeFromCategory,
} from '../useH1Adjustment'

vi.mock('@/utils/eventBus', () => ({
  eventBus: { emit: vi.fn(), on: vi.fn(), off: vi.fn() },
}))

function makeMap(rows?: unknown[]) {
  const m = new Map<string, { item_id: string; conclusion: null; remark: string | null }>()
  if (rows) {
    m.set('H1-3-rows', {
      item_id: 'H1-3-rows',
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

  it('maps legacy AJE/RJE and adjustType', () => {
    expect(categoryFromLegacy({ entryType: 'AJE' })).toBe('账项调整')
    expect(categoryFromLegacy({ entryType: 'RJE' })).toBe('报表调整')
    expect(categoryFromLegacy({ adjustType: 'RJE' })).toBe('报表调整')
    expect(categoryFromLegacy({ category: '重分类调整' })).toBe('报表调整')
  })

  it('derives entryType from category', () => {
    expect(entryTypeFromCategory('账项调整')).toBe('AJE')
    expect(entryTypeFromCategory('其他')).toBe('AJE')
    expect(entryTypeFromCategory('报表调整')).toBe('RJE')
  })
})

describe('useH1Adjustment', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('loads and normalizes legacy debit/credit/reference fields', () => {
    const allResponses = makeMap([
      {
        rowId: 'r1',
        description: '补提折旧',
        adjustType: 'AJE',
        debit: 1000,
        credit: 0,
        reference: 'H1-12',
        accountCode: '1602',
      },
    ])
    const saves: { id: string; val: unknown }[] = []
    const state = useH1Adjustment(ref('wp1'), ref('p1'), allResponses as any, {
      onSave: (id, val) => saves.push({ id, val }),
    })

    expect(state.rows.value).toHaveLength(1)
    const row = state.rows.value[0]
    expect(row.category).toBe('账项调整')
    expect(row.entryType).toBe('AJE')
    expect(row.debitAmount).toBe(1000)
    expect(row.indexRef).toBe('H1-12')
    expect(row.accountName).toBe('累计折旧')
  })

  it('addRow defaults to 账项调整 + 1601 and persists', () => {
    const allResponses = makeMap()
    const saves: { id: string; val: any }[] = []
    const state = useH1Adjustment(ref('wp1'), ref('p1'), allResponses as any, {
      onSave: (id, val) => saves.push({ id, val }),
    })

    state.addRow()
    expect(state.rows.value).toHaveLength(1)
    expect(state.rows.value[0].category).toBe('账项调整')
    expect(state.rows.value[0].accountCode).toBe('1601')
    expect(saves.some((s) => s.id === 'H1-3-rows')).toBe(true)
  })

  it('isBalanced and ajeNet/rjeNet', () => {
    const allResponses = makeMap([
      { category: '账项调整', debitAmount: 500, creditAmount: 0 },
      { category: '账项调整', debitAmount: 0, creditAmount: 500 },
      { category: '报表调整', debitAmount: 200, creditAmount: 0 },
      { category: '报表调整', debitAmount: 0, creditAmount: 200 },
    ])
    const state = useH1Adjustment(ref('wp1'), ref('p1'), allResponses as any)

    expect(state.isBalanced.value).toBe(true)
    expect(state.ajeNet.value).toBe(0)
    expect(state.rjeNet.value).toBe(0)

    state.updateCell(state.rows.value[0].rowId, 'debitAmount', 800)
    expect(state.isBalanced.value).toBe(false)
    expect(state.balanceDiff.value).toBe(300)
    expect(state.ajeNet.value).toBe(300)
  })

  it('changing category to 报表调整 sets entryType RJE', () => {
    const allResponses = makeMap()
    const state = useH1Adjustment(ref('wp1'), ref('p1'), allResponses as any, {
      onSave: () => {},
    })
    state.addRow()
    const id = state.rows.value[0].rowId
    state.updateCell(id, 'category', '报表调整')
    expect(state.rows.value[0].entryType).toBe('RJE')
  })

  it('pushToA13 skips 报表调整 by default', async () => {
    const { eventBus } = await import('@/utils/eventBus')
    const allResponses = makeMap([
      { category: '账项调整', description: 'AJE行', debitAmount: 100, creditAmount: 0 },
      { category: '报表调整', description: 'RJE行', debitAmount: 50, creditAmount: 0 },
    ])
    const state = useH1Adjustment(ref('wp1'), ref('p1'), allResponses as any, {
      onSave: () => {},
    })
    state.pushToA13()
    expect(eventBus.emit).toHaveBeenCalledWith(
      'a13:push-misstatement',
      expect.objectContaining({
        items: expect.arrayContaining([
          expect.objectContaining({ description: 'AJE行', entryType: 'AJE' }),
        ]),
      }),
    )
    const call = (eventBus.emit as any).mock.calls.find((c: any[]) => c[0] === 'a13:push-misstatement')
    expect(call[1].items).toHaveLength(1)
  })
})
