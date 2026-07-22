/**
 * H2-13 在建工程盘点检查表 — 对齐致同「在建工程盘点检查表」+ 参照 H1-10 固定资产盘点检查表
 *
 * 逻辑：目标认定 → 样本选取 → 现场过程 → 双向抽盘（账面→现场/现场→账面）
 *      → 三数量差异自动计算 → 覆盖率 → 进度/转固/停工观察 → 说明/结论
 *
 * CIP 相对固定资产的增量列：进度状况、是否达到可使用状态、已停工时间、停工原因
 */
import {
  calcRowDiffs,
  deriveResultFromQty,
  normalizeDirection,
  SAMPLING_METHOD_OPTS,
  type StocktakeDirection,
} from './h1StocktakeCheckModel'

export { SAMPLING_METHOD_OPTS, calcRowDiffs, deriveResultFromQty, normalizeDirection }
export type { StocktakeDirection }

/** 样本选取与现场过程元数据（与致同第二节/第三节表头一致） */
export interface H2StocktakeCheckMeta {
  testPopulation: string
  specificSample: string
  samplingPopulation: string
  samplingMethod: string
  samplingProcess: string
  location: string
  clientStaff: string
  auditors: string
  countTime: string
  /** 期末在建工程成本合计（覆盖率分母） */
  totalBookCost: number | null
}

export interface H2StocktakeCheckRow {
  rowId: string
  seq: number
  /** 抽盘方向：账面→现场测存在；现场→账面测完整 */
  direction: StocktakeDirection
  /** 在建工程名称 */
  name: string
  /** 资产/工程编号 */
  assetNo: string
  location: string
  unit: string
  unitPrice: number
  /** 盘点前财务账面数量 */
  bookQty: number
  /** 盘点前财务账面金额 */
  bookAmount: number
  /** 企业盘点记录数量 */
  clientCountQty: number
  /** 审计抽盘数量 */
  sampleQty: number
  /** 盘点结果：账实相符/盘盈/盘亏 */
  result: string
  diffReason: string
  diffAmount: number
  /** 进度状况描述（致同列） */
  progressDesc: string
  /** 是否达到预定可使用状态 */
  readyForUse: '是' | '否' | ''
  /** 已停工时间 */
  stopDuration: string
  /** 停工原因 */
  stopReason: string
  /**
   * 施工状态（兼容旧数据 / H2-15 停工联动）
   * 可由停工字段自动推导
   */
  constructionStatus: '施工中' | '停工' | '完工' | ''
  /** 形象进度(%) — 兼容旧字段 */
  visibleProgress: number | null
  remark: string
  checker: string
  photoUrl: string
}

export const READY_FOR_USE_OPTS = ['是', '否'] as const

export const CONSTRUCTION_STATUS_OPTS = ['施工中', '停工', '完工'] as const

export function createEmptyCheckMeta(): H2StocktakeCheckMeta {
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

export function normalizeCheckMeta(raw: unknown): H2StocktakeCheckMeta {
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

/** 是否视为停工（供 H2-15 联动；兼容旧 constructionStatus） */
export function isStoppedCheckRow(row: Pick<H2StocktakeCheckRow, 'constructionStatus' | 'stopDuration' | 'stopReason'>): boolean {
  if (row.constructionStatus === '停工') return true
  if (String(row.stopDuration ?? '').trim()) return true
  if (String(row.stopReason ?? '').trim()) return true
  return false
}

/** 由停工/转固字段推导施工状态（不覆盖已明确填写的状态，除非冲突） */
export function deriveConstructionStatus(row: Pick<
  H2StocktakeCheckRow,
  'constructionStatus' | 'stopDuration' | 'stopReason' | 'readyForUse'
>): H2StocktakeCheckRow['constructionStatus'] {
  if (row.constructionStatus === '停工' || row.constructionStatus === '完工' || row.constructionStatus === '施工中') {
    // 停工线索优先纠正
    if (
      row.constructionStatus !== '停工'
      && (String(row.stopDuration ?? '').trim() || String(row.stopReason ?? '').trim())
    ) {
      return '停工'
    }
    if (row.readyForUse === '是' && row.constructionStatus === '施工中') return '完工'
    return row.constructionStatus
  }
  if (String(row.stopDuration ?? '').trim() || String(row.stopReason ?? '').trim()) return '停工'
  if (row.readyForUse === '是') return '完工'
  return ''
}

export function normalizeCheckRow(raw: any, idx: number): H2StocktakeCheckRow {
  const bookAmount = _num(raw.bookAmount ?? raw.bookValue ?? raw.carryingAmount)
  const bookQty = _num(raw.bookQty)
  const clientCountQty = _num(raw.clientCountQty)
  const sampleQty = _num(raw.sampleQty)
  const unitPrice = _num(raw.unitPrice)
  const direction = normalizeDirection(raw.direction)

  let result = String(raw.result ?? raw.stocktakeResult ?? raw.auditConclusion ?? '')
  if (!result && (bookQty > 0 || sampleQty > 0 || clientCountQty > 0)) {
    result = deriveResultFromQty(sampleQty, bookQty)
  }

  // 旧字段：progressDifference / siteLocation / photos / visibleProgress
  const progressDesc = String(
    raw.progressDesc
    ?? raw.progressDifference
    ?? (raw.visibleProgress != null ? `形象进度约 ${raw.visibleProgress}%` : ''),
  )
  const stopDuration = String(raw.stopDuration ?? raw.stopTime ?? '')
  const stopReason = String(raw.stopReason ?? '')
  let constructionStatus = (raw.constructionStatus ?? '') as H2StocktakeCheckRow['constructionStatus']
  if (constructionStatus !== '施工中' && constructionStatus !== '停工' && constructionStatus !== '完工') {
    constructionStatus = ''
  }
  const readyForUse = (raw.readyForUse === '是' || raw.readyForUse === '否')
    ? raw.readyForUse
    : ('' as const)

  const row: H2StocktakeCheckRow = {
    rowId: raw.rowId ?? raw.id ?? `cip-stk-${Math.random().toString(36).slice(2, 10)}`,
    seq: raw.seq ?? idx + 1,
    direction,
    name: String(raw.name ?? raw.projectName ?? ''),
    assetNo: String(raw.assetNo ?? raw.projectCode ?? ''),
    location: String(raw.location ?? raw.siteLocation ?? ''),
    unit: String(raw.unit ?? '项'),
    unitPrice,
    bookQty,
    bookAmount,
    clientCountQty,
    sampleQty,
    result,
    diffReason: String(raw.diffReason ?? ''),
    diffAmount: _num(raw.diffAmount),
    progressDesc,
    readyForUse,
    stopDuration,
    stopReason,
    constructionStatus,
    visibleProgress: raw.visibleProgress != null ? Number(raw.visibleProgress) : null,
    remark: String(raw.remark ?? ''),
    checker: String(raw.checker ?? ''),
    photoUrl: String(raw.photoUrl ?? raw.photos ?? ''),
  }
  row.constructionStatus = deriveConstructionStatus(row)
  return row
}

export function createEmptyCheckRow(
  direction: StocktakeDirection,
  seq: number,
  name = '',
): H2StocktakeCheckRow {
  return normalizeCheckRow({ direction, seq, name, result: '' }, seq - 1)
}

/** 数量变更后同步 result / diffAmount / 施工状态 */
export function applyQtySideEffects(row: H2StocktakeCheckRow): void {
  const diffs = calcRowDiffs(row)
  if (row.bookQty > 0 || row.sampleQty > 0 || row.clientCountQty > 0) {
    row.result = deriveResultFromQty(row.sampleQty, row.bookQty)
  }
  if (row.unitPrice) {
    row.diffAmount = diffs.sampleVsBook * row.unitPrice
  } else if (Math.abs(diffs.sampleVsBook) < 0.001) {
    row.diffAmount = 0
  } else if (row.bookQty > 0 && row.bookAmount) {
    row.diffAmount = diffs.sampleVsBook * (row.bookAmount / row.bookQty)
  }
  row.constructionStatus = deriveConstructionStatus(row)
}

export function calcDirectionCoverage(
  rows: H2StocktakeCheckRow[],
  totalBookCost: number | null | undefined,
) {
  const sampleAmount = rows.reduce((s, r) => s + (Number(r.bookAmount) || 0), 0)
  const denom = totalBookCost == null ? 0 : Number(totalBookCost)
  const varianceCount = rows.filter((r) => calcRowDiffs(r).hasVariance).length
  return {
    sampleAmount,
    totalBookCost: denom,
    ratioPct: denom > 0 ? (sampleAmount / denom) * 100 : null as number | null,
    rowCount: rows.length,
    varianceCount,
  }
}

/** 从 H2-12 计划草稿现场过程（仅填空） */
export function draftMetaFromPlan(
  meta: H2StocktakeCheckMeta,
  plan: {
    inspectionDate?: string
    location?: string
    participants?: string
    scope?: string
    selectedProjects?: { name: string; reason?: string }[]
  },
): H2StocktakeCheckMeta {
  const next = { ...meta }
  if (!next.location && plan.location) next.location = plan.location
  if (!next.countTime && plan.inspectionDate) next.countTime = plan.inspectionDate
  if (!next.auditors && plan.participants) next.auditors = plan.participants
  if (!next.testPopulation && plan.scope) next.testPopulation = plan.scope
  if (!next.specificSample && plan.selectedProjects?.length) {
    const reasons = plan.selectedProjects
      .filter((p) => p.reason && p.reason !== '随机选取')
      .map((p) => `${p.name}（${p.reason}）`)
    if (reasons.length) next.specificSample = reasons.join('；')
  }
  return next
}

/** H2-2 明细 → 抽盘检查行（账面→现场） */
export function mapDetailRowsToCheckRows(
  detailRows: any[],
  opts?: { direction?: StocktakeDirection; maxRows?: number; minAmount?: number },
): H2StocktakeCheckRow[] {
  const direction = opts?.direction ?? 'bookToFloor'
  const minAmount = opts?.minAmount ?? 0
  const maxRows = opts?.maxRows ?? 200
  const mapped = detailRows
    .map((d, i) => {
      const bookAmount = _num(d.cipEnd ?? d.endAudited ?? d.netValue ?? d.unadjustedEnd)
      if (bookAmount < minAmount) return null
      const row = createEmptyCheckRow(direction, i + 1, String(d.name ?? d.projectName ?? ''))
      row.assetNo = String(d.contractNo ?? d.assetNo ?? '')
      row.location = String(d.location ?? d.contractor ?? '')
      row.unit = '项'
      row.bookQty = 1
      row.bookAmount = bookAmount
      row.unitPrice = bookAmount
      row.visibleProgress = d.completionRate != null ? Number(d.completionRate) : null
      if (row.visibleProgress != null) {
        row.progressDesc = `账面完工进度约 ${row.visibleProgress}%`
      }
      row.remark = '来源:H2-2'
      return row
    })
    .filter(Boolean) as H2StocktakeCheckRow[]
  mapped.sort((a, b) => (b.bookAmount || 0) - (a.bookAmount || 0))
  return mapped.slice(0, maxRows).map((r, i) => ({ ...r, seq: i + 1 }))
}

export function sumDetailCipCost(detailRows: any[]): number {
  return detailRows.reduce((s, d) => {
    return s + _num(d.cipEnd ?? d.endAudited ?? d.netValue ?? d.unadjustedEnd)
  }, 0)
}

/** H2-13 页内结论草稿 */
export function draftCheckSheetConclusion(ctx: {
  total: number
  matchCount: number
  matchRate: number
  surplusCount: number
  deficitCount: number
  stoppedCount: number
  readyForUseCount: number
  bookToFloorCount: number
  floorToBookCount: number
  coveragePct: number | null
  location?: string
  countTime?: string
}): string {
  const lines = [
    `本次在建工程抽盘${ctx.countTime ? `于 ${ctx.countTime}` : ''}在 ${ctx.location || '____'} 执行，共检查 ${ctx.total} 项（账面→现场 ${ctx.bookToFloorCount}、现场→账面 ${ctx.floorToBookCount}）。`,
    `账实相符 ${ctx.matchCount} 项，相符率 ${ctx.matchRate.toFixed(1)}%；盘盈 ${ctx.surplusCount} 项，盘亏 ${ctx.deficitCount} 项。`,
  ]
  if (ctx.coveragePct != null) {
    lines.push(`抽盘账面金额占期末在建工程成本合计的覆盖率约 ${ctx.coveragePct.toFixed(2)}%。`)
  } else {
    lines.push('尚未录入期末在建工程成本合计，覆盖率待补算。')
  }
  if (ctx.stoppedCount > 0) {
    lines.push(`发现停工工程 ${ctx.stoppedCount} 项，须评估减值迹象并与 H2-15 联动。`)
  }
  if (ctx.readyForUseCount > 0) {
    lines.push(`其中 ${ctx.readyForUseCount} 项现场判断已达预定可使用状态，须关注是否及时转固（→H2-5）。`)
  }
  if (ctx.matchRate < 95 || ctx.deficitCount > 0 || ctx.stoppedCount > 0) {
    lines.push('存在账实差异、盘亏或停工事项，已在审计说明中分析；需关注企业处理及减值/转固跟进，并汇入 H2-14。')
  } else if (ctx.total === 0) {
    lines.push('尚未录入抽盘明细，本节审计目标尚待执行后结论。')
  } else {
    lines.push('双向抽盘未发现重大账实不符；在建工程存在性与完整性认定可获合理保证。详见 H2-12/H2-14。')
  }
  return lines.join('\n')
}

export function draftCheckSheetNote(ctx: {
  location?: string
  countTime?: string
  samplingMethod?: string
  specificSample?: string
  varianceCount: number
  stoppedCount: number
  readyForUseCount: number
}): string {
  return [
    `监盘地点：${ctx.location || '____'}；时间：${ctx.countTime || '____'}。`,
    `抽样方法：${ctx.samplingMethod || '____'}；特定样本：${ctx.specificSample || '无'}。`,
    `数量差异行 ${ctx.varianceCount} 项；停工 ${ctx.stoppedCount} 项；已达可使用状态 ${ctx.readyForUseCount} 项。`,
    '财务账面应与工程/资产管理部门记录核对一致；账面与实盘差异构成盘盈/盘亏，须分析原因并说明企业处理结果。',
    '盘点时关注易侵占工程物资、长期停滞及可能减值的存量工程；品质/形象进度影响减值与转固时点判断。',
  ].join('\n')
}
