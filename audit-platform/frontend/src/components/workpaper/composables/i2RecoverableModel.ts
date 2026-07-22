/**
 * i2RecoverableModel — I2-16 可收回金额纯函数与类型
 *
 * 对齐致同「研发支出减值准备测试表-可收回金额」Excel（I2-16）：
 *   一、公允净额：N = IF(销售协议>0,协议,IF(活跃市场>0,市场,估计)) − Σ处置费用
 *   二、预计未来现金流量现值：DCF + WACC/CAPM（税前折现率默认）
 *   三、可收回金额 = MAX(公允净额, 使用价值)  对应源表 N23=MAX(N14,N20)
 *
 * Spec Req 10.2：DCF 测算复用 I1-13 模式（同 CAS8 公式链）。
 */
export {
  DCF_FORECAST_YEARS,
  defaultFvDisposal,
  defaultWaccParams,
  resolveI1FairValue as resolveI2FairValue,
  calcI1DisposalTotal as calcI2DisposalTotal,
  calcFairValueNet,
  hasFvDetail,
  normalizeFvDisposal,
  normalizeWaccParams,
  calcEffectiveDiscountRate,
  calcI1RecoverableResult as calcI2RecoverableResult,
  validateWaccParams,
  calcCostOfEquity,
  calcWaccAfterTax,
  calcPreTaxDiscountRate,
  calcRecoverableAmount,
  type I1FairValueDisposal as I2FairValueDisposal,
  type I1WaccParams as I2WaccParams,
  type I1DcfCalcResult as I2DcfCalcResult,
} from './i1RecoverableModel'

const SYNC_TOLERANCE = 0.01

export function buildI2ConclusionDraft(opts: {
  assetName: string
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
    `经测算，开发支出「${opts.assetName || '未命名'}」`,
    `可收回金额为 ${opts.recoverableAmount.toFixed(2)} 元（取自${opts.recoverableSource}：`,
    `公允净额 ${opts.fairValueNet.toFixed(2)} / 使用价值 ${opts.valueInUse.toFixed(2)}）；`,
    preferNote,
    opts.bookValue > 0
      ? `账面价值 ${opts.bookValue.toFixed(2)} 元，`
      : '',
    impair > 0.01
      ? `应计提减值 ${impair.toFixed(2)} 元，建议联动回写 I2-15；`
      : `可收回金额不低于账面价值，本期无需计提减值；`,
    `折现率 ${(opts.effectiveDiscountRate * 100).toFixed(2)}%（${opts.fromWacc ? 'WACC' : '手工'}）、`,
    `永续增长率 ${(opts.growthRate * 100).toFixed(2)}% 已复核□。`,
  ].filter(Boolean).join('')
}

export interface I2WaccCompareResult {
  currentWacc: number
  priorWacc: number
  industryWacc: number
  vsPriorBp: number | null
  vsIndustryBp: number | null
  warnings: string[]
}

/** WACC 与上期/行业对比（bp = 基点；入参可为小数 0.08 或百分数 8） */
export function compareI2Wacc(opts: {
  currentWacc: number
  priorWacc?: number
  industryWacc?: number
  /** 与上期/行业差异告警阈值（小数，默认 1% = 0.01） */
  threshold?: number
}): I2WaccCompareResult {
  const toDec = (r: number) => {
    const n = Number(r) || 0
    if (n <= 0) return 0
    return n > 1 ? n / 100 : n
  }
  const th = opts.threshold ?? 0.01
  const current = toDec(opts.currentWacc)
  const prior = toDec(opts.priorWacc ?? 0)
  const industry = toDec(opts.industryWacc ?? 0)
  const warnings: string[] = []
  let vsPriorBp: number | null = null
  let vsIndustryBp: number | null = null
  if (prior > 0 && current > 0) {
    vsPriorBp = Math.round((current - prior) * 10000)
    if (Math.abs(current - prior) >= th) {
      warnings.push(`本期 WACC ${(current * 100).toFixed(2)}% 与上期 ${(prior * 100).toFixed(2)}% 相差 ${vsPriorBp}bp，请说明变动原因`)
    }
  }
  if (industry > 0 && current > 0) {
    vsIndustryBp = Math.round((current - industry) * 10000)
    if (Math.abs(current - industry) >= th) {
      warnings.push(`本期 WACC 与行业参考 ${(industry * 100).toFixed(2)}% 相差 ${vsIndustryBp}bp，请说明是否反映资产特定风险`)
    }
  }
  return { currentWacc: current, priorWacc: prior, industryWacc: industry, vsPriorBp, vsIndustryBp, warnings }
}

export function buildI2SensitivityNote(opts: {
  assetName: string
  scenarios: Array<{
    scenario: string
    recoverableAmount: number
    differenceFromBase: number
  }>
}): string {
  const lines = opts.scenarios.map((s) =>
    `· ${s.scenario}：可收回 ${s.recoverableAmount.toFixed(2)}（较基准 ${s.differenceFromBase >= 0 ? '+' : ''}${s.differenceFromBase.toFixed(2)}）`,
  )
  return [
    `【敏感性分析 — ${opts.assetName || '未命名'}】`,
    ...lines,
    '已复核关键假设变动对可收回金额的影响，并评估是否影响减值结论。',
  ].join('\n')
}

export function applyPreferValueInUse(
  fairValueNet: number,
  valueInUse: number,
  prefer: boolean,
  reason: string,
): { recoverableAmount: number; recoverableSource: string; warnings: string[] } {
  const warnings: string[] = []
  if (prefer) {
    if (!(reason || '').trim()) {
      warnings.push('已勾选「仅使用价值」，须填写无法可靠确定公允净额的理由')
    }
    return {
      recoverableAmount: valueInUse,
      recoverableSource: '使用价值（仅测）',
      warnings,
    }
  }
  const recoverableAmount = Math.max(fairValueNet || 0, valueInUse || 0)
  let recoverableSource = '未确定'
  if (fairValueNet >= valueInUse && fairValueNet > 0) recoverableSource = '公允净额'
  else if (valueInUse > 0) recoverableSource = '使用价值'
  return { recoverableAmount, recoverableSource, warnings }
}

export type I216SyncStatus = 'synced' | 'stale' | 'missing-i16' | 'no-test'

export interface I216SyncCheck {
  name: string
  needTest: boolean
  linkedToDcf: boolean
  i15Recoverable: number
  i15FairValue: number
  i15Dcf: number
  i16Recoverable: number
  i16FairValue: number
  i16Dcf: number
  status: I216SyncStatus
  message: string
}

export function classifyI216SyncStatus(
  i15: {
    needTest: boolean
    linkedToDcf: boolean
    fairValueLessDisposal: number
    dcfValue: number
    recoverableAmount: number
  },
  i16: {
    fairValueLessDisposal: number
    valueInUse: number
    recoverableAmount: number
  } | null,
): Pick<I216SyncCheck, 'status' | 'message'> {
  if (!i15.needTest) {
    return { status: 'no-test', message: '无须测试' }
  }
  if (!i16) {
    return { status: 'missing-i16', message: 'I2-16 尚无同名测算组' }
  }
  if (i16.recoverableAmount <= 0 && i15.recoverableAmount <= 0) {
    return { status: 'missing-i16', message: '须测试但可收回金额尚未测算' }
  }
  const fvOk = Math.abs(i15.fairValueLessDisposal - i16.fairValueLessDisposal) < SYNC_TOLERANCE
  const dcfOk = Math.abs(i15.dcfValue - i16.valueInUse) < SYNC_TOLERANCE
  const recOk = Math.abs(i15.recoverableAmount - i16.recoverableAmount) < SYNC_TOLERANCE
  if (fvOk && dcfOk && recOk) {
    return { status: 'synced', message: i15.linkedToDcf ? '已与 I2-16 一致' : '金额一致（未标记联动）' }
  }
  const parts: string[] = []
  if (!fvOk) parts.push(`③差 ${Math.abs(i15.fairValueLessDisposal - i16.fairValueLessDisposal).toFixed(2)}`)
  if (!dcfOk) parts.push(`④差 ${Math.abs(i15.dcfValue - i16.valueInUse).toFixed(2)}`)
  if (!recOk) parts.push(`⑤差 ${Math.abs(i15.recoverableAmount - i16.recoverableAmount).toFixed(2)}`)
  return { status: 'stale', message: `与 I2-16 不一致（${parts.join('，')}），请联动回写` }
}

export function buildI216SyncChecks(
  impairmentRows: Array<{
    name: string
    needTest: boolean
    linkedToDcf: boolean
    fairValueLessDisposal: number
    dcfValue: number
    recoverableAmount: number
  }>,
  recoverableRows: Array<{
    name: string
    fairValueLessDisposal: number
    valueInUse: number
    recoverableAmount: number
  }>,
): I216SyncCheck[] {
  const byName = new Map<string, (typeof recoverableRows)[0]>()
  for (const r of recoverableRows) {
    const key = (r.name || '').trim()
    if (key) byName.set(key, r)
  }

  const out: I216SyncCheck[] = []
  const seen = new Set<string>()

  for (const row of impairmentRows) {
    const name = (row.name || '').trim()
    if (!name) continue
    seen.add(name)
    const i16 = byName.get(name) ?? null
    const { status, message } = classifyI216SyncStatus(row, i16)
    out.push({
      name,
      needTest: row.needTest,
      linkedToDcf: row.linkedToDcf,
      i15Recoverable: row.recoverableAmount,
      i15FairValue: row.fairValueLessDisposal,
      i15Dcf: row.dcfValue,
      i16Recoverable: i16?.recoverableAmount ?? 0,
      i16FairValue: i16?.fairValueLessDisposal ?? 0,
      i16Dcf: i16?.valueInUse ?? 0,
      status,
      message,
    })
  }

  for (const r of recoverableRows) {
    const name = (r.name || '').trim()
    if (!name || seen.has(name)) continue
    out.push({
      name,
      needTest: false,
      linkedToDcf: false,
      i15Recoverable: 0,
      i15FairValue: 0,
      i15Dcf: 0,
      i16Recoverable: r.recoverableAmount,
      i16FairValue: r.fairValueLessDisposal,
      i16Dcf: r.valueInUse,
      status: 'stale',
      message: 'I2-16 有测算但 I2-15 无同名行',
    })
  }

  return out
}
