/**
 * G12-6 凭证检查 ↔ G12-3 调整 / G12A 程序 / G12-2 套期明细 / G12-4 FV / G12-5 净敞口
 */
import { G12_VOUCHER_CHECK_DEFS, formatG12SamplingMethodLabel } from './g12VoucherConstants'
import { G12_ACCOUNT_CODE } from './g12Constants'
import { parseNum } from './useG12FormulaEngine'
import type { G12VoucherRow } from './useG12VoucherCheck'
import type { ChecklistResponse } from './useF1FormData'

export const G12_AJE_KEY = 'G12-aje-rows'
export const G12_HEDGE_DETAIL_KEY = 'G12-hedge-detail-rows'
export const G12_FV_KEY = 'G12-fv-test-rows'
export const G12_NET_EXPOSURE_KEY = 'G12-net-exposure-rows'
export const G12A_PROCEDURE_SHEET = '净敞口套期收益审计程序表G12A'
/** G12A seq10：检查净敞口套期收益相关凭证 */
export const G12A_VOUCHER_PROGRAM_NOS = [10] as const
export const G12A_VOUCHER_MARK_KEY = 'G12A-voucher-complete'

const AMT_THRESHOLD = 0.005

export function describeG12FailedChecks(row: G12VoucherRow): string {
  const failed = G12_VOUCHER_CHECK_DEFS
    .filter((d) => row[d.key] === false)
    .map((d) => d.label)
  return failed.join('、') || '异常'
}

/** 金额类异常：异常且套期会计/公允价值核对未通过，且发生额>0 */
export function isG12QuantitativeVoucherAbnormal(row: G12VoucherRow): boolean {
  if (!row.isAbnormal) return false
  const amt = Math.max(Math.abs(parseNum(row.debitAmount)), Math.abs(parseNum(row.creditAmount)))
  if (amt <= AMT_THRESHOLD) return false
  return row.check5HedgeAccounting === false || row.check6FVValuation === false || row.check3Accounting === false
}

export interface G12VoucherPushItem {
  summary: string
  amount: number
  indexRef: string
  remark: string
  voucherNo: string
  hedgeRelationId: string
}

export function buildG12VoucherPushItems(rows: G12VoucherRow[]): G12VoucherPushItem[] {
  const items: G12VoucherPushItem[] = []
  for (const row of rows) {
    if (!isG12QuantitativeVoucherAbnormal(row)) continue
    const amount = Math.max(Math.abs(parseNum(row.debitAmount)), Math.abs(parseNum(row.creditAmount)))
    if (amount <= AMT_THRESHOLD) continue
    const voucherNo = row.voucherNo?.trim() || row.rowId
    items.push({
      summary: `G12-6 凭证异常：${voucherNo} ${row.businessContent || ''}`.trim(),
      amount,
      indexRef: 'G12-6',
      remark: [
        `来自 G12-6 凭证检查；未通过：${describeG12FailedChecks(row)}`,
        row.abnormalDesc ? `说明：${row.abnormalDesc}` : '',
      ].filter(Boolean).join('；'),
      voucherNo,
      hedgeRelationId: row.hedgeRelationId || '',
    })
  }
  return items
}

function genAdjId(suffix: string): string {
  return `g12vc-adj-${suffix}`
}

export function pushG12VoucherAbnormalToAdjustment(
  allResponses: Map<string, ChecklistResponse>,
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void,
  rows: G12VoucherRow[],
): { pushed: number; skipped: number } {
  const targets = buildG12VoucherPushItems(rows)
  if (!targets.length) return { pushed: 0, skipped: 0 }

  let existing: any[] = []
  try {
    const json = allResponses.get(G12_AJE_KEY)?.remark
    existing = json ? JSON.parse(json) : []
    if (!Array.isArray(existing)) existing = []
  } catch {
    existing = []
  }

  let pushed = 0
  let skipped = 0
  for (const item of targets) {
    const dup = existing.some((r) =>
      String(r.summary || '').includes(item.voucherNo)
      && String(r.remark || '').includes('G12-6'),
    )
    if (dup) { skipped += 1; continue }
    existing.push({
      rowId: genAdjId(item.voucherNo),
      seq: existing.length + 1,
      entryType: 'AJE',
      date: '',
      summary: item.summary,
      accountCode: G12_ACCOUNT_CODE,
      accountName: '净敞口套期收益',
      debitAmount: item.amount,
      creditAmount: 0,
      preparedBy: '',
      remark: item.remark,
      indexRef: item.indexRef,
    })
    pushed += 1
  }
  if (pushed) {
    debouncedSave(G12_AJE_KEY, { remark: JSON.stringify(existing) })
  }
  return { pushed, skipped }
}

/** 从 G12-2 套期明细汇总净敞口套期损益，作为本期发生额提示 */
export function calcG12PopulationHint(allResponses: Map<string, ChecklistResponse>): number {
  try {
    const json = allResponses.get(G12_HEDGE_DETAIL_KEY)?.remark
    if (!json) return 0
    const rows = JSON.parse(json)
    if (!Array.isArray(rows)) return 0
    return rows.reduce((s: number, r: any) => s + Math.abs(parseNum(r.profitLossAmount)), 0)
  } catch {
    return 0
  }
}

export function buildG12VoucherProcedureSummary(input: {
  rowCount: number
  abnormal: number
  quantitative: number
  inspectionRatioPct: number | null
}): string {
  const ratio = input.inspectionRatioPct == null ? '—' : `${input.inspectionRatioPct.toFixed(1)}%`
  return [
    `G12-6 凭证检查 ${input.rowCount} 行`,
    `异常 ${input.abnormal}`,
    `金额类异常 ${input.quantitative}`,
    `检查比例 ${ratio}`,
  ].join('；')
}

export async function markG12AProcedureSteps(opts: {
  projectId: string
  year?: number
  programNos: readonly number[]
  status?: string
  linkedWorkpapers?: string
  executionSummary?: string
}): Promise<number> {
  if (!opts.projectId || !opts.programNos.length) return 0
  const { api } = await import('@/services/apiProxy')
  const year = opts.year || new Date().getFullYear()
  const scope = `procedure_table:${G12A_PROCEDURE_SHEET}`
  const status = opts.status || 'completed'
  let n = 0
  for (const programNo of opts.programNos) {
    const fields: Array<{ field: string; value: unknown }> = [
      { field: 'status', value: status },
    ]
    if (opts.linkedWorkpapers) fields.push({ field: 'linked_workpapers', value: opts.linkedWorkpapers })
    if (opts.executionSummary) fields.push({ field: 'execution_summary', value: opts.executionSummary })
    for (const f of fields) {
      try {
        await api.post('/api/workpapers/field-overrides', {
          project_id: opts.projectId,
          year,
          scope,
          item_key: String(programNo),
          field: f.field,
          value: f.value,
        }, { _silent: true } as any)
        if (f.field === 'status') n += 1
      } catch { /* optional */ }
    }
  }
  return n
}

// ─── 抽凭方法学 → 抽样过程 ───────────────────────────────────────────────────

export interface G12SamplingMethodologyLike {
  samplingMethod?: string
  samplingInterval?: string | null
  sampleSize?: number
  suggestedSampleSize?: number | null
  tolerableMisstatement?: number | null
  expectedMisstatement?: number | null
  confidenceLevel?: number | null
  accountCodes?: string[]
  randomSeed?: string | null
}

/** 将抽凭引擎方法学快照格式化为「抽样过程」文本 */
export function formatG12SamplingProcessFromMethodology(m: G12SamplingMethodologyLike): string {
  const method = formatG12SamplingMethodLabel(m.samplingMethod || '')
  const parts = [
    `抽凭引擎回填：方法=${method || m.samplingMethod || '—'}`,
    m.accountCodes?.length ? `科目=${m.accountCodes.join(',')}` : '',
    m.sampleSize != null ? `样本=${m.sampleSize}笔` : '',
    m.suggestedSampleSize != null ? `建议样本量=${m.suggestedSampleSize}` : '',
    m.samplingInterval ? `MUS间隔=${m.samplingInterval}` : '',
    m.tolerableMisstatement != null ? `可容忍错报=${m.tolerableMisstatement}` : '',
    m.expectedMisstatement != null ? `预计错报=${m.expectedMisstatement}` : '',
    m.confidenceLevel != null ? `置信度=${m.confidenceLevel}` : '',
    m.randomSeed ? `seed=${m.randomSeed}` : '',
    `时间=${new Date().toISOString().slice(0, 19)}`,
  ].filter(Boolean)
  return parts.join('；')
}

// ─── G12-5 净敞口检查行级勾稽（按套期关系编号）─────────────────────────────

export interface G12NetExposureLinkRow {
  hedgeRelationId?: string
  item?: string
  netPosition?: string
  hedgingInstrument?: string
  supportingEvidence?: string
  position1Desc?: string
  position2Desc?: string
}

export type G12NetExposureLinkStatus = 'ok' | 'incomplete' | 'missing' | 'no_id'

export interface G12NetExposureLinkHint {
  voucherRowId: string
  hedgeRelationId: string
  status: G12NetExposureLinkStatus
  message: string
  /** 建议写入核对⑤（套期会计）：仅 status=ok 时为 true */
  suggestCheck5: boolean | null
}

function parseNetExposureRows(allResponses: Map<string, ChecklistResponse>): G12NetExposureLinkRow[] {
  try {
    const json = allResponses.get(G12_NET_EXPOSURE_KEY)?.remark
    if (!json) return []
    const rows = JSON.parse(json)
    return Array.isArray(rows) ? rows : []
  } catch {
    return []
  }
}

function isNetExposureRowComplete(r: G12NetExposureLinkRow): boolean {
  return !!(
    String(r.item || '').trim()
    && String(r.position1Desc || '').trim()
    && String(r.position2Desc || '').trim()
    && String(r.netPosition || '').trim()
  )
}

function resolveNetExposureRelationId(r: G12NetExposureLinkRow): string {
  return String(r.hedgeRelationId || '').trim()
}

/** 按套期关系编号匹配 G12-5 净敞口检查行 */
export function buildG12NetExposureLinkHints(
  voucherRows: G12VoucherRow[],
  allResponses: Map<string, ChecklistResponse>,
): G12NetExposureLinkHint[] {
  const neRows = parseNetExposureRows(allResponses)
  const byId = new Map<string, G12NetExposureLinkRow>()
  for (const r of neRows) {
    const id = resolveNetExposureRelationId(r)
    if (id && !byId.has(id)) byId.set(id, r)
  }

  const hints: G12NetExposureLinkHint[] = []
  for (const v of voucherRows) {
    const id = String(v.hedgeRelationId || '').trim()
    if (!id) {
      hints.push({
        voucherRowId: v.rowId,
        hedgeRelationId: '',
        status: 'no_id',
        message: '未填套期关系编号，无法勾稽 G12-5',
        suggestCheck5: null,
      })
      continue
    }
    const hit = byId.get(id)
    if (!hit) {
      hints.push({
        voucherRowId: v.rowId,
        hedgeRelationId: id,
        status: 'missing',
        message: `G12-5 无编号 ${id} 的净敞口检查行`,
        suggestCheck5: null,
      })
      continue
    }
    if (!isNetExposureRowComplete(hit)) {
      hints.push({
        voucherRowId: v.rowId,
        hedgeRelationId: id,
        status: 'incomplete',
        message: `G12-5「${hit.item || id}」头寸/净头寸未填完整`,
        suggestCheck5: null,
      })
      continue
    }
    hints.push({
      voucherRowId: v.rowId,
      hedgeRelationId: id,
      status: 'ok',
      message: `已勾稽 G12-5：${hit.item || id}；净头寸=${hit.netPosition}`,
      suggestCheck5: true,
    })
  }
  return hints
}

export function summarizeG12NetExposureLinks(hints: G12NetExposureLinkHint[]): {
  ok: number
  incomplete: number
  missing: number
  noId: number
} {
  return {
    ok: hints.filter((h) => h.status === 'ok').length,
    incomplete: hints.filter((h) => h.status === 'incomplete').length,
    missing: hints.filter((h) => h.status === 'missing').length,
    noId: hints.filter((h) => h.status === 'no_id').length,
  }
}

/**
 * 将 G12-5 勾稽结果回写到凭证行：
 * - status=ok 且核对⑤为空 → 置通过，并在备注追加勾稽说明
 */
export function applyG12NetExposureLinkHints(
  rows: G12VoucherRow[],
  hints: G12NetExposureLinkHint[],
): { updated: number; rows: G12VoucherRow[] } {
  const byId = new Map(hints.map((h) => [h.voucherRowId, h]))
  let updated = 0
  const next = rows.map((r) => {
    const h = byId.get(r.rowId)
    if (!h || h.status !== 'ok' || h.suggestCheck5 !== true) return r
    if (r.check5HedgeAccounting !== null) return r
    updated += 1
    const note = h.message
    const remark = r.remark?.includes('G12-5') ? r.remark : [r.remark, note].filter(Boolean).join('；')
    return { ...r, check5HedgeAccounting: true as const, remark }
  })
  return { updated, rows: next }
}

// ─── G12-4 FV 估值依据 → 核对⑥ ───────────────────────────────────────────────

export interface G12FvCiteRow {
  hedgeRelationId?: string
  instrumentValuationMethod?: string
  instrumentValuationSource?: string
  instrumentFVLevel?: string
  instrumentName?: string
  itemTestMethod?: string
  itemEffectivenessConclusion?: string
}

function parseFvRows(allResponses: Map<string, ChecklistResponse>): G12FvCiteRow[] {
  try {
    const json = allResponses.get(G12_FV_KEY)?.remark
    if (!json) return []
    const rows = JSON.parse(json)
    return Array.isArray(rows) ? rows : []
  } catch {
    return []
  }
}

/** 格式化 G12-4 估值依据文案 */
export function formatG12FvValuationBasis(fv: G12FvCiteRow): string {
  const parts = [
    fv.instrumentName ? `工具=${fv.instrumentName}` : '',
    fv.instrumentValuationMethod ? `方法=${fv.instrumentValuationMethod}` : '',
    fv.instrumentValuationSource ? `来源=${fv.instrumentValuationSource}` : '',
    fv.instrumentFVLevel ? `层次=${fv.instrumentFVLevel}` : '',
    fv.itemTestMethod ? `有效性测试=${fv.itemTestMethod}` : '',
    fv.itemEffectivenessConclusion && fv.itemEffectivenessConclusion !== 'pending'
      ? `有效性结论=${fv.itemEffectivenessConclusion}`
      : '',
  ].filter(Boolean)
  if (!parts.length) return ''
  return `【G12-4估值】${parts.join('；')}`
}

export function findG12FvByHedgeRelationId(
  allResponses: Map<string, ChecklistResponse>,
  hedgeRelationId: string,
): G12FvCiteRow | null {
  const id = String(hedgeRelationId || '').trim()
  if (!id) return null
  return parseFvRows(allResponses).find((r) => String(r.hedgeRelationId || '').trim() === id) ?? null
}

/**
 * 一键引用 G12-4 估值依据至凭证行：
 * - 写入 supportingDocDesc（若已有非 G12-4 内容则追加）
 * - 核对⑥为空时置为通过
 */
export function citeG12FvValuationToVoucher(
  row: G12VoucherRow,
  allResponses: Map<string, ChecklistResponse>,
): { ok: boolean; message: string; patch?: Partial<G12VoucherRow> } {
  const id = String(row.hedgeRelationId || '').trim()
  if (!id) {
    return { ok: false, message: '请先填写套期关系编号' }
  }
  const fv = findG12FvByHedgeRelationId(allResponses, id)
  if (!fv) {
    return { ok: false, message: `G12-4 无编号 ${id} 的公允价值测试行` }
  }
  const basis = formatG12FvValuationBasis(fv)
  if (!basis) {
    return { ok: false, message: `G12-4「${id}」估值方法/来源/层次均为空` }
  }
  const existing = String(row.supportingDocDesc || '').trim()
  let supportingDocDesc: string
  if (existing.includes('【G12-4估值】')) {
    supportingDocDesc = existing.replace(/【G12-4估值】[^；]*/g, basis).replace(/；{2,}/g, '；').replace(/^；|；$/g, '').trim()
  } else {
    supportingDocDesc = existing ? `${existing}；${basis}` : basis
  }
  const patch: Partial<G12VoucherRow> = { supportingDocDesc }
  if (row.check6FVValuation === null) {
    patch.check6FVValuation = true
  }
  return { ok: true, message: `已引用 G12-4 估值依据（${id}）`, patch }
}

/** 批量引用：仅处理有套期关系编号且能匹配到 G12-4 的行 */
export function batchCiteG12FvValuation(
  rows: G12VoucherRow[],
  allResponses: Map<string, ChecklistResponse>,
): { cited: number; skipped: number; rows: G12VoucherRow[] } {
  let cited = 0
  let skipped = 0
  const next = rows.map((r) => {
    const res = citeG12FvValuationToVoucher(r, allResponses)
    if (!res.ok || !res.patch) {
      if (String(r.hedgeRelationId || '').trim()) skipped += 1
      return r
    }
    cited += 1
    return { ...r, ...res.patch }
  })
  return { cited, skipped, rows: next }
}
