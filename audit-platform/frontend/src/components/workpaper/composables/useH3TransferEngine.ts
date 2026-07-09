/**
 * H3 投资性房地产 — 互转引擎（纯函数，无副作用）
 * 三方向转换：自用→投资 / 投资→自用 / 在建→投资
 * CAS3 第12-15条互转会计处理
 * Spec: .kiro/specs/h3-investment-property/
 * Requirements: 7.2-7.5, 12.2
 */

// ---------- 自用 → 投资性房地产（公允价值模式） ----------

/**
 * 自用→投资(公允价值模式): CAS3第13条
 * - 公允 > 账面：差额计入其他综合收益(OCI)
 * - 公允 < 账面：差额计入当期损益(PL)
 * - 公允 = 账面：OCI=0, PL=0
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
 * 投资→自用: 转换日公允价值作为自用资产的入账价值
 * 无论原计量模式，一律以公允价值入账
 */
export function calcInvestToSelf(fairValue: number): number {
  return fairValue
}

// ---------- 在建工程 → 投资性房地产 ----------

/**
 * 在建→投资(成本模式): 以在建工程账面价值作为入账价值
 * 直接转入，不产生损益
 */
export function calcCipToInvestCost(cipBookValue: number): number {
  return cipBookValue
}

/**
 * 在建→投资(公允价值模式): 以转换日公允价值入账
 * entryValue = fairValue（入账价值）
 * diff = fairValue - cipBookValue（公允与账面的差额，计入当期损益）
 */
export function calcCipToInvestFair(
  cipBookValue: number,
  fairValue: number,
): { entryValue: number; diff: number } {
  return {
    entryValue: fairValue,
    diff: fairValue - cipBookValue,
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

// ---------- 产权差异 ----------

/**
 * 产权差异 = 账面价值 - 证载价值
 * 用于H3-12产权核对表验证产权登记与账面的一致性
 */
export function calcTitleDiff(bookValue: number, certValue: number): number {
  return bookValue - certValue
}
