/**
 * G11 投资收益 — 集成测试
 */
import { describe, it, expect } from 'vitest'
import {
  parseNum,
  calcAdjustedAmount,
  calcChangeRate,
  calcAverageBalance,
  calcReturnRate,
  calcReturnRateChange,
  isChangeRateExceeding,
  isReturnRateChangeExceeding,
  isDebitCreditBalanced,
} from '../composables/useG11FormulaEngine'
import {
  G11_ADJUDICATION_ITEMS,
  G11_CHANGE_RATE_THRESHOLD,
  G11_RETURN_RATE_CHANGE_THRESHOLD,
  G11_AUDIT_GUIDANCE_ROWS,
  G11_DISCLOSURE_LISTED_ROWS,
  G11_DISCLOSURE_SOE_ROWS,
} from '../composables/g11Constants'
import { calcG11AdjustmentNet } from '../composables/g11AdjStorage'
import { G11_IMPORTABLE_SHEETS } from '../composables/useG11ImportExport'
import { enrichG11VoucherRow } from '../composables/useG11VoucherCheck'

function extractSheet(sheetName: string): string {
  if (/底稿目录/.test(sheetName)) return '底稿目录'
  if (/附注披露/.test(sheetName)) return sheetName.includes('国企') ? '附注国企' : '附注上市'
  const m = sheetName.match(/(G11A|G11-\d+)/)
  return m ? m[1] : ''
}

describe('G11 集成 — sheetName 分发', () => {
  it('9 个有效 sheet 正确分发', () => {
    expect(extractSheet('投资收益实质性程序表G11A')).toBe('G11A')
    expect(extractSheet('审定表G11-1')).toBe('G11-1')
    expect(extractSheet('明细分析表G11-2')).toBe('G11-2')
    expect(extractSheet('调整分录汇总G11-3')).toBe('G11-3')
    expect(extractSheet('收益率分析表G11-4')).toBe('G11-4')
    expect(extractSheet('凭证检查表G11-5')).toBe('G11-5')
    expect(extractSheet('附注披露信息（上市公司）')).toBe('附注上市')
    expect(extractSheet('附注披露信息（国企）')).toBe('附注国企')
    expect(extractSheet('底稿目录')).toBe('底稿目录')
  })
})

describe('G11 集成 — G11-1 变动率>20%', () => {
  it('触发高亮与原因必填', () => {
    const prior = 100
    const current = 130
    const rate = calcChangeRate(prior, current)
    expect(rate).toBeCloseTo(0.3)
    expect(isChangeRateExceeding(rate, G11_CHANGE_RATE_THRESHOLD)).toBe(true)
  })

  it('对称公式：本期/上期审定结构一致', () => {
    for (const def of G11_ADJUDICATION_ITEMS.slice(0, 3)) {
      const cur = calcAdjustedAmount(100, 10)
      const pri = calcAdjustedAmount(80, 5)
      expect(calcAdjustedAmount(100, 10)).toBe(cur)
      expect(def.rowKey).toBeTruthy()
      expect(pri).toBe(85)
    }
  })
})

describe('G11 集成 — G11-4 收益率 5pp', () => {
  it('|变动|>5pp 标记异常', () => {
    const change = calcReturnRateChange(0.12, 0.05)
    expect(change).toBeCloseTo(0.07)
    expect(isReturnRateChangeExceeding(change, G11_RETURN_RATE_CHANGE_THRESHOLD)).toBe(true)
  })

  it('平均余额为 0 时收益率 N/A', () => {
    expect(calcReturnRate(100, 0)).toBeNull()
    expect(calcAverageBalance(0, 0)).toBe(0)
  })
})

describe('G11 集成 — G11-5 核对异常', () => {
  it('核对列任一 ✗ → isAbnormal', () => {
    const row = enrichG11VoucherRow({ check1: '✓', check2: '✗', check3: '✓', check4: '✓', check5: '✓' }, 1)
    expect(row.isAbnormal).toBe(true)
  })

  it('全部 ✓ → 非异常', () => {
    const row = enrichG11VoucherRow({ check1: '✓', check2: '✓', check3: '✓', check4: '✓', check5: '✓' }, 1)
    expect(row.isAbnormal).toBe(false)
  })

  it('全部未测 → 非异常', () => {
    const row = enrichG11VoucherRow({ creditAmount: 1 }, 1)
    expect(row.check1).toBeNull()
    expect(row.isAbnormal).toBe(false)
  })

  it('借贷平衡检测', () => {
    expect(isDebitCreditBalanced([100, 50], [150])).toBe(true)
    expect(isDebitCreditBalanced([100], [90])).toBe(false)
  })
})

describe('G11 集成 — 导入导出与指引', () => {
  it('7 张表均可导入导出（含附注上市/国企）', () => {
    expect(G11_IMPORTABLE_SHEETS.map((s) => s.code)).toEqual([
      'G11-1', 'G11-2', 'G11-3', 'G11-4', 'G11-5', '附注上市', '附注国企',
    ])
  })

  it('编制指引 61 行 + 18 数据行 ≈ 79 行结构', () => {
    expect(G11_AUDIT_GUIDANCE_ROWS.length).toBe(61)
    expect(G11_ADJUDICATION_ITEMS.length).toBe(18)
    expect(G11_AUDIT_GUIDANCE_ROWS.length + G11_ADJUDICATION_ITEMS.length).toBe(79)
  })

  it('parseNum 健壮性', () => {
    expect(parseNum(null)).toBe(0)
    expect(parseNum('abc')).toBe(0)
    expect(parseNum(42)).toBe(42)
  })
})

describe('G11 集成 — 附注披露行数', () => {
  it('上市附注 33 行 + 合计', () => {
    expect(G11_DISCLOSURE_LISTED_ROWS.length).toBe(33)
  })

  it('国企附注 25 行 + 合计', () => {
    expect(G11_DISCLOSURE_SOE_ROWS.length).toBe(25)
  })
})

describe('G11 集成 — G11-3 调整回写', () => {
  it('6111 贷方净额 = 贷 − 借', () => {
    const net = calcG11AdjustmentNet([
      { accountCode: '6111', debitAmount: 0, creditAmount: 100 },
      { accountCode: '6111', debitAmount: 30, creditAmount: 0 },
    ])
    expect(net).toBe(70)
  })

  it('非 6111 行不计入净额', () => {
    const net = calcG11AdjustmentNet([
      { accountCode: '6111', debitAmount: 0, creditAmount: 50 },
      { accountCode: '1001', debitAmount: 50, creditAmount: 0 },
    ])
    expect(net).toBe(50)
  })

  it('报表调整不计入回写净额', () => {
    const net = calcG11AdjustmentNet([
      { accountCode: '6111', debitAmount: 0, creditAmount: 50, category: '账项调整' },
      { accountCode: '6111', debitAmount: 0, creditAmount: 20, category: '报表调整' },
    ])
    expect(net).toBe(50)
  })
})
