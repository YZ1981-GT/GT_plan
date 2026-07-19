/**
 * useG12Disclosure — 附注披露（上市 12 行 / 国企 11 行 × 5 列）
 */
import { ref, computed, watch, onMounted, onBeforeUnmount, type Ref } from 'vue'
import { parseNum, calcChangeAmount, calcChangeRate } from './useG12FormulaEngine'
import { G12_ACCOUNT_CODE, G12_DISCLOSURE_LISTED_ROWS, G12_DISCLOSURE_SOE_ROWS } from './g12Constants'
import type { ChecklistResponse } from './useF1FormData'
import { api } from '@/services/apiProxy'

export interface G12DisclosureRow {
  rowKey: string
  label: string
  currentAmount: number
  priorAmount: number
  changeAmount: number
  changeRate: number | null
  remark: string
}

function rowDefs(variant: 'listed' | 'soe') {
  return variant === 'listed' ? G12_DISCLOSURE_LISTED_ROWS : G12_DISCLOSURE_SOE_ROWS
}

function defaultRows(variant: 'listed' | 'soe'): G12DisclosureRow[] {
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

function enrichRow(raw: Partial<G12DisclosureRow> & { rowKey: string }, variant: 'listed' | 'soe'): G12DisclosureRow {
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

export function useG12Disclosure(opts: {
  variant: 'listed' | 'soe'
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
  wpId: Ref<string>
  isReadonly: Ref<boolean>
}) {
  const itemId = opts.variant === 'listed' ? 'G12-disclosure-listed' : 'G12-disclosure-soe'
  const noteItemId = `${itemId}-note`

  const rows = ref<G12DisclosureRow[]>(defaultRows(opts.variant))
  const noteText = ref('')
  const adjudicatedAmount = ref<number | null>(null)
  const aiLoading = ref(false)

  function loadFromStore(): void {
    const raw = opts.allResponses.value.get(itemId)?.remark
    if (raw) {
      try {
        const parsed = JSON.parse(raw)
        if (Array.isArray(parsed)) {
          rows.value = parsed.map((r: any) => enrichRow({ ...r, rowKey: r.rowKey }, opts.variant))
          return
        }
        // 兼容旧版单行存储
        if (parsed && typeof parsed === 'object' && parsed.label) {
          rows.value = defaultRows(opts.variant).map((r) =>
            r.rowKey === 'net_hedge'
              ? enrichRow({ ...r, currentAmount: parsed.currentAmount, priorAmount: parsed.priorAmount, label: parsed.label }, opts.variant)
              : r,
          )
          return
        }
      } catch { /* fallback */ }
    }
    rows.value = defaultRows(opts.variant)
  }

  watch(() => opts.allResponses.value.get(itemId)?.remark, loadFromStore, { immediate: true })
  watch(() => opts.allResponses.value.get(noteItemId)?.remark, (v) => { if (v != null) noteText.value = v }, { immediate: true })

  const totalRow = computed(() => {
    const currentAmount = rows.value.reduce((s, r) => s + r.currentAmount, 0)
    const priorAmount = rows.value.reduce((s, r) => s + r.priorAmount, 0)
    return enrichRow({ rowKey: 'total', label: '合计', currentAmount, priorAmount, remark: '' }, opts.variant)
  })

  const displayRows = computed(() => [...rows.value, totalRow.value])

  function persist(): void {
    opts.debouncedSave(itemId, {
      remark: JSON.stringify(rows.value.map((r) => ({
        rowKey: r.rowKey, label: r.label, currentAmount: r.currentAmount,
        priorAmount: r.priorAmount, remark: r.remark,
      }))),
    })
    opts.debouncedSave(noteItemId, { remark: noteText.value })
    window.dispatchEvent(new CustomEvent('disclosure:note-text-updated', {
      detail: {
        accountCode: G12_ACCOUNT_CODE,
        section: opts.variant,
        text: noteText.value,
        currentAmount: totalRow.value.currentAmount,
      },
    }))
  }

  function updateField(rowKey: string, field: keyof G12DisclosureRow, value: unknown): void {
    if (opts.isReadonly.value || rowKey === 'total') return
    const idx = rows.value.findIndex((r) => r.rowKey === rowKey)
    if (idx === -1) return
    const next = [...rows.value]
    next[idx] = enrichRow({ ...next[idx], [field]: value }, opts.variant)
    rows.value = next
    persist()
  }

  function updateNoteText(val: string): void {
    if (opts.isReadonly.value) return
    noteText.value = val
    persist()
  }

  function handleAdjudicated(e: Event): void {
    const d = (e as CustomEvent<{ accountCode: string; adjudicatedAmount: number }>).detail
    if (d?.accountCode === G12_ACCOUNT_CODE) {
      adjudicatedAmount.value = d.adjudicatedAmount
      if (!opts.isReadonly.value) {
        const idx = rows.value.findIndex((r) => r.rowKey === 'net_hedge')
        if (idx !== -1) {
          const next = [...rows.value]
          next[idx] = enrichRow({ ...next[idx], currentAmount: d.adjudicatedAmount }, opts.variant)
          rows.value = next
          persist()
        }
      }
    }
  }

  function pullLatestAdjudicated(): void {
    const amt = opts.allResponses.value.get('G12-1-adjudicated-amount')?.conclusion
    if (amt != null) adjudicatedAmount.value = parseNum(amt)
    const prior = opts.allResponses.value.get('G12-adj-prior')?.remark
    if (prior) {
      try {
        const store = JSON.parse(prior) as Record<string, any>
        const netPrior = store.net_hedge
        if (netPrior) {
          rows.value = rows.value.map((r) =>
            r.rowKey === 'net_hedge'
              ? enrichRow({ ...r, priorAmount: parseNum(netPrior.priorAudited ?? netPrior.priorUnadjusted) }, opts.variant)
              : r,
          )
        }
      } catch { /* ignore */ }
    }
  }

  async function generateAi(section = 'adjudication-analysis'): Promise<void> {
    if (opts.isReadonly.value || !opts.wpId.value) return
    aiLoading.value = true
    try {
      const res = await api.post(
        `/api/workpapers/${opts.wpId.value}/g12/ai/${section}`,
        { existingContent: noteText.value, relatedContext: { rows: rows.value, total: totalRow.value.currentAmount } },
        { _silent: true } as any,
      )
      const content = res?.data?.data?.content ?? res?.data?.content ?? res?.content ?? ''
      if (content) { noteText.value = content; persist() }
    } catch {
      const draft = `本期净敞口套期收益合计 ${totalRow.value.currentAmount.toLocaleString()} 元，详见套期关系明细及公允价值测试。`
      noteText.value = noteText.value ? `${noteText.value}\n${draft}` : draft
      persist()
    } finally { aiLoading.value = false }
  }

  async function generateAiConclusion(): Promise<void> {
    await generateAi('adjudication-analysis')
  }

  const title = computed(() => opts.variant === 'listed' ? '附注披露（上市公司）' : '附注披露（国企）')

  onMounted(() => {
    pullLatestAdjudicated()
    window.addEventListener('substantive:adjudicated', handleAdjudicated)
  })
  onBeforeUnmount(() => window.removeEventListener('substantive:adjudicated', handleAdjudicated))

  return {
    rows, displayRows, totalRow, noteText, adjudicatedAmount, aiLoading, title,
    updateField, updateNoteText, generateAi, generateAiConclusion, pullLatestAdjudicated,
  }
}
