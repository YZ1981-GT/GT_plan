/**
 * useG14Detail — G14-2 明细表（固定9行 + 合计，减值准备滚动勾稽）
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { G14_LINE_ITEMS } from './g14Constants'
import {
  parseNum,
  calcAdjustedAmount,
  calcProvisionRollForward,
  calcProfitLossFromSheet,
  calcSubtotal,
  isRollForwardBalanced,
  isReconciled,
} from './useG14FormulaEngine'
import type { ChecklistResponse } from './useF1FormData'

export interface G14DetailRow {
  rowKey: string
  label: string
  provisionAccount: string
  currentUnadjusted: number
  currentAdjustment: number
  currentAudited: number
  openingProvision: number
  currentProvision: number
  currentReversal: number
  currentWriteoff: number
  closingProvision: number
  profitLoss: number
  reconciled: boolean
  rollForwardBalanced: boolean
  indexRef: string
}

const ITEM_ID_ROWS = 'G14-detail-rows'

function createDefaultRows(): G14DetailRow[] {
  return G14_LINE_ITEMS.map((def) => ({
    rowKey: def.rowKey,
    label: def.label,
    provisionAccount: def.provisionAccount,
    currentUnadjusted: 0,
    currentAdjustment: 0,
    currentAudited: 0,
    openingProvision: 0,
    currentProvision: 0,
    currentReversal: 0,
    currentWriteoff: 0,
    closingProvision: 0,
    profitLoss: 0,
    reconciled: true,
    rollForwardBalanced: true,
    indexRef: '',
  }))
}

function enrichRow(raw: Partial<G14DetailRow> & { rowKey: string }): G14DetailRow {
  const def = G14_LINE_ITEMS.find((d) => d.rowKey === raw.rowKey)
  const currentUnadjusted = parseNum(raw.currentUnadjusted)
  const currentAdjustment = parseNum(raw.currentAdjustment)
  const openingProvision = parseNum(raw.openingProvision)
  const currentProvision = parseNum(raw.currentProvision)
  const currentReversal = parseNum(raw.currentReversal)
  const currentWriteoff = parseNum(raw.currentWriteoff)
  const closingProvision = parseNum(raw.closingProvision)
  const currentAudited = calcAdjustedAmount(currentUnadjusted, currentAdjustment)
  const profitLoss = calcProfitLossFromSheet(currentProvision, currentReversal)
  const closingComputed = calcProvisionRollForward(
    openingProvision,
    currentProvision,
    currentReversal,
    currentWriteoff,
  )
  return {
    rowKey: raw.rowKey,
    label: def?.label ?? raw.label ?? raw.rowKey,
    provisionAccount: def?.provisionAccount ?? raw.provisionAccount ?? '',
    currentUnadjusted,
    currentAdjustment,
    currentAudited,
    openingProvision,
    currentProvision,
    currentReversal,
    currentWriteoff,
    closingProvision,
    profitLoss,
    reconciled: isReconciled(currentAudited, profitLoss),
    rollForwardBalanced: isRollForwardBalanced(
      openingProvision,
      currentProvision,
      currentReversal,
      currentWriteoff,
      closingProvision,
    ),
    indexRef: raw.indexRef ?? '',
  }
}

function parseStoredRows(json: string | null | undefined): G14DetailRow[] {
  if (!json) return createDefaultRows()
  try {
    const parsed = JSON.parse(json)
    if (!Array.isArray(parsed)) return createDefaultRows()
    const byKey = new Map(parsed.map((r: any) => [r.rowKey, r]))
    return G14_LINE_ITEMS.map((def) => enrichRow({ ...def, ...(byKey.get(def.rowKey) ?? {}) }))
  } catch {
    return createDefaultRows()
  }
}

export interface UseG14DetailOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean> | ComputedRef<boolean>
}

export function useG14Detail(options: UseG14DetailOptions) {
  const rows = ref<G14DetailRow[]>(createDefaultRows())

  watch(
    () => options.allResponses.value.get(ITEM_ID_ROWS)?.remark,
    (json) => { rows.value = parseStoredRows(json) },
    { immediate: true },
  )

  function persist(): void {
    const payload = rows.value.map((r) => ({
      rowKey: r.rowKey,
      currentUnadjusted: r.currentUnadjusted,
      currentAdjustment: r.currentAdjustment,
      openingProvision: r.openingProvision,
      currentProvision: r.currentProvision,
      currentReversal: r.currentReversal,
      currentWriteoff: r.currentWriteoff,
      closingProvision: r.closingProvision,
      indexRef: r.indexRef,
    }))
    options.debouncedSave(ITEM_ID_ROWS, { remark: JSON.stringify(payload) })
    window.dispatchEvent(new CustomEvent('g14:detail-updated'))
  }

  function updateCell(rowKey: string, field: keyof G14DetailRow, value: unknown): void {
    if (options.isReadonly.value) return
    const idx = rows.value.findIndex((r) => r.rowKey === rowKey)
    if (idx === -1) return
    const raw = { ...rows.value[idx], [field]: value }
    const next = [...rows.value]
    next[idx] = enrichRow(raw)
    rows.value = next
    persist()
  }

  const dataRows = computed(() => rows.value)
  const totalRow = computed(() => {
    const r = rows.value
    const currentUnadjusted = calcSubtotal(r.map((x) => x.currentUnadjusted))
    const currentAdjustment = calcSubtotal(r.map((x) => x.currentAdjustment))
    const currentAudited = calcSubtotal(r.map((x) => x.currentAudited))
    const profitLoss = calcSubtotal(r.map((x) => x.profitLoss))
    return enrichRow({
      rowKey: 'total',
      label: '合计',
      provisionAccount: '',
      currentUnadjusted,
      currentAdjustment,
      currentAudited,
      openingProvision: calcSubtotal(r.map((x) => x.openingProvision)),
      currentProvision: calcSubtotal(r.map((x) => x.currentProvision)),
      currentReversal: calcSubtotal(r.map((x) => x.currentReversal)),
      currentWriteoff: calcSubtotal(r.map((x) => x.currentWriteoff)),
      closingProvision: calcSubtotal(r.map((x) => x.closingProvision)),
      profitLoss,
      indexRef: '',
    })
  })

  const grandTotalAudited = computed(() => totalRow.value.currentAudited)
  const detailTotalMismatch = computed(() =>
  !isReconciled(totalRow.value.currentAudited, totalRow.value.profitLoss),
  )

  return {
    rows: dataRows,
    totalRow,
    grandTotalAudited,
    detailTotalMismatch,
    updateCell,
    persist,
    ITEM_ID_ROWS,
  }
}
