import { useWorkpaperAuditYear } from './workpaperAuditYear'
/**
 * useG2Adjudication — G2-1 应收利息审定表
 * 对齐 Excel：期初/期末 × 本账/账项调整/审定 + 变动额/变动率 + 差异分析
 * 行结构：原值 / 坏账准备 / 净值(=原值−坏账) × 单项/组合
 */
import { ref, computed, watch, onMounted, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import {
  G2_ACCOUNT_CODE,
  G2_CHANGE_RATE_THRESHOLD,
  G2_ADJUDICATION_ITEMS,
  leafKeysForSection,
  parseG2AdjStore,
  applyG2AdjustmentWriteback,
  G2_ADJ_WRITEBACK_ROW_KEY,
  type G2AdjRowDef,
  type G2AdjRowStore,
  type G2AdjSection,
} from './g2AdjudicationItems'
import {
  parseNum,
  calcAuditedAmount,
  calcChangeAmount,
  calcChangeRate,
  calcSubtotal,
  isChangeRateExceeding,
} from './useG2IntRecFormulaEngine'
import {
  loadG2DetailPartials,
  loadG2BadDebtLeaves,
  aggregateGrossFromDetail,
  aggregateProvisionFromBadDebt,
} from './g2CrossHelpers'
import { api } from '@/services/apiProxy'
import type { ChecklistResponse } from './useF1FormData'

export { G2_ACCOUNT_CODE, G2_CHANGE_RATE_THRESHOLD }

/** @deprecated 旧行常量，保留兼容 */
export const G2_ROW_ITEMS = [
  { rowKey: 'bond-interest', label: '债权投资利息' },
  { rowKey: 'other-bond-interest', label: '其他债权投资利息' },
  { rowKey: 'deposit-interest', label: '定期存款利息' },
  { rowKey: 'other', label: '其他' },
] as const

const ITEM_ID_ROWS = 'G2-1-rows'
const ITEM_ID_ROWS_LEGACY = 'G2-1-adj-rows'
const ITEM_ID_TB = 'G2-1-tb'
const ITEM_ID_TB_LEGACY = 'G2-1-adj-tb-1132'
const ITEM_ID_NOTE = 'G2-1-note'
const ITEM_ID_NOTE_LEGACY = 'G2-1-adj-note'
const ITEM_ID_CONCLUSION = 'G2-1-conclusion'
const ITEM_ID_CONCLUSION_LEGACY = 'G2-1-adj-conclusion'

export type G2AdjEditableField =
  | 'openingUnadjusted'
  | 'openingAdjustment'
  | 'closingUnadjusted'
  | 'closingAdjustment'
  | 'reasonAnalysis'

export interface G2AdjudicationRow {
  rowKey: string
  id: string
  item: string
  label: string
  kind: G2AdjRowDef['kind']
  section?: G2AdjSection
  methodKey?: string
  indent: number
  editable: boolean
  openingUnadjusted: number
  openingAdjustment: number
  openingAudited: number
  /** @deprecated alias → openingAudited */
  openingAdjusted: number
  closingUnadjusted: number
  closingAdjustment: number
  closingAudited: number
  /** @deprecated alias → closingAudited */
  closingAdjusted: number
  changeAmount: number
  changeRate: number | '' | 'N/A'
  reasonAnalysis: string
  changeRateHighlight: boolean
  reasonRequired: boolean
  indexRef: string
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
    changeRate: '' as const,
    reasonAnalysis: '',
    changeRateHighlight: false,
    reasonRequired: false,
  }
}

function withDerived(
  base: Omit<
    G2AdjudicationRow,
    | 'openingAudited'
    | 'closingAudited'
    | 'openingAdjusted'
    | 'closingAdjusted'
    | 'changeAmount'
    | 'changeRate'
    | 'changeRateHighlight'
    | 'reasonRequired'
    | 'id'
    | 'item'
    | 'indexRef'
  > & {
    openingAudited?: number
    closingAudited?: number
  },
): G2AdjudicationRow {
  const openingAudited =
    base.openingAudited ??
    calcAuditedAmount(base.openingUnadjusted, base.openingAdjustment, 0)
  const closingAudited =
    base.closingAudited ??
    calcAuditedAmount(base.closingUnadjusted, base.closingAdjustment, 0)
  const changeAmount = calcChangeAmount(closingAudited, openingAudited)
  const changeRate = calcChangeRate(openingAudited, closingAudited)
  const highlight = isChangeRateExceeding(changeRate, G2_CHANGE_RATE_THRESHOLD)
  return {
    ...base,
    id: base.rowKey,
    item: base.label,
    indexRef: '',
    openingAudited,
    closingAudited,
    openingAdjusted: openingAudited,
    closingAdjusted: closingAudited,
    changeAmount,
    changeRate,
    changeRateHighlight: highlight,
    reasonRequired: highlight,
  }
}

function sumKeys(
  map: Map<string, G2AdjudicationRow>,
  keys: string[],
  field:
    | 'openingUnadjusted'
    | 'openingAdjustment'
    | 'closingUnadjusted'
    | 'closingAdjustment'
    | 'openingAudited'
    | 'closingAudited',
): number {
  return calcSubtotal(keys.map((k) => map.get(k)?.[field] ?? 0))
}

/** 供单测：由持久化 store 构建完整审定表行 */
export function buildG2AdjudicationRows(store: G2AdjRowStore): G2AdjudicationRow[] {
  return buildRows(store)
}

function buildRows(store: G2AdjRowStore): G2AdjudicationRow[] {
  const byKey = new Map<string, G2AdjudicationRow>()

  for (const def of G2_ADJUDICATION_ITEMS) {
    if (def.kind === 'section_header') {
      byKey.set(
        def.rowKey,
        withDerived({
          rowKey: def.rowKey,
          label: def.label,
          kind: def.kind,
          section: def.section,
          indent: def.indent ?? 0,
          editable: false,
          ...emptyAmounts(),
        }),
      )
      continue
    }

    if (def.kind === 'leaf' && def.editable) {
      const raw = store[def.rowKey] ?? {}
      byKey.set(
        def.rowKey,
        withDerived({
          rowKey: def.rowKey,
          label: def.label,
          kind: def.kind,
          section: def.section,
          methodKey: def.methodKey,
          indent: def.indent ?? 0,
          editable: true,
          openingUnadjusted: parseNum(raw.openingUnadjusted),
          openingAdjustment: parseNum(raw.openingAdjustment),
          closingUnadjusted: parseNum(raw.closingUnadjusted),
          closingAdjustment: parseNum(raw.closingAdjustment),
          reasonAnalysis: String(raw.reasonAnalysis ?? ''),
        }),
      )
      continue
    }

    byKey.set(
      def.rowKey,
      withDerived({
        rowKey: def.rowKey,
        label: def.label,
        kind: def.kind,
        section: def.section,
        indent: def.indent ?? 0,
        editable: false,
        ...emptyAmounts(),
      }),
    )
  }

  // 原值 / 坏账小计
  for (const section of ['gross', 'provision'] as const) {
    const keys = leafKeysForSection(section)
    const subKey = `${section}__subtotal`
    byKey.set(
      subKey,
      withDerived({
        rowKey: subKey,
        label: '小计',
        kind: 'section_subtotal',
        section,
        indent: 0,
        editable: false,
        openingUnadjusted: sumKeys(byKey, keys, 'openingUnadjusted'),
        openingAdjustment: sumKeys(byKey, keys, 'openingAdjustment'),
        closingUnadjusted: sumKeys(byKey, keys, 'closingUnadjusted'),
        closingAdjustment: sumKeys(byKey, keys, 'closingAdjustment'),
        reasonAnalysis: '',
      }),
    )
  }

  // 净值 = 原值小计 − 坏账小计
  const gross = byKey.get('gross__subtotal')
  const provision = byKey.get('provision__subtotal')
  byKey.set(
    'net__row',
    withDerived({
      rowKey: 'net__row',
      label: '三、应收利息净值',
      kind: 'net_row',
      section: 'net',
      indent: 0,
      editable: false,
      openingUnadjusted: (gross?.openingUnadjusted ?? 0) - (provision?.openingUnadjusted ?? 0),
      openingAdjustment: (gross?.openingAdjustment ?? 0) - (provision?.openingAdjustment ?? 0),
      closingUnadjusted: (gross?.closingUnadjusted ?? 0) - (provision?.closingUnadjusted ?? 0),
      closingAdjustment: (gross?.closingAdjustment ?? 0) - (provision?.closingAdjustment ?? 0),
      openingAudited: (gross?.openingAudited ?? 0) - (provision?.openingAudited ?? 0),
      closingAudited: (gross?.closingAudited ?? 0) - (provision?.closingAudited ?? 0),
      reasonAnalysis: '',
    }),
  )

  // 合计 = 净值（列报口径）
  const net = byKey.get('net__row')
  byKey.set(
    'footer-total',
    withDerived({
      rowKey: 'footer-total',
      label: '合计',
      kind: 'footer',
      indent: 0,
      editable: false,
      openingUnadjusted: net?.openingUnadjusted ?? 0,
      openingAdjustment: net?.openingAdjustment ?? 0,
      closingUnadjusted: net?.closingUnadjusted ?? 0,
      closingAdjustment: net?.closingAdjustment ?? 0,
      openingAudited: net?.openingAudited ?? 0,
      closingAudited: net?.closingAudited ?? 0,
      reasonAnalysis: '',
    }),
  )

  return G2_ADJUDICATION_ITEMS.map((def) => byKey.get(def.rowKey)!).filter(Boolean)
}

function readRemark(
  allResponses: Map<string, ChecklistResponse>,
  primary: string,
  legacy?: string,
): string {
  return allResponses.get(primary)?.remark
    || (legacy ? allResponses.get(legacy)?.remark : undefined)
    || ''
}

export interface UseG2AdjudicationOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}

export function useG2Adjudication(options: UseG2AdjudicationOptions) {
  const _auditYearRef = useWorkpaperAuditYear()

  const { allResponses, projectId, isReadonly } = options
  const readonly = isReadonly ?? ref(false)

  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  const auditNote = ref('')
  const auditConclusion = ref('')
  const rowStore = ref<G2AdjRowStore>({})

  function hydrateStore(): void {
    const raw = readRemark(allResponses.value, ITEM_ID_ROWS, ITEM_ID_ROWS_LEGACY)
    rowStore.value = parseG2AdjStore(raw)
  }

  watch(
    () => [
      allResponses.value.get(ITEM_ID_ROWS)?.remark,
      allResponses.value.get(ITEM_ID_ROWS_LEGACY)?.remark,
    ],
    () => hydrateStore(),
    { immediate: true },
  )

  const dataRows: ComputedRef<G2AdjudicationRow[]> = computed(() =>
    buildRows(rowStore.value),
  )

  const subtotalRow: ComputedRef<G2AdjudicationRow> = computed(() => {
    const total = dataRows.value.find((r) => r.rowKey === 'footer-total')
    return (
      total ??
      withDerived({
        rowKey: 'subtotal',
        label: '合计',
        kind: 'footer',
        indent: 0,
        editable: false,
        ...emptyAmounts(),
      })
    )
  })

  const trialBalanceAmount: ComputedRef<number> = computed(() =>
    parseNum(readRemark(allResponses.value, ITEM_ID_TB, ITEM_ID_TB_LEGACY)),
  )

  const variance: ComputedRef<number> = computed(
    () => subtotalRow.value.closingAudited - trialBalanceAmount.value,
  )

  const hasVarianceHighlight: ComputedRef<boolean> = computed(
    () => Math.abs(variance.value) > 0.005,
  )

  watch(
    () => readRemark(allResponses.value, ITEM_ID_NOTE, ITEM_ID_NOTE_LEGACY),
    (v) => {
      auditNote.value = v || ''
    },
    { immediate: true },
  )
  watch(
    () => readRemark(allResponses.value, ITEM_ID_CONCLUSION, ITEM_ID_CONCLUSION_LEGACY),
    (v) => {
      auditConclusion.value = v || ''
    },
    { immediate: true },
  )

  function publishAdjudicated(): void {
    const amount = subtotalRow.value.closingAudited
    const payload = {
      wpCode: 'G2',
      accountCode: G2_ACCOUNT_CODE,
      adjudicatedAmount: amount,
      auditedAmount: amount,
      priorAudited: subtotalRow.value.openingAudited,
    }
    try {
      window.dispatchEvent(new CustomEvent('substantive:adjudicated', { detail: payload }))
      window.dispatchEvent(
        new CustomEvent('g2:writeback-trial-balance', {
          detail: {
            accountCode: G2_ACCOUNT_CODE,
            auditedAmount: amount,
          },
        }),
      )
    } catch {
      /* ignore */
    }
  }

  watch(
    () => subtotalRow.value.closingAudited,
    () => {
      publishAdjudicated()
    },
  )

  function updateField(rowKey: string, field: G2AdjEditableField, value: number | string): void {
    if (readonly.value) return
    const def = G2_ADJUDICATION_ITEMS.find((d) => d.rowKey === rowKey)
    if (!def?.editable) return
    const prev = rowStore.value[rowKey] ?? {}
    const next = { ...prev }
    if (field === 'reasonAnalysis') {
      next.reasonAnalysis = String(value ?? '')
    } else {
      next[field] = typeof value === 'number' ? value : parseNum(value)
    }
    rowStore.value = { ...rowStore.value, [rowKey]: next }
    persistStore()
  }

  /** @deprecated 兼容旧 API */
  function updateCell(rowKey: string, field: string, value: number | string): void {
    const fieldMap: Record<string, G2AdjEditableField> = {
      openingUnadjusted: 'openingUnadjusted',
      openingAJE: 'openingAdjustment',
      openingRJE: 'openingAdjustment',
      openingAdjustment: 'openingAdjustment',
      closingUnadjusted: 'closingUnadjusted',
      closingAJE: 'closingAdjustment',
      closingRJE: 'closingAdjustment',
      closingAdjustment: 'closingAdjustment',
      reasonAnalysis: 'reasonAnalysis',
      indexRef: 'reasonAnalysis',
    }
    const mapped = fieldMap[field]
    if (!mapped) return
    updateField(rowKey, mapped, value)
  }

  function setTrialBalance(amount: number): void {
    allResponses.value.set(ITEM_ID_TB, {
      item_id: ITEM_ID_TB,
      conclusion: null,
      remark: String(amount),
    })
    debounceSave()
  }

  /**
   * 从 G2-2 / G2-3 汇总未审数（保留已有账项调整与差异分析）。
   * - 原值：G2-2 期末应收（Stage3→单项，其余→组合）；期初取 agingPrior 合计
   * - 坏账：G2-3 单项/组合期末审定
   */
  function syncFromSupporting(): { gross: number; provision: number } {
    if (readonly.value) return { gross: 0, provision: 0 }
    const details = loadG2DetailPartials(allResponses.value)
    const leaves = loadG2BadDebtLeaves(allResponses.value)
    const gross = aggregateGrossFromDetail(details)
    const provision = aggregateProvisionFromBadDebt(leaves)

    const next: G2AdjRowStore = { ...rowStore.value }
    const writeLeaf = (
      rowKey: string,
      openingUnadjusted: number,
      closingUnadjusted: number,
    ) => {
      const prev = next[rowKey] ?? {}
      next[rowKey] = {
        ...prev,
        openingUnadjusted,
        closingUnadjusted,
        openingAdjustment: parseNum(prev.openingAdjustment),
        closingAdjustment: parseNum(prev.closingAdjustment),
        reasonAnalysis: prev.reasonAnalysis ?? '',
      }
    }

    writeLeaf('gross-individual', gross.individualOpening, gross.individualClosing)
    writeLeaf('gross-collective', gross.collectiveOpening, gross.collectiveClosing)
    writeLeaf('provision-individual', provision.individualOpening, provision.individualClosing)
    writeLeaf('provision-collective', provision.collectiveOpening, provision.collectiveClosing)

    rowStore.value = next
    persistStore()
    publishAdjudicated()
    return {
      gross: details.length,
      provision: leaves.length,
    }
  }

  /** 拉取试算 1132（优先 audited_amount / unadjusted_amount） */
  async function fetchTrialBalance(): Promise<number | null> {
    const _year = _auditYearRef.value
    if (_year == null) return null
    const pid = projectId.value
    if (!pid) return null
    try {
      const res = await api.get(`/api/projects/${pid}/trial-balance`, {
        params: { year: _year, account_prefix: G2_ACCOUNT_CODE  },
        _silent: true,
      } as any)
      const list = Array.isArray(res?.data ?? res)
        ? (res?.data ?? res)
        : (res?.data?.items ?? [])
      const hit = list.find((r: any) =>
        String(r.standard_account_code ?? r.account_code ?? '').startsWith(G2_ACCOUNT_CODE),
      )
      if (!hit) return null
      const amount = parseNum(
        hit.audited_amount ?? hit.unadjusted_amount ?? hit.ending_balance
          ?? ((Number(hit.debit_amount ?? 0) - Number(hit.credit_amount ?? 0))),
      )
      setTrialBalance(amount)
      return amount
    } catch {
      return null
    }
  }

  function applyAdjustmentWriteback(netAdjustment: number, rowKey = G2_ADJ_WRITEBACK_ROW_KEY): void {
    if (readonly.value) return
    rowStore.value = applyG2AdjustmentWriteback(rowStore.value, netAdjustment, rowKey)
    persistStore()
    publishAdjudicated()
  }

  function persistStore(): void {
    const json = JSON.stringify(rowStore.value)
    allResponses.value.set(ITEM_ID_ROWS, {
      item_id: ITEM_ID_ROWS,
      conclusion: null,
      remark: json,
    })
    debounceSave()
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
      const items = [
        allResponses.value.get(ITEM_ID_ROWS),
        allResponses.value.get(ITEM_ID_NOTE),
        allResponses.value.get(ITEM_ID_CONCLUSION),
        allResponses.value.get(ITEM_ID_TB),
      ].filter(Boolean)
      window.dispatchEvent(new CustomEvent('g2:save-items', { detail: { items } }))
    } catch {
      /* silent */
    }
  }

  watch(auditNote, (val) => {
    allResponses.value.set(ITEM_ID_NOTE, {
      item_id: ITEM_ID_NOTE,
      conclusion: null,
      remark: val,
    })
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

  /** G2-5「写入对照」后即时刷新本表审计说明 */
  function handleCalcCrossRef(e: Event): void {
    const note = (e as CustomEvent<{ note?: string }>).detail?.note
    if (typeof note === 'string' && note !== auditNote.value) {
      auditNote.value = note
    }
  }

  function handleAdjustmentConfirmed(e: Event): void {
    const d = (e as CustomEvent<{ netAdjustment?: number; rowKey?: string }>).detail
    if (d?.netAdjustment == null) return
    const rowKey = d.rowKey || G2_ADJ_WRITEBACK_ROW_KEY
    const net = Number(d.netAdjustment)
    // G2-4 已直接写过 G2-1-rows 时，本地 store 经 watch 已同步；避免重复 persist
    const prev = parseNum(rowStore.value[rowKey]?.closingAdjustment)
    if (Math.abs(prev - net) < 0.005) {
      publishAdjudicated()
      return
    }
    applyAdjustmentWriteback(net, rowKey)
  }

  onMounted(() => {
    window.addEventListener('g2:calc-cross-ref', handleCalcCrossRef)
    window.addEventListener('g2:adjustment-confirmed', handleAdjustmentConfirmed)
  })

  onBeforeUnmount(() => {
    window.removeEventListener('g2:calc-cross-ref', handleCalcCrossRef)
    window.removeEventListener('g2:adjustment-confirmed', handleAdjustmentConfirmed)
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
      flushSave()
    }
  })

  return {
    dataRows,
    rows: dataRows,
    subtotalRow,
    trialBalanceAmount,
    variance,
    hasVarianceHighlight,
    auditNote,
    auditConclusion,
    updateField,
    updateCell,
    setTrialBalance,
    fetchTrialBalance,
    syncFromSupporting,
    applyAdjustmentWriteback,
    publishAdjudicated,
    G2_CHANGE_RATE_THRESHOLD,
  }
}

export default useG2Adjudication
