/**
 * K6 持有待售 — 减值孰低法引擎（纯函数）
 *
 * CAS42 持有待售后续计量：
 *   持有待售资产按 **账面价值与公允价值减去出售费用后的净额孰低** 计量。
 *
 * 核心公式：
 * - 公允价值净额 = 公允价值 - 预计出售费用 （可为负数，表示出售费用超过公允价值）
 * - 减值金额 = MAX(0, 账面价值 - 公允价值净额) （孰低法，减值≥0）
 * - 本期应补提 = 减值金额 - 已计提减值 （可为负数表示转回，但转回有上限）
 * - 处置组减值分摊：先抵减商誉，余额按账面比例分摊至组内非流动资产
 * - 分摊比例 = 组内资产账面 / 组账面合计 （组合计为0时兜底返回0）
 *
 * 设计原则：纯函数，无Vue响应式，无副作用，可PBT验证
 * 所有函数对 NaN / undefined 输入视为 0 处理
 *
 * Spec: .kiro/specs/k6-held-for-sale/ Requirements 5.2-5.4, 6.2-6.3, 9.4-9.6
 */

// ─── Helpers ────────────────────────────────────────────────────────────────

/** 将 NaN / undefined / null 转为 0 */
function safeNum(v: unknown): number {
  if (v === null || v === undefined) return 0
  const n = Number(v)
  return Number.isNaN(n) ? 0 : n
}

// ─── Types ──────────────────────────────────────────────────────────────────

/** 处置组减值分摊结果 */
export interface GroupImpairmentAllocation {
  /** 商誉抵减金额（先冲商誉） */
  goodwillDeduction: number
  /** 分摊至该资产的减值金额 */
  itemAllocation: number
}

// ─── 公式函数 ───────────────────────────────────────────────────────────────

/**
 * 公允价值净额 = 公允价值 - 预计出售费用
 *
 * ⚠️ 结果可为负数！表示出售费用超过公允价值，
 * 此时减值金额将等于全部账面价值。
 *
 * @param fairValue 公允价值
 * @param sellingCost 预计出售费用
 * @returns 公允价值净额
 *
 * Requirements 5.2, 9.4
 */
export function calcFairValueNet(fairValue: number, sellingCost: number): number {
  return safeNum(fairValue) - safeNum(sellingCost)
}

/**
 * 减值金额 = MAX(0, 账面价值 - 公允价值净额)
 *
 * 孰低法：账面价值高于公允价值净额时确认减值。
 * 若公允价值净额 ≥ 账面价值，则无需计提减值（返回 0）。
 * 结果保证 ≥ 0。
 *
 * @param bookValue 账面价值
 * @param fairValueNet 公允价值净额（= 公允价值 - 出售费用）
 * @returns 减值金额（≥ 0）
 *
 * Requirements 5.3, 9.5
 */
export function calcImpairment(bookValue: number, fairValueNet: number): number {
  return Math.max(0, safeNum(bookValue) - safeNum(fairValueNet))
}

/**
 * 本期应补提 = 减值金额 - 已计提减值
 *
 * 正数表示需补提减值，负数表示可转回（但CAS42转回有上限：
 * 不得超过假设不划分持有待售时确认的折旧/摊销等金额调整后的账面价值）
 *
 * @param impairmentAmount 本期应确认减值总额
 * @param existingProvision 已计提减值准备余额
 * @returns 本期应补提金额（正=补提；负=转回）
 *
 * Requirements 5.4
 */
export function calcAdditionalProvision(impairmentAmount: number, existingProvision: number): number {
  return safeNum(impairmentAmount) - safeNum(existingProvision)
}

/**
 * 分摊比例 = 组内资产账面 / 组账面合计
 *
 * 处置组减值分摊时，先抵减商誉，剩余减值按各非流动资产
 * 账面价值占组内非流动资产账面合计的比例进行分摊。
 *
 * 兜底：组账面合计为 0 时返回 0（避免除零错误）
 *
 * @param itemBook 组内该资产的账面价值
 * @param groupBook 组账面合计（不含商誉）
 * @returns 分摊比例（0~1 之间，组合计为0时返回0）
 *
 * Requirements 6.3, 9.6
 */
export function calcAllocationRatio(itemBook: number, groupBook: number): number {
  const g = safeNum(groupBook)
  if (g === 0) return 0
  return safeNum(itemBook) / g
}

/**
 * 处置组减值分摊：先抵商誉，余额按比例分摊
 *
 * CAS42处置组减值顺序：
 * 1. 先抵减处置组内商誉的账面价值（商誉减值不可转回）
 * 2. 剩余减值按组内各非流动资产账面价值比例分摊
 *
 * @param groupImpairment 处置组整体减值金额
 * @param goodwillBook 组内商誉账面价值
 * @param itemBook 该资产的账面价值
 * @param groupBookExGoodwill 组内非流动资产账面合计（不含商誉）
 * @returns { goodwillDeduction: 商誉抵减金额, itemAllocation: 分摊至该资产的减值 }
 *
 * Requirements 6.2, 6.3
 */
export function calcGroupImpairmentAllocation(
  groupImpairment: number,
  goodwillBook: number,
  itemBook: number,
  groupBookExGoodwill: number
): GroupImpairmentAllocation {
  const imp = safeNum(groupImpairment)
  const gw = safeNum(goodwillBook)

  // 先抵商誉：最多抵减到商誉归零
  const goodwillDeduction = Math.min(imp, gw)
  // 余额分摊给非流动资产
  const remaining = Math.max(0, imp - goodwillDeduction)
  // 按比例分摊
  const ratio = calcAllocationRatio(itemBook, groupBookExGoodwill)
  const itemAllocation = remaining * ratio

  return { goodwillDeduction, itemAllocation }
}
