import { describe, it, expect } from 'vitest'
import {
  calcBalanceIntegrity,
  compareToTrialBalance,
  detectGaps,
  screenAnomalies,
  benfordDistribution,
  benfordChiSquareTest,
  type JournalEntry,
  type AnomalyRules,
  type TrialBalanceRow,
} from '../useC24AnalyticsEngine'

// ─── 辅助工厂 ───────────────────────────────────────────────

function makeEntry(overrides: Partial<JournalEntry> = {}): JournalEntry {
  return {
    voucherDate: '2025-01-15',
    voucherMonth: 1,
    voucherType: '转',
    voucherNo: '转-001',
    summary: '销售收入',
    accountCode: '6001',
    accountName: '主营业务收入',
    debit: 0,
    credit: 0,
    voucherSheets: '1',
    preparer: '张三',
    reviewer: '李四',
    poster: '王五',
    ...overrides,
  }
}

function defaultRules(overrides: Partial<AnomalyRules> = {}): AnomalyRules {
  return {
    holidays: ['2025-01-01', '2025-01-28', '2025-01-29', '2025-01-30', '2025-01-31'],
    nightStartHour: 22,
    nightEndHour: 6,
    largeAmountThreshold: 1000000,
    approvalLimit: 500000,
    roundAmountDigits: 4,
    vagueKeywords: ['调整', '暂估', '其他'],
    checkEmptySummary: true,
    duplicateCheck: true,
    ...overrides,
  }
}

// ─── 1. calcBalanceIntegrity ────────────────────────────────

describe('calcBalanceIntegrity', () => {
  it('空数组返回0且平衡', () => {
    const result = calcBalanceIntegrity([])
    expect(result.debitTotal).toBe(0)
    expect(result.creditTotal).toBe(0)
    expect(result.balanced).toBe(true)
  })

  it('借贷相等时balanced=true', () => {
    const entries = [
      makeEntry({ debit: 1000, credit: 0 }),
      makeEntry({ debit: 0, credit: 1000 }),
    ]
    const result = calcBalanceIntegrity(entries)
    expect(result.debitTotal).toBe(1000)
    expect(result.creditTotal).toBe(1000)
    expect(result.balanced).toBe(true)
  })

  it('借贷不等时balanced=false', () => {
    const entries = [
      makeEntry({ debit: 1000, credit: 0 }),
      makeEntry({ debit: 0, credit: 999 }),
    ]
    const result = calcBalanceIntegrity(entries)
    expect(result.debitTotal).toBe(1000)
    expect(result.creditTotal).toBe(999)
    expect(result.balanced).toBe(false)
  })

  it('浮点精度：0.1+0.2应正确', () => {
    const entries = [
      makeEntry({ debit: 0.1, credit: 0 }),
      makeEntry({ debit: 0.2, credit: 0 }),
      makeEntry({ debit: 0, credit: 0.3 }),
    ]
    const result = calcBalanceIntegrity(entries)
    expect(result.balanced).toBe(true)
  })
})

// ─── 2. compareToTrialBalance ───────────────────────────────

describe('compareToTrialBalance', () => {
  it('空输入返回空', () => {
    expect(compareToTrialBalance([], [])).toEqual([])
  })

  it('分录汇总与试算表一致时diff=0', () => {
    const entries = [
      makeEntry({ accountCode: '1001', debit: 500, credit: 0 }),
      makeEntry({ accountCode: '1001', debit: 300, credit: 0 }),
    ]
    const tb: TrialBalanceRow[] = [
      { accountCode: '1001', debitAmount: 800, creditAmount: 0 },
    ]
    const result = compareToTrialBalance(entries, tb)
    expect(result).toHaveLength(1)
    expect(result[0].diff).toBe(0)
    expect(result[0].jeDebitSum).toBe(800)
  })

  it('有差异时diff非零', () => {
    const entries = [
      makeEntry({ accountCode: '2001', debit: 0, credit: 1000 }),
    ]
    const tb: TrialBalanceRow[] = [
      { accountCode: '2001', debitAmount: 0, creditAmount: 900 },
    ]
    const result = compareToTrialBalance(entries, tb)
    // jeNet = 0-1000 = -1000, tbNet = 0-900 = -900, diff = -1000-(-900) = -100
    expect(result[0].diff).toBe(-100)
  })

  it('覆盖试算表中有而分录无的科目', () => {
    const entries: JournalEntry[] = []
    const tb: TrialBalanceRow[] = [
      { accountCode: '3001', debitAmount: 500, creditAmount: 0 },
    ]
    const result = compareToTrialBalance(entries, tb)
    expect(result).toHaveLength(1)
    expect(result[0].account).toBe('3001')
    expect(result[0].jeNet).toBe(0)
    expect(result[0].tbNet).toBe(500)
    expect(result[0].diff).toBe(-500)
  })
})

// ─── 3. detectGaps ──────────────────────────────────────────

describe('detectGaps', () => {
  it('空数组返回空', () => {
    expect(detectGaps([])).toEqual([])
  })

  it('连续无缺口返回空', () => {
    const nos = ['付-001', '付-002', '付-003', '付-004']
    expect(detectGaps(nos)).toEqual([])
  })

  it('检测单个缺口', () => {
    const nos = ['付-001', '付-002', '付-005']
    const gaps = detectGaps(nos)
    expect(gaps).toHaveLength(1)
    expect(gaps[0].start).toBe('付-003')
    expect(gaps[0].end).toBe('付-004')
    expect(gaps[0].count).toBe(2)
  })

  it('检测多个缺口', () => {
    const nos = ['转-001', '转-003', '转-007']
    const gaps = detectGaps(nos)
    expect(gaps).toHaveLength(2)
    expect(gaps[0].count).toBe(1) // 缺002
    expect(gaps[1].count).toBe(3) // 缺004,005,006
  })

  it('不同类型分别检测', () => {
    const nos = ['付-001', '付-003', '收-001', '收-002']
    const gaps = detectGaps(nos)
    // 只有"付"类型有缺口
    expect(gaps).toHaveLength(1)
    expect(gaps[0].type).toBe('付')
  })

  it('单条凭证号不检测', () => {
    expect(detectGaps(['付-001'])).toEqual([])
  })
})

// ─── 4. screenAnomalies ─────────────────────────────────────

describe('screenAnomalies', () => {
  it('空数组返回空', () => {
    expect(screenAnomalies([], defaultRules())).toEqual([])
  })

  it('规则1: 假期录入', () => {
    const entries = [makeEntry({ voucherDate: '2025-01-01', debit: 100 })]
    const result = screenAnomalies(entries, defaultRules())
    expect(result[0].reasons).toContain('假期录入')
  })

  it('规则4: 大额分录', () => {
    const entries = [makeEntry({ debit: 2000000 })]
    const result = screenAnomalies(entries, defaultRules())
    expect(result[0].reasons).toContain('大额分录')
  })

  it('规则5: 刚好低于审批限额', () => {
    // approvalLimit=500000, 5%容差=25000, 所以 475000~499999 命中
    const entries = [makeEntry({ debit: 490000 })]
    const result = screenAnomalies(entries, defaultRules())
    expect(result[0].reasons).toContain('刚好低于审批限额')
  })

  it('规则6: 约整数（末尾4个0）', () => {
    const entries = [makeEntry({ debit: 1000000 })]
    const result = screenAnomalies(entries, defaultRules())
    expect(result[0].reasons).toContain('约整数')
  })

  it('规则9: 借贷方不常见组合', () => {
    const entries = [makeEntry({ debit: 100, credit: 50 })]
    const result = screenAnomalies(entries, defaultRules())
    expect(result[0].reasons).toContain('借贷方不常见组合')
  })

  it('规则12: 含模糊词', () => {
    const entries = [makeEntry({ summary: '暂估入库', debit: 100 })]
    const result = screenAnomalies(entries, defaultRules())
    expect(result[0].reasons).toContain('含模糊词')
  })

  it('规则13: 没有摘要', () => {
    const entries = [makeEntry({ summary: '', debit: 100 })]
    const result = screenAnomalies(entries, defaultRules())
    expect(result[0].reasons).toContain('没有摘要')
  })

  it('规则8: 重复检测', () => {
    const entries = [
      makeEntry({ debit: 500, summary: '办公费' }),
      makeEntry({ debit: 500, summary: '办公费' }),
    ]
    const result = screenAnomalies(entries, defaultRules())
    // 两条都应标记重复
    expect(result.length).toBeGreaterThanOrEqual(1)
    const hasDup = result.some(r => r.reasons.includes('同金额或同摘要重复'))
    expect(hasDup).toBe(true)
  })

  it('规则11: 特殊事件', () => {
    const entries = [makeEntry({ summary: '关联交易款', debit: 100 })]
    const result = screenAnomalies(entries, defaultRules())
    expect(result[0].reasons).toContain('与特殊事件有关')
  })

  it('正常分录无命中时不出现在结果中', () => {
    const entries = [makeEntry({ debit: 100, summary: '日常报销' })]
    const rules = defaultRules({ holidays: [], vagueKeywords: [], checkEmptySummary: false, duplicateCheck: false })
    const result = screenAnomalies(entries, rules)
    expect(result).toEqual([])
  })
})

// ─── 5. benfordDistribution ─────────────────────────────────

describe('benfordDistribution', () => {
  it('空数组返回9行零分布', () => {
    const result = benfordDistribution([])
    expect(result).toHaveLength(9)
    expect(result[0].digit).toBe(1)
    expect(result[0].count).toBe(0)
    expect(result[0].actual).toBe(0)
  })

  it('expected(d)=log10(1+1/d)', () => {
    const result = benfordDistribution([100])
    for (let i = 0; i < 9; i++) {
      const d = i + 1
      expect(result[i].expected).toBeCloseTo(Math.log10(1 + 1 / d), 10)
    }
  })

  it('单值100首位数为1', () => {
    const result = benfordDistribution([100])
    expect(result[0].count).toBe(1) // digit=1
    expect(result[0].actual).toBe(1)
  })

  it('Σactual=1（非空时）', () => {
    const amounts = [123, 456, 789, 234, 567, 890, 111, 222, 333]
    const result = benfordDistribution(amounts)
    const totalActual = result.reduce((s, r) => s + r.actual, 0)
    expect(totalActual).toBeCloseTo(1, 10)
  })

  it('排除零值', () => {
    const amounts = [0, 0, 100, 200]
    const result = benfordDistribution(amounts)
    // total应为2（排除0）
    const totalCount = result.reduce((s, r) => s + r.count, 0)
    expect(totalCount).toBe(2)
  })

  it('负数取绝对值', () => {
    const result = benfordDistribution([-500])
    expect(result[4].count).toBe(1) // digit=5
  })
})

// ─── 6. benfordChiSquareTest ────────────────────────────────

describe('benfordChiSquareTest', () => {
  it('完美本福特分布卡方值接近0', () => {
    // 生成接近本福特分布的大样本
    const amounts: number[] = []
    for (let d = 1; d <= 9; d++) {
      const expectedPct = Math.log10(1 + 1 / d)
      const count = Math.round(expectedPct * 1000)
      for (let i = 0; i < count; i++) {
        amounts.push(d * 100 + Math.random() * 99)
      }
    }
    const dist = benfordDistribution(amounts)
    const result = benfordChiSquareTest(dist, 0.05)
    expect(result.significant).toBe(false)
    expect(result.criticalValue).toBe(15.507)
  })

  it('均匀分布应显著偏离', () => {
    // 每个首位数等量
    const amounts: number[] = []
    for (let d = 1; d <= 9; d++) {
      for (let i = 0; i < 100; i++) {
        amounts.push(d * 10)
      }
    }
    const dist = benfordDistribution(amounts)
    const result = benfordChiSquareTest(dist, 0.05)
    expect(result.significant).toBe(true)
  })

  it('默认alpha=0.05', () => {
    const dist = benfordDistribution([100])
    const result = benfordChiSquareTest(dist)
    expect(result.criticalValue).toBe(15.507)
  })
})
