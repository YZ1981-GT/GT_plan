/**
 * H3-2 → H3-1 按类别聚合 / 回填预览 / 应用
 * mode=book：只回填账面 roll-forward + 未审，保留 H3-1 已有 AJE/RJE
 * mode=full：连同明细审定调整区一并覆盖
 */
import { calcAuditedAmount, calcFairEndBalance } from './useH3FormulaEngine'
import {
  H3_ASSET_CATEGORIES,
  normalizeH3Category,
  isStandardH3Category,
  type H3AssetCategory,
} from './h3CategoryMap'

export type H3FillMode = 'book' | 'full'

export interface H3FillDiffRow {
  category: string
  block: string
  field: string
  before: number
  after: number
  delta: number
}

export interface H3CostCategoryAgg {
  begin: number
  increase: number
  decrease: number
  transfer: number
  end: number
  unadj: number
  aje: number
  rje: number
  audited: number
  depBegin: number
  depProv: number
  depRev: number
  depEnd: number
  depUnadj: number
  depAje: number
  depRje: number
  depAudited: number
  impBegin: number
  impProv: number
  impRev: number
  impEnd: number
  impUnadj: number
  impAje: number
  impRje: number
  impAudited: number
}

export interface H3FairCategoryAgg {
  begin: number
  increase: number
  decrease: number
  transfer: number
  fvChange: number
  end: number
  unadj: number
  aje: number
  rje: number
  audited: number
}

function _emptyCost(): H3CostCategoryAgg {
  return {
    begin: 0, increase: 0, decrease: 0, transfer: 0, end: 0,
    unadj: 0, aje: 0, rje: 0, audited: 0,
    depBegin: 0, depProv: 0, depRev: 0, depEnd: 0,
    depUnadj: 0, depAje: 0, depRje: 0, depAudited: 0,
    impBegin: 0, impProv: 0, impRev: 0, impEnd: 0,
    impUnadj: 0, impAje: 0, impRje: 0, impAudited: 0,
  }
}

function _emptyFair(): H3FairCategoryAgg {
  return {
    begin: 0, increase: 0, decrease: 0, transfer: 0, fvChange: 0, end: 0,
    unadj: 0, aje: 0, rje: 0, audited: 0,
  }
}

/** 原始类别文本是否已是标准三类之一 */
export { isStandardH3Category } from './h3CategoryMap'

export function aggregateH32CostByCategory(detail: any[]): {
  map: Record<H3AssetCategory, H3CostCategoryAgg>
  unmatchedEnd: number
  unmatchedCount: number
} {
  const map: Record<H3AssetCategory, H3CostCategoryAgg> = {
    '房屋及建筑物': _emptyCost(),
    '土地使用权': _emptyCost(),
    '其他': _emptyCost(),
  }
  let unmatchedEnd = 0
  let unmatchedCount = 0

  for (const r of detail) {
    const rawType = String(r.assetType || r.category || '').trim()
    const cat = normalizeH3Category(rawType)
    if (!isStandardH3Category(rawType)) {
      unmatchedCount++
      unmatchedEnd += Number(r.costEnd) || 0
    }
    const a = map[cat]
    const costBegin = Number(r.costBegin) || 0
    const costInc = Number(r.costIncrease) || 0
    const costDec = Number(r.costDecrease) || 0
    const transfer = (Number(r.transferIn) || 0) - (Number(r.transferOut) || 0)
    const costEnd = Number(r.costEnd) || (costBegin + costInc - costDec + transfer)
    const costUnadj = r.costUnadj != null ? Number(r.costUnadj) || 0 : costEnd
    const costAje = Number(r.costAje) || 0
    const costRje = Number(r.costRje) || 0
    const costAudited = r.costAudited != null
      ? Number(r.costAudited) || 0
      : calcAuditedAmount(costUnadj, costAje, costRje)

    a.begin += costBegin
    a.increase += costInc
    a.decrease += costDec
    a.transfer += transfer
    a.end += costEnd
    a.unadj += costUnadj
    a.aje += costAje
    a.rje += costRje
    a.audited += costAudited

    const depBegin = Number(r.accDepBegin) || 0
    const depProv = Number(r.depProvision) || 0
    const depRev = Number(r.depReversal) || 0
    const depEnd = Number(r.accDepEnd) || (depBegin + depProv - depRev)
    const depUnadj = r.depUnadj != null ? Number(r.depUnadj) || 0 : depEnd
    const depAje = Number(r.depAje) || 0
    const depRje = Number(r.depRje) || 0
    const depAudited = r.depAudited != null
      ? Number(r.depAudited) || 0
      : calcAuditedAmount(depUnadj, depAje, depRje)

    a.depBegin += depBegin
    a.depProv += depProv
    a.depRev += depRev
    a.depEnd += depEnd
    a.depUnadj += depUnadj
    a.depAje += depAje
    a.depRje += depRje
    a.depAudited += depAudited

    const impBegin = Number(r.impairmentBegin) || 0
    const impProv = Number(r.impairmentProvision) || 0
    const impRev = Number(r.impairmentReversal) || 0
    const impEnd = Number(r.impairmentEnd) || (impBegin + impProv - impRev)
    const impUnadj = r.impairUnadj != null ? Number(r.impairUnadj) || 0 : impEnd
    const impAje = Number(r.impairAje) || 0
    const impRje = Number(r.impairRje) || 0
    const impAudited = r.impairAudited != null
      ? Number(r.impairAudited) || 0
      : calcAuditedAmount(impUnadj, impAje, impRje)

    a.impBegin += impBegin
    a.impProv += impProv
    a.impRev += impRev
    a.impEnd += impEnd
    a.impUnadj += impUnadj
    a.impAje += impAje
    a.impRje += impRje
    a.impAudited += impAudited
  }

  return { map, unmatchedEnd, unmatchedCount }
}

export function aggregateH32FairByCategory(detail: any[]): {
  map: Record<H3AssetCategory, H3FairCategoryAgg>
  unmatchedEnd: number
  unmatchedCount: number
} {
  const map: Record<H3AssetCategory, H3FairCategoryAgg> = {
    '房屋及建筑物': _emptyFair(),
    '土地使用权': _emptyFair(),
    '其他': _emptyFair(),
  }
  let unmatchedEnd = 0
  let unmatchedCount = 0

  for (const r of detail) {
    const rawType = String(r.assetType || r.category || '').trim()
    const cat = normalizeH3Category(rawType)
    if (!isStandardH3Category(rawType)) {
      unmatchedCount++
      unmatchedEnd += Number(r.fairValueEnd) || 0
    }
    const a = map[cat]
    const begin = Number(r.fairValueBegin) || 0
    const inc = Number(r.fairIncrease) || 0
    const dec = Number(r.fairDecrease) || 0
    const transfer = (Number(r.transferIn) || 0) - (Number(r.transferOut) || 0)
    const fvChange = Number(r.fvChangeAudited != null ? r.fvChangeAudited : r.fairValueChange) || 0
    const end = Number(r.fairValueEnd)
      || calcFairEndBalance(begin, inc, dec, transfer, Number(r.fairValueChange) || 0)
    const unadj = r.fairUnadj != null ? Number(r.fairUnadj) || 0 : end
    const aje = Number(r.fairAje) || 0
    const rje = Number(r.fairRje) || 0
    const audited = r.fairAudited != null
      ? Number(r.fairAudited) || 0
      : calcAuditedAmount(unadj, aje, rje)

    a.begin += begin
    a.increase += inc
    a.decrease += dec
    a.transfer += transfer
    a.fvChange += fvChange
    a.end += end
    a.unadj += unadj
    a.aje += aje
    a.rje += rje
    a.audited += audited
  }

  return { map, unmatchedEnd, unmatchedCount }
}

function _pushDiff(
  out: H3FillDiffRow[],
  category: string,
  block: string,
  field: string,
  before: number,
  after: number,
): void {
  const delta = after - before
  if (Math.abs(delta) < 0.005) return
  out.push({ category, block, field, before, after, delta })
}

/** 预览成本模式回填差异 */
export function previewCostFillDiff(opts: {
  originalRows: any[]
  depRows: any[]
  impairRows: any[]
  map: Record<H3AssetCategory, H3CostCategoryAgg>
  mode: H3FillMode
}): H3FillDiffRow[] {
  const diffs: H3FillDiffRow[] = []
  const { map, mode } = opts

  for (const row of opts.originalRows) {
    const cat = normalizeH3Category(row.category)
    const a = map[cat]
    const unadj = mode === 'full' ? a.unadj : a.end
    const aje = mode === 'full' ? a.aje : (Number(row.aje) || 0)
    const rje = mode === 'full' ? a.rje : (Number(row.rje) || 0)
    const audited = calcAuditedAmount(unadj, aje, rje)
    _pushDiff(diffs, cat, '原值', '期初', Number(row.beginBalance) || 0, a.begin)
    _pushDiff(diffs, cat, '原值', '增加', Number(row.increase) || 0, a.increase)
    _pushDiff(diffs, cat, '原值', '减少', Number(row.decrease) || 0, a.decrease)
    _pushDiff(diffs, cat, '原值', '转换', Number(row.transfer) || 0, a.transfer)
    _pushDiff(diffs, cat, '原值', '期末', Number(row.endBalance) || 0, a.end)
    _pushDiff(diffs, cat, '原值', '未审', Number(row.unadjusted) || 0, unadj)
    if (mode === 'full') {
      _pushDiff(diffs, cat, '原值', 'AJE', Number(row.aje) || 0, a.aje)
      _pushDiff(diffs, cat, '原值', 'RJE', Number(row.rje) || 0, a.rje)
    }
    _pushDiff(diffs, cat, '原值', '审定', Number(row.audited) || 0, audited)
  }

  for (const row of opts.depRows) {
    const cat = normalizeH3Category(row.category)
    const a = map[cat]
    const unadj = mode === 'full' ? a.depUnadj : a.depEnd
    const aje = mode === 'full' ? a.depAje : (Number(row.aje) || 0)
    const rje = mode === 'full' ? a.depRje : (Number(row.rje) || 0)
    const audited = calcAuditedAmount(unadj, aje, rje)
    _pushDiff(diffs, cat, '折旧', '期初', Number(row.beginBalance) || 0, a.depBegin)
    _pushDiff(diffs, cat, '折旧', '计提', Number(row.provision) || 0, a.depProv)
    _pushDiff(diffs, cat, '折旧', '转回', Number(row.reversal) || 0, a.depRev)
    _pushDiff(diffs, cat, '折旧', '期末', Number(row.endBalance) || 0, a.depEnd)
    _pushDiff(diffs, cat, '折旧', '未审', Number(row.unadjusted) || 0, unadj)
    if (mode === 'full') {
      _pushDiff(diffs, cat, '折旧', 'AJE', Number(row.aje) || 0, a.depAje)
      _pushDiff(diffs, cat, '折旧', 'RJE', Number(row.rje) || 0, a.depRje)
    }
    _pushDiff(diffs, cat, '折旧', '审定', Number(row.audited) || 0, audited)
  }

  for (const row of opts.impairRows) {
    const cat = normalizeH3Category(row.category)
    const a = map[cat]
    const unadj = mode === 'full' ? a.impUnadj : a.impEnd
    const aje = mode === 'full' ? a.impAje : (Number(row.aje) || 0)
    const rje = mode === 'full' ? a.impRje : (Number(row.rje) || 0)
    const audited = calcAuditedAmount(unadj, aje, rje)
    _pushDiff(diffs, cat, '减值', '期初', Number(row.beginBalance) || 0, a.impBegin)
    _pushDiff(diffs, cat, '减值', '计提', Number(row.provision) || 0, a.impProv)
    _pushDiff(diffs, cat, '减值', '转回', Number(row.reversal) || 0, a.impRev)
    _pushDiff(diffs, cat, '减值', '期末', Number(row.endBalance) || 0, a.impEnd)
    _pushDiff(diffs, cat, '减值', '未审', Number(row.unadjusted) || 0, unadj)
    if (mode === 'full') {
      _pushDiff(diffs, cat, '减值', 'AJE', Number(row.aje) || 0, a.impAje)
      _pushDiff(diffs, cat, '减值', 'RJE', Number(row.rje) || 0, a.impRje)
    }
    _pushDiff(diffs, cat, '减值', '审定', Number(row.audited) || 0, audited)
  }

  return diffs
}

export function previewFairFillDiff(opts: {
  rows: any[]
  map: Record<H3AssetCategory, H3FairCategoryAgg>
  mode: H3FillMode
}): H3FillDiffRow[] {
  const diffs: H3FillDiffRow[] = []
  const { map, mode } = opts
  for (const row of opts.rows) {
    const cat = normalizeH3Category(row.category)
    const a = map[cat]
    const unadj = mode === 'full' ? a.unadj : a.end
    const aje = mode === 'full' ? a.aje : (Number(row.aje) || 0)
    const rje = mode === 'full' ? a.rje : (Number(row.rje) || 0)
    const audited = calcAuditedAmount(unadj, aje, rje)
    _pushDiff(diffs, cat, '公允', '期初', Number(row.beginFair) || 0, a.begin)
    _pushDiff(diffs, cat, '公允', '增加', Number(row.increase) || 0, a.increase)
    _pushDiff(diffs, cat, '公允', '减少', Number(row.decrease) || 0, a.decrease)
    _pushDiff(diffs, cat, '公允', '转换', Number(row.transfer) || 0, a.transfer)
    _pushDiff(diffs, cat, '公允', '公允变动', Number(row.fairValueChange) || 0, a.fvChange)
    _pushDiff(diffs, cat, '公允', '期末', Number(row.endFair) || 0, a.end)
    _pushDiff(diffs, cat, '公允', '未审', Number(row.unadjusted) || 0, unadj)
    if (mode === 'full') {
      _pushDiff(diffs, cat, '公允', 'AJE', Number(row.aje) || 0, a.aje)
      _pushDiff(diffs, cat, '公允', 'RJE', Number(row.rje) || 0, a.rje)
    }
    _pushDiff(diffs, cat, '公允', '审定', Number(row.audited) || 0, audited)
  }
  return diffs
}

/** 按期末余额权重分摊 H3-6 净转换到各类别 */
export function allocateTransferByWeight(
  categories: { category: string; weight: number }[],
  netTransfer: number,
): Record<H3AssetCategory, number> {
  const result = emptyCategoryAmountMapLocal()
  const totalW = categories.reduce((s, c) => s + Math.max(0, c.weight), 0)
  if (totalW <= 0 || Math.abs(netTransfer) < 0.005) {
    result['其他'] = netTransfer
    return result
  }
  let allocated = 0
  categories.forEach((c, i) => {
    const cat = normalizeH3Category(c.category)
    const w = Math.max(0, c.weight)
    const amount = i === categories.length - 1
      ? netTransfer - allocated
      : Math.round((netTransfer * w / totalW) * 100) / 100
    result[cat] += amount
    allocated += amount
  })
  return result
}

function emptyCategoryAmountMapLocal(): Record<H3AssetCategory, number> {
  return { '房屋及建筑物': 0, '土地使用权': 0, '其他': 0 }
}
