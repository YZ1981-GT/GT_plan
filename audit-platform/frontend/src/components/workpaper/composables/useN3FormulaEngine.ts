/**
 * useN3FormulaEngine — N3 递延所得税负债公式引擎（负债类！期末余额）
 *
 * 纯函数，无副作用、无 Vue reactivity、确定性输出。
 * 科目：2901 递延所得税负债（**贷方/负债类科目**）
 *
 * ─── 负债类方向铁律 ───
 * 负债类（贷方科目）期末余额 = 期初 + 贷方发生（确认/增加）- 借方发生（转回/减少）
 * 与资产类（借方科目）期末 = 期初 + 借方 - 贷方 **方向相反！**
 *
 * 2901递延所得税负债是负债类贷方科目：
 *   - 贷方增加（确认递延税负债）：借:所得税费用-递延 贷:递延所得税负债
 *   - 借方减少（转回递延税负债）：借:递延所得税负债 贷:所得税费用-递延
 *   - 期末 = 期初 + 贷方(确认) - 借方(转回)
 *
 * 这是 N 税费循环负债类科目共用规则（N2应交税费/N3递延税负债）。
 * ─────────────────────────────────────
 *
 * 本引擎覆盖：
 * - P1: 审定数公式链（N3-1 审定表）
 * - P2: 负债类贷方期末余额（期初+贷-借）
 * - P5: 合计行恒等（数组求和）
 * - 占比计算（单项/合计）
 * - 变动额（期末-期初）
 * - 变动率（xlsx公式模式 =IF(AND(B7=0,J7=0),0,IF(AND(B7=0,J7>0),1,J7/B7))）
 *
 * Spec: .kiro/specs/n3-deferred-tax-liabilities/ Task 2.1
 * Requirements: 1.5, 2.3, 2.4, 6.6
 */

// ─── helpers ────────────────────────────────────────────────

/**
 * 安全数值解析：null/undefined/NaN/空→0
 *
 * @param val - 任意输入值
 * @returns 有效数字，无效时返回0
 */
export function parseNum(val: string | number | null | undefined): number {
  if (val === null || val === undefined || val === '') return 0
  const n = typeof val === 'number' ? val : Number(val)
  return Number.isFinite(n) ? n : 0
}

// ─── P1: 审定数公式链 ───────────────────────────────────────

/**
 * 计算审定数（Property P1）
 *
 * 审定数 = 未审数 + 审计调整(AJE) + 重分类调整(RJE)
 *
 * 来源：N3-1 审定表
 * N循环所有科目审定公式统一（资产/负债/损益类均相同）。
 *
 * @param unadjusted - 未审数（trial_balance.unadjusted_amount）
 * @param aje - 审计调整金额（正=调增，负=调减）
 * @param rje - 重分类调整金额
 * @returns 审定数
 */
export function calcAuditedAmount(unadjusted: number, aje: number, rje: number): number {
  return parseNum(unadjusted) + parseNum(aje) + parseNum(rje)
}

// ─── P2: 负债类期末余额（贷方！） ──────────────────────────

/**
 * 计算负债类科目期末余额（Property P2）
 *
 * ⚠️⚠️⚠️ 负债类（贷方科目）方向：
 *   期末 = 期初 + 贷方发生额（确认/增加） - 借方发生额（转回/减少）
 *
 * 来源：N3-1 审定表
 * 2901递延所得税负债贷方增加场景：
 *   - 确认递延所得税负债（应纳税暂时性差异增加）：
 *     借:所得税费用-递延 贷:递延所得税负债
 * 2901递延所得税负债借方减少场景：
 *   - 转回递延所得税负债（应纳税暂时性差异减少）：
 *     借:递延所得税负债 贷:所得税费用-递延
 *
 * ⚠️ 与资产类方向相反！
 *   N3负债类：期末 = 期初 + 贷方(确认) - 借方(转回)
 *   N1资产类：期末 = 期初 + 借方(确认) - 贷方(转回)
 *
 * @param begin - 期初余额（贷方余额）
 * @param credit - 贷方发生额（确认/增加）
 * @param debit - 借方发生额（转回/减少）
 * @returns 期末余额（贷方余额）
 */
export function calcLiabilityEndBalance(begin: number, credit: number, debit: number): number {
  return parseNum(begin) + parseNum(credit) - parseNum(debit)
}

// ─── P5: 合计行恒等 ────────────────────────────────────────

/**
 * 数组求和（Property P5）
 *
 * 用于：
 * - N3-1 审定表各应纳税暂时性差异项目合计
 * - N3-2 明细表各列合计行
 * - 递延所得税负债合计
 *
 * @param arr - 待求和的金额数组
 * @returns 合计金额
 */
export function calcSubtotal(arr: number[]): number {
  if (!Array.isArray(arr)) return 0
  let total = 0
  for (const v of arr) {
    total += parseNum(v)
  }
  return total
}

// ─── 占比计算 ───────────────────────────────────────────────

/**
 * 计算单项占合计比例
 *
 * 公式：占比 = item / total
 * 合计为0时返回0（除零保护）。
 *
 * 用于：
 * - N3-2 明细表各项递延税负债占合计比例
 * - N3-1 审定表各暂时性差异项目占比
 *
 * @param item - 单项金额
 * @param total - 合计金额
 * @returns 占比（小数形式，如0.25表示25%）
 */
export function calcProportion(item: number, total: number): number {
  const t = parseNum(total)
  const i = parseNum(item)
  if (t === 0) return 0
  return i / t
}

// ─── 变动额 ─────────────────────────────────────────────────

/**
 * 计算变动额
 *
 * 变动额 = 期末 - 期初
 *
 * 用于：
 * - N3-1 审定表本期变动额（供N5递延所得税费用核对）
 * - N3-2 明细表各项递延税负债本期增减
 *
 * @param end - 期末金额
 * @param begin - 期初金额
 * @returns 变动额（正=净增加，负=净减少）
 */
export function calcChange(end: number, begin: number): number {
  return parseNum(end) - parseNum(begin)
}

// ─── 变动率（xlsx公式模式） ─────────────────────────────────

/**
 * 计算变动率
 *
 * 匹配 xlsx 公式：=IF(AND(B7=0,J7=0),0,IF(AND(B7=0,J7>0),1,J7/B7))
 *
 * 逻辑：
 * - 期初=0 且 变动=0 → 0（无变动无意义）
 * - 期初=0 且 变动>0 → 1（从无到有，100%增长）
 * - 其他情况 → change / begin
 *
 * 注：xlsx原始公式只处理了 begin=0 且 change>0 的情况，
 * 未处理 begin=0 且 change<0。按业务逻辑，负债从0到负值
 * 不太可能出现（负债不能为负），但为健壮性返回 change/begin
 * 在 begin≠0 分支处理。若 begin=0 且 change<0，
 * 此处返回0（与xlsx公式=IF(AND(B7=0,J7=0),0,...) 保持一致，
 * 其他条件不匹配时隐式返回0）。
 *
 * 用于：
 * - N3-1 审定表本期变动率
 *
 * @param begin - 期初余额（基数）
 * @param change - 变动额（期末-期初）
 * @returns 变动率（小数形式，如0.25表示25%）
 */
export function calcChangeRate(begin: number, change: number): number {
  const b = parseNum(begin)
  const c = parseNum(change)
  if (b === 0 && c === 0) return 0
  if (b === 0 && c > 0) return 1
  if (b === 0) return 0
  return c / b
}
