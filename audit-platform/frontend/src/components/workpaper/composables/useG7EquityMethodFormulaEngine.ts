/**
 * G7 长期股权投资(权益法组) — 公式引擎（权益法核算全流程）
 *
 * 9个纯函数 + parseNum，无副作用、无Vue响应式依赖，支持 fast-check PBT 验证。
 *
 * 核心公式链：
 * - 初始投资成本 = 支付对价 + 直接相关费用 (G7-13)
 * - 享有净资产份额 = 净资产公允价值 × 持股比例 (G7-13)
 * - 商誉/营业外收入 = 初始成本 - 享有份额 (G7-13)
 * - 调整后净利润 = 报告净利润 - 内部交易 - FV折旧 + 政策调整 + 其他 (G7-14)
 * - 持股比例份额 = 值 × 持股比例 (G7-14, 通用乘法)
 * - 权益法余额递推 = 期初 + 投资收益 + OCI + 其他权益 - 股利 (G7-14)
 * - 未实现利润 = 交易金额 × 毛利率 (G7-15)
 * - 应抵销金额 = 顺流:全额 / 逆流:×比例 (G7-15)
 * - 减值金额 = MAX(0, 账面价值 - 可收回金额) (G7-17)
 *
 * Spec: .kiro/specs/g7-long-term-equity-method/
 * Requirements: 7.1, 4.2, 4.3, 4.4, 5.2, 5.3, 5.5, 5.6, 5.7, 6.2, 6.3, 6.6
 */

// ═══ parseNum: 安全数值转换（null/undefined/NaN/空串/'  '/'abc' → 0）═══

/**
 * 安全数值转换：null/undefined/NaN/空字符串/'  '/'abc' → 0; 有效数值→原值
 * @source G7权益法公式引擎通用辅助，所有公式输入前调用
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

// ═══ P1: 初始投资成本 = 支付对价 + 直接相关费用 ═══

/**
 * 初始投资成本 = 支付对价 + 直接相关费用
 * G7-13 Tab1 初始计量
 * @source CAS2 初始投资成本确定，Requirements 4.2
 */
export function calcInvestmentCost(consideration: number, directCosts: number): number {
  return Math.round((parseNum(consideration) + parseNum(directCosts)) * 100) / 100
}

// ═══ P2: 享有可辨认净资产公允价值份额 = 净资产FV × 持股比例 ═══

/**
 * 享有可辨认净资产公允价值份额 = 净资产公允价值 × 持股比例
 * G7-13 Tab1 初始计量
 * @source CAS2 投资成本测试，Requirements 4.3
 */
export function calcShareOfNetAssets(netAssetFV: number, ratio: number): number {
  return Math.round((parseNum(netAssetFV) * parseNum(ratio)) * 100) / 100
}

// ═══ P3: 商誉/营业外收入 = 初始成本 - 享有份额 ═══

/**
 * 商誉/营业外收入差额 = 初始投资成本 - 享有份额
 * 正值=商誉（借方资产），负值=营业外收入（贷方收益）
 * G7-13 Tab1 差额列
 * @source CAS2 投资成本测试商誉判断，Requirements 4.4
 */
export function calcGoodwill(initialCost: number, shareOfNetAssets: number): number {
  return Math.round((parseNum(initialCost) - parseNum(shareOfNetAssets)) * 100) / 100
}

// ═══ P4: 调整后净利润 = 报告净利润 - 内部交易 - FV折旧 + 政策调整 + 其他 ═══

/**
 * 调整后净利润 = 报告净利润 - 内部交易抵销 - 公允价值折旧摊销 + 会计政策调整 + 其他调整
 * G7-14 Tab1 净利润调整（±用加法表示，负数即减）
 * @source CAS2 权益法核算前净利润调整，Requirements 5.2
 */
export function calcAdjustedNetProfit(
  reported: number,
  internalTrans: number,
  fvDepreciation: number,
  policyAdj: number,
  other: number
): number {
  return Math.round((
    parseNum(reported)
    - parseNum(internalTrans)
    - parseNum(fvDepreciation)
    + parseNum(policyAdj)
    + parseNum(other)
  ) * 100) / 100
}

// ═══ P5: 持股比例份额 = 值 × 持股比例（通用乘法）═══

/**
 * 持股比例份额 = 值 × 持股比例
 * 通用乘法函数，适用于：投资收益份额、OCI份额、其他权益份额
 * G7-14 Tab1/Tab2
 * @source CAS2 权益法按比例确认，Requirements 5.3, 5.5, 5.6
 */
export function calcEquityShare(value: number, ratio: number): number {
  return Math.round((parseNum(value) * parseNum(ratio)) * 100) / 100
}

// ═══ P6: 权益法余额递推 = 期初 + 投资收益 + OCI + 其他权益 - 股利 ═══

/**
 * 期末权益法余额 = 期初 + 投资收益 + OCI份额 + 其他权益份额 - 利润分配(股利)
 * G7-14 Tab2 期末权益法余额
 * @source CAS2 权益法账面递推公式，Requirements 5.7
 */
export function calcEquityMethodBalance(
  opening: number,
  income: number,
  oci: number,
  equityChange: number,
  dividend: number
): number {
  return Math.round((
    parseNum(opening)
    + parseNum(income)
    + parseNum(oci)
    + parseNum(equityChange)
    - parseNum(dividend)
  ) * 100) / 100
}

// ═══ P7（未实现利润）: 交易金额 × 毛利率 ═══

/**
 * 未实现利润 = 交易金额 × 毛利率
 * G7-15 内部交易抵销
 * @source CAS2 内部交易未实现利润计算，Requirements 6.2
 */
export function calcUnrealizedProfit(transactionAmount: number, grossMargin: number): number {
  return Math.round((parseNum(transactionAmount) * parseNum(grossMargin)) * 100) / 100
}

// ═══ P8（应抵销金额）: 顺流=全额 / 逆流=×比例 ═══

/**
 * 应抵销金额：
 * - 顺流交易(投资方→被投资方)：应抵销 = 未实现利润（全额）
 * - 逆流交易(被投资方→投资方)：应抵销 = 未实现利润 × 持股比例
 * G7-15 内部交易抵销
 * @source CAS2 内部交易顺流/逆流差异化处理，Requirements 6.3
 */
export function calcEliminationAmount(
  direction: 'downstream' | 'upstream',
  unrealizedProfit: number,
  ratio: number
): number {
  const profit = parseNum(unrealizedProfit)
  if (direction === 'downstream') {
    return Math.round(profit * 100) / 100
  }
  return Math.round((profit * parseNum(ratio)) * 100) / 100
}

// ═══ P9（减值金额）: MAX(0, 账面价值 - 可收回金额) ═══

/**
 * 减值金额 = MAX(0, 账面价值 - 可收回金额)
 * 减值永远非负（可收回>账面时不存在减值转回到超过原账面）
 * G7-17 减值测试
 * @source CAS8 资产减值准则，Requirements 6.6
 */
export function calcImpairmentAmount(bookValue: number, recoverableAmount: number): number {
  const diff = parseNum(bookValue) - parseNum(recoverableAmount)
  return Math.round(Math.max(0, diff) * 100) / 100
}
