/**
 * decimal.ts 单元测试 — 金额 Decimal 化（V3 收官增强 Req 2）
 *
 * 覆盖：
 * 1. toDecimal：null/undefined 处理、NaN/Infinity 拒绝、合法输入
 * 2. addAmount：空参数、多值累加、混合类型、无浮点误差
 * 3. quantize：scale=0/2/4、ROUND_HALF_UP 行为
 * 4. amountTolerance：小/中/大金额三档
 * 5. amountEquals：相等、容差内、容差外
 */
import { describe, it, expect } from 'vitest'
import Decimal from 'decimal.js'
import {
  AmountConversionError,
  addAmount,
  amountEquals,
  amountTolerance,
  quantize,
  toDecimal,
} from '../decimal'

describe('toDecimal — 安全转换', () => {
  it('合法 number 输入', () => {
    const d = toDecimal(123.45)
    expect(d).not.toBeNull()
    expect((d as Decimal).toString()).toBe('123.45')
  })

  it('合法 string 输入', () => {
    const d = toDecimal('999.99')
    expect((d as Decimal).toString()).toBe('999.99')
  })

  it('Decimal 实例直接通过', () => {
    const input = new Decimal('42.42')
    const d = toDecimal(input)
    expect((d as Decimal).equals(input)).toBe(true)
  })

  it('null + allowNull=true 返回 null', () => {
    expect(toDecimal(null, true)).toBeNull()
    expect(toDecimal(undefined, true)).toBeNull()
  })

  it('null + allowNull=false 抛异常', () => {
    expect(() => toDecimal(null)).toThrow(AmountConversionError)
    expect(() => toDecimal(undefined)).toThrow(AmountConversionError)
  })

  it('NaN 抛异常', () => {
    expect(() => toDecimal(NaN)).toThrow(AmountConversionError)
  })

  it('Infinity 抛异常', () => {
    expect(() => toDecimal(Infinity)).toThrow(AmountConversionError)
    expect(() => toDecimal(-Infinity)).toThrow(AmountConversionError)
  })

  it('空字符串抛异常', () => {
    expect(() => toDecimal('')).toThrow(AmountConversionError)
    expect(() => toDecimal('   ')).toThrow(AmountConversionError)
  })

  it('非法字符串抛异常', () => {
    expect(() => toDecimal('abc')).toThrow(AmountConversionError)
    expect(() => toDecimal('1.2.3')).toThrow(AmountConversionError)
  })

  it('科学计数法字符串可解析', () => {
    const d = toDecimal('1.5e3')
    expect((d as Decimal).toString()).toBe('1500')
  })

  it('错误消息携带字段名', () => {
    expect(() => toDecimal(null, false, '调整金额')).toThrow(/调整金额/)
  })
})

describe('addAmount — 金额累加', () => {
  it('空参数返回 0', () => {
    expect(addAmount().toString()).toBe('0')
  })

  it('单值累加', () => {
    expect(addAmount('100.50').toString()).toBe('100.5')
  })

  it('多值累加', () => {
    expect(addAmount('1.00', '2.00', '3.00').toString()).toBe('6')
  })

  it('避免浮点误差：0.1 + 0.2 === 0.3', () => {
    // 原生 JS：0.1 + 0.2 === 0.30000000000000004
    expect((0.1 + 0.2) === 0.3).toBe(false)
    // 而 Decimal 必须精确等于 0.3
    expect(addAmount(0.1, 0.2).toString()).toBe('0.3')
    expect(addAmount(0.1, 0.2).equals(new Decimal('0.3'))).toBe(true)
  })

  it('避免浮点误差：连续累加 0.1 十次 === 1.0', () => {
    const tenPointOnes = Array.from({ length: 10 }, () => 0.1)
    expect(addAmount(...tenPointOnes).toString()).toBe('1')
    // 对照原生 JS
    const native = tenPointOnes.reduce((a, b) => a + b, 0)
    expect(native === 1).toBe(false)
  })

  it('混合类型：string / number / Decimal', () => {
    const sum = addAmount('100.00', 200, new Decimal('300.50'))
    expect(sum.toString()).toBe('600.5')
  })

  it('负数累加', () => {
    expect(addAmount('100.00', '-30.00', '-20.00').toString()).toBe('50')
  })

  it('NaN 输入抛异常', () => {
    expect(() => addAmount(NaN)).toThrow(AmountConversionError)
  })
})

describe('quantize — 四舍五入', () => {
  it('默认 scale=2 元位', () => {
    expect(quantize('123.456').toString()).toBe('123.46')
    expect(quantize('123.454').toString()).toBe('123.45')
  })

  it('scale=0 整元', () => {
    expect(quantize('123.5', 0).toString()).toBe('124')
    expect(quantize('123.49', 0).toString()).toBe('123')
  })

  it('scale=4 千分位', () => {
    expect(quantize('0.123456', 4).toString()).toBe('0.1235')
    expect(quantize('0.123444', 4).toString()).toBe('0.1234')
  })

  it('ROUND_HALF_UP 行为：0.5 进位', () => {
    expect(quantize('0.005', 2).toString()).toBe('0.01')
    expect(quantize('0.015', 2).toString()).toBe('0.02')
    expect(quantize('0.025', 2).toString()).toBe('0.03')
    // 注意：JS Math.round(0.025*100)/100 由于浮点误差结果不稳定，Decimal 必须精确
  })

  it('ROUND_HALF_UP 行为：负数远离 0', () => {
    // ROUND_HALF_UP 在 decimal.js 中是远离 0 取整
    expect(quantize('-0.005', 2).toString()).toBe('-0.01')
    expect(quantize('-0.015', 2).toString()).toBe('-0.02')
  })

  it('已精确值不变', () => {
    expect(quantize('100.00').toString()).toBe('100')
    expect(quantize('100.50').toString()).toBe('100.5')
  })

  it('Decimal 实例输入', () => {
    expect(quantize(new Decimal('99.999')).toString()).toBe('100')
  })

  it('number 输入', () => {
    expect(quantize(99.999).toString()).toBe('100')
  })
})

describe('amountTolerance — 动态容差', () => {
  it('null/undefined 返回最小容差 0.01', () => {
    expect(amountTolerance(null).toString()).toBe('0.01')
    expect(amountTolerance(undefined).toString()).toBe('0.01')
  })

  it('< 1万 → 0.01 绝对容差', () => {
    expect(amountTolerance('0').toString()).toBe('0.01')
    expect(amountTolerance('100').toString()).toBe('0.01')
    expect(amountTolerance('9999.99').toString()).toBe('0.01')
  })

  it('[1万, 100万) → 万分之一', () => {
    expect(amountTolerance('10000').toString()).toBe('1')
    expect(amountTolerance('500000').toString()).toBe('50')
    expect(amountTolerance('999999').equals(new Decimal('999999').times('0.0001'))).toBe(true)
  })

  it('≥ 100万 → 千分之一（默认 ratio）', () => {
    expect(amountTolerance('1000000').toString()).toBe('1000')
    expect(amountTolerance('10000000').toString()).toBe('10000')
  })

  it('支持自定义 ratio', () => {
    expect(amountTolerance('1000000', '0.005').toString()).toBe('5000')
  })

  it('负数取绝对值', () => {
    expect(amountTolerance('-50000').equals(amountTolerance('50000'))).toBe(true)
    expect(amountTolerance('-1000000').toString()).toBe('1000')
  })
})

describe('amountEquals — 容差等值判断', () => {
  it('完全相等返回 true', () => {
    expect(amountEquals('100.00', '100.00')).toBe(true)
    expect(amountEquals(0, 0)).toBe(true)
  })

  it('小金额：差异在 0.01 内返回 true', () => {
    expect(amountEquals('100.00', '100.005')).toBe(true)
    expect(amountEquals('100.00', '100.01')).toBe(true)
  })

  it('小金额：差异超过 0.01 返回 false', () => {
    expect(amountEquals('100.00', '100.02')).toBe(false)
    expect(amountEquals('100.00', '101.00')).toBe(false)
  })

  it('中金额（[1万, 100万)）：万分之一容差内 true', () => {
    // 50万 → 容差 50，差 30 应 true
    expect(amountEquals('500000', '500030')).toBe(true)
    // 差 100 应 false
    expect(amountEquals('500000', '500100')).toBe(false)
  })

  it('大金额（≥100万）：千分之一容差内 true', () => {
    // 1000万 → 容差 1万，差 5000 应 true
    expect(amountEquals('10000000', '10005000')).toBe(true)
    // 差 2万 应 false
    expect(amountEquals('10000000', '10020000')).toBe(false)
  })

  it('避免浮点误差：0.1+0.2 与 0.3 视为相等', () => {
    const sum = addAmount(0.1, 0.2)
    expect(amountEquals(sum, '0.3')).toBe(true)
    // 而原生 0.1+0.2 = 0.30000000000000004 — 用 Decimal 累加后 = 0.3 完全相等
    expect(sum.equals(new Decimal('0.3'))).toBe(true)
  })

  it('混合类型输入', () => {
    expect(amountEquals(100, '100.00')).toBe(true)
    expect(amountEquals(new Decimal('100'), 100.005)).toBe(true)
  })

  it('一正一负差异极大：返回 false', () => {
    expect(amountEquals('100', '-100')).toBe(false)
  })
})
