/**
 * useS15FormulaEngine — S15 每股收益与净资产收益率公式引擎
 *
 * 纯函数，无副作用、无 Vue reactivity、确定性输出。
 *
 * 本引擎覆盖：
 * - 加权平均股数 b = b0 + b1 + (c1×c2/m0 + d1×d2/m0) - (e1×e2/m0) - b4
 * - 基本每股收益 eps = a1 / b, epsEx = a2 / b
 * - 稀释每股收益 = (P + (dilutionInterest - conversionCost)×(1-taxRate)) / (b + dilutionShares×dilutionMonths/m0)
 * - 全面摊薄 ROE = P / E
 * - 加权平均 ROE = P / (E0 + NP/2 + Ei×Mi/M0 - Ej×Mj/M0 + Ek×Mk/M0)
 *
 * Spec: .kiro/specs/s-estimate-calculation-workpapers/ Task 3.1
 * Requirements: 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.3, 3.5
 */

import { computed, type Ref } from 'vue'

// ─── helpers ────────────────────────────────────────────────

/** 安全数值解析：null/undefined/NaN/空→0 */
export function parseNum(val: string | number | null | undefined): number {
  if (val === null || val === undefined || val === '') return 0
  const n = typeof val === 'number' ? val : Number(val)
  return Number.isFinite(n) ? n : 0
}

// ─── interfaces ─────────────────────────────────────────────

export interface EpsInput {
  npAttrParent: number       // 归母净利润 a1
  npAttrParentEx: number     // 扣非归母净利润 a2
  shareOpening: number       // 期初股份 b0
  shareCapitalized: number   // 转增/股票股利 b1
  newIssue: { count: number; monthsToEnd: number }   // c1, c2
  debtToEquity: { count: number; monthsToEnd: number } // d1, d2
  repurchase: { count: number; monthsToEnd: number }   // e1, e2
  merged: number             // 并股 b4
  periodMonths: number       // m0
}

export interface DilutedEpsInput {
  npAttrParent: number       // 归母净利润 P
  weightedAvgShares: number  // 基本加权平均股数 b
  dilutionInterest: number   // 已确认为费用的稀释性潜在普通股利息
  conversionCost: number     // 转换费用
  taxRate: number            // 所得税率（小数，如 0.25）
  dilutionShares: number     // 稀释性潜在普通股数
  dilutionMonths: number     // 稀释性潜在普通股存续月份数
  periodMonths: number       // 报告期月份数 m0
}

export interface RoeInput {
  np: number                 // 归母净利润 P
  npEx: number               // 扣非归母净利润
  e0: number                 // 期初净资产 E0
  eEnd: number               // 期末净资产
  minorityEquity: number     // 少数股东权益
  ei: number                 // 新增净资产 Ei
  mi: number                 // 新增净资产下月起至期末月份 Mi
  ej: number                 // 减少净资产 Ej
  mj: number                 // 减少净资产下月起至期末月份 Mj
  ek: number                 // 其他增减净资产 Ek
  mk: number                 // 其他增减下月起至期末月份 Mk
  m0: number                 // 报告期月份数 M0
}

// ─── 1. 加权平均股数（Property P2） ───────────────────────────

/**
 * 计算发行在外普通股加权平均数
 *
 * 公式：b = b0 + b1 + (c1×c2/m0 + d1×d2/m0) - (e1×e2/m0) - b4
 *
 * 来源：S15-2 基本每股收益计算表
 * - b0: 期初股份总数
 * - b1: 公积金转增/股票股利增加
 * - c1×c2/m0: 发行新股加权
 * - d1×d2/m0: 债转股加权
 * - e1×e2/m0: 回购股份加权（减项）
 * - b4: 并股数（减项）
 *
 * @param i - EpsInput
 * @returns 加权平均股数（m0<=0 时返回 0）
 */
export function calcWeightedAvgShares(i: EpsInput): number {
  const m0 = parseNum(i.periodMonths)
  if (m0 <= 0) return 0

  const b0 = parseNum(i.shareOpening)
  const b1 = parseNum(i.shareCapitalized)
  const c1 = parseNum(i.newIssue?.count)
  const c2 = parseNum(i.newIssue?.monthsToEnd)
  const d1 = parseNum(i.debtToEquity?.count)
  const d2 = parseNum(i.debtToEquity?.monthsToEnd)
  const e1 = parseNum(i.repurchase?.count)
  const e2 = parseNum(i.repurchase?.monthsToEnd)
  const b4 = parseNum(i.merged)

  return b0 + b1 + (c1 * c2 / m0 + d1 * d2 / m0) - (e1 * e2 / m0) - b4
}

// ─── 2. 基本每股收益（Property P3） ─────────────────────────

/**
 * 计算基本每股收益
 *
 * 公式：
 * - eps = a1 / b（归母净利润 / 加权平均股数）
 * - epsEx = a2 / b（扣非归母净利润 / 加权平均股数）
 *
 * 来源：S15-2 row23/row24
 *
 * @param i - EpsInput
 * @returns { eps, epsEx, unable }，unable=true 表示加权股数=0 或 m0<=0
 */
export function calcBasicEps(i: EpsInput): { eps: number; epsEx: number; unable: boolean } {
  const b = calcWeightedAvgShares(i)
  if (b === 0) {
    return { eps: 0, epsEx: 0, unable: true }
  }
  const a1 = parseNum(i.npAttrParent)
  const a2 = parseNum(i.npAttrParentEx)
  return {
    eps: a1 / b,
    epsEx: a2 / b,
    unable: false,
  }
}

// ─── 3. 稀释每股收益 ───────────────────────────────────────

/**
 * 计算稀释每股收益（S15-3 / S15-4）
 *
 * 公式：
 * dilutedEps = (P + (dilutionInterest - conversionCost) × (1 - taxRate))
 *            / (b + dilutionShares × dilutionMonths / m0)
 *
 * 分子加回已确认为费用的稀释性潜在普通股利息，扣除转换费用，税后调整。
 * 分母加入稀释性潜在普通股的加权数。
 *
 * @param i - DilutedEpsInput
 * @returns { dilutedEps, unable }
 */
export function calcDilutedEps(i: DilutedEpsInput): { dilutedEps: number; unable: boolean } {
  const m0 = parseNum(i.periodMonths)
  if (m0 <= 0) {
    return { dilutedEps: 0, unable: true }
  }

  const p = parseNum(i.npAttrParent)
  const b = parseNum(i.weightedAvgShares)
  const interest = parseNum(i.dilutionInterest)
  const cost = parseNum(i.conversionCost)
  const taxRate = parseNum(i.taxRate)
  const dShares = parseNum(i.dilutionShares)
  const dMonths = parseNum(i.dilutionMonths)

  const numerator = p + (interest - cost) * (1 - taxRate)
  const denominator = b + dShares * dMonths / m0

  if (denominator === 0) {
    return { dilutedEps: 0, unable: true }
  }

  return {
    dilutedEps: numerator / denominator,
    unable: false,
  }
}

// ─── 4. 净资产收益率（Property P4） ─────────────────────────

/**
 * 计算净资产收益率（全面摊薄 + 加权平均）
 *
 * 公式：
 * - 全面摊薄 ROE = P / E，其中 E = eEnd - minorityEquity（归属公司普通股股东期末净资产）
 * - 加权平均 ROE = P / (E0 + NP/2 + Ei×Mi/M0 - Ej×Mj/M0 + Ek×Mk/M0)
 *
 * 来源：S15-4 净资产收益率计算表
 *
 * @param i - RoeInput
 * @returns { fullyDiluted, weightedAvg, unable }
 */
export function calcDilutedRoe(i: RoeInput): {
  fullyDiluted: number
  weightedAvg: number
  unable: boolean
} {
  const m0 = parseNum(i.m0)
  if (m0 <= 0) {
    return { fullyDiluted: 0, weightedAvg: 0, unable: true }
  }

  const np = parseNum(i.np)
  const eEnd = parseNum(i.eEnd)
  const minority = parseNum(i.minorityEquity)
  const e0 = parseNum(i.e0)
  const ei = parseNum(i.ei)
  const mi = parseNum(i.mi)
  const ej = parseNum(i.ej)
  const mj = parseNum(i.mj)
  const ek = parseNum(i.ek)
  const mk = parseNum(i.mk)

  // 全面摊薄：E = 期末净资产 - 少数股东权益
  const e = eEnd - minority
  if (e === 0) {
    return { fullyDiluted: 0, weightedAvg: 0, unable: true }
  }

  const fullyDiluted = np / e

  // 加权平均净资产 = E0 + NP/2 + Ei×Mi/M0 - Ej×Mj/M0 + Ek×Mk/M0
  const weightedNetAssets = e0 + np / 2 + (ei * mi / m0) - (ej * mj / m0) + (ek * mk / m0)
  if (weightedNetAssets === 0) {
    return { fullyDiluted, weightedAvg: 0, unable: true }
  }

  const weightedAvg = np / weightedNetAssets

  return { fullyDiluted, weightedAvg, unable: false }
}

// ─── 5. 配股调整后加权平均股数（Req 2.4） ────────────────────

export interface RightsIssueInput {
  baseWeightedAvgShares: number  // 原加权平均股数
  rightsRatio: number            // 配股比例（如 10:3 → 0.3）
  exRightsPrice: number          // 配股除权价
  marketPriceBefore: number      // 配股前市价
}

/**
 * 配股调整后加权平均股数
 *
 * 配股调整系数 f = 配股前市价 / 配股除权价
 * 配股调整后加权平均股数 = 原加权平均股数 × f
 *
 * @param i - RightsIssueInput
 * @returns { adjustedShares, unable }
 */
export function calcRightsIssueAdjustedShares(i: RightsIssueInput): {
  adjustedShares: number
  unable: boolean
} {
  const base = parseNum(i.baseWeightedAvgShares)
  const exRights = parseNum(i.exRightsPrice)
  const market = parseNum(i.marketPriceBefore)

  if (exRights === 0) {
    return { adjustedShares: 0, unable: true }
  }

  const adjustmentFactor = market / exRights
  return {
    adjustedShares: base * adjustmentFactor,
    unable: false,
  }
}

// ─── 6. 扣非后 ROE（双口径同输入结构） ─────────────────────

/**
 * 计算扣非后净资产收益率（全面摊薄 + 加权平均）
 *
 * 与 calcDilutedRoe 相同公式结构，但分子用 npEx 替代 np
 *
 * @param i - RoeInput
 * @returns { fullyDilutedEx, weightedAvgEx, unable }
 */
export function calcDilutedRoeEx(i: RoeInput): {
  fullyDilutedEx: number
  weightedAvgEx: number
  unable: boolean
} {
  const m0 = parseNum(i.m0)
  if (m0 <= 0) {
    return { fullyDilutedEx: 0, weightedAvgEx: 0, unable: true }
  }

  const npEx = parseNum(i.npEx)
  const np = parseNum(i.np)
  const eEnd = parseNum(i.eEnd)
  const minority = parseNum(i.minorityEquity)
  const e0 = parseNum(i.e0)
  const ei = parseNum(i.ei)
  const mi = parseNum(i.mi)
  const ej = parseNum(i.ej)
  const mj = parseNum(i.mj)
  const ek = parseNum(i.ek)
  const mk = parseNum(i.mk)

  // 全面摊薄：E = 期末净资产 - 少数股东权益
  const e = eEnd - minority
  if (e === 0) {
    return { fullyDilutedEx: 0, weightedAvgEx: 0, unable: true }
  }

  const fullyDilutedEx = npEx / e

  // 加权平均净资产 = E0 + NP/2 + Ei×Mi/M0 - Ej×Mj/M0 + Ek×Mk/M0
  // 注意：加权平均净资产的分母中 NP/2 用的是归母净利润（不是扣非），因为净资产变动不区分非经常
  const weightedNetAssets = e0 + np / 2 + (ei * mi / m0) - (ej * mj / m0) + (ek * mk / m0)
  if (weightedNetAssets === 0) {
    return { fullyDilutedEx, weightedAvgEx: 0, unable: true }
  }

  const weightedAvgEx = npEx / weightedNetAssets

  return { fullyDilutedEx, weightedAvgEx, unable: false }
}

// ─── composable wrapper ─────────────────────────────────────

/**
 * Vue composable wrapper — 将纯函数以 reactive 方式暴露给组件
 *
 * 使用方式：
 * ```ts
 * const { weightedAvgShares, basicEps, dilutedRoe } = useS15FormulaEngine(epsInputRef, roeInputRef)
 * ```
 */
export function useS15FormulaEngine(epsInput?: Ref<EpsInput>, roeInput?: Ref<RoeInput>) {
  const weightedAvgShares = computed(() => {
    if (!epsInput?.value) return 0
    return calcWeightedAvgShares(epsInput.value)
  })

  const basicEps = computed(() => {
    if (!epsInput?.value) return { eps: 0, epsEx: 0, unable: true }
    return calcBasicEps(epsInput.value)
  })

  const dilutedRoe = computed(() => {
    if (!roeInput?.value) return { fullyDiluted: 0, weightedAvg: 0, unable: true }
    return calcDilutedRoe(roeInput.value)
  })

  const dilutedRoeEx = computed(() => {
    if (!roeInput?.value) return { fullyDilutedEx: 0, weightedAvgEx: 0, unable: true }
    return calcDilutedRoeEx(roeInput.value)
  })

  return {
    // 纯函数（直接导出供独立调用）
    calcWeightedAvgShares,
    calcBasicEps,
    calcDilutedEps,
    calcDilutedRoe,
    calcDilutedRoeEx,
    calcRightsIssueAdjustedShares,
    parseNum,
    // reactive computeds
    weightedAvgShares,
    basicEps,
    dilutedRoe,
    dilutedRoeEx,
  }
}
