/**
 * useL1FormulaEngine — L1 短期借款公式引擎
 *
 * 纯函数，无副作用、无 Vue reactivity、确定性输出。
 * 科目：2001 短期借款（**贷方/负债类！**）
 *
 * ─── 负债类方向铁律 ───
 * 负债类（贷方科目）期末余额 = 期初 + 贷方发生（借入）- 借方发生（归还）
 * 与资产类（借方科目）期末 = 期初 + 借方 - 贷方 **方向相反！**
 * 这是 L 筹资循环 L1~L7 所有底稿的共同规则。
 * ─────────────────────
 */

// ─── 1. 审定数公式链 ────────────────────────────────────────

/**
 * 计算审定数
 * 审定数 = 未审数 + 审计调整(AJE) + 重分类调整(RJE)
 *
 * @param unadjusted - 未审数（trial_balance.unadjusted_amount）
 * @param aje - 审计调整金额（正=调增，负=调减）
 * @param rje - 重分类调整金额
 * @returns 审定数
 */
export function calcAuditedAmount(unadjusted: number, aje: number, rje: number): number {
  return unadjusted + aje + rje
}

// ─── 2. 负债类期末余额（贷方！） ─────────────────────────────

/**
 * 计算负债类科目期末余额
 *
 * ⚠️ 负债类（贷方科目）方向：
 *   期末 = 期初 + 贷方发生额（借入/增加） - 借方发生额（归还/减少）
 *
 * 与资产类相反！资产类期末 = 期初 + 借方 - 贷方
 * 此为 L 循环（短期借款/长期借款/应付债券等）共用铁律。
 *
 * @param beginning - 期初余额
 * @param credit - 贷方发生额（借入/增加）
 * @param debit - 借方发生额（归还/减少）
 * @returns 期末余额
 */
export function calcLiabilityEndBalance(beginning: number, credit: number, debit: number): number {
  return beginning + credit - debit
}

// ─── 3. 分类小计 ────────────────────────────────────────────

/**
 * 按分类汇总金额（如按借款类型：信用/保证/抵押/质押分类小计）
 *
 * @param amounts - 待求和的金额数组
 * @returns 合计金额
 */
export function calcSubtotal(amounts: number[]): number {
  let total = 0
  for (const a of amounts) {
    total += a
  }
  return total
}

// ─── 4. 征信差异 ────────────────────────────────────────────

/**
 * 计算征信报告余额与账面余额的差异
 *
 * 差异 = 征信倒轧余额 - 账面余额
 * 差异≠0 时需红色高亮并要求填写差异说明（完整性认定核心控制）
 *
 * @param creditBalance - 征信倒轧余额（报表日）
 * @param bookBalance - 账面借款余额
 * @returns 差异金额（正=征信大于账面，可能有未入账借款）
 */
export function calcCreditDiff(creditBalance: number, bookBalance: number): number {
  return creditBalance - bookBalance
}

// ─── 5. 担保比例 ────────────────────────────────────────────

/**
 * 计算担保比例（抵质押贷款额 / 资产账面净值 × 100）
 *
 * 含义：担保覆盖率 — 贷款额占抵质押资产净值的百分比
 * - 比例 > 100% 表示贷款超过担保资产价值（风险！）
 * - 比例 < 100% 表示资产价值覆盖贷款
 *
 * 边界：当 assetNetValue = 0 时返回 0（除零保护）
 * 注：实务中资产净值为0说明资产已全额折旧/摊销，此时担保无实质意义，
 * 返回0而非Infinity以避免UI显示异常，审计人员应人工关注此情形。
 *
 * @param guaranteedLoan - 抵质押贷款额
 * @param assetNetValue - 抵质押资产账面净值（= 原值 - 折旧/摊销）
 * @returns 担保比例（百分比），如 150 表示 150%
 */
export function calcPledgeRatio(guaranteedLoan: number, assetNetValue: number): number {
  if (assetNetValue === 0) return 0
  return (guaranteedLoan / assetNetValue) * 100
}

// ─── 6. 征信倒轧余额 ───────────────────────────────────────

/**
 * 计算报表日征信倒轧余额
 *
 * 公式：报表日倒轧余额 = 查询日余额 + 增加金额 - 减少金额
 * 来源：L1-4 征信核对表 xlsx 公式 P11: =J11+N11-O11
 *
 * 含义：征信报告查询日（如2025-01-15）到报表日（如2024-12-31）之间，
 * 用增减金额倒轧出报表日应有的余额，用于与账面对比。
 *
 * @param queryBalance - 征信查询日余额
 * @param increase - 查询日到报表日增加金额（贷方）
 * @param decrease - 查询日到报表日减少金额（借方）
 * @returns 报表日倒轧余额
 */
export function calcCreditRollForward(queryBalance: number, increase: number, decrease: number): number {
  return queryBalance + increase - decrease
}
