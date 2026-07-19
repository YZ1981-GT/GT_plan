/**
 * useG11Disclosure — 附注披露（上市/国企）
 */
import { ref, computed, watch, onMounted, onBeforeUnmount, type Ref } from 'vue'
import {
  G11_ACCOUNT_CODE,
  G11_DISCLOSURE_LISTED_ROWS,
  G11_DISCLOSURE_SOE_ROWS,
} from './g11Constants'
import { parseNum, calcChangeAmount, calcChangeRate, calcSubtotal } from './useG11FormulaEngine'
import type { ChecklistResponse } from './useF1FormData'
import { api } from '@/services/apiProxy'

export interface G11DisclosureRow {
  rowKey: string
  label: string
  currentAmount: number
  priorAmount: number
  changeAmount: number
  changeRate: number | null
  remark: string
}

function rowDefs(variant: 'listed' | 'soe') {
  return variant === 'listed' ? G11_DISCLOSURE_LISTED_ROWS : G11_DISCLOSURE_SOE_ROWS
}

function defaultRows(variant: 'listed' | 'soe'): G11DisclosureRow[] {
  return rowDefs(variant).map((def) => ({
    rowKey: def.rowKey,
    label: def.label,
    currentAmount: 0,
    priorAmount: 0,
    changeAmount: 0,
    changeRate: null,
    remark: '',
  }))
}

function enrichRow(raw: Partial<G11DisclosureRow> & { rowKey: string }, variant: 'listed' | 'soe'): G11DisclosureRow {
  const def = rowDefs(variant).find((d) => d.rowKey === raw.rowKey)
  const currentAmount = parseNum(raw.currentAmount)
  const priorAmount = parseNum(raw.priorAmount)
  return {
    rowKey: raw.rowKey,
    label: def?.label ?? raw.label ?? raw.rowKey,
    currentAmount,
    priorAmount,
    changeAmount: calcChangeAmount(currentAmount, priorAmount),
    changeRate: calcChangeRate(priorAmount, currentAmount),
    remark: raw.remark ?? '',
  }
}

export function useG11Disclosure(options: {
  variant: 'listed' | 'soe'
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
  wpId: Ref<string>
  isReadonly: Ref<boolean>
}) {
  const variant = options.variant
  const itemId = variant === 'listed' ? 'G11-disclosure-listed' : 'G11-disclosure-soe'
  const noteItemId = `${itemId}-note`

  const rows = ref<G11DisclosureRow[]>(defaultRows(variant))
  const noteText = ref('')
  const adjudicatedAmount = ref<number | null>(null)
  const aiLoading = ref(false)

  const title = computed(() =>
    variant === 'listed' ? '附注披露信息（上市公司）' : '附注披露信息（国企）',
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
    const adj = options.allResponses.value.get('G11-1-adjudicated-amount')?.conclusion
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

  function updateField(rowKey: string, field: 'currentAmount' | 'priorAmount' | 'remark', value: unknown): void {
    if (options.isReadonly.value || rowKey === 'total') return
    rows.value = rows.value.map((r) => {
      if (r.rowKey !== rowKey) return r
      const patch = { ...r, [field]: field === 'remark' ? String(value ?? '') : parseNum(value) }
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
          detail: { accountCode: G11_ACCOUNT_CODE, text: noteText.value },
        }))
      } catch { /* silent */ }
    }, 2000)
  }

  function handleAdjudicated(e: Event): void {
    const detail = (e as CustomEvent).detail
    if (detail?.accountCode === G11_ACCOUNT_CODE) {
      adjudicatedAmount.value = parseNum(detail.adjudicatedAmount)
    }
  }

  function pullLatestAdjudicated(): void {
    const adj = options.allResponses.value.get('G11-1-adjudicated-amount')?.conclusion
    if (adj != null) adjudicatedAmount.value = parseNum(adj)
  }

  async function generateAiConclusion(): Promise<void> {
    if (options.isReadonly.value) return
    aiLoading.value = true
    try {
      const res = await api.post(`/api/workpapers/${options.wpId.value}/g11/ai/adjudication-analysis`, {
        variant,
        rows: rows.value,
      }, { _silent: true } as any)
      const text = res?.data?.data?.content ?? res?.data?.content ?? res?.content ?? ''
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
