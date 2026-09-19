/**
 * useF5MajorAdjustment — F5-8 重大调整事项核查表 单元测试
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref } from 'vue'
import {
  useF5MajorAdjustment,
  migrateF5MajorAdjRows,
  computeF5MajorAdjRow,
  emptyF5MajorAdjRow,
  defaultF5MajorAdjRows,
  F5_MAJOR_ADJ_DEFAULT_ROWS,
} from '../useF5MajorAdjustment'
import type { ChecklistResponse } from '../useF1FormData'

function mkResponses(seed?: Record<string, string>) {
  const map = ref(new Map<string, ChecklistResponse>())
  if (seed) {
    for (const [k, v] of Object.entries(seed)) {
      map.value.set(k, { item_id: k, conclusion: null, remark: v })
    }
  }
  return map
}

describe('migrate / compute', () => {
  it('净额=借方−贷方', () => {
    const row = computeF5MajorAdjRow({
      ...emptyF5MajorAdjRow(),
      debitAmount: 1000,
      creditAmount: 200,
    })
    expect(row.netAmount).toBe(800)
  })

  it('兼容旧单金额与字段别名', () => {
    const rows = migrateF5MajorAdjRows(JSON.stringify([
      {
        rowId: '1',
        adjustmentDate: '2024-01-01',
        adjustmentItem: '返利冲减成本',
        adjustmentAmount: 5000,
        adjustmentReason: '协议返利',
        approvalBasis: '董事会决议',
        voucherNo: '记-001',
        auditEvaluation: '充分',
      },
      {
        date: '2024-02-01',
        itemContent: '贷方调整',
        adjustAmount: -300,
        reasonAdequate: '待补充',
      },
    ]))
    expect(rows[0].date).toBe('2024-01-01')
    expect(rows[0].itemContent).toBe('返利冲减成本')
    expect(rows[0].debitAmount).toBe(5000)
    expect(rows[0].creditAmount).toBe(0)
    expect(rows[0].adjustmentReason).toContain('协议返利')
    expect(rows[0].reasonAdequate).toBe('充分')
    expect(rows[1].creditAmount).toBe(300)
    expect(rows[1].debitAmount).toBe(0)
  })
})

describe('useF5MajorAdjustment', () => {
  beforeEach(() => { vi.useFakeTimers() })
  afterEach(() => { vi.useRealTimers() })

  it(`默认 ${F5_MAJOR_ADJ_DEFAULT_ROWS} 行；增删；理由不充分计数`, () => {
    const allResponses = mkResponses()
    const adj = useF5MajorAdjustment({
      allResponses,
      isReadonly: ref(false),
      materiality: ref(1000),
    })
    expect(adj.rows.value).toHaveLength(defaultF5MajorAdjRows().length)

    adj.addRow()
    const id = adj.rows.value[adj.rows.value.length - 1].id
    adj.updateCell(id, 'itemContent', '重大结转调整')
    adj.updateCell(id, 'debitAmount', 5000)
    adj.updateCell(id, 'reasonAdequate', '不充分')
    expect(adj.filledCount.value).toBe(1)
    expect(adj.inadequateCount.value).toBe(1)
    expect(adj.exceedCount.value).toBe(1)
    expect(adj.isRowHighlighted(adj.rows.value.find((r) => r.id === id)!)).toBe(true)

    adj.removeRow(id)
    expect(adj.rows.value.find((r) => r.id === id)).toBeFalsy()
  })

  it('抽凭样本 merge 借方/贷方', () => {
    const allResponses = mkResponses()
    const adj = useF5MajorAdjustment({ allResponses, isReadonly: ref(false) })
    const n = adj.mergeSamplingRows([
      { voucher_date: '2024-03-01', voucher_no: '记-9', summary: '成本调整', debit_amount: 100, credit_amount: 0 },
    ])
    expect(n).toBe(1)
    expect(adj.rows.value[0].voucherNo).toBe('记-9')
    expect(adj.rows.value[0].debitAmount).toBe(100)
  })
})
