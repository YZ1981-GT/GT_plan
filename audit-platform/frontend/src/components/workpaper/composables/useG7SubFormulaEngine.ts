/**
 * G7 长期股权投资(子公司组) — 公式引擎（子公司投资全生命周期）
 *
 * 7个纯函数 + parseNum，无副作用、无Vue响应式依赖，支持 fast-check PBT 验证。
 *
 * 核心公式链：
 * - 同控初始投资成本 = 被合并方账面净资产 × 持股比例 (CAS20同控)
 * - 非同控初始投资成本 = 支付对价 + 直接相关费用 (CAS20非同控)
 * - 商誉 = 初始投资成本 - 享有份额（正=商誉，负=廉价购买利得）
 * - 成本法投资收益 = 被投资方宣告股利 × 持股比例
 * - 成本法期末账面 = 期初 + 追加投资 - 减值
 * - 处置损益 = 处置对价 - 处置日账面 - 应收股利 + 可转损益OCI
 * - 借贷平衡：|SUM(debits) - SUM(credits)| < 0.01
 *
 * Spec: .kiro/specs/g7-long-term-equity-subsidiary/
 * Requirements: 7.1, 3.3, 3.4, 4.2, 4.3, 5.3
 */

// ═══ parseNum: 安全数值转换（null/undefined/NaN/空串/'  '/'abc' → 0）═══

/**
 * 安全数值转换：null/undefined/NaN/空字符串/'  '/'abc' → 0; 有效数值→原值
 * @source G7子公司组公式引擎通用辅助，所有公式输入前调用
 */
export function parseNum(v: unknown): number {
  if (v === null || v === undefined || v === '') return 0
  if (typeof v === 'string') {
    const trimmed = v.trim()
    if (trimmed === '') return 0
    const n = Number(trimmed)
    return Number.isFinite(n) ? n : 0
  }
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

// ═══ P1: 同控初始投资成本 = 被合并方账面净资产 × 持股比例 ═══

/**
 * 同一控制下企业合并：初始投资成本 = 被合并方账面净资产 × 持股比例
 * 合并方以被合并方净资产账面价值的份额作为初始投资成本，差额调整资本公积→留存收益
 * G7-8 同控初始计量测试
 * @source CAS20 同一控制下企业合并，Requirements 3.3
 */
export function calcSameControlCost(netAssets: number, ratio: number): number {
  return Math.round((parseNum(netAssets) * parseNum(ratio)) * 100) / 100
}

// ═══ P2: 非同控初始投资成本 = 支付对价 + 直接相关费用 ═══

/**
 * 非同一控制下企业合并：初始投资成本 = 支付对价 + 直接相关费用
 * 购买方按公允价值计量，合并中发生的审计、法律服务等直接费用计入初始成本
 * G7-9 非同控初始计量测试
 * @source CAS20 非同一控制下企业合并，Requirements 3.4
 */
export function calcNotSameControlCost(price: number, fees: number): number {
  return Math.round((parseNum(price) + parseNum(fees)) * 100) / 100
}

// ═══ P3: 商誉 = 初始投资成本 - 享有被购买方可辨认净资产公允价值份额 ═══

/**
 * 商誉 = 初始投资成本 - 享有被购买方可辨认净资产公允价值份额
 * 正值=商誉（资产），负值=营业外收入（廉价购买利得/负商誉）
 * G7-9 非同控初始计量测试 商誉列
 * @source CAS20 非同一控制下企业合并商誉确认，Requirements 3.4, 7.1
 */
export function calcGoodwill(cost: number, shareOfFV: number): number {
  return Math.round((parseNum(cost) - parseNum(shareOfFV)) * 100) / 100
}

// ═══ P4: 成本法投资收益 = 被投资方宣告分派现金股利 × 持股比例 ═══

/**
 * 成本法投资收益 = 被投资方宣告分派现金股利 × 持股比例
 * 子公司个别报表采用成本法核算，不调整长投账面，仅确认被宣告的现金股利
 * G7-10 后续计量测试表 应确认投资收益列
 * @source CAS2 成本法后续计量，Requirements 4.2
 */
export function calcCostMethodIncome(dividend: number, ratio: number): number {
  return Math.round((parseNum(dividend) * parseNum(ratio)) * 100) / 100
}

// ═══ P5: 成本法期末账面余额 = 期初 + 本期增加 - 减值计提 ═══

/**
 * 成本法期末账面余额 = 期初账面 + 本期增加(追加投资) - 减值计提
 * 成本法下不含权益法调整，仅追加投资和减值影响账面价值
 * G7-10 后续计量测试表 期末账面列
 * @source CAS2 成本法后续计量，Requirements 4.3
 */
export function calcSubsequentBalance(opening: number, addition: number, impairment: number): number {
  return Math.round((parseNum(opening) + parseNum(addition) - parseNum(impairment)) * 100) / 100
}

// ═══ P6: 处置损益 = 处置对价 - 处置日账面 - 应收股利 + 可转损益OCI ═══

/**
 * 处置损益(个别报表) = 处置对价 - 处置日长投账面 - 处置日应收股利 + 可转损益OCI
 * 适用于：非一揽子单次处置(G7-11)；一揽子交易在丧失控制权日统一确认(G7-12)
 * G7-11 非一揽子处置测试表 个别报表处置损益列
 * @source CAS2/CAS33 丧失控制权处置，Requirements 5.3
 */
export function calcDisposalGain(price: number, bookValue: number, dividend: number, oci: number): number {
  return Math.round((parseNum(price) - parseNum(bookValue) - parseNum(dividend) + parseNum(oci)) * 100) / 100
}

// ═══ P7: 借贷平衡校验 — |SUM(debits) - SUM(credits)| < 0.01 ═══

/**
 * 借贷平衡校验：|SUM(debits) - SUM(credits)| < 0.01
 * G7-18凭证检查表顶部借贷差额汇总，差额≠0红色告警
 * @source G7-18凭证检查表 借贷平衡，Requirements 6.2, 7.1
 */
export function isDebitCreditBalanced(debits: number[], credits: number[]): boolean {
  const sumD = debits.reduce((s, v) => s + parseNum(v), 0)
  const sumC = credits.reduce((s, v) => s + parseNum(v), 0)
  return Math.abs(sumD - sumC) < 0.01
}
