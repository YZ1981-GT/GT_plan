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

/** 合计行 = 数组求和；空数组返回0 */
export function calcSubtotal(arr: number[]): number {
  if (!Array.isArray(arr) || arr.length === 0) return 0
  return arr.reduce((sum, v) => sum + safeNum(v), 0)
}
