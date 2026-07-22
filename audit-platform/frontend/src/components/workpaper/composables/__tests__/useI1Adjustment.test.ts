/**
 * useI1Adjustment — I1-3 调整分录汇总单测
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import {
  useI1Adjustment,
  categoryFromLegacy,
  entryTypeFromCategory,
  resolveI1AuditYear,
  yearFromPeriodResponses,
} from '../useI1Adjustment'

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
    m.set('I1-3-rows', {
      item_id: 'I1-3-rows',
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
  })

  it('derives entryType from category', () => {
    expect(entryTypeFromCategory('账项调整')).toBe('AJE')
    expect(entryTypeFromCategory('其他')).toBe('AJE')
    expect(entryTypeFromCategory('报表调整')).toBe('RJE')
  })
})

describe('useI1Adjustment', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('loads and normalizes legacy debit/entryType fields', () => {
    const allResponses = makeMap([
      {
        rowId: 'r1',
        description: '补记无形资产',
        entryType: 'AJE',
        debit: 10000,
        credit: 0,
        accountCode: '1701',
      },
      {
        rowId: 'r2',
        description: '补记无形资产',
        entryType: 'AJE',
        debit: 0,
        credit: 10000,
        accountCode: '1002',
        accountName: '银行存款',
      },
    ])
    const state = useI1Adjustment({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses: allResponses as any,
      isReadonly: ref(false),
    })

    expect(state.rows.value).toHaveLength(2)
    expect(state.rows.value[0].category).toBe('账项调整')
    expect(state.rows.value[0].debitAmount).toBe(10000)
    expect(state.rows.value[0].accountName).toBe('无形资产')
    expect(state.isBalanced.value).toBe(true)
    expect(state.costAjeNet.value).toBe(10000)
  })

  it('computes amort/impair nets separately', () => {
    const allResponses = makeMap([
      { description: '补提摊销', category: '账项调整', accountCode: '5601', debitAmount: 500, creditAmount: 0 },
      { description: '补提摊销', category: '账项调整', accountCode: '1702', debitAmount: 0, creditAmount: 500 },
      { description: '补提减值', category: '账项调整', accountCode: '5601', debitAmount: 200, creditAmount: 0 },
      { description: '补提减值', category: '账项调整', accountCode: '1703', debitAmount: 0, creditAmount: 200 },
    ])
    const state = useI1Adjustment({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses: allResponses as any,
    })
    expect(state.isBalanced.value).toBe(true)
    expect(state.amortAjeNet.value).toBe(-500)
    expect(state.impairAjeNet.value).toBe(-200)
  })

  it('pushToAdjustmentModule requires balance and year', async () => {
    const { api } = await import('@/services/apiProxy')
    const allResponses = makeMap([
      { description: 'x', category: '账项调整', accountCode: '1701', debitAmount: 100, creditAmount: 0 },
    ])
    const state = useI1Adjustment({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses: allResponses as any,
      auditYear: ref(2025),
    })
    const n = await state.pushToAdjustmentModule()
    expect(n).toBe(0)
    expect(state.lastSyncMsg.value).toContain('借贷不平衡')
    expect(api.post).not.toHaveBeenCalled()
  })

  it('pushToAdjustmentModule posts balanced group', async () => {
    const { api } = await import('@/services/apiProxy')
    ;(api.post as any).mockResolvedValue({ entry_group_id: 'g-1' })
    const saved: Record<string, any> = {}
    const allResponses = makeMap([
      { description: '补记', category: '账项调整', accountCode: '1701', debitAmount: 1000, creditAmount: 0 },
      { description: '补记', category: '账项调整', accountCode: '1002', debitAmount: 0, creditAmount: 1000 },
    ])
    const state = useI1Adjustment({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses: allResponses as any,
      auditYear: ref(2025),
      onSave: (id, v) => { saved[id] = v },
    })
    const n = await state.pushToAdjustmentModule()
    expect(n).toBe(1)
    expect(api.post).toHaveBeenCalled()
    expect(state.rows.value.every((r) => r.sourceGroupId === 'g-1')).toBe(true)
  })
  it('flags unbalanced description groups while whole table may balance', () => {
    const allResponses = makeMap([
      { description: '事项A', category: '账项调整', accountCode: '1701', debitAmount: 100, creditAmount: 0 },
      { description: '事项A', category: '账项调整', accountCode: '1002', debitAmount: 0, creditAmount: 100 },
      { description: '事项B', category: '账项调整', accountCode: '1701', debitAmount: 50, creditAmount: 0 },
      { description: '事项C', category: '账项调整', accountCode: '1002', debitAmount: 0, creditAmount: 50 },
    ])
    const state = useI1Adjustment({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses: allResponses as any,
    })
    expect(state.isBalanced.value).toBe(true)
    expect(state.groupBalanceIssues.value).toHaveLength(2)
    expect(state.groupBalanceIssues.value.map((g) => g.description).sort()).toEqual(['事项B', '事项C'])
  })
})

describe('resolveI1AuditYear', () => {
  it('prefers props.year over runtime and period', () => {
    const m = new Map([
      ['I1-amort-period', { item_id: 'I1-amort-period', conclusion: null, remark: JSON.stringify({ periodEnd: '2024-12-31' }) }],
    ])
    expect(resolveI1AuditYear({
      propYear: 2025,
      runtimeYear: 2023,
      allResponses: m,
    })).toBe(2025)
  })

  it('falls back to runtime then period end then calendar', () => {
    expect(resolveI1AuditYear({
      runtimeYear: '2024',
      now: new Date('2030-01-01'),
    })).toBe(2024)

    const m = new Map([
      ['I1-11-period', { item_id: 'I1-11-period', conclusion: null, remark: JSON.stringify({ periodEnd: '2022-06-30' }) }],
    ])
    expect(yearFromPeriodResponses(m)).toBe(2022)
    expect(resolveI1AuditYear({
      allResponses: m,
      now: new Date('2030-01-01'),
    })).toBe(2022)

    expect(resolveI1AuditYear({ now: new Date('2030-06-01') })).toBe(2030)
  })
})
