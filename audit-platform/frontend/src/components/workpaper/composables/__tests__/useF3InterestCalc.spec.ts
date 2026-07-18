/** useF3InterestCalc.spec — F3-4 应付票据（带息）利息测算表 */
import { describe, it, expect } from 'vitest'
import {
  emptyInterestRow,
  isBlankInterestRow,
  computeInterestRow,
  safeParseInterestRows,
} from '../useF3InterestCalc'

describe('F3-4 利息测算公式', () => {
  it('期限 = 到期日 − 出票日，应计利息 = 面值 × 利率% × 期限 / 360', () => {
    const row = computeInterestRow({
      ...emptyInterestRow(1),
      issueDate: '2025-01-01',
      dueDate: '2025-07-01',
      faceValue: 1000000,
      interestRate: 3.6,
      bookInterest: 18000,
    })
    expect(row.termDays).toBe(181)
    expect(row.payableInterest).toBeCloseTo(1000000 * 3.6 / 100 * 181 / 360, 2)
    expect(row.variance).toBeCloseTo(row.payableInterest - 18000, 2)
  })

  it('无日期时退化为 面值 × 利率%（对齐源表 ROUND(F*G,2)）', () => {
    const row = computeInterestRow({
      ...emptyInterestRow(1),
      faceValue: 500000,
      interestRate: 2.5,
    })
    expect(row.termDays).toBe(0)
    expect(row.payableInterest).toBe(12500)
  })

  it('空行判定：仅公式列有值仍视为空行', () => {
    expect(isBlankInterestRow(emptyInterestRow(1))).toBe(true)
    expect(isBlankInterestRow({ ...emptyInterestRow(1), ticketNo: 'HP001' })).toBe(false)
    expect(isBlankInterestRow({ ...emptyInterestRow(1), bookInterest: 100 })).toBe(false)
  })
})

describe('F3-4 旧数据迁移与修剪', () => {
  it('旧字段迁移：drawer→说明、noteNo→票据号、计息起止兜底为出票/到期日', () => {
    const legacy = JSON.stringify([{
      rowId: 'old-1', seq: 1, drawer: '甲公司', noteNo: 'HP20250001',
      faceValue: 800000, interestRate: 3, interestStart: '2025-02-01', interestEnd: '2025-08-01',
      bookInterest: 12000,
    }])
    const rows = safeParseInterestRows(legacy)
    expect(rows).toHaveLength(1)
    expect(rows[0].ticketNo).toBe('HP20250001')
    expect(rows[0].note).toBe('出票人：甲公司')
    expect(rows[0].issueDate).toBe('2025-02-01')
    expect(rows[0].dueDate).toBe('2025-08-01')
    expect(rows[0].termDays).toBe(181)
    expect(rows[0].payableInterest).toBeCloseTo(800000 * 3 / 100 * 181 / 360, 2)
  })

  it('修剪空行并重排序号，全部为空时保留一行', () => {
    const mixed = JSON.stringify([
      { rowId: 'a', seq: 1 },
      { rowId: 'b', seq: 2, ticketNo: 'HP002', faceValue: 100 },
      { rowId: 'c', seq: 3 },
    ])
    const rows = safeParseInterestRows(mixed)
    expect(rows).toHaveLength(1)
    expect(rows[0].ticketNo).toBe('HP002')
    expect(rows[0].seq).toBe(1)

    const allBlank = JSON.stringify([{ rowId: 'x', seq: 1 }, { rowId: 'y', seq: 2 }])
    expect(safeParseInterestRows(allBlank)).toHaveLength(1)
  })

  it('非法 JSON 返回空数组', () => {
    expect(safeParseInterestRows('not-json')).toEqual([])
    expect(safeParseInterestRows(null)).toEqual([])
  })
})
