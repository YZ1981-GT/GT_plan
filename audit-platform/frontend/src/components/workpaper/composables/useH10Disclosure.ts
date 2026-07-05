/**
 * useH10Disclosure — 附注披露（上市/国企）
 */
import { ref, computed, watch, onMounted, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import {
  H10_ACCOUNT_CODE,
  H10_DISCLOSURE_LISTED_ROWS,
  H10_DISCLOSURE_SOE_ROWS,
} from './h10Constants'
import { parseNum, calcChangeAmount, calcChangeRate, calcSubtotal } from './useH10FormulaEngine'
import type { ChecklistResponse } from './useF1FormData'
import { api } from '@/services/apiProxy'

export interface H10DisclosureRow {
  rowKey: string
  label: string
  currentAmount: number
  priorAmount: number
  nonRecurringAmount?: number
  changeAmount: number
  changeRate: number | null
  remark: string
}

type Variant = 'listed' | 'soe'

function rowDefs(variant: Variant) {
  return variant === 'listed' ? H10_DISCLOSURE_LISTED_ROWS : H10_DISCLOSURE_SOE_ROWS
}

function defaultRows(variant: Variant): H10DisclosureRow[] {
  return rowDefs(variant).map((def) => ({
    rowKey: def.rowKey,
    label: def.label,
    currentAmount: 0,
    priorAmount: 0,
    nonRecurringAmount: variant === 'soe' ? 0 : undefined,
    changeAmount: 0,
    changeRate: null,
    remark: '',
  }))
}

function enrichRow(
  raw: Partial<H10DisclosureRow> & { rowKey: string },
  variant: Variant,
): H10DisclosureRow {
  const def = rowDefs(variant).find((d) => d.rowKey === raw.rowKey)
  const currentAmount = parseNum(raw.currentAmount)
  const priorAmount = parseNum(raw.priorAmount)
  return {
    rowKey: raw.rowKey,
    label: def?.label ?? raw.label ?? raw.rowKey,
    currentAmount,
    priorAmount,
    nonRecurringAmount: variant === 'soe' ? parseNum(raw.nonRecurringAmount) : undefined,
    changeAmount: calcChangeAmount(currentAmount, priorAmount),
    changeRate: calcChangeRate(priorAmount, currentAmount),
    remark: raw.remark ?? '',
  }
}

export function useH10Disclosure(options: {
  variant: Variant
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
  wpId: Ref<string>
  isReadonly: Ref<boolean> | ComputedRef<boolean>
}) {
  const variant = options.variant
  const itemId = variant === 'listed' ? 'H10-disclosure-listed' : 'H10-disclosure-soe'
  const noteItemId = `${itemId}-note`

  const rows = ref<H10DisclosureRow[]>(defaultRows(variant))
  const noteText = ref('')
  const adjudicatedAmount = ref<number | null>(null)
  const aiLoading = ref(false)

  const title = computed(() =>
    variant === 'listed' ? '附注披露信息（上市公司）' : '附注披露信息（国有企业）',
  )

  function loadFromStore(): void {
    const raw = options.allResponses.value.get(itemId)?.remark
    if (raw) {
      try {
        const parsed = JSON.parse(raw)
        if (Array.isArray(parsed)) {
          const byKey = new Map(parsed.map((r: any) => [r.rowKey, r]))
          rows.value = rowDefs(variant).map((def) =>
            enrichRow({ ...def, ...byKey.get(def.rowKey) }, variant),
          )
        }
      } catch { /* ignore */ }
    }
    noteText.value = options.allResponses.value.get(noteItemId)?.conclusion ?? ''
    const adj = options.allResponses.value.get('H10-1-adjudicated-amount')?.conclusion
    if (adj != null && adj !== '') adjudicatedAmount.value = parseNum(adj)
  }

  watch(() => options.allResponses.value, loadFromStore, { deep: true, immediate: true })

  const displayRows = computed(() => {
    const data = rows.value
    const total = {
      rowKey: 'total',
      label: '合  计',
      currentAmount: calcSubtotal(data.map((r) => r.currentAmount)),
      priorAmount: calcSubtotal(data.map((r) => r.priorAmount)),
      nonRecurringAmount: variant === 'soe'
        ? calcSubtotal(data.map((r) => parseNum(r.nonRecurringAmount)))
        : undefined,
      changeAmount: 0,
      changeRate: null as number | null,
      remark: '',
    }
    total.changeAmount = calcChangeAmount(total.currentAmount, total.priorAmount)
    total.changeRate = calcChangeRate(total.priorAmount, total.currentAmount)
    return [...data, total]
  })

  function persist(): void {
    options.debouncedSave(itemId, { remark: JSON.stringify(rows.value) })
  }

  function updateField(
    rowKey: string,
    field: 'currentAmount' | 'priorAmount' | 'nonRecurringAmount' | 'remark',
    value: unknown,
  ): void {
    if (options.isReadonly.value || rowKey === 'total') return
    rows.value = rows.value.map((r) => {
      if (r.rowKey !== rowKey) return r
      const patch = {
        ...r,
        [field]: field === 'remark' ? String(value ?? '') : parseNum(value),
      }
      return enrichRow(patch, variant)
    })
    persist()
    publishNoteDebounced()
  }

  function updateNoteText(value: string): void {
    if (options.isReadonly.value) return
    noteText.value = value
    options.debouncedSave(noteItemId, { conclusion: value })
    publishNoteDebounced()
  }

  let noteTimer: ReturnType<typeof setTimeout> | null = null
  function publishNoteDebounced(): void {
    if (noteTimer) clearTimeout(noteTimer)
    noteTimer = setTimeout(() => {
      noteTimer = null
      try {
        window.dispatchEvent(new CustomEvent('disclosure:note-text-updated', {
          detail: { accountCode: H10_ACCOUNT_CODE, text: noteText.value },
        }))
      } catch { /* silent */ }
    }, 2000)
  }

  function handleAdjudicated(e: Event): void {
    const detail = (e as CustomEvent).detail
    if (detail?.accountCode === H10_ACCOUNT_CODE) {
      adjudicatedAmount.value = parseNum(detail.adjudicatedAmount)
    }
  }

  function pullLatestAdjudicated(): void {
    const adj = options.allResponses.value.get('H10-1-adjudicated-amount')?.conclusion
    if (adj != null) adjudicatedAmount.value = parseNum(adj)
  }

  async function generateAiConclusion(): Promise<void> {
    if (options.isReadonly.value) return
    aiLoading.value = true
    try {
      const res = await api.post(`/api/workpapers/${options.wpId.value}/h10/ai/disclosure-analysis`, {
        variant,
        rows: rows.value,
      }, { _silent: true } as any)
      const text = res?.data?.content ?? res?.content ?? ''
      if (text) updateNoteText(text)
    } catch { /* AI optional */ }
    finally { aiLoading.value = false }
  }

  onMounted(() => {
    window.addEventListener('substantive:adjudicated', handleAdjudicated)
    pullLatestAdjudicated()
  })
  onBeforeUnmount(() => {
    window.removeEventListener('substantive:adjudicated', handleAdjudicated)
    if (noteTimer) clearTimeout(noteTimer)
  })

  return {
    title,
    rows,
    displayRows,
    noteText,
    adjudicatedAmount,
    aiLoading,
    updateField,
    updateNoteText,
    pullLatestAdjudicated,
    generateAiConclusion,
  }
}
