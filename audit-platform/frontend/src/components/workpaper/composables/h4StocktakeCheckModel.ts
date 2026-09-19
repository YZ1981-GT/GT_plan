/**
 * H4-6 工程物资盘点检查表 — 对齐致同「盘点检查表H4-6」+ 参照 H1-10 双向抽盘
 *
 * 逻辑：目标认定 → 样本选取 → 现场过程 → 双向抽盘（账面→实物 / 实物→账面）
 *      → 三数量差异自动计算 → 覆盖率（避免 #DIV/0!）→ 品质状况 → 说明/结论
 *      → 闲置/毁损/盘亏推送 H4-7 减值关注
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

export type H4StocktakeCheckMeta = StocktakeCheckMeta

/** 品质状况（致同 H4-6 L 列） */
export const H4_QUALITY_OPTS = ['正常', '闲置', '毁损', '待报废', '积压', '其他'] as const

export const ITEM_H47_STOCKTAKE_CONCERNS = 'H4-7-stocktake-concerns'

export interface H4StocktakeCheckRow {
  rowId: string
  seq: number
  /** 抽盘方向：账面→实物测存在；实物→账面测完整 */
  direction: StocktakeDirection
  /** 工程物资名称/类别 */
  name: string
  /** 资产编号 */
  assetNo: string
  /** 规格型号 */
  spec: string
  /** 单位 */
  unit: string
  /** 存放位置（现场补充，非致同主列） */
  location: string
  unitPrice: number
  /** 盘点前财务账面数量 */
  bookQty: number
  /** 盘点前财务账面金额 */
  bookAmount: number
  /** 企业盘点记录数量 */
  clientCountQty: number
  /** 审计抽盘数量 */
  sampleQty: number
  /** 品质状况：正常/闲置/毁损等 */
  qualityStatus: string
  /** 盘点结果：账实相符/盘盈/盘亏 */
  result: string
  diffReason: string
  /** 差异金额（单价×抽盘与账面数量差） */
  diffAmount: number
  remark: string
  /** 兼容旧版 countDate */
  countDate: string
}

export interface H4StocktakeImpairmentConcern {
  sourceRowId: string
  name: string
  assetNo: string
  bookAmount: number
  reasons: string[]
  qualityStatus: string
  result: string
  remark: string
}

export function createEmptyCheckMeta(): H4StocktakeCheckMeta {
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

export function normalizeCheckMeta(raw: unknown): H4StocktakeCheckMeta {
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

/**
 * 兼容旧 H4-6 行：
 * bookAmt→bookAmount；countQty→sampleQty；无企业盘点时默认=账面
 */
export function normalizeCheckRow(raw: any, idx: number): H4StocktakeCheckRow {
  const bookAmount = _num(raw.bookAmount ?? raw.bookAmt)
  const bookQty = _num(raw.bookQty)
  const hasExplicitClient = raw.clientCountQty != null && raw.clientCountQty !== ''
  const hasExplicitSample =
    (raw.sampleQty != null && raw.sampleQty !== '')
    || (raw.countQty != null && raw.countQty !== '')
  const clientCountQty = hasExplicitClient
    ? _num(raw.clientCountQty)
    : (hasExplicitSample ? _num(raw.countQty ?? raw.sampleQty) : bookQty)
  const sampleQty = hasExplicitSample
    ? _num(raw.sampleQty ?? raw.countQty)
    : bookQty

  let unitPrice = _num(raw.unitPrice)
  if (!unitPrice && bookQty > 0 && bookAmount > 0) {
    unitPrice = bookAmount / bookQty
  } else if (!unitPrice && _num(raw.countAmt) && sampleQty > 0) {
    unitPrice = _num(raw.countAmt) / sampleQty
  }

  const direction = normalizeDirection(raw.direction)
  let result = String(raw.result ?? raw.stocktakeResult ?? '')
  if (!result && (bookQty > 0 || sampleQty > 0 || clientCountQty > 0 || bookAmount > 0)) {
    result = deriveResultFromQty(sampleQty, bookQty)
  }

  return {
    rowId: raw.rowId ?? raw.id ?? `h4st-${Math.random().toString(36).slice(2, 10)}`,
    seq: raw.seq ?? idx + 1,
    direction,
    name: String(raw.name ?? raw.materialName ?? ''),
    assetNo: String(raw.assetNo ?? raw.assetCode ?? ''),
    spec: String(raw.spec ?? ''),
    unit: String(raw.unit ?? '') || '件',
    location: String(raw.location ?? ''),
    unitPrice,
    bookQty,
    bookAmount,
    clientCountQty,
    sampleQty,
    qualityStatus: String(raw.qualityStatus ?? ''),
    result,
    diffReason: String(raw.diffReason ?? raw.varianceReason ?? ''),
    diffAmount: _num(raw.diffAmount),
    remark: String(raw.remark ?? ''),
    countDate: String(raw.countDate ?? ''),
  }
}

export function createEmptyCheckRow(
  direction: StocktakeDirection,
  seq: number,
  name = '',
): H4StocktakeCheckRow {
  return normalizeCheckRow(
    { direction, seq, name, bookQty: 0, clientCountQty: 0, sampleQty: 0 },
    seq - 1,
  )
}

export function applyQtySideEffects(row: H4StocktakeCheckRow): void {
  const diffs = calcRowDiffs(row)
  row.result = deriveResultFromQty(row.sampleQty, row.bookQty)
  if (row.unitPrice) {
    row.diffAmount = diffs.sampleVsBook * row.unitPrice
  } else if (Math.abs(diffs.sampleVsBook) < 0.001) {
    row.diffAmount = 0
  } else if (row.bookQty > 0 && row.bookAmount) {
    row.diffAmount = diffs.sampleVsBook * (row.bookAmount / row.bookQty)
  }
}

/** H4-2 明细 → 盘点行（默认账面→实物，大额优先） */
export function mapH42RowsToCheckRows(
  detailRows: any[],
  opts?: {
    direction?: StocktakeDirection
    maxRows?: number
    minAmount?: number
  },
): H4StocktakeCheckRow[] {
  const direction = opts?.direction ?? 'bookToFloor'
  const minAmount = opts?.minAmount ?? 0
  const maxRows = opts?.maxRows ?? 200

  const mapped = detailRows
    .map((d, i) => {
      const bookAmount = _num(d.endAmount ?? d.bookAmount ?? d.bookAmt)
      if (bookAmount < minAmount) return null
      const qty = _num(d.endQty ?? d.quantity ?? d.bookQty) || 0
      const name = String(d.name ?? '').trim()
        || String(d.category ?? '').trim()
        || `物资${i + 1}`
      const row = createEmptyCheckRow(direction, i + 1, name)
      if (d.category && d.name) {
        row.name = `${d.category}/${d.name}`
      }
      row.assetNo = String(d.rowId ?? '').replace(/^row-/, '').slice(0, 14)
      row.spec = String(d.spec ?? '')
      row.unit = String(d.unit ?? '') || '件'
      row.bookQty = qty
      row.clientCountQty = qty
      row.sampleQty = qty
      row.bookAmount = bookAmount
      row.unitPrice = qty > 0 ? bookAmount / qty : bookAmount
      row.remark = '来源:H4-2'
      return row
    })
    .filter(Boolean) as H4StocktakeCheckRow[]

  mapped.sort((a, b) => (b.bookAmount || 0) - (a.bookAmount || 0))
  return mapped.slice(0, maxRows).map((r, i) => ({ ...r, seq: i + 1 }))
}

export function sumH42EndAmount(detailRows: any[]): number {
  return detailRows.reduce((s, d) => s + _num(d.endAmount ?? d.bookAmount ?? d.bookAmt), 0)
}

export interface H4StocktakeStats {
  total: number
  matchCount: number
  surplusCount: number
  deficitCount: number
  matchRate: number
  varianceCount: number
  deficitAmount: number
  surplusAmount: number
  bookToFloorCount: number
  floorToBookCount: number
  idleCount: number
  damagedCount: number
  concernCount: number
}

export function calcStocktakeStats(rows: H4StocktakeCheckRow[]): H4StocktakeStats {
  const total = rows.length
  const matchCount = rows.filter((r) => r.result === '账实相符').length
  const surplusCount = rows.filter((r) => r.result === '盘盈').length
  const deficitCount = rows.filter((r) => r.result === '盘亏').length
  const varianceCount = rows.filter((r) => calcRowDiffs(r).hasVariance).length
  const idleCount = rows.filter((r) => r.qualityStatus === '闲置' || r.qualityStatus === '积压').length
  const damagedCount = rows.filter((r) =>
    r.qualityStatus === '毁损' || r.qualityStatus === '待报废',
  ).length
  const concernCount = rows.filter((r) => isImpairmentConcern(r)).length
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
    varianceCount,
    deficitAmount,
    surplusAmount,
    bookToFloorCount: rows.filter((r) => r.direction !== 'floorToBook').length,
    floorToBookCount: rows.filter((r) => r.direction === 'floorToBook').length,
    idleCount,
    damagedCount,
    concernCount,
  }
}

export function isImpairmentConcern(row: H4StocktakeCheckRow): boolean {
  return (
    row.qualityStatus === '闲置'
    || row.qualityStatus === '积压'
    || row.qualityStatus === '毁损'
    || row.qualityStatus === '待报废'
    || row.result === '盘亏'
  )
}

export function collectStocktakeImpairmentConcerns(
  rows: H4StocktakeCheckRow[],
): H4StocktakeImpairmentConcern[] {
  const out: H4StocktakeImpairmentConcern[] = []
  for (const r of rows) {
    if (!isImpairmentConcern(r)) continue
    const reasons: string[] = []
    if (r.qualityStatus === '闲置' || r.qualityStatus === '积压') reasons.push(r.qualityStatus)
    if (r.qualityStatus === '毁损' || r.qualityStatus === '待报废') reasons.push(r.qualityStatus)
    if (r.result === '盘亏') reasons.push('盘亏')
    out.push({
      sourceRowId: r.rowId,
      name: r.name,
      assetNo: r.assetNo,
      bookAmount: r.bookAmount,
      reasons,
      qualityStatus: r.qualityStatus,
      result: r.result,
      remark: r.diffReason || r.remark || '',
    })
  }
  return out
}

export function draftCheckSheetNote(ctx: {
  stats: H4StocktakeStats
  meta: H4StocktakeCheckMeta
  bookToFloorCoverage: DirectionCoverage
  floorToBookCoverage: DirectionCoverage
}): string {
  const { stats, meta, bookToFloorCoverage, floorToBookCoverage } = ctx
  const lines = [
    `盘点地点：${meta.location || '____'}；时间：${meta.countTime || '____'}；企业人员：${meta.clientStaff || '____'}；监盘：${meta.auditors || '____'}。`,
    `测试总体：${meta.testPopulation || '（待填）'}；抽样方法：${meta.samplingMethod || '—'}。`,
    `共抽盘 ${stats.total} 项（账面→实物 ${stats.bookToFloorCount}、实物→账面 ${stats.floorToBookCount}），账实相符 ${stats.matchCount}、盘盈 ${stats.surplusCount}、盘亏 ${stats.deficitCount}；三数量差异 ${stats.varianceCount} 项。`,
  ]
  if (stats.idleCount || stats.damagedCount) {
    lines.push(`品质关注：闲置/积压 ${stats.idleCount}、毁损/待报废 ${stats.damagedCount}，需联动减值测算（H4-7）。`)
  }
  if (bookToFloorCoverage.ratioPct != null) {
    lines.push(`账面→实物覆盖率：抽盘金额 ${bookToFloorCoverage.sampleAmount.toFixed(2)} / 期末余额 ${bookToFloorCoverage.totalBookCost.toFixed(2)} = ${bookToFloorCoverage.ratioPct.toFixed(2)}%。`)
  }
  if (floorToBookCoverage.ratioPct != null) {
    lines.push(`实物→账面覆盖率：抽盘金额 ${floorToBookCoverage.sampleAmount.toFixed(2)} / 期末余额 ${floorToBookCoverage.totalBookCost.toFixed(2)} = ${floorToBookCoverage.ratioPct.toFixed(2)}%。`)
  }
  if (bookToFloorCoverage.ratioPct == null && floorToBookCoverage.ratioPct == null) {
    lines.push('尚未录入期末工程物资余额合计，样本覆盖率待补算（请自 H4-2 同步或手工填入，避免除零）。')
  }
  if (stats.deficitCount > 0 || stats.varianceCount > 0) {
    lines.push('存在账实/三数量差异，已逐笔记录；需追查企业处理并评估对财务报表的影响。监盘计划与小结可参考固定资产（H1）做法。')
  }
  if (stats.floorToBookCount === 0 && stats.bookToFloorCount > 0) {
    lines.push('提示：尚未执行「实物→账面」完整性抽盘，建议补充以免仅测存在性。')
  }
  return lines.join('\n')
}

export function draftCheckSheetConclusion(ctx: {
  stats: H4StocktakeStats
  bookToFloorCoverage: DirectionCoverage
  floorToBookCoverage: DirectionCoverage
  meta: H4StocktakeCheckMeta
}): string {
  const { stats, bookToFloorCoverage, floorToBookCoverage, meta } = ctx
  const cov = bookToFloorCoverage.ratioPct ?? floorToBookCoverage.ratioPct
  const lines = [
    `本次工程物资双向抽盘${meta.countTime ? `于 ${meta.countTime}` : ''}在 ${meta.location || '____'} 执行，共检查 ${stats.total} 项（账面→实物 ${stats.bookToFloorCount}、实物→账面 ${stats.floorToBookCount}）。`,
    `账实相符 ${stats.matchCount} 项（相符率 ${stats.matchRate.toFixed(1)}%）；盘盈 ${stats.surplusCount}、盘亏 ${stats.deficitCount}。`,
  ]
  if (cov != null) {
    lines.push(`抽盘样本占期末工程物资余额约 ${cov.toFixed(2)}%。`)
  } else {
    lines.push('尚未录入期末余额合计，覆盖率待补算。')
  }
  if (stats.total === 0) {
    lines.push('尚未录入抽盘明细，本节审计目标尚待执行后结论。')
  } else if (stats.floorToBookCount === 0) {
    lines.push('已完成存在性抽盘，但完整性（实物→账面）尚未执行或记录；结论暂不完全。')
  } else if (stats.deficitCount > 0 || stats.varianceCount > 0 || stats.concernCount > 0) {
    lines.push('存在账实差异、三数量不一致或品质异常（闲置/毁损等），已在盘点情况说明记录；需关注减值迹象并与 H4-7/H4-8 联动。')
  } else {
    lines.push('双向抽盘未发现重大账实不符；工程物资存在性与完整性认定可获合理保证。')
  }
  return lines.join('\n')
}
