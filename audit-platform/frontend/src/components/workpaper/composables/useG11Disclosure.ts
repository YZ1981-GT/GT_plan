/**
 * useG11Disclosure — 附注披露（上市/国企）
 * G11-2 明细优先 → G11-1 审定分项 → 残差进「其他」；上市含处置交易性子表；国企含汇回限制说明。
 */
import { ref, computed, watch, onMounted, onBeforeUnmount, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { G11_ACCOUNT_CODE } from './g11Constants'
import { parseNum, calcChangeAmount, calcChangeRate } from './useG11FormulaEngine'
import {
  G11_ADJUDICATED_KEY,
  G11_CROSS_TOLERANCE,
  G11_DISCLOSURE_COL_LABELS,
  G11_LISTED_TRADING_DISPOSE_ROWS,
  G11_SOE_REPATRIATION_PLACEHOLDER,
  G11_TRADING_DISPOSE_HINT,
  G11_TRADING_DISPOSE_SUFFIXES,
  type G11TradingDisposeSuffix,
} from './g11SchemaRows'
import {
  computeG11DisclosurePull,
  parseG11DiscStore,
  buildG11TradingDisposeFromDetailRows,
  sumG11DisclosureLeafCurrent,
  sumG11DisclosureLeafPrior,
  sumG11TradingDisposeCurrent,
  defaultG11TradingDisposeMap,
  type G11DiscStoreV2,
  type G11TradingDisposeMap,
} from './g11DisclosureFromAdj'
import type { ChecklistResponse } from './useF1FormData'
import { api } from '@/services/apiProxy'
import { buildG11NoteTextFromStore } from './g11NoteText'
import { G11_NOTE_SECTION } from './g11NoteSectionMap'
import type { G11SyncSnapshot } from './g11DisclosureSyncPayload'

export interface G11DisclosureRow {
  rowKey: string
  label: string
  currentAmount: number
  priorAmount: number
  changeAmount: number
  changeRate: number | null
  remark: string
}

function enrichRow(raw: Partial<G11DisclosureRow> & { rowKey: string; label?: string }): G11DisclosureRow {
  const currentAmount = parseNum(raw.currentAmount)
  const priorAmount = parseNum(raw.priorAmount)
  return {
    rowKey: raw.rowKey,
    label: raw.label ?? raw.rowKey,
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

  const store = ref<G11DiscStoreV2>(parseG11DiscStore(undefined, variant))
  const noteText = ref('')
  const adjudicatedAmount = ref<number | null>(null)
  const aiLoading = ref(false)
  const pullSummary = ref('')
  const lastPullUsedResidual = ref(false)
  const lastPulledAdjAmount = ref<number | null>(null)

  const title = computed(() =>
    variant === 'listed' ? '附注披露信息（上市公司）' : '附注披露信息（国企）',
  )

  const colLabels = computed(() => G11_DISCLOSURE_COL_LABELS[variant])

  const rows = computed({
    get: () => store.value.rows.map((r) => enrichRow(r)),
    set: (v: G11DisclosureRow[]) => {
      store.value = { ...store.value, rows: v.map((r) => ({
        rowKey: r.rowKey,
        label: r.label,
        currentAmount: r.currentAmount,
        priorAmount: r.priorAmount,
        remark: r.remark,
      })) }
    },
  })

  const tradingDisposeMap = computed(() =>
    store.value.tradingDispose ?? defaultG11TradingDisposeMap(),
  )

  const repatriationNote = computed({
    get: () => store.value.repatriationNote ?? (variant === 'soe' ? G11_SOE_REPATRIATION_PLACEHOLDER : ''),
    set: (v: string) => {
      store.value = { ...store.value, repatriationNote: v }
    },
  })

  function loadFromStore(): void {
    store.value = parseG11DiscStore(options.allResponses.value.get(itemId)?.remark, variant)
    noteText.value = options.allResponses.value.get(noteItemId)?.conclusion ?? ''
    const adj = options.allResponses.value.get(G11_ADJUDICATED_KEY)?.conclusion
    if (adj != null && adj !== '') adjudicatedAmount.value = parseNum(adj)
  }

  watch(() => options.allResponses.value, loadFromStore, { deep: true, immediate: true })

  const disclosureCurrentSum = computed(() => sumG11DisclosureLeafCurrent(store.value.rows))
  const disclosurePriorSum = computed(() => sumG11DisclosureLeafPrior(store.value.rows))

  const adjCrossVariance = computed(() => {
    if (adjudicatedAmount.value == null) return null
    return disclosureCurrentSum.value - adjudicatedAmount.value
  })

  const hasAdjCrossMismatch = computed(() =>
    adjCrossVariance.value != null && Math.abs(adjCrossVariance.value) > G11_CROSS_TOLERANCE,
  )

  const adjChangedSincePull = computed(() => {
    if (adjudicatedAmount.value == null || lastPulledAdjAmount.value == null) return false
    return Math.abs(adjudicatedAmount.value - lastPulledAdjAmount.value) > G11_CROSS_TOLERANCE
  })

  const tradingDisposeRows = computed(() => {
    const map = tradingDisposeMap.value
    return G11_LISTED_TRADING_DISPOSE_ROWS.map((def) => {
      const pair = map[def.rowKey as G11TradingDisposeSuffix] ?? { currentAmount: 0, priorAmount: 0 }
      return enrichRow({
        rowKey: def.rowKey,
        label: def.label,
        currentAmount: pair.currentAmount,
        priorAmount: pair.priorAmount,
        remark: '',
      })
    })
  })

  const tradingDisposeDisplayRows = computed(() => {
    const data = tradingDisposeRows.value
    const currentAmount = sumG11TradingDisposeCurrent(tradingDisposeMap.value)
    const priorAmount = calcSubtotalPrior(tradingDisposeMap.value)
    return [
      ...data,
      {
        rowKey: 'total',
        label: '合  计',
        currentAmount,
        priorAmount,
        changeAmount: calcChangeAmount(currentAmount, priorAmount),
        changeRate: calcChangeRate(priorAmount, currentAmount),
        remark: '',
      },
    ]
  })

  function calcSubtotalPrior(map: G11TradingDisposeMap): number {
    return G11_TRADING_DISPOSE_SUFFIXES.reduce((s, k) => s + parseNum(map[k]?.priorAmount), 0)
  }

  const tradingDisposeMainAmount = computed(() => {
    const row = store.value.rows.find((r) => r.rowKey === 'trading_dispose')
    return parseNum(row?.currentAmount)
  })

  const tradingDisposeCrossVariance = computed(() => {
    if (variant !== 'listed') return null
    const sub = sumG11TradingDisposeCurrent(tradingDisposeMap.value)
    if (Math.abs(sub) < G11_CROSS_TOLERANCE && Math.abs(tradingDisposeMainAmount.value) < G11_CROSS_TOLERANCE) {
      return null
    }
    if (Math.abs(sub) < G11_CROSS_TOLERANCE) return null // 子表未填时不告警
    return sub - tradingDisposeMainAmount.value
  })

  const hasTradingDisposeMismatch = computed(() =>
    tradingDisposeCrossVariance.value != null
    && Math.abs(tradingDisposeCrossVariance.value) > G11_CROSS_TOLERANCE,
  )

  const displayRows = computed(() => {
    const data = rows.value
    const currentAmount = disclosureCurrentSum.value
    const priorAmount = disclosurePriorSum.value
    const total = {
      rowKey: 'total',
      label: '合  计',
      currentAmount,
      priorAmount,
      changeAmount: calcChangeAmount(currentAmount, priorAmount),
      changeRate: calcChangeRate(priorAmount, currentAmount),
      remark: '',
    }
    return [...data, total]
  })

  function persist(): void {
    options.debouncedSave(itemId, { remark: JSON.stringify(store.value) })
  }

  function updateField(rowKey: string, field: 'currentAmount' | 'priorAmount' | 'remark', value: unknown): void {
    if (options.isReadonly.value || rowKey === 'total') return
    store.value = {
      ...store.value,
      rows: store.value.rows.map((r) => {
        if (r.rowKey !== rowKey) return r
        if (field === 'remark') return { ...r, remark: String(value ?? '') }
        return { ...r, [field]: parseNum(value) }
      }),
    }
    persist()
    publishNoteDebounced()
  }

  function updateTradingDisposeField(
    rowKey: string,
    field: 'currentAmount' | 'priorAmount',
    value: unknown,
  ): void {
    if (options.isReadonly.value || variant !== 'listed' || rowKey === 'total') return
    const key = rowKey as G11TradingDisposeSuffix
    if (!G11_TRADING_DISPOSE_SUFFIXES.includes(key)) return
    const map = { ...tradingDisposeMap.value }
    map[key] = {
      ...map[key],
      [field]: parseNum(value),
    }
    store.value = { ...store.value, tradingDispose: map }
    persist()
  }

  function updateRepatriationNote(value: string): void {
    if (options.isReadonly.value || variant !== 'soe') return
    store.value = { ...store.value, repatriationNote: value }
    persist()
  }

  function updateNoteText(value: string): void {
    if (options.isReadonly.value) return
    noteText.value = value
    options.debouncedSave(noteItemId, { conclusion: value })
    publishNoteDebounced()
  }

  let noteTimer: ReturnType<typeof setTimeout> | null = null
  function publishNoteUpdate(): void {
    try {
      window.dispatchEvent(new CustomEvent('disclosure:note-text-updated', {
        detail: {
          wpCode: 'G11',
          accountCode: G11_ACCOUNT_CODE,
          section: variant,
          sectionId: G11_NOTE_SECTION[variant],
          variant,
          wpId: options.wpId.value,
          text: noteText.value,
          currentAmount: disclosureCurrentSum.value,
          timestamp: Date.now(),
        },
      }))
    } catch { /* silent */ }
  }

  function publishNoteDebounced(): void {
    if (noteTimer) clearTimeout(noteTimer)
    noteTimer = setTimeout(() => {
      noteTimer = null
      publishNoteUpdate()
    }, 2000)
  }

  function generateNoteFromStore(overwrite = true): string {
    const built = buildG11NoteTextFromStore(store.value, variant, {
      adjudicatedAmount: adjudicatedAmount.value,
    })
    if (built && (overwrite || !noteText.value.trim())) {
      updateNoteText(built)
    } else if (built) {
      publishNoteUpdate()
    }
    return built
  }

  function handleAdjudicated(e: Event): void {
    const detail = (e as CustomEvent).detail
    if (detail?.accountCode === G11_ACCOUNT_CODE) {
      adjudicatedAmount.value = parseNum(detail.adjudicatedAmount)
    }
  }

  function onDisclosurePulled(ev: Event): void {
    const detail = (ev as CustomEvent<{ usedResidual?: boolean; summary?: string }>).detail
    if (detail?.summary) pullSummary.value = detail.summary
    if (detail?.usedResidual != null) lastPullUsedResidual.value = detail.usedResidual
    loadFromStore()
    const adj = options.allResponses.value.get(G11_ADJUDICATED_KEY)?.conclusion
    if (adj != null && adj !== '') lastPulledAdjAmount.value = parseNum(adj)
  }

  function pullLatestAdjudicated(writeCategories = false): void {
    const adj = options.allResponses.value.get(G11_ADJUDICATED_KEY)?.conclusion
    if (adj != null && adj !== '') adjudicatedAmount.value = parseNum(adj)
    if (writeCategories) pullFromAdjudication()
  }

  /** G11-2 明细优先，否则 G11-1 分项；无分项则残差进「其他」；上市顺带尝试灌处置交易性子表 */
  function pullFromAdjudication(): void {
    if (options.isReadonly.value) return
    const adj = options.allResponses.value.get(G11_ADJUDICATED_KEY)?.conclusion
    if (adj != null && adj !== '') adjudicatedAmount.value = parseNum(adj)

    const result = computeG11DisclosurePull(options.allResponses.value, store.value.rows, variant)
    let tradingDispose = store.value.tradingDispose
    let tdFilled = 0
    if (variant === 'listed') {
      try {
        const raw = options.allResponses.value.get('G11-detail-rows')?.remark
        const detailRows = raw ? JSON.parse(raw) : []
        const td = buildG11TradingDisposeFromDetailRows(Array.isArray(detailRows) ? detailRows : [])
        if (td.filled.length > 0) {
          tradingDispose = td.amounts
          tdFilled = td.filled.length
        }
      } catch { /* ignore */ }
    }

    store.value = {
      ...store.value,
      rows: result.next,
      tradingDispose: variant === 'listed' ? (tradingDispose ?? defaultG11TradingDisposeMap()) : undefined,
      repatriationNote: variant === 'soe'
        ? (store.value.repatriationNote?.trim() || G11_SOE_REPATRIATION_PLACEHOLDER)
        : undefined,
    }
    lastPulledAdjAmount.value = adjudicatedAmount.value
    lastPullUsedResidual.value = result.usedResidual
    pullSummary.value = tdFilled > 0
      ? `${result.summary}；处置交易性明细 ${tdFilled} 类←G11-2`
      : result.summary
    persist()
    if (!noteText.value.trim()) {
      generateNoteFromStore(true)
    } else {
      publishNoteDebounced()
    }

    if (result.usedResidual) {
      ElMessage.warning(pullSummary.value)
    } else if (result.filledKeys.length === 0 && tdFilled === 0) {
      ElMessage.info('暂无可带入分项：请在 G11-2 填写项目名称，或在 G11-1 填写各投资收益分项')
    } else {
      ElMessage.success(`已带入 ${result.filledKeys.length} 项：${pullSummary.value}`)
    }
  }

  async function generateAiConclusion(): Promise<void> {
    if (options.isReadonly.value) return
    aiLoading.value = true
    try {
      const res = await api.post(
        `/api/workpapers/${options.wpId.value}/g11/ai/disclosure-note`,
        {
          variant,
          existingContent: noteText.value,
          rows: store.value.rows.slice(0, 20),
          relatedContext: {
            adjudicatedAmount: adjudicatedAmount.value,
            disclosureCurrentSum: disclosureCurrentSum.value,
            disclosurePriorSum: disclosurePriorSum.value,
            tradingDispose: variant === 'listed' ? store.value.tradingDispose : undefined,
            repatriationNote: variant === 'soe' ? store.value.repatriationNote : undefined,
          },
        },
        { _silent: true } as any,
      )
      const text = res?.data?.data?.content ?? res?.data?.content ?? res?.content ?? ''
      if (text) updateNoteText(text)
    } catch { /* AI optional */ }
    finally { aiLoading.value = false }
  }

  function getSyncSnapshot(auditNote = '', auditConclusion = ''): G11SyncSnapshot {
    return {
      store: { ...store.value },
      noteText: noteText.value,
      auditNote,
      auditConclusion,
    }
  }

  onMounted(() => {
    window.addEventListener('substantive:adjudicated', handleAdjudicated)
    window.addEventListener('g11:disclosure-pulled', onDisclosurePulled)
    pullLatestAdjudicated(false)
    publishNoteUpdate()
  })
  onBeforeUnmount(() => {
    window.removeEventListener('substantive:adjudicated', handleAdjudicated)
    window.removeEventListener('g11:disclosure-pulled', onDisclosurePulled)
    if (noteTimer) clearTimeout(noteTimer)
  })

  return {
    title,
    colLabels,
    rows,
    displayRows,
    noteText,
    adjudicatedAmount,
    disclosureCurrentSum,
    disclosurePriorSum,
    adjCrossVariance,
    hasAdjCrossMismatch,
    adjChangedSincePull,
    pullSummary,
    lastPullUsedResidual,
    tradingDisposeDisplayRows,
    tradingDisposeHint: G11_TRADING_DISPOSE_HINT,
    hasTradingDisposeMismatch,
    tradingDisposeCrossVariance,
    tradingDisposeMainAmount,
    repatriationNote,
    aiLoading,
    updateField,
    updateTradingDisposeField,
    updateRepatriationNote,
    updateNoteText,
    pullLatestAdjudicated,
    pullFromAdjudication,
    clearPullSummary: () => { pullSummary.value = '' },
    generateAiConclusion,
    generateNoteFromStore,
    getSyncSnapshot,
  }
}
