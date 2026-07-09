/**
 * useM10FormulaEngine — M10 其他权益工具公式引擎
 *
 * 纯函数，无副作用、无 Vue reactivity、确定性输出。
 * 科目：4003 其他权益工具（**贷方/权益类！**）
 *
 * ─── 权益类贷方方向铁律 ───
 * 其他权益工具是所有者权益的正常科目（贷方余额）。
 * 期末余额 = 期初 + 贷方发生（发行增加） - 借方发生（赎回/转换减少）
 *
 * ⚠️ 与M3库存股（借方备抵）方向相反！
 *   M10其他权益工具（贷方权益）：期末 = 期初 + 贷方 - 借方
 *   M3库存股（借方备抵）：      期末 = 期初 + 借方 - 贷方
 * ─────────────────────────────────────
 *
 * 科目4003其他权益工具业务特征（CAS37《金融工具列报》）：
 * - 永续债发行 → 贷方增加（借:银行存款 贷:其他权益工具）
 * - 优先股发行 → 贷方增加（借:银行存款 贷:其他权益工具）
 * - 赎回/转换 → 借方减少（借:其他权益工具 贷:银行存款/实收资本）
 * - 期末 = 期初 + 贷方(发行) - 借方(赎回/转换)
 *
 * 本引擎覆盖：
 * - P1: 审定数公式链（M10-1 审定表）
 * - P2: 权益类贷方期末余额
 * - P6: 分类小计（数组求和）
 * - 变动额/变动率（M10-1 审定表比较列）
 * - 净发行额/明细期末（M10-2 明细表）
 *
 * Spec: .kiro/specs/m10-other-equity-instruments/ Task 2.1
 * Requirements: 2.3-2.4, 6.4
 */

// ─── helpers ────────────────────────────────────────────────

/** 将 NaN / undefined / null 视为 0 */
function safe(v: unknown): number {
  if (v === null || v === undefined) return 0
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

// ─── P1: 审定数公式链 ───────────────────────────────────────

/**
 * 计算审定数（Property P1）
 * 审定数 = 未审数 + 审计调整(AJE) + 重分类调整(RJE)
 *
 * 来源：M10-1 审定表
 * M循环所有科目审定公式统一。
 *
 * @param unadjusted - 未审数（trial_balance.unadjusted_amount）
 * @param aje - 审计调整金额（正=调增，负=调减）
 * @param rje - 重分类调整金额
 * @returns 审定数
 */
export function calcAuditedAmount(unadjusted: number, aje: number, rje: number): number {
  return safe(unadjusted) + safe(aje) + safe(rje)
}

// ─── P2: 权益类贷方期末余额 ─────────────────────────────────

/**
 * 计算权益类科目期末余额（Property P2）
 *
 * ⚠️⚠️⚠️ 权益类贷方科目方向：
 *   期末 = 期初 + 贷方发生额（发行增加） - 借方发生额（赎回/转换减少）
 *
 * 来源：M10-1 审定表 + M10-2 明细表
 * 其他权益工具贷方增加场景：
 *   - 永续债发行（借:银行存款 贷:其他权益工具）
 *   - 优先股发行（借:银行存款 贷:其他权益工具）
 * 其他权益工具借方减少场景：
 *   - 赎回（借:其他权益工具 贷:银行存款）
 *   - 转换为普通股（借:其他权益工具 贷:实收资本/资本公积）
 *
 * ⚠️ 与M3库存股（借方备抵类）方向相反！
 *   M10权益类：期末 = 期初 + 贷方(发行) - 借方(赎回/转换)
 *   M3备抵类：期末 = 期初 + 借方(回购) - 贷方(注销)
 *
 * @param begin - 期初余额（贷方余额）
 * @param credit - 贷方发生额（发行增加）
 * @param debit - 借方发生额（赎回/转换减少）
 * @returns 期末余额（贷方余额）
 */
export function calcEquityEndBalance(begin: number, credit: number, debit: number): number {
  return safe(begin) + safe(credit) - safe(debit)
}

// ─── P6: 分类小计 ───────────────────────────────────────────

/**
 * 数组求和（按工具类型分类汇总）（Property P6）
 *
 * 用于：
 * - M10-1 审定表按工具类型（永续债/优先股/其他）分类合计
 * - M10-2 明细表列小计
 * - M10-4 区分检查表核对合计行
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

// ─── 变动额（M10-1 审定表比较列） ───────────────────────────

/**
 * 计算变动额
 * 变动额 = 期末审定数 - 期初审定数
 *
 * 来源：M10-1 审定表 J列（=I-E）
 *
 * @param endAudited - 期末审定数
 * @param beginAudited - 期初审定数
 * @returns 变动额
 */
export function calcVariance(endAudited: number, beginAudited: number): number {
  return safe(endAudited) - safe(beginAudited)
}

// ─── 变动率（M10-1 审定表比较列） ───────────────────────────

/**
 * 计算变动率
 *
 * 来源：M10-1 审定表 K列
 * 公式：=IF(AND(期初=0,期末=0),"",IF(AND(期初=0,期末>0),1,(期末-期初)/期初))
 *
 * - 期初=0 且 期末=0 → null（不显示）
 * - 期初=0 且 期末>0 → 1（100%）
 * - 其他 → (期末-期初)/期初
 *
 * @param beginAudited - 期初审定数
 * @param endAudited - 期末审定数
 * @returns 变动率（小数），或 null 表示不适用
 */
export function calcVarianceRate(beginAudited: number, endAudited: number): number | null {
  const b = safe(beginAudited)
  const e = safe(endAudited)
  if (b === 0 && e === 0) return null
  if (b === 0 && e > 0) return 1
  return (e - b) / b
}

// ─── 净发行额（M10-2 明细表） ────────────────────────────────

/**
 * 计算净发行额
 * 净发行额 = 发行总额 - 发行费用
 *
 * 来源：M10-2 明细表
 * 永续债/优先股发行时需扣除承销费等发行费用。
 *
 * @param grossIssuance - 发行总额
 * @param issuanceCost - 发行费用（承销费、法律费等）
 * @returns 净发行额
 */
export function calcNetIssuance(grossIssuance: number, issuanceCost: number): number {
  return safe(grossIssuance) - safe(issuanceCost)
}

// ─── 明细期末余额（M10-2 明细表） ────────────────────────────

/**
 * 计算明细表期末余额
 * 明细期末 = 期初 + 本期发行(净额) - 本期赎回/转换
 *
 * 来源：M10-2 明细表（权益类贷方方向：+发行-赎回）
 * 与 calcEquityEndBalance 逻辑一致，但语义针对单项工具明细。
 *
 * @param begin - 期初余额
 * @param issuance - 本期发行额（净额，已扣发行费用）
 * @param reduction - 本期减少额（赎回/转换）
 * @returns 期末余额
 */
export function calcDetailEndBalance(begin: number, issuance: number, reduction: number): number {
  return safe(begin) + safe(issuance) - safe(reduction)
}

// ─── composable wrapper ─────────────────────────────────────

/**
 * useM10FormulaEngine composable 包装
 *
 * 提供所有纯函数的统一导出，保持与其他底稿composable命名一致。
 * 核心函数直接 export 供 PBT 直接引用。
 */
export function useM10FormulaEngine() {
  return {
    calcAuditedAmount,
    calcEquityEndBalance,
    calcSubtotal,
    calcVariance,
    calcVarianceRate,
    calcNetIssuance,
    calcDetailEndBalance,
  }
}
