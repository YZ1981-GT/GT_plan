/**
 * useG8Disclosure — 附注披露（上市/国企）
 * 结构对齐 Excel 底稿：余额表 + 指定原因 + OCI/期末明细表
 */
import { ref, computed, watch, onMounted, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import { G8_ACCOUNT_CODE } from './g8Constants'
import {
  createEmptyListedStore,
  createEmptySoeStore,
  migrateLegacyDisclosureStore,
  disclosureStoreHasContent,
  g8DisclosureRemarkHasContent,
  type G8DisclosureStoreV2,
  type G8DiscBalanceRow,
  type G8DiscListedOciRow,
  type G8DiscSoeDetailRow,
  G8_LISTED_INTRO,
  G8_LISTED_DESIGNATION_HINT,
  G8_LISTED_DESIGNATION_PLACEHOLDER,
  G8_SOE_SECTION1_TITLE,
  G8_SOE_SECTION2_TITLE,
  G8_SOE_DESIGNATION_HINT,
  G8_SOE_DESIGNATION_PLACEHOLDER,
} from './g8SchemaRows'
import {
  pullG8DisclosureFromDetail,
  buildG8DesignationFromResponses,
  type G8DiscPullResult,
} from './g8DisclosureFromDetail'
import { parseNum } from './useG8FormulaEngine'
import type { ChecklistResponse } from './useF1FormData'
import { api } from '@/services/apiProxy'

type Variant = 'listed' | 'soe'

const DIFF_TOLERANCE = 0.01

function itemId(variant: Variant): string {
  return variant === 'listed' ? 'G8-disclosure-listed' : 'G8-disclosure-soe'
}

function noteItemId(variant: Variant): string {
  return `${itemId(variant)}-note`
}

export function useG8Disclosure(opts: {
  variant: Variant
  wpId: Ref<string>
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean> | ComputedRef<boolean>
}) {
  const store = ref<G8DisclosureStoreV2>(
    opts.variant === 'listed' ? createEmptyListedStore() : createEmptySoeStore(),
  )
  const adjudicatedAmount = ref<number | null>(null)
  const noteText = ref('')
  const aiLoading = ref(false)
  const sectionAiLoading = ref<Record<string, boolean>>({})

  const title = computed(() =>
    opts.variant === 'listed' ? '附注披露信息（上市公司）' : '附注披露信息（国企）',
  )

  const introText = computed(() =>
    opts.variant === 'listed' ? G8_LISTED_INTRO : G8_SOE_SECTION1_TITLE,
  )

  const designationHint = computed(() =>
    opts.variant === 'listed' ? G8_LISTED_DESIGNATION_HINT : G8_SOE_DESIGNATION_HINT,
  )

  const designationPlaceholder = computed(() =>
    opts.variant === 'listed' ? G8_LISTED_DESIGNATION_PLACEHOLDER : G8_SOE_DESIGNATION_PLACEHOLDER,
  )

  const section2Title = computed(() =>
    opts.variant === 'listed' ? null : G8_SOE_SECTION2_TITLE,
  )

  function loadStore(): void {
    const raw = opts.allResponses.value.get(itemId(opts.variant))?.remark
    let parsed: unknown = null
    try {
      parsed = raw ? JSON.parse(raw) : null
    } catch {
      parsed = null
    }
    store.value = migrateLegacyDisclosureStore(parsed, opts.variant)
    noteText.value = opts.allResponses.value.get(noteItemId(opts.variant))?.conclusion ?? ''
    const adj = opts.allResponses.value.get('G8-1-adjudicated-amount')?.conclusion
    if (adj != null && adj !== '') adjudicatedAmount.value = parseNum(adj)
  }

  watch(() => opts.allResponses.value.get(itemId(opts.variant))?.remark, loadStore, { immediate: true })
  watch(() => opts.allResponses.value.get(noteItemId(opts.variant))?.conclusion, (v) => {
    noteText.value = v ?? ''
  }, { immediate: true })
  watch(() => opts.allResponses.value.get('G8-1-adjudicated-amount')?.conclusion, (v) => {
    if (v != null && v !== '') adjudicatedAmount.value = parseNum(v)
  })

  const balanceRows = computed<G8DiscBalanceRow[]>(() => {
    const rows = store.value.balanceRows.map((r, i) => ({
      rowKey: `bal_${i + 1}`,
      label: r.label,
      closing: r.closing,
      prior: r.prior,
    }))
    const closing = rows.reduce((s, r) => s + parseNum(r.closing), 0)
    const prior = rows.reduce((s, r) => s + parseNum(r.prior), 0)
    rows.push({ rowKey: 'bal_total', label: '合  计', closing, prior, isTotal: true })
    return rows
  })

  const ociRows = computed<G8DiscListedOciRow[]>(() => {
    if (opts.variant !== 'listed') return []
    return (store.value.ociRows ?? []).map((r, i) => ({
      rowKey: `oci_${i + 1}`,
      label: r.label,
      ociPeriod: r.ociPeriod,
      ociCumulative: r.ociCumulative,
      dividend: r.dividend,
      transferToRE: r.transferToRE,
      derecogReason: r.derecogReason,
    }))
  })

  const detailRows = computed<G8DiscSoeDetailRow[]>(() => {
    if (opts.variant !== 'soe') return []
    const rows = (store.value.detailRows ?? []).map((r, i) => ({
      rowKey: `detail_${i + 1}`,
      label: r.label,
      dividend: r.dividend,
      ociPeriod: r.ociPeriod,
      ociCumulative: r.ociCumulative,
      transferAmt: r.transferAmt,
      transferReason: r.transferReason,
    }))
    const sum = (pick: (r: typeof rows[0]) => number) => rows.reduce((s, r) => s + parseNum(pick(r)), 0)
    rows.push({
      rowKey: 'detail_total',
      label: '合  计',
      dividend: sum((r) => r.dividend),
      ociPeriod: sum((r) => r.ociPeriod),
      ociCumulative: sum((r) => r.ociCumulative),
      transferAmt: sum((r) => r.transferAmt),
      transferReason: '',
      isTotal: true,
    })
    return rows
  })

  /** 余额表合计期末 — 与 G8-1 审定勾稽 */
  const primaryCurrentAmount = computed(() =>
    store.value.balanceRows.reduce((s, r) => s + parseNum(r.closing), 0),
  )

  const adjCrossVariance = computed(() => {
    if (adjudicatedAmount.value == null) return null
    return primaryCurrentAmount.value - adjudicatedAmount.value
  })

  const hasAdjCrossMismatch = computed(() =>
    adjCrossVariance.value != null && Math.abs(adjCrossVariance.value) > DIFF_TOLERANCE,
  )

  function persist(): void {
    opts.debouncedSave(itemId(opts.variant), { remark: JSON.stringify(store.value) })
  }

  function updateBalance(rowKey: string, field: 'label' | 'closing' | 'prior', value: unknown): void {
    if (opts.isReadonly.value || rowKey === 'bal_total') return
    const idx = Number(rowKey.replace('bal_', '')) - 1
    if (idx < 0 || idx >= store.value.balanceRows.length) return
    const next = [...store.value.balanceRows]
    const cur = { ...next[idx] }
    if (field === 'label') cur.label = String(value ?? '')
    else cur[field] = parseNum(value)
    next[idx] = cur
    store.value = { ...store.value, balanceRows: next }
    persist()
    publishNoteUpdate()
  }

  function updateDesignation(value: string): void {
    if (opts.isReadonly.value) return
    store.value = { ...store.value, designationText: value }
    persist()
    publishNoteUpdate()
  }

  function updateOci(
    rowKey: string,
    field: keyof Omit<G8DiscListedOciRow, 'rowKey'>,
    value: unknown,
  ): void {
    if (opts.isReadonly.value || opts.variant !== 'listed') return
    const idx = Number(rowKey.replace('oci_', '')) - 1
    const list = [...(store.value.ociRows ?? [])]
    if (idx < 0 || idx >= list.length) return
    const cur = { ...list[idx] }
    if (field === 'label' || field === 'derecogReason') cur[field] = String(value ?? '')
    else cur[field] = parseNum(value)
    list[idx] = cur
    store.value = { ...store.value, ociRows: list }
    persist()
    publishNoteUpdate()
  }

  function updateDetail(
    rowKey: string,
    field: keyof Omit<G8DiscSoeDetailRow, 'rowKey' | 'isTotal'>,
    value: unknown,
  ): void {
    if (opts.isReadonly.value || opts.variant !== 'soe' || rowKey === 'detail_total') return
    const idx = Number(rowKey.replace('detail_', '')) - 1
    const list = [...(store.value.detailRows ?? [])]
    if (idx < 0 || idx >= list.length) return
    const cur = { ...list[idx] }
    if (field === 'label' || field === 'transferReason') cur[field] = String(value ?? '')
    else cur[field] = parseNum(value)
    list[idx] = cur
    store.value = { ...store.value, detailRows: list }
    persist()
    publishNoteUpdate()
  }

  function updateNoteText(value: string): void {
    if (opts.isReadonly.value) return
    noteText.value = value
    opts.debouncedSave(noteItemId(opts.variant), { conclusion: value })
    publishNoteUpdate()
  }

  /** 写入审定数到余额合计口径：首行期末 = 审定 − 其余行期末 */
  function writeFirstRowAmount(amount: number): void {
    const next = store.value.balanceRows.map((r) => ({ ...r }))
    if (!next.length) return
    const others = next.slice(1).reduce((s, r) => s + parseNum(r.closing), 0)
    next[0] = { ...next[0], closing: amount - others }
    if (!(next[0].label || '').trim()) next[0].label = '权益工具投资（FVOCI）'
    store.value = { ...store.value, balanceRows: next }
    persist()
  }

  function onAdjudicated(ev: Event): void {
    const detail = (ev as CustomEvent).detail
    if (detail?.accountCode !== G8_ACCOUNT_CODE) return
    adjudicatedAmount.value = parseNum(detail.adjudicatedAmount)
    if (!opts.isReadonly.value) {
      writeFirstRowAmount(adjudicatedAmount.value ?? 0)
    }
  }

  function pullLatestAdjudicated(writeFirst = false): void {
    const adj = opts.allResponses.value.get('G8-1-adjudicated-amount')?.conclusion
    if (adj == null || adj === '') {
      adjudicatedAmount.value = null
      return
    }
    adjudicatedAmount.value = parseNum(adj)
    if (writeFirst && !opts.isReadonly.value) {
      writeFirstRowAmount(adjudicatedAmount.value)
    }
  }

  /** 从 G8-2 带入余额 + OCI/明细；指定原因优先 G8-5 再 G8-2 */
  function syncFromDetail(fillDesignation = true): G8DiscPullResult {
    const result = pullG8DisclosureFromDetail(opts.allResponses.value, opts.variant, { fillDesignation })
    if (opts.isReadonly.value) return result
    if (!result.sourceCount) return result

    // 溢出汇总行清空原因文案，避免误用单一项目原因
    if (result.overflowCount > 0) {
      if (result.store.ociRows?.length) {
        const last = result.store.ociRows[result.store.ociRows.length - 1]
        if (last.label === '其他') last.derecogReason = ''
      }
      if (result.store.detailRows?.length) {
        const last = result.store.detailRows[result.store.detailRows.length - 1]
        if (last.label === '其他') last.transferReason = ''
      }
    }

    if (!fillDesignation) {
      result.store.designationText = store.value.designationText
      result.designationFilled = false
    }
    store.value = result.store
    persist()
    publishNoteUpdate()
    return result
  }

  /** 仅刷新指定原因（G8-2 / G8-5） */
  function syncDesignationOnly(): { filled: boolean; text: string } {
    const text = buildG8DesignationFromResponses(opts.allResponses.value)
    if (opts.isReadonly.value) return { filled: false, text }
    if (!text.trim()) return { filled: false, text: '' }
    updateDesignation(text)
    return { filled: true, text }
  }

  function publishNoteUpdate(): void {
    try {
      const parts = [
        noteText.value,
        store.value.designationText,
        ...store.value.balanceRows.map((r) => `${r.label}: ${r.closing}`),
      ].filter(Boolean)
      window.dispatchEvent(new CustomEvent('disclosure:note-text-updated', {
        detail: { accountCode: G8_ACCOUNT_CODE, text: parts.join('\n') },
      }))
    } catch { /* silent */ }
  }

  async function generateAiConclusion(): Promise<void> {
    if (opts.isReadonly.value) return
    aiLoading.value = true
    try {
      const section = opts.variant === 'listed' ? 'disclosure-listed-note' : 'disclosure-soe-note'
      const res = await api.post(
        `/api/workpapers/${opts.wpId.value}/g8/ai/${section}`,
        {
          variant: opts.variant,
          existingContent: noteText.value,
          rows: balanceRows.value,
          relatedContext: {
            adjudicatedAmount: adjudicatedAmount.value,
            primaryCurrentAmount: primaryCurrentAmount.value,
            adjCrossVariance: adjCrossVariance.value,
            hasAdjCrossMismatch: hasAdjCrossMismatch.value,
            designationText: store.value.designationText,
            ociRows: store.value.ociRows,
            detailRows: store.value.detailRows,
          },
        },
        { _silent: true } as any,
      )
      const content = res?.data?.content ?? res?.content ?? ''
      if (content) updateNoteText(content)
    } catch { /* AI optional */ }
    finally { aiLoading.value = false }
  }

  async function generateSectionAi(section: 'designation' | 'note'): Promise<void> {
    if (opts.isReadonly.value) return
    sectionAiLoading.value = { ...sectionAiLoading.value, [section]: true }
    try {
      const existing = section === 'designation' ? store.value.designationText : noteText.value
      const res = await api.post(
        `/api/workpapers/${opts.wpId.value}/g8/ai/disclosure-section`,
        {
          existingContent: existing,
          relatedContext: {
            section,
            variant: opts.variant,
            balanceClosing: primaryCurrentAmount.value,
            designationHint: designationHint.value,
          },
        },
        { _silent: true } as any,
      )
      const content = res?.data?.content ?? res?.content ?? ''
      if (content) {
        if (section === 'designation') updateDesignation(content)
        else updateNoteText(content)
      }
    } catch { /* AI optional */ }
    finally {
      sectionAiLoading.value = { ...sectionAiLoading.value, [section]: false }
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

  const hasContent = computed(() => disclosureStoreHasContent(store.value))

  const otherVariantLabel = computed(() =>
    opts.variant === 'listed' ? '附注披露信息（国企）' : '附注披露信息（上市公司）',
  )

  const otherVariantHasContent = computed(() => {
    const otherKey = opts.variant === 'listed' ? 'G8-disclosure-soe' : 'G8-disclosure-listed'
    const otherVariant = opts.variant === 'listed' ? 'soe' : 'listed'
    return g8DisclosureRemarkHasContent(
      opts.allResponses.value.get(otherKey)?.remark,
      otherVariant,
    )
  })

  const completenessGaps = computed(() => {
    const gaps: string[] = []
    if (!(store.value.designationText || '').trim()) gaps.push('指定原因未填')
    if (adjudicatedAmount.value == null) gaps.push('尚未发布 G8-1 审定数')
    else if (hasAdjCrossMismatch.value) gaps.push('余额合计与审定数未勾稽')
    return gaps
  })

  return {
    title,
    introText,
    designationHint,
    designationPlaceholder,
    section2Title,
    store,
    balanceRows,
    ociRows,
    detailRows,
    noteText,
    designationText: computed(() => store.value.designationText),
    adjudicatedAmount,
    primaryCurrentAmount,
    adjCrossVariance,
    hasAdjCrossMismatch,
    hasContent,
    otherVariantLabel,
    otherVariantHasContent,
    completenessGaps,
    aiLoading,
    sectionAiLoading,
    updateBalance,
    updateDesignation,
    updateOci,
    updateDetail,
    updateNoteText,
    pullLatestAdjudicated,
    syncFromDetail,
    syncDesignationOnly,
    generateAiConclusion,
    generateSectionAi,
  }
}
