/**
 * useL7FormulaEngine — L7 其他非流动负债公式引擎
 *
 * 纯函数，无副作用、无 Vue reactivity、确定性输出。
 * 科目：2801 其他非流动负债（**贷方/负债类！**）
 *
 * ─── 负债类方向铁律 ───
 * 负债类（贷方科目）期末余额 = 期初 + 贷方发生（增加） - 借方发生（减少）
 * 与资产类（借方科目）期末 = 期初 + 借方 - 贷方 **方向相反！**
 * 这是 L 筹资循环 L1~L7 所有底稿的共同规则。
 * ─────────────────────
 *
 * 本引擎覆盖：
 * - 审定数公式链（L7-1 审定表）
 * - 负债类期末余额（贷方科目方向）
 * - 明细表期末余额（按项目列示）
 * - 分类小计（数组求和）
 * - 变动额/变动率（期间比较）
 * - 跨sheet交叉验证（审定 vs 明细）
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
 * 来源：L7-1 审定表
 * 与 L3/L4/L5 相同公式，L 循环统一。
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
 * 计算负债类科目期末余额（L7-1 审定表 + L7-2 明细表）
 *
 * ⚠️ 负债类（贷方科目）方向：
 *   期末 = 期初 + 贷方发生额（增加） - 借方发生额（减少）
 *
 * 来源：L7-1 审定表
 * 其他非流动负债贷方增加场景：新增递延收益/保证金/押金等
 * 其他非流动负债借方减少场景：到期退还/结转/核销
 *
 * 与资产类相反！资产类期末 = 期初 + 借方 - 贷方
 * 此为 L 循环（短期借款/长期借款/应付债券/长期应付款/其他非流动负债）共用铁律。
 *
 * @param begin - 期初余额
 * @param credit - 贷方发生额（增加）
 * @param debit - 借方发生额（减少）
 * @returns 期末余额
 */
export function calcLiabilityEndBalance(begin: number, credit: number, debit: number): number {
  return safe(begin) + safe(credit) - safe(debit)
}

// ─── 3. 分类小计 ────────────────────────────────────────────

/**
 * 数组求和（按项目/分类汇总）
 *
 * 用于：
 * - L7-1 审定表按项目分类合计
 * - L7-2 明细表列小计
 * - 各列合计行
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
 * 变动额 = 本期数(current) - 上期数(previous)
 *
 * 来源：L7-1 审定表变动分析列
 * 正值=本期增加，负值=本期减少
 *
 * @param current - 本期审定数/期末余额
 * @param previous - 上期审定数/期末余额
 * @returns 变动额
 */
export function calcVariance(current: number, previous: number): number {
  return safe(current) - safe(previous)
}

// ─── 5. 变动率 ─────────────────────────────────────────────

/**
 * 计算变动率
 *
 * 公式逻辑（来源xlsx）：
 *   IF(AND(E=0, J=0), 0, IF(AND(E=0, J>0), 1, J/E))
 * 翻译：
 *   - 上期=0 且 本期=0 → 0（无变动）
 *   - 上期=0 且 本期>0 → 1（100%增长）
 *   - 其他 → 本期/上期（变动比率）
 *
 * 注意：这里 previous 对应 E列(上期)，current 对应 J列(本期)
 *
 * @param current - 本期审定数
 * @param previous - 上期审定数
 * @returns 变动率（小数形式，1=100%）
 */
export function calcVarianceRate(current: number, previous: number): number {
  const c = safe(current)
  const p = safe(previous)
  if (p === 0 && c === 0) return 0
  if (p === 0 && c > 0) return 1
  if (p === 0) return c / 1 // 上期=0且本期<0，按xlsx公式逻辑 J/E 会产生 -Infinity，这里保护性处理
  return c / p
}

// ─── 6. 明细表期末余额 ─────────────────────────────────────

/**
 * 计算明细表期末余额
 * 明细表期末 = 期初 + 本期增加 - 本期减少
 *
 * 来源：L7-2 明细表（与负债类主公式同方向）
 * 本期增加 = 贷方发生（新增负债项目）
 * 本期减少 = 借方发生（到期/退还/核销）
 *
 * 本质与 calcLiabilityEndBalance 相同，语义不同：
 * - calcLiabilityEndBalance 用于审定表（借/贷科目维度）
 * - calcDetailEndBalance 用于明细表（增加/减少业务维度）
 *
 * @param begin - 期初余额
 * @param increase - 本期增加
 * @param decrease - 本期减少
 * @returns 期末余额
 */
export function calcDetailEndBalance(begin: number, increase: number, decrease: number): number {
  return safe(begin) + safe(increase) - safe(decrease)
}

// ─── 7. 跨sheet交叉验证 ────────────────────────────────────

/**
 * 审定表 vs 明细表合计交叉验证
 *
 * 比对审定表的科目审定合计与明细表各项目期末余额之和，
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
