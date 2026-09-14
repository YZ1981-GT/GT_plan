/**
 * H4 工程物资 — 公式引擎（纯函数，无副作用）
 * 科目：1605工程物资（借方/资产类）
 *
 * 审定口径（冲突决议 C2）：
 * - H4-1 xlsx：审定 = 未审 + 账项调整（单列；前端可拆 AJE/RJE 展示，回写时合并）
 * - calcAuditedAmount(unadj, aje, rje) 第三参保留兼容；H4-1 调用时 rje=0、aje=账项调整净额
 *
 * Spec: .kiro/specs/h4-engineering-materials/
 */

/** 审定数 = 未审数 + AJE调整 + RJE重分类 */
export function calcAuditedAmount(unadj: number, aje: number, rje: number): number {
  return unadj + aje + rje
}

/** 资产类期末余额（借方科目1605）：期末 = 期初 + 借方发生 - 贷方发生 */
export function calcAssetEndBalance(begin: number, debit: number, credit: number): number {
  return begin + debit - credit
}

/**
 * 三角勾稽校验：差额 = 期末 - (期初 + 增加 - 减少)
 * 返回0表示勾稽平衡，非0表示存在差异
 */
export function calcTriangleReconciliation(begin: number, increase: number, decrease: number, end: number): number {
  return end - (begin + increase - decrease)
}

/** 合计 = SUM(数组)；空数组返回0 */
export function calcSubtotal(arr: number[]): number {
  return arr.reduce((a, b) => a + b, 0)
}

/**
 * 差异率(%) = (实际 - 预期) / 预期 × 100
 * 预期为0时：实际也为0返回0，否则返回100（表示完全偏离）
 */
export function calcDiffRate(actual: number, expected: number): number {
  if (expected === 0) return actual === 0 ? 0 : 100
  return (actual - expected) / expected * 100
}

/**
 * 关联价差率(%) = (交易价格 - 市场价格) / 市场价格 × 100
 * 市场价格为0时：交易价格也为0返回0，否则返回100（表示完全偏离）
 */
export function calcPriceDiffRate(transPrice: number, marketPrice: number): number {
  if (marketPrice === 0) return transPrice === 0 ? 0 : 100
  return (transPrice - marketPrice) / marketPrice * 100
}

/**
 * H4-7 可收回金额 ⑤ = MAX(③公允净额, ④预计未来现金流量现值)
 * 对齐源模板 Excel：H = MAX(F, G)
 */
export function calcRecoverableAmount(fairValueNet: number, pvCashFlows: number): number {
  return Math.max(Number(fairValueNet) || 0, Number(pvCashFlows) || 0)
}

/**
 * H4-7 期末应计提减值 ⑥ = MAX(②账面价值 − ⑤可收回金额, 0)
 * 对齐源模板 Excel：I = IF(E>H, E-H, 0)
 * （部分模板表头误写「⑤−②」，以单元格公式为准）
 */
export function calcRequiredProvision(bookValue: number, recoverableAmount: number): number {
  return Math.max((Number(bookValue) || 0) - (Number(recoverableAmount) || 0), 0)
}

/**
 * H4-7 本期应补提/冲回 ⑧ = ⑥ − ⑦
 * 对齐源模板 Excel：K = I − J；CAS8 长期资产减值不得转回，⑧＜0 仅预警不自动冲回
 */
export function calcPeriodImpairmentAdjustment(requiredProvision: number, bookedProvision: number): number {
  return (Number(requiredProvision) || 0) - (Number(bookedProvision) || 0)
}

/**
 * H4-2 单价 = 金额 / 数量。
 * 数量为 0 时返回 null（UI 显示 "-"），避免 Excel 源模板常见的 #DIV/0!。
 */
export function calcUnitPrice(amount: number, quantity: number): number | null {
  const qty = Number(quantity) || 0
  if (qty === 0) return null
  return (Number(amount) || 0) / qty
}

/** H4-2 账面价值 / 净值 = 原值 − 跌价准备 */
export function calcNetBookValue(originalCost: number, impairment: number): number {
  return (Number(originalCost) || 0) - (Number(impairment) || 0)
}

/**
 * H4-2 审定原值期末 = 审定期初 + 审定增加 − 审定减少
 * （与 Excel 第2页「核实情况→审定金额」三角勾稽一致）
 */
export function calcAuditedEndBalance(
  auditedBegin: number,
  auditedIncrease: number,
  auditedDecrease: number,
): number {
  return calcAssetEndBalance(auditedBegin, auditedIncrease, auditedDecrease)
}
