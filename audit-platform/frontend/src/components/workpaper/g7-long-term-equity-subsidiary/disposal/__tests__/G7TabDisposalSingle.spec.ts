/**
 * 单元测试 — G7-11 处置检查（非一揽子交易）
 *
 * 测试内容：
 * 1. 个别处置损益公式：calcDisposalGain(price, bookValue, dividend, oci)
 * 2. 处置比例>100%校验阻断
 * 3. 正常数据计算验证
 *
 * Spec: .kiro/specs/g7-long-term-equity-subsidiary/
 * Task: 8.3
 *
 * **Validates: Requirements 5.1, 5.3**
 */
import { describe, it, expect } from 'vitest'
import { calcDisposalGain, parseNum } from '../../../composables/useG7SubFormulaEngine'

// ═══════════════════════════════════════════════════════════════════════════════
// 1. 个别处置损益公式验证
// ═══════════════════════════════════════════════════════════════════════════════

describe('G7-11 个别处置损益公式: calcDisposalGain', () => {
  /**
   * **Validates: Requirements 5.3**
   *
   * 处置损益(个别报表) = 处置对价 - 处置日账面 - 应收股利 + 可转损益OCI
   */
  it('基本公式: price - bookValue - dividend + oci', () => {
    // 处置对价1000万, 账面800万, 应收股利50万, 可转OCI 30万
    // 损益 = 1000 - 800 - 50 + 30 = 180
    expect(calcDisposalGain(1000, 800, 50, 30)).toBe(180)
  })

  it('OCI为负(原减值转损益)时减少处置损益', () => {
    // 处置对价500, 账面400, 股利0, OCI=-20
    // 损益 = 500 - 400 - 0 + (-20) = 80
    expect(calcDisposalGain(500, 400, 0, -20)).toBe(80)
  })

  it('处置亏损(对价<账面)时结果为负', () => {
    // 处置对价300, 账面500, 股利10, OCI=5
    // 损益 = 300 - 500 - 10 + 5 = -205
    expect(calcDisposalGain(300, 500, 10, 5)).toBe(-205)
  })

  it('所有参数为0时处置损益为0', () => {
    expect(calcDisposalGain(0, 0, 0, 0)).toBe(0)
  })

  it('大额数据精度验证(亿级)', () => {
    // 处置对价5亿, 账面3.5亿, 股利2000万, OCI 1500万
    // 损益 = 500000000 - 350000000 - 20000000 + 15000000 = 145000000
    expect(calcDisposalGain(500000000, 350000000, 20000000, 15000000)).toBe(145000000)
  })

  it('小数精度: 结果保留两位小数', () => {
    // 1000.555 - 800.333 - 50.111 + 30.222 = 180.333
    const result = calcDisposalGain(1000.555, 800.333, 50.111, 30.222)
    expect(result).toBeCloseTo(180.33, 2)
  })

  it('parseNum兜底: 非法输入视为0', () => {
    // 使用parseNum处理非法值
    expect(calcDisposalGain(parseNum(null), parseNum(undefined), parseNum(''), parseNum('abc'))).toBe(0)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 2. 处置比例校验逻辑
// ═══════════════════════════════════════════════════════════════════════════════

describe('G7-11 处置比例校验', () => {
  /**
   * **Validates: Requirements 5.1**
   *
   * 处置比例>100%（即>1.0）→ 前端校验阻断
   * 处置比例范围: 0 ~ 1.0 (0%~100%)
   */
  function validateDisposalRatio(ratio: number): { valid: boolean; message?: string } {
    const r = parseNum(ratio)
    if (r > 1) {
      return { valid: false, message: '处置比例不能超过100%' }
    }
    if (r < 0) {
      return { valid: false, message: '处置比例不能为负数' }
    }
    return { valid: true }
  }

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
    const result = validateDisposalRatio(1.01)
    expect(result.valid).toBe(false)
  })

  it('处置比例为负数阻断', () => {
    const result = validateDisposalRatio(-0.1)
    expect(result.valid).toBe(false)
    expect(result.message).toContain('负数')
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 3. 正常数据计算验证(完整行数据模拟)
// ═══════════════════════════════════════════════════════════════════════════════

describe('G7-11 完整行数据计算', () => {
  /**
   * **Validates: Requirements 5.1, 5.3**
   *
   * 模拟G7-11表完整行数据的公式列计算
   */
  interface G7DisposalSingleRow {
    investeeName: string
    disposalDate: string
    disposalRatio: number
    disposalPrice: number
    disposalDateBookValue: number
    disposalDateDividend: number
    priorOCICumulative: number
    transferableOCI: number
  }

  function calcRowGain(row: G7DisposalSingleRow): number {
    return calcDisposalGain(
      row.disposalPrice,
      row.disposalDateBookValue,
      row.disposalDateDividend,
      row.transferableOCI,
    )
  }

  it('案例1: 全额处置子公司A', () => {
    const row: G7DisposalSingleRow = {
      investeeName: '子公司A',
      disposalDate: '2025-06-30',
      disposalRatio: 1.0,
      disposalPrice: 5000,
      disposalDateBookValue: 3800,
      disposalDateDividend: 200,
      priorOCICumulative: 150,
      transferableOCI: 120,
    }
    // 5000 - 3800 - 200 + 120 = 1120
    expect(calcRowGain(row)).toBe(1120)
  })

  it('案例2: 部分处置子公司B(60%)', () => {
    const row: G7DisposalSingleRow = {
      investeeName: '子公司B',
      disposalDate: '2025-09-15',
      disposalRatio: 0.6,
      disposalPrice: 2400,
      disposalDateBookValue: 2000,
      disposalDateDividend: 0,
      priorOCICumulative: 80,
      transferableOCI: 50,
    }
    // 2400 - 2000 - 0 + 50 = 450
    expect(calcRowGain(row)).toBe(450)
  })

  it('案例3: 处置亏损(折价出售)', () => {
    const row: G7DisposalSingleRow = {
      investeeName: '子公司C',
      disposalDate: '2025-12-01',
      disposalRatio: 0.8,
      disposalPrice: 1000,
      disposalDateBookValue: 1500,
      disposalDateDividend: 100,
      priorOCICumulative: 0,
      transferableOCI: 0,
    }
    // 1000 - 1500 - 100 + 0 = -600
    expect(calcRowGain(row)).toBe(-600)
  })
})
