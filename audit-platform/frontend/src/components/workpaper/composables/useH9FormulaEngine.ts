/**
 * H9 租赁负债 — 公式引擎（纯函数，无副作用）
 * 科目：2205租赁负债（贷方/负债类）+ 未确认融资费用（借方/负债备抵类）
 * ⚠️ 负债类贷方科目：期末=期初+贷方-借方（与资产类 H1~H8 相反！）
 * Spec: .kiro/specs/h9-lease-liabilities/
 * Requirements: 2.3-2.5
 */

/**
 * 审定数 = 未审数 + AJE调整 + RJE重分类
 * Source: H9-1 审定数 D=B+C (未审+调整); I=G+H (期末审定=未审+AJE)
 */
export function calcAuditedAmount(unadj: number, aje: number, rje: number): number {
  return unadj + aje + rje
}

/**
 * 负债类期末余额（贷方科目2205租赁负债）：期末 = 期初 + 贷方发生(增加) - 借方发生(减少)
 * ⚠️ CRITICAL: 与资产类相反！负债增加在贷方、减少在借方
 * Source: H9-2 E=B-C+D 重构为 end=begin+credit-debit
 *         H9-1 审定期末 L=I-J+K (审定期初-审定借+审定贷)
 */
export function calcLiabilityEndBalance(begin: number, credit: number, debit: number): number {
  return begin + credit - debit
}

/**
 * 备抵类期末余额（借方/负债备抵：未确认融资费用）：期末 = 期初 + 借方发生 - 贷方发生
 * 未确认融资费用是负债的备抵科目，余额在借方，增加在借方、减少（摊销确认）在贷方
 * Source: H9-3 E=B+C-D (借方备抵: 期初+借-贷)
 *         H9-3 审定期末 M=J+K-L
 */
export function calcContraLiabilityEndBalance(begin: number, debit: number, credit: number): number {
  return begin + debit - credit
}

/**
 * 净额 = 租赁负债原值 - 未确认融资费用
 * 即账面上的租赁负债净额（附注披露金额）
 * Source: H9-1 row18=row8-row13 (原值-未确认融资费用)
 */
export function calcNetLiability(liability: number, unearnedFinanceCost: number): number {
  return liability - unearnedFinanceCost
}

/**
 * 报表数 = 审定数 − 重分类至一年内到期
 * Source: H9-1 F=D-E / K=I-J
 */
export function calcFsAmount(audited: number, reclassification: number): number {
  return audited - reclassification
}

/**
 * 本期审定 vs 上期审定：变动额 = 期末报表数 − 期初报表数
 * Source: H9-1 L=K-F
 */
export function calcChangeAmount(endFs: number, beginFs: number): number {
  return endFs - beginFs
}

/**
 * 变动率：对齐 Excel H9-1 M列
 * IF(期初=0且变动=0)→0；IF(期初=0且变动>0)→1；否则 变动/期初
 * 返回小数（0.3 = 30%），UI 再格式化为百分比
 */
export function calcChangeRate(beginFs: number, changeAmt: number): number {
  if (beginFs === 0 && changeAmt === 0) return 0
  if (beginFs === 0 && changeAmt > 0) return 1
  if (beginFs === 0) return changeAmt < 0 ? -1 : 1
  return changeAmt / beginFs
}

/**
 * 到期日分析四档合计应等于最终审定（±1 元容差）
 */
export function calcMaturityBucketsSum(
  within1Y: number,
  y1to2: number,
  y2to3: number,
  over3Y: number,
): number {
  return within1Y + y1to2 + y2to3 + over3Y
}

/**
 * 合计 = SUM(数组)；空数组返回0
 * Source: H9-1 row11=SUM(row8:row10), H9-2 row14=SUM(9:13), etc.
 */
export function calcSubtotal(arr: number[]): number {
  return arr.reduce((a, b) => a + b, 0)
}

/**
 * 价差率(%) = (实际租金 - 市场租金) / 市场租金 × 100
 * 用于H9-6关联交易检查表，评估关联方租赁价格公允性
 * 当market=0时返回0避免除零
 * Source: Requirement 5.3 (关联交易价差率)
 */
export function calcPriceDiffRate(actual: number, market: number): number {
  if (market === 0) return 0
  return (actual - market) / market * 100
}
