/**
 * useH10Disclosure — 附注披露（上市/国企）
 *
 * 编制逻辑：H10-1 审定分项 → 披露主表；上市另编试运行收入/成本明细（净额回写主表试运行行）。
 * 附注联动：eventBus disclosure:note-text-updated + sync-from-workpaper 结构化子表。
 */
import { ref, computed, watch, onMounted, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import { ElMessage } from 'element-plus'
import {
  H10_ACCOUNT_CODE,
  H10_DISCLOSURE_LISTED_ROWS,
  H10_DISCLOSURE_SOE_ROWS,
  H10_DISCLOSURE_LEGACY_KEY_MAP,
  H10_TRIAL_DETAIL_ROWS,
} from './h10Constants'
import { parseH10AdjStore } from './h10AdjStorage'
import { parseNum, calcChangeAmount, calcChangeRate, calcSubtotal, calcAuditedAmount } from './useH10FormulaEngine'
import { H10_NOTE_SECTION } from './h10NoteSectionMap'
import {
  g14DisclosureHasAnyAmount,
  hasG14DisclosureAmount,
} from './g14DisclosureVisibility'
import type { ChecklistResponse } from './useF1FormData'
import { api } from '@/services/apiProxy'
import { eventBus } from '@/utils/eventBus'

export interface H10DisclosureRow {
  rowKey: string
  label: string
  currentAmount: number
  priorAmount: number
  nonRecurringAmount?: number
  changeAmount: number
  changeRate: number | null
  remark: string
}

export interface H10TrialDetailRow {
  rowKey: string
  label: string
  currentIncome: number
  currentCost: number
  priorIncome: number
  priorCost: number
}

type Variant = 'listed' | 'soe'

function rowDefs(variant: Variant) {
  return variant === 'listed' ? H10_DISCLOSURE_LISTED_ROWS : H10_DISCLOSURE_SOE_ROWS
}

function defaultRows(variant: Variant): H10DisclosureRow[] {
  return rowDefs(variant).map((def) => ({
    rowKey: def.rowKey,
    label: def.label,
    currentAmount: 0,
    priorAmount: 0,
    nonRecurringAmount: variant === 'soe' ? 0 : undefined,
    changeAmount: 0,
    changeRate: null,
    remark: '',
  }))
}

function defaultTrialRows(): H10TrialDetailRow[] {
  return H10_TRIAL_DETAIL_ROWS.map((def) => ({
    rowKey: def.rowKey,
    label: def.label,
    currentIncome: 0,
    currentCost: 0,
    priorIncome: 0,
    priorCost: 0,
  }))
}

function enrichRow(
  raw: Partial<H10DisclosureRow> & { rowKey: string },
  variant: Variant,
): H10DisclosureRow {
  const def = rowDefs(variant).find((d) => d.rowKey === raw.rowKey)
  const currentAmount = parseNum(raw.currentAmount)
  const priorAmount = parseNum(raw.priorAmount)
  return {
    rowKey: raw.rowKey,
    label: def?.label ?? raw.label ?? raw.rowKey,
    currentAmount,
    priorAmount,
    nonRecurringAmount: variant === 'soe' ? parseNum(raw.nonRecurringAmount) : undefined,
    changeAmount: calcChangeAmount(currentAmount, priorAmount),
    changeRate: calcChangeRate(priorAmount, currentAmount),
    remark: raw.remark ?? '',
  }
}

function trialNet(r: H10TrialDetailRow): { current: number; prior: number } {
  return {
    current: parseNum(r.currentIncome) - parseNum(r.currentCost),
    prior: parseNum(r.priorIncome) - parseNum(r.priorCost),
  }
}

function migrateLegacyRows(parsed: any[]): any[] {
  const byKey = new Map<string, any>()
  for (const r of parsed) {
    if (!r?.rowKey) continue
    const target = H10_DISCLOSURE_LEGACY_KEY_MAP[r.rowKey] ?? r.rowKey
    const prev = byKey.get(target)
    if (!prev) {
      byKey.set(target, { ...r, rowKey: target })
      continue
    }
    byKey.set(target, {
      ...prev,
      currentAmount: parseNum(prev.currentAmount) + parseNum(r.currentAmount),
      priorAmount: parseNum(prev.priorAmount) + parseNum(r.priorAmount),
      nonRecurringAmount: parseNum(prev.nonRecurringAmount) + parseNum(r.nonRecurringAmount),
    })
  }
  return [...byKey.values()]
}

export function useH10Disclosure(options: {
  variant: Variant
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
  wpId: Ref<string>
  projectId?: Ref<string | undefined>
  isReadonly: Ref<boolean> | ComputedRef<boolean>
}) {
  const variant = options.variant
  const itemId = variant === 'listed' ? 'H10-disclosure-listed' : 'H10-disclosure-soe'
  const noteItemId = `${itemId}-note`
  const trialItemId = 'H10-disclosure-listed-trial'
  const noteSectionId = H10_NOTE_SECTION[variant]

  const rows = ref<H10DisclosureRow[]>(defaultRows(variant))
  const trialRows = ref<H10TrialDetailRow[]>(defaultTrialRows())
  const noteText = ref('')
  const adjudicatedAmount = ref<number | null>(null)
  const aiLoading = ref(false)
  /** 强制显示模板空行；有数据后默认隐藏无发生额项 */
  const showEmptyRows = ref(false)
  const prefsItemId = `${itemId}-prefs`

  const title = computed(() =>
    variant === 'listed' ? '附注披露信息（上市公司）' : '附注披露信息（国有企业）',
  )

  function loadPrefs(): void {
    const raw = options.allResponses.value.get(prefsItemId)?.remark
    if (!raw) return
    try {
      const parsed = JSON.parse(raw)
      if (typeof parsed?.showEmptyRows === 'boolean') showEmptyRows.value = parsed.showEmptyRows
    } catch { /* ignore */ }
  }

  function setShowEmptyRows(val: boolean): void {
    showEmptyRows.value = val
    options.debouncedSave(prefsItemId, {
      remark: JSON.stringify({ showEmptyRows: showEmptyRows.value }),
    })
  }

  function loadFromStore(): void {
    const raw = options.allResponses.value.get(itemId)?.remark
    if (raw) {
      try {
        const parsed = JSON.parse(raw)
        if (Array.isArray(parsed)) {
          const migrated = migrateLegacyRows(parsed)
          const byKey = new Map(migrated.map((r: any) => [r.rowKey, r]))
          rows.value = rowDefs(variant).map((def) =>
            enrichRow({ ...def, ...byKey.get(def.rowKey) }, variant),
          )
        }
      } catch { /* ignore */ }
    } else {
      rows.value = defaultRows(variant)
    }

    if (variant === 'listed') {
      const trialRaw = options.allResponses.value.get(trialItemId)?.remark
      if (trialRaw) {
        try {
          const parsed = JSON.parse(trialRaw)
          if (Array.isArray(parsed)) {
            const byKey = new Map(parsed.map((r: any) => [r.rowKey, r]))
            trialRows.value = H10_TRIAL_DETAIL_ROWS.map((def) => ({
              rowKey: def.rowKey,
              label: def.label,
              currentIncome: parseNum(byKey.get(def.rowKey)?.currentIncome),
              currentCost: parseNum(byKey.get(def.rowKey)?.currentCost),
              priorIncome: parseNum(byKey.get(def.rowKey)?.priorIncome),
              priorCost: parseNum(byKey.get(def.rowKey)?.priorCost),
            }))
          }
        } catch { /* ignore */ }
      } else {
        trialRows.value = defaultTrialRows()
      }
    }

    noteText.value = options.allResponses.value.get(noteItemId)?.conclusion ?? ''
    const adj = options.allResponses.value.get('H10-1-adjudicated-amount')?.conclusion
    if (adj != null && adj !== '') adjudicatedAmount.value = parseNum(adj)
  }

  watch(() => options.allResponses.value, loadFromStore, { deep: true, immediate: true })
  watch(() => options.allResponses.value.get(prefsItemId)?.remark, loadPrefs, { immediate: true })

  function hasH10Amount(row: H10DisclosureRow): boolean {
    return hasG14DisclosureAmount(row)
      || (variant === 'soe' && Math.abs(parseNum(row.nonRecurringAmount)) >= 0.005)
  }

  const includeEmptyInDisplay = computed(() =>
    showEmptyRows.value || !g14DisclosureHasAnyAmount(rows.value),
  )

  const visibleDataRows = computed(() => {
    if (includeEmptyInDisplay.value) return rows.value
    return rows.value.filter((r) => hasH10Amount(r))
  })

  const hiddenEmptyCount = computed(() => {
    if (includeEmptyInDisplay.value) return 0
    return Math.max(0, rows.value.length - visibleDataRows.value.length)
  })

  const displayRows = computed(() => {
    const data = visibleDataRows.value
    // 合计始终按全量行，避免隐藏空行后合计被缩小
    const all = rows.value
    const total = {
      rowKey: 'total',
      label: '合  计',
      currentAmount: calcSubtotal(all.map((r) => r.currentAmount)),
      priorAmount: calcSubtotal(all.map((r) => r.priorAmount)),
      nonRecurringAmount: variant === 'soe'
        ? calcSubtotal(all.map((r) => parseNum(r.nonRecurringAmount)))
        : undefined,
      changeAmount: 0,
      changeRate: null as number | null,
      remark: '',
    }
    total.changeAmount = calcChangeAmount(total.currentAmount, total.priorAmount)
    total.changeRate = calcChangeRate(total.priorAmount, total.currentAmount)
    return [...data, total]
  })

  /** 试运行净额合计（解释第15号：日常活动相关应关注营业收入） */
  const trialNetTotal = computed(() => {
    if (variant !== 'listed') return 0
    return calcSubtotal(trialRows.value.map((r) => trialNet(r).current))
  })

  const soeNonRecurringDiff = computed(() => {
    if (variant !== 'soe') return null
    const current = calcSubtotal(rows.value.map((r) => r.currentAmount))
    const nr = calcSubtotal(rows.value.map((r) => parseNum(r.nonRecurringAmount)))
    return Math.round((current - nr) * 100) / 100
  })

  const trialDisplayRows = computed(() => {
    const data = trialRows.value
    const total = {
      rowKey: 'total',
      label: '合  计',
      currentIncome: calcSubtotal(data.map((r) => r.currentIncome)),
      currentCost: calcSubtotal(data.map((r) => r.currentCost)),
      priorIncome: calcSubtotal(data.map((r) => r.priorIncome)),
      priorCost: calcSubtotal(data.map((r) => r.priorCost)),
    }
    return [...data, total]
  })

  const disclosureTotal = computed(() => displayRows.value.find((r) => r.rowKey === 'total')!)

  const reconcileDiff = computed(() => {
    if (adjudicatedAmount.value == null) return null
    return Math.round((disclosureTotal.value.currentAmount - adjudicatedAmount.value) * 100) / 100
  })

  function persist(): void {
    options.debouncedSave(itemId, { remark: JSON.stringify(rows.value) })
  }

  function persistTrial(): void {
    if (variant !== 'listed') return
    options.debouncedSave(trialItemId, { remark: JSON.stringify(trialRows.value) })
  }

  /** 试运行明细净额回写主表「试运行销售损益」行 */
  function applyTrialNetToMain(publish = true): void {
    if (variant !== 'listed') return
    const current = calcSubtotal(trialRows.value.map((r) => trialNet(r).current))
    const prior = calcSubtotal(trialRows.value.map((r) => trialNet(r).prior))
    rows.value = rows.value.map((r) => {
      if (r.rowKey !== 'trial_operation_sales') return r
      return enrichRow({ ...r, currentAmount: current, priorAmount: prior }, variant)
    })
    persist()
    if (publish) publishNoteDebounced()
  }

  function updateField(
    rowKey: string,
    field: 'currentAmount' | 'priorAmount' | 'nonRecurringAmount' | 'remark',
    value: unknown,
  ): void {
    if (options.isReadonly.value || rowKey === 'total') return
    rows.value = rows.value.map((r) => {
      if (r.rowKey !== rowKey) return r
      const patch = {
        ...r,
        [field]: field === 'remark' ? String(value ?? '') : parseNum(value),
      }
      return enrichRow(patch, variant)
    })
    persist()
    publishNoteDebounced()
  }

  function updateTrialField(
    rowKey: string,
    field: 'currentIncome' | 'currentCost' | 'priorIncome' | 'priorCost',
    value: unknown,
  ): void {
    if (options.isReadonly.value || variant !== 'listed' || rowKey === 'total') return
    trialRows.value = trialRows.value.map((r) => {
      if (r.rowKey !== rowKey) return r
      return { ...r, [field]: parseNum(value) }
    })
    persistTrial()
    applyTrialNetToMain(true)
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
      publishNoteUpdate()
    }, 2000)
  }

  function publishNoteUpdate(): void {
    try {
      const payload = {
        wpCode: 'H10',
        accountCode: H10_ACCOUNT_CODE,
        projectId: options.projectId?.value ?? '',
        wpId: options.wpId.value,
        variant,
        section: variant,
        sectionId: noteSectionId,
        text: noteText.value,
        timestamp: Date.now(),
      }
      eventBus.emit('disclosure:note-text-updated', payload as any)
    } catch { /* silent */ }
  }

  function handleAdjudicated(detail: any): void {
    if (!detail) return
    const code = detail.accountCode ?? detail.account_code
    if (code === H10_ACCOUNT_CODE) {
      adjudicatedAmount.value = parseNum(detail.adjudicatedAmount ?? detail.auditedAmount ?? detail.audited_amount)
    }
  }

  function pullLatestAdjudicated(): void {
    const adj = options.allResponses.value.get('H10-1-adjudicated-amount')?.conclusion
    if (adj != null) adjudicatedAmount.value = parseNum(adj)
  }

  /** 从 H10-1 审定分项带入披露主表（试运行行保留明细净额优先） */
  function pullFromAdjudication(): void {
    if (options.isReadonly.value) return
    pullLatestAdjudicated()
    const store = parseH10AdjStore(options.allResponses.value.get('H10-adj-rows')?.remark)
    let filled = 0
    rows.value = rows.value.map((r) => {
      if (r.rowKey === 'trial_operation_sales' && variant === 'listed') {
        const nets = trialRows.value.map(trialNet)
        const hasTrial = nets.some((n) => Math.abs(n.current) > 0.005 || Math.abs(n.prior) > 0.005)
        if (hasTrial) {
          return enrichRow({
            ...r,
            currentAmount: calcSubtotal(nets.map((n) => n.current)),
            priorAmount: calcSubtotal(nets.map((n) => n.prior)),
          }, variant)
        }
      }
      const raw = store[r.rowKey]
      if (!raw) return r
      const currentAudited = calcAuditedAmount(
        parseNum(raw.currentUnadjusted),
        parseNum(raw.currentAje),
        parseNum(raw.currentRje),
      )
      const priorAudited = calcAuditedAmount(
        parseNum(raw.priorUnadjusted),
        parseNum(raw.priorAje),
        parseNum(raw.priorRje),
      )
      if (Math.abs(currentAudited) > 0.005 || Math.abs(priorAudited) > 0.005) filled += 1
      const patch: Partial<H10DisclosureRow> = {
        ...r,
        currentAmount: currentAudited,
        priorAmount: priorAudited,
      }
      if (variant === 'soe') {
        // 处置长期资产损益通常属非经常性损益，默认带入本期审定数，可手工改
        patch.nonRecurringAmount = currentAudited
      }
      return enrichRow(patch as H10DisclosureRow, variant)
    })
    persist()
    publishNoteUpdate()
    ElMessage.success(filled > 0 ? `已从 H10-1 带入 ${filled} 个分项` : '已刷新审定数（H10-1 分项暂无金额）')
  }

  function getSyncSnapshot() {
    return {
      rows: rows.value as H10DisclosureRow[],
      trialRows: trialRows.value as H10TrialDetailRow[],
      noteText: noteText.value,
      adjudicatedAmount: adjudicatedAmount.value as number | null,
    }
  }

  async function generateAiConclusion(): Promise<void> {
    if (options.isReadonly.value) return
    aiLoading.value = true
    try {
      const res = await api.post(`/api/workpapers/${options.wpId.value}/h10/ai/disclosure-analysis`, {
        variant,
        rows: rows.value,
        trialRows: variant === 'listed' ? trialRows.value : undefined,
      }, { _silent: true } as any)
      const text = res?.data?.content ?? res?.content ?? ''
      if (text) updateNoteText(text)
    } catch { /* AI optional */ }
    finally { aiLoading.value = false }
  }

  function onBusAdjudicated(detail: any): void {
    handleAdjudicated(detail)
  }

  function onWindowAdjudicated(e: Event): void {
    handleAdjudicated((e as CustomEvent).detail)
  }

  onMounted(() => {
    eventBus.on('substantive:adjudicated', onBusAdjudicated)
    window.addEventListener('substantive:adjudicated', onWindowAdjudicated)
    pullLatestAdjudicated()
  })
  onBeforeUnmount(() => {
    eventBus.off('substantive:adjudicated', onBusAdjudicated)
    window.removeEventListener('substantive:adjudicated', onWindowAdjudicated)
    if (noteTimer) clearTimeout(noteTimer)
  })

  return {
    title,
    rows,
    displayRows,
    trialRows,
    trialDisplayRows,
    trialNetTotal,
    soeNonRecurringDiff,
    showEmptyRows,
    setShowEmptyRows,
    hiddenEmptyCount,
    noteText,
    noteSectionId,
    adjudicatedAmount,
    disclosureTotal,
    reconcileDiff,
    aiLoading,
    updateField,
    updateTrialField,
    updateNoteText,
    pullLatestAdjudicated,
    pullFromAdjudication,
    getSyncSnapshot,
    publishNoteUpdate,
    generateAiConclusion,
  }
}
