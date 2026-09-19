/**
 * 披露内部勾稽 —— 平台共用原语
 *
 * 各循环的勾稽**规则**必须逐条取自源模板公式（禁自造校验），但「怎么比、怎么汇总、
 * 缺数据怎么表达」是共性的，收在这里避免每个循环各写一份 `eqCheck`。
 *
 * 设计约束（起源于 H1 / N1 两轮实践）：
 * - 容差 **0.01 元**（源模板金额保留 2 位小数）
 * - 任一侧 `null`（未取到）→ `level='skip'`，**不误报**（跨底稿取数未就绪时不判定）
 * - 两侧同为 `null` 也是 skip：此时"相等"不构成有效结论
 * - 纯函数：不依赖 Vue / DOM，可单测与 PBT
 *
 * spec: `n-cycle-tax-disclosure-alignment` Task 7.1（自 `n1DisclosureConsistency` 提取）
 */

/** 金额比较容差（元） */
export const WP_CHECK_TOLERANCE = 0.01

export type WpCheckLevel = 'ok' | 'warn' | 'error' | 'skip'

export type NullableAmount = number | null

export interface WpCheckResult {
  /** 规则短名（展示用） */
  label: string
  /** 规则说明（tooltip，须含源模板公式出处） */
  rule: string
  left: NullableAmount
  right: NullableAmount
  /** left − right；任一侧 null 时为 null */
  diff: NullableAmount
  level: WpCheckLevel
  /** 追溯索引（`GtIndexChip` 用） */
  refs?: string[]
}

/** 可空求和：全为 null 时返回 null（不塌成 0） */
export function sumNullable(vals: readonly NullableAmount[]): NullableAmount {
  let has = false
  let total = 0
  for (const v of vals) {
    if (v === null || v === undefined || !Number.isFinite(v)) continue
    has = true
    total += v
  }
  return has ? Math.round(total * 100) / 100 : null
}

/** 数值归一：非有限数（含 undefined / 空串 / NaN）→ null */
export function nz(v: unknown): NullableAmount {
  return typeof v === 'number' && Number.isFinite(v) ? v : null
}

/**
 * 相等类校验。任一侧 `null` → skip（未取到不报错）。
 */
export function eqCheck(
  label: string,
  rule: string,
  left: NullableAmount,
  right: NullableAmount,
  refs?: string[],
): WpCheckResult {
  if (left === null || left === undefined || right === null || right === undefined) {
    return { label, rule, left: left ?? null, right: right ?? null, diff: null, level: 'skip', refs }
  }
  const diff = Math.round((left - right) * 100) / 100
  return {
    label,
    rule,
    left,
    right,
    diff,
    level: Math.abs(diff) <= WP_CHECK_TOLERANCE ? 'ok' : 'error',
    refs,
  }
}

/**
 * 段小计校验：`小计 == 段内明细之和`。
 *
 * 段内**无明细行**时返回 `null`（不产出该条）—— 空段的小计可能来自跨底稿取数，
 * 不是"明细之和"，硬校验会误报。
 */
export function segmentSumCheck(
  label: string,
  rule: string,
  details: readonly NullableAmount[] | undefined,
  subtotal: NullableAmount,
  refs?: string[],
): WpCheckResult | null {
  if (!details || details.length === 0) return null
  return eqCheck(label, rule, subtotal, sumNullable(details), refs)
}

export interface WpCheckSummary {
  total: number
  ok: number
  error: number
  skip: number
  /** 全部为 ok（且至少 1 条）→ true；空结果不算通过 */
  allPassed: boolean
}

export function summarizeChecks(results: readonly WpCheckResult[]): WpCheckSummary {
  const ok = results.filter((r) => r.level === 'ok').length
  const error = results.filter((r) => r.level === 'error').length
  const skip = results.filter((r) => r.level === 'skip' || r.level === 'warn').length
  return { total: results.length, ok, error, skip, allPassed: error === 0 && ok > 0 }
}
