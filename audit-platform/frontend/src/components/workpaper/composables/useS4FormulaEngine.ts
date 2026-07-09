/**
 * useS4FormulaEngine — S4 非货币性资产交换公式引擎
 *
 * 纯函数，无副作用、无 Vue reactivity、确定性输出。
 *
 * 本引擎覆盖：
 * - 交换损益 gainLoss = outFairValue - outBookValue（换出资产损益）
 * - 换入成本 inCost = outFairValue + taxes（以公允价值计量口径）
 * - 准则适用性判断 judgeApplicable = 6项排除全为false → 适用
 * - 商业实质判断 judgeCommercialSubstance = cashflowDifferent
 *
 * 源模板公式：
 * - 审定表S4-1: 损益=换出资产公允-换出资产账面; 换入成本=换出公允+税费
 * - 商业实质S4-2: =IF(AND(B8="不属于",...,G8="不属于"),"是","否")
 *
 * Spec: .kiro/specs/s-special-transaction-workpapers/ Task 3.1
 * Requirements: 2.2, 2.3, 2.4
 */

// ─── helpers ────────────────────────────────────────────────

/** 安全数值解析：null/undefined/NaN/空→0 */
export function parseNum(val: string | number | null | undefined): number {
  if (val === null || val === undefined || val === '') return 0
  const n = typeof val === 'number' ? val : Number(val)
  return Number.isFinite(n) ? n : 0
}

// ─── interfaces ─────────────────────────────────────────────

export interface S4ExchangeInput {
  inFairValue: number   // 换入资产公允价值
  outFairValue: number  // 换出资产公允价值
  outBookValue: number  // 换出资产账面价值
  taxes: number         // 相关税费
}

export interface CommercialSubstanceInput {
  exclusions: boolean[]      // 6项排除情形 (true=属于该情形 → 不适用)
  cashflowDifferent: boolean // 现金流量风险/时间/金额显著不同
}

// ─── 1. 交换损益 + 换入成本（Property P2） ───────────────────

/**
 * 计算非货币性资产交换损益与换入资产成本
 *
 * 公式（以公允价值计量口径）：
 * - gainLoss = outFairValue - outBookValue（换出资产损益）
 * - inCost = outFairValue + taxes（换入资产成本）
 *
 * 来源：审定表S4-1
 *
 * @param input - S4ExchangeInput
 * @returns { gainLoss, inCost }
 */
export function calcExchangeGainLoss(input: S4ExchangeInput): { gainLoss: number; inCost: number } {
  const outFairValue = parseNum(input.outFairValue)
  const outBookValue = parseNum(input.outBookValue)
  const taxes = parseNum(input.taxes)

  return {
    gainLoss: outFairValue - outBookValue,
    inCost: outFairValue + taxes,
  }
}

// ─── 2. 准则适用性判断（Property P3） ───────────────────────

/**
 * 判断是否适用非货币性资产交换准则
 *
 * 源公式：=IF(AND(B8="不属于",...,G8="不属于"),"是","否")
 * 即：6项排除情形全部为false（"不属于"）→ 适用准则（返回true）
 *
 * 来源：商业实质判断S4-2
 *
 * @param input - CommercialSubstanceInput
 * @returns true = 适用准则（全部排除情形均为"不属于"）
 */
export function judgeApplicable(input: CommercialSubstanceInput): boolean {
  const exclusions = input.exclusions
  if (!Array.isArray(exclusions) || exclusions.length !== 6) return false
  return exclusions.every(e => e === false)
}

// ─── 3. 商业实质判断（Property P3） ─────────────────────────

/**
 * 判断是否具有商业实质
 *
 * 商业实质 = 未来现金流量在风险/时间/金额方面显著不同
 * 直接返回 cashflowDifferent 值
 *
 * 来源：商业实质判断S4-2
 *
 * @param input - CommercialSubstanceInput
 * @returns true = 具有商业实质
 */
export function judgeCommercialSubstance(input: CommercialSubstanceInput): boolean {
  return input.cashflowDifferent === true
}
