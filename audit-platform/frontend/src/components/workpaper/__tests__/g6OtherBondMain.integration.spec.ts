/**
 * G6 其他债权投资(main组) — 集成测试
 */
import { describe, it, expect } from 'vitest'
import {
  parseNum,
  calcDebitBalance,
  calcAdjustedAmount,
  calcSubtotal,
  calcEndingSubtotal,
  calcUnadjustedProvision,
  calcImpairmentAdjustment,
  calcAdjustedBookValue,
  calcChangeRate,
  isDebitCreditBalanced,
  calcReportAmount,
} from '@/composables/useG6MainFormulaEngine'
import { G6_MAIN_IMPORT_EXPORT_SHEETS } from '../composables/useG6MainImportExport'

function extractSheet(sheetName: string): string {
  if (/底稿目录/.test(sheetName)) return '底稿目录'
  if (/附注披露/.test(sheetName)) return sheetName.includes('国企') ? '附注国企' : '附注上市'
  const m = sheetName.match(/(G6A|G6-\d+)/)
  return m ? m[1] : ''
}

describe('G6 集成 — sheetName 分发', () => {
  it('8 个有效 sheet 正确分发', () => {
    expect(extractSheet('其他债权投资实质性程序表G6A')).toBe('G6A')
    expect(extractSheet('审定表G6-1')).toBe('G6-1')
    expect(extractSheet('明细表G6-2')).toBe('G6-2')
    expect(extractSheet('坏账准备明细表G6-3')).toBe('G6-3')
    expect(extractSheet('调整分录汇总G6-4')).toBe('G6-4')
    expect(extractSheet('附注披露信息（上市公司）')).toBe('附注上市')
    expect(extractSheet('附注披露信息（国企）')).toBe('附注国企')
    expect(extractSheet('底稿目录')).toBe('底稿目录')
  })
})

describe('G6 集成 — 借方公式链', () => {
  it('calcDebitBalance 资产方向', () => {
    expect(calcDebitBalance(100, 50, 20)).toBe(130)
  })

  it('审定数 = 未审 + 调整', () => {
    expect(calcAdjustedAmount(200, -15)).toBe(185)
  })

  it('报表列示数 = 小计 + FV变动 - 减值', () => {
    expect(calcReportAmount(1000, 50, 30)).toBe(1020)
  })

  it('期初小计 = 成本 + 利息调整 + 应计利息', () => {
    expect(calcSubtotal(100, 10, 5)).toBe(115)
  })

  it('期末小计 = 期初小计 + 增加 - 减少 + 利息收入', () => {
    expect(calcEndingSubtotal(115, 20, 5, 8)).toBe(138)
  })
})

describe('G6 集成 — ECL 公式链', () => {
  it('③ = ① × ②', () => {
    expect(calcUnadjustedProvision(1000, 0.05)).toBe(50)
  })

  it('⑧ = ③ + ⑥ 且 ⑨ = ⑦ - ⑧', () => {
    const provision = calcUnadjustedProvision(1000, 0.05)
    const adj = calcImpairmentAdjustment(100, 0.06, 1000, 0.05)
    const adjustedBalance = 1100
    const adjustedProvision = provision + adj
    const bookValue = calcAdjustedBookValue(adjustedBalance, adjustedProvision)
    expect(adjustedProvision).toBeCloseTo(adjustedBalance * 0.06, 1)
    expect(bookValue).toBeCloseTo(adjustedBalance - adjustedProvision, 1)
  })
})

describe('G6 集成 — 变动率与借贷平衡', () => {
  it('prior≈0 时变动率为 null', () => {
    expect(calcChangeRate(0, 100)).toBeNull()
  })

  it('借贷平衡容差', () => {
    expect(isDebitCreditBalanced([100, 50], [150])).toBe(true)
    expect(isDebitCreditBalanced([100], [90])).toBe(false)
  })

  it('parseNum 无效输入归零', () => {
    expect(parseNum(null)).toBe(0)
    expect(parseNum('abc')).toBe(0)
    expect(parseNum(42)).toBe(42)
  })
})

describe('G6 集成 — 导入导出配置', () => {
  it('3 张动态行表支持导入导出', () => {
    const codes = G6_MAIN_IMPORT_EXPORT_SHEETS.map((s) => s.code)
    expect(codes).toEqual(['G6-2', 'G6-3', 'G6-4'])
  })

  it('G6-2/G6-3 为多 sheet 宽表导出', () => {
    const multi = G6_MAIN_IMPORT_EXPORT_SHEETS.filter((s) => s.multiSheet).map((s) => s.code)
    expect(multi).toEqual(['G6-2', 'G6-3'])
  })
})
