/**
 * useD1FormulaEngine — D1 应收票据共享纯函数公式引擎
 *
 * 所有函数为纯函数，无副作用，便于单元测试和 PBT。
 * 供 useD1Adjudication / useD1DetailCategory / useD1DetailCustomer / useD1BadDebt 复用。
 *
 * Spec: .kiro/specs/d1-adjudication-table/
 * Requirements: 1.3, 1.4, 1.5, 1.6, 1.7, 6.4, 10.5
 */

// ─── 数值解析 ─────────────────────────────────────────────────────────────────

/**
 * 安全数值解析：null/undefined/空串/NaN/±Infinity → 0
 *
 * 审计底稿中大量字段可能为空或无效值，统一转为数字 0 以确保公式运算不出 NaN。
 * 非有限值也必须归零：`parseFloat('Infinity')` / `parseFloat('1e400')` 都能过 `isNaN`
 * 检查，一旦漏进公式，`Infinity - Infinity` / `Infinity / Infinity` 会让整表变 NaN。
 */
export function parseNum(val: string | number | null | undefined): number {
  if (val === null || val === undefined || val === '') return 0
  const n = typeof val === 'number' ? val : parseFloat(val)
  return Number.isFinite(n) ? n : 0
}

// ─── 审定表公式 ──────────────────────────────────────────────────────────────

/**
 * 审定数 = 未审数 + AJE净额 + RJE净额
 *
 * 源模板公式 E8=B8+C8+D8，AJE/RJE 为净额不分借贷。
 * 适用于 D1-1 审定表、D1-2 按类别明细、D1-3 按客户明细的审定金额计算。
 */
export function calcAuditedAmount(unadjusted: number, aje: number, rje: number): number {
  return unadjusted + aje + rje
}

/**
 * 变动率计算，含期初=0特殊处理：
 * - 期初=0 且 审定=0 → ''（无意义）
 * - 期初=0 且 审定≠0 → 1（100%新增）
 * - 其他 → (审定-期初)/期初
 */
export function calcChangeRate(prior: number, audited: number): number | '' {
  if (prior === 0 && audited === 0) return ''
  if (prior === 0) return 1
  return (audited - prior) / prior
}

// ─── 小计与净值 ──────────────────────────────────────────────────────────────

/**
 * 小计 = SUM(明细行对应列)
 *
 * 审定表中每个区块的小计行公式，不可手动编辑。
 */
export function calcSubtotal(rows: number[]): number {
  return rows.reduce((sum, v) => sum + v, 0)
}

/**
 * 净值 = 原值 - 坏账准备
 *
 * D1-1 审定表第三区块"应收票据净值"行公式。
 */
export function calcNetValue(grossValue: number, badDebt: number): number {
  return grossValue - badDebt
}

// ─── 阈值判定 ────────────────────────────────────────────────────────────────

/**
 * 增减比例绝对值是否超阈值
 *
 * 审定表中 |变动率| > 30% 时红色高亮。rate 为 '' 时视为未超阈值。
 */
export function isChangeRateExceeding(rate: number | '', threshold: number): boolean {
  if (rate === '') return false
  return Math.abs(rate) > threshold
}

// ─── ECL 坏账准备公式 ────────────────────────────────────────────────────────

/**
 * ECL 预期信用损失率 = 各阶段迁徙率连乘
 *
 * D1-4 坏账准备按组合计提时，各账龄段迁徙率连乘得出预期损失率。
 * 空数组返回 0（无数据无意义）。
 */
export function calcExpectedLossRate(migrationRates: number[]): number {
  if (migrationRates.length === 0) return 0
  return migrationRates.reduce((acc, r) => acc * r, 1)
}

/**
 * 应计提 = 余额 × 损失率
 *
 * D1-4 坏账准备单项/组合计提核心公式。
 */
export function calcProvision(balance: number, lossRate: number): number {
  return balance * lossRate
}

/**
 * 差异 = 实际账面余额 - 应计提
 *
 * 正值表示多提，负值表示少提。
 */
export function calcDifference(actual: number, should: number): number {
  return actual - should
}

// ─── 安全除法（IFERROR 语义） ────────────────────────────────────────────────

/**
 * 安全除法：divisor=0 返回 0，否则返回 numerator/divisor
 *
 * 对应源模板 IFERROR(x/y, 0) 语义，用于：
 * - 比例列计算 = IFERROR(本行余额 / 合计行余额, 0)
 * - 预期信用损失率 = IFERROR(坏账准备 / 账面余额, 0)
 */
export function safeDivide(numerator: number, divisor: number): number {
  if (divisor === 0) return 0
  return numerator / divisor
}

// ─── 坏账准备变动公式 ────────────────────────────────────────────────────────

/**
 * 期末未审数 = 期初审定 + 本期计提 - 本期收回 - 本期转回 - 本期核销 + 本期其他
 *
 * D1-4 坏账准备明细表各行的期末未审数自动计算。
 */
export function calcBadDebtEndBalance(
  priorAudited: number,
  provision: number,
  recovery: number,
  reversal: number,
  writeOff: number,
  other: number
): number {
  return priorAudited + provision - recovery - reversal - writeOff + other
}

/**
 * 披露表「本期计提、收回或转回的坏账准备」变动表期末数。
 *
 * 🔴 与 `calcBadDebtEndBalance`（D1-4 明细表）**符号不同**，两者不可互用：
 *
 * | 表 | 源模板公式 | 「其他」方向 |
 * |----|-----------|-------------|
 * | D1-4 坏账准备明细表 | `K12=B12+SUM(F12:G12)-SUM(H12:J12)`（本期增加含「其他增加」） | **加项** |
 * | 披露变动表（上市 `B100` / 国企 `G48`） | `期初+计提-收回或转回-核销-转销-其他变动` | **减项** |
 *
 * 改造前披露变动表复用了 D1-4 的函数（其他为加项）→ 与自家勾稽面板的 F4-7 判定
 * （已按源模板 G48 取减项）**符号相反**，只要「其他变动」非 0，披露表算出的期末数
 * 就会被自己的勾稽面板判为异常。
 *
 * @param prior 期初数（上年年末数）
 * @param provision 本期计提
 * @param reversal 本期收回或转回
 * @param writeOff 本期核销
 * @param transfer 本期转销（源模板上市 `[本期转销]` 可选行）
 * @param other 其他 / 其他变动
 */
export function calcDisclosureBadDebtEnd(
  prior: number,
  provision: number,
  reversal: number,
  writeOff: number,
  transfer: number,
  other: number,
): number {
  return prior + provision - reversal - writeOff - transfer - other
}

/**
 * 期末未审数 = 期初审定 + 本期增加 - 本期减少
 *
 * D1-2（按类别）/ D1-3（按客户）原值明细表的期末未审数计算。
 */
export function calcCurrentUnadjusted(
  priorAudited: number,
  increase: number,
  decrease: number
): number {
  return priorAudited + increase - decrease
}

// ─── 贴息（贴现利息）公式 ────────────────────────────────────────────────────

/**
 * 贴息天数 = 到期日 - 贴现日（自然天数差）
 *
 * D1-9 贴息检查表：解析到期日与贴现日为日期，返回相差的整数天数。
 * 任一日期为空或非法 → 返回 0。
 * 贴现日 > 到期日（异常数据）→ 返回 0（贴息天数显示为 0）。
 */
export function calcDiscountDays(maturityDate: string, discountDate: string): number {
  if (!maturityDate || !discountDate) return 0
  const maturity = new Date(maturityDate).getTime()
  const discount = new Date(discountDate).getTime()
  if (isNaN(maturity) || isNaN(discount)) return 0
  const days = (maturity - discount) / 86400000
  if (days < 0) return 0
  return days
}

/**
 * 应计贴现利息 = 票面金额 × 贴现率 × 贴息天数 / 360
 *
 * D1-9 贴息检查表核心公式 P×R×D/360，用于与账面贴现利息核对。
 */
export function calcDiscountInterest(faceValue: number, discountRate: number, days: number): number {
  return (faceValue * discountRate * days) / 360
}

/**
 * 贴息差异 = 应计贴现利息 - 账面贴现利息
 *
 * D1-9 贴息检查表：正值表示应计大于账面（少计），负值表示应计小于账面（多计）。
 * 差异 ≠ 0 时高亮提示。
 */
export function calcInterestDifference(calculated: number, booked: number): number {
  return calculated - booked
}

// ─── D1-7 备查簿公式 ─────────────────────────────────────────────────────────

/** 6 家大型商业银行 + 9 家上市股份制商业银行（与 D1-6 编制提示一致） */
export const HIGH_CREDIT_BANK_KEYWORDS = [
  '中国银行', '农业银行', '建设银行', '工商银行', '邮储银行', '交通银行',
  '招商银行', '浦发银行', '中信银行', '光大银行', '华夏银行', '民生银行',
  '平安银行', '兴业银行', '浙商银行',
]

/**
 * 备查簿年末余额 = 年初 + 本期收到 - 本期背书 - 本期到期承兑 - 本期贴现
 */
export function calcMemoEndingBalance(
  beginning: number,
  received: number,
  endorsed: number,
  matured: number,
  discounted: number,
): number {
  return beginning + received - endorsed - matured - discounted
}

/** 承兑人名称是否属于高信用银行（子串匹配） */
export function isHighCreditBank(acceptor: string): boolean {
  const name = (acceptor || '').trim()
  if (!name) return false
  return HIGH_CREDIT_BANK_KEYWORDS.some((kw) => name.includes(kw))
}

/** 日期字符串比较：a 是否早于 b（非法日期返回 false） */
export function isDateBefore(a: string, b: string): boolean {
  if (!a || !b) return false
  const ta = new Date(a).getTime()
  const tb = new Date(b).getTime()
  if (isNaN(ta) || isNaN(tb)) return false
  return ta < tb
}

/**
 * 期末未到期背书贴现金额：审计基准日尚未到期且状态为已贴现/已背书时取票面金额
 */
export function calcUnexpiredEndorsedDiscounted(
  amount: number,
  status: string,
  maturityDate: string,
  cutoffDate: string,
): number {
  if (!amount || !cutoffDate || !maturityDate) return 0
  if (status !== '已贴现' && status !== '已背书') return 0
  if (isDateBefore(maturityDate, cutoffDate) || maturityDate === cutoffDate) return 0
  return amount
}

/**
 * 终止确认建议：高信用银行承兑贴现/背书倾向终止确认；商业承兑及低信用倾向不终止确认
 */
export function suggestDerecognized(
  status: string,
  acceptor: string,
  noteType: string,
): string {
  if (status !== '已贴现' && status !== '已背书') return ''
  if (noteType.includes('商业')) return '否'
  if (isHighCreditBank(acceptor)) return '是'
  return '否'
}

/** 信用评级建议：高信用银行承兑默认 AA 档，商业承兑默认其他 */
export function suggestCreditRating(acceptor: string, noteType: string): string {
  if (noteType.includes('商业')) return '其他'
  if (isHighCreditBank(acceptor)) return 'AA'
  return 'A'
}

// ─── 业务模式与列报项目判定（QA矩阵IF公式） ──────────────────────────────────

/**
 * QA矩阵业务模式判定：根据4个 Y/N 答案返回业务模式描述
 *
 * D1-6 业务模式分析，对应源模板 R21 的 IF(AND(...)) 嵌套公式：
 * - Q1=Y ∧ Q2=N → 以收取合同现金流量为目标的业务模式
 * - Q1=Y ∧ Q2=Y ∧ Q4=Y → 以收取合同现金流量和出售金融资产为目标的业务模式
 * - Q1=N ∨ (Q2=Y ∧ Q4=N) → 其他业务模式（以公允价值计量且其变动计入当期损益）
 * - 其余 → ''（判定条件不足）
 */
export function determineBusinessMode(
  q1: 'Y' | 'N' | '', q2: 'Y' | 'N' | '', q3: 'Y' | 'N' | '', q4: 'Y' | 'N' | ''
): string {
  if (q1 === 'Y' && q2 === 'N') {
    return '属于以收取合同现金流量为目标的业务模式'
  }
  if (q1 === 'Y' && q2 === 'Y' && q4 === 'Y') {
    return '属于以收取合同现金流量和出售金融资产为目标的业务模式'
  }
  if (q1 === 'N' || (q2 === 'Y' && q4 === 'N')) {
    return '其他业务模式（以公允价值计量且其变动计入当期损益）'
  }
  return ''
}

/**
 * 列报项目判定：根据业务模式返回列报科目
 *
 * D1-6 判定结果 → D1-1 列报分类映射。
 * 注意判定顺序：'收取合同现金流量和出售金融资产' 必须先于 '收取合同现金流量为目标' 判断，
 * 因为前者字符串包含子串 '收取合同现金流量'，顺序颠倒会导致误匹配。
 * - 收取合同现金流量和出售金融资产 → 应收款项融资
 * - 收取合同现金流量为目标 → 应收票据
 * - 其他业务模式 → 以公允价值计量且其变动计入当期损益的金融资产
 * - 其余 → ''
 */
export function determineReportItem(businessMode: string): string {
  if (businessMode.includes('收取合同现金流量和出售金融资产')) {
    return '应收款项融资'
  }
  if (businessMode.includes('收取合同现金流量为目标')) {
    return '应收票据'
  }
  if (businessMode.includes('其他业务模式')) {
    return '以公允价值计量且其变动计入当期损益的金融资产'
  }
  return ''
}

// ─── 坏账分类表派生列（读时推导，禁止持久化）─────────────────────────────────

/** 坏账分类行的最小形状（仅派生列所需字段）。 */
export interface ClassRowDerivable {
  balance: number
  provision: number
  ratio: number
  lossRate: number
  bookValue: number
}

/**
 * 重算单行的三个派生列（纯函数）。
 *
 * 口径取自应收票据校验预设（`note_check_preset_formulas.json` 的 `F4-*`）：
 * - `F4-25` 比例(%)          = 该行账面余额 ÷ **合计行**账面余额 × 100
 * - `F4-12` 预期信用损失率(%) = 坏账准备 ÷ 账面余额 × 100
 * - `F4-11` 账面价值          = 账面余额 − 坏账准备
 *
 * 🔴 三列必须**读时推导**，不能持久化后再用：
 * 历史实现把 `ratio` 存进行对象、只在编辑时用**编辑前**的合计做分母重算被编辑的那一行，
 * 组件层又把两个不同分母的 `ratio` 相加（银承 / 商承）→ 浏览器实测「按组合计提坏账准备」
 * 行显示 162.50%（应 100.00%），且错值已随同步进入附注。
 * 比率乘 100 由展示层 `fmtPct` / 同步层 `pct()` 负责，此处一律存分数。
 */
export function deriveClassRow<T extends ClassRowDerivable>(row: T, totalBalance: number): T {
  return {
    ...row,
    ratio: safeDivide(row.balance, totalBalance),
    lossRate: safeDivide(row.provision, row.balance),
    bookValue: calcNetValue(row.balance, row.provision),
  }
}

/** 批量重算派生列（分母统一取传入的合计账面余额）。 */
export function deriveClassRows<T extends ClassRowDerivable>(
  rows: readonly T[],
  totalBalance: number,
): T[] {
  return rows.map((r) => deriveClassRow(r, totalBalance))
}

/**
 * 部分 ÷ 整体（分数），整体为 0 时返回 0。
 *
 * 组件层聚合行（如国企「按组合计提坏账准备」= 银承 + 商承）必须用本函数按
 * **聚合后的金额**重算，禁止把成员行的比率相加。
 */
export function ratioOf(part: number, whole: number): number {
  return safeDivide(part, whole)
}
