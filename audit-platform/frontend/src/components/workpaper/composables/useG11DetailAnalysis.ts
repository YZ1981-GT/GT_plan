/**
 * useG11DetailAnalysis — G11-2 明细分析表
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import {
  parseNum,
  calcAdjustedAmount,
  calcChangeAmount,
  calcChangeRate,
  calcSubtotal,
} from './useG11FormulaEngine'
import type { ChecklistResponse } from './useF1FormData'
import { G11_ADJUDICATION_ITEMS } from './g11Constants'

export interface G11DetailRow {
  id: string
  seq: number
  itemName: string
  investeeName: string
  group: string
  currentUnadjusted: number
  currentAdjustment: number
  currentAudited: number
  currentShare: number | null
  priorUnadjusted: number
  priorAdjustment: number
  priorAudited: number
  priorShare: number | null
  changeAmount: number
  changeRate: number | null
  reasonIndex: string
}

const ITEM_ID_ROWS = 'G11-detail-rows'

function resolveGroup(itemName: string): string {
  const hit = G11_ADJUDICATION_ITEMS.find((d) => d.label === itemName || itemName.includes(d.label.slice(0, 6)))
  return hit?.group ?? '其他'
}

function generateId(): string {
  return `g11d-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`
}

function enrichRow(raw: Partial<G11DetailRow> & { id?: string }, seq: number, totals?: { current: number; prior: number }): G11DetailRow {
  const currentUnadjusted = parseNum(raw.currentUnadjusted)
  const currentAdjustment = parseNum(raw.currentAdjustment)
  const priorUnadjusted = parseNum(raw.priorUnadjusted)
  const priorAdjustment = parseNum(raw.priorAdjustment)
  const currentAudited = calcAdjustedAmount(currentUnadjusted, currentAdjustment)
  const priorAudited = calcAdjustedAmount(priorUnadjusted, priorAdjustment)
  const currentShare = totals && totals.current > 0 ? currentAudited / totals.current : (raw.currentShare ?? null)
  const priorShare = totals && totals.prior > 0 ? priorAudited / totals.prior : (raw.priorShare ?? null)
  return {
    id: raw.id ?? generateId(),
    seq,
    itemName: raw.itemName ?? '',
    investeeName: raw.investeeName ?? '',
    group: raw.group ?? resolveGroup(raw.itemName ?? ''),
    currentUnadjusted,
    currentAdjustment,
    currentAudited,
    currentShare: currentShare != null ? parseNum(currentShare) : null,
    priorUnadjusted,
    priorAdjustment,
    priorAudited,
    priorShare: priorShare != null ? parseNum(priorShare) : null,
    changeAmount: calcChangeAmount(currentAudited, priorAudited),
    changeRate: calcChangeRate(priorAudited, currentAudited),
    reasonIndex: raw.reasonIndex ?? '',
  }
}

function parseRows(json: string | null | undefined): G11DetailRow[] {
  if (!json) return []
  try {
    const parsed = JSON.parse(json)
    if (!Array.isArray(parsed)) return []
    return parsed.map((r, i) => enrichRow(r, i + 1))
  } catch {
    return []
  }
}

export function useG11DetailAnalysis(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean> | ComputedRef<boolean>
}) {
  const rows = ref<G11DetailRow[]>([])

function recomputeAll(): void {
    const currentTotal = calcSubtotal(rows.value.map((r) => calcAdjustedAmount(parseNum(r.currentUnadjusted), parseNum(r.currentAdjustment))))
    const priorTotal = calcSubtotal(rows.value.map((r) => calcAdjustedAmount(parseNum(r.priorUnadjusted), parseNum(r.priorAdjustment))))
    rows.value = rows.value.map((r, i) => enrichRow(r, i + 1, { current: currentTotal, prior: priorTotal }))
  }

  watch(
    () => opts.allResponses.value.get(ITEM_ID_ROWS)?.remark,
    (json) => {
      const parsed = parseRows(json)
      rows.value = parsed
      recomputeAll()
    },
    { immediate: true },
  )

  function persist(): void {
    opts.debouncedSave(ITEM_ID_ROWS, { remark: JSON.stringify(rows.value) })
  }

  function reseq(): void {
    rows.value = rows.value.map((r, i) => ({ ...r, seq: i + 1 }))
  }

  const totalRow = computed(() => {
    const currentAudited = calcSubtotal(rows.value.map((r) => r.currentAudited))
    const priorAudited = calcSubtotal(rows.value.map((r) => r.priorAudited))
    return {
      currentAudited,
      priorAudited,
      changeAmount: calcChangeAmount(currentAudited, priorAudited),
      changeRate: calcChangeRate(priorAudited, currentAudited),
    }
  })

  const groupedRows = computed(() => {
    const map = new Map<string, G11DetailRow[]>()
    for (const row of rows.value) {
      const g = row.group || '其他'
      if (!map.has(g)) map.set(g, [])
      map.get(g)!.push(row)
    }
    return [...map.entries()].map(([groupName, groupRows]) => ({
      groupName,
      rows: groupRows,
      subtotal: {
        currentAudited: calcSubtotal(groupRows.map((r) => r.currentAudited)),
        priorAudited: calcSubtotal(groupRows.map((r) => r.priorAudited)),
      },
    }))
  })

  function applyOtherAdjustment(net: number): void {
    if (opts.isReadonly.value) return
    const other = rows.value.find((r) => r.itemName === '其他' || r.group === '其他')
    if (!other) return
    updateRow(other.id, { currentAdjustment: net })
  }

  function updateRow(id: string, patch: Partial<G11DetailRow>): void {
    if (opts.isReadonly.value) return
    rows.value = rows.value.map((r) => (r.id === id ? { ...r, ...patch } : r))
    recomputeAll()
    persist()
  }

  async function addRow(): Promise<void> {
    if (opts.isReadonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('请输入投资项目/项目名称', '新增明细行', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
      })
      if (!value?.trim()) return
      rows.value = [...rows.value, enrichRow({ itemName: value.trim() }, rows.value.length + 1)]
      persist()
    } catch { /* cancelled */ }
  }

  function removeRow(id: string): void {
    if (opts.isReadonly.value) return
    rows.value = rows.value.filter((r) => r.id !== id)
    reseq()
    persist()
  }

  function loadRows(data: Partial<G11DetailRow>[]): void {
    rows.value = data.map((r, i) => enrichRow(r as G11DetailRow, i + 1))
    recomputeAll()
    persist()
  }

  function reloadFromStore(): void {
    const json = opts.allResponses.value.get(ITEM_ID_ROWS)?.remark
    rows.value = parseRows(json)
    recomputeAll()
  }

  return { rows, totalRow, groupedRows, updateRow, addRow, removeRow, loadRows, reloadFromStore, applyOtherAdjustment }
}
