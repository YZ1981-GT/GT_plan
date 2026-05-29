/**
 * 金额 Decimal 化工具 — V3 收官增强 Req 2（前端版）
 *
 * 镜像后端 `backend/app/services/_decimal_helpers.py`，使用 decimal.js 库
 * 避免 JS 浮点误差（典型反例：0.1 + 0.2 !== 0.3）。
 *
 * 核心函数：
 * - toDecimal：统一将 string/number/null/undefined 转为 Decimal，处理边界 case
 * - addAmount：金额累加（自动 Decimal 化）
 * - quantize：按业务场景四舍五入（元/千分位/整元）
 * - amountTolerance：按金额规模动态容差
 * - amountEquals：容差等值判断
 *
 * 精度配置：
 * - precision = 28（与后端 Python decimal 默认一致，覆盖 10^15 量级金额 + 0.0001 分位）
 * - rounding = ROUND_HALF_UP（与后端一致，会计/审计标准）
 */
import Decimal from 'decimal.js'

// 全局精度上下文 — 与后端保持一致
Decimal.set({ precision: 28, rounding: Decimal.ROUND_HALF_UP })

/**
 * 金额转换异常（继承 Error，便于 try/catch 区分）。
 */
export class AmountConversionError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'AmountConversionError'
  }
}

/**
 * string/number/null/undefined -> Decimal，统一边界处理。
 *
 * - null/undefined + allowNull=false：抛 AmountConversionError
 * - null/undefined + allowNull=true：返回 null
 * - NaN / Infinity：抛 AmountConversionError
 * - 空字符串、非法字符串：抛 AmountConversionError
 *
 * @param value 待转换值
 * @param allowNull 是否允许 null/undefined（true 时返回 null）
 * @param field 字段名（用于错误消息）
 */
export function toDecimal(
  value: string | number | Decimal | null | undefined,
  allowNull = false,
  field = '金额',
): Decimal | null {
  if (value === null || value === undefined) {
    if (allowNull) return null
    throw new AmountConversionError(`${field} 不能为空`)
  }

  // number 类型先拒绝 NaN/Infinity（Decimal 构造也会报，但提前拦截更清晰）
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) {
      throw new AmountConversionError(`${field} 不能为 NaN 或 Infinity`)
    }
  }

  // 空字符串 / 仅空白 → 非法
  if (typeof value === 'string' && value.trim() === '') {
    throw new AmountConversionError(`${field} 不能为空`)
  }

  let d: Decimal
  try {
    d = value instanceof Decimal ? value : new Decimal(value)
  } catch {
    throw new AmountConversionError(`${field} 格式非法: ${String(value)}`)
  }

  if (d.isNaN() || !d.isFinite()) {
    throw new AmountConversionError(`${field} 不能为 NaN 或 Infinity`)
  }

  return d
}

/**
 * 金额相加，自动 Decimal 化避免浮点误差。
 *
 * - 空参数：返回 Decimal(0)
 * - 任一参数非法（NaN/Infinity）：抛 AmountConversionError
 *
 * @example
 *   addAmount(0.1, 0.2).toString() === '0.3'  // 而 0.1 + 0.2 === 0.30000000000000004
 */
export function addAmount(...values: (string | number | Decimal)[]): Decimal {
  return values.reduce<Decimal>((acc, v) => {
    const d = toDecimal(v, false, '金额')
    return acc.plus(d as Decimal)
  }, new Decimal(0))
}

/**
 * 按业务场景 quantize（四舍五入）。
 *
 * - scale=2：元（0.01）— 默认
 * - scale=4：千分位（0.0001）— 汇率 / 比率
 * - scale=0：整元（部分汇总场景）
 *
 * 使用 ROUND_HALF_UP（与后端会计标准一致）。
 */
export function quantize(value: Decimal | string | number, scale = 2): Decimal {
  const d = toDecimal(value, false, '金额') as Decimal
  return d.toDecimalPlaces(scale, Decimal.ROUND_HALF_UP)
}

/**
 * 按金额规模动态容差（参考后端 amount_tolerance）。
 *
 * 规则:
 *   - amount 为 null/0：tolerance = 0.01（绝对值最小容差）
 *   - |amount| < 1万：tolerance = 0.01（绝对值）
 *   - |amount| ∈ [1万, 100万)：tolerance = |amount| * 0.0001（万分之一）
 *   - |amount| ≥ 100万：tolerance = |amount| * ratio（默认 0.001 千分之一）
 *
 * @param amount 参考金额
 * @param ratio 大金额容差比率（默认 0.001）
 */
export function amountTolerance(
  amount: Decimal | string | number | null | undefined,
  ratio: Decimal | string | number = '0.001',
): Decimal {
  if (amount === null || amount === undefined) {
    return new Decimal('0.01')
  }

  const d = toDecimal(amount, false, '金额') as Decimal
  const absAmount = d.abs()

  // < 1 万
  if (absAmount.lessThan('10000')) {
    return new Decimal('0.01')
  }

  // [1 万, 100 万)
  if (absAmount.lessThan('1000000')) {
    return absAmount.times('0.0001')
  }

  // ≥ 100 万
  return absAmount.times(new Decimal(ratio))
}

/**
 * 容差等值判断：|a - b| <= tolerance(max(|a|, |b|))
 *
 * 容差由两值绝对值的较大者决定，调用 amountTolerance 计算。
 *
 * @example
 *   amountEquals('100.00', '100.005')        // true（小金额 0.01 容差内）
 *   amountEquals('100.00', '100.02')         // false
 *   amountEquals('1000000', '1000999')       // true（百万级千分之一容差）
 */
export function amountEquals(
  a: Decimal | string | number,
  b: Decimal | string | number,
): boolean {
  const da = toDecimal(a, false, '金额') as Decimal
  const db = toDecimal(b, false, '金额') as Decimal
  const diff = da.minus(db).abs()

  // 取两者绝对值较大者作为容差参考
  const ref = Decimal.max(da.abs(), db.abs())
  const tol = amountTolerance(ref)

  return diff.lessThanOrEqualTo(tol)
}
