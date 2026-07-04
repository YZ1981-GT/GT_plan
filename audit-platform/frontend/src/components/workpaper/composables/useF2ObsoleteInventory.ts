/**
 * useF2ObsoleteInventory — F2-48 长库龄呆滞超保质期存货
 */
import { ref, computed, watch, onBeforeUnmount, type Ref } from 'vue'
import {
  parseNum,
  calcSubtotal,
  isExpired,
  calcRemainingShelfDays,
  calcImpairmentProvision,
} from './useF2InvValFormulaEngine'
import { readValRowJson, type ChecklistResponse } from './useF2ValuationFormData'

export interface ObsoleteInventoryRow {
  rowId: string
  itemName: string
  qty: number
  bookCost: number
  ageDays: number
  shelfDays: number
  isObsolete: boolean
  disposalPlan: string
  impairmentSuggestion: number
  remark: string
}

const ROWS_KEY = 'F2-48-rows'
const NOTE_KEY = 'F2-48-note'

export const DISPOSAL_OPTIONS = ['正常销售', '促销', '报废', '退货', '转跌价'] as const

function genId(): string {
  return `f2obs-${Date.now().toString(36)}`
}

function enrichRow(r: ObsoleteInventoryRow) {
  const expired = isExpired(r.ageDays, r.shelfDays)
  const remainingDays = calcRemainingShelfDays(r.ageDays, r.shelfDays)
  const highlight = expired || r.isObsolete
  const nrv = r.bookCost * (expired ? 0.5 : 0.8)
  const suggested = calcImpairmentProvision(r.bookCost, nrv)
  return { ...r, expired, remainingDays, highlight, suggestedImpairment: suggested }
}

export function useF2ObsoleteInventory(options: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}) {
  const { allResponses, isReadonly } = options
  const readonly = isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  const rows = ref<ObsoleteInventoryRow[]>([{
    rowId: genId(), itemName: '', qty: 0, bookCost: 0, ageDays: 0, shelfDays: 365,
    isObsolete: false, disposalPlan: '正常销售', impairmentSuggestion: 0, remark: '',
  }])
  const auditNote = ref('')

  watch(() => allResponses.value.get(ROWS_KEY)?.remark, (v) => {
    if (!v) return
    try {
      const parsed = JSON.parse(v)
      if (Array.isArray(parsed) && parsed.length) rows.value = parsed
    } catch { /* ignore */ }
  }, { immediate: true })

  watch(() => allResponses.value.get(NOTE_KEY)?.remark, (v) => { auditNote.value = v || '' }, { immediate: true })

  const enrichedRows = computed(() => rows.value.map(enrichRow))

  const summary = computed(() => ({
    longAgeCount: enrichedRows.value.filter((r) => r.ageDays >= 365).length,
    obsoleteCount: enrichedRows.value.filter((r) => r.isObsolete).length,
    expiredCount: enrichedRows.value.filter((r) => r.expired).length,
    impairmentTotal: calcSubtotal(enrichedRows.value.map((r) => r.suggestedImpairment)),
  }))

  function persist(): void {
    allResponses.value.set(ROWS_KEY, { item_id: ROWS_KEY, conclusion: null, remark: JSON.stringify(rows.value) })
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      const items = [allResponses.value.get(ROWS_KEY), allResponses.value.get(NOTE_KEY)].filter(Boolean)
      if (items.length) window.dispatchEvent(new CustomEvent('f2-val:save-items', { detail: { items } }))
    }, 2000)
  }

  function addRow(): void {
    if (readonly.value) return
    rows.value = [...rows.value, {
      rowId: genId(), itemName: '', qty: 0, bookCost: 0, ageDays: 0, shelfDays: 365,
      isObsolete: false, disposalPlan: '正常销售', impairmentSuggestion: 0, remark: '',
    }]
    persist()
  }

  function removeRow(rowId: string): void {
    if (readonly.value || rows.value.length <= 1) return
    rows.value = rows.value.filter((r) => r.rowId !== rowId)
    persist()
  }

  function updateRow(rowId: string, patch: Partial<ObsoleteInventoryRow>): void {
    if (readonly.value) return
    rows.value = rows.value.map((r) => {
      if (r.rowId !== rowId) return r
      const next = { ...r, ...patch }
      if (patch.qty !== undefined || patch.bookCost !== undefined || patch.ageDays !== undefined) {
        next.qty = parseNum(next.qty)
        next.bookCost = parseNum(next.bookCost)
        next.ageDays = parseNum(next.ageDays)
      }
      return next
    })
    persist()
  }

  watch(auditNote, (val) => {
    if (readonly.value) return
    allResponses.value.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: val })
    persist()
  })

  onBeforeUnmount(() => { if (debounceTimer) { clearTimeout(debounceTimer); persist() } })

  return { enrichedRows, summary, auditNote, addRow, removeRow, updateRow }
}

export default useF2ObsoleteInventory
