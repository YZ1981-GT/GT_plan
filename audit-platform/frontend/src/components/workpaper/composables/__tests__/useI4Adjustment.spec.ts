/**
 * useI4Adjustment — I4-3 长期待摊调整分录汇总单测
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import {
  useI4Adjustment,
  categoryFromLegacy,
  entryTypeFromCategory,
  buildI4ExpenseReclassDraft,
  buildI4AmortSupplementDraft,
} from '../useI4Adjustment'

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

describe('buildI4ExpenseReclassDraft / buildI4AmortSupplementDraft', () => {
  it('费用化重分类借贷成对平衡', () => {
    const lines = buildI4ExpenseReclassDraft({
      projectName: '办公室装修',
      amount: 50000,
    })
    expect(lines).toHaveLength(2)
    expect(lines[0].accountCode).toBe('6602')
    expect(lines[0].debitAmount).toBe(50000)
    expect(lines[1].accountCode).toBe('1801')
    expect(lines[1].creditAmount).toBe(50000)
    expect(lines[0].description).toBe(lines[1].description)
  })

  it('补提摊销借贷成对平衡', () => {
    const lines = buildI4AmortSupplementDraft({
      projectName: '开办费',
      amount: 12000,
    })
    expect(lines).toHaveLength(2)
    expect(lines[0].debitAmount).toBe(12000)
    expect(lines[1].creditAmount).toBe(12000)
    expect(lines[1].accountCode).toBe('1801')
  })

  it('金额为 0 时不生成', () => {
    expect(buildI4ExpenseReclassDraft({ projectName: 'X', amount: 0 })).toEqual([])
    expect(buildI4AmortSupplementDraft({ projectName: 'X', amount: 0 })).toEqual([])
  })
})

describe('useI4Adjustment', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('加载并规范化旧版 debit/entryType 字段', () => {
    const allResponses = makeMap({
      'I4-3-rows': [
        {
          rowId: 'r1',
          summary: '补提摊销-装修',
          entryType: 'AJE',
          debit: 10000,
          credit: 0,
          accountCode: '6602',
        },
        {
          rowId: 'r2',
          summary: '补提摊销-装修',
          entryType: 'AJE',
          debit: 0,
          credit: 10000,
          accountCode: '1801',
        },
      ],
    })
    const state = useI4Adjustment({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses,
    })
    expect(state.rows.value).toHaveLength(2)
    expect(state.rows.value[0].category).toBe('账项调整')
    expect(state.rows.value[0].debitAmount).toBe(10000)
    expect(state.rows.value[0].description).toBe('补提摊销-装修')
    expect(state.isBalanced.value).toBe(true)
    expect(state.ltpaAjeNet.value).toBe(-10000)
  })

  it('类别切换为报表调整时 entryType=RJE', () => {
    const allResponses = makeMap()
    const saved: Record<string, any> = {}
    const state = useI4Adjustment({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses,
      onSave: (id, v) => { saved[id] = v },
    })
    state.addRow({ description: '重分类测试', debitAmount: 100, creditAmount: 0 })
    const id = state.rows.value[0].rowId
    state.updateCell(id, 'category', '报表调整')
    expect(state.rows.value[0].entryType).toBe('RJE')
  })

  it('seedExpenseReclass 生成成对分录', () => {
    const allResponses = makeMap()
    const state = useI4Adjustment({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses,
      onSave: () => {},
    })
    const n = state.seedExpenseReclass({ projectName: '门店装修', amount: 8000 })
    expect(n).toBe(2)
    expect(state.isBalanced.value).toBe(true)
    expect(state.ltpaAjeNet.value).toBe(-8000)
  })

  it('迁移旧审计说明键', () => {
    const allResponses = makeMap({
      'I4-adjustment-audit-note': '旧说明',
      'I4-adjustment-audit-conclusion': '旧结论',
    })
    const state = useI4Adjustment({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses,
    })
    expect(state.auditNote.value).toBe('旧说明')
    expect(state.auditConclusion.value).toBe('旧结论')
  })
})
