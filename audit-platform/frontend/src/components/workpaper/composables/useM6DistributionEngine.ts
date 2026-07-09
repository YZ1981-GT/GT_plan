/**
 * useM6DistributionEngine — M6 利润分配结转引擎（核心！）
 *
 * 纯函数，无副作用、无 Vue reactivity、确定性输出。
 * 科目：4104 利润分配-未分配利润（**贷方/权益类！**）
 *
 * ─── 利润分配结转核心公式链 ───
 * 期末未分配利润 = 期初未分配利润 + 本年净利润 - 提取盈余公积 - 分配股利
 *
 * 结转关系：
 * - 上游：接收本年净利润（利润表结转，借:本年利润 贷:利润分配-未分配利润）
 * - 下游①：驱动M5盈余公积计提（借:利润分配-未分配利润 贷:盈余公积）
 *   surplusAccrual = 提取法定盈余公积 + 提取任意盈余公积
 * - 下游②：驱动M1应付股利分配（借:利润分配-未分配利润 贷:应付股利）
 *   dividend = 应付现金股利 + 转作股本的股利
 *
 * 联动核对：M6记录的分配额须与M5实际计提、M1实际宣告一致
 * ─────────────────────────────────────
 *
 * 本引擎覆盖：
 * - P3: 利润分配结转核心公式链（期末=期初+本年净利润-提取盈余公积-分配股利）
 * - P4: 可供分配利润（=期初+本年净利润）
 * - P5: 联动差异（=M6值-来源值）
 * - P7: 结转公式链一致性（calcRetainedEnd === calcDistributable - sa - d）
 *
 * Spec: .kiro/specs/m6-retained-earnings/ Task 2.2
 * Requirements: 3.2, 4.5, 6.1-6.3
 */

// ─── helpers ────────────────────────────────────────────────

/** 将 NaN / undefined / null 视为 0 */
function safe(v: unknown): number {
  if (v === null || v === undefined) return 0
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

// ─── P3: 利润分配结转核心公式链 ─────────────────────────────

/**
 * 计算期末未分配利润（Property P3，核心！）
 *
 * 期末未分配利润 = 期初 + 本年净利润 - 提取盈余公积 - 分配股利
 *
 * 业务含义：
 * - begin: 期初未分配利润（年初余额，含前期差错追溯调整后）
 * - netProfit: 本年净利润（利润表结转，贷方增加未分配利润）
 * - surplusAccrual: 提取盈余公积合计（法定10%+任意，→M5）
 * - dividend: 分配股利合计（现金股利+转增股本，→M1）
 *
 * 等价性保证（P7）：
 *   calcRetainedEnd(b,np,sa,d) === calcDistributable(b,np) - sa - d
 *
 * @param begin - 期初未分配利润
 * @param netProfit - 本年净利润
 * @param surplusAccrual - 提取盈余公积合计（法定+任意）
 * @param dividend - 分配股利合计（现金+转增）
 * @returns 期末未分配利润
 */
export function calcRetainedEnd(begin: number, netProfit: number, surplusAccrual: number, dividend: number): number {
  return safe(begin) + safe(netProfit) - safe(surplusAccrual) - safe(dividend)
}

// ─── P4: 可供分配利润 ───────────────────────────────────────

/**
 * 计算可供分配利润（Property P4）
 *
 * 可供分配利润 = 期初未分配利润 + 本年净利润
 *
 * 这是分配前的利润总池，尚未扣除盈余公积计提和股利分配。
 * 用于M6-2明细表中间行展示，以及检查表M6-4的核对。
 *
 * @param begin - 期初未分配利润
 * @param netProfit - 本年净利润
 * @returns 可供分配利润
 */
export function calcDistributable(begin: number, netProfit: number): number {
  return safe(begin) + safe(netProfit)
}

// ─── P5: 联动差异 ──────────────────────────────────────────

/**
 * 计算联动差异（Property P5）
 *
 * 联动差异 = M6值 - 来源值
 *
 * 用于跨底稿核对：
 * - M6记录的提取盈余公积 vs M5实际计提（surplusVsM5）
 * - M6记录的分配股利 vs M1实际宣告（dividendVsM1）
 * - 差异=0表示一致；差异≠0时红色高亮提示核对
 *
 * @param m6Value - M6底稿中记录的分配金额
 * @param sourceValue - 来源底稿实际确认的金额（M5计提/M1宣告）
 * @returns 差异值（0=一致，非0=需核对）
 */
export function calcLinkageDiff(m6Value: number, sourceValue: number): number {
  return safe(m6Value) - safe(sourceValue)
}
