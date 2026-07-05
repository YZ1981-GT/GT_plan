/**
 * 单元测试 — G7-12 处置检查（一揽子交易）
 *
 * 测试内容：
 * 1. cumulativePrice = SUM(transactionPrice[0..i]) 正确累加
 * 2. cumulativeShareChange = SUM(shareholdingChange[0..i]) 正确累加
 * 3. 一揽子判断依据(packageJudgmentBasis)为空 → 保存阻断
 * 4. 多行累计计算一致性
 *
 * Spec: .kiro/specs/g7-long-term-equity-subsidiary/
 * Task: 8.3
 *
 * **Validates: Requirements 5.2, 5.4**
 */
import { describe, it, expect } from 'vitest'
import { calcDisposalGain, parseNum } from '../../../composables/useG7SubFormulaEngine'

// ═══════════════════════════════════════════════════════════════════════════════
// 辅助函数：一揽子交易累计计算
// ═══════════════════════════════════════════════════════════════════════════════

interface G7DisposalPackageRow {
  id: string
  seq: number
  investeeName: string
  transactionDate: string
  transactionPrice: number
  shareholdingChange: number
  cumulativePrice: number
  cumulativeShareChange: number
  lossOfControlDate: string
  lossDateBookValue: number
  remainingInvestmentFV: number
  retrospectiveAdjustment: number
  consolidatedGain: number
  packageJudgmentBasis: string
  auditConclusion: string
  indexRef: string
}

/**
 * 计算一揽子交易累计对价 — SUM(transactionPrice[0..i])
 * 第i行的累计对价 = 第0行到第i行所有交易对价之和
 */
function calcCumulativePrice(rows: Pick<G7DisposalPackageRow, 'transactionPrice'>[], index: number): number {
  let sum = 0
  for (let i = 0; i <= index; i++) {
    sum += parseNum(rows[i]?.transactionPrice)
  }
  return Math.round(sum * 100) / 100
}

/**
 * 计算一揽子交易累计持股变动 — SUM(shareholdingChange[0..i])
 * 第i行的累计持股变动 = 第0行到第i行所有持股变动之和
 */
function calcCumulativeShareChange(rows: Pick<G7DisposalPackageRow, 'shareholdingChange'>[], index: number): number {
  let sum = 0
  for (let i = 0; i <= index; i++) {
    sum += parseNum(rows[i]?.shareholdingChange)
  }
  return Math.round(sum * 100) / 100
}

/**
 * 一揽子判断依据校验 — packageJudgmentBasis 必填
 */
function validatePackageJudgmentBasis(rows: Pick<G7DisposalPackageRow, 'packageJudgmentBasis'>[]): {
  valid: boolean
  message?: string
  invalidRows?: number[]
} {
  const invalidRows: number[] = []
  for (let i = 0; i < rows.length; i++) {
    const basis = (rows[i].packageJudgmentBasis ?? '').trim()
    if (!basis) {
      invalidRows.push(i)
    }
  }
  if (invalidRows.length > 0) {
    return {
      valid: false,
      message: '一揽子判断依据为必填项，请填写判断依据',
      invalidRows,
    }
  }
  return { valid: true }
}

// ═══════════════════════════════════════════════════════════════════════════════
// 1. cumulativePrice 累计对价正确累加
// ═══════════════════════════════════════════════════════════════════════════════

describe('G7-12 累计对价计算: cumulativePrice = SUM(transactionPrice[0..i])', () => {
  /**
   * **Validates: Requirements 5.2, 5.4**
   */
  it('单行：累计对价等于该行交易对价', () => {
    const rows = [{ transactionPrice: 1000 }]
    expect(calcCumulativePrice(rows, 0)).toBe(1000)
  })

  it('两行：第二行累计等于前两行之和', () => {
    const rows = [
      { transactionPrice: 1000 },
      { transactionPrice: 500 },
    ]
    expect(calcCumulativePrice(rows, 0)).toBe(1000)
    expect(calcCumulativePrice(rows, 1)).toBe(1500)
  })

  it('三行逐步递增累加', () => {
    const rows = [
      { transactionPrice: 200 },
      { transactionPrice: 300 },
      { transactionPrice: 500 },
    ]
    expect(calcCumulativePrice(rows, 0)).toBe(200)
    expect(calcCumulativePrice(rows, 1)).toBe(500)
    expect(calcCumulativePrice(rows, 2)).toBe(1000)
  })

  it('含小数的累加精度保证', () => {
    const rows = [
      { transactionPrice: 100.33 },
      { transactionPrice: 200.67 },
      { transactionPrice: 300.50 },
    ]
    expect(calcCumulativePrice(rows, 0)).toBe(100.33)
    expect(calcCumulativePrice(rows, 1)).toBe(301)
    expect(calcCumulativePrice(rows, 2)).toBe(601.5)
  })

  it('含零值行不影响累加', () => {
    const rows = [
      { transactionPrice: 500 },
      { transactionPrice: 0 },
      { transactionPrice: 300 },
    ]
    expect(calcCumulativePrice(rows, 1)).toBe(500)
    expect(calcCumulativePrice(rows, 2)).toBe(800)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 2. cumulativeShareChange 累计持股变动正确累加
// ═══════════════════════════════════════════════════════════════════════════════

describe('G7-12 累计持股变动: cumulativeShareChange = SUM(shareholdingChange[0..i])', () => {
  /**
   * **Validates: Requirements 5.2, 5.4**
   */
  it('单行：累计变动等于该行变动', () => {
    const rows = [{ shareholdingChange: -0.10 }]
    expect(calcCumulativeShareChange(rows, 0)).toBe(-0.10)
  })

  it('多次减持：持股变动为负值递减', () => {
    const rows = [
      { shareholdingChange: -0.10 },  // 第一次减持10%
      { shareholdingChange: -0.15 },  // 第二次减持15%
      { shareholdingChange: -0.20 },  // 第三次减持20%
    ]
    expect(calcCumulativeShareChange(rows, 0)).toBe(-0.10)
    expect(calcCumulativeShareChange(rows, 1)).toBe(-0.25)
    expect(calcCumulativeShareChange(rows, 2)).toBe(-0.45)
  })

  it('持股变动累计不超过-1.0（全部处置）', () => {
    const rows = [
      { shareholdingChange: -0.30 },
      { shareholdingChange: -0.30 },
      { shareholdingChange: -0.40 },
    ]
    // 最后一行累计=-1.0，即全部处置
    expect(calcCumulativeShareChange(rows, 2)).toBe(-1.0)
  })

  it('小数精度: 避免浮点误差', () => {
    const rows = [
      { shareholdingChange: -0.07 },
      { shareholdingChange: -0.03 },
    ]
    // -0.07 + (-0.03) = -0.10（避免JS浮点 -0.09999...）
    expect(calcCumulativeShareChange(rows, 1)).toBe(-0.10)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 3. 一揽子判断依据必填校验
// ═══════════════════════════════════════════════════════════════════════════════

describe('G7-12 一揽子判断依据(packageJudgmentBasis)必填校验', () => {
  /**
   * **Validates: Requirements 5.2**
   *
   * 一揽子判断依据为空 → 保存时阻断（Toast提示必填）
   */
  it('所有行有判断依据→通过校验', () => {
    const rows = [
      { packageJudgmentBasis: '多次交易在6个月内完成，且存在明确的商业安排' },
      { packageJudgmentBasis: '各次交易的对价安排体现为一揽子交易设计' },
    ]
    expect(validatePackageJudgmentBasis(rows)).toEqual({ valid: true })
  })

  it('第一行为空→阻断并标注行号', () => {
    const rows = [
      { packageJudgmentBasis: '' },
      { packageJudgmentBasis: '存在明确安排' },
    ]
    const result = validatePackageJudgmentBasis(rows)
    expect(result.valid).toBe(false)
    expect(result.message).toContain('必填')
    expect(result.invalidRows).toContain(0)
  })

  it('多行为空→阻断并标注所有空行', () => {
    const rows = [
      { packageJudgmentBasis: '' },
      { packageJudgmentBasis: '有依据' },
      { packageJudgmentBasis: '   ' },  // 仅空格视为空
    ]
    const result = validatePackageJudgmentBasis(rows)
    expect(result.valid).toBe(false)
    expect(result.invalidRows).toEqual([0, 2])
  })

  it('纯空格内容视为空→阻断', () => {
    const rows = [
      { packageJudgmentBasis: '   \t  ' },
    ]
    const result = validatePackageJudgmentBasis(rows)
    expect(result.valid).toBe(false)
  })

  it('空数组→通过(无数据无需校验)', () => {
    expect(validatePackageJudgmentBasis([])).toEqual({ valid: true })
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 4. 多行累计计算一致性
// ═══════════════════════════════════════════════════════════════════════════════

describe('G7-12 多行累计计算一致性', () => {
  /**
   * **Validates: Requirements 5.2, 5.4**
   *
   * 验证一揽子交易完整场景：3次交易逐步丧失控制权
   */
  const packageRows = [
    { transactionPrice: 800, shareholdingChange: -0.20 },   // 第一次: 减持20%, 对价800万
    { transactionPrice: 600, shareholdingChange: -0.15 },   // 第二次: 减持15%, 对价600万
    { transactionPrice: 1200, shareholdingChange: -0.25 },  // 第三次: 减持25%, 对价1200万(丧失控制权)
  ]

  it('累计对价逐行递增且最终等于所有交易对价之和', () => {
    expect(calcCumulativePrice(packageRows, 0)).toBe(800)
    expect(calcCumulativePrice(packageRows, 1)).toBe(1400)
    expect(calcCumulativePrice(packageRows, 2)).toBe(2600)
    // 最终累计 = 800 + 600 + 1200
    expect(calcCumulativePrice(packageRows, 2)).toBe(800 + 600 + 1200)
  })

  it('累计持股变动逐行递减且最终等于总变动', () => {
    expect(calcCumulativeShareChange(packageRows, 0)).toBe(-0.20)
    expect(calcCumulativeShareChange(packageRows, 1)).toBe(-0.35)
    expect(calcCumulativeShareChange(packageRows, 2)).toBe(-0.60)
    // 最终累计 = -0.20 + (-0.15) + (-0.25) = -0.60
    expect(calcCumulativeShareChange(packageRows, 2)).toBe(-0.20 + -0.15 + -0.25)
  })

  it('每行累计对价 = 上一行累计 + 本行交易对价', () => {
    for (let i = 1; i < packageRows.length; i++) {
      const prevCumulative = calcCumulativePrice(packageRows, i - 1)
      const currentCumulative = calcCumulativePrice(packageRows, i)
      expect(currentCumulative).toBeCloseTo(prevCumulative + packageRows[i].transactionPrice, 10)
    }
  })

  it('每行累计持股变动 = 上一行累计 + 本行变动', () => {
    for (let i = 1; i < packageRows.length; i++) {
      const prevCumulative = calcCumulativeShareChange(packageRows, i - 1)
      const currentCumulative = calcCumulativeShareChange(packageRows, i)
      expect(currentCumulative).toBeCloseTo(prevCumulative + packageRows[i].shareholdingChange, 10)
    }
  })

  it('丧失控制权日统一确认: 使用calcDisposalGain计算最终损益', () => {
    // 在丧失控制权日，用累计数据计算处置损益
    const totalPrice = calcCumulativePrice(packageRows, 2)  // 2600
    const lossDateBookValue = 2000
    const dividend = 100
    const oci = 50

    // 合并处置损益 = 累计对价 - 丧失日账面 - 应收股利 + 可转OCI
    // = 2600 - 2000 - 100 + 50 = 550
    const gain = calcDisposalGain(totalPrice, lossDateBookValue, dividend, oci)
    expect(gain).toBe(550)
  })
})
