/**
 * g14AdjStorage / useG14Adjustment — G14-3 调整分录
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, computed } from 'vue'

vi.mock('../workpaperAuditYear', () => ({
  useWorkpaperAuditYear: () => computed(() => 2025),
}))

vi.mock('@/services/apiProxy', () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
  },
}))

vi.mock('@/utils/eventBus', () => ({
  eventBus: {
    on: vi.fn(),
    off: vi.fn(),
    emit: vi.fn(),
  },
}))

import {
  aggregateG14AdjustmentByRow,
  calcG14AdjustmentNet,
  categoryFromLegacy,
  inferG14AdjudicationRowKey,
  summarizeG14Adjustment,
} from '../g14AdjStorage'
import { useG14Adjustment } from '../useG14Adjustment'
import type { ChecklistResponse } from '../useF1FormData'
import { api } from '@/services/apiProxy'

describe('g14AdjStorage', () => {
  it('categoryFromLegacy 兼容旧 entryType / 重分类调整', () => {
    expect(categoryFromLegacy({ entryType: 'RJE' })).toBe('报表调整')
    expect(categoryFromLegacy({ entryType: 'AJE' })).toBe('账项调整')
    expect(categoryFromLegacy({ category: '其他' })).toBe('其他')
    expect(categoryFromLegacy({ category: '重分类调整' })).toBe('报表调整')
  })

  it('inferG14AdjudicationRowKey 按摘要关键词识别回写行', () => {
    expect(inferG14AdjudicationRowKey({ description: '补提应收账款坏账损失' })).toBe('ar')
    expect(inferG14AdjudicationRowKey({ description: '其他应收款 ECL 转回' })).toBe('othar')
    expect(inferG14AdjudicationRowKey({ description: '债权投资减值补提' })).toBe('debt')
    expect(inferG14AdjudicationRowKey({ description: '合同资产减值准备补提' })).toBe('ca')
    expect(inferG14AdjudicationRowKey({ description: '财务担保预计损失' })).toBe('guarantee')
    expect(inferG14AdjudicationRowKey({ adjudicationRowKey: 'notes', description: '任意' })).toBe('notes')
  })

  it('calcG14AdjustmentNet：6702 借−贷，报表调整不计入', () => {
    const net = calcG14AdjustmentNet([
      { category: '账项调整', accountCode: '6702', debitAmount: 100, creditAmount: 0 },
      { category: '账项调整', accountCode: '1231', debitAmount: 0, creditAmount: 100 },
      { category: '报表调整', accountCode: '6702', debitAmount: 50, creditAmount: 0 },
      { category: '账项调整', accountCode: '6702', debitAmount: 0, creditAmount: 30 },
    ])
    expect(net).toBe(70)
  })

  it('aggregateG14AdjustmentByRow 按回写行分项', () => {
    const by = aggregateG14AdjustmentByRow([
      { category: '账项调整', accountCode: '6702', adjudicationRowKey: 'ar', debitAmount: 80, creditAmount: 0 },
      { category: '账项调整', accountCode: '6702', description: '补提应收账款', debitAmount: 20, creditAmount: 0 },
      { category: '报表调整', accountCode: '6702', adjudicationRowKey: 'ar', debitAmount: 10, creditAmount: 0 },
      { category: '账项调整', accountCode: '1231', adjudicationRowKey: 'ar', debitAmount: 0, creditAmount: 100 },
    ])
    expect(by.ar).toBe(100)
    expect(by.other).toBe(0)
  })

  it('summarizeG14Adjustment 区分 AJE/RJE 净额', () => {
    const s = summarizeG14Adjustment([
      { category: '账项调整', accountCode: '6702', debitAmount: 100, creditAmount: 0 },
      { category: '报表调整', accountCode: '6702', debitAmount: 0, creditAmount: 40 },
      { category: '账项调整', accountCode: '1231', debitAmount: 0, creditAmount: 100 },
    ])
    expect(s.ajeCount).toBe(2)
    expect(s.rjeCount).toBe(1)
    expect(s.netAje6702).toBe(100)
    expect(s.netRje6702).toBe(-40)
    expect(s.balanceDiff).toBe(-40)
  })
})

describe('useG14Adjustment', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('兼容旧 summary/entryType/重分类调整存档并归一化', () => {
    const allResponses = ref(new Map<string, ChecklistResponse>([
      ['G14-aje-rows', {
        item_id: 'G14-aje-rows',
        conclusion: null,
        remark: JSON.stringify([{
          rowId: 'legacy',
          entryType: 'RJE',
          summary: '重分类至资产减值损失',
          category: '重分类调整',
          accountCode: '6702',
          accountName: '信用减值损失',
          debitAmount: 10,
          creditAmount: 0,
        }]),
      } as ChecklistResponse],
    ]))
    const saves: Array<{ id: string; data: Partial<ChecklistResponse> }> = []
    const adj = useG14Adjustment({
      allResponses,
      isReadonly: ref(false),
      debouncedSave: (id, data) => saves.push({ id, data }),
    })
    expect(adj.rows.value).toHaveLength(1)
    expect(adj.rows.value[0].description).toBe('重分类至资产减值损失')
    expect(adj.rows.value[0].category).toBe('报表调整')
    expect(adj.rows.value[0].entryType).toBe('RJE')
    expect(adj.summary.value.netRje6702).toBe(10)
    expect(adj.summary.value.netAje6702).toBe(0)
  })

  it('syncToDetail 按回写行分项回写 6702 账项净额', () => {
    const allResponses = ref(new Map())
    let applied: Record<string, number> | null = null
    const adj = useG14Adjustment({
      allResponses,
      isReadonly: ref(false),
      debouncedSave: () => {},
      applyAdjustmentToDetail: (byRow) => { applied = byRow },
    })

    adj.addRow()
    const id1 = adj.rows.value[0].rowId
    adj.updateRow(id1, {
      category: '账项调整',
      accountCode: '6702',
      adjudicationRowKey: 'ar',
      debitAmount: 5000,
      creditAmount: 0,
      description: '补提应收账款 ECL',
    })
    adj.addRow()
    const id2 = adj.rows.value[1].rowId
    adj.updateRow(id2, {
      category: '账项调整',
      accountCode: '1231',
      adjudicationRowKey: 'ar',
      debitAmount: 0,
      creditAmount: 5000,
      description: '补提应收账款 ECL',
    })
    adj.syncToDetail()

    expect(applied?.ar).toBe(5000)
    expect(applied?.other).toBe(0)
  })

  it('从调整分录模块同步含 6702 的分录组', async () => {
    ;(api.get as any).mockResolvedValue({
      data: {
        items: [{
          entry_group_id: 'eg-g14-1',
          adjustment_no: 'AJE-014',
          adjustment_type: 'aje',
          description: '补提信用减值',
          line_items: [
            { standard_account_code: '6702', account_name: '信用减值损失', debit_amount: 1000, credit_amount: 0 },
            { standard_account_code: '1231', account_name: '坏账准备', debit_amount: 0, credit_amount: 1000 },
          ],
        }],
      },
    })
    const allResponses = ref(new Map())
    const adj = useG14Adjustment({
      allResponses,
      isReadonly: ref(false),
      projectId: ref('proj-1'),
      debouncedSave: () => {},
    })
    const n = await adj.syncFromAdjustmentModule()
    expect(n).toBe(2)
    expect(adj.rows.value.every((r) => r.sourceGroupId === 'eg-g14-1')).toBe(true)
    expect(adj.rows.value.some((r) => r.accountCode === '6702')).toBe(true)
  })

  it('推送至中央调整分录模块并回写 sourceGroupId', async () => {
    ;(api.post as any).mockResolvedValue({ entry_group_id: 'eg-push-1' })
    const allResponses = ref(new Map())
    const adj = useG14Adjustment({
      allResponses,
      isReadonly: ref(false),
      projectId: ref('proj-1'),
      debouncedSave: () => {},
    })
    adj.addRow()
    const id1 = adj.rows.value[0].rowId
    adj.updateRow(id1, {
      description: '补提',
      accountCode: '6702',
      debitAmount: 200,
      creditAmount: 0,
    })
    adj.addRow()
    const id2 = adj.rows.value[1].rowId
    adj.updateRow(id2, {
      description: '补提',
      accountCode: '1231',
      debitAmount: 0,
      creditAmount: 200,
    })
    const pushed = await adj.pushToCentralModule()
    expect(pushed).toBe(1)
    expect(adj.rows.value.every((r) => r.sourceGroupId === 'eg-push-1')).toBe(true)
  })
})
