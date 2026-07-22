/**
 * H1-10 盘点检查表 — 对齐致同「固定资产盘点检查表」结构
 *
 * 逻辑：目标认定 → 样本选取 → 现场过程 → 双向抽盘（账面→实物/实物→账面）
 *      → 三数量差异自动计算 → 覆盖率 → 说明/结论
 */

export type StocktakeDirection = 'bookToFloor' | 'floorToBook'

/** 样本选取与现场过程元数据 */
export interface StocktakeCheckMeta {
  /** 测试总体说明（期末固定资产数量/金额） */
  testPopulation: string
  /** 特定样本说明（大额/关联方/异常） */
  specificSample: string
  /** 抽样总体说明 */
  samplingPopulation: string
  /** 抽样方法：随机/系统/货币单位/随意 等 */
  samplingMethod: string
  /** 抽样过程说明（如 IDEA） */
  samplingProcess: string
  /** 盘点地点 */
  location: string
  /** 企业盘点人员 */
  clientStaff: string
  /** 监盘人员（审计） */
  auditors: string
  /** 盘点时间 */
  countTime: string
  /** 固定资产原值合计（覆盖率分母，避免 #DIV/0!） */
  totalBookCost: number | null
}

export interface StocktakeCheckRow {
  rowId: string
  seq: number
  /** 抽盘方向：账面→实物测存在；实物→账面测完整 */
  direction: StocktakeDirection
  name: string
  assetNo: string
  location: string
  spec: string
  unit: string
  unitPrice: number
  /** 盘点前财务账面数量 */
  bookQty: number
  /** 盘点前财务账面金额（原值口径） */
  bookAmount: number
  /** 企业盘点记录数量 */
  clientCountQty: number
  /** 审计抽盘数量 */
  sampleQty: number
  /** 品质状况：正常/闲置/毁损 等 */
  qualityStatus: string
  /** 盘点结果：账实相符/盘盈/盘亏（可由数量差自动推导） */
  result: string
  diffReason: string
  /** 差异金额（手工或按单价×数量差） */
  diffAmount: number
  suggestion: string
  checker: string
  remark: string
  // ── 兼容旧字段（H1-11 回填仍可读） ──
  bookCost: number
  bookNetValue: number
  actualStatus: string
  photoUrl: string
  nameplateCheck: string
  quantityCheck: string
  conditionAssess: string
}

export interface CheckRowDiffs {
  sampleVsBook: number
  sampleVsClient: number
  clientVsBook: number
  hasVariance: boolean
}

export interface DirectionCoverage {
  sampleAmount: number
  totalBookCost: number
  /** null 表示分母为空，UI 显示「—」而非 #DIV/0! */
  ratioPct: number | null
  rowCount: number
  varianceCount: number
}

export const QUALITY_OPTS = ['正常', '闲置', '毁损', '待报废', '其他'] as const

export const SAMPLING_METHOD_OPTS = [
  '随机选样',
  '系统选样',
  '货币单位选样',
  '随意选样',
  '全面盘点',
] as const

export function createEmptyCheckMeta(): StocktakeCheckMeta {
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

export function normalizeCheckMeta(raw: unknown): StocktakeCheckMeta {
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

/** 旧行无 direction 时默认归入账面→实物 */
export function normalizeDirection(raw: unknown): StocktakeDirection {
  const s = String(raw ?? '').trim()
  if (
    s === 'floorToBook'
    || s.includes('实物→账面')
    || s.includes('实物至账面')
    || s.includes('完整')
  ) {
    return 'floorToBook'
  }
  return 'bookToFloor'
}

export function normalizeCheckRow(raw: any, idx: number): StocktakeCheckRow {
  const bookAmount = _num(raw.bookAmount ?? raw.bookCost ?? raw.originalCost)
  const bookQty = _num(raw.bookQty)
  const clientCountQty = _num(raw.clientCountQty)
  const sampleQty = _num(raw.sampleQty)
  const unitPrice = _num(raw.unitPrice)
  const direction = normalizeDirection(raw.direction)

  let result = String(raw.result ?? raw.stocktakeResult ?? '')
  if (!result && (bookQty > 0 || sampleQty > 0 || clientCountQty > 0)) {
    result = deriveResultFromQty(sampleQty, bookQty)
  }

  const quality =
    String(raw.qualityStatus ?? raw.actualStatus ?? raw.conditionAssess ?? raw.conditionEval ?? '') || ''

  return {
    rowId: raw.rowId ?? raw.id ?? `stk-${Math.random().toString(36).slice(2, 10)}`,
    seq: raw.seq ?? idx + 1,
    direction,
    name: String(raw.name ?? raw.assetName ?? ''),
    assetNo: String(raw.assetNo ?? raw.assetCode ?? ''),
    location: String(raw.location ?? ''),
    spec: String(raw.spec ?? ''),
    unit: String(raw.unit ?? ''),
    unitPrice,
    bookQty,
    bookAmount,
    clientCountQty,
    sampleQty,
    qualityStatus: quality,
    result,
    diffReason: String(raw.diffReason ?? raw.varianceReason ?? ''),
    diffAmount: _num(raw.diffAmount),
    suggestion: String(raw.suggestion ?? ''),
    checker: String(raw.checker ?? raw.inspector ?? ''),
    remark: String(raw.remark ?? ''),
    bookCost: bookAmount,
    bookNetValue: _num(raw.bookNetValue ?? raw.netValue),
    actualStatus: String(raw.actualStatus ?? (quality || '在用')),
    photoUrl: String(raw.photoUrl ?? ''),
    nameplateCheck: String(raw.nameplateCheck ?? raw.plateCheck ?? ''),
    quantityCheck: String(raw.quantityCheck ?? raw.qtyCheck ?? ''),
    conditionAssess: String(raw.conditionAssess ?? raw.conditionEval ?? ''),
  }
}

export function createEmptyCheckRow(
  direction: StocktakeDirection,
  seq: number,
  name = '',
): StocktakeCheckRow {
  return normalizeCheckRow({ direction, seq, name, result: '' }, seq - 1)
}

/** 抽盘 − 账面 → 结果 */
export function deriveResultFromQty(sampleQty: number, bookQty: number): string {
  const d = sampleQty - bookQty
  if (Math.abs(d) < 0.001) return '账实相符'
  return d > 0 ? '盘盈' : '盘亏'
}

export function calcRowDiffs(row: Pick<StocktakeCheckRow, 'sampleQty' | 'bookQty' | 'clientCountQty'>): CheckRowDiffs {
  const sampleVsBook = row.sampleQty - row.bookQty
  const sampleVsClient = row.sampleQty - row.clientCountQty
  const clientVsBook = row.clientCountQty - row.bookQty
  const hasVariance =
    Math.abs(sampleVsBook) > 0.001
    || Math.abs(sampleVsClient) > 0.001
    || Math.abs(clientVsBook) > 0.001
  return { sampleVsBook, sampleVsClient, clientVsBook, hasVariance }
}

/** 数量变更后同步 result / diffAmount / 兼容字段 */
export function applyQtySideEffects(row: StocktakeCheckRow): void {
  const diffs = calcRowDiffs(row)
  row.result = deriveResultFromQty(row.sampleQty, row.bookQty)
  row.quantityCheck = Math.abs(diffs.sampleVsBook) < 0.001 ? '一致' : '不一致'
  // 差异金额：优先 单价×数量差；无单价则保留已有金额
  if (row.unitPrice) {
    row.diffAmount = diffs.sampleVsBook * row.unitPrice
  } else if (Math.abs(diffs.sampleVsBook) < 0.001) {
    row.diffAmount = 0
  }
  row.bookCost = row.bookAmount
  if (row.qualityStatus && !row.actualStatus) {
    row.actualStatus = row.qualityStatus
  }
}

export function calcDirectionCoverage(
  rows: StocktakeCheckRow[],
  totalBookCost: number | null | undefined,
): DirectionCoverage {
  const sampleAmount = rows.reduce((s, r) => s + (Number(r.bookAmount) || 0), 0)
  const denom = totalBookCost == null ? 0 : Number(totalBookCost)
  const varianceCount = rows.filter((r) => calcRowDiffs(r).hasVariance).length
  return {
    sampleAmount,
    totalBookCost: denom,
    ratioPct: denom > 0 ? (sampleAmount / denom) * 100 : null,
    rowCount: rows.length,
    varianceCount,
  }
}

/** 从 H1-9 计划草稿现场过程（仅填空） */
export function draftMetaFromPlan(
  meta: StocktakeCheckMeta,
  plan: { stocktakeDate?: string; location?: string; participants?: string; method?: string; scope?: string },
): StocktakeCheckMeta {
  const next = { ...meta }
  if (!next.location && plan.location) next.location = plan.location
  if (!next.countTime && plan.stocktakeDate) next.countTime = plan.stocktakeDate
  if (!next.auditors && plan.participants) next.auditors = plan.participants
  // 默认「随机选样」视为未手工改过，可被计划方法覆盖
  if (plan.method === '全面盘点' && (!next.samplingMethod || next.samplingMethod === '随机选样')) {
    next.samplingMethod = '全面盘点'
  }
  if (!next.testPopulation && plan.scope) next.testPopulation = plan.scope
  return next
}

/** H1-2 明细行 → 抽盘检查行（账面→实物） */
export function mapDetailRowsToCheckRows(
  detailRows: any[],
  opts?: { direction?: StocktakeDirection; maxRows?: number; minAmount?: number },
): StocktakeCheckRow[] {
  const direction = opts?.direction ?? 'bookToFloor'
  const minAmount = opts?.minAmount ?? 0
  const maxRows = opts?.maxRows ?? 200
  const mapped = detailRows
    .map((d, i) => {
      const bookAmount = _num(
        d.originalCostEnd ?? d.originalCost ?? d.costClosing ?? d.bookCost ?? d.originalCostBegin,
      )
      if (bookAmount < minAmount) return null
      const row = createEmptyCheckRow(direction, i + 1, String(d.name ?? d.assetName ?? ''))
      row.assetNo = String(d.assetNo ?? d.assetCode ?? '')
      row.location = String(d.location ?? d.storageLocation ?? d.department ?? '')
      row.spec = String(d.spec ?? d.specification ?? '')
      row.unit = String(d.unit ?? '台')
      row.bookQty = _num(d.qty ?? d.quantity ?? d.bookQty) || 1
      row.bookAmount = bookAmount
      row.bookCost = bookAmount
      row.bookNetValue = _num(d.netValueEnd ?? d.netValue ?? d.bookNetValue)
      row.unitPrice = row.bookQty > 0 ? bookAmount / row.bookQty : bookAmount
      row.remark = '来源:H1-2'
      return row
    })
    .filter(Boolean) as StocktakeCheckRow[]
  // 大额优先
  mapped.sort((a, b) => (b.bookAmount || 0) - (a.bookAmount || 0))
  return mapped.slice(0, maxRows).map((r, i) => ({ ...r, seq: i + 1 }))
}

/** 从 H1-2 汇总期末原值（覆盖率分母） */
export function sumDetailOriginalCost(detailRows: any[]): number {
  return detailRows.reduce((s, d) => {
    const amt = _num(
      d.originalCostEnd ?? d.originalCost ?? d.costClosing ?? d.bookCost ?? d.originalCostBegin,
    )
    return s + amt
  }, 0)
}

/** H1-10 页内结论草稿（检查表口径，非 H1-11 小结） */
export function draftCheckSheetConclusion(ctx: {
  total: number
  matchCount: number
  matchRate: number
  surplusCount: number
  deficitCount: number
  surplusAmount: number
  deficitAmount: number
  bookToFloorCount: number
  floorToBookCount: number
  coveragePct: number | null
  location?: string
  countTime?: string
}): string {
  const lines = [
    `本次固定资产抽盘${ctx.countTime ? `于 ${ctx.countTime}` : ''}在 ${ctx.location || '____'} 执行，共检查 ${ctx.total} 项（账面→实物 ${ctx.bookToFloorCount}、实物→账面 ${ctx.floorToBookCount}）。`,
    `账实相符 ${ctx.matchCount} 项，相符率 ${ctx.matchRate.toFixed(1)}%；盘盈 ${ctx.surplusCount} 项（约 ${ctx.surplusAmount.toFixed(2)} 元），盘亏 ${ctx.deficitCount} 项（约 ${ctx.deficitAmount.toFixed(2)} 元）。`,
  ]
  if (ctx.coveragePct != null) {
    lines.push(`抽盘账面金额占固定资产原值合计的覆盖率约 ${ctx.coveragePct.toFixed(2)}%。`)
  } else {
    lines.push('尚未录入固定资产原值合计，覆盖率待补算。')
  }
  if (ctx.matchRate < 95 || ctx.deficitCount > 0) {
    lines.push('存在账实差异或盘亏，已在审计说明中分析原因；需关注企业对盘盈盘亏的会计处理及减值迹象，并汇入 H1-11。')
  } else if (ctx.total === 0) {
    lines.push('尚未录入抽盘明细，本节审计目标尚待执行后结论。')
  } else {
    lines.push('双向抽盘未发现重大账实不符；固定资产存在性与完整性认定可获合理保证。详见 H1-9/H1-11。')
  }
  return lines.join('\n')
}
