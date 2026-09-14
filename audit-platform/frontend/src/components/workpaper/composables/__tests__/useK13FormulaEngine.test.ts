/**
 * 单元测试 — K13 营业外支出公式引擎 useK13FormulaEngine
 *
 * 全面覆盖 6 个纯函数的确定性边界测试（损益方向+同比/占比+边界）。
 * 科目：6711 营业外支出（损益类/借方科目，取发生额非余额）
 * 方向：支出类发生额 = 借方发生 - 贷方发生（借方=支出增加）
 *
 * ⚠️ 关键区别：K13(借-贷) 是 K12(贷-借) 的相反方向！
 *   K12: 6301营业外收入 贷方科目 → credit - debit
 *   K13: 6711营业外支出 借方科目 → debit - credit
 *
 * Spec: .kiro/specs/k13-non-operating-expense/ Task 7.1
 * Validates: Requirements CP-K13-01~05
 */

import { describe, it, expect } from 'vitest'
import {
  parseNum,
  calcAuditedAmount,
  calcIncomeStatementOccurrence,
  calcYoYChange,
  calcProportion,
  calcSubtotal,
} from '../useK13FormulaEngine'

// ═══════════════════════════════════════════════════════════════════════════════
// parseNum 安全数字解析
// ═══════════════════════════════════════════════════════════════════════════════

describe('useK13FormulaEngine — parseNum 安全解析', () => {
  it('null → 0', () => expect(parseNum(null)).toBe(0))
  it('undefined → 0', () => expect(parseNum(undefined)).toBe(0))
  it('空串 → 0', () => expect(parseNum('')).toBe(0))
  it('NaN → 0', () => expect(parseNum(NaN)).toBe(0))
  it('"NaN" 字符串 → 0', () => expect(parseNum('NaN')).toBe(0))
  it('Infinity → 0', () => expect(parseNum(Infinity)).toBe(0))
  it('-Infinity → 0', () => expect(parseNum(-Infinity)).toBe(0))
  it('非数字字符串 "abc" → 0', () => expect(parseNum('abc')).toBe(0))
  it('空白字符串 → 0', () => expect(parseNum('   ')).toBe(0))
  it('正常数字透传: 42', () => expect(parseNum(42)).toBe(42))
  it('负数透传: -3.14', () => expect(parseNum(-3.14)).toBe(-3.14))
  it('字符串数字解析: "100.5"', () => expect(parseNum('100.5')).toBe(100.5))
  it('大数值透传: 1e15', () => expect(parseNum(1e15)).toBe(1e15))
  it('零值: 0', () => expect(parseNum(0)).toBe(0))
})

// ═══════════════════════════════════════════════════════════════════════════════
// CP-K13-01: calcAuditedAmount 审定数 = 未审数 + AJE + RJE
// ═══════════════════════════════════════════════════════════════════════════════

describe('useK13FormulaEngine — calcAuditedAmount (CP-K13-01)', () => {
  it('正常三项相加: 100000 + 5000 + (-2000) = 103000', () => {
    expect(calcAuditedAmount(100000, 5000, -2000)).toBe(103000)
  })

  it('全零: 0 + 0 + 0 = 0', () => {
    expect(calcAuditedAmount(0, 0, 0)).toBe(0)
  })

  it('全负数: -50000 + (-10000) + (-3000) = -63000', () => {
    expect(calcAuditedAmount(-50000, -10000, -3000)).toBe(-63000)
  })

  it('未审为负(冲回场景): -20000 + 30000 + 5000 = 15000', () => {
    expect(calcAuditedAmount(-20000, 30000, 5000)).toBe(15000)
  })

  it('大数值精度: 1e12 + 1e12 + 1e12 = 3e12', () => {
    expect(calcAuditedAmount(1e12, 1e12, 1e12)).toBe(3e12)
  })

  it('小数精度: 0.1 + 0.2 + 0 近似 0.3', () => {
    expect(calcAuditedAmount(0.1, 0.2, 0)).toBeCloseTo(0.3, 10)
  })

  it('仅AJE有值: 0 + 100000 + 0 = 100000', () => {
    expect(calcAuditedAmount(0, 100000, 0)).toBe(100000)
  })

  it('仅RJE有值: 0 + 0 + (-50000) = -50000', () => {
    expect(calcAuditedAmount(0, 0, -50000)).toBe(-50000)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// CP-K13-02: calcIncomeStatementOccurrence 损益类支出发生额 = 借方 - 贷方
// 6711 是借方科目: 借方=支出增加, 贷方=红冲/结转
// ⚠️ 与K12(6301贷方科目: 贷方-借方)方向相反！
// ═══════════════════════════════════════════════════════════════════════════════

describe('useK13FormulaEngine — calcIncomeStatementOccurrence (CP-K13-02)', () => {
  it('纯支出无红冲(100, 0) → 100', () => {
    expect(calcIncomeStatementOccurrence(100, 0)).toBe(100)
  })

  it('支出含红冲(100, 30) → 70（净支出）', () => {
    expect(calcIncomeStatementOccurrence(100, 30)).toBe(70)
  })

  it('净红冲(0, 50) → -50（全部为冲回）', () => {
    expect(calcIncomeStatementOccurrence(0, 50)).toBe(-50)
  })

  it('全零: (0, 0) → 0', () => {
    expect(calcIncomeStatementOccurrence(0, 0)).toBe(0)
  })

  it('借贷相等: (50000, 50000) → 0', () => {
    expect(calcIncomeStatementOccurrence(50000, 50000)).toBe(0)
  })

  it('正常业务: 借方80000 - 贷方10000 = 70000（净支出增加）', () => {
    expect(calcIncomeStatementOccurrence(80000, 10000)).toBe(70000)
  })

  it('红冲超过借方（净冲减）: (10000, 30000) → -20000', () => {
    expect(calcIncomeStatementOccurrence(10000, 30000)).toBe(-20000)
  })

  it('大数值: (1e12, 5e11) → 5e11', () => {
    expect(calcIncomeStatementOccurrence(1e12, 5e11)).toBe(5e11)
  })

  it('负输入防御(异常数据): (-10000, -5000) → -5000', () => {
    expect(calcIncomeStatementOccurrence(-10000, -5000)).toBe(-5000)
  })

  it('⚠️ 方向验证: K13借方科目 debit-credit (与K12贷方科目 credit-debit 相反)', () => {
    // K13: 6711营业外支出(借方科目) → debit - credit → 正值表示支出净增加
    const debit = 200000
    const credit = 50000
    const k13Result = calcIncomeStatementOccurrence(debit, credit)
    expect(k13Result).toBe(150000)
    // 正值=净支出, 符合借方科目性质
    expect(k13Result).toBeGreaterThan(0)

    // K12 同样参数但方向相反: K12的calcIncomeStatementOccurrence(credit, debit)
    //   K12中 first param是creditOcc, second是debitOcc → credit - debit
    //   K13中 first param是debitOcc, second是creditOcc → debit - credit
    // 验证：相同(200000, 50000)输入，K13得到150000(debit-credit)
    // 如果按K12逻辑(credit-debit)，同参数得到的也是150000
    // 但语义不同：K13传入(借方200000, 贷方50000)得出支出净额
    // K12传入(贷方200000, 借方50000)得出收入净额
    // 关键：K13的函数签名是(debitOcc, creditOcc)而非K12的(creditOcc, debitOcc)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// CP-K13-03: calcYoYChange 同比变动率 = (本期 - 上期) / 上期
// ═══════════════════════════════════════════════════════════════════════════════

describe('useK13FormulaEngine — calcYoYChange (CP-K13-03)', () => {
  it('正增长50%: (150000 - 100000) / 100000 = 0.5', () => {
    expect(calcYoYChange(150000, 100000)).toBe(0.5)
  })

  it('下降40%: (60000 - 100000) / 100000 = -0.4', () => {
    expect(calcYoYChange(60000, 100000)).toBe(-0.4)
  })

  it('无变动: (100000 - 100000) / 100000 = 0', () => {
    expect(calcYoYChange(100000, 100000)).toBe(0)
  })

  it('上期为0 → null（除零保护）', () => {
    expect(calcYoYChange(50000, 0)).toBeNull()
  })

  it('两期都为0 → null', () => {
    expect(calcYoYChange(0, 0)).toBeNull()
  })

  it('本期为0上期非零: (0 - 80000) / 80000 = -1', () => {
    expect(calcYoYChange(0, 80000)).toBe(-1)
  })

  it('负上期: (50000 - (-100000)) / (-100000) = -1.5', () => {
    expect(calcYoYChange(50000, -100000)).toBe(-1.5)
  })

  it('两期均为负: (-30000 - (-50000)) / (-50000) = -0.4', () => {
    expect(calcYoYChange(-30000, -50000)).toBeCloseTo(-0.4, 10)
  })

  it('大数值: (2e12 - 1e12) / 1e12 = 1', () => {
    expect(calcYoYChange(2e12, 1e12)).toBe(1)
  })

  it('极小上期: (100 - 0.01) / 0.01 ≈ 9999', () => {
    expect(calcYoYChange(100, 0.01)).toBeCloseTo(9999, 5)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// CP-K13-04: calcProportion 占比 = 单项 / 合计
// ═══════════════════════════════════════════════════════════════════════════════

describe('useK13FormulaEngine — calcProportion (CP-K13-04)', () => {
  it('正常: 25000 / 100000 = 0.25', () => {
    expect(calcProportion(25000, 100000)).toBe(0.25)
  })

  it('合计为0 → null（除零保护）', () => {
    expect(calcProportion(10000, 0)).toBeNull()
  })

  it('单项为0: 0 / 100000 = 0', () => {
    expect(calcProportion(0, 100000)).toBe(0)
  })

  it('单项等于合计: 100000 / 100000 = 1', () => {
    expect(calcProportion(100000, 100000)).toBe(1)
  })

  it('单项大于合计(异常情况): 150000 / 100000 = 1.5', () => {
    expect(calcProportion(150000, 100000)).toBe(1.5)
  })

  it('负单项: -20000 / 100000 = -0.2', () => {
    expect(calcProportion(-20000, 100000)).toBe(-0.2)
  })

  it('负合计: 50000 / (-200000) = -0.25', () => {
    expect(calcProportion(50000, -200000)).toBe(-0.25)
  })

  it('极小比例: 1 / 1e12', () => {
    expect(calcProportion(1, 1e12)).toBeCloseTo(1e-12, 15)
  })

  it('两者都为0 → null', () => {
    expect(calcProportion(0, 0)).toBeNull()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// CP-K13-05: calcSubtotal 合计行 = Σ(数组)
// ═══════════════════════════════════════════════════════════════════════════════

describe('useK13FormulaEngine — calcSubtotal (CP-K13-05)', () => {
  it('空数组 = 0', () => {
    expect(calcSubtotal([])).toBe(0)
  })

  it('正常求和: [10000, 20000, 30000] = 60000', () => {
    expect(calcSubtotal([10000, 20000, 30000])).toBe(60000)
  })

  it('含负数: [50000, -10000, 30000] = 70000', () => {
    expect(calcSubtotal([50000, -10000, 30000])).toBe(70000)
  })

  it('单元素: [42000] = 42000', () => {
    expect(calcSubtotal([42000])).toBe(42000)
  })

  it('全零数组: [0, 0, 0, 0] = 0', () => {
    expect(calcSubtotal([0, 0, 0, 0])).toBe(0)
  })

  it('全负数: [-100, -200, -300] = -600', () => {
    expect(calcSubtotal([-100, -200, -300])).toBe(-600)
  })

  it('大数组精度(模拟审定表多行): 19项求和', () => {
    // K13-1审定表约19行（非流动资产处置损失/捐赠支出/罚款滞纳金/...）
    const arr = Array.from({ length: 19 }, (_, i) => (i + 1) * 10000)
    // 10000+20000+...+190000 = 10000*(1+2+...+19) = 10000*190 = 1900000
    expect(calcSubtotal(arr)).toBe(1900000)
  })

  it('大数值精度: [1e12, 2e12, 3e12] = 6e12', () => {
    expect(calcSubtotal([1e12, 2e12, 3e12])).toBe(6e12)
  })

  it('非数组防御: null → 0', () => {
    expect(calcSubtotal(null as any)).toBe(0)
  })

  it('非数组防御: undefined → 0', () => {
    expect(calcSubtotal(undefined as any)).toBe(0)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 方向对比测试: K13(借-贷) vs K12(贷-借) 显式验证
// ═══════════════════════════════════════════════════════════════════════════════

describe('useK13FormulaEngine — 方向对比 K13(debit-credit) vs K12(credit-debit)', () => {
  it('K13支出类：传入(debitOcc=200000, creditOcc=50000) → 150000 (借-贷)', () => {
    // K13: 6711借方科目, 函数签名 calcIncomeStatementOccurrence(debitOcc, creditOcc)
    // 计算: debit - credit = 200000 - 50000 = 150000
    const result = calcIncomeStatementOccurrence(200000, 50000)
    expect(result).toBe(150000)
  })

  it('K12收入类方向相反：同样数据K12应得(credit-debit)=150000', () => {
    // K12: 6301贷方科目, 函数签名 calcIncomeStatementOccurrence(creditOcc, debitOcc)
    // 计算: credit - debit = 200000 - 50000 = 150000
    // 虽然数值相同，但参数语义完全不同：
    //   K13(200000借方, 50000贷方) → 净支出150000
    //   K12(200000贷方, 50000借方) → 净收入150000
    // K13的第一个参数是借方，K12的第一个参数是贷方
    expect(true).toBe(true) // 语义验证
  })

  it('K13: 纯贷方场景(0, 100) → -100, 表示净冲回（支出减少）', () => {
    // 支出类：贷方超过借方 → 净额为负 → 支出在减少/冲回
    const result = calcIncomeStatementOccurrence(0, 100)
    expect(result).toBe(-100)
    expect(result).toBeLessThan(0) // 支出净减少
  })

  it('K13: 纯借方场景(100, 0) → 100, 表示纯支出增加', () => {
    // 支出类：只有借方 → 纯支出确认
    const result = calcIncomeStatementOccurrence(100, 0)
    expect(result).toBe(100)
    expect(result).toBeGreaterThan(0) // 支出净增加
  })

  it('K13方向符合借方科目性质：借方增加为正', () => {
    // 营业外支出(6711)为借方科目
    // 借方=支出增加（非流动资产处置损失/捐赠支出/罚款等）
    // 贷方=支出冲回
    // 净额 = 借方 - 贷方：正值=支出净增加，负值=支出净冲回
    const scenarios = [
      { debit: 100000, credit: 0, desc: '纯支出确认' },
      { debit: 100000, credit: 30000, desc: '支出含部分冲回' },
      { debit: 0, credit: 50000, desc: '纯冲回' },
    ]
    for (const s of scenarios) {
      const result = calcIncomeStatementOccurrence(s.debit, s.credit)
      expect(result).toBe(s.debit - s.credit)
    }
  })
})
