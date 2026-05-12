/**
 * 金额除数注入 key
 * 由父组件 provide，GtAmountCell 通过 inject 获取
 * 用于四表金额单位切换（元/万元/千元）
 */
export const AMOUNT_DIVISOR_KEY = Symbol('amountDivisor')
