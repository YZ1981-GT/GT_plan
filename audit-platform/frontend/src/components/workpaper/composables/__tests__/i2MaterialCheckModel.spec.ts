import { describe, it, expect } from 'vitest'
import {
  normalizeI2MaterialRow,
  summarizeI2Material,
  extractI27MaterialTotal,
  hasQtyMismatch,
  hasProjectMismatch,
  suggestAbnormal,
  formatCoverageLabel,
  emptyI2MaterialRow,
} from '../i2MaterialCheckModel'

describe('i2MaterialCheckModel', () => {
  it('兼容旧版精简字段并回填借方金额', () => {
    const row = normalizeI2MaterialRow({
      materialName: '试剂A',
      quantity: 10,
      unitPrice: 2.5,
      requisitionNo: 'LL-001',
      projectName: '项目甲',
      conclusion: '相符',
    })
    expect(row.inventoryName).toBe('试剂A')
    expect(row.slipDateNo).toBe('LL-001')
    expect(row.debitAmount).toBe(25)
    expect(row.slipQty).toBe(10)
  })

  it('检查比例在总体为 0 时返回 null（避免 #DIV/0!）', () => {
    const rows = [emptyI2MaterialRow({ debitAmount: 100 })]
    const s = summarizeI2Material(rows, 0)
    expect(s.coverageRate).toBeNull()
    expect(formatCoverageLabel(s.coverageRate)).toBe('N/A')
  })

  it('检查比例 = 样本借方合计 / 本期发生额', () => {
    const rows = [
      emptyI2MaterialRow({ debitAmount: 300 }),
      emptyI2MaterialRow({ debitAmount: 200 }),
    ]
    const s = summarizeI2Material(rows, 1000)
    expect(s.checkedTotal).toBe(500)
    expect(s.coverageRate).toBe(50)
  })

  it('数量/项目不符可识别并建议异常标记', () => {
    const row = emptyI2MaterialRow({
      projectName: '项目甲',
      slipProject: '项目乙',
      quantity: 10,
      slipQty: 8,
    })
    expect(hasQtyMismatch(row)).toBe(true)
    expect(hasProjectMismatch(row)).toBe(true)
    expect(suggestAbnormal(row)).toBe('数量不符')
  })

  it('从 I2-7 行提取材料费合计', () => {
    const total = extractI27MaterialTotal([
      { materialDirect: 100, materialAux: 50, materialFuel: 0 },
      { materialSubtotal: 200 },
    ])
    expect(total).toBe(350)
  })

  it('异常计数排除「否」与空值', () => {
    const s = summarizeI2Material([
      emptyI2MaterialRow({ debitAmount: 1, isAbnormal: '否' }),
      emptyI2MaterialRow({ debitAmount: 1, isAbnormal: '' }),
      emptyI2MaterialRow({ debitAmount: 1, isAbnormal: '生产混入' }),
    ], 100)
    expect(s.anomalyCount).toBe(1)
  })
})
