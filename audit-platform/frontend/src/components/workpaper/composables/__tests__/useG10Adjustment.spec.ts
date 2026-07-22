/**
 * useG10Adjustment / g10AdjStorage — G10-3 单元测试
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import {
  summarizeG10Adjustment,
  aggregateG10AdjustmentAjeRjeByRow,
  applyG10AdjustmentWritebacks,
  defaultG10AdjStore,
  calcG10AdjustmentNet,
  compareG10Adj3VsG101Writeback,
  sumG10BookFvAdjustmentNet,
  G10_AJE_ROWS_KEY,
  G10_ADJ_ROWS_KEY,
} from '../g10AdjStorage'
import { useG10Adjustment, G10_ADJ_ACCOUNT_OPTIONS } from '../useG10Adjustment'
import type { ChecklistResponse } from '../useF1FormData'

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), warning: vi.fn(), info: vi.fn() },
  ElMessageBox: {
    prompt: vi.fn(),
    confirm: vi.fn().mockResolvedValue(true),
  },
}))

vi.mock('@/services/apiProxy', () => ({
  api: { get: vi.fn(), post: vi.fn() },
}))

vi.mock('@/utils/eventBus', () => ({
  eventBus: { on: vi.fn(), off: vi.fn(), emit: vi.fn() },
}))

describe('g10AdjStorage 汇总与回写勾稽', () => {
  it('summarizeG10Adjustment 分项统计', () => {
    const s = summarizeG10Adjustment([
      { entryType: 'AJE', accountCode: '2101', debitAmount: 0, creditAmount: 100 },
      { entryType: 'AJE', accountCode: '6101', debitAmount: 100, creditAmount: 0 },
      { entryType: 'RJE', accountCode: '2101', debitAmount: 20, creditAmount: 0 },
      { entryType: 'RJE', accountCode: '2501', debitAmount: 0, creditAmount: 20 },
    ])
    expect(s.rowCount).toBe(4)
    expect(s.ajeCount).toBe(2)
    expect(s.rjeCount).toBe(2)
    expect(s.balanceDiff).toBe(0)
    expect(s.net2101).toBe(80)
    expect(s.fvPlNet).toBe(100)
  })

  it('aggregate + apply 回写 book_fv 分项', () => {
    const wb = aggregateG10AdjustmentAjeRjeByRow([
      {
        entryType: 'AJE',
        accountCode: '2101',
        debitAmount: 0,
        creditAmount: 80,
        liabilityType: '衍生金融负债',
      },
    ])
    expect(wb.byRow.book_derivative_liability?.closingAje).toBe(80)
    const next = applyG10AdjustmentWritebacks(defaultG10AdjStore(), wb)
    expect(sumG10BookFvAdjustmentNet(next)).toBe(80)
  })

  it('compareG10Adj3VsG101Writeback 一致时 diff=0', () => {
    const wb = aggregateG10AdjustmentAjeRjeByRow([
      { entryType: 'AJE', accountCode: '2101', debitAmount: 0, creditAmount: 50 },
      { entryType: 'AJE', accountCode: '6101', debitAmount: 50, creditAmount: 0 },
    ])
    const store = applyG10AdjustmentWritebacks(defaultG10AdjStore(), wb)
    const m = new Map<string, ChecklistResponse>([
      [G10_AJE_ROWS_KEY, {
        item_id: G10_AJE_ROWS_KEY,
        remark: JSON.stringify([
          { entryType: 'AJE', accountCode: '6101', debitAmount: 50, creditAmount: 0 },
          { entryType: 'AJE', accountCode: '2101', debitAmount: 0, creditAmount: 50 },
        ]),
      } as ChecklistResponse],
      [G10_ADJ_ROWS_KEY, { item_id: G10_ADJ_ROWS_KEY, remark: JSON.stringify(store) } as ChecklistResponse],
    ])
    const cross = compareG10Adj3VsG101Writeback(m)
    expect(cross?.adj3Net2101).toBe(50)
    expect(cross?.diff).toBe(0)
  })
})

describe('useG10Adjustment', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('科目选项含 2101/6101/2501', () => {
    const codes = G10_ADJ_ACCOUNT_OPTIONS.map((o) => o.code)
    expect(codes).toContain('2101')
    expect(codes).toContain('6101')
    expect(codes).toContain('2501')
  })

  it('加载行并计算借贷平衡与 2101 净额', () => {
    const allResponses = ref(new Map<string, ChecklistResponse>([
      [G10_AJE_ROWS_KEY, {
        item_id: G10_AJE_ROWS_KEY,
        conclusion: null,
        remark: JSON.stringify([
          {
            rowId: 'a1', seq: 1, entryType: 'AJE', date: '2025-01-01',
            summary: '负债上升', accountCode: '6101', accountName: '公允价值变动损益',
            debitAmount: 200, creditAmount: 0, preparedBy: '', remark: '', indexRef: '', liabilityType: '', adjudicationRowKey: '',
          },
          {
            rowId: 'a2', seq: 2, entryType: 'AJE', date: '2025-01-01',
            summary: '负债上升（公允变动）', accountCode: '2101', accountName: '交易性金融负债',
            debitAmount: 0, creditAmount: 200, preparedBy: '', remark: '', indexRef: '', liabilityType: '', adjudicationRowKey: '',
          },
        ]),
      } as ChecklistResponse],
    ]))

    const adj = useG10Adjustment({
      allResponses,
      debouncedSave: (id, d) => {
        allResponses.value.set(id, {
          item_id: id,
          conclusion: d.conclusion ?? null,
          remark: d.remark ?? null,
        } as ChecklistResponse)
      },
      isReadonly: ref(false),
      projectId: ref(''),
    })

    expect(adj.rows.value).toHaveLength(2)
    expect(adj.isBalanced.value).toBe(true)
    expect(adj.summary.value.net2101).toBe(200)
    expect(adj.summary.value.fvPlNet).toBe(200)
    expect(calcG10AdjustmentNet(adj.rows.value)).toBe(200)
  })

  it('updateRow 选科目自动带名称', () => {
    const allResponses = ref(new Map<string, ChecklistResponse>([
      [G10_AJE_ROWS_KEY, {
        item_id: G10_AJE_ROWS_KEY,
        conclusion: null,
        remark: JSON.stringify([{
          rowId: 'r1', seq: 1, entryType: 'AJE', date: '',
          summary: 't', accountCode: '2101', accountName: '交易性金融负债',
          debitAmount: 0, creditAmount: 0, preparedBy: '', remark: '', indexRef: '', liabilityType: '', adjudicationRowKey: '',
        }]),
      } as ChecklistResponse],
    ]))
    const adj = useG10Adjustment({
      allResponses,
      debouncedSave: (id, d) => {
        allResponses.value.set(id, {
          item_id: id,
          conclusion: null,
          remark: d.remark ?? null,
        } as ChecklistResponse)
      },
      isReadonly: ref(false),
      projectId: ref(''),
    })
    adj.updateRow('r1', { accountCode: '6101' })
    expect(adj.rows.value[0].accountName).toBe('公允价值变动损益')
  })
})
