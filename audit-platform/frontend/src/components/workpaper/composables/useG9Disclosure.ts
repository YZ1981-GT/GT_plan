/**
 * useG9Disclosure — 附注披露（上市/国企）
 */
import { ref, computed, watch, onMounted, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import { G9_ACCOUNT_CODE, G9_DISCLOSURE_LISTED_ROWS, G9_DISCLOSURE_SOE_ROWS } from './g9Constants'
import { parseNum } from './useG9FormulaEngine'
import type { ChecklistResponse } from './useF1FormData'
import { api } from '@/services/apiProxy'

type Variant = 'listed' | 'soe'

function itemId(variant: Variant): string {
  return variant === 'listed' ? 'G9-disclosure-listed' : 'G9-disclosure-soe'
}

function noteItemId(variant: Variant): string {
  return `${itemId(variant)}-note`
}

export function useG9Disclosure(opts: {
  variant: Variant
  wpId: Ref<string>
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean> | ComputedRef<boolean>
}) {
  const rowDefs = opts.variant === 'listed' ? G9_DISCLOSURE_LISTED_ROWS : G9_DISCLOSURE_SOE_ROWS
  const adjudicatedAmount = ref<number | null>(null)
  const noteText = ref('')
  const aiLoading = ref(false)
  const sectionAiLoading = ref<Record<string, boolean>>({})

  type RowVal = { currentAmount: number; priorAmount: number; noteText: string }
  const store = ref<Record<string, RowVal>>({})

  const title = computed(() =>
    opts.variant === 'listed' ? '附注披露信息（上市公司）' : '附注披露信息（国企）',
  )

  function loadStore(): void {
    const raw = opts.allResponses.value.get(itemId(opts.variant))?.remark
    try {
      store.value = raw ? JSON.parse(raw) : {}
    } catch {
      store.value = {}
    }
    noteText.value = opts.allResponses.value.get(noteItemId(opts.variant))?.conclusion ?? ''
    const adj = opts.allResponses.value.get('G9-1-adjudicated-amount')?.conclusion
    if (adj != null && adj !== '') adjudicatedAmount.value = parseNum(adj)
  }

  watch(() => opts.allResponses.value.get(itemId(opts.variant))?.remark, loadStore, { immediate: true })
  watch(() => opts.allResponses.value.get(noteItemId(opts.variant))?.conclusion, (v) => {
    noteText.value = v ?? ''
  }, { immediate: true })

  const rows = computed(() =>
    rowDefs.map((def) => {
      const v = store.value[def.rowKey] ?? { currentAmount: 0, priorAmount: 0, noteText: '' }
      return { ...def, ...v }
    }),
  )

  function persist(): void {
    opts.debouncedSave(itemId(opts.variant), { remark: JSON.stringify(store.value) })
  }

  function updateField(rowKey: string, field: keyof RowVal, value: unknown): void {
    if (opts.isReadonly.value) return
    const cur = store.value[rowKey] ?? { currentAmount: 0, priorAmount: 0, noteText: '' }
    if (field === 'noteText') cur.noteText = String(value ?? '')
    else cur[field] = parseNum(value)
    store.value = { ...store.value, [rowKey]: cur }
    persist()
    publishNoteUpdate()
  }

  function updateNoteText(value: string): void {
    if (opts.isReadonly.value) return
    noteText.value = value
    opts.debouncedSave(noteItemId(opts.variant), { conclusion: value })
    publishNoteUpdate()
  }

  function onAdjudicated(ev: Event): void {
    const detail = (ev as CustomEvent).detail
    if (detail?.accountCode !== G9_ACCOUNT_CODE) return
    adjudicatedAmount.value = parseNum(detail.adjudicatedAmount)
    const firstKey = rowDefs[0]?.rowKey
    if (firstKey) {
      const cur = store.value[firstKey] ?? { currentAmount: 0, priorAmount: 0, noteText: '' }
      cur.currentAmount = adjudicatedAmount.value ?? 0
      store.value = { ...store.value, [firstKey]: cur }
      persist()
    }
  }

  function pullLatestAdjudicated(): void {
    const adj = opts.allResponses.value.get('G9-1-adjudicated-amount')?.conclusion
    if (adj != null) adjudicatedAmount.value = parseNum(adj)
  }

  function publishNoteUpdate(): void {
    try {
      const text = noteText.value || rows.value.map((r) => `${r.label}: ${r.noteText}`).join('\n')
      window.dispatchEvent(new CustomEvent('disclosure:note-text-updated', {
        detail: { accountCode: G9_ACCOUNT_CODE, text },
      }))
    } catch { /* silent */ }
  }

  async function generateAiConclusion(): Promise<void> {
    if (opts.isReadonly.value) return
    aiLoading.value = true
    try {
      const res = await api.post(
        `/api/workpapers/${opts.wpId.value}/g9/ai/adjudication-analysis`,
        {
          variant: opts.variant,
          existingContent: noteText.value,
          rows: rows.value.slice(0, 20),
          relatedContext: { adjudicatedAmount: adjudicatedAmount.value },
        },
        { _silent: true } as any,
      )
      const content = res?.data?.content ?? res?.content ?? ''
      if (content) updateNoteText(content)
    } catch { /* AI optional */ }
    finally { aiLoading.value = false }
  }

  async function generateSectionAi(rowKey: string): Promise<void> {
    if (opts.isReadonly.value) return
    const row = rows.value.find((r) => r.rowKey === rowKey)
    if (!row) return
    sectionAiLoading.value = { ...sectionAiLoading.value, [rowKey]: true }
    try {
      const res = await api.post(
        `/api/workpapers/${opts.wpId.value}/g9/ai/disclosure-section`,
        {
          existingContent: row.noteText,
          relatedContext: {
            label: row.label,
            currentAmount: row.currentAmount,
            priorAmount: row.priorAmount,
            variant: opts.variant,
          },
        },
        { _silent: true } as any,
      )
      const content = res?.data?.content ?? res?.content ?? ''
      if (content) updateField(rowKey, 'noteText', content)
    } catch { /* AI optional */ }
    finally {
      sectionAiLoading.value = { ...sectionAiLoading.value, [rowKey]: false }
    }
  }

  onMounted(() => {
    window.addEventListener('substantive:adjudicated', onAdjudicated)
    pullLatestAdjudicated()
    publishNoteUpdate()
  })
  onBeforeUnmount(() => {
    window.removeEventListener('substantive:adjudicated', onAdjudicated)
  })

  return {
    title,
    rows,
    noteText,
    adjudicatedAmount,
    aiLoading,
    sectionAiLoading,
    updateField,
    updateNoteText,
    pullLatestAdjudicated,
    generateAiConclusion,
    generateSectionAi,
  }
}
