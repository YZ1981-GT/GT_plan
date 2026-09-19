/**
 * useG14Disclosure — 附注披露（上市 9+合计 / 国企 4+合计）
 *
 * 上市/国企模板：「不存在的项目可以删除」——无发生额行默认不展示、不进附注正文；
 * 与附注模块：EventBus sectionId + sync-from-workpaper 结构化子表（空行不推送）。
 */
import { ref, computed, watch, onMounted, onBeforeUnmount, type Ref } from 'vue'
import { parseNum, calcChangeAmount, calcChangeRate } from './useG14FormulaEngine'
import {
  G14_ACCOUNT_CODE,
  G14_DISCLOSURE_LISTED_ROWS,
  G14_DISCLOSURE_SOE_ROWS,
  G14_DISCLOSURE_TEMPLATE_HINT,
  G14_SOE_BAD_DEBT_SOURCES,
  G14_SOE_OTHER_EXTRA_SOURCES,
} from './g14Constants'
import {
  filterG14DisclosureRows,
  g14DisclosureHasAnyAmount,
} from './g14DisclosureVisibility'
import { buildG14NoteTextFromRows } from './g14NoteText'
import { G14_NOTE_SECTION } from './g14NoteSectionMap'
import type { G14SyncSnapshot } from './g14DisclosureSyncPayload'
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

function sumDetailAudited(detailRows: any[], keys: readonly string[]): number {
  return detailRows
    .filter((d) => keys.includes(d.rowKey))
    .reduce((s, d) => s + parseNum(d.currentAudited), 0)
}

function priorAuditedFromStoreEntry(entry: Record<string, unknown> | null | undefined): number {
  if (!entry) return 0
  const direct = parseNum(entry.priorAudited)
  if (Math.abs(direct) > 0.0001) return direct
  return parseNum(entry.priorUnadjusted) + parseNum(entry.priorAdjustment)
}

function sumPriorStore(store: Record<string, any>, keys: readonly string[]): number {
  return keys.reduce((s, k) => s + priorAuditedFromStoreEntry(store[k]), 0)
}

export function useG14Disclosure(options: {
  variant: 'listed' | 'soe'
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  wpId: Ref<string>
  isReadonly: Ref<boolean>
  projectId?: Ref<string>
}) {
  const variant = options.variant
  const itemId = variant === 'listed' ? 'G14-disclosure-listed' : 'G14-disclosure-soe'
  const noteItemId = `${itemId}-note`
  const prefsItemId = `${itemId}-prefs`
  const noteSectionId = G14_NOTE_SECTION[variant]

  const rows = ref<G14DisclosureRow[]>(defaultRows(variant))
  const noteText = ref('')
  const adjudicatedAmount = ref<number | null>(null)
  const aiLoading = ref(false)
  /** 强制显示模板空行（编制期补数）；有数据后默认隐藏空项 */
  const showEmptyRows = ref(false)

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

  function loadPrefs(): void {
    const raw = options.allResponses.value.get(prefsItemId)?.remark
    if (!raw) return
    try {
      const parsed = JSON.parse(raw)
      if (typeof parsed?.showEmptyRows === 'boolean') {
        showEmptyRows.value = parsed.showEmptyRows
      }
    } catch { /* ignore */ }
  }

  watch(() => options.allResponses.value.get(itemId)?.remark, loadFromStore, { immediate: true })
  watch(() => options.allResponses.value.get(prefsItemId)?.remark, loadPrefs, { immediate: true })
  watch(() => options.allResponses.value.get(noteItemId)?.remark, (v) => {
    if (v != null) noteText.value = v
  }, { immediate: true })

  const totalRow = computed(() => {
    const currentAmount = rows.value.reduce((s, r) => s + r.currentAmount, 0)
    const priorAmount = rows.value.reduce((s, r) => s + r.priorAmount, 0)
    return enrichRow({ rowKey: 'total', label: '合  计', currentAmount, priorAmount, remark: '' }, variant)
  })

  /** 空表仍展示全部模板行，便于录入；有数据后默认省略空项 */
  const includeEmptyInDisplay = computed(() =>
    showEmptyRows.value || !g14DisclosureHasAnyAmount(rows.value),
  )

  const visibleDataRows = computed(() =>
    filterG14DisclosureRows(rows.value, { includeEmpty: includeEmptyInDisplay.value }),
  )

  const displayRows = computed(() => [...visibleDataRows.value, totalRow.value])

  /** 附注模块用：始终省略空行（不受「显示空项」开关影响） */
  const noteDataRows = computed(() =>
    filterG14DisclosureRows(rows.value, { includeEmpty: false }),
  )

  const hiddenEmptyCount = computed(() => {
    if (includeEmptyInDisplay.value) return 0
    return Math.max(0, rows.value.length - visibleDataRows.value.length)
  })

  const autoNoteDraft = computed(() =>
    buildG14NoteTextFromRows(
      rows.value.map((r) => ({
        rowKey: r.rowKey,
        label: r.label,
        currentAmount: r.currentAmount,
        priorAmount: r.priorAmount,
        remark: r.remark,
      })),
      variant,
      { adjudicatedAmount: adjudicatedAmount.value },
    ),
  )

  function persistPrefs(): void {
    options.debouncedSave(prefsItemId, {
      remark: JSON.stringify({ showEmptyRows: showEmptyRows.value }),
    })
  }

  let noteTimer: ReturnType<typeof setTimeout> | null = null

  function publishNoteUpdate(): void {
    window.dispatchEvent(new CustomEvent('disclosure:note-text-updated', {
      detail: {
        wpCode: 'G14',
        accountCode: G14_ACCOUNT_CODE,
        section: variant,
        sectionId: noteSectionId,
        sectionIds: [noteSectionId],
        variant,
        wpId: options.wpId.value,
        projectId: options.projectId?.value ?? '',
        text: noteText.value,
        rows: noteDataRows.value.map((r) => ({
          rowKey: r.rowKey,
          label: r.label,
          currentAmount: r.currentAmount,
          priorAmount: r.priorAmount,
        })),
        currentAmount: totalRow.value.currentAmount,
        priorAmount: totalRow.value.priorAmount,
        templateHintExcluded: G14_DISCLOSURE_TEMPLATE_HINT,
        timestamp: Date.now(),
      },
    }))
  }

  function publishNoteDebounced(): void {
    if (noteTimer) clearTimeout(noteTimer)
    noteTimer = setTimeout(() => {
      noteTimer = null
      publishNoteUpdate()
    }, 2000)
  }

  function persist(): void {
    options.debouncedSave(itemId, {
      remark: JSON.stringify(rows.value.map((r) => ({
        rowKey: r.rowKey, label: r.label, currentAmount: r.currentAmount,
        priorAmount: r.priorAmount, remark: r.remark,
      }))),
    })
    options.debouncedSave(noteItemId, { remark: noteText.value })
    publishNoteDebounced()
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

  function setShowEmptyRows(val: boolean): void {
    showEmptyRows.value = val
    persistPrefs()
  }

  function applyAutoNoteDraft(): void {
    if (options.isReadonly.value) return
    noteText.value = autoNoteDraft.value
    persist()
  }

  function getSyncSnapshot(): G14SyncSnapshot {
    return {
      rows: rows.value.map((r) => ({
        rowKey: r.rowKey,
        label: r.label,
        currentAmount: r.currentAmount,
        priorAmount: r.priorAmount,
        remark: r.remark,
      })),
      noteText: noteText.value,
      adjudicatedAmount: adjudicatedAmount.value,
    }
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
        const badDebt = sumDetailAudited(detailRows, G14_SOE_BAD_DEBT_SOURCES)
        const otherExtra = sumDetailAudited(detailRows, G14_SOE_OTHER_EXTRA_SOURCES)
        rows.value = rows.value.map((r) => {
          if (r.rowKey === 'bad_debt') {
            return enrichRow({ ...r, currentAmount: badDebt }, variant)
          }
          if (r.rowKey === 'other') {
            const hit = detailRows.find((d) => d.rowKey === 'other')
            return enrichRow({
              ...r,
              currentAmount: parseNum(hit?.currentAudited) + otherExtra,
            }, variant)
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
    const amt = options.allResponses.value.get('G14-1-adjudicated-amount')?.conclusion
    if (amt != null) {
      adjudicatedAmount.value = parseNum(amt)
    } else {
      const tb = options.allResponses.value.get('G14-adj-tb')?.remark
      if (tb != null) adjudicatedAmount.value = parseNum(tb)
    }
    syncFromDetail()
    const prior = options.allResponses.value.get('G14-adj-prior')
    if (prior?.remark) {
      try {
        const store = JSON.parse(prior.remark) as Record<string, any>
        if (variant === 'listed') {
          rows.value = rows.value.map((r) => {
            const p = store[r.rowKey]
            return p ? enrichRow({ ...r, priorAmount: priorAuditedFromStoreEntry(p) }, variant) : r
          })
        } else {
          const badDebtPrior = sumPriorStore(store, G14_SOE_BAD_DEBT_SOURCES)
          const otherExtraPrior = sumPriorStore(store, G14_SOE_OTHER_EXTRA_SOURCES)
          rows.value = rows.value.map((r) => {
            if (r.rowKey === 'bad_debt') {
              return enrichRow({ ...r, priorAmount: badDebtPrior }, variant)
            }
            if (r.rowKey === 'other') {
              return enrichRow({
                ...r,
                priorAmount: priorAuditedFromStoreEntry(store.other) + otherExtraPrior,
              }, variant)
            }
            const p = store[r.rowKey]
            return p ? enrichRow({ ...r, priorAmount: priorAuditedFromStoreEntry(p) }, variant) : r
          })
        }
        persist()
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
          relatedContext: {
            rows: noteDataRows.value,
            total: totalRow.value.currentAmount,
            adjudicatedAmount: adjudicatedAmount.value,
            templateHint: G14_DISCLOSURE_TEMPLATE_HINT,
            noteSectionId,
          },
        },
        { _silent: true } as any,
      )
      const content = res?.data?.content ?? res?.content ?? ''
      if (content) { noteText.value = content; persist() }
    } catch {
      noteText.value = autoNoteDraft.value
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
    window.addEventListener('g14:detail-updated', onDetailUpdated)
    publishNoteUpdate()
  })
  onBeforeUnmount(() => {
    window.removeEventListener('substantive:adjudicated', handleAdjudicated)
    window.removeEventListener('g14:detail-updated', onDetailUpdated)
    if (noteTimer) clearTimeout(noteTimer)
  })

  function onDetailUpdated(): void {
    syncFromDetail()
  }

  return {
    rows,
    displayRows,
    visibleDataRows,
    noteDataRows,
    totalRow,
    noteText,
    autoNoteDraft,
    adjudicatedAmount,
    aiLoading,
    title,
    showEmptyRows,
    hiddenEmptyCount,
    includeEmptyInDisplay,
    noteSectionId,
    templateHint: G14_DISCLOSURE_TEMPLATE_HINT,
    updateField,
    updateNoteText,
    setShowEmptyRows,
    applyAutoNoteDraft,
    regenerateNoteFromRows: applyAutoNoteDraft,
    generateAiConclusion,
    pullLatestAdjudicated,
    syncFromDetail,
    getSyncSnapshot,
    publishNoteUpdate,
  }
}
