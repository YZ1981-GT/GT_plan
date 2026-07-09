/**
 * useL6FormulaEngine — L6 专项应付款公式引擎
 *
 * 纯函数，无副作用、无 Vue reactivity、确定性输出。
 * 科目：2601 专项应付款（**贷方/负债类！**）
 *
 * ─── 负债类方向铁律 ───
 * 负债类（贷方科目）期末余额 = 期初 + 贷方发生（拨入/增加） - 借方发生（结转/返还/减少）
 * 与资产类（借方科目）期末 = 期初 + 借方 - 贷方 **方向相反！**
 * 这是 L 筹资循环 L1~L7 所有底稿的共同规则。
 * ─────────────────────
 *
 * 本引擎覆盖：
 * - 审定数公式链（L6-1 审定表）
 * - 负债类期末余额（贷方科目方向）
 * - 明细表期末余额（按专项项目列示）
 * - 分类小计（数组求和）
 * - 变动额/变动率（期间比较）
 * - 检查比例（已检查/总额）
 */

// ─── helpers ────────────────────────────────────────────────

/** 将 NaN / undefined / null 视为 0 */
function safe(v: unknown): number {
  if (v === null || v === undefined) return 0
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

// ─── 1. 审定数公式链 ────────────────────────────────────────

/**
 * 计算审定数
 * 审定数 = 未审数 + 审计调整(AJE) + 重分类调整(RJE)
 *
 * 来源：L6-1 审定表
 * 与 L3/L4/L5/L7 相同公式，L 循环统一。
 *
 * @param unadjusted - 未审数（trial_balance.unadjusted_amount）
 * @param aje - 审计调整金额（正=调增，负=调减）
 * @param rje - 重分类调整金额
 * @returns 审定数
 */
export function calcAuditedAmount(unadjusted: number, aje: number, rje: number): number {
  return safe(unadjusted) + safe(aje) + safe(rje)
}

// ─── 2. 负债类期末余额（贷方！） ─────────────────────────────

/**
 * 计算负债类科目期末余额（L6-1 审定表）
 *
 * ⚠️ 负债类（贷方科目）方向：
 *   期末 = 期初 + 贷方发生额（拨入/增加） - 借方发生额（结转/返还/减少）
 *
 * 来源：L6-1 审定表
 * 专项应付款贷方增加场景：收到政府专项拨款、科研经费拨入等
 * 专项应付款借方减少场景：项目结转（形成资产/费用化）、退还拨款
 *
 * 与资产类相反！资产类期末 = 期初 + 借方 - 贷方
 * 此为 L 循环（短期借款/长期借款/应付债券/长期应付款/专项应付款/其他非流动负债）共用铁律。
 *
 * @param begin - 期初余额
 * @param credit - 贷方发生额（拨入/增加）
 * @param debit - 借方发生额（结转/返还/减少）
 * @returns 期末余额
 */
export function calcLiabilityEndBalance(begin: number, credit: number, debit: number): number {
  return safe(begin) + safe(credit) - safe(debit)
}

// ─── 3. 分类小计 ────────────────────────────────────────────

/**
 * 数组求和（按专项项目/分类汇总）
 *
 * 用于：
 * - L6-1 审定表按专项项目分类合计
 * - L6-2 明细表各列小计
 * - 合计行
 *
 * @param arr - 待求和的金额数组
 * @returns 合计金额
 */
export function calcSubtotal(arr: number[]): number {
  if (!Array.isArray(arr)) return 0
  let total = 0
  for (const a of arr) {
    total += safe(a)
  }
  return total
}

// ─── 4. 变动额 ─────────────────────────────────────────────

/**
 * 计算变动额
 * 变动额 = 期末审定(current) - 期初审定(prior)
 *
 * 来源：L6-1 审定表变动分析列
 * 正值=本期增加（拨入>结转），负值=本期减少（结转>拨入）
 *
 * @param current - 本期审定数/期末余额
 * @param prior - 上期审定数/期末余额
 * @returns 变动额
 */
export function calcVariance(current: number, prior: number): number {
  return safe(current) - safe(prior)
}

// ─── 5. 变动率 ─────────────────────────────────────────────

/**
 * 计算变动率
 *
 * 公式逻辑（来源L6-1 xlsx K7）：
 *   IF(AND(E7=0, J7=0), 0, IF(AND(E7=0, J7>0), 1, J7/E7))
 * 翻译：
 *   - prior=0 且 variance=0 → 0（无变动）
 *   - prior=0 且 variance>0 → 1（100%增长，用1兜底）
 *   - 其他 → variance / prior（变动比率）
 *
 * 注：这里 variance = current - prior，即 J 列对应变动额
 * prior 对应 E 列（期初审定数）
 *
 * @param current - 本期审定数
 * @param prior - 上期审定数
 * @returns 变动率（小数形式，1=100%）
 */
export function calcVarianceRate(current: number, prior: number): number {
  const c = safe(current)
  const p = safe(prior)
  const variance = c - p
  if (p === 0 && variance === 0) return 0
  if (p === 0 && variance > 0) return 1
  if (p === 0) return variance // prior=0且variance<0，保护性处理（避免除零）
  return variance / p
}

// ─── 6. 明细表期末余额 ─────────────────────────────────────

/**
 * 计算明细表期末余额（L6-2 明细表）
 * 明细期末 = 期初 + 本期拨入 - 本期结转 - 本期返还
 *
 * 来源：L6-2 明细表（负债类贷方科目方向）
 * 本期拨入 = 贷方发生（收到新拨款）
 * 本期结转 = 借方发生之一（项目完工结转形成资产/费用化）
 * 本期返还 = 借方发生之二（退还未使用拨款）
 *
 * 注意：本期结转+本期返还 合计 = 借方发生总额
 * 本质与 calcLiabilityEndBalance 等价（debit = carryForward + refund）
 *
 * @param begin - 期初余额
 * @param creditIn - 本期拨入（贷方）
 * @param carryForward - 本期结转（借方之一：形成资产/费用化）
 * @param refund - 本期返还（借方之二：退还未用拨款）
 * @returns 期末余额
 */
export function calcDetailEndBalance(
  begin: number,
  creditIn: number,
  carryForward: number,
  refund: number
): number {
  return safe(begin) + safe(creditIn) - safe(carryForward) - safe(refund)
}

// ─── 7. 检查比例 ───────────────────────────────────────────

/**
 * 计算检查比例（L6-4 检查表）
 * 检查比例 = 已检查金额 / 本期发生额
 *
 * 公式逻辑：
 *   IF(total=0, 0, checked/total)
 * 含义：当本期发生额为0时，比例记为0（避免除零）
 *
 * @param checked - 已检查金额
 * @param total - 本期发生额（拨入+结转+返还之和）
 * @returns 检查比例（小数形式，0~1+）
 */
export function calcCheckRatio(checked: number, total: number): number {
  const c = safe(checked)
  const t = safe(total)
  if (t === 0) return 0
  return c / t
}

// ─── 8. 跨sheet交叉验证 ────────────────────────────────────

/**
 * 审定表 vs 明细表合计交叉验证
 *
 * 比对审定表L6-1的科目审定合计与明细表L6-2各专项项目期末余额之和，
 * 差额为0表示勾稽一致。
 *
 * @param adjTotal - 审定表合计金额
 * @param detailTotal - 明细表各项目期末余额之和
 * @returns { diff: 差额, isMatch: 是否一致 }
 */
export function validateAdjudicationVsDetail(
  adjTotal: number,
  detailTotal: number
): { diff: number; isMatch: boolean } {
  const d = safe(adjTotal) - safe(detailTotal)
  return { diff: d, isMatch: d === 0 }
}

// ─── Composable convenience wrapper ────────────────────────

/**
 * useL6FormulaEngine — 便捷组合式函数包装器
 *
 * 将所有纯函数打包返回，便于组件内解构使用。
 * 纯转发，无额外逻辑。
 */
export function useL6FormulaEngine() {
  return {
    calcAuditedAmount,
    calcLiabilityEndBalance,
    calcSubtotal,
    calcVariance,
    calcVarianceRate,
    calcDetailEndBalance,
    calcCheckRatio,
    validateAdjudicationVsDetail,
  }
}
