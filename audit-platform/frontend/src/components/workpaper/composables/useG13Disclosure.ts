/**
 * useG13Disclosure — 附注披露（上市 9+合计 / 国企 7+合计 × 5 列）
 */
import { ref, computed, watch, onMounted, onBeforeUnmount, type Ref } from 'vue'
import { parseNum, calcChangeAmount, calcChangeRate } from './useG13FormulaEngine'
import {
  G13_ACCOUNT_CODE,
  G13_DISCLOSURE_LISTED_ROWS,
  G13_DISCLOSURE_SOE_ROWS,
  G13_DETAIL_TO_DISCLOSURE,
} from './g13Constants'
import type { ChecklistResponse } from './useF1FormData'
import { api } from '@/services/apiProxy'

export interface G13DisclosureRow {
  rowKey: string
  label: string
  currentAmount: number
  priorAmount: number
  changeAmount: number
  changeRate: number | null
  remark: string
}

function rowDefs(variant: 'listed' | 'soe') {
  return variant === 'listed' ? G13_DISCLOSURE_LISTED_ROWS : G13_DISCLOSURE_SOE_ROWS
}

function defaultRows(variant: 'listed' | 'soe'): G13DisclosureRow[] {
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

function enrichRow(raw: Partial<G13DisclosureRow> & { rowKey: string }, variant: 'listed' | 'soe'): G13DisclosureRow {
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

export function useG13Disclosure(options: {
  variant: 'listed' | 'soe'
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  wpId: Ref<string>
  isReadonly: Ref<boolean>
}) {
  const variant = options.variant
  const itemId = variant === 'listed' ? 'G13-disclosure-listed' : 'G13-disclosure-soe'
  const noteItemId = `${itemId}-note`

  const rows = ref<G13DisclosureRow[]>(defaultRows(variant))
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
        if (parsed && typeof parsed === 'object' && parsed.label) {
          rows.value = defaultRows(variant).map((r) =>
            r.rowKey === 'trading_assets'
              ? enrichRow({ ...r, currentAmount: parsed.currentAmount, priorAmount: parsed.priorAmount }, variant)
              : r,
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
        accountCode: G13_ACCOUNT_CODE,
        section: variant,
        text: noteText.value,
        currentAmount: totalRow.value.currentAmount,
      },
    }))
  }

  function updateField(rowKey: string, field: keyof G13DisclosureRow, value: unknown): void {
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
    const detailJson = options.allResponses.value.get('G13-detail-rows')?.remark
    if (!detailJson) return
    try {
      const detailRows = JSON.parse(detailJson) as any[]
      const sums = new Map<string, number>()
      for (const d of detailRows) {
        let key = G13_DETAIL_TO_DISCLOSURE[d.belongAccount] ?? 'other'
        if (variant === 'soe') {
          if (d.belongAccount === 'G9') key = 'derivative_assets'
          if (d.belongAccount === 'G10') key = 'trading_liabilities'
        }
        sums.set(key, (sums.get(key) ?? 0) + parseNum(d.currentAudited ?? d.fvChange))
      }
      rows.value = rows.value.map((r) =>
        sums.has(r.rowKey) ? enrichRow({ ...r, currentAmount: sums.get(r.rowKey)! }, variant) : r,
      )
      persist()
    } catch { /* ignore */ }
  }

  function handleAdjudicated(e: Event): void {
    const d = (e as CustomEvent<{ accountCode: string; adjudicatedAmount: number }>).detail
    if (d?.accountCode === G13_ACCOUNT_CODE) {
      adjudicatedAmount.value = d.adjudicatedAmount
      syncFromDetail()
    }
  }

  function pullLatestAdjudicated(): void {
    const amt = options.allResponses.value.get('G13-1-adjudicated-amount')?.conclusion
    if (amt != null) adjudicatedAmount.value = parseNum(amt)
    syncFromDetail()
    const prior = options.allResponses.value.get('G13-adj-prior')?.remark
    if (prior) {
      try {
        const store = JSON.parse(prior) as Record<string, any>
        const priorSums = new Map<string, number>()
        for (const [adjKey, val] of Object.entries(store)) {
          let discKey = adjKey
          if (variant === 'soe' && adjKey === 'derivatives') discKey = 'derivative_assets'
          if (rowDefs(variant).some((d) => d.rowKey === discKey)) {
            priorSums.set(discKey, parseNum(val?.priorAudited))
          }
        }
        rows.value = rows.value.map((r) =>
          priorSums.has(r.rowKey) ? enrichRow({ ...r, priorAmount: priorSums.get(r.rowKey)! }, variant) : r,
        )
      } catch { /* ignore */ }
    }
  }

  async function generateAiConclusion(): Promise<void> {
    if (options.isReadonly.value || !options.wpId.value) return
    aiLoading.value = true
    try {
      const res = await api.post(
        `/api/workpapers/${options.wpId.value}/g13/ai/fv-change-conclusion`,
        {
          existingContent: noteText.value,
          relatedContext: { rows: rows.value, total: totalRow.value.currentAmount, adjudicatedAmount: adjudicatedAmount.value },
        },
        { _silent: true } as any,
      )
      const content = res?.data?.content ?? res?.content ?? ''
      if (content) { noteText.value = content; persist() }
    } catch {
      const draft = `本期公允价值变动收益合计 ${totalRow.value.currentAmount.toLocaleString()} 元，主要来源于交易性金融资产/负债及衍生工具公允价值变动。`
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
    syncFromDetail,
  }
}
