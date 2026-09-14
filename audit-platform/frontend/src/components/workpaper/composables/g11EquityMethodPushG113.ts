/**
 * G7-14 权益法投资收益差异 → G11-3 建议调整分录
 */
import {
  aggregateG11AdjustmentByRow,
  applyG11AdjustmentWriteback,
  calcG11AdjustmentNet,
  parseG11AdjStore,
} from './g11AdjStorage'
import { G11_ACCOUNT_CODE, G11_ADJUDICATION_ITEMS } from './g11Constants'
import { parseNum } from './useG11FormulaEngine'
import type { G11EquityIncomeSeed } from './g11CrossHelpers'
import type { G11AdjustmentRow } from './useG11Adjustment'
import type { ChecklistResponse } from './useF1FormData'
import { G11_AJE_KEY, G11_ADJ_KEY, G11_DETAIL_KEY } from './g11VoucherCross'

export const G714_G11_SUGGESTED_SOURCE_KIND = 'g7-14-g11-suggested'
const PENNY = 0.005

function genRowId(suffix: string): string {
  return `g11g714-${suffix}-${Date.now().toString(36)}`
}

function isOverMateriality(amount: number, materialityLevel = 0): boolean {
  const amt = Math.abs(amount)
  if (amt < PENNY) return false
  if (materialityLevel > 0 && amt < materialityLevel) return false
  return true
}

/** 由 G7-14 投资收益差异生成 G11-3 借贷平衡建议分录（6111 ↔ 1511） */
export function buildG714SuggestedG11Adjustments(
  seeds: G11EquityIncomeSeed[],
  materialityLevel = 0,
): G11AdjustmentRow[] {
  const out: G11AdjustmentRow[] = []
  for (const seed of seeds) {
    const diff = parseNum(seed.incomeDifference)
    if (!isOverMateriality(diff, materialityLevel)) continue
    const name = seed.investeeName || '权益法被投资单位'
    const desc = `【G7-14】${name} 权益法投资收益差异调整（差异=${diff.toFixed(2)}）`
    const remark = `来源：G7-14 投资收益差异；sourceKind=${G714_G11_SUGGESTED_SOURCE_KIND}`
    const incomeTooHigh = diff > 0
    const amt = Math.abs(diff)
    const base = {
      description: desc,
      category: '账项调整',
      reportItem: '投资收益',
      noteItem: '',
      indexRef: 'G7-14/G11-3',
      remark,
      adjudicationRowKey: 'equity_method',
      entryType: 'AJE' as const,
      date: new Date().toISOString().slice(0, 10),
      preparedBy: '',
      sourceGroupId: `g714-${name}`,
    }
    out.push({
      ...base,
      rowId: genRowId(`${name}-dr`),
      accountCode: incomeTooHigh ? G11_ACCOUNT_CODE : '1511',
      accountName: incomeTooHigh ? '投资收益' : '长期股权投资',
      debitAmount: amt,
      creditAmount: 0,
    })
    out.push({
      ...base,
      rowId: genRowId(`${name}-cr`),
      accountCode: incomeTooHigh ? '1511' : G11_ACCOUNT_CODE,
      accountName: incomeTooHigh ? '长期股权投资' : '投资收益',
      debitAmount: 0,
      creditAmount: amt,
    })
  }
  return out
}

function parseAjeRows(raw: unknown): Record<string, unknown>[] {
  if (!raw) return []
  if (Array.isArray(raw)) return raw
  if (typeof raw === 'string') {
    try {
      const parsed = JSON.parse(raw)
      return Array.isArray(parsed) ? parsed : []
    } catch {
      return []
    }
  }
  return []
}

function isReplacedG714Draft(row: Record<string, unknown>): boolean {
  const sk = String(row.sourceKind ?? '')
  if (sk === G714_G11_SUGGESTED_SOURCE_KIND) return true
  const remark = String(row.remark ?? '')
  if (remark.includes(`sourceKind=${G714_G11_SUGGESTED_SOURCE_KIND}`)) return true
  const desc = String(row.description ?? row.summary ?? '')
  return /^【G7-14】/.test(desc) && remark.includes('G7-14')
}

/** 合并进 G11-aje-rows：仅替换同源 G7-14 建议草稿 */
export function mergeSuggestedIntoG11Aje(
  existing: Record<string, unknown>[],
  suggested: G11AdjustmentRow[],
): Record<string, unknown>[] {
  const kept = existing.filter((row) => !isReplacedG714Draft(row))
  const next = [...kept, ...suggested.map((r) => ({
    ...r,
    summary: r.description,
    sourceKind: G714_G11_SUGGESTED_SOURCE_KIND,
  }))]
  return next.map((row, index) => ({ ...row, seq: index + 1 }))
}

function writebackFromAje(
  responses: Map<string, ChecklistResponse>,
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void,
  ajeRows: Record<string, unknown>[],
  applyAdjustmentToDetail?: (byRow: Record<string, number>) => void,
): void {
  const byRow = aggregateG11AdjustmentByRow(ajeRows as any)
  const store = parseG11AdjStore(responses.get(G11_ADJ_KEY)?.remark)
  const patched = applyG11AdjustmentWriteback(store, byRow)
  debouncedSave(G11_ADJ_KEY, { remark: JSON.stringify(patched) })
  applyAdjustmentToDetail?.(byRow)

  const detailRaw = responses.get(G11_DETAIL_KEY)?.remark
  if (!detailRaw) return
  try {
    const parsed = JSON.parse(detailRaw)
    if (!Array.isArray(parsed)) return
    const otherLabel = G11_ADJUDICATION_ITEMS.find((d) => d.rowKey === 'other')?.label || '其他'
    let touched = false
    const next = parsed.map((r: Record<string, unknown>) => {
      const key = String(r.rowKey ?? '')
      const net = byRow[key]
      if (net == null || Math.abs(net) < PENNY) return r
      touched = true
      return { ...r, currentAdjustment: net }
    })
    if (!touched && Math.abs(byRow.other ?? 0) >= PENNY) {
      const idx = next.findIndex((r: Record<string, unknown>) => {
        const name = String(r.itemName ?? '')
        return String(r.rowKey) === 'other' || name.includes(otherLabel)
      })
      if (idx >= 0) next[idx] = { ...next[idx], currentAdjustment: byRow.other }
      else touched = true
    }
    if (touched) debouncedSave(G11_DETAIL_KEY, { remark: JSON.stringify(next) })
  } catch { /* ignore */ }
}

export interface PushG714G113Result {
  ok: boolean
  written: number
  message: string
}

/** 将 G7-14 投资收益差异建议分录写入 G11-3 并回写 G11-1/G11-2 */
export function pushSuggestedAdjustmentsFromG714Seeds(opts: {
  responses: Map<string, ChecklistResponse>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  seeds: G11EquityIncomeSeed[]
  materialityLevel?: number
  applyAdjustmentToDetail?: (byRow: Record<string, number>) => void
}): PushG714G113Result {
  const suggested = buildG714SuggestedG11Adjustments(opts.seeds, opts.materialityLevel ?? 0)
  if (!suggested.length) {
    return { ok: false, written: 0, message: '无达到推送阈值的 G7-14 投资收益差异' }
  }

  const existing = parseAjeRows(opts.responses.get(G11_AJE_KEY)?.remark)
  const merged = mergeSuggestedIntoG11Aje(existing, suggested)
  opts.debouncedSave(G11_AJE_KEY, { remark: JSON.stringify(merged) })
  writebackFromAje(opts.responses, opts.debouncedSave, merged, opts.applyAdjustmentToDetail)

  try {
    window.dispatchEvent(new CustomEvent('g11:adjustment-synced', {
      detail: {
        netAdjustment: calcG11AdjustmentNet(merged as any),
        source: 'G7-14',
        count: suggested.length,
      },
    }))
  } catch { /* silent */ }

  return {
    ok: true,
    written: suggested.length,
    message: `已写入 G11-3 共 ${suggested.length} 行（仅替换同源 G7-14 建议草稿）`,
  }
}
