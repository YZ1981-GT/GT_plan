/**
 * useG9Adjustment / g9AdjStorage — G9-3 单元测试
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import {
  summarizeG9Adjustment,
  aggregateG9AdjustmentAjeRje,
  applyG9AdjustmentWriteback,
  defaultG9AdjStore,
  calcG9AdjustmentNet,
} from '../g9AdjStorage'
import { useG9Adjustment, G9_ADJ_ACCOUNT_OPTIONS } from '../useG9Adjustment'
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

describe('g9AdjStorage 汇总', () => {
  it('summarizeG9Adjustment 分项统计', () => {
    const s = summarizeG9Adjustment([
      { entryType: 'AJE', accountCode: '1504', debitAmount: 100, creditAmount: 0 },
      { entryType: 'AJE', accountCode: '6101', debitAmount: 0, creditAmount: 100 },
      { entryType: 'RJE', accountCode: '1504', debitAmount: 0, creditAmount: 30 },
      { entryType: 'RJE', accountCode: '4002', debitAmount: 30, creditAmount: 0 },
    ])
    expect(s.rowCount).toBe(4)
    expect(s.ajeCount).toBe(2)
    expect(s.rjeCount).toBe(2)
    expect(s.totalDebits).toBe(130)
    expect(s.totalCredits).toBe(130)
    expect(s.balanceDiff).toBe(0)
    expect(s.net1504).toBe(70)
    expect(s.ajeNet1504).toBe(100)
    expect(s.rjeNet1504).toBe(-30)
    expect(s.fvPlNet).toBe(-100)
    expect(s.ociNet).toBe(30)
  })

  it('calcG9AdjustmentNet 汇总 G9 科目别名', () => {
    expect(calcG9AdjustmentNet([
      { accountCode: '1519', debitAmount: 50, creditAmount: 10 },
      { accountCode: '6101', debitAmount: 0, creditAmount: 40 },
    ])).toBe(40)
    expect(calcG9AdjustmentNet([
      { accountCode: '1504', debitAmount: 50, creditAmount: 10 },
    ])).toBe(40)
  })

  it('aggregate + apply 回写', () => {
    const wb = aggregateG9AdjustmentAjeRje([
      { entryType: 'AJE', accountCode: '1504', debitAmount: 100, creditAmount: 0 },
      { entryType: 'RJE', accountCode: '1504', debitAmount: 0, creditAmount: 30 },
    ])
    expect(wb.closingAje).toBe(100)
    expect(wb.closingRje).toBe(-30)
    const next = applyG9AdjustmentWriteback(defaultG9AdjStore(), wb)
    expect(next.fvtpl_1?.closingAJE).toBe(100)
    expect(next.fvtpl_1?.closingRJE).toBe(-30)
  })
})

describe('useG9Adjustment', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('科目选项含 1519/6101/4002', () => {
    const codes = G9_ADJ_ACCOUNT_OPTIONS.map((o) => o.code)
    expect(codes).toContain('1519')
    expect(codes).toContain('6101')
    expect(codes).toContain('4002')
  })

  it('加载行并计算借贷平衡与回写预览', () => {
    const saves: Array<{ id: string; data: Partial<ChecklistResponse> }> = []
    const allResponses = ref(new Map<string, ChecklistResponse>([
      ['G9-adjustment-rows', {
        item_id: 'G9-adjustment-rows',
        conclusion: null,
        remark: JSON.stringify([
          {
            rowId: 'a1', seq: 1, entryType: 'AJE', date: '2025-01-01',
            summary: '公允上升', accountCode: '1504', accountName: '其他非流动金融资产',
            debitAmount: 200, creditAmount: 0, preparedBy: '', remark: '',
          },
          {
            rowId: 'a2', seq: 2, entryType: 'AJE', date: '2025-01-01',
            summary: '公允上升（公允变动）', accountCode: '6101', accountName: '公允价值变动损益',
            debitAmount: 0, creditAmount: 200, preparedBy: '', remark: '',
          },
        ]),
      } as ChecklistResponse],
    ]))

    const adj = useG9Adjustment({
      allResponses,
      debouncedSave: (id, d) => {
        saves.push({ id, data: d })
        allResponses.value.set(id, {
          item_id: id,
          conclusion: d.conclusion ?? null,
          remark: d.remark ?? null,
        } as ChecklistResponse)
      },
      isReadonly: ref(false),
    })

    expect(adj.rows.value).toHaveLength(2)
    expect(adj.balanceOk.value).toBe(true)
    expect(adj.summary.value.net1504).toBe(200)
    expect(adj.summary.value.fvPlNet).toBe(-200)
    expect(adj.writebackPreview.value.closingAje).toBe(200)
  })

  it('updateRow 选科目自动带名称', () => {
    const allResponses = ref(new Map<string, ChecklistResponse>([
      ['G9-adjustment-rows', {
        item_id: 'G9-adjustment-rows',
        conclusion: null,
        remark: JSON.stringify([{
          rowId: 'r1', seq: 1, entryType: 'AJE', date: '',
          summary: 't', accountCode: '1504', accountName: '其他非流动金融资产',
          debitAmount: 0, creditAmount: 0, preparedBy: '', remark: '',
        }]),
      } as ChecklistResponse],
    ]))
    const adj = useG9Adjustment({
      allResponses,
      debouncedSave: (id, d) => {
        allResponses.value.set(id, {
          item_id: id,
          conclusion: null,
          remark: d.remark ?? null,
        } as ChecklistResponse)
      },
      isReadonly: ref(false),
    })
    adj.updateRow('r1', { accountCode: '6101' })
    expect(adj.rows.value[0].accountName).toBe('公允价值变动损益')
  })
})
