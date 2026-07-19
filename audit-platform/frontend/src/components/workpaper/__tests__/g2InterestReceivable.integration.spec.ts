/**
 * G2 应收利息 — 集成测试
 *
 * Spec: .kiro/specs/g2-interest-receivable/ Task 10.1
 * 验证公式链、sheetName分发、ECL三阶段、抽凭分配、EventBus、导入导出覆盖
 */
import { describe, it, expect, vi } from 'vitest'
import { ref } from 'vue'
import {
  calcInterest365,
  calcAccruedDays,
  calcDebitBalance,
  calcAdjustedAmount,
  calcECL,
  calcOverdueDays,
  determineStage,
  calcNetReceivable,
  isDebitCreditBalanced,
} from '../composables/useG2IntRecFormulaEngine'
import { G2_IMPORTABLE_SHEETS } from '../composables/useG2ImportExport'

// Mock onBeforeUnmount
vi.mock('vue', async () => {
  const actual = await vi.importActual('vue')
  return { ...actual as any, onBeforeUnmount: vi.fn() }
})

describe('G2 集成测试 — sheetName分发', () => {
  function extractSheet(sheetName: string): string {
    if (/G2-note-listed|附注披露.*上市|附注.*上市/.test(sheetName)) return '附注上市'
    if (/G2-note-soe|附注披露.*国企|附注.*国企/.test(sheetName)) return '附注国企'
    if (/附注/.test(sheetName)) return sheetName.includes('国企') ? '附注国企' : '附注上市'
    const m = sheetName.match(/(G2A|G2-\d+)/)
    return m ? m[1] : ''
  }

  it('10个sheet名正确分发', () => {
    expect(extractSheet('G2A 实质性程序表')).toBe('G2A')
    expect(extractSheet('G2-1 审定表')).toBe('G2-1')
    expect(extractSheet('附注披露(上市)')).toBe('附注上市')
    expect(extractSheet('附注披露(国企)')).toBe('附注国企')
    expect(extractSheet('附注披露信息（上市公司）')).toBe('附注上市')
    expect(extractSheet('G2-附注披露信息（国企）')).toBe('附注国企')
    expect(extractSheet('G2-note-listed')).toBe('附注上市')
    expect(extractSheet('G2-2 明细表')).toBe('G2-2')
    expect(extractSheet('G2-3 坏账准备明细')).toBe('G2-3')
    expect(extractSheet('G2-4 调整分录')).toBe('G2-4')
    expect(extractSheet('G2-5 利息测算表')).toBe('G2-5')
    expect(extractSheet('G2-6 长期未收回检查')).toBe('G2-6')
    expect(extractSheet('G2-7 坏账准备测算')).toBe('G2-7')
    expect(extractSheet('G2-8 凭证检查表')).toBe('G2-8')
  })

  it('未匹配返回空字符串（走OO兜底）', () => {
    expect(extractSheet('UnknownSheet')).toBe('')
    expect(extractSheet('')).toBe('')
  })
})

describe('G2 集成测试 — 借方余额公式链', () => {
  it('期初审定+借方-贷方=期末未审→+AJE+RJE=期末审定', () => {
    const openingUnadjusted = 1000
    const openingAJE = 200
    const openingRJE = -50
    const periodDebit = 500
    const periodCredit = 150

    // Step 1: 期初审定
    const openingAdjusted = calcAdjustedAmount(openingUnadjusted, openingAJE, openingRJE)
    expect(openingAdjusted).toBe(1150) // 1000+200-50

    // Step 2: 期末未审（借方科目）
    const closingUnadjusted = calcDebitBalance(openingAdjusted, periodDebit, periodCredit)
    expect(closingUnadjusted).toBe(1500) // 1150+500-150

    // Step 3: 期末审定
    const closingAJE = 100
    const closingRJE = -30
    const closingAdjusted = calcAdjustedAmount(closingUnadjusted, closingAJE, closingRJE)
    expect(closingAdjusted).toBe(1570) // 1500+100-30
  })
})

describe('G2 集成测试 — 利息测算全链路', () => {
  it('面值×利率×天数/365 完整链路', () => {
    const faceValue = 1000000
    const couponRate = 4.5
    const startDate = '2025-01-01'
    const endDate = '2025-07-01' // 181 days

    const days = calcAccruedDays(startDate, endDate)
    expect(days).toBe(181)

    const interest = calcInterest365(faceValue, couponRate, days)
    const expected = (1000000 * 4.5 / 100 * 181) / 365
    expect(interest).toBeCloseTo(expected, 2)

    // 净应收 = 应计 - 已收
    const received = 10000
    const net = calcNetReceivable(interest, received)
    expect(net).toBeCloseTo(expected - 10000, 2)
  })
})

describe('G2 集成测试 — ECL三阶段测算', () => {
  it('Stage1: 12个月PD', () => {
    const stage = determineStage(false, false)
    expect(stage).toBe(1)
    const pd12Month = 0.02
    const lgd = 0.45
    const ead = 500000
    const ecl = calcECL(ead, pd12Month, lgd)
    expect(ecl).toBeCloseTo(500000 * 0.02 * 0.45, 5)
  })

  it('Stage2: 整个存续期PD（信用风险显著增加）', () => {
    const stage = determineStage(false, true)
    expect(stage).toBe(2)
    const pdLifetime = 0.15
    const lgd = 0.45
    const ead = 500000
    const ecl = calcECL(ead, pdLifetime, lgd)
    expect(ecl).toBeCloseTo(500000 * 0.15 * 0.45, 5)
  })

  it('Stage3: 已减值（优先级最高）', () => {
    const stage = determineStage(true, true) // both true → Stage3 wins
    expect(stage).toBe(3)
    const pdLifetime = 0.80
    const lgd = 0.60
    const ead = 500000
    const ecl = calcECL(ead, pdLifetime, lgd)
    expect(ecl).toBeCloseTo(500000 * 0.80 * 0.60, 5)
  })
})

describe('G2 集成测试 — G2-8抽凭引擎样本分配', () => {
  it('insertDebitSamples/insertCreditSamples 独立增加行', async () => {
    const { useG2VoucherCheck } = await import('../composables/useG2VoucherCheck')
    const allResponses = ref(new Map<string, any>())
    const vc = useG2VoucherCheck({
      wpId: ref('wp-1'),
      projectId: ref('proj-1'),
      allResponses,
      isReadonly: ref(false),
    })

    expect(vc.debitRows.value).toHaveLength(0)
    expect(vc.creditRows.value).toHaveLength(0)

    // 借方样本
    vc.insertDebitSamples([
      { summary: '利息确认', amount: 5000, source: '抽凭' },
      { summary: '利息计提', amount: 3000, source: '抽凭' },
    ])
    expect(vc.debitRows.value).toHaveLength(2)
    expect(vc.debitRows.value[0].source).toBe('抽凭')

    // 贷方样本
    vc.insertCreditSamples([
      { summary: '利息收回', amount: 4000, source: '抽凭' },
    ])
    expect(vc.creditRows.value).toHaveLength(1)
    expect(vc.creditRows.value[0].source).toBe('抽凭')

    // 互不影响
    expect(vc.debitRows.value).toHaveLength(2)
  })
})

describe('G2 集成测试 — 导入导出覆盖8张表', () => {
  it('G2_IMPORTABLE_SHEETS 包含 G2-1~G2-8', () => {
    expect(G2_IMPORTABLE_SHEETS).toHaveLength(8)
    const codes = G2_IMPORTABLE_SHEETS.map((s) => s.code)
    expect(codes).toContain('G2-1')
    expect(codes).toContain('G2-2')
    expect(codes).toContain('G2-3')
    expect(codes).toContain('G2-4')
    expect(codes).toContain('G2-5')
    expect(codes).toContain('G2-6')
    expect(codes).toContain('G2-7')
    expect(codes).toContain('G2-8')
  })
})

describe('G2 集成测试 — 公式引擎逾期天数（G2-8 等仍用）', () => {
  it('逾期天数按约定日计算', () => {
    const now = new Date('2025-07-01')
    expect(calcOverdueDays('2024-12-13', now)).toBeGreaterThan(180)
    expect(calcOverdueDays('2025-03-03', now)).toBeGreaterThan(90)
    expect(calcOverdueDays('2025-06-01', now)).toBeLessThanOrEqual(90)
  })

  it('逾期天数恒≥0', () => {
    expect(calcOverdueDays('2030-01-01')).toBe(0)
    expect(calcOverdueDays('')).toBe(0)
  })
})

describe('G2 集成测试 — G2-6 长期挂账滚动态', () => {
  it('期末=期初+借方−贷方；账龄超1年计入长期', async () => {
    const { useG2OverdueCheck } = await import('../composables/useG2OverdueCheck')
    const { ref } = await import('vue')
    const map = new Map()
    map.set('G2-6-overdue-rows', {
      item_id: 'G2-6-overdue-rows',
      conclusion: null,
      remark: JSON.stringify([
        {
          id: '1', seq: 1, debtorName: '甲',
          openingBalance: 100, periodDebit: 50, periodCredit: 20,
          aging: '1-2年', auditedBalance: 130, postPeriodCollection: 0,
          businessDesc: '', unrecoveredReason: '', isUncollectible: '', actionPlan: '', remark: '',
        },
      ]),
    })
    const overdue = useG2OverdueCheck({
      wpId: ref('w'),
      projectId: ref('p'),
      allResponses: ref(map),
      isReadonly: ref(false),
    })
    expect(overdue.dataRows.value[0].closingBalance).toBe(130)
    expect(overdue.summary.value.longTermCount).toBe(1)
  })
})

describe('G2 集成测试 — 借贷平衡', () => {
  it('相等时平衡', () => {
    expect(isDebitCreditBalanced([1000, 2000], [1500, 1500])).toBe(true)
  })

  it('不等时不平衡', () => {
    expect(isDebitCreditBalanced([1000], [999])).toBe(false)
  })
})
