/**
 * useG6MainAdjustment — G6-4 调整分录汇总单元测试
 */
import { describe, it, expect, vi, afterEach } from 'vitest'
import { ref } from 'vue'
import {
  useG6MainAdjustment,
  aggregateG6WritebackNets,
  normalizeG6AdjustmentEntry,
  parseG6AdjustmentEntries,
  G6_4_STORAGE_KEY,
} from '../useG6MainAdjustment'
import { useG6MainAdjudication } from '../useG6MainAdjudication'
import type { ChecklistResponse } from '../useF1FormData'
import { parseG6AdjStore } from '../g6AdjudicationItems'

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn() },
  ElMessageBox: { prompt: vi.fn(), confirm: vi.fn() },
}))

vi.mock('@/services/apiProxy', () => ({
  api: { get: vi.fn().mockResolvedValue({ data: { items: [] } }) },
}))

const disposers: Array<() => void> = []
afterEach(() => {
  while (disposers.length) disposers.pop()?.()
})

function setupAdjustment(seed?: Record<string, string>) {
  const map = new Map<string, ChecklistResponse>()
  if (seed) {
    for (const [k, v] of Object.entries(seed)) {
      map.set(k, { item_id: k, conclusion: v, remark: v })
    }
  }
  const allResponses = ref(map)
  const adjustment = useG6MainAdjustment({
    allResponses,
    isReadonly: ref(false),
  })
  return { adjustment, allResponses }
}

describe('G6-4 调整分录 — 列结构与持久化', () => {
  it('兼容旧 AJE/RJE 字段并映射类别', () => {
    const entry = normalizeG6AdjustmentEntry(
      {
        entryType: 'RJE',
        summary: '重分类',
        accountCode: '150301',
        debitAmount: 100,
        creditAmount: 0,
        preparedBy: 'G6-4',
      },
      0,
    )
    expect(entry.category).toBe('报表调整')
    expect(entry.description).toBe('重分类')
    expect(entry.indexRef).toBe('G6-4')
    expect(entry.entryType).toBe('RJE')
  })

  it('从 G6-4-rows conclusion 解析分录', () => {
    const rows = [
      {
        description: '补提减值',
        category: '账项调整',
        accountCode: '150305',
        accountName: '其他债权投资减值准备',
        debitAmount: 0,
        creditAmount: 50000,
        indexRef: 'G6-4',
      },
      {
        description: '补提减值',
        category: '账项调整',
        accountCode: '6702',
        accountName: '信用减值损失',
        debitAmount: 50000,
        creditAmount: 0,
        indexRef: 'G6-4',
      },
    ]
    const parsed = parseG6AdjustmentEntries({ conclusion: JSON.stringify(rows) })
    expect(parsed).toHaveLength(2)
    expect(parsed[0].accountCode).toBe('150305')
  })

  it('按科目分流回写净额：成本/利息/减值', () => {
    const nets = aggregateG6WritebackNets([
      normalizeG6AdjustmentEntry(
        { category: '账项调整', accountCode: '150301', debitAmount: 100000, creditAmount: 0 },
        0,
      ),
      normalizeG6AdjustmentEntry(
        { category: '账项调整', accountCode: '150302', debitAmount: 0, creditAmount: 20000 },
        1,
      ),
      normalizeG6AdjustmentEntry(
        { category: '账项调整', accountCode: '150305', debitAmount: 0, creditAmount: 30000 },
        2,
      ),
      normalizeG6AdjustmentEntry(
        { category: '报表调整', accountCode: '150301', debitAmount: 999, creditAmount: 0 },
        3,
      ),
      normalizeG6AdjustmentEntry(
        { category: '账项调整', accountCode: '1012', debitAmount: 0, creditAmount: 50000 },
        4,
      ),
    ])
    expect(nets.costNet).toBe(100000)
    expect(nets.interestNet).toBe(-20000)
    expect(nets.impairmentNet).toBe(30000)
  })

  it('保存回写后持久化 G6-4-rows 并写入 G6-1', () => {
    const { adjustment, allResponses } = setupAdjustment()
    adjustment.entries.value = [
      normalizeG6AdjustmentEntry(
        {
          description: '调成本',
          category: '账项调整',
          accountCode: '150301',
          debitAmount: 10000,
          creditAmount: 0,
        },
        0,
      ),
      normalizeG6AdjustmentEntry(
        {
          description: '调成本',
          category: '账项调整',
          accountCode: '1012',
          debitAmount: 0,
          creditAmount: 10000,
        },
        1,
      ),
    ]
    const ok = adjustment.saveAndWriteback()
    expect(ok).toBe(true)
    const stored = allResponses.value.get(G6_4_STORAGE_KEY)
    expect(stored?.conclusion).toBeTruthy()
    const g61 = parseG6AdjStore(allResponses.value.get('G6-1-rows')?.conclusion)
    expect(g61['cost-portfolio']?.closingAdjustment).toBe(10000)
  })
})

describe('G6-1 监听 g6:adjustment-writeback', () => {
  it('事件回写分流到成本/减值组合行', () => {
    const map = new Map<string, ChecklistResponse>()
    const allResponses = ref(map)
    const adj = useG6MainAdjudication({
      wpId: ref('wp-g6'),
      projectId: ref('proj-1'),
      allResponses,
      isReadonly: ref(false),
    })
    disposers.push(adj.dispose)

    window.dispatchEvent(
      new CustomEvent('g6:adjustment-writeback', {
        detail: {
          costNet: 8000,
          interestNet: -500,
          impairmentNet: 2000,
          fvNet: 0,
        },
      }),
    )

    expect(adj.store.value['cost-portfolio']?.closingAdjustment).toBe(8000)
    expect(adj.store.value['interest-portfolio']?.closingAdjustment).toBe(-500)
    expect(adj.store.value['impairment-portfolio']?.closingAdjustment).toBe(2000)
  })
})
