/**
 * H5 油气资产 — 公式引擎（纯函数，无副作用）
 * 科目：1611油气资产（借方/资产类）+ 累计折耗（贷方/备抵类）
 * 特征：折耗（非折旧）使用单位产量法；行业限制 oil_gas/mining
 * Spec: .kiro/specs/h5-oil-gas-assets/
 *
 * 边界约定：
 *  - 所有函数输入若为 NaN → 视为 0
 *  - 除法分母为 0 → 返回 0（不抛异常）
 */

// ─── 辅助 ───────────────────────────────────────────────────────────────────────

/** 将 NaN/undefined/null 安全转为 0 */
function safe(v: number): number {
  return Number.isFinite(v) ? v : 0
}

// ─── 公式函数 ─────────────────────────────────────────────────────────────────

/**
 * 审定数 = 未审数 + AJE调整 + RJE重分类
 * Requirements: 2.3
 */
export function calcAuditedAmount(unadj: number, aje: number, rje: number): number {
  return safe(unadj) + safe(aje) + safe(rje)
}

/**
 * 资产类期末余额（借方科目1611油气资产）
 * 期末 = 期初 + 借方发生 - 贷方发生
 * Requirements: 2.4
 */
export function calcAssetEndBalance(begin: number, debit: number, credit: number): number {
  return safe(begin) + safe(debit) - safe(credit)
}

/**
 * 备抵类期末余额（贷方科目 累计折耗）
 * 期末 = 期初 + 贷方发生 - 借方发生
 * Requirements: 2.5
 */
export function calcContraEndBalance(begin: number, debit: number, credit: number): number {
  return safe(begin) + safe(credit) - safe(debit)
}

/**
 * 三角勾稽差额 = end - (begin + increase - decrease)
 * 返回 0 表示恒等（勾稽平衡），非 0 表示存在差异
 * Requirements: 2.6
 */
export function calcTriangleReconciliation(
  begin: number,
  increase: number,
  decrease: number,
  end: number,
): number {
  return safe(end) - (safe(begin) + safe(increase) - safe(decrease))
}

/**
 * 净值 = 原值 - 累计折耗 - 减值准备
 * Requirements: 8.4
 */
export function calcNetValue(cost: number, accDepletion: number, impairment: number): number {
  return safe(cost) - safe(accDepletion) - safe(impairment)
}

/**
 * 合计 = Σarr；空数组返回 0
 * Requirements: 2.6
 */
export function calcSubtotal(arr: number[]): number {
  if (!arr || arr.length === 0) return 0
  return arr.reduce((sum, v) => sum + safe(v), 0)
}

/**
 * 变动率(%) = (本期 - 上期) / |上期| × 100
 * 上期为 0 时返回 0
 * Requirements: 2.6
 */
export function calcChangeRate(current: number, prior: number): number {
  const p = safe(prior)
  if (p === 0) return 0
  return ((safe(current) - p) / Math.abs(p)) * 100
}

/**
 * 价差率(%) = (交易价格 - 市场价格) / 市场价格 × 100
 * 市场价格为 0 时返回 0
 * Requirements: 8.4
 */
export function calcPriceDiffRate(transPrice: number, marketPrice: number): number {
  const mp = safe(marketPrice)
  if (mp === 0) return 0
  return ((safe(transPrice) - mp) / mp) * 100
}

/**
 * 租赁收益率(%) = 年租金收入 / 资产净值 × 100
 * 净值为 0 时返回 0
 * Requirements: 11.1
 */
export function calcLeaseReturnRate(annualRent: number, netValue: number): number {
  const nv = safe(netValue)
  if (nv === 0) return 0
  return (safe(annualRent) / nv) * 100
}
