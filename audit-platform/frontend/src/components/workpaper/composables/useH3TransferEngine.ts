/**
 * H3 投资性房地产 — 互转引擎（纯函数，无副作用）
 * 四方向转换：自用→投资 / 投资→自用 / 在建→投资 / 存货→投资
 * CAS3 第12-15条互转会计处理
 * Spec: .kiro/specs/h3-investment-property/
 * Requirements: 7.2-7.5, 12.2
 */

// ---------- 净值计算（Excel ①②③④ / ⑤⑥⑦⑧） ----------

/** 净值 = 原值 − 累计折旧/摊销 − 减值准备 */
export function calcNetValue(
  original: number,
  accumulatedDepreciation: number,
  impairmentProvision: number,
): number {
  return original - accumulatedDepreciation - impairmentProvision
}

// ---------- 部分转换金额（应用转换比例） ----------

/**
 * 实际转换金额 = 基础金额 × 转换比例%
 * 用于部分转换场景（如一栋楼50%自用50%出租，只转换其中一半）
 */
export function applyConversionRatio(baseAmount: number, ratioPercent: number): number {
  if (ratioPercent <= 0 || ratioPercent > 100) return baseAmount
  return baseAmount * (ratioPercent / 100)
}

// ---------- 自用 → 投资性房地产 ----------

/**
 * 自用→投资(成本模式): 以账面净值 × 转换比例转入，不产生损益
 */
export function calcSelfToInvestCost(netValue: number, ratioPercent = 100): number {
  return applyConversionRatio(netValue, ratioPercent)
}

/**
 * 自用→投资(公允价值模式): CAS3第13条
 * - 公允 > 账面：差额计入其他综合收益(OCI)
 * - 公允 < 账面：差额计入当期损益(PL)
 * - 公允 = 账面：OCI=0, PL=0
 * 公允价值和账面净值均已按转换比例折算后传入
 */
export function calcSelfToInvestFair(
  bookValue: number,
  fairValue: number,
): { oci: number; pl: number } {
  const diff = fairValue - bookValue
  return {
    oci: Math.max(diff, 0),
    pl: Math.min(diff, 0),
  }
}

// ---------- 投资性房地产 → 自用 ----------

/**
 * 投资→自用(公允价值模式): 转换日公允价值作为自用资产入账价值
 */
export function calcInvestToSelfFair(fairValue: number, ratioPercent = 100): number {
  return applyConversionRatio(fairValue, ratioPercent)
}

/** @deprecated 使用 calcInvestToSelfFair */
export function calcInvestToSelf(fairValue: number): number {
  return calcInvestToSelfFair(fairValue)
}

/**
 * 投资→自用(成本模式): 以投资性房地产账面净值 × 比例转入自用
 */
export function calcInvestToSelfCost(bookValue: number, ratioPercent = 100): number {
  return applyConversionRatio(bookValue, ratioPercent)
}

// ---------- 在建工程 → 投资性房地产 ----------

/**
 * 在建→投资(成本模式): 以在建工程账面价值作为入账价值，直接转入不产生损益
 */
export function calcCipToInvestCost(cipBookValue: number, ratioPercent = 100): number {
  return applyConversionRatio(cipBookValue, ratioPercent)
}

/**
 * 在建→投资(公允价值模式): 以转换日公允价值入账
 * entryValue = fairValue × 比例；diff = entry - cip × 比例（计入当期损益）
 */
export function calcCipToInvestFair(
  cipBookValue: number,
  fairValue: number,
  ratioPercent = 100,
): { entryValue: number; diff: number } {
  const entry = applyConversionRatio(fairValue, ratioPercent)
  const cipPart = applyConversionRatio(cipBookValue, ratioPercent)
  return {
    entryValue: entry,
    diff: entry - cipPart,
  }
}

// ---------- 存货 → 投资性房地产（CAS3 第14条） ----------

/**
 * 存货→投资(成本模式): 以存货账面价值转入，不产生损益（CAS3第14条）
 */
export function calcInventoryToInvestCost(inventoryBookValue: number, ratioPercent = 100): number {
  return applyConversionRatio(inventoryBookValue, ratioPercent)
}

/**
 * 存货→投资(公允价值模式): CAS3第14条
 * 以转换日公允价值入账；公允 vs 账面差额计入当期损益（非OCI）
 */
export function calcInventoryToInvestFair(
  inventoryBookValue: number,
  fairValue: number,
  ratioPercent = 100,
): { entryValue: number; pl: number } {
  const entry = applyConversionRatio(fairValue, ratioPercent)
  const bookPart = applyConversionRatio(inventoryBookValue, ratioPercent)
  return {
    entryValue: entry,
    pl: entry - bookPart,
  }
}

// ---------- 转出 = 转入 差额验证 ----------

/**
 * 转出=转入差额：验证互转金额一致性
 * 返回0表示平衡（转出方金额=转入方金额）
 * 非0表示存在差异，需红色高亮
 */
export function calcTransferDiff(transferOut: number, transferIn: number): number {
  return transferOut - transferIn
}

// ---------- 重要性预警 ----------

/**
 * 判断单笔转换金额是否超过重要性水平
 */
export function isAboveMateriality(amount: number, materialityThreshold: number): boolean {
  return materialityThreshold > 0 && Math.abs(amount) >= materialityThreshold
}

/**
 * 转换金额占资产总额比率
 */
export function calcTransferRatio(transferTotal: number, assetTotal: number): number {
  if (assetTotal <= 0) return 0
  return Math.abs(transferTotal) / assetTotal
}

// ---------- 产权差异 ----------

/**
 * 产权差异 = 账面价值 - 证载价值
 * 用于H3-12产权核对表验证产权登记与账面的一致性
 */
export function calcTitleDiff(bookValue: number, certValue: number): number {
  return bookValue - certValue
}
