/**
 * I3 商誉 — 公式引擎（纯函数，无副作用）
 * 科目：1711商誉（借方/资产类）
 * 核心特殊：**商誉不摊销！** 仅年度减值测试
 * - 期末 = 期初 + 新并购 - 减值（只减不增，无摊销）
 * - 减值先冲商誉（至零为止），剩余按比例分摊至资产组其他资产
 * - 商誉减值不可转回
 * Spec: .kiro/specs/i3-goodwill/
 */

/** 审定数 = 未审数 + AJE调整 + RJE重分类 */
export function calcAuditedAmount(unadj: number, aje: number, rje: number): number {
  return unadj + aje + rje
}

/**
 * 商誉期末余额（**不摊销！**）
 * 期末 = 期初 + 新并购(通常0) - 减值
 * 注意：商誉无摊销项，与I1（有摊销）根本不同
 */
export function calcGoodwillEndBalance(begin: number, newAcquisition: number, impairment: number): number {
  return begin + newAcquisition - impairment
}

/**
 * 商誉净值 = 原值(初始确认金额) - 累计减值准备
 * 商誉无累计摊销，净值仅受减值影响
 */
export function calcGoodwillNetValue(originalCost: number, accImpairment: number): number {
  return originalCost - accImpairment
}

/**
 * 初始商誉 = 合并成本 - 被购方可辨认净资产公允价值份额
 * CAS20企业合并：非同一控制下合并产生的商誉
 */
export function calcInitialGoodwill(mergerCost: number, netAssetFairValue: number): number {
  return mergerCost - netAssetFairValue
}

/** 合计 = SUM(数组)；空数组返回0 */
export function calcSubtotal(arr: number[]): number {
  return arr.reduce((a, b) => a + b, 0)
}

/**
 * 单项其他资产可承担的最大减值（CAS8 §23）：
 * 抵减后账面不得低于可收回金额；未填可收回时上限=账面价值。
 */
export function calcAssetAllocCap(
  bookValue: number,
  recoverableAmount?: number | null,
): number {
  const book = Math.max(0, bookValue)
  if (recoverableAmount == null || !Number.isFinite(recoverableAmount)) return book
  return Math.max(0, book - Math.max(0, recoverableAmount))
}

/**
 * 减值分摊（CAS8两步法）
 *
 * 规则：
 *   Step 1: 先冲商誉 → 商誉减至0为止（goodwillImpairment = MIN(totalImpairment, goodwillAmount)）
 *   Step 2: 剩余减值 → 按资产组其他资产账面价值比例分摊
 *
 * 约束：
 *   - 商誉减值不可转回
 *   - 每项其他资产分摊不超过其账面价值，且抵减后不低于可收回金额（可选 recoverableAmount）
 *
 * @param totalImpairment 资产组总减值金额（≥0）
 * @param goodwillAmount  商誉账面价值（≥0）
 * @param otherAssets     资产组其他资产列表（name + bookValue + 可选 recoverableAmount）
 * @returns 商誉承担的减值 + 其他各资产分摊明细
 */
export function calcImpairmentAllocation(
  totalImpairment: number,
  goodwillAmount: number,
  otherAssets: { name: string; bookValue: number; recoverableAmount?: number | null }[]
): { goodwillImpairment: number; otherAllocations: { name: string; amount: number }[] } {
  // Step 1: 先冲商誉
  const goodwillImpairment = Math.min(Math.max(0, totalImpairment), Math.max(0, goodwillAmount))

  // Step 2: 剩余减值按比例分摊至其他资产（受可收回金额下限约束）
  let remainingImpairment = Math.max(0, totalImpairment) - goodwillImpairment

  const caps = otherAssets.map(a => calcAssetAllocCap(a.bookValue, a.recoverableAmount))
  const totalCap = caps.reduce((s, c) => s + c, 0)

  let otherAllocations: { name: string; amount: number }[]

  if (remainingImpairment <= 0 || totalCap <= 0) {
    otherAllocations = otherAssets.map(a => ({ name: a.name, amount: 0 }))
  } else {
    // 先按账面比例试算，再按 cap 截断；截断后的差额按剩余 cap 再分配一轮
    const totalBook = otherAssets.reduce((s, a) => s + Math.max(0, a.bookValue), 0)
    otherAllocations = otherAssets.map((a, i) => {
      const raw = totalBook > 0
        ? (Math.max(0, a.bookValue) / totalBook) * remainingImpairment
        : 0
      return { name: a.name, amount: Math.min(caps[i], raw) }
    })

    let allocated = otherAllocations.reduce((s, a) => s + a.amount, 0)
    let leftover = remainingImpairment - allocated
    if (leftover > 1e-8) {
      // 将未分完部分按剩余能力再分配
      const residualCaps = caps.map((c, i) => Math.max(0, c - otherAllocations[i].amount))
      const residualTotal = residualCaps.reduce((s, c) => s + c, 0)
      if (residualTotal > 0) {
        otherAllocations = otherAllocations.map((a, i) => ({
          name: a.name,
          amount: a.amount + (residualCaps[i] / residualTotal) * leftover,
        }))
      }
    }
  }

  return { goodwillImpairment, otherAllocations }
}
