/**
 * g13AdjStorage / useG13Adjustment — G13-3 调整分录
 */
import { describe, it, expect, vi } from 'vitest'
import { ref, computed } from 'vue'

vi.mock('../workpaperAuditYear', () => ({
  useWorkpaperAuditYear: () => computed(() => 2025),
}))

import {
  aggregateG13AdjustmentByBelong,
  aggregateG13AdjustmentByAdjRow,
  calcG13AdjustmentNet,
  categoryFromLegacy,
  inferG13BelongAccount,
  summarizeG13Adjustment,
} from '../g13AdjStorage'
import { useG13Adjustment } from '../useG13Adjustment'
import type { ChecklistResponse } from '../useF1FormData'

describe('g13AdjStorage', () => {
  it('categoryFromLegacy 兼容旧 entryType', () => {
    expect(categoryFromLegacy({ entryType: 'RJE' })).toBe('报表调整')
    expect(categoryFromLegacy({ entryType: 'AJE' })).toBe('账项调整')
    expect(categoryFromLegacy({ category: '其他' })).toBe('其他')
  })

  it('inferG13BelongAccount 按摘要关键词识别所属科目', () => {
    expect(inferG13BelongAccount({ description: '补提交易性金融资产公允变动' })).toBe('G1')
    expect(inferG13BelongAccount({ description: 'G10 负债公允下降' })).toBe('G10')
    expect(inferG13BelongAccount({ description: '投资性房地产重估' })).toBe('H3')
    expect(inferG13BelongAccount({ belongAccount: 'G8', description: '任意' })).toBe('G8')
  })

  it('calcG13AdjustmentNet：6101 贷−借，报表调整不计入', () => {
    const net = calcG13AdjustmentNet([
      { category: '账项调整', accountCode: '6101', debitAmount: 0, creditAmount: 100 },
      { category: '账项调整', accountCode: '1501', debitAmount: 100, creditAmount: 0 },
      { category: '报表调整', accountCode: '6101', debitAmount: 0, creditAmount: 50 },
      { category: '账项调整', accountCode: '6101', debitAmount: 30, creditAmount: 0 },
    ])
    expect(net).toBe(70)
  })

  it('aggregateG13AdjustmentByBelong 按所属科目分项', () => {
    const by = aggregateG13AdjustmentByBelong([
      { category: '账项调整', accountCode: '6101', belongAccount: 'G1', debitAmount: 0, creditAmount: 80 },
      { category: '账项调整', accountCode: '6101', description: '衍生工具', debitAmount: 20, creditAmount: 0 },
      { category: '报表调整', accountCode: '6101', belongAccount: 'G1', debitAmount: 0, creditAmount: 10 },
    ])
    expect(by.G1).toBe(80)
    expect(by.G9).toBe(-20)
    expect(by.other).toBe(0)
  })

  it('aggregateG13AdjustmentByAdjRow 衍生负债与 mapBelongToAdjRow 一致', () => {
    const byAdj = aggregateG13AdjustmentByAdjRow([
      { category: '账项调整', accountCode: '6101', belongAccount: 'G9', description: '衍生金融负债估值', debitAmount: 0, creditAmount: 30 },
      { category: '账项调整', accountCode: '6101', belongAccount: 'G10', description: '衍生工具重估', debitAmount: 10, creditAmount: 0 },
      { category: '账项调整', accountCode: '6101', belongAccount: 'G9', description: '远期合约资产', debitAmount: 0, creditAmount: 40 },
    ])
    expect(byAdj.derivative_liabilities).toBe(20) // 30 + (-10)
    expect(byAdj.derivative_assets).toBe(40)
  })

  it('summarizeG13Adjustment 区分 AJE/RJE 净额', () => {
    const s = summarizeG13Adjustment([
      { category: '账项调整', accountCode: '6101', debitAmount: 0, creditAmount: 100 },
      { category: '报表调整', accountCode: '6101', debitAmount: 40, creditAmount: 0 },
      { category: '账项调整', accountCode: '1501', debitAmount: 100, creditAmount: 0 },
    ])
    expect(s.ajeCount).toBe(2)
    expect(s.rjeCount).toBe(1)
    expect(s.netAje6101).toBe(100)
    expect(s.netRje6101).toBe(-40)
    expect(s.balanceDiff).toBe(40)
  })
})

describe('useG13Adjustment', () => {
  it('兼容旧 summary/entryType 存档并归一化', () => {
    const allResponses = ref(new Map<string, ChecklistResponse>([
      ['G13-aje-rows', {
        item_id: 'G13-aje-rows',
        conclusion: null,
        remark: JSON.stringify([{
          rowId: 'legacy',
          entryType: 'RJE',
          summary: '重分类至投资收益',
          accountCode: '6101',
          accountName: '公允价值变动收益',
          debitAmount: 10,
          creditAmount: 0,
        }]),
      } as ChecklistResponse],
    ]))
    const saves: Array<{ id: string; data: Partial<ChecklistResponse> }> = []
    const adj = useG13Adjustment({
      allResponses,
      isReadonly: ref(false),
      debouncedSave: (id, data) => saves.push({ id, data }),
    })
    expect(adj.rows.value).toHaveLength(1)
    expect(adj.rows.value[0].description).toBe('重分类至投资收益')
    expect(adj.rows.value[0].category).toBe('报表调整')
    expect(adj.rows.value[0].entryType).toBe('RJE')
    expect(adj.summary.value.netRje6101).toBe(-10)
    expect(adj.summary.value.netAje6101).toBe(0)
  })

  it('syncToDetail 仅回写账项调整并按所属科目拆分', () => {
    const allResponses = ref(new Map<string, ChecklistResponse>())
    const received: Array<Record<string, number>> = []
    const saves: Array<{ id: string; data: Partial<ChecklistResponse> }> = []
    const adj = useG13Adjustment({
      allResponses,
      isReadonly: ref(false),
      debouncedSave: (id, data) => saves.push({ id, data }),
      applyAdjustmentToDetail: (byBelong) => received.push(byBelong),
    })
    adj.addRow()
    const r1 = adj.rows.value[0].rowId
    adj.updateRow(r1, {
      description: 'G1 公允上调',
      belongAccount: 'G1',
      accountCode: '6101',
      debitAmount: 0,
      creditAmount: 50,
    })
    adj.addRow()
    const r2 = adj.rows.value[1].rowId
    adj.updateRow(r2, {
      description: '对方科目',
      accountCode: '1501',
      belongAccount: 'G1',
      debitAmount: 50,
      creditAmount: 0,
    })
    adj.addRow()
    const r3 = adj.rows.value[2].rowId
    adj.updateRow(r3, {
      description: '报表重分类',
      category: '报表调整',
      accountCode: '6101',
      belongAccount: 'G1',
      debitAmount: 20,
      creditAmount: 0,
    })
    adj.addRow()
    const r4 = adj.rows.value[3].rowId
    adj.updateRow(r4, {
      description: '报表重分类对方',
      category: '报表调整',
      accountCode: '6111',
      belongAccount: 'G1',
      debitAmount: 0,
      creditAmount: 20,
    })
    expect(adj.isBalanced.value).toBe(true)
    expect(adj.rows.value.filter((r) => r.category === '报表调整')).toHaveLength(2)
    adj.syncToDetail()
    expect(received).toHaveLength(1)
    expect(received[0].G1).toBe(50)
    expect(adj.summary.value.netAje6101).toBe(50)

    const overlaySave = saves.find((s) => s.id === 'G13-aje-adj-overlay')
    expect(overlaySave).toBeTruthy()
    const overlay = JSON.parse(String(overlaySave!.data.remark))
    expect(overlay.trading_assets).toBe(50)
  })

  it('syncToAdjudicationOverlay 无明细回调时仍写入 G13-1 overlay', () => {
    const saves: Array<{ id: string; data: Partial<ChecklistResponse> }> = []
    const adj = useG13Adjustment({
      allResponses: ref(new Map()),
      isReadonly: ref(false),
      debouncedSave: (id, data) => saves.push({ id, data }),
    })
    adj.addRow()
    adj.updateRow(adj.rows.value[0].rowId, {
      belongAccount: 'H3',
      accountCode: '6101',
      debitAmount: 0,
      creditAmount: 120,
    })
    adj.addRow()
    adj.updateRow(adj.rows.value[1].rowId, {
      accountCode: '1521',
      debitAmount: 120,
      creditAmount: 0,
    })
    const overlay = adj.syncToAdjudicationOverlay()
    expect(overlay.investment_property).toBe(120)
    expect(saves.some((s) => s.id === 'G13-aje-adj-overlay')).toBe(true)
  })

  it('人工选择所属科目后改摘要不覆盖', () => {
    const allResponses = ref(new Map<string, ChecklistResponse>())
    const adj = useG13Adjustment({
      allResponses,
      isReadonly: ref(false),
      debouncedSave: () => {},
    })
    adj.addRow()
    const id = adj.rows.value[0].rowId
    adj.updateRow(id, { belongAccount: 'H3', description: '初始' })
    adj.updateRow(id, { description: '补提交易性金融资产公允变动' })
    expect(adj.rows.value[0].belongAccount).toBe('H3')
  })
})
