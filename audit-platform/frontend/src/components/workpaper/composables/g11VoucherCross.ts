/**
 * G11-5 凭证检查 ↔ G11-3 调整 / G11A 程序
 */
import { G11_VOUCHER_CHECK_DEFS } from './g11VoucherConstants'
import { G11_ACCOUNT_CODE, G11_ADJUDICATION_ITEMS } from './g11Constants'
import { calcG11AdjustmentNet, parseG11AdjStore, patchG11AdjRow } from './g11AdjStorage'
import { parseNum } from './useG11FormulaEngine'
import type { G11VoucherCheckRow } from './useG11VoucherCheck'
import type { ChecklistResponse } from './useF1FormData'

export const G11_AJE_KEY = 'G11-aje-rows'
export const G11_ADJ_KEY = 'G11-adj-rows'
export const G11_DETAIL_KEY = 'G11-detail-rows'
export const G11A_PROCEDURE_SHEET = '投资收益实质性程序表G11A'
/** G11A seq3：重大投资收益检查（含 G11-5 凭证） */
export const G11A_VOUCHER_PROGRAM_NOS = [3] as const
export const G11A_VOUCHER_MARK_KEY = 'G11A-voucher-complete'

const AMT_THRESHOLD = 0.005

export function describeG11FailedChecks(row: G11VoucherCheckRow): string {
  const failed = G11_VOUCHER_CHECK_DEFS
    .filter((d) => row[d.key] === false)
    .map((d) => d.label)
  return failed.join('、') || '异常'
}

/** 金额类异常：异常且金额/账务核对未通过，且贷方金额>0 */
export function isG11QuantitativeVoucherAbnormal(row: G11VoucherCheckRow): boolean {
  if (!row.isAbnormal) return false
  const amt = Math.abs(parseNum(row.creditAmount))
  if (amt <= AMT_THRESHOLD) return false
  return row.check3 === false || row.check5 === false
}

export interface G11VoucherPushItem {
  summary: string
  amount: number
  indexRef: string
  remark: string
  voucherNo: string
  counterAccount: string
  counterDetail: string
}

export function isFromG115(row: { summary?: string; remark?: string; indexRef?: string }): boolean {
  const indexRef = String((row as any).indexRef || (row as any).indexNo || '')
  if (indexRef === 'G11-5' || indexRef.includes('G11-5')) return true
  const summary = String(row.summary || '')
  if (/^G11-5\s*凭证异常/.test(summary)) return true
  if (/来自 G11-5/.test(String(row.remark || ''))) return true
  return false
}

export function buildG11VoucherPushItems(rows: G11VoucherCheckRow[]): G11VoucherPushItem[] {
  const items: G11VoucherPushItem[] = []
  for (const row of rows) {
    if (!isG11QuantitativeVoucherAbnormal(row)) continue
    const amount = Math.abs(parseNum(row.creditAmount))
    if (amount <= AMT_THRESHOLD) continue
    const voucherNo = row.voucherNo?.trim() || row.id
    const failed = describeG11FailedChecks(row)
    items.push({
      summary: `G11-5 凭证异常：${voucherNo} ${row.businessContent || ''}`.trim(),
      amount,
      indexRef: 'G11-5',
      remark: [
        `来自 G11-5 凭证检查；未通过：${failed}`,
        row.abnormalDesc ? `说明：${row.abnormalDesc}` : '',
      ].filter(Boolean).join('；'),
      voucherNo,
      counterAccount: row.counterAccount || '',
      counterDetail: row.counterDetail || '',
    })
  }
  return items
}

function genAdjId(suffix: string): string {
  return `g11vc-adj-${suffix}`
}

function parseCounter(code: string): { code: string; name: string } {
  const m = String(code || '').trim().match(/^(\d{4})\s*(.*)$/)
  if (m) return { code: m[1], name: m[2]?.trim() || '对方科目' }
  const name = String(code || '').trim() || '待定对方科目'
  return { code: '', name }
}

/** 默认按收益高估冲减：借 6111 / 贷 对方科目 */
function buildAdjPair(
  item: G11VoucherPushItem,
  seq: number,
  idSuffix: string,
): Record<string, unknown>[] {
  const amt = item.amount
  const counter = parseCounter(item.counterAccount)
  const base = {
    entryType: 'AJE',
    date: new Date().toISOString().slice(0, 10),
    preparedBy: '',
    remark: item.remark,
  }
  return [
    {
      ...base,
      rowId: genAdjId(`${idSuffix}a`),
      seq,
      summary: item.summary,
      accountCode: G11_ACCOUNT_CODE,
      accountName: '投资收益',
      debitAmount: amt,
      creditAmount: 0,
    },
    {
      ...base,
      rowId: genAdjId(`${idSuffix}b`),
      seq: seq + 1,
      summary: item.summary,
      accountCode: counter.code || '0000',
      accountName: counter.name + (item.counterDetail ? `/${item.counterDetail}` : ''),
      debitAmount: 0,
      creditAmount: amt,
    },
  ]
}

function writebackG11AdjFromAje(
  responses: Map<string, ChecklistResponse>,
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void,
  ajeRows: Array<{ accountCode?: string; debitAmount?: number; creditAmount?: number }>,
): void {
  const net = calcG11AdjustmentNet(ajeRows)
  const store = parseG11AdjStore(responses.get(G11_ADJ_KEY)?.remark)
  const patched = patchG11AdjRow(store, 'other', {
    currentAdjustment: net,
    indexRef: 'G11-3/G11-5',
  })
  debouncedSave(G11_ADJ_KEY, { remark: JSON.stringify(patched) })

  // G11-2 明细「其他」行：若存在则同步本期调整
  const detailRaw = responses.get(G11_DETAIL_KEY)?.remark
  if (!detailRaw) return
  try {
    const parsed = JSON.parse(detailRaw)
    if (!Array.isArray(parsed)) return
    const otherLabel = G11_ADJUDICATION_ITEMS.find((d) => d.rowKey === 'other')?.label || '其他'
    let touched = false
    const next = parsed.map((r: Record<string, unknown>) => {
      const name = String(r.itemName ?? r.name ?? r.label ?? '')
      const key = String(r.rowKey ?? r.id ?? '')
      if (key === 'other' || name.includes(otherLabel) || name === '其他') {
        touched = true
        return { ...r, currentAdjustment: net }
      }
      return r
    })
    if (touched) debouncedSave(G11_DETAIL_KEY, { remark: JSON.stringify(next) })
  } catch { /* ignore */ }
}

/** 推送 G11-5 金额类异常至 G11-3，并回写 G11-1/G11-2「其他」 */
export function pushG11VoucherAbnormalToAdjustment(
  responses: Map<string, ChecklistResponse>,
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void,
  rows: G11VoucherCheckRow[],
): { pushed: number; skipped: number } {
  const items = buildG11VoucherPushItems(rows)
  if (!items.length) return { pushed: 0, skipped: 0 }

  let existing: Record<string, unknown>[] = []
  const raw = responses.get(G11_AJE_KEY)?.remark
  if (raw) {
    try {
      const parsed = JSON.parse(raw)
      if (Array.isArray(parsed)) existing = parsed
    } catch { /* ignore */ }
  }

  const summaries = new Set(
    existing.map((r) => String(r.summary || '').trim()).filter(Boolean),
  )
  const toPush = items.filter((it) => !summaries.has(it.summary.trim()))
  const skipped = items.length - toPush.length
  if (!toPush.length) return { pushed: 0, skipped }

  const added: Record<string, unknown>[] = []
  let seqBase = existing.length
  toPush.forEach((it, i) => {
    const pair = buildAdjPair(it, seqBase + added.length + 1, `${Date.now().toString(36)}-${i}`)
    added.push(...pair)
  })

  const merged = [...existing, ...added]
  debouncedSave(G11_AJE_KEY, { remark: JSON.stringify(merged) })
  writebackG11AdjFromAje(responses, debouncedSave, merged as any)
  try {
    window.dispatchEvent(new CustomEvent('g11:adjustment-synced', {
      detail: { netAdjustment: calcG11AdjustmentNet(merged as any), source: 'G11-5' },
    }))
  } catch { /* silent */ }

  return { pushed: toPush.length, skipped }
}

export function buildG11VoucherProcedureSummary(input: {
  rowCount: number
  abnormal: number
  quantitative: number
  inspectionRatioPct: number | null
}): string {
  const ratio = input.inspectionRatioPct == null ? '—' : `${input.inspectionRatioPct.toFixed(1)}%`
  return [
    `G11-5 凭证检查 ${input.rowCount} 行`,
    `异常 ${input.abnormal}`,
    `金额类异常 ${input.quantitative}`,
    `检查比例 ${ratio}`,
  ].join('；')
}

/** 回填 G11A 程序步骤（FieldOverrideService） */
export async function markG11AProcedureSteps(opts: {
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
  const scope = `procedure_table:${G11A_PROCEDURE_SHEET}`
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
        n += 1
      } catch { /* optional */ }
    }
  }
  return n
}
