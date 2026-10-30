/**
 * useG13Disclosure — 附注披露（上市 9+合计 / 国企 7+合计 × 5 列）
 *
 * 上市模板：「不存在的项目可以删除」——无发生额行默认不展示、不进附注正文；
 * 「其中」挂靠主行，主行不存在时子行一并省略。
 * 与附注模块：EventBus sectionId + sync-from-workpaper 结构化子表（空行不推送）。
 */
import { ref, computed, watch, onMounted, onBeforeUnmount, getCurrentInstance, type Ref } from 'vue'
import { parseNum, calcChangeAmount, calcChangeRate } from './useG13FormulaEngine'
import {
  G13_ACCOUNT_CODE,
  G13_DISCLOSURE_LISTED_ROWS,
  G13_DISCLOSURE_SOE_ROWS,
  G13_DISCLOSURE_TEMPLATE_HINT,
  G13_DETAIL_TO_DISCLOSURE,
  G13_ADJ_TO_DISCLOSURE_LISTED,
  mapBelongToAdjRow,
  mapBelongToOfWhichRow,
  type G13DisclosureRowDef,
} from './g13Constants'
import {
  filterG13DisclosureRows,
  g13DisclosureHasAnyAmount,
} from './g13DisclosureVisibility'
import { buildG13NoteTextFromRows } from './g13NoteText'
import { G13_NOTE_SECTION } from './g13NoteSectionMap'
import type { G13SyncSnapshot } from './g13DisclosureSyncPayload'
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

export interface G13DisclosurePatchResult {
  changed: boolean
  sourceFound: boolean
  fieldsChanged: number
}

interface AmountSource {
  found: boolean
  value: number
}

const MISSING_AMOUNT: AmountSource = { found: false, value: 0 }

function amountSource(value: unknown): AmountSource {
  if (value == null || (typeof value === 'string' && value.trim() === '')) return MISSING_AMOUNT
  const parsed = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(parsed) ? { found: true, value: parsed } : MISSING_AMOUNT
}

function priorAmountSource(entry: unknown): AmountSource {
  if (!entry || typeof entry !== 'object' || Array.isArray(entry)) return MISSING_AMOUNT
  const value = entry as Record<string, unknown>
  const audited = amountSource(value.priorAudited)
  if (audited.found) return audited

  const unadjusted = amountSource(value.priorUnadjusted)
  const adjustment = amountSource(value.priorAdjustment)
  if (!unadjusted.found && !adjustment.found) return MISSING_AMOUNT
  return { found: true, value: unadjusted.value + adjustment.value }
}

function emptyPatchResult(): G13DisclosurePatchResult {
  return { changed: false, sourceFound: false, fieldsChanged: 0 }
}

function mergePatchResults(...results: G13DisclosurePatchResult[]): G13DisclosurePatchResult {
  const fieldsChanged = results.reduce((total, result) => total + result.fieldsChanged, 0)
  return {
    changed: fieldsChanged > 0,
    sourceFound: results.some((result) => result.sourceFound),
    fieldsChanged,
  }
}

function rowDefs(variant: 'listed' | 'soe'): readonly G13DisclosureRowDef[] {
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
  projectId?: Ref<string>
}) {
  const variant = options.variant
  const itemId = variant === 'listed' ? 'G13-disclosure-listed' : 'G13-disclosure-soe'
  const noteItemId = `${itemId}-note`
  const prefsItemId = `${itemId}-prefs`
  const noteSectionId = G13_NOTE_SECTION[variant]

  const rows = ref<G13DisclosureRow[]>(defaultRows(variant))
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

  const defs = computed(() => rowDefs(variant))

  const totalRow = computed(() => {
    const includable = new Set(
      defs.value.filter((d) => !d.ofWhich).map((d) => d.rowKey),
    )
    const currentAmount = rows.value
      .filter((r) => includable.has(r.rowKey))
      .reduce((s, r) => s + r.currentAmount, 0)
    const priorAmount = rows.value
      .filter((r) => includable.has(r.rowKey))
      .reduce((s, r) => s + r.priorAmount, 0)
    return enrichRow({ rowKey: 'total', label: '合  计', currentAmount, priorAmount, remark: '' }, variant)
  })

  /** 空表仍展示全部模板行，便于录入；有数据后默认省略空项 */
  const includeEmptyInDisplay = computed(() =>
    showEmptyRows.value || !g13DisclosureHasAnyAmount(rows.value),
  )

  const visibleDataRows = computed(() =>
    filterG13DisclosureRows(rows.value, defs.value, {
      includeEmpty: includeEmptyInDisplay.value,
    }),
  )

  const displayRows = computed(() => [...visibleDataRows.value, totalRow.value])

  /** 附注模块用：始终省略空行（不受「显示空项」开关影响） */
  const noteDataRows = computed(() =>
    filterG13DisclosureRows(rows.value, defs.value, { includeEmpty: false }),
  )

  const hiddenEmptyCount = computed(() => {
    if (includeEmptyInDisplay.value) return 0
    return Math.max(0, rows.value.length - visibleDataRows.value.length)
  })

  const autoNoteDraft = computed(() =>
    buildG13NoteTextFromRows(
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
        wpCode: 'G13',
        accountCode: G13_ACCOUNT_CODE,
        section: variant,
        sectionId: noteSectionId,
        sectionIds: [noteSectionId],
        variant,
        wpId: options.wpId.value,
        projectId: options.projectId?.value ?? '',
        text: noteText.value,
        /** 附注模块只收有发生额的分项，不含模板提示与空行 */
        rows: noteDataRows.value.map((r) => ({
          rowKey: r.rowKey,
          label: r.label,
          currentAmount: r.currentAmount,
          priorAmount: r.priorAmount,
        })),
        currentAmount: totalRow.value.currentAmount,
        priorAmount: totalRow.value.priorAmount,
        templateHintExcluded: G13_DISCLOSURE_TEMPLATE_HINT,
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

  function setShowEmptyRows(val: boolean): void {
    showEmptyRows.value = val
    persistPrefs()
  }

  /** 用当前可见分项覆盖附注说明（不含空行与编制提示） */
  function applyAutoNoteDraft(): void {
    if (options.isReadonly.value) return
    noteText.value = autoNoteDraft.value
    persist()
  }

  function getSyncSnapshot(): G13SyncSnapshot {
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

  function applyAmountPatch(
    field: 'currentAmount' | 'priorAmount',
    amounts: Map<string, number>,
  ): G13DisclosurePatchResult {
    let sourceFound = false
    let fieldsChanged = 0
    const patchedRows = rows.value.map((row) => {
      if (!amounts.has(row.rowKey)) return row
      sourceFound = true
      const amount = amounts.get(row.rowKey)!
      if (row[field] === amount) return row
      fieldsChanged += 1
      return enrichRow({ ...row, [field]: amount }, variant)
    })
    if (fieldsChanged > 0) rows.value = patchedRows
    return { changed: fieldsChanged > 0, sourceFound, fieldsChanged }
  }

  function persistPatch(result: G13DisclosurePatchResult, enabled = true): void {
    if (enabled && result.sourceFound && result.changed && !options.isReadonly.value) {
      persist()
    }
  }

  /** 「从明细同步」：仅在来源存在、值变化且可写时保存本期回填。 */
  function syncFromDetail(): G13DisclosurePatchResult {
    const result = applyDetailPatch()
    persistPatch(result)
    return result
  }

  /** 由 G13-2 明细按来源汇总本期发生额；缺字段或缺行保留已存值，明确 0 有效。 */
  function applyDetailPatch(): G13DisclosurePatchResult {
    const detailJson = options.allResponses.value.get('G13-detail-rows')?.remark
    if (!detailJson) return emptyPatchResult()
    try {
      const detailRows = JSON.parse(detailJson) as any[]
      if (!Array.isArray(detailRows)) return emptyPatchResult()
      const sums = new Map<string, number>()
      let hasAmountSource = false
      for (const d of detailRows) {
        const audited = amountSource(d?.currentAudited)
        const amount = audited.found ? audited : amountSource(d?.fvChange)
        if (!amount.found) continue
        hasAmountSource = true

        const belong = String(d.belongAccount ?? '')
        const instrumentType = String(d.instrumentType ?? '')
        const remark = String(d.remark ?? '')

        const adjKey = mapBelongToAdjRow(belong, instrumentType)
        let discKey: string
        if (variant === 'listed') {
          discKey = G13_ADJ_TO_DISCLOSURE_LISTED[adjKey] ?? G13_DETAIL_TO_DISCLOSURE[belong] ?? 'other'
        } else if (belong === 'G9') {
          discKey = /负债/.test(instrumentType) ? 'derivative_liabilities' : 'derivative_assets'
        } else if (belong === 'G10' && /衍生/.test(instrumentType)) {
          discKey = 'derivative_liabilities'
        } else {
          discKey = G13_DETAIL_TO_DISCLOSURE[belong] ?? 'other'
          if (discKey === 'derivatives') discKey = 'derivative_assets'
        }
        sums.set(discKey, (sums.get(discKey) ?? 0) + amount.value)

        if (variant === 'listed') {
          const ofWhichAdj = mapBelongToOfWhichRow(belong, instrumentType, remark)
          if (ofWhichAdj) {
            const ofWhichDisc = G13_ADJ_TO_DISCLOSURE_LISTED[ofWhichAdj] ?? ofWhichAdj
            sums.set(ofWhichDisc, (sums.get(ofWhichDisc) ?? 0) + amount.value)
          }
        }
      }

      // 一旦明细里至少有一项可解释的金额，它就是本期完整来源；上市“其中”备忘行
      // 没命中表示明确为 0。若所有来源行都缺金额，则仍按“来源不存在”保留已存值。
      if (variant === 'listed' && hasAmountSource) {
        for (const definition of rowDefs(variant)) {
          if (definition.ofWhich && !sums.has(definition.rowKey)) sums.set(definition.rowKey, 0)
        }
      }

      return applyAmountPatch('currentAmount', sums)
    } catch {
      return emptyPatchResult()
    }
  }

  /** 由 G13-1 上期审定回填上期发生额；显式 priorAudited=0 不回退到旧分量。 */
  function applyPriorPatch(): G13DisclosurePatchResult {
    const prior = options.allResponses.value.get('G13-adj-prior')?.remark
    if (!prior) return emptyPatchResult()
    try {
      const store = JSON.parse(prior) as Record<string, unknown>
      if (!store || typeof store !== 'object' || Array.isArray(store)) return emptyPatchResult()
      const priorSums = new Map<string, number>()
      for (const [adjKey, rawValue] of Object.entries(store)) {
        const amount = priorAmountSource(rawValue)
        if (!amount.found) continue

        let discKey = adjKey
        if (variant === 'listed') {
          if (adjKey === 'derivative_assets' || adjKey === 'derivative_liabilities') discKey = 'derivatives'
          if (adjKey === 'derivatives') discKey = 'derivatives'
        }
        if (variant === 'soe') {
          if (adjKey === 'derivatives') discKey = 'derivative_assets'
          // 国企无「其中」披露行：指定类备忘不单独落表
          if (
            adjKey === 'designated_fv_assets'
            || adjKey === 'designated_fv_liabilities'
            || adjKey === 'designated_fv_other'
          ) continue
        }
        if (rowDefs(variant).some((definition) => definition.rowKey === discKey)) {
          priorSums.set(discKey, (priorSums.get(discKey) ?? 0) + amount.value)
        }
      }
      return applyAmountPatch('priorAmount', priorSums)
    } catch {
      return emptyPatchResult()
    }
  }

  function handleAdjudicated(e: Event): void {
    const d = (e as CustomEvent<{ accountCode: string; adjudicatedAmount: number }>).detail
    if (d?.accountCode === G13_ACCOUNT_CODE) {
      adjudicatedAmount.value = d.adjudicatedAmount
      syncFromDetail()
    }
  }

  /**
   * 审定数 → G13-2 明细本期 → G13-1 上期审定。先完成两侧 patch，再按来源、变化和写权限最多保存一次。
   * 附注页离屏同步传 `{ persist: false }`，只改内存、不保存。
   */
  function pullLatestAdjudicated(opts: { persist?: boolean } = {}): G13DisclosurePatchResult {
    const adjudicated = amountSource(options.allResponses.value.get('G13-1-adjudicated-amount')?.conclusion)
    if (adjudicated.found) adjudicatedAmount.value = adjudicated.value

    const result = mergePatchResults(applyDetailPatch(), applyPriorPatch())
    persistPatch(result, opts.persist !== false)
    return result
  }

  async function generateAiConclusion(): Promise<void> {
    if (options.isReadonly.value || !options.wpId.value) return
    aiLoading.value = true
    try {
      const res = await api.post(
        `/api/workpapers/${options.wpId.value}/g13/ai/fv-change-conclusion`,
        {
          existingContent: noteText.value,
          relatedContext: {
            rows: noteDataRows.value,
            total: totalRow.value.currentAmount,
            adjudicatedAmount: adjudicatedAmount.value,
            templateHint: G13_DISCLOSURE_TEMPLATE_HINT,
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

  // 离屏实例化（附注页离屏同步在 effectScope 里调用，没有组件实例）不挂钩子、不订阅审定事件、不广播说明；挂载时的回填
  // 由调用方显式调 `pullLatestAdjudicated({ persist: false })`（spec note-pull-followup-closure R1）。组件内行为不变。
  if (getCurrentInstance()) {
    onMounted(() => {
      pullLatestAdjudicated()
      window.addEventListener('substantive:adjudicated', handleAdjudicated)
      publishNoteUpdate()
    })
    onBeforeUnmount(() => {
      window.removeEventListener('substantive:adjudicated', handleAdjudicated)
      if (noteTimer) clearTimeout(noteTimer)
    })
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
    templateHint: G13_DISCLOSURE_TEMPLATE_HINT,
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
