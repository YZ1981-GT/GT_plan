/**
 * K1 附注披露 — 溯源面板（附注区块 ↔ 源底稿 ↔ K1-1 审定）
 */
import type { Ref } from 'vue'
import { computed } from 'vue'
import { readAdjudicationTotals } from './k1DisclosureModel'
import { K1_SOE_SECTION_GUIDES, K1_LISTED_SECTION_GUIDES, type K1DisclosureVariant } from './k1NoteSectionMap'

export type K1TraceStatus = 'ok' | 'warn' | 'info'

export interface K1DisclosureTraceRow {
  id: string
  title: string
  noteTarget: string
  source: string
  sourceSheet: string
  adjudicationLabel: string
  adjudicationValue: number | null
  status: K1TraceStatus
  detail: string
}

function num(map: Map<string, any>, key: string): number {
  const raw = map.get(key)?.remark ?? map.get(key)?.value
  const n = Number(raw)
  return Number.isFinite(n) ? n : 0
}

function agingSubtotal(map: Map<string, any>, itemId: string): number {
  const raw = map.get(itemId)?.remark
  if (!raw) return 0
  try {
    const payload = typeof raw === 'string' ? JSON.parse(raw) : raw
    const rows = payload?.agingRows ?? []
    const sub = rows.find((r: { kind?: string }) => r.kind === 'subtotal')
    return Number(sub?.endAmount) || 0
  } catch {
    return 0
  }
}

function buildRows(variant: K1DisclosureVariant, map: Map<string, any>): K1DisclosureTraceRow[] {
  const guides = variant === 'listed' ? K1_LISTED_SECTION_GUIDES : K1_SOE_SECTION_GUIDES
  const adj = readAdjudicationTotals(map)
  const storageKey = variant === 'listed' ? 'K1-note-listed-rows' : 'K1-note-soe-rows'

  return guides.map((g) => {
    let adjudicationLabel = g.adjudicationLabel ?? '—'
    let adjudicationValue: number | null = null
    let status: K1TraceStatus = 'info'
    let detail = '待核对'

    if (g.adjudicationKey === 'receivable') {
      adjudicationValue = adj.receivableEnd
      adjudicationLabel = 'K1-1 其他应收款审定'
      const sub = agingSubtotal(map, storageKey)
      if (!adj.receivableEnd && !sub) {
        detail = 'K1-1 / 附注均未填'
      } else if (!sub) {
        status = 'info'
        detail = `K1-1 审定 ${adj.receivableEnd.toLocaleString('zh-CN')}`
      } else {
        const diff = sub - adj.receivableEnd
        status = Math.abs(diff) < 0.01 ? 'ok' : 'warn'
        detail = status === 'ok'
          ? `账龄小计与 K1-1 一致（${sub.toLocaleString('zh-CN')}）`
          : `账龄小计 ${sub.toLocaleString('zh-CN')} vs K1-1 ${adj.receivableEnd.toLocaleString('zh-CN')}（差 ${diff.toLocaleString('zh-CN')}）`
      }
    } else if (g.adjudicationKey === 'badDebt') {
      adjudicationValue = adj.badDebtEnd
      adjudicationLabel = 'K1-1 坏账准备审定'
      status = adj.badDebtEnd > 0 ? 'ok' : 'info'
      detail = adj.badDebtEnd > 0
        ? `K1-1 坏账审定 ${adj.badDebtEnd.toLocaleString('zh-CN')}`
        : '待完成 K1-1 / K1-3'
    } else if (g.adjudicationKey === 'net') {
      adjudicationValue = adj.receivableEnd - adj.badDebtEnd
      adjudicationLabel = 'K1-1 净值审定'
      status = adjudicationValue > 0 ? 'ok' : 'info'
      detail = `净值 ${adjudicationValue.toLocaleString('zh-CN')}`
    } else if (g.adjudicationKey === 'portfolio') {
      const label = g.portfolioLabel ?? ''
      const rowKey = g.portfolioRowKey ?? ''
      adjudicationLabel = label || '组合行'
      adjudicationValue = rowKey ? num(map, `K1-1-receivable-${rowKey}-audited`) : null
      status = adjudicationValue != null && adjudicationValue > 0 ? 'ok' : 'info'
      detail = adjudicationValue != null
        ? `${label} 审定 ${adjudicationValue.toLocaleString('zh-CN')}`
        : '待 K1-1 填写'
    } else {
      const hasSource = g.sourceSheet.includes('K1-1')
        ? adj.receivableEnd > 0
        : Boolean(map.get(g.sourceItemId ?? '')?.remark)
      status = hasSource ? 'ok' : 'info'
      detail = hasSource ? '源底稿已有数据' : '源底稿待填写'
    }

    return {
      id: g.id,
      title: g.title,
      noteTarget: g.noteTarget,
      source: g.source,
      sourceSheet: g.sourceSheet,
      adjudicationLabel,
      adjudicationValue,
      status,
      detail,
    }
  })
}

export function useK1DisclosureTrace(
  variant: K1DisclosureVariant,
  allResponses: Ref<Map<string, any>>,
) {
  const traceRows = computed(() => buildRows(variant, allResponses.value))
  const openCount = computed(() => traceRows.value.filter((r) => r.status === 'warn').length)

  return { traceRows, openCount }
}
