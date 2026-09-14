import { useWorkpaperAuditYear } from './workpaperAuditYear'
/**
 * useG4MainAdjudication — G4-1 审定表（对齐 Excel 模板）
 *
 * 列：期初/期末 ×（未审数 | 账项调整 | 审定数）+ 变动额/变动率 + 原因分析
 * 行：原值 / 减值 / 净值三层 + 试算平衡表数 / 差异数
 * 公式：审定 = 未审 + 账项调整；净值叶子 = 对应原值审定 − 减值审定
 * EventBus: publish substantive:adjudicated(accountCode='1501')
 *           subscribe g4:adjustment-writeback
 */
import { ref, computed, watch, onMounted, onBeforeUnmount, getCurrentInstance, type Ref } from 'vue'
import {
  G4_ACCOUNT_CODE,
  G4_CHANGE_RATE_THRESHOLD,
  G4_ADJUDICATION_ITEMS,
  G4_ADJ_WRITEBACK_ROW_KEY,
  parseG4AdjStore,
  applyG4AdjustmentWriteback,
  applyG4SplitAdjustmentWriteback,
  listG4WritebackAllocTargets,
  type G4AdjRowDef,
  type G4AdjRowStore,
  type G4AdjSection,
} from './g4AdjudicationItems'
import { parseNum, calcChangeRate, calcAmortizedCost } from '@/composables/useG4MainFormulaEngine'
import type { ChecklistResponse } from './useF1FormData'

export {
  G4_ACCOUNT_CODE,
  G4_CHANGE_RATE_THRESHOLD,
  G4_ADJ_WRITEBACK_ROW_KEY,
  applyG4AdjustmentWriteback,
  listG4WritebackAllocTargets,
}

const ITEM_ID_ROWS = 'G4-1-rows'
const ITEM_ID_TB = 'G4-1-adj-tb-1501'
const ITEM_ID_NOTE = 'G4-1-adj-note'
const ITEM_ID_CONCLUSION = 'G4-1-adj-conclusion'

export type G4AdjEditableField =
  | 'openingUnadjusted'
  | 'openingAdjustment'
  | 'closingUnadjusted'
  | 'closingAdjustment'
  | 'reasonAnalysis'

export interface G4AdjudicationRow {
  rowKey: string
  label: string
  kind: G4AdjRowDef['kind']
  section?: G4AdjSection
  indent: number
  editable: boolean
  openingUnadjusted: number
  openingAdjustment: number
  openingAudited: number
  closingUnadjusted: number
  closingAdjustment: number
  closingAudited: number
  changeAmount: number
  changeRate: number | null
  reasonAnalysis: string
  changeRateHighlight: boolean
  reasonRequired: boolean
  /** 兼容旧模板字段名 */
  openingAdjusted: number
  closingAdjusted: number
  openingAJE: number
  openingRJE: number
  closingAJE: number
  closingRJE: number
  item: string
  id: string
  isEditable: boolean
  isSubtotal: boolean
  indexRef: string
}

function audited(unadj: number, adj: number): number {
  return parseNum(unadj) + parseNum(adj)
}

function rateFlags(rate: number | null) {
  const highlight = rate != null && Math.abs(rate) > G4_CHANGE_RATE_THRESHOLD
  return { changeRateHighlight: highlight, reasonRequired: highlight }
}

function emptyAmounts() {
  return {
    openingUnadjusted: 0,
    openingAdjustment: 0,
    openingAudited: 0,
    closingUnadjusted: 0,
    closingAdjustment: 0,
    closingAudited: 0,
    changeAmount: 0,
    changeRate: null as number | null,
    reasonAnalysis: '',
    ...rateFlags(null),
  }
}

function withDerived(
  base: Omit<
    G4AdjudicationRow,
    | 'openingAudited'
    | 'closingAudited'
    | 'changeAmount'
    | 'changeRate'
    | 'changeRateHighlight'
    | 'reasonRequired'
    | 'openingAdjusted'
    | 'closingAdjusted'
    | 'openingAJE'
    | 'openingRJE'
    | 'closingAJE'
    | 'closingRJE'
    | 'item'
    | 'id'
    | 'isEditable'
    | 'isSubtotal'
    | 'indexRef'
  > & { openingAudited?: number; closingAudited?: number },
): G4AdjudicationRow {
  const openingAudited =
    base.openingAudited ?? audited(base.openingUnadjusted, base.openingAdjustment)
  const closingAudited =
    base.closingAudited ?? audited(base.closingUnadjusted, base.closingAdjustment)
  const changeAmount = closingAudited - openingAudited
  const changeRate = calcChangeRate(openingAudited, closingAudited)
  const flags = rateFlags(changeRate)
  return {
    ...base,
    openingAudited,
    closingAudited,
    changeAmount,
    changeRate,
    ...flags,
    openingAdjusted: openingAudited,
    closingAdjusted: closingAudited,
    openingAJE: base.openingAdjustment,
    openingRJE: 0,
    closingAJE: base.closingAdjustment,
    closingRJE: 0,
    item: base.label,
    id: base.rowKey,
    isEditable: !!base.editable,
    isSubtotal:
      base.kind === 'subtotal' ||
      base.kind === 'section_net' ||
      base.kind === 'section_header',
    indexRef: '',
  }
}

function cellOf(store: G4AdjRowStore, key: string) {
  const c = store[key] ?? {}
  return {
    openingUnadjusted: parseNum(c.openingUnadjusted),
    openingAdjustment: parseNum(c.openingAdjustment),
    closingUnadjusted: parseNum(c.closingUnadjusted),
    closingAdjustment: parseNum(c.closingAdjustment),
    reasonAnalysis: String(c.reasonAnalysis || ''),
  }
}

function leafKeys(section: G4AdjSection): string[] {
  return [`${section}-individual`, `${section}-portfolio`]
}

export interface UseG4MainAdjudicationOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}

export function useG4MainAdjudication(options: UseG4MainAdjudicationOptions) {
  const _auditYearRef = useWorkpaperAuditYear()

  const { projectId, allResponses, isReadonly } = options
  const readonly = isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  const auditNote = ref('')
  const auditConclusion = ref('')
  const lastWritebackNet = ref(0)

  function readRawStore(): G4AdjRowStore {
    const primary = allResponses.value.get(ITEM_ID_ROWS)
    const primaryRaw = primary?.conclusion || primary?.remark
    if (primaryRaw) return parseG4AdjStore(primaryRaw)

    const ov = allResponses.value.get('G4-1-adj-groups-original-value')?.remark
      || allResponses.value.get('G4-1-adj-groups-original-value')?.conclusion
    const imp = allResponses.value.get('G4-1-adj-groups-impairment')?.remark
      || allResponses.value.get('G4-1-adj-groups-impairment')?.conclusion
    const merged: G4AdjRowStore = {}
    if (ov) Object.assign(merged, parseG4AdjStore(ov))
    if (imp) Object.assign(merged, parseG4AdjStore(imp))
    const oneYearItem = allResponses.value.get('G4-1-adj-one-year')
    const oneYear = oneYearItem?.remark || oneYearItem?.conclusion
    if (oneYear) {
      try {
        const oy = JSON.parse(oneYear) as { openingAdjusted?: number; closingAdjusted?: number }
        merged['original__one-year'] = {
          openingUnadjusted: parseNum(oy.openingAdjusted),
          openingAdjustment: 0,
          closingUnadjusted: parseNum(oy.closingAdjusted),
          closingAdjustment: 0,
        }
      } catch { /* ignore */ }
    }
    return merged
  }

  const store = computed(() => readRawStore())

  const trialBalanceAmount = computed(() =>
    parseNum(allResponses.value.get(ITEM_ID_TB)?.remark),
  )

  function buildLeaf(def: G4AdjRowDef, s: G4AdjRowStore): G4AdjudicationRow {
    const cell = cellOf(s, def.rowKey)
    return withDerived({
      rowKey: def.rowKey,
      label: def.label,
      kind: def.kind,
      section: def.section,
      indent: def.indent ?? 0,
      editable: !!def.editable,
      ...cell,
    })
  }

  function sumLeaves(section: G4AdjSection, s: G4AdjRowStore) {
    const keys = leafKeys(section)
    const leafRows = keys.map((k) => {
      const def = G4_ADJUDICATION_ITEMS.find((d) => d.rowKey === k)!
      return buildLeaf(def, s)
    })
    const openingUnadjusted = leafRows.reduce((a, r) => a + r.openingUnadjusted, 0)
    const openingAdjustment = leafRows.reduce((a, r) => a + r.openingAdjustment, 0)
    const closingUnadjusted = leafRows.reduce((a, r) => a + r.closingUnadjusted, 0)
    const closingAdjustment = leafRows.reduce((a, r) => a + r.closingAdjustment, 0)
    return {
      openingUnadjusted,
      openingAdjustment,
      closingUnadjusted,
      closingAdjustment,
      openingAudited: audited(openingUnadjusted, openingAdjustment),
      closingAudited: audited(closingUnadjusted, closingAdjustment),
    }
  }

  function buildNetLeaf(def: G4AdjRowDef, s: G4AdjRowStore): G4AdjudicationRow {
    const suffix = def.rowKey.replace('net-', '')
    const ov = cellOf(s, `original-${suffix}`)
    const imp = cellOf(s, `impairment-${suffix}`)
    const ovOpen = audited(ov.openingUnadjusted, ov.openingAdjustment)
    const ovClose = audited(ov.closingUnadjusted, ov.closingAdjustment)
    const impOpen = audited(imp.openingUnadjusted, imp.openingAdjustment)
    const impClose = audited(imp.closingUnadjusted, imp.closingAdjustment)
    const openNet = calcAmortizedCost(ovOpen, impOpen)
    const closeNet = calcAmortizedCost(ovClose, impClose)
    return withDerived({
      rowKey: def.rowKey,
      label: def.label,
      kind: def.kind,
      section: 'net',
      indent: def.indent ?? 1,
      editable: false,
      openingUnadjusted: openNet,
      openingAdjustment: 0,
      closingUnadjusted: closeNet,
      closingAdjustment: 0,
      reasonAnalysis: '',
      openingAudited: openNet,
      closingAudited: closeNet,
    })
  }

  const rows = computed<G4AdjudicationRow[]>(() => {
    const s = store.value
    const out: G4AdjudicationRow[] = []

    for (const def of G4_ADJUDICATION_ITEMS) {
      if (def.kind === 'section_header') {
        out.push(
          withDerived({
            rowKey: def.rowKey,
            label: def.label,
            kind: def.kind,
            section: def.section,
            indent: 0,
            editable: false,
            ...emptyAmounts(),
          }),
        )
        continue
      }

      if (def.kind === 'leaf' && def.section === 'net') {
        out.push(buildNetLeaf(def, s))
        continue
      }

      if (def.kind === 'leaf') {
        out.push(buildLeaf(def, s))
        continue
      }

      if (def.kind === 'subtotal' && def.section) {
        const sum =
          def.section === 'net'
            ? (() => {
                const ind = buildNetLeaf(
                  G4_ADJUDICATION_ITEMS.find((d) => d.rowKey === 'net-individual')!,
                  s,
                )
                const port = buildNetLeaf(
                  G4_ADJUDICATION_ITEMS.find((d) => d.rowKey === 'net-portfolio')!,
                  s,
                )
                return {
                  openingUnadjusted: ind.openingUnadjusted + port.openingUnadjusted,
                  openingAdjustment: 0,
                  closingUnadjusted: ind.closingUnadjusted + port.closingUnadjusted,
                  closingAdjustment: 0,
                  openingAudited: ind.openingAudited + port.openingAudited,
                  closingAudited: ind.closingAudited + port.closingAudited,
                }
              })()
            : sumLeaves(def.section, s)
        out.push(
          withDerived({
            rowKey: def.rowKey,
            label: def.label,
            kind: def.kind,
            section: def.section,
            indent: 0,
            editable: false,
            openingUnadjusted: sum.openingUnadjusted,
            openingAdjustment: sum.openingAdjustment,
            closingUnadjusted: sum.closingUnadjusted,
            closingAdjustment: sum.closingAdjustment,
            reasonAnalysis: '',
            openingAudited: sum.openingAudited,
            closingAudited: sum.closingAudited,
          }),
        )
        continue
      }

      if (def.kind === 'one_year_deduct' && def.section) {
        const cell = cellOf(s, def.rowKey)
        out.push(
          withDerived({
            rowKey: def.rowKey,
            label: def.label,
            kind: def.kind,
            section: def.section,
            indent: 0,
            editable: true,
            ...cell,
          }),
        )
        continue
      }

      if (def.kind === 'section_net' && def.section) {
        const sub = out.find((r) => r.rowKey === `${def.section}__subtotal`)
        const oneYear = out.find((r) => r.rowKey === `${def.section}__one-year`)
        const openingAudited = (sub?.openingAudited ?? 0) - (oneYear?.openingAudited ?? 0)
        const closingAudited = (sub?.closingAudited ?? 0) - (oneYear?.closingAudited ?? 0)
        out.push(
          withDerived({
            rowKey: def.rowKey,
            label: def.label,
            kind: def.kind,
            section: def.section,
            indent: 0,
            editable: false,
            openingUnadjusted: openingAudited,
            openingAdjustment: 0,
            closingUnadjusted: closingAudited,
            closingAdjustment: 0,
            reasonAnalysis: '',
            openingAudited,
            closingAudited,
          }),
        )
        continue
      }

      if (def.rowKey === 'footer-tb') {
        const tb = trialBalanceAmount.value
        out.push(
          withDerived({
            rowKey: def.rowKey,
            label: def.label,
            kind: def.kind,
            indent: 0,
            editable: true,
            openingUnadjusted: 0,
            openingAdjustment: 0,
            closingUnadjusted: tb,
            closingAdjustment: 0,
            reasonAnalysis: '',
            openingAudited: 0,
            closingAudited: tb,
          }),
        )
        continue
      }

      if (def.rowKey === 'footer-variance') {
        const net = out.find((r) => r.rowKey === 'net__net')
        const tb = trialBalanceAmount.value
        const closingAudited = (net?.closingAudited ?? 0) - tb
        out.push(
          withDerived({
            rowKey: def.rowKey,
            label: def.label,
            kind: def.kind,
            indent: 0,
            editable: false,
            openingUnadjusted: 0,
            openingAdjustment: 0,
            closingUnadjusted: closingAudited,
            closingAdjustment: 0,
            reasonAnalysis: '',
            openingAudited: 0,
            closingAudited,
          }),
        )
      }
    }

    return out
  })

  const amortizedCostRow = computed(
    () => rows.value.find((r) => r.rowKey === 'net__net')!,
  )
  const variance = computed(
    () => rows.value.find((r) => r.rowKey === 'footer-variance')?.closingAudited ?? 0,
  )
  const hasVarianceHighlight = computed(() => Math.abs(variance.value) > 0.005)

  const originalValueRows = computed(() =>
    rows.value.filter((r) => r.section === 'original' && r.kind === 'leaf'),
  )
  const originalValueSubtotal = computed(
    () => rows.value.find((r) => r.rowKey === 'original__subtotal')!,
  )
  const impairmentRows = computed(() =>
    rows.value.filter((r) => r.section === 'impairment' && r.kind === 'leaf'),
  )
  const impairmentSubtotal = computed(
    () => rows.value.find((r) => r.rowKey === 'impairment__subtotal')!,
  )
  const oneYearDeductRow = computed(
    () => rows.value.find((r) => r.rowKey === 'original__one-year')!,
  )
  const oneYearMaturityRow = computed(() => oneYearDeductRow.value)
  const groups = computed(() => [
    {
      groupKey: 'original-value',
      groupName: '一、债权投资原值',
      expanded: true,
      rows: originalValueRows.value,
      subtotal: originalValueSubtotal.value,
      oneYearDeduct: oneYearDeductRow.value,
    },
    {
      groupKey: 'impairment',
      groupName: '二、债权投资减值准备',
      expanded: true,
      rows: impairmentRows.value,
      subtotal: impairmentSubtotal.value,
    },
    {
      groupKey: 'amortized-cost',
      groupName: '三、债权投资净值',
      expanded: true,
      rows: rows.value.filter((r) => r.section === 'net' && r.kind === 'leaf'),
      subtotal: amortizedCostRow.value,
    },
  ])

  watch(
    () => allResponses.value.get(ITEM_ID_NOTE)?.remark,
    (v) => { auditNote.value = v || '' },
    { immediate: true },
  )
  watch(
    () => allResponses.value.get(ITEM_ID_CONCLUSION)?.remark,
    (v) => { auditConclusion.value = v || '' },
    { immediate: true },
  )

  function persistStore(next: G4AdjRowStore): void {
    const json = JSON.stringify(next)
    allResponses.value.set(ITEM_ID_ROWS, {
      item_id: ITEM_ID_ROWS,
      conclusion: json,
      remark: json,
    })
    debounceSave()
  }

  function updateCell(rowKey: string, field: G4AdjEditableField, value: number | string): void {
    if (readonly.value) return
    if (rowKey === 'footer-tb') {
      setTrialBalance(typeof value === 'number' ? value : parseNum(value))
      return
    }
    const next = { ...store.value }
    const prev = { ...(next[rowKey] ?? {}) }
    if (field === 'reasonAnalysis') {
      prev.reasonAnalysis = String(value ?? '')
    } else {
      ;(prev as any)[field] = typeof value === 'number' ? value : parseNum(value)
    }
    next[rowKey] = prev
    persistStore(next)
  }

  /** 兼容旧调用：updateCell(groupKey, rowKey, field, value) 或新签名 */
  function updateCellCompat(
    a: string,
    b: string,
    c?: string | number,
    d?: number | string,
  ): void {
    if (d !== undefined && c !== undefined) {
      let rowKey = b
      if (rowKey.startsWith('ov-')) rowKey = rowKey.replace(/^ov-/, 'original-')
      if (rowKey.startsWith('imp-')) rowKey = rowKey.replace(/^imp-/, 'impairment-')
      // 旧 AJE/RJE → 合并写入 adjustment
      let field = c as string
      if (field === 'openingAJE' || field === 'openingRJE') field = 'openingAdjustment'
      if (field === 'closingAJE' || field === 'closingRJE') field = 'closingAdjustment'
      updateCell(rowKey, field as G4AdjEditableField, d)
      return
    }
    updateCell(a, b as G4AdjEditableField, c as number | string)
  }

  function updateOneYearRow(field: 'openingAdjusted' | 'closingAdjusted', value: number | string): void {
    const mapped = field === 'openingAdjusted' ? 'openingUnadjusted' : 'closingUnadjusted'
    updateCell('original__one-year', mapped, value)
  }

  function setTrialBalance(amount: number): void {
    allResponses.value.set(ITEM_ID_TB, {
      item_id: ITEM_ID_TB,
      conclusion: null,
      remark: String(amount),
    })
    debounceSave()
  }

  async function fetchTrialBalance(): Promise<void> {
    const _year = _auditYearRef.value
    if (_year == null) return null
    if (!projectId.value) return
    try {
      const resp = await (await import('@/services/apiProxy')).api.get(
        `/api/projects/${projectId.value}/trial-balance`,
        { params: { year: _year, account_code: G4_ACCOUNT_CODE  }, _silent: true } as any,
      )
      const data = resp?.data?.data ?? resp?.data
      if (data) {
        setTrialBalance(parseNum(data.audited_amount ?? data.unadjusted_amount ?? 0))
      }
    } catch { /* silent */ }
  }

  function publishAdjudicated(): void {
    const amount = amortizedCostRow.value?.closingAudited ?? 0
    try {
      window.dispatchEvent(
        new CustomEvent('substantive:adjudicated', {
          detail: {
            wpCode: 'G4',
            accountCode: G4_ACCOUNT_CODE,
            adjudicatedAmount: amount,
            auditedAmount: amount,
          },
        }),
      )
    } catch { /* silent */ }
  }

  watch(
    () => amortizedCostRow.value?.closingAudited,
    () => { publishAdjudicated() },
  )

  function applyWriteback(net: number): void {
    const next = applyG4AdjustmentWriteback(store.value, net)
    lastWritebackNet.value = net
    persistStore(next)
  }

  function applySplitWriteback(originalNet: number, impairmentNet: number): void {
    const next = applyG4SplitAdjustmentWriteback(store.value, originalNet, impairmentNet)
    lastWritebackNet.value = originalNet
    persistStore(next)
  }

  function onAdjustmentWriteback(e: Event): void {
    const detail = (e as CustomEvent).detail
    // 优先使用分离口径（G4-3 权威路径已写入时，同步本地 store）
    if (detail?.originalNet != null || detail?.impairmentNet != null) {
      applySplitWriteback(
        parseNum(detail.originalNet),
        parseNum(detail.impairmentNet),
      )
      return
    }
    const summaries = detail?.summaries as
      | Array<{ accountCode: string; ajeNet?: number; rjeNet?: number; net?: number }>
      | undefined
    if (Array.isArray(summaries)) {
      let originalNet = 0
      let impairmentNet = 0
      for (const item of summaries) {
        const code = String(item.accountCode || '')
        const aje = parseNum(item.ajeNet)
        if (code === '1502' || code.startsWith('1502')) {
          // 贷−借：ajeNet 是借−贷，取反
          impairmentNet += -aje
        } else if (code.startsWith('1501')) {
          originalNet += aje
        }
      }
      applySplitWriteback(originalNet, impairmentNet)
      return
    }
    if (detail?.netAdjustment != null) {
      applyWriteback(parseNum(detail.netAdjustment))
    }
  }

  function debounceSave(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      flushSave()
    }, 2000)
  }

  function flushSave(): void {
    try {
      const keys = [ITEM_ID_ROWS, ITEM_ID_TB, ITEM_ID_NOTE, ITEM_ID_CONCLUSION]
      const items = keys.map((k) => allResponses.value.get(k)).filter(Boolean)
      window.dispatchEvent(new CustomEvent('g4:save-items', { detail: { items } }))
    } catch { /* silent */ }
  }

  watch(auditNote, (val) => {
    allResponses.value.set(ITEM_ID_NOTE, { item_id: ITEM_ID_NOTE, conclusion: null, remark: val })
    debounceSave()
  })
  watch(auditConclusion, (val) => {
    allResponses.value.set(ITEM_ID_CONCLUSION, {
      item_id: ITEM_ID_CONCLUSION,
      conclusion: null,
      remark: val,
    })
    debounceSave()
  })

  function attachListeners(): void {
    window.addEventListener('g4:adjustment-writeback', onAdjustmentWriteback)
    window.addEventListener('g4:adjustment-confirmed', onAdjustmentWriteback)
  }
  function detachListeners(): void {
    window.removeEventListener('g4:adjustment-writeback', onAdjustmentWriteback)
    window.removeEventListener('g4:adjustment-confirmed', onAdjustmentWriteback)
  }

  if (getCurrentInstance()) {
    onMounted(attachListeners)
    onBeforeUnmount(() => {
      detachListeners()
      if (debounceTimer) {
        clearTimeout(debounceTimer)
        debounceTimer = null
        flushSave()
      }
    })
  } else {
    // 单测直调 composable 时仍挂载，并暴露 dispose 便于清理
    attachListeners()
  }

  return {
    rows,
    groups,
    originalValueRows,
    originalValueSubtotal,
    oneYearDeductRow,
    impairmentRows,
    impairmentSubtotal,
    amortizedCostRow,
    oneYearMaturityRow,
    trialBalanceAmount,
    variance,
    hasVarianceHighlight,
    lastWritebackNet,
    auditNote,
    auditConclusion,
    updateCell: updateCellCompat as any,
    updateOneYearRow,
    setTrialBalance,
    fetchTrialBalance,
    applyWriteback,
    publishAdjudicated,
    dispose: detachListeners,
    addRow: () => {},
    removeRow: () => {},
  }
}

export default useG4MainAdjudication

export type AdjudicationGroup = {
  groupKey: string
  groupName: string
  expanded: boolean
  rows: G4AdjudicationRow[]
  subtotal: G4AdjudicationRow
  oneYearDeduct?: G4AdjudicationRow
}
