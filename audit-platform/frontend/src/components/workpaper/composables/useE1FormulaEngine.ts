/**
 * useE1FormulaEngine — E1 货币资金共享纯函数公式引擎
 *
 * 所有函数为纯函数，无副作用，无 Vue 响应式依赖，便于单元测试和 PBT。
 * 覆盖货币资金循环（科目1001库存现金/1002银行存款/1012其他货币资金）的全部公式计算需求。
 *
 * 核心特色（vs D1/D4/D5）：
 * - 审定数 = 未审数 + 账项调整（单列合并，非 AJE/RJE 四列拆分）
 * - 变动率按模板口径：opening=0&ending=0→0; opening=0&ending>0→1; else change/opening
 * - 现金/数字货币余额链式：期末 = 期初 + 增加 - 减少
 * - 外币折算：原币 × 汇率
 * - 应计利息：原币金额 × 天数 × 日利率
 * - 银行余额调节：base + 已收未收 - 已付未付
 * - 借贷平衡校验（E1-5 调整分录）
 *
 * Spec: .kiro/specs/e1-monetary-fund-refactor/
 * Requirements: 1.2, 1.3, 3.2, 5.2, 6.2, 6.3, 7.4, 10.3, 12.2-12.5, 14.2
 */

// ─── 数值解析 ─────────────────────────────────────────────────────────────────

/**
 * 安全数值解析：null/undefined/空串/NaN/Infinity/非数值类型 → 0
 *
 * 审计底稿中大量字段可能为空或无效值，统一转为数字 0 以确保公式运算不出 NaN。
 * 接受 unknown 类型以兼容从 JSON 解析或 allResponses Map 读取的任意值。
 */
export function parseNum(val: unknown): number {
  if (val === null || val === undefined || val === '') return 0
  const n = typeof val === 'number' ? val : Number(val)
  if (!isFinite(n)) return 0
  return n
}

// ─── 审定表公式（E1-1）──────────────────────────────────────────────────────

/**
 * 审定数 = 未审数 + 账项调整（单列合并）
 *
 * E1-1 审定表真实模板：D=B+C（期初审定=期初未审+期初账项调整），G=E+F（期末同理）。
 * 与 D1/D4 的三列（未审+AJE+RJE）不同，E1 只有单列账项调整。
 */
export function calcAudited(unadjusted: number, adjustment: number): number {
  return unadjusted + adjustment
}

/**
 * 变动额 = 期末审定数 - 期初审定数
 *
 * E1-1 审定表 H列 = G - D。通用差额计算。
 */
export function calcChange(endingAudited: number, openingAudited: number): number {
  return endingAudited - openingAudited
}

/**
 * 变动率（模板口径）：
 * - 期初=0 且 期末=0 → 0（无变动）
 * - 期初=0 且 期末>0 → 1（100% 新增）
 * - 其他 → 变动额 / 期初审定数
 *
 * 注意：ending = opening + change，此处参数为 change 和 opening。
 * 返回 '' 表示不可计算（E1 模板中不出现此情况，但类型兼容保留）。
 *
 * E1-1 审定表 I列公式，与 D1/D4 的 N/A 处理不同——E1 模板明确规定上述三种情况。
 */
export function calcChangeRate(change: number, openingAudited: number): number | '' {
  const ending = openingAudited + change
  if (openingAudited === 0 && ending === 0) return 0
  if (openingAudited === 0 && ending > 0) return 1
  if (openingAudited === 0) return ''
  return change / openingAudited
}

// ─── 现金/数字货币余额链式（E1-2 / E1-4）────────────────────────────────────

/**
 * 期末余额 = 期初 + 本期增加 - 本期减少
 *
 * E1-2 现金明细（按币种）、E1-4 数字货币明细的核心链式公式。
 * 与 D5 的 calcEndBalance 类似但命名更贴近 E1 业务语义。
 */
export function calcCashBalance(opening: number, increase: number, decrease: number): number {
  return opening + increase - decrease
}

// ─── 银行余额调节（E1-6）────────────────────────────────────────────────────

/**
 * 调节后余额 = 基数 + 加项 - 减项
 *
 * E1-6 余额调节表：
 * - 企业侧：调节后企业余额 = 账面余额 + 企收银未收 - 企付银未付
 * - 银行侧：调节后银行余额 = 对账单余额 + 银收企未收 - 银付企未付
 *
 * 两侧使用同一公式，通过参数区分。
 */
export function calcReconciled(base: number, addItems: number, subItems: number): number {
  return base + addItems - subItems
}

// ─── 应计利息测算（E1-20）──────────────────────────────────────────────────

/**
 * 应计利息（原币）= 原币金额 × 天数 × 日利率
 *
 * E1-20 银行存款及其他货币资金应计利息测算表核心公式。
 * 人民币金额需再乘汇率（calcFxConvert）。
 */
export function calcAccruedInterest(fcAmount: number, days: number, dailyRate: number): number {
  return fcAmount * days * dailyRate
}

// ─── 外币折算（E1-2 / E1-3 / E1-4 / E1-8 / E1-20）────────────────────────

/**
 * 外币折算 = 原币金额 × 汇率
 *
 * 通用外币→人民币折算公式，适用于：
 * - E1-2 现金明细期末折算人民币
 * - E1-3 银行明细外币版各列折算
 * - E1-4 数字货币本位币折算
 * - E1-8 外币盘点折算
 * - E1-20 应计利息原币→人民币
 */
export function calcFxConvert(fcAmount: number, rate: number): number {
  return fcAmount * rate
}

// ─── 盘点差异（E1-7 / E1-8）────────────────────────────────────────────────

/**
 * 盘点差异 = 实盘数 - 账面余额
 *
 * E1-7 人民币盘点表、E1-8 外币盘点表的核心差异公式。
 * 正值表示盘盈，负值表示盘亏。差异≠0 时需橙色高亮+强制填写原因。
 */
export function calcCountDiff(actual: number, book: number): number {
  return actual - book
}

// ─── 数组求和（通用）────────────────────────────────────────────────────────

/**
 * 按字段名求和：对行数组中指定字段求和
 *
 * 适用于 E1-2/E1-3/E1-4 等动态行表的合计行计算。
 * 各行字段值通过 parseNum 安全解析，忽略非数值。
 */
export function sumField(rows: Array<Record<string, unknown>>, field: string): number {
  return rows.reduce((sum, row) => sum + parseNum(row[field]), 0)
}

// ─── 阈值判定 ────────────────────────────────────────────────────────────────

/**
 * 变动率绝对值是否超阈值
 *
 * rate 为 ''（不可计算）时返回 false。
 * E1-1 审定表 |变动率| > 30% 时红色高亮；E1-14 分析表同理。
 */
export function exceedsThreshold(rate: number | '', threshold: number): boolean {
  if (rate === '') return false
  return Math.abs(rate) > threshold
}

// ─── 借贷平衡校验（E1-5）────────────────────────────────────────────────────

/**
 * 借贷是否平衡：Σ借方 === Σ贷方
 *
 * E1-5 调整分录汇总底部平衡校验。
 * 使用 parseNum 安全求和，容忍行中字段为空/非数值。
 * 浮点精度：差异绝对值 < 0.001 视为平衡（避免浮点误差）。
 */
export function isBalanced(
  rows: Array<Record<string, unknown>>,
  debitField: string,
  creditField: string
): boolean {
  const totalDebit = rows.reduce((sum, row) => sum + parseNum(row[debitField]), 0)
  const totalCredit = rows.reduce((sum, row) => sum + parseNum(row[creditField]), 0)
  return Math.abs(totalDebit - totalCredit) < 0.001
}

// ─── 序列化/反序列化（持久化）───────────────────────────────────────────────

/**
 * 行序列化：仅保留用户输入字段，JSON.stringify
 *
 * 计算字段（如期末余额/审定数/变动率）不存储，反序列化时重新计算确保一致性。
 * userFields 参数指定需要保留的字段名列表。
 */
export function serializeRows<T>(rows: T[], userFields: string[]): string {
  const data = rows.map(row => {
    const obj: Record<string, unknown> = {}
    for (const field of userFields) {
      obj[field] = (row as Record<string, unknown>)[field]
    }
    return obj
  })
  return JSON.stringify(data)
}

/**
 * 行反序列化：解析 JSON 并重新计算派生字段
 *
 * recompute 回调函数负责重新计算每行的计算字段（如期末余额/审定数等）。
 * 解析失败时返回空数组（降级容错 + console.warn）。
 */
export function deserializeRows(json: string, recompute: (r: Record<string, unknown>) => Record<string, unknown>): Record<string, unknown>[] {
  try {
    const parsed = JSON.parse(json)
    if (!Array.isArray(parsed)) return []
    return parsed.map(r => recompute(r))
  } catch {
    console.warn('[E1FormulaEngine] deserializeRows: JSON parse failed, fallback to empty array')
    return []
  }
}
