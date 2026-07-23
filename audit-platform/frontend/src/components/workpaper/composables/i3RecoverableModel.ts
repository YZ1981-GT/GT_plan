/**
 * i3RecoverableModel — I3-7 可收回金额纯函数与类型
 *
 * 对齐致同「商誉减值准备测试表-可收回金额」Excel（I3-7）：
 *   一、公允净额：N = IF(销售协议>0,协议,IF(活跃市场>0,市场,估计)) − Σ处置费用
 *   二、预计未来现金流量现值：DCF + WACC/CAPM（税前折现率默认，CAS8）
 *   三、可收回金额 = MAX(公允净额, 使用价值)  对应源表 N23=MAX(N11,N20)
 *
 * 测算公式链复用 I1-13 / H4（同 CAS8）。
 */
export {
  DCF_FORECAST_YEARS,
  defaultFvDisposal,
  defaultWaccParams,
  resolveI1FairValue as resolveI3FairValue,
  calcI1DisposalTotal as calcI3DisposalTotal,
  calcFairValueNet,
  hasFvDetail,
  normalizeFvDisposal,
  normalizeWaccParams,
  calcEffectiveDiscountRate,
  calcI1RecoverableResult as calcI3RecoverableResult,
  validateWaccParams,
  calcCostOfEquity,
  calcWaccAfterTax,
  calcPreTaxDiscountRate,
  calcRecoverableAmount,
  type I1FairValueDisposal as I3FairValueDisposal,
  type I1WaccParams as I3WaccParams,
  type I1DcfCalcResult as I3DcfCalcResult,
} from './i1RecoverableModel'

/** 永续增长率对照（对齐 Excel：行业/市场/国家或地区长期平均） */
export interface I3GrowthBenchmarks {
  industryGrowthRate: number
  marketGrowthRate: number
  countryGrowthRate: number
  growthRateBasis: string
}

export function defaultGrowthBenchmarks(): I3GrowthBenchmarks {
  return {
    industryGrowthRate: 0,
    marketGrowthRate: 0,
    countryGrowthRate: 0,
    growthRateBasis: '',
  }
}

export function normalizeGrowthBenchmarks(raw: any): I3GrowthBenchmarks {
  const d = defaultGrowthBenchmarks()
  if (!raw || typeof raw !== 'object') return d
  return {
    industryGrowthRate: Number(raw.industryGrowthRate) || 0,
    marketGrowthRate: Number(raw.marketGrowthRate) || 0,
    countryGrowthRate: Number(raw.countryGrowthRate) || 0,
    growthRateBasis: String(raw.growthRateBasis ?? ''),
  }
}

/** 增长率合理性提示（相对行业/市场/国家对照） */
export function validateGrowthRate(
  growthRate: number,
  benchmarks: I3GrowthBenchmarks,
): string[] {
  const msgs: string[] = []
  const caps = [
    benchmarks.industryGrowthRate,
    benchmarks.marketGrowthRate,
    benchmarks.countryGrowthRate,
  ].filter((x) => x > 0)
  if (growthRate > 0.01 && !(benchmarks.growthRateBasis || '').trim()) {
    msgs.push('永续增长率大于 0，须填写确定依据，且通常不应超过行业/经济体长期增长率')
  }
  if (caps.length && growthRate > Math.max(...caps) + 1e-9) {
    msgs.push(
      `永续增长率 ${(growthRate * 100).toFixed(2)}% 高于已填对照上限 ${(Math.max(...caps) * 100).toFixed(2)}%，请说明理由`,
    )
  }
  return msgs
}

export function buildI3ConclusionDraft(opts: {
  cguName: string
  fairValueNet: number
  valueInUse: number
  recoverableAmount: number
  recoverableSource: string
  bookValue: number
  effectiveDiscountRate: number
  growthRate: number
  fromWacc: boolean
  preferValueInUse?: boolean
  preferValueInUseReason?: string
}): string {
  const impair = Math.max((opts.bookValue || 0) - opts.recoverableAmount, 0)
  const preferNote = opts.preferValueInUse
    ? `已选用「仅使用价值」路径（理由：${opts.preferValueInUseReason || '未填'}）；`
    : ''
  return [
    `经测算，资产组「${opts.cguName || '未命名'}」`,
    `可收回金额为 ${opts.recoverableAmount.toFixed(2)} 元（取自${opts.recoverableSource}：`,
    `公允净额 ${opts.fairValueNet.toFixed(2)} / 使用价值 ${opts.valueInUse.toFixed(2)}）；`,
    preferNote,
    opts.bookValue > 0
      ? `资产组账面价值(含商誉) ${opts.bookValue.toFixed(2)} 元，`
      : '',
    impair > 0.01
      ? `账面高于可收回金额 ${impair.toFixed(2)} 元，应联动回写 I3-6 并按“先冲商誉、再分摊其他资产”处理；商誉减值一经确认不得转回。`
      : `可收回金额不低于账面价值，本期无需就该资产组计提商誉减值；`,
    `折现率 ${(opts.effectiveDiscountRate * 100).toFixed(2)}%（${opts.fromWacc ? 'WACC/CAPM' : '手工'}）、`,
    `永续增长率 ${(opts.growthRate * 100).toFixed(2)}% 已复核□。`,
  ].filter(Boolean).join('')
}

/**
 * 旧版 I3-7 状态（收入/成本拆分 FCF）→ 直接税前净现金流。
 * FCF ≈ 收入 − 成本 − 税 + 折旧 − 资本支出 − 营运资本变动
 */
export function migrateLegacyCashFlows(state: any): number[] | null {
  if (!state || typeof state !== 'object') return null
  if (Array.isArray(state.cashFlows) && state.cashFlows.length) {
    return state.cashFlows.map((x: any) => Number(x) || 0)
  }
  const rev = state.revenue
  if (!Array.isArray(rev) || !rev.length) return null
  const n = rev.length
  const arr = (k: string) => {
    const a = state[k]
    return Array.isArray(a) ? a : []
  }
  const cost = arr('cost')
  const tax = arr('tax')
  const dep = arr('depreciation')
  const capex = arr('capex')
  const wc = arr('wcChange')
  return Array.from({ length: n }, (_, i) => {
    const ebit = (Number(rev[i]) || 0) - (Number(cost[i]) || 0)
    return ebit - (Number(tax[i]) || 0) + (Number(dep[i]) || 0)
      - (Number(capex[i]) || 0) - (Number(wc[i]) || 0)
  })
}

/** 从 allResponses 条目读取 remark（兼容裸字符串 / {remark}） */
export function readResponsePayload(raw: any): any {
  if (raw == null) return undefined
  const payload = raw.remark !== undefined ? raw.remark : raw
  if (typeof payload === 'string') {
    try {
      return JSON.parse(payload)
    } catch {
      return payload
    }
  }
  return payload
}
