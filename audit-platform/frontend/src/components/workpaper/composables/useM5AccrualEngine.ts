/**
 * useM5AccrualEngine — M5 盈余公积计提引擎
 *
 * 纯函数，无副作用、无 Vue reactivity、确定性输出。
 * 科目：4101 盈余公积（**贷方/权益类！**）
 *
 * ─── 法定盈余公积计提规则（公司法第167条）───
 * - 公司分配当年税后利润时，应当提取利润的10%列入法定公积金
 * - 累计额为公司注册资本的50%以上的，可以不再提取
 * - 计提基数 = 本期净利润 - 弥补以前年度亏损（来自M6未分配利润）
 * - 法定盈余公积与任意盈余公积分别计算
 * ─────────────────────────────────────────────
 *
 * 业务场景：
 * - M5-4 盈余公积计提检查表（42×9，11公式）
 * - 接收M6未分配利润的净利润作为计提基数输入
 * - 法定计提=计提基数×10%（固定比例）
 * - 任意计提=计提基数×股东会决议比例（可变）
 * - 累计法定盈余公积≥注册资本50%时，提示可停止计提
 *
 * 本引擎覆盖：
 * - P3: 法定盈余公积10%计提
 * - P4: 计提差异
 * - P5: 注册资本50%计提上限
 *
 * Spec: .kiro/specs/m5-surplus-reserve/ Task 2.2
 * Requirements: 4.3-4.5, 6.1-6.3
 */

// ─── helpers ────────────────────────────────────────────────

/** 将 NaN / undefined / null 视为 0 */
function safe(v: unknown): number {
  if (v === null || v === undefined) return 0
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

// ─── P3: 法定盈余公积10%计提 ────────────────────────────────

/**
 * 计算法定盈余公积应计提金额（Property P3）
 *
 * 公司法第167条：应当提取利润的10%列入公司法定公积金。
 *
 * 计提基数 = 本期净利润 - 弥补以前年度亏损（来自M6未分配利润）
 * 应计提法定盈余公积 = 计提基数 × 计提比例（默认10%）
 *
 * 来源：M5-4 盈余公积计提检查表 row13: B13=B11*B12
 * 其中 B11=计提基数，B12=计提比例(0.1)
 *
 * 注意：
 * - 法定盈余公积固定10%
 * - 任意盈余公积比例由股东会决议确定（通过rate参数传入）
 * - 计提基数为负（亏损年度）时，结果为负，实际不计提（由业务层判断）
 *
 * @param base - 计提基数（净利润 - 弥补以前年度亏损）
 * @param rate - 计提比例，默认0.1（10%）。任意盈余公积可传入其他比例
 * @returns 应计提金额
 */
export function calcStatutoryAccrual(base: number, rate: number = 0.1): number {
  return safe(base) * safe(rate)
}

// ─── P4: 计提差异 ───────────────────────────────────────────

/**
 * 计算计提差异（Property P4）
 *
 * 计提差异 = 应计提金额 - 账面已计提金额
 * - 差异 > 0：少计提，需补提
 * - 差异 < 0：多计提，需冲回或说明
 * - 差异 = 0：计提准确
 *
 * 来源：M5-4 计提检查表"差异"列
 * 当 |差异| > 阈值时前端红色高亮提示
 *
 * @param estimated - 应计提金额（calcStatutoryAccrual计算结果）
 * @param booked - 账面已计提金额（从M5-2明细表或TB取得）
 * @returns 计提差异（正=少提，负=多提）
 */
export function calcAccrualDiff(estimated: number, booked: number): number {
  return safe(estimated) - safe(booked)
}

// ─── P5: 注册资本50%计提上限 ────────────────────────────────

/**
 * 判断累计法定盈余公积是否已达注册资本50%上限（Property P5）
 *
 * 公司法第167条：法定公积金累计额为公司注册资本的50%以上的，可以不再提取。
 *
 * 来源：m5_conflict_resolution.md 第4节确认
 * xlsx中无显式公式（传统模板靠人工判断），前端新增自动化实现。
 *
 * 注意：
 * - 仅适用于法定盈余公积，不适用于任意盈余公积
 * - "可以不再提取"是权利而非义务，企业仍可继续计提
 * - 外商投资企业同样适用（2025.1.1起统一公司法）
 * - registeredCapital 为 0 或负数时，视为未达上限（防御性处理）
 *
 * @param accumulated - 累计法定盈余公积余额（含本期计提前已有余额）
 * @param registeredCapital - 公司注册资本
 * @returns true=已达上限可不再计提，false=未达上限须继续计提
 */
export function isAccrualCeilingReached(accumulated: number, registeredCapital: number): boolean {
  const acc = safe(accumulated)
  const cap = safe(registeredCapital)
  // 注册资本为0或负数时，不可能达到上限
  if (cap <= 0) return false
  return acc >= cap * 0.5
}
