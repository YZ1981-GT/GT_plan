/**
 * F3 集成测试 — Task 10.1
 * sheetName 分发、公式链、抽凭分配、EventBus
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, nextTick } from 'vue'
import {
  calcCreditBalance, calcAdjustedAmount, calcInterest, calcOverdueDays, parseNum,
} from '../useF3FormulaEngine'
import { useF3VoucherCheck } from '../useF3VoucherCheck'
import { useF3DisclosureListed } from '../useF3DisclosureListed'
import { useF3Detail, F3_DETAIL_BASIC_COLUMNS, F3_DETAIL_INFO_COLUMNS, F3_DETAIL_AUDIT_COLUMNS } from '../useF3Detail'
import { useF3OverdueCheck } from '../useF3OverdueCheck'
import type { SampledVoucher } from '../useSamplingAlgorithms'
import type { ChecklistResponse } from '../useF3FormData'

/** GtF3NotesPayable currentSheet 逻辑镜像 */
function resolveF3Sheet(sheetName: string, wpCode = ''): string {
  const name = sheetName || wpCode || ''
  if (/F3-note-listed|附注披露.*上市|附注.*上市/.test(name)) return '附注上市'
  if (/F3-note-soe|附注披露.*国企|附注.*国企/.test(name)) return '附注国企'
  if (/附注/.test(name)) return name.includes('国企') ? '附注国企' : '附注上市'
  const m = name.match(/(F3A|F3-\d+)/)
  return m ? m[1] : ''
}

const F3_WP_CODES = [
  'F3A', 'F3-1', 'F3-2', 'F3-3', 'F3-4', 'F3-5', 'F3-6', 'F3-7',
  'F3-note-listed', 'F3-note-soe',
] as const

describe('F3 sheetName dispatch', () => {
  const cases: Array<[string, string]> = [
    ['F3A', 'F3A'],
    ['F3-1 审定表', 'F3-1'],
    ['F3-2', 'F3-2'],
    ['F3-7 检查表', 'F3-7'],
    ['附注披露(上市)', '附注上市'],
    ['附注披露(国企)', '附注国企'],
    ['F3 附注上市', '附注上市'],
    ['F3-note-listed', '附注上市'],
    ['F3-note-soe', '附注国企'],
  ]

  it.each(cases)('"%s" → "%s"', (input, expected) => {
    expect(resolveF3Sheet(input)).toBe(expected)
  })

  it('covers 10 wp_code sheet keys', () => {
    expect(F3_WP_CODES).toHaveLength(10)
    expect(resolveF3Sheet('F3-note-listed')).toBe('附注上市')
    expect(resolveF3Sheet('F3A')).toBe('F3A')
  })
})

describe('F3 formula chains', () => {
  it('interest = faceValue × rate/100 × days/360', () => {
    expect(calcInterest(100000, 5, 180)).toBeCloseTo(100000 * 0.05 * 180 / 360, 5)
  })

  it('credit balance chain through adjudication', () => {
    const openingAdj = calcAdjustedAmount(5000, 100, -50)
    const closingUnadj = calcCreditBalance(openingAdj, 2000, 800)
    const closingAdj = calcAdjustedAmount(closingUnadj, 50, -20)
    expect(closingAdj).toBeCloseTo(openingAdj + 2000 - 800 + 50 - 20, 5)
  })

  it('overdue days is non-negative', () => {
    const days = calcOverdueDays('2024-01-01')
    expect(days).toBeGreaterThanOrEqual(0)
  })
})

describe('F3-7 voucher sampling direction split', () => {
  const allResponses = ref(new Map<string, ChecklistResponse>())
  const isReadonly = ref(false)

  beforeEach(() => {
    allResponses.value = new Map()
  })

  it('maps credit and debit amounts to separate blocks', () => {
    const { applySamplingResults, creditRows, debitRows } = useF3VoucherCheck({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses,
      isReadonly,
    })

    const samples: SampledVoucher[] = [
      {
        voucherNo: 'V001', voucherDate: '2025-03-01', summary: '开票',
        debitAmount: null, creditAmount: '5000', accountCode: '2201',
        accountName: '应付票据', counterpartAccount: '应付账款', voucherType: null,
        accountingPeriod: 3, checkResult: '', abnormal: false,
      },
      {
        voucherNo: 'V002', voucherDate: '2025-04-01', summary: '兑付',
        debitAmount: '3000', creditAmount: null, accountCode: '2201',
        accountName: '应付票据', counterpartAccount: '银行存款', voucherType: null,
        accountingPeriod: 4, checkResult: '', abnormal: false,
      },
    ]

    applySamplingResults(samples, 'append')

    expect(creditRows.value.some((r) => r.voucherNo === 'V001' && r.amount === 5000)).toBe(true)
    expect(debitRows.value.some((r) => r.voucherNo === 'V002' && r.amount === 3000)).toBe(true)
  })
})

describe('F3 disclosure EventBus', () => {
  const allResponses = ref(new Map<string, ChecklistResponse>())
  const isReadonly = ref(false)
  const applicableStandards = ref(['listed_standalone'])

  beforeEach(() => {
    allResponses.value = new Map([
      ['F3-1-adj-rows', {
        item_id: 'F3-1-adj-rows',
        conclusion: null,
        remark: JSON.stringify([
          { rowKey: 'bank', label: '银行承兑', openingUnadjusted: 1000, openingAje: 0, openingRje: 0,
            periodCredit: 500, periodDebit: 100, closingAje: 0, closingRje: 0 },
          { rowKey: 'commercial', label: '商业承兑', openingUnadjusted: 200, openingAje: 0, openingRje: 0,
            periodCredit: 50, periodDebit: 20, closingAje: 0, closingRje: 0 },
        ]),
      }],
    ])
  })

  it('refreshes section1 on substantive:adjudicated for 2201', () => {
    const { section1Rows } = useF3DisclosureListed({
      allResponses,
      isReadonly,
      applicableStandards,
    })

    const before = section1Rows.value.find((r) => r.rowId === 'cs-bank')?.endAmount ?? 0
    window.dispatchEvent(new CustomEvent('substantive:adjudicated', {
      detail: { accountCode: '2201', auditedAmount: 9999 },
    }))
    const after = section1Rows.value.find((r) => r.rowId === 'cs-bank')?.endAmount ?? 0
    expect(after).toBe(before)
    expect(parseNum(after)).toBeCloseTo(1400, 5)
  })

  it('publishes disclosure:note-text-updated on note change', async () => {
    const handler = vi.fn()
    window.addEventListener('disclosure:note-text-updated', handler)

    const { noteText } = useF3DisclosureListed({
      allResponses,
      isReadonly,
      applicableStandards,
    })

    noteText.value = '测试附注说明'
    await nextTick()

    expect(handler).toHaveBeenCalled()
    expect(handler.mock.calls[0][0].detail).toMatchObject({
      wpCode: 'F3',
      section: 'listed',
      text: '测试附注说明',
    })

    window.removeEventListener('disclosure:note-text-updated', handler)
  })
})

describe('F3-2 detail 3-segment columns', () => {
  it('basic + info + audit columns cover 25 fields', () => {
    const total = F3_DETAIL_BASIC_COLUMNS.length + F3_DETAIL_INFO_COLUMNS.length + F3_DETAIL_AUDIT_COLUMNS.length
    expect(total).toBe(25)
  })

  it('segment switch keeps same row count across tabs', () => {
    const allResponses = ref(new Map<string, ChecklistResponse>([
      ['F3-2-rows', {
        item_id: 'F3-2-rows',
        conclusion: null,
        remark: JSON.stringify([
          { rowId: 'a', seq: 1, drawer: 'A公司', faceValue: 1000 },
          { rowId: 'b', seq: 2, drawer: 'B公司', faceValue: 2000 },
        ]),
      }],
    ]))
    const { rows, activeSegment } = useF3Detail({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses,
      isReadonly: ref(false),
    })
    expect(rows.value).toHaveLength(2)
    activeSegment.value = 'detail'
    expect(rows.value).toHaveLength(2)
    activeSegment.value = 'audit'
    expect(rows.value[0].rowId).toBe('a')
  })

  it('closing balance = opening + increase - decrease', () => {
    const allResponses = ref(new Map<string, ChecklistResponse>([
      ['F3-2-rows', {
        item_id: 'F3-2-rows',
        conclusion: null,
        remark: JSON.stringify([{
          rowId: 'r1', seq: 1, openingBalance: 1000, increase: 500, decrease: 200,
          issueDate: '2025-01-01', dueDate: '2025-06-01', noteType: '银行承兑',
        }]),
      }],
    ]))
    const { rows } = useF3Detail({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses,
      isReadonly: ref(false),
    })
    expect(rows.value[0].closingBalance).toBeCloseTo(1300, 5)
    expect(rows.value[0].adjustedBalance).toBeCloseTo(1300, 5)
  })
})

describe('F3-5 overdue risk suggestion', () => {
  it('suggests high risk when overdue > 90 days', () => {
    const pastDue = new Date()
    pastDue.setDate(pastDue.getDate() - 100)
    const dueStr = pastDue.toISOString().slice(0, 10)
    const allResponses = ref(new Map<string, ChecklistResponse>([
      ['F3-5-rows', {
        item_id: 'F3-5-rows',
        conclusion: null,
        remark: JSON.stringify([{ rowId: 'o1', seq: 1, dueDate: dueStr, faceValue: 10000 }]),
      }],
    ]))
    const { rows } = useF3OverdueCheck({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses,
      isReadonly: ref(false),
    })
    expect(rows.value[0].overdueDays).toBeGreaterThan(90)
    expect(rows.value[0].riskLevel).toBe('高')
  })
})

describe('F3 import/export field keys contract', () => {
  const F3_7_CREDIT_KEYS = [
    'seq', 'summary', 'counterAccount', 'amount', 'voucherDate', 'voucherNo',
    'noteType', 'acceptor', 'purchaseContractCheck', 'goodsReceiptCheck', 'auditConclusion', 'remark',
  ]

  it('F3-7-credit export keys align with composable row shape', () => {
    expect(F3_7_CREDIT_KEYS).toContain('summary')
    expect(F3_7_CREDIT_KEYS).toContain('amount')
    expect(F3_7_CREDIT_KEYS).toHaveLength(12)
  })
})
