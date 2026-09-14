/**
 * useI5Adjustment — I5-3 调整分录汇总单测
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import {
  useI5Adjustment,
  categoryFromLegacy,
  entryTypeFromCategory,
  buildI5ExpenseReclassDraft,
  buildI5CurrentPortionReclassDraft,
} from '../useI5Adjustment'

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

describe('buildI5ExpenseReclassDraft / buildI5CurrentPortionReclassDraft', () => {
  it('费用化重分类借贷成对平衡', () => {
    const lines = buildI5ExpenseReclassDraft({
      projectName: '预付工程款',
      amount: 50000,
    })
    expect(lines).toHaveLength(2)
    expect(lines[0].accountCode).toBe('6602')
    expect(lines[0].debitAmount).toBe(50000)
    expect(lines[1].accountCode).toBe('1911')
    expect(lines[1].creditAmount).toBe(50000)
  })

  it('一年内到期 RJE 借贷成对平衡', () => {
    const lines = buildI5CurrentPortionReclassDraft({
      projectName: '预付土地出让金',
      amount: 80000,
    })
    expect(lines).toHaveLength(2)
    expect(lines[0].entryType).toBe('RJE')
    expect(lines[0].accountCode).toBe('1461')
    expect(lines[1].accountCode).toBe('1911')
    expect(lines[0].debitAmount).toBe(80000)
    expect(lines[1].creditAmount).toBe(80000)
  })

  it('金额为 0 时不生成', () => {
    expect(buildI5ExpenseReclassDraft({ projectName: 'X', amount: 0 })).toEqual([])
    expect(buildI5CurrentPortionReclassDraft({ projectName: 'X', amount: 0 })).toEqual([])
  })
})

describe('useI5Adjustment', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('加载并规范化旧版 debit/credit 字段', () => {
    const allResponses = makeMap({
      'I5-3-rows': [
        {
          rowId: 'r1',
          summary: '费用化-工程款',
          entryType: 'AJE',
          debit: 10000,
          credit: 0,
          accountCode: '6602',
        },
      ],
    })
    const state = useI5Adjustment({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses: allResponses as any,
      isReadonly: ref(false),
      onSave: vi.fn(),
    })
    state.load()
    expect(state.rows.value).toHaveLength(1)
    expect(state.rows.value[0].debitAmount).toBe(10000)
    expect(state.rows.value[0].category).toBe('账项调整')
  })

  it('saveAndSync 触发保存与调整事件', () => {
    const dispatchSpy = vi.spyOn(window, 'dispatchEvent')
    const onSave = vi.fn()
    const allResponses = makeMap({
      'I5-3-rows': [
        {
          rowId: 'a',
          description: '测试',
          category: '账项调整',
          entryType: 'AJE',
          projectName: '预付工程款',
          debitAmount: 100,
          creditAmount: 0,
          accountCode: '6602',
        },
        {
          rowId: 'b',
          description: '测试',
          category: '账项调整',
          entryType: 'AJE',
          projectName: '预付工程款',
          debitAmount: 0,
          creditAmount: 100,
          accountCode: '1911',
        },
      ],
    })
    const state = useI5Adjustment({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses: allResponses as any,
      isReadonly: ref(false),
      onSave,
    })
    state.load()
    state.saveAndSync()
    expect(onSave).toHaveBeenCalled()
    expect(dispatchSpy).toHaveBeenCalled()
    const evt = dispatchSpy.mock.calls.find((c) => (c[0] as CustomEvent).type === 'i5:adjustments-changed')
    expect(evt).toBeTruthy()
    dispatchSpy.mockRestore()
  })
})
