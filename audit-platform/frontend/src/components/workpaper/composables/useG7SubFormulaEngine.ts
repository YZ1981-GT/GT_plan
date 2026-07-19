/**
 * G7 长期股权投资(子公司组) — 公式引擎（子公司投资全生命周期）
 *
 * 纯函数 + parseNum，无副作用、无Vue响应式依赖，支持 fast-check PBT 验证。
 *
 * 核心公式链：
 * - 同控初始投资成本 = 被合并方账面净资产 × 持股比例 (CAS20同控)
 * - 非同控初始投资成本 = 合并对价公允价值；直接相关中介费用费用化 (CAS20非同控)
 * - 商誉 = 初始投资成本 - 享有份额（正=商誉，负=廉价购买利得）
 * - 成本法投资收益 = 被投资方宣告股利 × 持股比例
 * - 成本法期末账面 = 期初 + 追加投资 - 减值
 * - 购买少数股权合并调整 = 购买成本 − 持续计算净资产FV × 新增持股比例 (CAS33权益性交易)
 * - 不丧失控制权处置：个别投资收益 = 对价 − 账面×减少比例/原比例；合并调整 = 对价 − 净资产FV×减少比例
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

/**
 * 一次合并差额⑤ = 初始投资成本③ − 支付对价合计④
 * 正数贷记资本公积；负数冲减资本公积/留存收益
 */
export function calcSameControlMergerDifference(initialCost: number, totalConsideration: number): number {
  return Math.round((parseNum(initialCost) - parseNum(totalConsideration)) * 100) / 100
}

/**
 * 分步同控合并日初始成本⑤ = 合并日净资产账面价值④ × 累计持股比例①
 */
export function calcSameControlStepCost(mergerDateNetAssets: number, cumulativeRatio: number): number {
  return Math.round((parseNum(mergerDateNetAssets) * parseNum(cumulativeRatio)) * 100) / 100
}

/**
 * 分步同控调整⑥ = 累计对价② + 原持股账面价值 + 原投资调整③ − 初始成本⑤
 */
export function calcSameControlStepDifference(
  cumulativeConsideration: number,
  priorHoldingBookValue: number,
  priorAdjustments: number,
  initialCost: number,
): number {
  return Math.round(
    (parseNum(cumulativeConsideration) + parseNum(priorHoldingBookValue) + parseNum(priorAdjustments)
      - parseNum(initialCost)) * 100,
  ) / 100
}

// ═══ P2: 非同控合并对价合计（兼容旧接口名） ═══

/**
 * 非同一控制下企业合并：合并对价公允价值合计。
 *
 * 历史 Requirements 3.4 将「直接费用」并入本函数第二参数；按现行 CAS20，
 * 审计/法律/评估等中介费用应于发生时计入当期损益，不构成合并成本。
 * 第二参数仅为旧调用兼容保留，计算时不纳入成本；费用单独列示为「费用化」。
 *
 * @source CAS20 非同一控制下企业合并；兼容 Requirements 3.4
 */
export function calcNotSameControlCost(price: number, fees: number = 0): number {
  void fees
  return Math.round(parseNum(price) * 100) / 100
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

// ═══ G7-10 §1: 股利差异 = 应享有股利 − 实际入账股利 ═══

/**
 * 股利差异 = 被审计单位应分配股利 − 实际入账股利
 * G7-10 第1节 被投资单位分配股利测算
 * @source CAS2 成本法，宣告日确认投资收益
 */
export function calcDividendVariance(entitled: number, recorded: number): number {
  return Math.round((parseNum(entitled) - parseNum(recorded)) * 100) / 100
}

// ═══ G7-10 §2: 购买少数股权 — 对价合计 / 净资产份额 / 权益调整 ═══

/**
 * 对价/成本合计 = 现金 + 非现金资产FV + 承担债务账面 + 发行权益工具面值 + 或有对价
 * 用于 G7-10 购买少数股权②、不丧失控制权处置④
 */
export function calcConsiderationTotal(
  cash: number,
  nonCashFV: number,
  debtBV: number,
  equityFace: number,
  contingent: number,
): number {
  return Math.round(
    (parseNum(cash) + parseNum(nonCashFV) + parseNum(debtBV) + parseNum(equityFace) + parseNum(contingent)) * 100,
  ) / 100
}

/**
 * 按新增持股比例享有的持续计算净资产公允价值份额
 * ④ = ③ × ①（③=自购买日持续计算净资产FV，①=新增持股比例）
 * G7-10 第2节 购买少数股东股权
 * @source CAS33 权益性交易，不确认商誉
 */
export function calcNciPurchaseShare(netAssetsFV: number, addedRatio: number): number {
  return Math.round((parseNum(netAssetsFV) * parseNum(addedRatio)) * 100) / 100
}

/**
 * 购买少数股权合并报表权益调整
 * ⑤ = ② − ④（购买成本 − 按新增比例享有的净资产份额）
 * 差额调整资本公积，不足冲减留存收益；不确认商誉/损益
 * @source CAS33 母公司购买子公司少数股权
 */
export function calcNciEquityAdjustment(purchaseCost: number, shareOfNetAssets: number): number {
  return Math.round((parseNum(purchaseCost) - parseNum(shareOfNetAssets)) * 100) / 100
}

// ═══ G7-10 §3: 处置子公司权益但不丧失控制权 ═══

/**
 * 个别报表投资收益（成本法）
 * ⑤ = ④ − ① × ③ / ②
 * （处置对价 − 处置日长投账面 × 减少持股比例 / 原持股比例）
 * @source CAS2 成本法部分处置仍保持控制
 */
export function calcPartialDisposalIndividualGain(
  consideration: number,
  bookValue: number,
  reducedRatio: number,
  originalRatio: number,
): number {
  const orig = parseNum(originalRatio)
  if (orig === 0) return 0
  const disposedCarrying = (parseNum(bookValue) * parseNum(reducedRatio)) / orig
  return Math.round((parseNum(consideration) - disposedCarrying) * 100) / 100
}

/**
 * 合并报表：按减少持股比例享有的持续计算净资产公允价值份额
 * ⑦ = ⑥ × ③
 * @source CAS33 不丧失控制权的处置
 */
export function calcPartialDisposalConsolShare(netAssetsFV: number, reducedRatio: number): number {
  return Math.round((parseNum(netAssetsFV) * parseNum(reducedRatio)) * 100) / 100
}

/**
 * 合并报表权益调整（不确认损益）
 * ⑧ = ④ − ⑦（处置对价 − 减少比例对应净资产份额）
 * @source CAS33 权益性交易
 */
export function calcPartialDisposalConsolAdjustment(consideration: number, consolShare: number): number {
  return Math.round((parseNum(consideration) - parseNum(consolShare)) * 100) / 100
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
