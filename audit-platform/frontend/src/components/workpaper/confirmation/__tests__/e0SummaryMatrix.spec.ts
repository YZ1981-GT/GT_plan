/**
 * e0SummaryMatrix.spec.ts — 品种矩阵纯函数测试（Property 6/7）
 */
import { describe, it, expect } from 'vitest'
import { buildE0SummaryMatrix, E0_MATRIX_CATEGORIES, E0_MATRIX_METRICS } from '../e0SummaryMatrix'
import type { ConfirmationRow } from '../confirmationTypes'

describe('buildE0SummaryMatrix', () => {
  it('返回 6 品种 × 6 指标的二维数组', () => {
    const result = buildE0SummaryMatrix({ rows: [] })
    expect(result.length).toBe(6)
    for (const row of result) {
      expect(row.length).toBe(6)
    }
  })

  it('品种与指标名逐字一致', () => {
    const result = buildE0SummaryMatrix({ rows: [] })
    for (let i = 0; i < 6; i++) {
      expect(result[i][0].category).toBe(E0_MATRIX_CATEGORIES[i])
      for (let j = 0; j < 6; j++) {
        expect(result[i][j].metric).toBe(E0_MATRIX_METRICS[j])
      }
    }
  })

  describe('Property 6: 求和与比例', () => {
    const rows: ConfirmationRow[] = [
      { account_type: '银行存款', amount: 100000, confirmed_amount: 80000 },
      { account_type: '银行存款', amount: 50000, confirmed_amount: 50000 },
      { account_type: '理财产品', amount: 200000, confirmed_amount: 0 },
    ]

    it('发函金额 = 按品种求和', () => {
      const result = buildE0SummaryMatrix({ rows, bookAmounts: { '银行存款': 500000 } })
      // 银行存款发函金额 = 100000 + 50000 = 150000
      expect(result[0][1].value).toBe(150000)
      // 理财产品发函金额 = 200000
      expect(result[5][1].value).toBe(200000)
    })

    it('回函确认金额 = 按品种求和', () => {
      const result = buildE0SummaryMatrix({ rows, bookAmounts: { '银行存款': 500000 } })
      // 银行存款 = 80000 + 50000
      expect(result[0][3].value).toBe(130000)
    })

    it('分母 0 → 比例为 0（ISERROR 兜底）', () => {
      // 短期借款无行 → 发函金额 0 → 回函占发函比例应为 0 而非 NaN
      const result = buildE0SummaryMatrix({ rows, bookAmounts: { '短期借款': 0 } })
      // 发函金额占账面比例：发函 0 / 账面 0 → 0
      expect(result[2][2].value).toBe(0)
      // 回函占发函比例：确认 0 / 发函 0 → 0
      expect(result[2][4].value).toBe(0)
    })

    it('bookAmounts 缺该品种 → 比例返回 null', () => {
      const result = buildE0SummaryMatrix({ rows, bookAmounts: { '银行存款': 500000 } })
      // 其他货币资金：无 bookAmounts → 发函占账面比例 = null
      expect(result[1][2].value).toBeNull()
      // 理财产品同理
      expect(result[5][2].value).toBeNull()
    })

    it('输出 SHALL NOT 含 NaN/Infinity', () => {
      const result = buildE0SummaryMatrix({ rows })
      for (const catCells of result) {
        for (const cell of catCells) {
          if (cell.value !== null) {
            expect(Number.isFinite(cell.value)).toBe(true)
          }
        }
      }
    })
  })

  describe('Property 7: 只读边界', () => {
    it('仅「本期（期末）账面金额」行 editable=true', () => {
      const result = buildE0SummaryMatrix({ rows: [] })
      for (const catCells of result) {
        for (const cell of catCells) {
          if (cell.metric === '本期（期末）账面金额') {
            expect(cell.editable).toBe(true)
          } else {
            expect(cell.editable).toBe(false)
          }
        }
      }
    })
  })

  describe('PBT: 任意行集下无 NaN/Infinity', () => {
    function randomRow(): ConfirmationRow {
      const types = ['银行存款', '其他货币资金', '短期借款', '长期借款', '应付票据', '理财产品']
      return {
        account_type: types[Math.floor(Math.random() * types.length)],
        amount: Math.random() * 1e8 - 5e7, // 含负数
        confirmed_amount: Math.random() * 1e8 - 5e7,
      }
    }

    it.each(Array.from({ length: 20 }, (_, i) => i))('seed %d: 无 NaN/Infinity', () => {
      const rows = Array.from({ length: Math.floor(Math.random() * 30) }, randomRow)
      const bookAmounts: Partial<Record<string, number>> = {}
      if (Math.random() > 0.5) bookAmounts['银行存款'] = Math.random() * 1e8
      if (Math.random() > 0.5) bookAmounts['短期借款'] = 0

      const result = buildE0SummaryMatrix({ rows, bookAmounts: bookAmounts as any })
      for (const catCells of result) {
        for (const cell of catCells) {
          if (cell.value !== null) {
            expect(Number.isFinite(cell.value), `NaN/Inf found: ${cell.category}/${cell.metric}`).toBe(true)
          }
        }
      }
    })
  })
})
