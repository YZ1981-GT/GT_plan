/**
 * 单元测试 — G7-11 处置检查（非一揽子交易）
 *
 * Spec: .kiro/specs/g7-long-term-equity-subsidiary/
 * Task: 8.3
 *
 * **Validates: Requirements 5.1, 5.3**
 */
import { describe, it, expect } from 'vitest'
import { calcDisposalGain, parseNum } from '../../../composables/useG7SubFormulaEngine'
import {
  validateDisposalRatio,
  normalizeDisposalRatio,
  recalcDisposalSingleRow,
  createEmptyDisposalSingleRow,
  hydrateDisposalSingleRow,
  clearConsolidatedGainManual,
  setConsolidatedGainManual,
  calcConsolidatedDisposalGain,
  pickBookValueFromG710,
} from '../g7DisposalSingleModel'

describe('G7-11 个别处置损益公式: calcDisposalGain', () => {
  it('基本公式: price - bookValue - dividend + oci', () => {
    expect(calcDisposalGain(1000, 800, 50, 30)).toBe(180)
  })

  it('OCI为负(原减值转损益)时减少处置损益', () => {
    expect(calcDisposalGain(500, 400, 0, -20)).toBe(80)
  })

  it('处置亏损(对价<账面)时结果为负', () => {
    expect(calcDisposalGain(300, 500, 10, 5)).toBe(-205)
  })

  it('所有参数为0时处置损益为0', () => {
    expect(calcDisposalGain(0, 0, 0, 0)).toBe(0)
  })

  it('大额数据精度验证(亿级)', () => {
    expect(calcDisposalGain(500000000, 350000000, 20000000, 15000000)).toBe(145000000)
  })

  it('小数精度: 结果保留两位小数', () => {
    const result = calcDisposalGain(1000.555, 800.333, 50.111, 30.222)
    expect(result).toBeCloseTo(180.33, 2)
  })

  it('parseNum兜底: 非法输入视为0', () => {
    expect(calcDisposalGain(parseNum(null), parseNum(undefined), parseNum(''), parseNum('abc'))).toBe(0)
  })
})

describe('G7-11 处置比例校验（生产 validateDisposalRatio）', () => {
  it('处置比例=50%通过校验', () => {
    expect(validateDisposalRatio(0.5)).toEqual({ valid: true })
  })

  it('处置比例=100%通过校验(丧失控制权)', () => {
    expect(validateDisposalRatio(1.0)).toEqual({ valid: true })
  })

  it('处置比例=0通过校验(边界)', () => {
    expect(validateDisposalRatio(0)).toEqual({ valid: true })
  })

  it('处置比例>100%阻断', () => {
    const result = validateDisposalRatio(1.5)
    expect(result.valid).toBe(false)
    expect(result.message).toContain('100%')
  })

  it('处置比例=101%阻断', () => {
    expect(validateDisposalRatio(1.01).valid).toBe(false)
  })

  it('处置比例为负数阻断', () => {
    const result = validateDisposalRatio(-0.1)
    expect(result.valid).toBe(false)
    expect(result.message).toContain('负数')
  })

  it('normalizeDisposalRatio: 百分数 30 → 0.3', () => {
    expect(normalizeDisposalRatio(30)).toBe(0.3)
  })

  it('normalizeDisposalRatio: 已是小数保持', () => {
    expect(normalizeDisposalRatio(0.3)).toBe(0.3)
  })
})

describe('G7-11 完整行数据计算', () => {
  it('案例1: 全额处置子公司A', () => {
    const row = hydrateDisposalSingleRow({
      investeeName: '子公司A',
      disposalDate: '2025-06-30',
      disposalRatio: 1.0,
      disposalPrice: 5000,
      disposalDateBookValue: 3800,
      disposalDateDividend: 200,
      priorOCICumulative: 150,
      transferableOCI: 120,
    }, 1)
    expect(row.individualGain).toBe(1120)
  })

  it('案例2: 部分处置子公司B(60%)', () => {
    const row = hydrateDisposalSingleRow({
      investeeName: '子公司B',
      disposalRatio: 0.6,
      disposalPrice: 2400,
      disposalDateBookValue: 2000,
      transferableOCI: 50,
    }, 1)
    expect(row.individualGain).toBe(450)
  })

  it('案例3: 处置亏损(折价出售)', () => {
    const row = hydrateDisposalSingleRow({
      investeeName: '子公司C',
      disposalRatio: 0.8,
      disposalPrice: 1000,
      disposalDateBookValue: 1500,
      disposalDateDividend: 100,
    }, 1)
    expect(row.individualGain).toBe(-600)
  })

  it('priorOCICumulative 不进个别损益公式', () => {
    const row = createEmptyDisposalSingleRow(1)
    row.disposalPrice = 1000
    row.disposalDateBookValue = 800
    row.disposalDateDividend = 0
    row.priorOCICumulative = 999
    row.transferableOCI = 50
    recalcDisposalSingleRow(row)
    expect(row.individualGain).toBe(250)
  })

  it('合并处置损益默认公式', () => {
    expect(calcConsolidatedDisposalGain(180, 20, 50)).toBe(150)
  })

  it('合并处置损益可手工覆盖，按公式可恢复', () => {
    const row = hydrateDisposalSingleRow({
      disposalPrice: 1000,
      disposalDateBookValue: 800,
      consolidationAdjustment: 10,
      consolidatedNetAssetShare: 50,
    }, 1)
    expect(row.individualGain).toBe(200)
    expect(row.consolidatedGain).toBe(160)
    setConsolidatedGainManual(row, 999)
    expect(row.consolidatedGainManual).toBe(true)
    expect(row.consolidatedGain).toBe(999)
    row.disposalPrice = 1100
    recalcDisposalSingleRow(row)
    expect(row.consolidatedGain).toBe(999)
    clearConsolidatedGainManual(row)
    expect(row.consolidatedGainManual).toBe(false)
    expect(row.consolidatedGain).toBe(260)
  })

  it('hydrate 兼容旧字段名 bookValueDisposed', () => {
    const row = hydrateDisposalSingleRow({
      bookValueDisposed: 500,
      dividendReceivable: 10,
      consolAdjustment: 5,
      netAssetShare: 20,
      disposalPrice: 800,
    }, 1)
    expect(row.disposalDateBookValue).toBe(500)
    expect(row.disposalDateDividend).toBe(10)
    expect(row.consolidationAdjustment).toBe(5)
    expect(row.consolidatedNetAssetShare).toBe(20)
    expect(row.individualGain).toBe(290)
  })

  it('pickBookValueFromG710 按名称匹配 partialDisposal', () => {
    const book = pickBookValueFromG710(
      [{ section: 'partialDisposal', investeeName: '甲公司', bookValueAtDisposal: 1234 }],
      '甲公司',
    )
    expect(book).toBe(1234)
  })

  it('pickBookValueFromG710 匹配 companyName 并算剩余账面', () => {
    const book = pickBookValueFromG710(
      {
        rows: [{
          section: 'partialDisposal',
          companyName: '乙公司',
          bookValueAtDisposal: 1000,
          originalRatio: 0.8,
          reducedRatio: 0.2,
        }],
      },
      '乙公司',
    )
    // 剩余 = 1000 × (1 − 0.2/0.8) = 750
    expect(book).toBe(750)
  })

  it('pickBookValueFromG710 信封+investeeId 优先', () => {
    const book = pickBookValueFromG710(
      {
        materialityLevel: 1,
        rows: [
          { section: 'partialDisposal', companyName: '丙', investeeId: 'id-1', bookValueAtDisposal: 500, originalRatio: 1, reducedRatio: 0 },
          { section: 'partialDisposal', companyName: '丁', investeeId: 'id-2', bookValueAtDisposal: 900 },
        ],
      },
      '错名',
      'id-2',
    )
    expect(book).toBe(900)
  })
})
