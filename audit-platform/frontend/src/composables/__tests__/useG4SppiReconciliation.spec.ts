/**
 * Unit Tests — G4-8 盘点倒轧迁移与倒轧公式
 */
import { describe, it, expect } from 'vitest'
import { migrateLegacyItem } from '../useG4SppiReconciliation'
import { calcReportDateQuantity } from '../useG4SppiFormulaEngine'

describe('migrateLegacyItem', () => {
  it('保留拆分增减字段', () => {
    const row = migrateLegacyItem(
      {
        securitiesName: '国债21',
        countQuantity: 1000,
        countFaceValue: 100,
        increaseQuantity: 100,
        decreaseQuantity: 20,
        bookQuantity: 920,
        bookFaceValue: 100,
      },
      0,
    )
    expect(row.reportQuantity).toBe(920)
    expect(row.reportTotal).toBe(92000)
    expect(row.bookTotal).toBe(92000)
    expect(row.variance).toBe(0)
    expect(row.varianceQuantity).toBe(0)
  })

  it('旧 changeQuantity≥0 迁移为减少，保持 report=count+change', () => {
    const row = migrateLegacyItem(
      {
        securitiesName: '企债A',
        countQuantity: 100,
        countFaceValue: 10,
        changeQuantity: 10,
        changeFaceValueTotal: 100,
        bookQuantity: 110,
        bookFaceValue: 10,
      },
      0,
    )
    expect(row.decreaseQuantity).toBe(10)
    expect(row.increaseQuantity).toBe(0)
    expect(row.reportQuantity).toBe(110)
  })

  it('旧 changeQuantity<0 迁移为增加', () => {
    const row = migrateLegacyItem(
      {
        securitiesName: '企债B',
        countQuantity: 100,
        countFaceValue: 10,
        changeQuantity: -15,
        bookQuantity: 85,
        bookFaceValue: 10,
      },
      0,
    )
    expect(row.increaseQuantity).toBe(15)
    expect(row.reportQuantity).toBe(85)
  })

  it('利率到期日由盘点日继承至报表日', () => {
    const row = migrateLegacyItem(
      {
        securitiesName: '国债',
        countQuantity: 1,
        countFaceValue: 100,
        countCouponRate: 3.5,
        countMaturityDate: '2030-12-31',
        bookQuantity: 1,
        bookFaceValue: 100,
      },
      0,
    )
    expect(row.reportCouponRate).toBe(3.5)
    expect(row.reportMaturityDate).toBe('2030-12-31')
  })
})

describe('倒轧方向示例（对齐致同）', () => {
  it('盘点日1000，期后购入100、处置20 → 报表日920', () => {
    expect(calcReportDateQuantity(1000, 100, 20)).toBe(920)
  })
})
