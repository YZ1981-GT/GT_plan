/**
 * H3-9 投资性房地产盘点检查表 — 对齐致同「盘点检查表H3-9」+ 参照 H1-10 双向抽盘
 *
 * 逻辑：目标认定 → 样本选取 → 现场过程 → 双向抽盘（账面→实物 / 实物→账面）
 *      → 三数量差异自动计算 → 覆盖率（避免 #DIV/0!）
 *      → IR 专用列（产权/面积/用途/租赁/空置）→ 说明/结论
 */
import {
  calcRowDiffs,
  calcDirectionCoverage,
  deriveResultFromQty,
  normalizeDirection,
  SAMPLING_METHOD_OPTS,
  type CheckRowDiffs,
  type DirectionCoverage,
  type StocktakeCheckMeta,
  type StocktakeDirection,
} from './h1StocktakeCheckModel'

export {
  SAMPLING_METHOD_OPTS,
  calcRowDiffs,
  calcDirectionCoverage,
  deriveResultFromQty,
  normalizeDirection,
}
export type { CheckRowDiffs, DirectionCoverage, StocktakeDirection }

export type H3StocktakeCheckMeta = StocktakeCheckMeta

export interface H3StocktakeCheckRow {
  rowId: string
  seq: number
  /** 抽盘方向：账面→实物测存在；实物→账面测完整 */
  direction: StocktakeDirection
  assetName: string
  assetNo: string
  location: string
  /** 面积(㎡) — 规格口径 */
  area: number
  unit: string
  unitPrice: number
  bookQty: number
  bookAmount: number
  clientCountQty: number
  sampleQty: number
  purpose: string
  leaseStatus: string
  tenant: string
  titleCertNo: string
  qualityStatus: string
  result: string
  diffReason: string
  diffAmount: number
  remark: string
  // ── 兼容旧版字段（H3-12 联动仍可读） ──
  physicalStatus: string
  maintenance: string
  bookValue: number
  conclusion: string
}

export const LEASE_STATUS_OPTS = ['已出租', '空置', '到期', '部分出租'] as const
export const PURPOSE_OPTS = ['出租', '增值', '出租+增值'] as const
export const QUALITY_OPTS = ['正常', '闲置', '毁损', '待处置', '其他'] as const

export function createEmptyCheckMeta(): H3StocktakeCheckMeta {
  return {
    testPopulation: '',
    specificSample: '',
    samplingPopulation: '',
    samplingMethod: '随机选样',
    samplingProcess: '',
    location: '',
    clientStaff: '',
    auditors: '',
    countTime: '',
    totalBookCost: null,
  }
}

export function normalizeCheckMeta(raw: unknown): H3StocktakeCheckMeta {
  const base = createEmptyCheckMeta()
  if (!raw || typeof raw !== 'object') return base
  const o = raw as Record<string, unknown>
  return {
    testPopulation: String(o.testPopulation ?? ''),
    specificSample: String(o.specificSample ?? ''),
    samplingPopulation: String(o.samplingPopulation ?? ''),
    samplingMethod: String(o.samplingMethod ?? base.samplingMethod),
    samplingProcess: String(o.samplingProcess ?? ''),
    location: String(o.location ?? ''),
    clientStaff: String(o.clientStaff ?? ''),
    auditors: String(o.auditors ?? ''),
    countTime: String(o.countTime ?? ''),
    totalBookCost: o.totalBookCost == null || o.totalBookCost === ''
      ? null
      : Number(o.totalBookCost) || 0,
  }
}

function _num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function _mapLegacyConclusion(c: string): string {
  const s = (c || '').trim()
  if (s === '相符') return '账实相符'
  if (s === '不符') return '盘亏'
  if (s === '待查') return ''
  return s
}

export function normalizeCheckRow(raw: any, idx: number): H3StocktakeCheckRow {
  const bookAmount = _num(
    raw.bookAmount ?? raw.bookValue ?? raw.bookCost ?? raw.originalCost,
  )
  const bookQty = _num(raw.bookQty) || (bookAmount > 0 || String(raw.assetName ?? raw.name ?? '').trim() ? 1 : 0)
  const hasExplicitClient = raw.clientCountQty != null && raw.clientCountQty !== ''
  const hasExplicitSample = raw.sampleQty != null && raw.sampleQty !== ''
  const clientCountQty = hasExplicitClient ? _num(raw.clientCountQty) : bookQty
  const sampleQty = hasExplicitSample ? _num(raw.sampleQty) : bookQty
  const area = _num(raw.area)
  const unitPrice = _num(raw.unitPrice) || (bookQty > 0 && bookAmount > 0 ? bookAmount / bookQty : 0)
  const direction = normalizeDirection(raw.direction)

  let result = String(raw.result ?? raw.stocktakeResult ?? '')
  if (!result) result = _mapLegacyConclusion(String(raw.conclusion ?? ''))
  if (!result && (bookQty > 0 || sampleQty > 0 || clientCountQty > 0)) {
    result = deriveResultFromQty(sampleQty, bookQty)
  }

  const quality = String(
    raw.qualityStatus ?? raw.physicalStatus ?? raw.maintenance ?? '',
  ).trim()

  return {
    rowId: raw.rowId ?? raw.id ?? `h3st-${Math.random().toString(36).slice(2, 10)}`,
    seq: raw.seq ?? idx + 1,
    direction,
    assetName: String(raw.assetName ?? raw.name ?? ''),
    assetNo: String(raw.assetNo ?? raw.assetCode ?? ''),
    location: String(raw.location ?? ''),
    area,
    unit: String(raw.unit ?? '处') || '处',
    unitPrice,
    bookQty,
    bookAmount,
    clientCountQty,
    sampleQty,
    purpose: String(raw.purpose ?? ''),
    leaseStatus: String(raw.leaseStatus ?? raw.rentalStatus ?? ''),
    tenant: String(raw.tenant ?? ''),
    titleCertNo: String(raw.titleCertNo ?? ''),
    qualityStatus: quality,
    result,
    diffReason: String(raw.diffReason ?? raw.varianceReason ?? ''),
    diffAmount: _num(raw.diffAmount),
    remark: String(raw.remark ?? ''),
    physicalStatus: String(raw.physicalStatus ?? quality),
    maintenance: String(raw.maintenance ?? ''),
    bookValue: bookAmount,
    conclusion: String(raw.conclusion ?? ''),
  }
}

export function createEmptyCheckRow(
  direction: StocktakeDirection,
  seq: number,
  assetName = '',
): H3StocktakeCheckRow {
  return normalizeCheckRow(
    { direction, seq, assetName, bookQty: 1, clientCountQty: 1, sampleQty: 1 },
    seq - 1,
  )
}

export function applyQtySideEffects(row: H3StocktakeCheckRow): void {
  const diffs = calcRowDiffs(row)
  row.result = deriveResultFromQty(row.sampleQty, row.bookQty)
  row.conclusion = row.result === '账实相符' ? '相符' : row.result ? '不符' : ''
  if (row.unitPrice) {
    row.diffAmount = diffs.sampleVsBook * row.unitPrice
  } else if (Math.abs(diffs.sampleVsBook) < 0.001) {
    row.diffAmount = 0
  }
  row.bookValue = row.bookAmount
  if (row.qualityStatus && !row.physicalStatus) {
    row.physicalStatus = row.qualityStatus
  }
}

/** H3-2 明细 → 盘点行（默认账面→实物，数量 1） */
export function mapH32RowsToCheckRows(
  detailRows: any[],
  opts?: {
    direction?: StocktakeDirection
    maxRows?: number
    minAmount?: number
    measurementModel?: 'cost' | 'fair_value'
  },
): H3StocktakeCheckRow[] {
  const direction = opts?.direction ?? 'bookToFloor'
  const minAmount = opts?.minAmount ?? 0
  const maxRows = opts?.maxRows ?? 200
  const isFair = opts?.measurementModel === 'fair_value'

  const mapped = detailRows
    .map((d, i) => {
      const bookAmount = isFair
        ? _num(d.fairValueEnd ?? d.fairValueBegin)
        : _num(d.originalCostEnd ?? d.originalCost ?? d.costEnd)
      if (bookAmount < minAmount) return null
      const row = createEmptyCheckRow(direction, i + 1, String(d.assetName ?? ''))
      row.assetNo = String(d.rowId ?? '').replace(/^(dc|df)-/, '').slice(0, 12)
      row.location = String(d.location ?? '')
      row.area = _num(d.area)
      row.bookQty = 1
      row.clientCountQty = 1
      row.sampleQty = 1
      row.bookAmount = bookAmount
      row.bookValue = bookAmount
      row.unitPrice = bookAmount
      row.purpose = /土地/.test(String(d.assetType ?? '')) ? '增值' : '出租'
      row.remark = '来源:H3-2'
      return row
    })
    .filter(Boolean) as H3StocktakeCheckRow[]

  mapped.sort((a, b) => (b.bookAmount || 0) - (a.bookAmount || 0))
  return mapped.slice(0, maxRows).map((r, i) => ({ ...r, seq: i + 1 }))
}

export function sumH32BookAmount(
  detailRows: any[],
  measurementModel: 'cost' | 'fair_value' = 'cost',
): number {
  const isFair = measurementModel === 'fair_value'
  return detailRows.reduce((s, d) => {
    const amt = isFair
      ? _num(d.fairValueEnd ?? d.fairValueBegin)
      : _num(d.originalCostEnd ?? d.originalCost ?? d.costEnd)
    return s + amt
  }, 0)
}

export interface H3StocktakeStats {
  total: number
  matchCount: number
  surplusCount: number
  deficitCount: number
  matchRate: number
  rentedCount: number
  vacantCount: number
  vacantRate: number
  varianceCount: number
  deficitAmount: number
  surplusAmount: number
  bookToFloorCount: number
  floorToBookCount: number
}

export function calcStocktakeStats(rows: H3StocktakeCheckRow[]): H3StocktakeStats {
  const total = rows.length
  const matchCount = rows.filter((r) => r.result === '账实相符').length
  const surplusCount = rows.filter((r) => r.result === '盘盈').length
  const deficitCount = rows.filter((r) => r.result === '盘亏').length
  const rentedCount = rows.filter((r) => r.leaseStatus === '已出租').length
  const vacantCount = rows.filter((r) => r.leaseStatus === '空置').length
  const varianceCount = rows.filter((r) => calcRowDiffs(r).hasVariance).length
  const deficitAmount = rows
    .filter((r) => r.result === '盘亏')
    .reduce((s, r) => s + Math.abs(r.diffAmount || r.bookAmount), 0)
  const surplusAmount = rows
    .filter((r) => r.result === '盘盈')
    .reduce((s, r) => s + Math.abs(r.diffAmount || 0), 0)

  return {
    total,
    matchCount,
    surplusCount,
    deficitCount,
    matchRate: total > 0 ? (matchCount / total) * 100 : 0,
    rentedCount,
    vacantCount,
    vacantRate: total > 0 ? (vacantCount / total) * 100 : 0,
    varianceCount,
    deficitAmount,
    surplusAmount,
    bookToFloorCount: rows.filter((r) => r.direction !== 'floorToBook').length,
    floorToBookCount: rows.filter((r) => r.direction === 'floorToBook').length,
  }
}

export function draftCheckSheetNote(ctx: {
  stats: H3StocktakeStats
  meta: H3StocktakeCheckMeta
  bookToFloorCoverage: DirectionCoverage
  floorToBookCoverage: DirectionCoverage
}): string {
  const { stats, meta, bookToFloorCoverage, floorToBookCoverage } = ctx
  const lines = [
    `盘点地点：${meta.location || '____'}；时间：${meta.countTime || '____'}；企业人员：${meta.clientStaff || '____'}；监盘：${meta.auditors || '____'}。`,
    `测试总体：${meta.testPopulation || '（待填）'}；抽样方法：${meta.samplingMethod || '—'}。`,
    `共抽盘 ${stats.total} 项（账面→实物 ${stats.bookToFloorCount}、实物→账面 ${stats.floorToBookCount}），账实相符 ${stats.matchCount}、盘盈 ${stats.surplusCount}、盘亏 ${stats.deficitCount}；三数量差异 ${stats.varianceCount} 项。`,
    `租赁状态：已出租 ${stats.rentedCount}、空置 ${stats.vacantCount}（空置率 ${stats.vacantRate.toFixed(1)}%）${stats.vacantRate > 20 ? '，空置率偏高需关注减值/公允复核' : ''}。`,
  ]
  if (bookToFloorCoverage.ratioPct != null) {
    lines.push(`账面→实物覆盖率：抽盘金额 ${bookToFloorCoverage.sampleAmount.toFixed(2)} / 期末原值 ${bookToFloorCoverage.totalBookCost.toFixed(2)} = ${bookToFloorCoverage.ratioPct.toFixed(2)}%。`)
  }
  if (floorToBookCoverage.ratioPct != null) {
    lines.push(`实物→账面覆盖率：抽盘金额 ${floorToBookCoverage.sampleAmount.toFixed(2)} / 期末原值 ${floorToBookCoverage.totalBookCost.toFixed(2)} = ${floorToBookCoverage.ratioPct.toFixed(2)}%。`)
  }
  if (bookToFloorCoverage.ratioPct == null && floorToBookCoverage.ratioPct == null) {
    lines.push('尚未录入期末投资性房地产原值合计，样本覆盖率待补算（请自 H3-2 同步或手工填入）。')
  }
  if (stats.deficitCount > 0 || stats.varianceCount > 0) {
    lines.push('存在账实差异，已逐笔记录差异原因；需追查企业处理并评估对财务报表的影响，必要时联动 H3-10/H3-12。')
  }
  if (stats.floorToBookCount === 0 && stats.bookToFloorCount > 0) {
    lines.push('提示：尚未执行「实物→账面」完整性抽盘，建议补充以免仅测存在性。')
  }
  return lines.join('\n')
}

export function draftCheckSheetConclusion(ctx: {
  stats: H3StocktakeStats
  bookToFloorCoverage: DirectionCoverage
  floorToBookCoverage: DirectionCoverage
  meta: H3StocktakeCheckMeta
}): string {
  const { stats, bookToFloorCoverage, floorToBookCoverage, meta } = ctx
  const cov = bookToFloorCoverage.ratioPct ?? floorToBookCoverage.ratioPct
  const lines = [
    `本次投资性房地产双向抽盘${meta.countTime ? `于 ${meta.countTime}` : ''}在 ${meta.location || '____'} 执行，共检查 ${stats.total} 项（账面→实物 ${stats.bookToFloorCount}、实物→账面 ${stats.floorToBookCount}）。`,
    `账实相符 ${stats.matchCount} 项（相符率 ${stats.matchRate.toFixed(1)}%）；盘盈 ${stats.surplusCount}、盘亏 ${stats.deficitCount}；空置 ${stats.vacantCount}（空置率 ${stats.vacantRate.toFixed(1)}%）。`,
  ]
  if (cov != null) {
    lines.push(`抽盘样本占期末原值合计约 ${cov.toFixed(2)}%。`)
  } else {
    lines.push('尚未录入期末原值合计，覆盖率待补算。')
  }
  if (stats.total === 0) {
    lines.push('尚未录入抽盘明细，本节审计目标尚待执行后结论。')
  } else if (stats.floorToBookCount === 0) {
    lines.push('已完成存在性抽盘，但完整性（实物→账面）尚未执行或记录；结论暂不完全。')
  } else if (stats.deficitCount > 0 || stats.varianceCount > 0 || stats.vacantRate > 20) {
    lines.push('存在账实差异、三数量不一致或空置率偏高，已在审计说明记录；需关注减值迹象并与 H3-10/H3-12 联动。')
  } else {
    lines.push('双向抽盘未发现重大账实不符；投资性房地产存在性与完整性认定可获合理保证。')
  }
  return lines.join('\n')
}
