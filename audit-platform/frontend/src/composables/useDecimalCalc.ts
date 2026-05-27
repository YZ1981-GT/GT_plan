import Decimal from 'decimal.js'

Decimal.set({ precision: 20, rounding: Decimal.ROUND_HALF_EVEN })

export interface DecimalCalcOptions {
  /** 结果保留小数位数，默认 2 */
  dp?: number
  /** 舍入模式，默认 ROUND_HALF_EVEN */
  rounding?: Decimal.Rounding
}

/**
 * 高精度金额计算 composable。
 * 所有方法返回 string（toFixed 格式），避免浮点精度丢失。
 */
export function useDecimalCalc(options: DecimalCalcOptions = {}) {
  const { dp = 2, rounding = Decimal.ROUND_HALF_EVEN } = options

  function safeParse(v: number | string): Decimal | null {
    try {
      const d = new Decimal(v)
      if (!d.isFinite()) return null
      return d
    } catch {
      return null
    }
  }

  function add(a: number | string, b: number | string): string {
    const da = safeParse(a)
    const db = safeParse(b)
    if (!da || !db) {
      console.warn('[useDecimalCalc] add: non-numeric input', { a, b })
      return (0).toFixed(dp)
    }
    return da.plus(db).toFixed(dp, rounding)
  }

  function sub(a: number | string, b: number | string): string {
    const da = safeParse(a)
    const db = safeParse(b)
    if (!da || !db) {
      console.warn('[useDecimalCalc] sub: non-numeric input', { a, b })
      return (0).toFixed(dp)
    }
    return da.minus(db).toFixed(dp, rounding)
  }

  function mul(a: number | string, b: number | string): string {
    const da = safeParse(a)
    const db = safeParse(b)
    if (!da || !db) {
      console.warn('[useDecimalCalc] mul: non-numeric input', { a, b })
      return (0).toFixed(dp)
    }
    return da.times(db).toFixed(dp, rounding)
  }

  function div(a: number | string, b: number | string): string {
    const da = safeParse(a)
    const db = safeParse(b)
    if (!da || !db) {
      console.warn('[useDecimalCalc] div: non-numeric input', { a, b })
      return (0).toFixed(dp)
    }
    if (db.isZero()) {
      console.warn('[useDecimalCalc] div: divide by zero', { a, b })
      return (0).toFixed(dp)
    }
    return da.div(db).toFixed(dp, rounding)
  }

  function sum(...values: (number | string)[]): string {
    let acc = new Decimal(0)
    for (const v of values) {
      const dv = safeParse(v)
      if (!dv) {
        console.warn('[useDecimalCalc] sum: non-numeric input', { v })
        return (0).toFixed(dp)
      }
      acc = acc.plus(dv)
    }
    return acc.toFixed(dp, rounding)
  }

  return { add, sub, mul, div, sum }
}
