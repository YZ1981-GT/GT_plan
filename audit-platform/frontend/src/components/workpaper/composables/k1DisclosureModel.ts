/**
 * K1 其他应收款附注披露（上市公司）数据模型与聚合
 *
 * 对齐源底稿「附注披露信息（上市公司）」+ note_template_listed §五、8
 * 账龄段跟随项目 aging config（THREE_YEAR / FIVE_YEAR / CUSTOM）
 */
import type { AgingSegment } from '@/composables/useAgingConfig'
import { parseNum } from './useD2FormulaEngine'
import {
  dominantAgingLabel,
  extractTopLargeFromK1Detail,
  loadK1DetailPartials,
  type K1DetailPartial,
} from './k1CrossHelpers'
import type { K1StageMovementRow } from './useK1BadDebt'
import { parseK13Payload, recalcStageClosing } from './useK1BadDebt'
import { parseK1StageRowsFromMap, type K1StageRow } from './useK1StageCheck'
import { buildDisclosureAgingLabelMap } from './disclosureAgingLabels'

// ─── Types ───────────────────────────────────────────────────────────────────

/**
 * data       普通账龄段行（参与 subtotal 求和）
 * sub        1 年以内月度细分行（源模板「其中：0-X个月」/「X-Y个月」），**不参与** subtotal 求和
 * subtotal1y 1 年以内小计（只读，= within1 的 data 行金额）
 */
export type K1AgingRowKind = 'data' | 'sub' | 'subtotal1y' | 'subtotal' | 'provision' | 'total'

export interface K1AgingDisclosureRow {
  rowId: string
  segmentKey: string
  label: string
  kind: K1AgingRowKind
  endAmount: number
  priorAmount: number
  editable: boolean
  autoFilled?: boolean
  /** sub 行：标签可编辑（月度区间由项目自定） */
  labelEditable?: boolean
}

export interface K1NatureDisclosureRow {
  rowId: string
  label: string
  endGross: number
  endProvision: number
  endBookValue: number
  priorGross: number
  priorProvision: number
  priorBookValue: number
  editable: boolean
  autoFilled?: boolean
}

export interface K1StageEclDisclosureRow {
  rowId: string
  rowKey: string
  label: string
  kind: 'header' | 'data' | 'subtotal' | 'total'
  balance: number
  eclRate: number | null
  provision: number
  bookValue: number
  reason: string
  editable: boolean
  autoFilled?: boolean
}

export interface K1ReversalDisclosureRow {
  rowId: string
  unitName: string
  reason: string
  method: string
  basis: string
  amount: number
  /** 转回或收回前累计已计提坏账准备金额（国企源模板 R92 专有列，上市版不披露） */
  cumulativeProvision?: number
}

export interface K1WriteoffDisclosureRow {
  rowId: string
  unitName: string
  nature: string
  amount: number
  reason: string
  procedure: string
  relatedParty: string
}

export interface K1Top5DisclosureRow {
  rowId: string
  unitName: string
  nature: string
  endBalance: number
  aging: string
  proportionPct: number
  provision: number
  autoFilled?: boolean
}

export interface K1GovGrantRow {
  rowId: string
  unitName: string
  projectName: string
  endBalance: number
  aging: string
  expectedCollection: string
}

export interface K1TransferRow {
  rowId: string
  item: string
  method: string
  derecognizedAmount: number
  gainLoss: number
}

/** 转移且继续涉入形成的资产 / 负债明细（源模板 listed R153-R159 / soe R117-R123） */
export interface K1ContinuedInvolvementRow {
  rowId: string
  side: 'asset' | 'liability'
  item: string
  amount: number
}

/**
 * notes key 约定（两版共用，见 spec design §2.4）
 * balanceChange / eclBasis / writeoffNote / transferNote
 * stage2NoneTextEnd / stage2NoneTextPrior
 */
export const K1_NOTE_KEYS = {
  balanceChange: 'balanceChange',
  eclBasis: 'eclBasis',
  writeoffNote: 'writeoffNote',
  transferNote: 'transferNote',
} as const

export const K1_STAGE2_NONE_TEXT_END =
  '期末，本公司不存在处于第二阶段的应收利息、应收股利和其他应收款。'
export const K1_STAGE2_NONE_TEXT_PRIOR =
  '截至上年年末，本公司不存在处于第二阶段的应收利息、应收股利和其他应收款。'

export interface K1ListedDisclosurePayloadV2 {
  version: 2
  agingRows: K1AgingDisclosureRow[]
  natureRows: K1NatureDisclosureRow[]
  stage1Rows: K1StageEclDisclosureRow[]
  stage2Rows: K1StageEclDisclosureRow[]
  stage3Rows: K1StageEclDisclosureRow[]
  /** 上年年末三阶段快照（源模板 R61-R89） */
  priorStage1Rows: K1StageEclDisclosureRow[]
  priorStage2Rows: K1StageEclDisclosureRow[]
  priorStage3Rows: K1StageEclDisclosureRow[]
  /** 【或】不存在处于第二阶段（源模板 R49 / R80） */
  stage2NoneEnd: boolean
  stage2NonePrior: boolean
  stageMovements: K1StageMovementRow[]
  reversalRows: K1ReversalDisclosureRow[]
  writeoffSummaryAmount: number
  writeoffDetailRows: K1WriteoffDisclosureRow[]
  top5Rows: K1Top5DisclosureRow[]
  fundCentralizationAmount: number
  fundCentralizationNote: string
  govGrantRows: K1GovGrantRow[]
  transferRows: K1TransferRow[]
  continuedInvolvementRows: K1ContinuedInvolvementRow[]
  /** @deprecated 由 continuedInvolvementRows 小计派生，仅为旧 payload 兼容保留 */
  continuedInvolvementAssets: number
  /** @deprecated 同上 */
  continuedInvolvementLiabilities: number
  notes: Record<string, string>
}

/** 继续涉入表小计（资产 / 负债各自求和） */
export function summarizeContinuedInvolvement(rows: K1ContinuedInvolvementRow[]): {
  assets: number
  liabilities: number
} {
  return {
    assets: rows.filter((r) => r.side === 'asset').reduce((s, r) => s + parseNum(r.amount), 0),
    liabilities: rows
      .filter((r) => r.side === 'liability')
      .reduce((s, r) => s + parseNum(r.amount), 0),
  }
}

/** 旧标量 continuedInvolvementAssets/Liabilities → 明细行迁移 */
export function migrateContinuedInvolvement(
  rows: unknown,
  legacyAssets: unknown,
  legacyLiabilities: unknown,
): K1ContinuedInvolvementRow[] {
  if (Array.isArray(rows) && rows.length) {
    return rows
      .filter((r): r is Record<string, unknown> => !!r && typeof r === 'object')
      .map((r) => ({
        rowId: String(r.rowId || uid('ci')),
        side: r.side === 'liability' ? 'liability' : 'asset',
        item: String(r.item ?? ''),
        amount: parseNum(r.amount),
      }))
  }
  const out: K1ContinuedInvolvementRow[] = []
  const a = parseNum(legacyAssets)
  const l = parseNum(legacyLiabilities)
  if (a) out.push({ rowId: uid('ci'), side: 'asset', item: '继续涉入形成的资产', amount: a })
  if (l) out.push({ rowId: uid('ci'), side: 'liability', item: '继续涉入形成的负债', amount: l })
  return out
}

export const K1_DISC_STORAGE_KEY = 'K1-note-listed-rows'
export const K1_DISC_NOTE_KEY = 'K1-note-listed-note'

export const K1_DEFAULT_NATURE_LABELS = ['备用金', '保证金、押金'] as const

/**
 * 附注模板账龄标签（`1至2年` 口径）。
 * 字面量已收敛到共享模块 `disclosureAgingLabels`（原 per-cycle 表与共享表逐项同值）；
 * K1 首档用通用 `1年以内`，故不传 overrides。
 */
export const K1_NOTE_AGING_LABEL: Record<string, string> = buildDisclosureAgingLabelMap()

// ─── Helpers ─────────────────────────────────────────────────────────────────

function uid(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

export function noteAgingLabel(key: string, fallbackLabel?: string): string {
  return K1_NOTE_AGING_LABEL[key] || fallbackLabel || key
}

export function aggregateAgingFromK1Detail(
  details: K1DetailPartial[],
  segmentKeys: string[],
): { end: Record<string, number>; prior: Record<string, number> } {
  const end: Record<string, number> = Object.fromEntries(segmentKeys.map((k) => [k, 0]))
  const prior: Record<string, number> = Object.fromEntries(segmentKeys.map((k) => [k, 0]))
  for (const d of details) {
    for (const [k, v] of Object.entries(d.agingAudited || {})) {
      if (k in end) end[k] += parseNum(v)
    }
    for (const [k, v] of Object.entries(d.agingPrior || {})) {
      if (k in prior) prior[k] += parseNum(v)
    }
  }
  return { end, prior }
}

export interface K1NatureAggregate {
  endGross: number
  endProvision: number
  priorGross: number
  priorProvision: number
}

export function aggregateNatureFromK1Detail(
  details: K1DetailPartial[],
): Map<string, K1NatureAggregate> {
  const map = new Map<string, K1NatureAggregate>()
  for (const d of details) {
    const label = String(d.nature || '').trim() || '其他'
    const hit = map.get(label) || { endGross: 0, endProvision: 0, priorGross: 0, priorProvision: 0 }
    hit.endGross += parseNum(d.endBalance)
    hit.endProvision += parseNum(d.badDebtProvision)
    hit.priorGross += parseNum(d.beginBalance)
    map.set(label, hit)
  }
  return map
}

/** 源模板 R9/R10：1 年以内月度细分行默认标签 */
export const K1_WITHIN1_SUB_LABELS = ['其中：0-6个月', '7-12个月'] as const

export function buildAgingDisclosureRows(
  segments: AgingSegment[],
  agg: { end: Record<string, number>; prior: Record<string, number> },
  provision: { end: number; prior: number },
  opts: { withinOneYearBreakdown?: boolean; withinOneYearSubLabels?: readonly string[] } = {},
): K1AgingDisclosureRow[] {
  const withBreakdown = opts.withinOneYearBreakdown ?? true
  const subLabels = opts.withinOneYearSubLabels ?? K1_WITHIN1_SUB_LABELS

  const dataRows: K1AgingDisclosureRow[] = []
  for (const seg of segments) {
    dataRows.push({
      rowId: uid('aging'),
      segmentKey: seg.key,
      label: noteAgingLabel(seg.key, seg.label),
      kind: 'data',
      endAmount: parseNum(agg.end[seg.key]),
      priorAmount: parseNum(agg.prior[seg.key]),
      editable: true,
      autoFilled: true,
    })
    // 源模板 R9~R12：1 年以内下挂月度细分 + 1年以内小计
    if (withBreakdown && seg.key === 'within1') {
      subLabels.forEach((label, i) => {
        dataRows.push({
          rowId: uid('agingsub'),
          segmentKey: `within1-sub${i + 1}`,
          label,
          kind: 'sub',
          endAmount: 0,
          priorAmount: 0,
          editable: true,
          labelEditable: true,
        })
      })
      dataRows.push({
        rowId: uid('aging1y'),
        segmentKey: 'subtotal1y',
        label: '1年以内小计：',
        kind: 'subtotal1y',
        endAmount: parseNum(agg.end[seg.key]),
        priorAmount: parseNum(agg.prior[seg.key]),
        editable: false,
      })
    }
  }

  const isSummable = (r: K1AgingDisclosureRow) => r.kind === 'data'
  const subtotalEnd = dataRows.filter(isSummable).reduce((s, r) => s + r.endAmount, 0)
  const subtotalPrior = dataRows.filter(isSummable).reduce((s, r) => s + r.priorAmount, 0)

  dataRows.push({
    rowId: uid('aging'),
    segmentKey: 'subtotal',
    label: '小计',
    kind: 'subtotal',
    endAmount: subtotalEnd,
    priorAmount: subtotalPrior,
    editable: false,
  })
  dataRows.push({
    rowId: uid('aging'),
    segmentKey: 'provision',
    label: '减：坏账准备',
    kind: 'provision',
    endAmount: provision.end,
    priorAmount: provision.prior,
    editable: true,
    autoFilled: true,
  })
  dataRows.push({
    rowId: uid('aging'),
    segmentKey: 'total',
    label: '合计',
    kind: 'total',
    endAmount: subtotalEnd - provision.end,
    priorAmount: subtotalPrior - provision.prior,
    editable: false,
  })
  return dataRows
}

export function buildNatureDisclosureRows(
  natureMap: Map<string, K1NatureAggregate>,
  defaults: readonly string[] = K1_DEFAULT_NATURE_LABELS,
): K1NatureDisclosureRow[] {
  const labels = new Set<string>([...defaults, ...natureMap.keys()])
  const rows: K1NatureDisclosureRow[] = []
  for (const label of labels) {
    const hit = natureMap.get(label)
    const endGross = hit?.endGross ?? 0
    const endProvision = hit?.endProvision ?? 0
    const priorGross = hit?.priorGross ?? 0
    const priorProvision = hit?.priorProvision ?? 0
    if (!hit && !defaults.includes(label as typeof K1_DEFAULT_NATURE_LABELS[number])) continue
    rows.push({
      rowId: uid('nature'),
      label,
      endGross,
      endProvision,
      endBookValue: endGross - endProvision,
      priorGross,
      priorProvision,
      priorBookValue: priorGross - priorProvision,
      editable: true,
      autoFilled: !!hit,
    })
  }
  if (!rows.length) {
    for (const label of defaults) {
      rows.push({
        rowId: uid('nature'),
        label,
        endGross: 0,
        endProvision: 0,
        endBookValue: 0,
        priorGross: 0,
        priorProvision: 0,
        priorBookValue: 0,
        editable: true,
      })
    }
  }
  return rows
}

export function summarizeNatureRows(rows: K1NatureDisclosureRow[]): K1NatureDisclosureRow {
  const sum = (pick: (r: K1NatureDisclosureRow) => number) =>
    rows.reduce((s, r) => s + pick(r), 0)
  return {
    rowId: '__total__',
    label: '合计',
    endGross: sum((r) => r.endGross),
    endProvision: sum((r) => r.endProvision),
    endBookValue: sum((r) => r.endBookValue),
    priorGross: sum((r) => r.priorGross),
    priorProvision: sum((r) => r.priorProvision),
    priorBookValue: sum((r) => r.priorBookValue),
    editable: false,
  }
}

function createStageBlockRows(stage: 1 | 2 | 3, portfolioLabels: string[]): K1StageEclDisclosureRow[] {
  const rows: K1StageEclDisclosureRow[] = [
    {
      rowId: uid('stg'),
      rowKey: 'individual-header',
      label: '按单项计提坏账准备',
      kind: 'header',
      balance: 0,
      eclRate: null,
      provision: 0,
      bookValue: 0,
      reason: '',
      editable: false,
    },
    {
      rowId: uid('stg'),
      rowKey: 'individual-1',
      label: '其他应收款单位1',
      kind: 'data',
      balance: 0,
      eclRate: 0,
      provision: 0,
      bookValue: 0,
      reason: '',
      editable: true,
    },
    {
      rowId: uid('stg'),
      rowKey: 'individual-2',
      label: '其他应收款单位2',
      kind: 'data',
      balance: 0,
      eclRate: 0,
      provision: 0,
      bookValue: 0,
      reason: '',
      editable: true,
    },
    {
      rowId: uid('stg'),
      rowKey: 'portfolio-header',
      label: '按组合计提坏账准备【注意：与会计政策中披露的组合保持一致】',
      kind: 'subtotal',
      balance: 0,
      eclRate: null,
      provision: 0,
      bookValue: 0,
      reason: '',
      editable: false,
    },
  ]
  for (let i = 0; i < portfolioLabels.length; i++) {
    rows.push({
      rowId: uid('stg'),
      rowKey: `portfolio-${i}`,
      label: portfolioLabels[i],
      kind: 'data',
      balance: 0,
      eclRate: 0,
      provision: 0,
      bookValue: 0,
      reason: '',
      editable: true,
    })
  }
  rows.push({
    rowId: uid('stg'),
    rowKey: 'total',
    label: '合计',
    kind: 'total',
    balance: 0,
    eclRate: null,
    provision: 0,
    bookValue: 0,
    reason: '',
    editable: false,
  })
  return rows
}

export function recomputeStageEclRows(rows: K1StageEclDisclosureRow[]): K1StageEclDisclosureRow[] {
  const next = rows.map((r) => ({ ...r }))
  for (const r of next) {
    if (r.kind === 'data') {
      r.bookValue = Math.round((r.balance - r.provision) * 100) / 100
    }
  }
  const dataRows = next.filter((r) => r.kind === 'data')
  const total = next.find((r) => r.rowKey === 'total')
  const portfolioHeader = next.find((r) => r.rowKey === 'portfolio-header')
  if (portfolioHeader) {
    const portfolioData = dataRows.filter((r) => r.rowKey.startsWith('portfolio-'))
    portfolioHeader.balance = portfolioData.reduce((s, r) => s + r.balance, 0)
    portfolioHeader.provision = portfolioData.reduce((s, r) => s + r.provision, 0)
    portfolioHeader.bookValue = portfolioHeader.balance - portfolioHeader.provision
  }
  if (total) {
    total.balance = dataRows.reduce((s, r) => s + r.balance, 0)
    total.provision = dataRows.reduce((s, r) => s + r.provision, 0)
    total.bookValue = total.balance - total.provision
  }
  return next
}

export function buildDefaultStageBlocks(portfolioLabels: string[] = [...K1_DEFAULT_NATURE_LABELS]): {
  stage1: K1StageEclDisclosureRow[]
  stage2: K1StageEclDisclosureRow[]
  stage3: K1StageEclDisclosureRow[]
} {
  return {
    stage1: recomputeStageEclRows(createStageBlockRows(1, portfolioLabels)),
    stage2: recomputeStageEclRows(createStageBlockRows(2, portfolioLabels)),
    stage3: recomputeStageEclRows(createStageBlockRows(3, portfolioLabels)),
  }
}

export function buildTop5FromK1Detail(details: K1DetailPartial[], limit = 5): K1Top5DisclosureRow[] {
  const imported = extractTopLargeFromK1Detail(details, { limit, excludeRelated: false })
  const total = imported.reduce((s, r) => s + r.closingBalance, 0) || 1
  return imported.map((r) => ({
    rowId: uid('top5'),
    unitName: r.debtorName,
    nature: r.businessDesc,
    endBalance: r.closingBalance,
    aging: r.aging,
    proportionPct: Math.round((r.closingBalance / total) * 10000) / 100,
    provision: r.provision,
    autoFilled: true,
  }))
}

export function readK13StageMovements(raw: unknown): K1StageMovementRow[] {
  return parseK13Payload(raw).stageMovements
}

/** K1-9 转回检查行 → 披露表转回行（`accumProvision` = 转回前累计已计提坏账准备） */
export function mapK9ReversalRow(r: any): K1ReversalDisclosureRow {
  return {
    rowId: r?.id || uid('rev'),
    unitName: r?.unit || '',
    reason: r?.reason || '',
    method: r?.method || '',
    basis: r?.basis || '',
    amount: parseNum(r?.amount),
    cumulativeProvision: parseNum(r?.accumProvision),
  }
}

export function emptyK1ListedPayload(portfolioLabels?: string[]): K1ListedDisclosurePayloadV2 {
  const stages = buildDefaultStageBlocks(portfolioLabels)
  const priorStages = buildDefaultStageBlocks(portfolioLabels)
  return {
    version: 2,
    agingRows: [],
    natureRows: buildNatureDisclosureRows(new Map()),
    stage1Rows: stages.stage1,
    stage2Rows: stages.stage2,
    stage3Rows: stages.stage3,
    priorStage1Rows: priorStages.stage1,
    priorStage2Rows: priorStages.stage2,
    priorStage3Rows: priorStages.stage3,
    stage2NoneEnd: false,
    stage2NonePrior: false,
    stageMovements: [],
    reversalRows: [],
    writeoffSummaryAmount: 0,
    writeoffDetailRows: [],
    top5Rows: [],
    fundCentralizationAmount: 0,
    fundCentralizationNote: '',
    govGrantRows: [],
    transferRows: [],
    continuedInvolvementRows: [],
    continuedInvolvementAssets: 0,
    continuedInvolvementLiabilities: 0,
    notes: {},
  }
}

export function parseK1ListedPayload(raw: unknown, segments: AgingSegment[]): K1ListedDisclosurePayloadV2 {
  if (!raw) return emptyK1ListedPayload()
  let parsed: any = raw
  if (typeof raw === 'string') {
    try {
      parsed = JSON.parse(raw)
    } catch {
      return emptyK1ListedPayload()
    }
  }
  if (parsed?.version !== 2) {
    return migrateLegacyListedSections(parsed, segments)
  }
  const base = emptyK1ListedPayload()
  return {
    ...base,
    ...parsed,
    agingRows: Array.isArray(parsed.agingRows) ? parsed.agingRows : [],
    natureRows: Array.isArray(parsed.natureRows) ? parsed.natureRows : base.natureRows,
    stage1Rows: recomputeStageEclRows(Array.isArray(parsed.stage1Rows) ? parsed.stage1Rows : base.stage1Rows),
    stage2Rows: recomputeStageEclRows(Array.isArray(parsed.stage2Rows) ? parsed.stage2Rows : base.stage2Rows),
    stage3Rows: recomputeStageEclRows(Array.isArray(parsed.stage3Rows) ? parsed.stage3Rows : base.stage3Rows),
    priorStage1Rows: recomputeStageEclRows(
      Array.isArray(parsed.priorStage1Rows) ? parsed.priorStage1Rows : base.priorStage1Rows,
    ),
    priorStage2Rows: recomputeStageEclRows(
      Array.isArray(parsed.priorStage2Rows) ? parsed.priorStage2Rows : base.priorStage2Rows,
    ),
    priorStage3Rows: recomputeStageEclRows(
      Array.isArray(parsed.priorStage3Rows) ? parsed.priorStage3Rows : base.priorStage3Rows,
    ),
    stage2NoneEnd: parsed.stage2NoneEnd === true,
    stage2NonePrior: parsed.stage2NonePrior === true,
    stageMovements: Array.isArray(parsed.stageMovements) ? parsed.stageMovements : [],
    reversalRows: Array.isArray(parsed.reversalRows) ? parsed.reversalRows : [],
    writeoffDetailRows: Array.isArray(parsed.writeoffDetailRows) ? parsed.writeoffDetailRows : [],
    top5Rows: Array.isArray(parsed.top5Rows) ? parsed.top5Rows : [],
    govGrantRows: Array.isArray(parsed.govGrantRows) ? parsed.govGrantRows : [],
    transferRows: Array.isArray(parsed.transferRows) ? parsed.transferRows : [],
    continuedInvolvementRows: migrateContinuedInvolvement(
      parsed.continuedInvolvementRows,
      parsed.continuedInvolvementAssets,
      parsed.continuedInvolvementLiabilities,
    ),
    notes: parsed.notes && typeof parsed.notes === 'object' ? parsed.notes : {},
  }
}

/** 从旧 K1-disc-listed-* 分段 JSON 迁移 */
function migrateLegacyListedSections(legacy: any, segments: AgingSegment[]): K1ListedDisclosurePayloadV2 {
  const payload = emptyK1ListedPayload()
  if (!legacy || typeof legacy !== 'object') return payload

  const sectionMap: Record<string, keyof K1ListedDisclosurePayloadV2> = {
    aging: 'agingRows',
    nature: 'natureRows',
    'bad-debt-method': 'stage1Rows',
    'bad-debt-change': 'stageMovements',
    'top-five': 'top5Rows',
  }

  for (const [secId, field] of Object.entries(sectionMap)) {
    const sec = legacy[secId]
    if (!sec?.rows?.length) continue
    if (field === 'agingRows') {
      payload.agingRows = sec.rows.map((r: any) => ({
        rowId: uid('aging'),
        segmentKey: r.item || '',
        label: r.item || '',
        kind: r.item === '小计' ? 'subtotal' : r.item === '合计' ? 'total' : 'data',
        endAmount: parseNum(r.endBalance),
        priorAmount: parseNum(r.beginBalance),
        editable: true,
      }))
    }
    if (field === 'natureRows') {
      payload.natureRows = sec.rows
        .filter((r: any) => r.item !== '合计')
        .map((r: any) => ({
          rowId: uid('nature'),
          label: r.item || '',
          endGross: parseNum(r.endBalance),
          endProvision: parseNum(r.badDebtProvision),
          endBookValue: parseNum(r.bookValue),
          priorGross: parseNum(r.beginBalance),
          priorProvision: 0,
          priorBookValue: parseNum(r.beginBalance),
          editable: true,
        }))
    }
    if (field === 'top5Rows') {
      payload.top5Rows = sec.rows
        .filter((r: any) => !/小计|合计/.test(String(r.item)))
        .map((r: any) => ({
          rowId: uid('top5'),
          unitName: r.item || '',
          nature: r.remark || '',
          endBalance: parseNum(r.endBalance),
          aging: '',
          proportionPct: parseNum(r.proportion),
          provision: parseNum(r.badDebtProvision),
        }))
    }
  }

  if (!payload.agingRows.length && segments.length) {
    payload.agingRows = buildAgingDisclosureRows(
      segments,
      { end: {}, prior: {} },
      { end: 0, prior: 0 },
    )
  }
  return payload
}

export function serializeK1ListedPayload(payload: K1ListedDisclosurePayloadV2): string {
  return JSON.stringify(payload)
}

export function readAdjudicationTotals(map: Map<string, any>): {
  receivableEnd: number
  receivablePrior: number
  badDebtEnd: number
  badDebtPrior: number
} {
  const get = (k: string) => parseNum(map.get(k)?.remark ?? map.get(k)?.value)
  return {
    receivableEnd: get('K1-1-audited-receivable') || get('K1-1-receivable-end'),
    receivablePrior: get('K1-1-prior-audited-receivable') || get('K1-1-receivable-begin'),
    badDebtEnd: get('K1-1-audited-baddebt') || get('K1-1-baddebt-end'),
    badDebtPrior: get('K1-1-prior-audited-baddebt') || get('K1-1-baddebt-begin'),
  }
}

export function autoFillFromK1Sources(
  payload: K1ListedDisclosurePayloadV2,
  map: Map<string, any>,
  segments: AgingSegment[],
  opts: { force?: boolean } = {},
): K1ListedDisclosurePayloadV2 {
  const force = opts.force ?? false
  const details = loadK1DetailPartials(map)
  const segmentKeys = segments.map((s) => s.key)
  const agingAgg = aggregateAgingFromK1Detail(details, segmentKeys)
  const adj = readAdjudicationTotals(map)

  const agingEmpty = !payload.agingRows.some((r) => r.kind === 'data' && r.endAmount)
  if (force || agingEmpty) {
    payload.agingRows = buildAgingDisclosureRows(segments, agingAgg, {
      end: adj.badDebtEnd,
      prior: adj.badDebtPrior,
    })
  } else if (force) {
    const provRow = payload.agingRows.find((r) => r.kind === 'provision')
    if (provRow) {
      provRow.endAmount = adj.badDebtEnd
      provRow.priorAmount = adj.badDebtPrior
      provRow.autoFilled = true
    }
  }

  const natureMap = aggregateNatureFromK1Detail(details)
  const portfolioLabels = [...new Set([...K1_DEFAULT_NATURE_LABELS, ...natureMap.keys()])]
  const natureEmpty = payload.natureRows.every((r) => !r.endGross && !r.priorGross)
  if (force || natureEmpty) {
    payload.natureRows = buildNatureDisclosureRows(natureMap, portfolioLabels)
  }

  const top5Empty = !payload.top5Rows.length
  if (force || top5Empty) {
    payload.top5Rows = buildTop5FromK1Detail(details)
  }

  const k13Raw = map.get('K1-3-baddebt-rows')?.remark
  if (k13Raw && (force || !payload.stageMovements.length)) {
    payload.stageMovements = readK13StageMovements(k13Raw)
  }

  const k9Raw = map.get('K1-9-writeoff')?.remark
  if (k9Raw) {
    try {
      const k9 = typeof k9Raw === 'string' ? JSON.parse(k9Raw) : k9Raw
      if (force || !payload.reversalRows.length) {
        payload.reversalRows = (k9?.tables?.reversal || []).map(mapK9ReversalRow)
      }
      if (force || !payload.writeoffDetailRows.length) {
        payload.writeoffDetailRows = (k9?.tables?.writeoff || []).map((r: any) => ({
          rowId: r.id || uid('wof'),
          unitName: r.unit || '',
          nature: r.nature || '',
          amount: parseNum(r.amount),
          reason: r.reason || '',
          procedure: r.procedure || '',
          relatedParty: r.relatedParty || '',
        }))
        payload.writeoffSummaryAmount = payload.writeoffDetailRows.reduce((s, r) => s + r.amount, 0)
      }
    } catch {
      /* ignore */
    }
  }

  payload.stage1Rows = recomputeStageEclRows(payload.stage1Rows)
  payload.stage2Rows = recomputeStageEclRows(payload.stage2Rows)
  payload.stage3Rows = recomputeStageEclRows(payload.stage3Rows)
  return payload
}

export function calcAgingTieOut(
  agingRows: K1AgingDisclosureRow[],
  adjReceivable: number,
): { subtotal: number; diff: number; matched: boolean } {
  const subtotal = agingRows.find((r) => r.kind === 'subtotal')?.endAmount ?? 0
  const diff = Math.round((subtotal - adjReceivable) * 100) / 100
  return { subtotal, diff, matched: Math.abs(diff) < 0.01 }
}

export function calcNatureTieOut(
  natureRows: K1NatureDisclosureRow[],
  adjReceivable: number,
): { totalGross: number; diff: number; matched: boolean } {
  const totalGross = summarizeNatureRows(natureRows).endGross
  const diff = Math.round((totalGross - adjReceivable) * 100) / 100
  return { totalGross, diff, matched: Math.abs(diff) < 0.01 }
}

/** T3 勾稽：1 年以内月度细分合计 = 1 年以内（期末/上年年末各校验，仅存在细分行时生效） */
export function calcWithinOneYearTieOut(agingRows: K1AgingDisclosureRow[]): {
  applicable: boolean
  subSumEnd: number
  subSumPrior: number
  within1End: number
  within1Prior: number
  diffEnd: number
  diffPrior: number
  matched: boolean
} {
  const subs = agingRows.filter((r) => r.kind === 'sub')
  const within1 = agingRows.find((r) => r.kind === 'data' && r.segmentKey === 'within1')
  const subSumEnd = subs.reduce((s, r) => s + parseNum(r.endAmount), 0)
  const subSumPrior = subs.reduce((s, r) => s + parseNum(r.priorAmount), 0)
  const within1End = parseNum(within1?.endAmount)
  const within1Prior = parseNum(within1?.priorAmount)
  const diffEnd = Math.round((subSumEnd - within1End) * 100) / 100
  const diffPrior = Math.round((subSumPrior - within1Prior) * 100) / 100
  // 细分行全为 0 视为未启用细分披露，不报警
  const applicable = !!subs.length && !!within1 && (subSumEnd !== 0 || subSumPrior !== 0)
  return {
    applicable,
    subSumEnd,
    subSumPrior,
    within1End,
    within1Prior,
    diffEnd,
    diffPrior,
    matched: !applicable || (Math.abs(diffEnd) < 0.01 && Math.abs(diffPrior) < 0.01),
  }
}

/** 三阶段块坏账合计（取 total 行 provision） */
export function stageBlocksProvisionTotal(
  ...blocks: K1StageEclDisclosureRow[][]
): number {
  return blocks.reduce(
    (s, rows) => s + parseNum(rows.find((r) => r.rowKey === 'total')?.provision),
    0,
  )
}

/** T4prior 勾稽：上年年末三阶段坏账合计 = 账龄表「减：坏账准备」上年年末 */
export function calcPriorProvisionTieOut(
  agingRows: K1AgingDisclosureRow[],
  priorStageTotal: number,
): { agingProvision: number; stageTotal: number; diff: number; matched: boolean } {
  const agingProvision = parseNum(
    agingRows.find((r) => r.kind === 'provision')?.priorAmount,
  )
  const diff = Math.round((agingProvision - priorStageTotal) * 100) / 100
  return { agingProvision, stageTotal: priorStageTotal, diff, matched: Math.abs(diff) < 0.01 }
}

function movementRowTotal(rows: K1StageMovementRow[], key: string): number {
  const r = rows.find((x) => x.key === key)
  if (!r) return 0
  return parseNum(r.stage1) + parseNum(r.stage2) + parseNum(r.stage3)
}

/**
 * T5/T6/T7 勾稽：④ 坏账变动表与 ③ 三阶段快照、⑤ 核销汇总互等。
 * `movements` 行 key 约定见 useK1BadDebt（opening/closing/writeOff…）。
 */
export function calcMovementTieOut(
  movements: K1StageMovementRow[],
  endStageTotal: number,
  priorStageTotal: number,
  writeoffSummary: number,
): {
  closingTotal: number
  openingTotal: number
  writeOffTotal: number
  closingDiff: number
  openingDiff: number
  writeoffDiff: number
  matched: boolean
} {
  const closingTotal = movementRowTotal(movements, 'closing')
  const openingTotal = movementRowTotal(movements, 'opening')
  // 变动表核销行为负数口径（准备减少），⑤ 核销汇总为正数口径 → 取绝对值比对
  const writeOffTotal = movementRowTotal(movements, 'writeoff')
  const closingDiff = Math.round((closingTotal - endStageTotal) * 100) / 100
  const openingDiff = Math.round((openingTotal - priorStageTotal) * 100) / 100
  const writeoffDiff = Math.round((Math.abs(writeOffTotal) - Math.abs(writeoffSummary)) * 100) / 100
  const has = movements.length > 0
  return {
    closingTotal,
    openingTotal,
    writeOffTotal,
    closingDiff,
    openingDiff,
    writeoffDiff,
    matched:
      !has
      || (Math.abs(closingDiff) < 0.01 && Math.abs(openingDiff) < 0.01 && Math.abs(writeoffDiff) < 0.01),
  }
}

/** T12 勾稽：前五名占比合计 ≤ 100%（超 100% 说明分母取错） */
export function calcTop5ProportionCheck(rows: K1Top5DisclosureRow[]): {
  totalPct: number
  exceeded: boolean
} {
  const totalPct = Math.round(rows.reduce((s, r) => s + parseNum(r.proportionPct), 0) * 100) / 100
  return { totalPct, exceeded: totalPct > 100.01 }
}

export function dominantAgingForDetail(d: K1DetailPartial): string {
  return dominantAgingLabel(d.agingAudited)
}

// ─── SOE 国企披露模型 ─────────────────────────────────────────────────────────

export interface K1MethodDisclosureRow {
  rowId: string
  rowKey: 'individual' | 'portfolio' | 'total'
  label: string
  endBalance: number
  endBalancePct: number | null
  endProvision: number
  endEclRate: number | null
  endBookValue: number
  priorBalance: number
  priorBalancePct: number | null
  priorProvision: number
  priorEclRate: number | null
  priorBookValue: number
  editable: boolean
  autoFilled?: boolean
}

export interface K1IndividualDetailRow {
  rowId: string
  debtorName: string
  balance: number
  provision: number
  eclRate: number | null
  reason: string
  editable: boolean
  autoFilled?: boolean
}

export interface K1PortfolioAgingRow {
  rowId: string
  segmentKey: string
  label: string
  endBalance: number
  endBalancePct: number | null
  endProvision: number
  priorBalance: number
  priorBalancePct: number | null
  priorProvision: number
  editable: boolean
  autoFilled?: boolean
}

/**
 * 「其他组合」行（源模板 soe R57-R61 / 附注「采用余额百分比法或其他组合方法…」）。
 * 与 K1PortfolioAgingRow 的区别：此处比例是**人工输入的计提比例**，坏账准备由比例派生；
 * 账龄组合的比例是各账龄段余额占组合总额的**结构占比**（派生值）。
 */
export interface K1OtherPortfolioRow {
  rowId: string
  label: string
  endBalance: number
  endRatePct: number | null
  endProvision: number
  priorBalance: number
  priorRatePct: number | null
  priorProvision: number
  editable: boolean
}

export interface K1SoeDisclosurePayloadV2 {
  version: 2
  agingRows: K1AgingDisclosureRow[]
  methodRows: K1MethodDisclosureRow[]
  individualDetailRows: K1IndividualDetailRow[]
  portfolioAgingRows: K1PortfolioAgingRow[]
  otherPortfolioRows: K1OtherPortfolioRow[]
  stageMovements: K1StageMovementRow[]
  balanceStageMovements: K1StageMovementRow[]
  reversalRows: K1ReversalDisclosureRow[]
  writeoffSummaryAmount: number
  writeoffDetailRows: K1WriteoffDisclosureRow[]
  top5Rows: K1Top5DisclosureRow[]
  govGrantRows: K1GovGrantRow[]
  transferRows: K1TransferRow[]
  continuedInvolvementRows: K1ContinuedInvolvementRow[]
  /** @deprecated 由 continuedInvolvementRows 小计派生，仅为旧 payload 兼容保留 */
  continuedInvolvementAssets: number
  /** @deprecated 同上 */
  continuedInvolvementLiabilities: number
  notes: Record<string, string>
}

/** 其他组合：坏账准备 = 账面余额 × 计提比例（人工覆盖后不再派生） */
export function recomputeOtherPortfolioRows(
  rows: K1OtherPortfolioRow[],
): K1OtherPortfolioRow[] {
  return rows.map((r) => {
    const next = { ...r }
    if (next.endRatePct != null) {
      next.endProvision = Math.round(next.endBalance * (next.endRatePct / 100) * 100) / 100
    }
    if (next.priorRatePct != null) {
      next.priorProvision = Math.round(next.priorBalance * (next.priorRatePct / 100) * 100) / 100
    }
    return next
  })
}

/** 旧结构（复用 K1PortfolioAgingRow，字段名 endBalancePct）→ 新 K1OtherPortfolioRow */
export function migrateOtherPortfolioRows(raw: unknown): K1OtherPortfolioRow[] {
  if (!Array.isArray(raw)) return []
  return raw
    .filter((r): r is Record<string, unknown> => !!r && typeof r === 'object')
    .map((r) => ({
      rowId: String(r.rowId || uid('oport')),
      label: String(r.label ?? ''),
      endBalance: parseNum(r.endBalance),
      endRatePct: r.endRatePct != null ? parseNum(r.endRatePct) : (r.endBalancePct != null ? parseNum(r.endBalancePct) : null),
      endProvision: parseNum(r.endProvision),
      priorBalance: parseNum(r.priorBalance),
      priorRatePct: r.priorRatePct != null ? parseNum(r.priorRatePct) : (r.priorBalancePct != null ? parseNum(r.priorBalancePct) : null),
      priorProvision: parseNum(r.priorProvision),
      editable: true,
    }))
}

/** T10 勾稽：账龄组合坏账 + 其他组合坏账 = 方法表「组合计提」行坏账 */
export function calcPortfolioSplitTieOut(
  portfolioAgingRows: K1PortfolioAgingRow[],
  otherPortfolioRows: K1OtherPortfolioRow[],
  methodRows: K1MethodDisclosureRow[],
): { sumProvision: number; methodProvision: number; diff: number; matched: boolean } {
  const sumProvision =
    portfolioAgingRows.reduce((s, r) => s + parseNum(r.endProvision), 0)
    + otherPortfolioRows.reduce((s, r) => s + parseNum(r.endProvision), 0)
  const methodProvision = parseNum(
    methodRows.find((r) => r.rowKey === 'portfolio')?.endProvision,
  )
  const diff = Math.round((sumProvision - methodProvision) * 100) / 100
  return { sumProvision, methodProvision, diff, matched: Math.abs(diff) < 0.01 }
}

/** T9 勾稽：单项明细合计 = 方法表「单项计提」行 */
export function calcIndividualSplitTieOut(
  individualDetailRows: K1IndividualDetailRow[],
  methodRows: K1MethodDisclosureRow[],
): {
  detailBalance: number
  detailProvision: number
  methodBalance: number
  methodProvision: number
  diffBalance: number
  diffProvision: number
  matched: boolean
} {
  const detailBalance = individualDetailRows.reduce((s, r) => s + parseNum(r.balance), 0)
  const detailProvision = individualDetailRows.reduce((s, r) => s + parseNum(r.provision), 0)
  const m = methodRows.find((r) => r.rowKey === 'individual')
  const methodBalance = parseNum(m?.endBalance)
  const methodProvision = parseNum(m?.endProvision)
  const diffBalance = Math.round((detailBalance - methodBalance) * 100) / 100
  const diffProvision = Math.round((detailProvision - methodProvision) * 100) / 100
  const applicable = individualDetailRows.length > 0
  return {
    detailBalance,
    detailProvision,
    methodBalance,
    methodProvision,
    diffBalance,
    diffProvision,
    matched: !applicable || (Math.abs(diffBalance) < 0.01 && Math.abs(diffProvision) < 0.01),
  }
}

export const K1_SOE_DISC_STORAGE_KEY = 'K1-note-soe-rows'
export const K1_SOE_DISC_NOTE_KEY = 'K1-note-soe-note'

export function buildDefaultMethodRows(): K1MethodDisclosureRow[] {
  return recomputeMethodRows([
    {
      rowId: uid('method'),
      rowKey: 'individual',
      label: '单项计提坏账准备的其他应收款项',
      endBalance: 0, endBalancePct: null, endProvision: 0, endEclRate: null, endBookValue: 0,
      priorBalance: 0, priorBalancePct: null, priorProvision: 0, priorEclRate: null, priorBookValue: 0,
      editable: true,
    },
    {
      rowId: uid('method'),
      rowKey: 'portfolio',
      label: '按信用风险特征组合计提坏账准备的其他应收款项',
      endBalance: 0, endBalancePct: null, endProvision: 0, endEclRate: null, endBookValue: 0,
      priorBalance: 0, priorBalancePct: null, priorProvision: 0, priorEclRate: null, priorBookValue: 0,
      editable: true,
    },
    {
      rowId: uid('method'),
      rowKey: 'total',
      label: '合计',
      endBalance: 0, endBalancePct: 100, endProvision: 0, endEclRate: null, endBookValue: 0,
      priorBalance: 0, priorBalancePct: 100, priorProvision: 0, priorEclRate: null, priorBookValue: 0,
      editable: false,
    },
  ])
}

export function recomputeMethodRows(rows: K1MethodDisclosureRow[]): K1MethodDisclosureRow[] {
  const next = rows.map((r) => ({ ...r }))
  for (const r of next) {
    if (r.rowKey !== 'total') {
      r.endBookValue = Math.round((r.endBalance - r.endProvision) * 100) / 100
      r.priorBookValue = Math.round((r.priorBalance - r.priorProvision) * 100) / 100
      r.endEclRate = r.endBalance > 0 ? Math.round((r.endProvision / r.endBalance) * 10000) / 100 : null
      r.priorEclRate = r.priorBalance > 0 ? Math.round((r.priorProvision / r.priorBalance) * 10000) / 100 : null
    }
  }
  const data = next.filter((r) => r.rowKey !== 'total')
  const total = next.find((r) => r.rowKey === 'total')
  if (total) {
    total.endBalance = data.reduce((s, r) => s + r.endBalance, 0)
    total.endProvision = data.reduce((s, r) => s + r.endProvision, 0)
    total.priorBalance = data.reduce((s, r) => s + r.priorBalance, 0)
    total.priorProvision = data.reduce((s, r) => s + r.priorProvision, 0)
    total.endBookValue = total.endBalance - total.endProvision
    total.priorBookValue = total.priorBalance - total.priorProvision
    total.endEclRate = total.endBalance > 0
      ? Math.round((total.endProvision / total.endBalance) * 10000) / 100 : null
    total.priorEclRate = total.priorBalance > 0
      ? Math.round((total.priorProvision / total.priorBalance) * 10000) / 100 : null
  }
  for (const r of next) {
    if (r.rowKey !== 'total' && total && total.endBalance > 0) {
      r.endBalancePct = Math.round((r.endBalance / total.endBalance) * 10000) / 100
    }
    if (r.rowKey !== 'total' && total && total.priorBalance > 0) {
      r.priorBalancePct = Math.round((r.priorBalance / total.priorBalance) * 10000) / 100
    }
  }
  return next
}

export function buildPortfolioAgingRows(
  segments: AgingSegment[],
  agg: { end: Record<string, number>; prior: Record<string, number> },
  provision: { end: number; prior: number },
): K1PortfolioAgingRow[] {
  const dataRows: K1PortfolioAgingRow[] = segments.map((seg) => ({
    rowId: uid('port'),
    segmentKey: seg.key,
    label: noteAgingLabel(seg.key, seg.label),
    endBalance: parseNum(agg.end[seg.key]),
    endBalancePct: null,
    endProvision: 0,
    priorBalance: parseNum(agg.prior[seg.key]),
    priorBalancePct: null,
    priorProvision: 0,
    editable: true,
    autoFilled: true,
  }))
  const endTotal = dataRows.reduce((s, r) => s + r.endBalance, 0)
  const priorTotal = dataRows.reduce((s, r) => s + r.priorBalance, 0)
  for (const r of dataRows) {
    r.endBalancePct = endTotal > 0 ? Math.round((r.endBalance / endTotal) * 10000) / 100 : null
    r.priorBalancePct = priorTotal > 0 ? Math.round((r.priorBalance / priorTotal) * 10000) / 100 : null
    // 坏账准备按组合账龄余额占比分摊（非全表总额分摊）
    if (endTotal > 0 && provision.end) {
      r.endProvision = Math.round(provision.end * (r.endBalance / endTotal) * 100) / 100
    }
    if (priorTotal > 0 && provision.prior) {
      r.priorProvision = Math.round(provision.prior * (r.priorBalance / priorTotal) * 100) / 100
    }
  }
  return dataRows
}

/** K1-3 单项子行名称集合 + 明细拆分 */
export interface K1ProvisionMethodSplit {
  individualNames: Set<string>
  individualDetails: K1DetailPartial[]
  portfolioDetails: K1DetailPartial[]
}

export function splitK1DetailByProvisionMethod(
  details: K1DetailPartial[],
  k13Raw: unknown,
): K1ProvisionMethodSplit {
  const payload = parseK13Payload(k13Raw)
  const individualSubs = payload.mainRows.filter((r) => r.category === 'individual' && r.isSubRow)
  const individualNames = new Set(
    individualSubs.map((s) => String(s.label || '').trim()).filter(Boolean),
  )
  const individualDetails = details.filter((d) => individualNames.has(d.counterparty.trim()))
  const portfolioDetails = details.filter((d) => !individualNames.has(d.counterparty.trim()))
  return { individualNames, individualDetails, portfolioDetails }
}

const BALANCE_TRANSFER_KEY: Record<string, string> = {
  '1-2': 's1-s2',
  '1-3': 's1-s3',
  '2-1': 's2-s1',
  '2-3': 's2-s3',
  '3-1': 's3-s1',
  '3-2': 's3-s2',
}

/** 国企附注：账面余额三阶段变动行定义（对齐 Excel 77~87） */
export function defaultBalanceStageMovements(): K1StageMovementRow[] {
  return [
    { key: 'opening', label: '期初余额', stage1: 0, stage2: 0, stage3: 0, editable: false },
    { key: 's1-s2', label: '—转入第二阶段', stage1: 0, stage2: 0, stage3: 0, editable: false },
    { key: 's1-s3', label: '—转入第三阶段', stage1: 0, stage2: 0, stage3: 0, editable: false },
    { key: 's2-s1', label: '—转回第一阶段', stage1: 0, stage2: 0, stage3: 0, editable: false },
    { key: 's2-s3', label: '—转入第三阶段', stage1: 0, stage2: 0, stage3: 0, editable: false },
    { key: 's3-s1', label: '—转回第一阶段', stage1: 0, stage2: 0, stage3: 0, editable: false },
    { key: 's3-s2', label: '—转回第二阶段', stage1: 0, stage2: 0, stage3: 0, editable: false },
    { key: 'addition', label: '本期新增', stage1: 0, stage2: 0, stage3: 0, editable: true },
    { key: 'collection', label: '本期收回或核销', stage1: 0, stage2: 0, stage3: 0, editable: true },
    { key: 'other', label: '其他变动', stage1: 0, stage2: 0, stage3: 0, editable: true },
    { key: 'closing', label: '期末余额', stage1: 0, stage2: 0, stage3: 0, editable: false },
  ]
}

function stageAmtKey(stage: 1 | 2 | 3): 'stage1' | 'stage2' | 'stage3' {
  return stage === 1 ? 'stage1' : stage === 2 ? 'stage2' : 'stage3'
}

function applyBalanceTransfer(
  movements: K1StageMovementRow[],
  from: 1 | 2 | 3,
  to: 1 | 2 | 3,
  amount: number,
): void {
  if (amount <= 0.005 || from === to) return
  const key = BALANCE_TRANSFER_KEY[`${from}-${to}`]
  const row = movements.find((r) => r.key === key)
  if (!row) return
  row[stageAmtKey(from)] = Math.round((row[stageAmtKey(from)] - amount) * 100) / 100
  row[stageAmtKey(to)] = Math.round((row[stageAmtKey(to)] + amount) * 100) / 100
}

/**
 * K1-7 + K1-2 → 账面余额三阶段变动表
 * - 期初：K1-2 期初余额按 K1-7 priorStage 归集
 * - 阶段迁移：priorStage ≠ stage 时按期初余额结转，净增减计入本期新增/收回
 */
export function buildBalanceStageMovementsFromK17(
  stageRows: K1StageRow[],
  details: K1DetailPartial[],
): K1StageMovementRow[] {
  const byName = new Map(details.map((d) => [d.counterparty.trim(), d]))
  const movements = defaultBalanceStageMovements().map((r) => ({ ...r }))
  const opening = movements.find((r) => r.key === 'opening')!
  const addition = movements.find((r) => r.key === 'addition')!
  const collection = movements.find((r) => r.key === 'collection')!

  for (const sr of stageRows) {
    const name = sr.counterparty.trim()
    if (!name) continue
    const detail = byName.get(name)
    const begin = parseNum(detail?.beginBalance)
    const end = parseNum(sr.endBalance)
    const prior = sr.priorStage
    const curr = sr.stage

    opening[stageAmtKey(prior)] = Math.round((opening[stageAmtKey(prior)] + begin) * 100) / 100

    if (prior === curr) {
      const delta = Math.round((end - begin) * 100) / 100
      if (delta > 0.005) {
        addition[stageAmtKey(curr)] = Math.round((addition[stageAmtKey(curr)] + delta) * 100) / 100
      } else if (delta < -0.005) {
        collection[stageAmtKey(curr)] = Math.round((collection[stageAmtKey(curr)] + delta) * 100) / 100
      }
    } else {
      applyBalanceTransfer(movements, prior, curr, begin)
      const delta = Math.round((end - begin) * 100) / 100
      if (delta > 0.005) {
        addition[stageAmtKey(curr)] = Math.round((addition[stageAmtKey(curr)] + delta) * 100) / 100
      } else if (delta < -0.005) {
        collection[stageAmtKey(curr)] = Math.round((collection[stageAmtKey(curr)] + delta) * 100) / 100
      }
    }
  }

  return recalcStageClosing(movements)
}

export function calcBalanceStageTieOut(
  balanceMovements: K1StageMovementRow[],
  adjReceivable: number,
): { closingTotal: number; diff: number; matched: boolean } {
  const closing = balanceMovements.find((r) => r.key === 'closing')
  const closingTotal = closing ? closing.stage1 + closing.stage2 + closing.stage3 : 0
  const diff = Math.round((closingTotal - adjReceivable) * 100) / 100
  return { closingTotal, diff, matched: Math.abs(diff) < 0.01 }
}

export function buildIndividualDetailFromK13(
  raw: unknown,
  details: K1DetailPartial[] = [],
): K1IndividualDetailRow[] {
  const payload = parseK13Payload(raw)
  const subs = payload.mainRows.filter((r) => r.category === 'individual' && r.isSubRow)
  if (!subs.length) return []
  return subs.map((r) => {
    const detail = details.find((d) => d.counterparty === r.label)
    const balance = detail?.endBalance ?? 0
    const provision = r.currentAudited
    return {
      rowId: r.id || uid('ind'),
      debtorName: r.label,
      balance,
      provision,
      eclRate: balance > 0 ? Math.round((provision / balance) * 10000) / 100 : null,
      reason: r.reason || '',
      editable: true,
      autoFilled: true,
    }
  })
}

export function buildMethodRowsFromK13(
  raw: unknown,
  details: K1DetailPartial[] = [],
  adj?: { receivableEnd: number; receivablePrior: number; badDebtEnd: number; badDebtPrior: number },
): K1MethodDisclosureRow[] {
  const payload = parseK13Payload(raw)
  const individualSubs = payload.mainRows.filter((r) => r.category === 'individual' && r.isSubRow)
  const portfolio = payload.mainRows.find((r) => r.category === 'portfolio' && r.isFixed)
  const sumField = (rows: typeof individualSubs, pick: (r: typeof individualSubs[0]) => number) =>
    rows.reduce((s, r) => s + pick(r), 0)
  const indEndProv = sumField(individualSubs, (r) => r.currentAudited)
  const indPriorProv = sumField(individualSubs, (r) => r.priorAudited)
  let indEndBal = 0
  let indPriorBal = 0
  for (const sub of individualSubs) {
    const d = details.find((x) => x.counterparty === sub.label)
    if (d) {
      indEndBal += d.endBalance
      indPriorBal += d.beginBalance
    }
  }
  const portEndProv = portfolio?.currentAudited ?? Math.max(0, (adj?.badDebtEnd ?? 0) - indEndProv)
  const portPriorProv = portfolio?.priorAudited ?? Math.max(0, (adj?.badDebtPrior ?? 0) - indPriorProv)
  const portEndBal = Math.max(0, (adj?.receivableEnd ?? 0) - indEndBal)
  const portPriorBal = Math.max(0, (adj?.receivablePrior ?? 0) - indPriorBal)
  return recomputeMethodRows([
    {
      rowId: uid('method'), rowKey: 'individual',
      label: '单项计提坏账准备的其他应收款项',
      endBalance: indEndBal, endBalancePct: null, endProvision: indEndProv, endEclRate: null, endBookValue: 0,
      priorBalance: indPriorBal, priorBalancePct: null, priorProvision: indPriorProv, priorEclRate: null, priorBookValue: 0,
      editable: true, autoFilled: true,
    },
    {
      rowId: uid('method'), rowKey: 'portfolio',
      label: '按信用风险特征组合计提坏账准备的其他应收款项',
      endBalance: portEndBal, endBalancePct: null, endProvision: portEndProv, endEclRate: null, endBookValue: 0,
      priorBalance: portPriorBal, priorBalancePct: null, priorProvision: portPriorProv, priorEclRate: null, priorBookValue: 0,
      editable: true, autoFilled: true,
    },
    {
      rowId: uid('method'), rowKey: 'total', label: '合计',
      endBalance: 0, endBalancePct: 100, endProvision: 0, endEclRate: null, endBookValue: 0,
      priorBalance: 0, priorBalancePct: 100, priorProvision: 0, priorEclRate: null, priorBookValue: 0,
      editable: false,
    },
  ])
}

export function buildGovGrantFromK1Detail(details: K1DetailPartial[]): K1GovGrantRow[] {
  return details
    .filter((d) => /政府补助|财政补贴|专项补助/i.test(d.nature || ''))
    .map((d) => ({
      rowId: uid('gov'),
      unitName: d.counterparty,
      projectName: d.nature || '',
      endBalance: d.endBalance,
      aging: dominantAgingLabel(d.agingAudited),
      expectedCollection: d.remark || '',
    }))
}

export function emptyK1SoePayload(): K1SoeDisclosurePayloadV2 {
  return {
    version: 2,
    agingRows: [],
    methodRows: buildDefaultMethodRows(),
    individualDetailRows: [],
    portfolioAgingRows: [],
    otherPortfolioRows: [],
    stageMovements: [],
    balanceStageMovements: [],
    reversalRows: [],
    writeoffSummaryAmount: 0,
    writeoffDetailRows: [],
    top5Rows: [],
    govGrantRows: [],
    transferRows: [],
    continuedInvolvementRows: [],
    continuedInvolvementAssets: 0,
    continuedInvolvementLiabilities: 0,
    notes: {},
  }
}

function migrateLegacySoeSections(map: Map<string, any>, segments: AgingSegment[]): K1SoeDisclosurePayloadV2 {
  const payload = emptyK1SoePayload()
  const legacyIds = ['aging', 'nature', 'bad-debt-change', 'important', 'other'] as const
  for (const secId of legacyIds) {
    const raw = map.get(`K1-disc-soe-${secId}`)?.value ?? map.get(`K1-disc-soe-${secId}`)?.remark
    if (!raw) continue
    try {
      const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw
      if (!parsed?.rows?.length) continue
      if (secId === 'aging') {
        payload.agingRows = parsed.rows.map((r: any) => ({
          rowId: uid('aging'),
          segmentKey: r.item || '',
          label: r.item || '',
          kind: /小计/.test(r.item) ? 'subtotal' : /合计/.test(r.item) ? 'total' : /坏账/.test(r.item) ? 'provision' : 'data',
          endAmount: parseNum(r.endBalance),
          priorAmount: parseNum(r.beginBalance),
          editable: true,
        }))
      }
      if (secId === 'important') {
        payload.top5Rows = parsed.rows
          .filter((r: any) => !/小计|合计/.test(String(r.item)))
          .slice(0, 5)
          .map((r: any) => ({
            rowId: uid('top5'),
            unitName: r.item || '',
            nature: r.remark || '',
            endBalance: parseNum(r.endBalance),
            aging: '',
            proportionPct: parseNum(r.proportion),
            provision: parseNum(r.badDebtProvision),
          }))
      }
      if (secId === 'other' && parsed.textContent) {
        payload.notes.other = parsed.textContent
      }
    } catch { /* ignore */ }
  }
  if (!payload.agingRows.length && segments.length) {
    payload.agingRows = buildAgingDisclosureRows(
      segments,
      { end: {}, prior: {} },
      { end: 0, prior: 0 },
      { withinOneYearBreakdown: false },
    )
  }
  return payload
}

export function parseK1SoePayload(
  raw: unknown,
  segments: AgingSegment[],
  map?: Map<string, any>,
): K1SoeDisclosurePayloadV2 {
  if (!raw && map) return migrateLegacySoeSections(map, segments)
  if (!raw) return emptyK1SoePayload()
  let parsed: any = raw
  if (typeof raw === 'string') {
    try { parsed = JSON.parse(raw) } catch { return emptyK1SoePayload() }
  }
  if (parsed?.version !== 2) {
    return map ? migrateLegacySoeSections(map, segments) : emptyK1SoePayload()
  }
  const base = emptyK1SoePayload()
  return {
    ...base,
    ...parsed,
    agingRows: Array.isArray(parsed.agingRows) ? parsed.agingRows : [],
    methodRows: recomputeMethodRows(Array.isArray(parsed.methodRows) ? parsed.methodRows : base.methodRows),
    individualDetailRows: Array.isArray(parsed.individualDetailRows) ? parsed.individualDetailRows : [],
    portfolioAgingRows: Array.isArray(parsed.portfolioAgingRows) ? parsed.portfolioAgingRows : [],
    otherPortfolioRows: recomputeOtherPortfolioRows(migrateOtherPortfolioRows(parsed.otherPortfolioRows)),
    stageMovements: Array.isArray(parsed.stageMovements) ? parsed.stageMovements : [],
    balanceStageMovements: Array.isArray(parsed.balanceStageMovements) ? parsed.balanceStageMovements : [],
    reversalRows: Array.isArray(parsed.reversalRows) ? parsed.reversalRows : [],
    writeoffDetailRows: Array.isArray(parsed.writeoffDetailRows) ? parsed.writeoffDetailRows : [],
    top5Rows: Array.isArray(parsed.top5Rows) ? parsed.top5Rows : [],
    govGrantRows: Array.isArray(parsed.govGrantRows) ? parsed.govGrantRows : [],
    transferRows: Array.isArray(parsed.transferRows) ? parsed.transferRows : [],
    continuedInvolvementRows: migrateContinuedInvolvement(
      parsed.continuedInvolvementRows,
      parsed.continuedInvolvementAssets,
      parsed.continuedInvolvementLiabilities,
    ),
    notes: parsed.notes && typeof parsed.notes === 'object' ? parsed.notes : {},
  }
}

export function serializeK1SoePayload(payload: K1SoeDisclosurePayloadV2): string {
  return JSON.stringify(payload)
}

export function autoFillSoeFromK1Sources(
  payload: K1SoeDisclosurePayloadV2,
  map: Map<string, any>,
  segments: AgingSegment[],
  opts: { force?: boolean } = {},
): K1SoeDisclosurePayloadV2 {
  const force = opts.force ?? false
  const details = loadK1DetailPartials(map)
  const segmentKeys = segments.map((s) => s.key)
  const agingAgg = aggregateAgingFromK1Detail(details, segmentKeys)
  const adj = readAdjudicationTotals(map)
  const k13Raw = map.get('K1-3-baddebt-rows')?.remark

  const agingEmpty = !payload.agingRows.some((r) => r.kind === 'data' && r.endAmount)
  if (force || agingEmpty) {
    // 国企源模板账龄表无「1 年以内」月度细分（仅上市版有）
    payload.agingRows = buildAgingDisclosureRows(
      segments,
      agingAgg,
      { end: adj.badDebtEnd, prior: adj.badDebtPrior },
      { withinOneYearBreakdown: false },
    )
  }

  if (k13Raw && (force || !payload.methodRows.some((r) => r.autoFilled && r.endBalance))) {
    payload.methodRows = buildMethodRowsFromK13(k13Raw, details, adj)
  }

  if (k13Raw && (force || !payload.individualDetailRows.length)) {
    payload.individualDetailRows = buildIndividualDetailFromK13(k13Raw, details)
  }

  const portEmpty = !payload.portfolioAgingRows.some((r) => r.endBalance)
  if (force || portEmpty) {
    const split = splitK1DetailByProvisionMethod(details, k13Raw || '')
    const portfolioAgg = aggregateAgingFromK1Detail(split.portfolioDetails, segmentKeys)
    const methodRows = payload.methodRows.some((r) => r.autoFilled)
      ? payload.methodRows
      : (k13Raw ? buildMethodRowsFromK13(k13Raw, details, adj) : payload.methodRows)
    const portfolioMethod = methodRows.find((r) => r.rowKey === 'portfolio')
    payload.portfolioAgingRows = buildPortfolioAgingRows(segments, portfolioAgg, {
      end: portfolioMethod?.endProvision ?? 0,
      prior: portfolioMethod?.priorProvision ?? 0,
    })
  }

  if (k13Raw && (force || !payload.stageMovements.length)) {
    payload.stageMovements = readK13StageMovements(k13Raw)
  }

  const k17Rows = parseK1StageRowsFromMap(map)
  if (k17Rows.length && (force || !payload.balanceStageMovements.length)) {
    payload.balanceStageMovements = buildBalanceStageMovementsFromK17(k17Rows, details)
  }

  if (force || !payload.top5Rows.length) {
    payload.top5Rows = buildTop5FromK1Detail(details, 5)
  }

  if (force || !payload.govGrantRows.length) {
    payload.govGrantRows = buildGovGrantFromK1Detail(details)
  }

  const k9Raw = map.get('K1-9-writeoff')?.remark
  if (k9Raw) {
    try {
      const k9 = typeof k9Raw === 'string' ? JSON.parse(k9Raw) : k9Raw
      if (force || !payload.reversalRows.length) {
        payload.reversalRows = (k9?.tables?.reversal || []).map(mapK9ReversalRow)
      }
      if (force || !payload.writeoffDetailRows.length) {
        payload.writeoffDetailRows = (k9?.tables?.writeoff || []).map((r: any) => ({
          rowId: r.id || uid('wof'),
          unitName: r.unit || '',
          nature: r.nature || '',
          amount: parseNum(r.amount),
          reason: r.reason || '',
          procedure: r.procedure || '',
          relatedParty: r.relatedParty || '',
        }))
        payload.writeoffSummaryAmount = payload.writeoffDetailRows.reduce((s, r) => s + r.amount, 0)
      }
    } catch { /* ignore */ }
  }

  return payload
}

export function calcMethodTieOut(
  methodRows: K1MethodDisclosureRow[],
  adjReceivable: number,
): { totalBalance: number; diff: number; matched: boolean } {
  const total = methodRows.find((r) => r.rowKey === 'total')?.endBalance ?? 0
  const diff = Math.round((total - adjReceivable) * 100) / 100
  return { totalBalance: total, diff, matched: Math.abs(diff) < 0.01 }
}
