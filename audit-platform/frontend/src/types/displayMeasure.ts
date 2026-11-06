/**
 * 跨层度量合同（design §4.2 / §17 G1、G4）。
 *
 * 与后端 `backend/app/contracts/display_measure.py` 逐值对拍
 * （`backend/tests/test_display_measure_contract.py` 解析本文件常量）。
 *
 * 只有 `amount` 消费金额单位除数；`ratio` 必须同时携带 `ratioScale`，
 * 其他 kind 携带 ratioScale 即为配置错误。
 */

/** 封闭的七类度量语义，顺序即对拍的规范顺序。 */
export const DISPLAY_MEASURE_KINDS = [
  'amount',
  'quantity',
  'count',
  'ratio',
  'exchange_rate',
  'unit_price',
  'text',
] as const

export type DisplayMeasureKind = (typeof DISPLAY_MEASURE_KINDS)[number]

/** 比例尺度：fraction 原值 0.2、percent_points 原值 20，都显示 20.00%。 */
export const RATIO_SCALES = ['fraction', 'percent_points'] as const

export type RatioScale = (typeof RATIO_SCALES)[number]

/** 核心列语义未登记或自相矛盾时的统一机器码。 */
export const DISPLAY_MEASURE_CONTRACT_INVALID = 'DISPLAY_MEASURE_CONTRACT_INVALID'

/** 只有这一类使用金额单位除数。 */
export const AMOUNT_KINDS = ['amount'] as const satisfies readonly DisplayMeasureKind[]

/** 其余 kind 的 divisor 恒为 1。 */
export const NON_AMOUNT_KINDS: readonly DisplayMeasureKind[] = DISPLAY_MEASURE_KINDS.filter(
  (k) => !(AMOUNT_KINDS as readonly DisplayMeasureKind[]).includes(k),
)

export interface DisplayMeasureSpec {
  kind: DisplayMeasureKind
  ratioScale?: RatioScale | null
}

/** 附注/合并附注详情响应里每张表的列语义状态（design §15 A6、§16 F8、§17 G2）。 */
export const MEASURE_STATUSES = ['matched', 'unmatched', 'invalid'] as const
export type MeasureStatus = (typeof MEASURE_STATUSES)[number]

export function isDisplayMeasureKind(v: unknown): v is DisplayMeasureKind {
  return typeof v === 'string' && (DISPLAY_MEASURE_KINDS as readonly string[]).includes(v)
}

export function isRatioScale(v: unknown): v is RatioScale {
  return typeof v === 'string' && (RATIO_SCALES as readonly string[]).includes(v)
}

/** amount 之外的 kind 一律不除金额单位。 */
export function usesAmountDivisor(kind: DisplayMeasureKind | null | undefined): boolean {
  return kind === 'amount'
}

export class DisplayMeasureContractError extends Error {
  readonly code = DISPLAY_MEASURE_CONTRACT_INVALID
  constructor(
    message: string,
    readonly locator?: string,
  ) {
    super(message)
    this.name = 'DisplayMeasureContractError'
  }
}

/**
 * 宽入口：未登记（null/空）返回 null，由调用方走未登记分支；非法组合抛错。
 * `ratio` 缺 scale、非 ratio 带 scale、未知值都是配置错误。
 */
export function buildMeasureSpec(
  kind: unknown,
  ratioScale?: unknown,
  locator?: string,
): DisplayMeasureSpec | null {
  const hasScale = ratioScale !== null && ratioScale !== undefined && ratioScale !== ''
  if (kind === null || kind === undefined || kind === '') {
    if (hasScale) {
      throw new DisplayMeasureContractError('未声明 measureKind 时不允许携带 ratioScale', locator)
    }
    return null
  }
  if (!isDisplayMeasureKind(kind)) {
    throw new DisplayMeasureContractError(`未知 measureKind: ${String(kind)}`, locator)
  }
  if (hasScale && !isRatioScale(ratioScale)) {
    throw new DisplayMeasureContractError(`未知 ratioScale: ${String(ratioScale)}`, locator)
  }
  if (kind === 'ratio') {
    if (!hasScale) {
      throw new DisplayMeasureContractError(
        'kind=ratio 必须同时声明 ratioScale（fraction 或 percent_points）',
        locator,
      )
    }
    return { kind, ratioScale: ratioScale as RatioScale }
  }
  if (hasScale) {
    throw new DisplayMeasureContractError(`kind=${kind} 不允许携带 ratioScale`, locator)
  }
  return { kind, ratioScale: null }
}
