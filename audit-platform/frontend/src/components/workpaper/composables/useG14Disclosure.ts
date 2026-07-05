/**
 * useG14Disclosure — 附注披露（上市 9+合计 / 国企 4+合计）
 */
import { ref, computed, watch, onMounted, onBeforeUnmount, type Ref } from 'vue'
import { parseNum, calcChangeAmount, calcChangeRate } from './useG14FormulaEngine'
import {
  G14_ACCOUNT_CODE,
  G14_DISCLOSURE_LISTED_ROWS,
  G14_DISCLOSURE_SOE_ROWS,
  G14_SOE_BAD_DEBT_SOURCES,
} from './g14Constants'
import type { ChecklistResponse } from './useF1FormData'
import { api } from '@/services/apiProxy'

export interface G14DisclosureRow {
  rowKey: string
  label: string
  currentAmount: number
  priorAmount: number
  changeAmount: number
  changeRate: number | null
  remark: string
}

function rowDefs(variant: 'listed' | 'soe') {
  return variant === 'listed' ? G14_DISCLOSURE_LISTED_ROWS : G14_DISCLOSURE_SOE_ROWS
}

function defaultRows(variant: 'listed' | 'soe'): G14DisclosureRow[] {
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

function enrichRow(raw: Partial<G14DisclosureRow> & { rowKey: string }, variant: 'listed' | 'soe'): G14DisclosureRow {
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

export function useG14Disclosure(options: {
  variant: 'listed' | 'soe'
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  wpId: Ref<string>
  isReadonly: Ref<boolean>
}) {
  const variant = options.variant
  const itemId = variant === 'listed' ? 'G14-disclosure-listed' : 'G14-disclosure-soe'
  const noteItemId = `${itemId}-note`

  const rows = ref<G14DisclosureRow[]>(defaultRows(variant))
  const noteText = ref('')
  const adjudicatedAmount = ref<number | null>(null)
  const aiLoading = ref(false)

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
          return
        }
      } catch { /* fallback */ }
    }
    rows.value = defaultRows(variant)
  }

  watch(() => options.allResponses.value.get(itemId)?.remark, loadFromStore, { immediate: true })
  watch(() => options.allResponses.value.get(noteItemId)?.remark, (v) => {
    if (v != null) noteText.value = v
  }, { immediate: true })

  const totalRow = computed(() => {
    const currentAmount = rows.value.reduce((s, r) => s + r.currentAmount, 0)
    const priorAmount = rows.value.reduce((s, r) => s + r.priorAmount, 0)
    return enrichRow({ rowKey: 'total', label: '合  计', currentAmount, priorAmount, remark: '' }, variant)
  })

  const displayRows = computed(() => [...rows.value, totalRow.value])

  function persist(): void {
    options.debouncedSave(itemId, {
      remark: JSON.stringify(rows.value.map((r) => ({
        rowKey: r.rowKey, label: r.label, currentAmount: r.currentAmount,
        priorAmount: r.priorAmount, remark: r.remark,
      }))),
    })
    options.debouncedSave(noteItemId, { remark: noteText.value })
    window.dispatchEvent(new CustomEvent('disclosure:note-text-updated', {
      detail: {
        accountCode: G14_ACCOUNT_CODE,
        section: variant,
        text: noteText.value,
        currentAmount: totalRow.value.currentAmount,
      },
    }))
  }

  function updateField(rowKey: string, field: keyof G14DisclosureRow, value: unknown): void {
    if (options.isReadonly.value || rowKey === 'total') return
    const idx = rows.value.findIndex((r) => r.rowKey === rowKey)
    if (idx === -1) return
    const next = [...rows.value]
    next[idx] = enrichRow({ ...next[idx], [field]: value }, variant)
    rows.value = next
    persist()
  }

  function updateNoteText(val: string): void {
    if (options.isReadonly.value) return
    noteText.value = val
    persist()
  }

  function syncFromDetail(): void {
    const detailJson = options.allResponses.value.get('G14-detail-rows')?.remark
    if (!detailJson) return
    try {
      const detailRows = JSON.parse(detailJson) as any[]
      if (variant === 'listed') {
        rows.value = rows.value.map((r) => {
          const hit = detailRows.find((d) => d.rowKey === r.rowKey)
          return hit ? enrichRow({ ...r, currentAmount: hit.currentAudited ?? r.currentAmount }, variant) : r
        })
      } else {
        rows.value = rows.value.map((r) => {
          if (r.rowKey === 'bad_debt') {
            const sum = detailRows
              .filter((d) => G14_SOE_BAD_DEBT_SOURCES.includes(d.rowKey))
              .reduce((s, d) => s + parseNum(d.currentAudited), 0)
            return enrichRow({ ...r, currentAmount: sum }, variant)
          }
          const hit = detailRows.find((d) => d.rowKey === r.rowKey)
          return hit ? enrichRow({ ...r, currentAmount: hit.currentAudited ?? r.currentAmount }, variant) : r
        })
      }
      persist()
    } catch { /* ignore */ }
  }

  function handleAdjudicated(e: Event): void {
    const d = (e as CustomEvent<{ accountCode: string; adjudicatedAmount: number }>).detail
    if (d?.accountCode === G14_ACCOUNT_CODE) {
      adjudicatedAmount.value = d.adjudicatedAmount
      syncFromDetail()
    }
  }

  function pullLatestAdjudicated(): void {
    const tb = options.allResponses.value.get('G14-adj-tb')?.remark
    if (tb != null) adjudicatedAmount.value = parseNum(tb)
    syncFromDetail()
    const prior = options.allResponses.value.get('G14-adj-prior')
    if (prior?.remark) {
      try {
        const store = JSON.parse(prior.remark) as Record<string, any>
        if (variant === 'listed') {
          rows.value = rows.value.map((r) => {
            const p = store[r.rowKey]
            return p ? enrichRow({ ...r, priorAmount: parseNum(p.priorAudited) }, variant) : r
          })
        } else {
          const badDebtPrior = G14_SOE_BAD_DEBT_SOURCES.reduce(
            (s, k) => s + parseNum(store[k]?.priorAudited),
            0,
          )
          rows.value = rows.value.map((r) => {
            if (r.rowKey === 'bad_debt') {
              return enrichRow({ ...r, priorAmount: badDebtPrior }, variant)
            }
            const p = store[r.rowKey]
            return p ? enrichRow({ ...r, priorAmount: parseNum(p.priorAudited) }, variant) : r
          })
        }
      } catch { /* ignore */ }
    }
  }

  async function generateAiConclusion(): Promise<void> {
    if (options.isReadonly.value || !options.wpId.value) return
    aiLoading.value = true
    try {
      const res = await api.post(
        `/api/workpapers/${options.wpId.value}/g14/ai/impairment-conclusion`,
        {
          existingContent: noteText.value,
          relatedContext: { rows: rows.value, total: totalRow.value.currentAmount },
        },
        { _silent: true } as any,
      )
      const content = res?.data?.content ?? res?.content ?? ''
      if (content) { noteText.value = content; persist() }
    } catch {
      const draft = `本期信用减值损失合计 ${totalRow.value.currentAmount.toLocaleString()} 元，主要来源于应收款项及债权投资 ECL 计提/转回。`
      noteText.value = noteText.value ? `${noteText.value}\n${draft}` : draft
      persist()
    } finally {
      aiLoading.value = false
    }
  }

  const title = computed(() =>
    variant === 'listed' ? '附注披露（上市公司）' : '附注披露（国企）',
  )

  onMounted(() => {
    pullLatestAdjudicated()
    window.addEventListener('substantive:adjudicated', handleAdjudicated)
  })
  onBeforeUnmount(() => {
    window.removeEventListener('substantive:adjudicated', handleAdjudicated)
  })

  return {
    rows,
    displayRows,
    totalRow,
    noteText,
    adjudicatedAmount,
    aiLoading,
    title,
    updateField,
    updateNoteText,
    generateAiConclusion,
    pullLatestAdjudicated,
  }
}
