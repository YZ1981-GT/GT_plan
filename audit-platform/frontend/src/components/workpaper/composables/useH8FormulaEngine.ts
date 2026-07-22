/**
 * H8 使用权资产 — 公式引擎（纯函数，无副作用）
 * 科目：1901使用权资产（借方/资产类）+ 累计折旧（贷方/备抵类）
 * Spec: .kiro/specs/h8-right-of-use-assets/
 */

// ─── 辅助：安全转数字（NaN/undefined/null → 0） ───────────────────────────────
function safeNum(v: unknown): number {
  if (v === null || v === undefined) return 0
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

/** 审定数 = 未审数 + AJE调整 + RJE重分类 */
export function calcAuditedAmount(unadj: number, aje: number, rje: number): number {
  return safeNum(unadj) + safeNum(aje) + safeNum(rje)
}

/** 资产类期末余额（借方科目1901使用权资产）：期末 = 期初 + 借方发生 - 贷方发生 */
export function calcAssetEndBalance(begin: number, debit: number, credit: number): number {
  return safeNum(begin) + safeNum(debit) - safeNum(credit)
}

/** 备抵类期末余额（累计折旧，贷方/备抵类）：期末 = 期初 + 贷方发生 - 借方发生 */
export function calcContraEndBalance(begin: number, debit: number, credit: number): number {
  return safeNum(begin) + safeNum(credit) - safeNum(debit)
}

/** 净值 = 原值(使用权资产) - 累计折旧 - 减值准备 */
export function calcNetValue(cost: number, accumulatedDepreciation: number, impairment: number): number {
  return safeNum(cost) - safeNum(accumulatedDepreciation) - safeNum(impairment)
}

/**
 * H8-10 减值测算用账面价值② = 原值 − 累计折旧（不含减值准备）
 * 勿与审定净值混淆（净值已扣减值）。
 */
export function calcImpairmentBookValue(cost: number, accumulatedDepreciation: number): number {
  return safeNum(cost) - safeNum(accumulatedDepreciation)
}

/**
 * 有迹象时⑤ = max(③,④)；无减值迹象时返回 0（CAS8：先迹象、后测试）。
 * 注意：与 h8RecoverableModel.calcRecoverableAmount（无闸门）区分。
 */
export function calcImpairmentRecoverableAmount(
  fairValueLessDisposal: number,
  dcfPresentValue: number,
  hasIndication: boolean,
): number {
  if (!hasIndication) return 0
  return Math.max(safeNum(fairValueLessDisposal), safeNum(dcfPresentValue))
}

/**
 * 期末应计提减值⑥ = max(② − ⑤, 0)；无迹象时为 0。
 * （源模板表头曾误写⑥=⑤−②，已纠正）
 */
export function calcRequiredImpairment(
  bookValue: number,
  recoverableAmount: number,
  hasIndication = true,
): number {
  if (!hasIndication) return 0
  return Math.max(safeNum(bookValue) - safeNum(recoverableAmount), 0)
}

/**
 * 本期应补提⑧ = max(⑥ − ⑦, 0)
 * CAS8：减值一经确认不得转回，故结果不为负。
 */
export function calcImpairmentSupplement(required: number, alreadyProvided: number): number {
  return Math.max(safeNum(required) - safeNum(alreadyProvided), 0)
}

/**
 * 多提待查⑨ = max(⑦ − ⑥, 0)
 * 仅提示调查（处置结转遗漏等），禁止做转回分录。
 */
export function calcImpairmentOverProvision(required: number, alreadyProvided: number): number {
  return Math.max(safeNum(alreadyProvided) - safeNum(required), 0)
}

/** 合计行 = 数组求和；空数组返回0 */
export function calcSubtotal(arr: number[]): number {
  if (!Array.isArray(arr) || arr.length === 0) return 0
  return arr.reduce((sum, v) => sum + safeNum(v), 0)
}

/**
 * 审定变动率(%)：对齐致同 Excel
 * - 期初审定=0 且变动=0 → 0
 * - 期初审定=0 且变动≠0 → ±100
 * - 否则 变动额 / |期初审定| × 100
 */
export function calcChangeRate(change: number, beginAudited: number): number | null {
  const c = safeNum(change)
  const b = safeNum(beginAudited)
  if (b === 0 && c === 0) return 0
  if (b === 0) return c > 0 ? 100 : c < 0 ? -100 : 0
  return (c / Math.abs(b)) * 100
}
