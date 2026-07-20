/**
 * useG9Disclosure — 附注披露（上市/国企）
 *
 * 结构对齐 Excel：种类/项目 | 期末 | 上年年末/期初 |（产品增强）附注文本 + 合计行
 * 带入：G9-2 工具种类/指定优先，否则 G9-1 标签分项；无分项时残差进「其他」
 */
import { ref, computed, watch, onMounted, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import { ElMessage } from 'element-plus'
import {
  G9_ACCOUNT_CODE,
  G9_DISCLOSURE_LISTED_ROWS,
  G9_DISCLOSURE_SOE_ROWS,
} from './g9Constants'
import {
  G9_DISCLOSURE_COL_LABELS,
  G9_DISCLOSURE_TOTAL_LABEL,
} from './g9SchemaRows'
import { parseNum, calcSubtotal } from './useG9FormulaEngine'
import { buildG9CrossChecks, G9_CROSS_TOLERANCE, G9_ADJUDICATED_KEY } from './g9CrossHelpers'
import {
  buildG9DisclosureAmountsFromResponses,
  applyG9DisclosureAmountsToStore,
  formatG9DiscPullSummary,
  type G9DiscAmountSource,
  type G9DiscBucket,
} from './g9DisclosureFromAdj'
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
  /** 最近一次分项带入时的审定数快照（用于「审定已变未同步」提示） */
  const lastPulledAdjAmount = ref<number | null>(null)
  const pullSummary = ref('')
  const lastPullUsedResidual = ref(false)

  type RowVal = { currentAmount: number; priorAmount: number; noteText: string }
  const store = ref<Record<string, RowVal>>({})

  const title = computed(() =>
    opts.variant === 'listed' ? '附注披露信息（上市公司）' : '附注披露信息（国企）',
  )

  const colLabels = computed(() => G9_DISCLOSURE_COL_LABELS[opts.variant])

  function loadStore(): void {
    const raw = opts.allResponses.value.get(itemId(opts.variant))?.remark
    try {
      store.value = raw ? JSON.parse(raw) : {}
    } catch {
      store.value = {}
    }
    noteText.value = opts.allResponses.value.get(noteItemId(opts.variant))?.conclusion ?? ''
    const adj = opts.allResponses.value.get(G9_ADJUDICATED_KEY)?.conclusion
    if (adj != null && adj !== '') adjudicatedAmount.value = parseNum(adj)
  }

  watch(() => opts.allResponses.value.get(itemId(opts.variant))?.remark, loadStore, { immediate: true })
  watch(() => opts.allResponses.value.get(noteItemId(opts.variant))?.conclusion, (v) => {
    noteText.value = v ?? ''
  }, { immediate: true })
  watch(() => opts.allResponses.value.get(G9_ADJUDICATED_KEY)?.conclusion, (v) => {
    if (v != null && v !== '') adjudicatedAmount.value = parseNum(v)
  })

  const dataRows = computed(() =>
    rowDefs.map((def) => {
      const v = store.value[def.rowKey] ?? { currentAmount: 0, priorAmount: 0, noteText: '' }
      return { ...def, ...v, isTotal: false as const }
    }),
  )

  const disclosureCurrentSum = computed(() =>
    calcSubtotal(dataRows.value.map((r) => parseNum(r.currentAmount))),
  )

  const disclosurePriorSum = computed(() =>
    calcSubtotal(dataRows.value.map((r) => parseNum(r.priorAmount))),
  )

  const rows = computed(() => [
    ...dataRows.value,
    {
      rowKey: `${opts.variant}_total`,
      label: G9_DISCLOSURE_TOTAL_LABEL,
      currentAmount: disclosureCurrentSum.value,
      priorAmount: disclosurePriorSum.value,
      noteText: '',
      isTotal: true as const,
    },
  ])

  const adjCrossVariance = computed(() => {
    if (adjudicatedAmount.value == null) return null
    return disclosureCurrentSum.value - adjudicatedAmount.value
  })

  const hasAdjCrossMismatch = computed(() =>
    adjCrossVariance.value != null && Math.abs(adjCrossVariance.value) > G9_CROSS_TOLERANCE,
  )

  /** 审定数相对上次带入已变化（弱提示，不自动覆写） */
  const adjChangedSincePull = computed(() => {
    if (lastPulledAdjAmount.value == null || adjudicatedAmount.value == null) return false
    return Math.abs(adjudicatedAmount.value - lastPulledAdjAmount.value) > G9_CROSS_TOLERANCE
  })

  const crossChecks = computed(() =>
    buildG9CrossChecks(opts.allResponses.value, {
      disclosureCurrentSum: disclosureCurrentSum.value,
      adjudicatedAmount: adjudicatedAmount.value,
      disclosureNoteText: noteText.value,
    }),
  )

  function persist(): void {
    opts.debouncedSave(itemId(opts.variant), { remark: JSON.stringify(store.value) })
  }

  function updateField(rowKey: string, field: keyof RowVal, value: unknown): void {
    if (opts.isReadonly.value) return
    if (rowKey.endsWith('_total')) return
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
  }

  function pullLatestAdjudicated(writeCategories = false): void {
    const adj = opts.allResponses.value.get(G9_ADJUDICATED_KEY)?.conclusion
    if (adj != null && adj !== '') adjudicatedAmount.value = parseNum(adj)
    if (writeCategories) pullFromAdjudication()
  }

  /** G9-2 工具种类/指定优先，否则 G9-1 标签；无分项则残差进「其他」 */
  function pullFromAdjudication(): void {
    if (opts.isReadonly.value) return
    const built = buildG9DisclosureAmountsFromResponses(opts.allResponses.value)
    const adj = opts.allResponses.value.get(G9_ADJUDICATED_KEY)?.conclusion
    if (adj != null && adj !== '') adjudicatedAmount.value = parseNum(adj)

    const result = applyG9DisclosureAmountsToStore(
      rowDefs,
      store.value,
      built.amounts,
      {
        residualCurrent: adjudicatedAmount.value,
        residualPrior: null,
        sources: built.sources,
      },
    )
    store.value = result.next
    lastPulledAdjAmount.value = adjudicatedAmount.value
    lastPullUsedResidual.value = result.usedResidual
    pullSummary.value = formatG9DiscPullSummary(result.sources, result.usedResidual)
    persist()
    publishNoteUpdate()

    if (result.usedResidual) {
      ElMessage.warning(pullSummary.value)
    } else if (result.filledBuckets.length === 0) {
      ElMessage.info('暂无可带入分项：请在 G9-2 填写工具种类/指定，或在 G9-1 填写债务/权益等行')
    } else {
      ElMessage.success(`已带入 ${result.filledBuckets.length} 类：${pullSummary.value}`)
    }
  }

  function publishNoteUpdate(): void {
    try {
      const text = noteText.value || dataRows.value.map((r) => `${r.label}: ${r.noteText}`).join('\n')
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
        `/api/workpapers/${opts.wpId.value}/g9/ai/disclosure-note`,
        {
          variant: opts.variant,
          existingContent: noteText.value,
          rows: dataRows.value.slice(0, 20),
          relatedContext: {
            adjudicatedAmount: adjudicatedAmount.value,
            disclosureCurrentSum: disclosureCurrentSum.value,
          },
        },
        { _silent: true } as any,
      )
      const content = res?.data?.data?.content ?? res?.data?.content ?? res?.content ?? ''
      if (content) updateNoteText(content)
    } catch { /* AI optional */ }
    finally { aiLoading.value = false }
  }

  async function generateSectionAi(rowKey: string): Promise<void> {
    if (opts.isReadonly.value) return
    if (rowKey.endsWith('_total')) return
    const row = dataRows.value.find((r) => r.rowKey === rowKey)
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
      const content = res?.data?.data?.content ?? res?.data?.content ?? res?.content ?? ''
      if (content) updateField(rowKey, 'noteText', content)
    } catch { /* AI optional */ }
    finally {
      sectionAiLoading.value = { ...sectionAiLoading.value, [rowKey]: false }
    }
  }

  onMounted(() => {
    window.addEventListener('substantive:adjudicated', onAdjudicated)
    pullLatestAdjudicated(false)
    publishNoteUpdate()
  })
  onBeforeUnmount(() => {
    window.removeEventListener('substantive:adjudicated', onAdjudicated)
  })

  return {
    title,
    colLabels,
    rows,
    dataRows,
    noteText,
    adjudicatedAmount,
    disclosureCurrentSum,
    disclosurePriorSum,
    adjCrossVariance,
    hasAdjCrossMismatch,
    adjChangedSincePull,
    pullSummary,
    lastPullUsedResidual,
    crossChecks,
    aiLoading,
    sectionAiLoading,
    updateField,
    updateNoteText,
    pullLatestAdjudicated,
    pullFromAdjudication,
    clearPullSummary: () => { pullSummary.value = '' },
    generateAiConclusion,
    generateSectionAi,
  }
}

export type { G9DiscAmountSource, G9DiscBucket }
