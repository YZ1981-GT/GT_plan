/**
 * useI3Adjustment — I3-3 商誉调整分录汇总单测
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import {
  useI3Adjustment,
  categoryFromLegacy,
  entryTypeFromCategory,
  buildI3ImpairmentDraftLines,
} from '../useI3Adjustment'

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

function makeMap(extra?: Record<string, unknown>) {
  const m = new Map<string, { item_id: string; conclusion: null; remark: string | null }>()
  if (extra) {
    for (const [k, v] of Object.entries(extra)) {
      m.set(k, {
        item_id: k,
        conclusion: null,
        remark: typeof v === 'string' ? v : JSON.stringify(v),
      })
    }
  }
  return ref(m)
}

describe('categoryFromLegacy / entryTypeFromCategory', () => {
  it('maps Excel categories', () => {
    expect(categoryFromLegacy({ category: '账项调整' })).toBe('账项调整')
    expect(categoryFromLegacy({ category: '报表调整' })).toBe('报表调整')
    expect(categoryFromLegacy({ entryType: 'RJE' })).toBe('报表调整')
  })

  it('derives entryType from category', () => {
    expect(entryTypeFromCategory('账项调整')).toBe('AJE')
    expect(entryTypeFromCategory('其他')).toBe('AJE')
    expect(entryTypeFromCategory('报表调整')).toBe('RJE')
  })
})

describe('buildI3ImpairmentDraftLines', () => {
  it('builds balanced debit loss / credit goodwill pair', () => {
    const lines = buildI3ImpairmentDraftLines({
      cguName: 'CGU-A',
      goodwillImpairment: 500000,
    })
    expect(lines).toHaveLength(2)
    expect(lines[0].accountCode).toBe('6701')
    expect(lines[0].debitAmount).toBe(500000)
    expect(lines[1].accountCode).toBe('1711')
    expect(lines[1].creditAmount).toBe(500000)
    expect(lines[0].description).toBe(lines[1].description)
  })

  it('returns empty when impairment is zero', () => {
    expect(buildI3ImpairmentDraftLines({ cguName: 'X', goodwillImpairment: 0 })).toEqual([])
  })
})

describe('useI3Adjustment', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('loads and normalizes legacy debit/entryType fields', () => {
    const allResponses = makeMap({
      'I3-3-rows': [
        {
          rowId: 'r1',
          summary: '计提商誉减值-CGU-A',
          entryType: 'AJE',
          debit: 100000,
          credit: 0,
          accountCode: '6701',
        },
        {
          rowId: 'r2',
          summary: '计提商誉减值-CGU-A',
          entryType: 'AJE',
          debit: 0,
          credit: 100000,
          accountCode: '1711',
        },
      ],
    })
    const state = useI3Adjustment({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses: allResponses as any,
      isReadonly: ref(false),
    })

    expect(state.rows.value).toHaveLength(2)
    expect(state.rows.value[0].category).toBe('账项调整')
    expect(state.rows.value[0].description).toBe('计提商誉减值-CGU-A')
    expect(state.rows.value[0].debitAmount).toBe(100000)
    expect(state.isBalanced.value).toBe(true)
    expect(state.goodwillAjeNet.value).toBe(-100000)
  })

  it('seeds draft lines from I3-6 goodwillImpairment', () => {
    const allResponses = makeMap({
      'I3-6-rows': [
        { cguName: 'CGU-A', goodwillImpairment: 200000, cguBookValue: 1000000 },
        { cguName: 'CGU-B', goodwillImpairment: 0 },
      ],
    })
    const saves: Array<[string, any]> = []
    const state = useI3Adjustment({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses: allResponses as any,
      isReadonly: ref(false),
      onSave: (id, v) => saves.push([id, v]),
    })

    const n = state.seedFromI36()
    expect(n).toBe(2)
    expect(state.rows.value).toHaveLength(2)
    expect(state.isBalanced.value).toBe(true)
    expect(state.goodwillAjeNet.value).toBe(-200000)
    expect(saves.some(([k]) => k === 'I3-3-rows')).toBe(true)
  })

  it('detects group imbalance while table may still sum to zero', () => {
    const allResponses = makeMap({
      'I3-3-rows': [
        { description: '事项A', entryType: 'AJE', accountCode: '6701', debit: 100, credit: 0 },
        { description: '事项B', entryType: 'AJE', accountCode: '1711', debit: 0, credit: 100 },
      ],
    })
    const state = useI3Adjustment({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses: allResponses as any,
      isReadonly: ref(false),
    })
    expect(state.isBalanced.value).toBe(true)
    expect(state.groupBalanceIssues.value.length).toBe(2)
  })
})
