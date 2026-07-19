import { useWorkpaperAuditYear } from './workpaperAuditYear'
/**
 * useG5Adjudication ??G5-1 ???????? Excel ????
 *
 * ???????????/??/??/????/?????
 *       ??????????
 *       ??????= ????????????????
 *       ?????? / ????
 * ??????= ?? + ???? + ??????|???|>30% ??????
 */
import { ref, computed, watch, onMounted, onUnmounted, type Ref } from 'vue'
import {
  parseNum,
  calcAdjustedAmount,
  calcNetValue,
  calcChangeRate,
} from '@/composables/useG5FormulaEngine'
import {
  G5_ACCOUNT_CODE,
  G5_CHANGE_RATE_THRESHOLD,
  G5_ADJUDICATION_ITEMS,
  G5_ADJ_WRITEBACK_ROW_KEY,
  leafKeysForSection,
  parseG5AdjStore,
  applyG5AdjustmentWriteback,
  type G5AdjRowDef,
  type G5AdjRowStore,
  type G5AdjRowKind,
} from './g5AdjudicationItems'
import { readCanonicalRaw } from './g5StorageContract'
import { api } from '@/services/apiProxy'
import type { ChecklistResponse } from './useF1FormData'

export { G5_ACCOUNT_CODE, G5_CHANGE_RATE_THRESHOLD, G5_ADJ_WRITEBACK_ROW_KEY }

const STORAGE_KEY = 'G5-1-rows'

export interface G5AdjudicationRow {
  rowKey: string
  id: string
  item: string
  label: string
  kind: G5AdjRowKind
  section?: string
  methodKey?: string
  indent: number
  editable: boolean
  isDerived: boolean
  openingUnadjusted: number
  openingAJE: number
  openingRJE: number
  openingAdjusted: number
  closingUnadjusted: number
  closingAJE: number
  closingRJE: number
  closingAdjusted: number
  changeAmount: number
  changeRate: number | null
  reasonAnalysis: string
  reasonRequired: boolean
}

function emptyAmounts() {
  return {
    openingUnadjusted: 0,
    openingAJE: 0,
    openingRJE: 0,
    closingUnadjusted: 0,
    closingAJE: 0,
    closingRJE: 0,
    reasonAnalysis: '',
  }
}

function withDerived(
  def: G5AdjRowDef,
  amounts: ReturnType<typeof emptyAmounts> & {
    openingAdjusted?: number
    closingAdjusted?: number
  },
): G5AdjudicationRow {
  const openingAdjusted =
    amounts.openingAdjusted
    ?? calcAdjustedAmount(amounts.openingUnadjusted, amounts.openingAJE, amounts.openingRJE)
  const closingAdjusted =
    amounts.closingAdjusted
    ?? calcAdjustedAmount(amounts.closingUnadjusted, amounts.closingAJE, amounts.closingRJE)
  const changeAmount = closingAdjusted - openingAdjusted
  const changeRate = calcChangeRate(openingAdjusted, closingAdjusted)
  const reasonRequired =
    changeRate !== null && Math.abs(changeRate) > G5_CHANGE_RATE_THRESHOLD
  const editable = !!def.editable
  return {
    rowKey: def.rowKey,
    id: def.rowKey,
    item: def.label,
    label: def.label,
    kind: def.kind,
    section: def.section,
    methodKey: def.methodKey,
    indent: def.indent ?? 0,
    editable,
    isDerived: !editable,
    openingUnadjusted: amounts.openingUnadjusted,
    openingAJE: amounts.openingAJE,
    openingRJE: amounts.openingRJE,
    openingAdjusted,
    closingUnadjusted: amounts.closingUnadjusted,
    closingAJE: amounts.closingAJE,
    closingRJE: amounts.closingRJE,
    closingAdjusted,
    changeAmount,
    changeRate,
    reasonAnalysis: amounts.reasonAnalysis || '',
    reasonRequired,
  }
}

function sumFields(
  map: Map<string, G5AdjudicationRow>,
  keys: string[],
  field:
    | 'openingUnadjusted'
    | 'openingAJE'
    | 'openingRJE'
    | 'openingAdjusted'
    | 'closingUnadjusted'
    | 'closingAJE'
    | 'closingRJE'
    | 'closingAdjusted',
): number {
  return keys.reduce((s, k) => s + parseNum(map.get(k)?.[field]), 0)
}

/** ???? UI?? store ??????*/
export function buildG5AdjudicationRows(
  store: G5AdjRowStore,
  tbClosing = 0,
): G5AdjudicationRow[] {
  const byKey = new Map<string, G5AdjudicationRow>()

  for (const def of G5_ADJUDICATION_ITEMS) {
    if (def.kind === 'section_header' || def.kind === 'group_header') {
      byKey.set(def.rowKey, withDerived(def, emptyAmounts()))
      continue
    }

    if (def.kind === 'leaf' || def.kind === 'deduction' || def.kind === 'tb_amount') {
      const saved = store[def.rowKey] || {}
      byKey.set(
        def.rowKey,
        withDerived(def, {
          openingUnadjusted: parseNum(saved.openingUnadjusted),
          openingAJE: parseNum(saved.openingAJE),
          openingRJE: parseNum(saved.openingRJE),
          closingUnadjusted: parseNum(saved.closingUnadjusted),
          closingAJE: parseNum(saved.closingAJE),
          closingRJE: parseNum(saved.closingRJE),
          reasonAnalysis: String(saved.reasonAnalysis ?? ''),
        }),
      )
      continue
    }

    // placeholder??????
    byKey.set(def.rowKey, withDerived(def, emptyAmounts()))
  }

  // ?? = ?? + ????
  for (const section of ['gross', 'provision'] as const) {
    const keys = leafKeysForSection(section)
    const sub = byKey.get(`${section}__subtotal`)
    if (sub) {
      byKey.set(
        `${section}__subtotal`,
        withDerived(
          G5_ADJUDICATION_ITEMS.find((d) => d.rowKey === `${section}__subtotal`)!,
          {
            ...emptyAmounts(),
            openingUnadjusted: sumFields(byKey, keys, 'openingUnadjusted'),
            openingAJE: sumFields(byKey, keys, 'openingAJE'),
            openingRJE: sumFields(byKey, keys, 'openingRJE'),
            closingUnadjusted: sumFields(byKey, keys, 'closingUnadjusted'),
            closingAJE: sumFields(byKey, keys, 'closingAJE'),
            closingRJE: sumFields(byKey, keys, 'closingRJE'),
          },
        ),
      )
    }

    // ?????= ?? ?????
    const subtotal = byKey.get(`${section}__subtotal`)
    const oneYear = byKey.get(`${section}-one-year`)
    const reportableDef = G5_ADJUDICATION_ITEMS.find((d) => d.rowKey === `${section}-reportable`)!
    byKey.set(
      `${section}-reportable`,
      withDerived(reportableDef, {
        ...emptyAmounts(),
        openingAdjusted: parseNum(subtotal?.openingAdjusted) - parseNum(oneYear?.openingAdjusted),
        closingAdjusted: parseNum(subtotal?.closingAdjusted) - parseNum(oneYear?.closingAdjusted),
        openingUnadjusted: parseNum(subtotal?.openingAdjusted) - parseNum(oneYear?.openingAdjusted),
        closingUnadjusted: parseNum(subtotal?.closingAdjusted) - parseNum(oneYear?.closingAdjusted),
      }),
    )
  }

  // ??????= ????????????????
  const grossR = byKey.get('gross-reportable')
  const provR = byKey.get('provision-reportable')
  const netDef = G5_ADJUDICATION_ITEMS.find((d) => d.rowKey === 'net__row')!
  byKey.set(
    'net__row',
    withDerived(netDef, {
      ...emptyAmounts(),
      openingAdjusted: calcNetValue(grossR?.openingAdjusted, provR?.openingAdjusted),
      closingAdjusted: calcNetValue(grossR?.closingAdjusted, provR?.closingAdjusted),
      openingUnadjusted: calcNetValue(grossR?.openingAdjusted, provR?.openingAdjusted),
      closingUnadjusted: calcNetValue(grossR?.closingAdjusted, provR?.closingAdjusted),
    }),
  )

  // ???? store ???????tbClosing
  const tbDef = G5_ADJUDICATION_ITEMS.find((d) => d.rowKey === 'tb-amount')!
  const tbSaved = store['tb-amount'] || {}
  const tbClosingAmt = tbSaved.closingUnadjusted != null
    ? parseNum(tbSaved.closingUnadjusted)
    : tbClosing
  byKey.set(
    'tb-amount',
    withDerived(tbDef, {
      ...emptyAmounts(),
      openingUnadjusted: parseNum(tbSaved.openingUnadjusted),
      closingUnadjusted: tbClosingAmt,
      // ????????????????????
      openingAdjusted: parseNum(tbSaved.openingUnadjusted),
      closingAdjusted: tbClosingAmt,
    }),
  )

  const net = byKey.get('net__row')
  const tb = byKey.get('tb-amount')
  const diffDef = G5_ADJUDICATION_ITEMS.find((d) => d.rowKey === 'tb-diff')!
  byKey.set(
    'tb-diff',
    withDerived(diffDef, {
      ...emptyAmounts(),
      openingAdjusted: parseNum(net?.openingAdjusted) - parseNum(tb?.openingAdjusted),
      closingAdjusted: parseNum(net?.closingAdjusted) - parseNum(tb?.closingAdjusted),
      openingUnadjusted: parseNum(net?.openingAdjusted) - parseNum(tb?.openingAdjusted),
      closingUnadjusted: parseNum(net?.closingAdjusted) - parseNum(tb?.closingAdjusted),
    }),
  )

  return G5_ADJUDICATION_ITEMS.map((d) => byKey.get(d.rowKey)!).filter(Boolean)
}

export function useG5Adjudication(opts: {
  wpId: any
  projectId: any
  htmlData: any
  isReadonly: any
  allResponses?: Ref<Map<string, ChecklistResponse>>
  debouncedSave?: (itemId: string, data: Partial<ChecklistResponse>) => void
}) {
  const _auditYearRef = useWorkpaperAuditYear()
  const store = ref<G5AdjRowStore>({})
  const tbValues = ref<{ opening: number; closing: number }>({ opening: 0, closing: 0 })
  let suppressPersist = false

  const isReadonly = computed(() => !!opts.isReadonly?.value || !!opts.isReadonly)

  const rows = computed(() => buildG5AdjudicationRows(store.value, tbValues.value.closing))

  const variance = computed(() => {
    const diff = rows.value.find((r) => r.rowKey === 'tb-diff')
    return diff?.closingAdjusted ?? 0
  })

  const adjudicatedAmount = computed(() => {
    const net = rows.value.find((r) => r.rowKey === 'net__row')
    return net?.closingAdjusted ?? 0
  })

  function serialize(): string {
    // ?? keyed store????G2-1????IE keyed_by round-trip
    return JSON.stringify(store.value)
  }

  function persist(): void {
    if (suppressPersist || isReadonly.value || !opts.debouncedSave) return
    const json = serialize()
    opts.debouncedSave(STORAGE_KEY, { remark: json, conclusion: json })
  }

  function hydrateFromStore(): void {
    const raw = readCanonicalRaw(opts.allResponses?.value.get(STORAGE_KEY))
    suppressPersist = true
    store.value = parseG5AdjStore(raw)
    // ??????????? tbValues
    if (store.value['tb-amount']?.closingUnadjusted == null && tbValues.value.closing) {
      store.value = {
        ...store.value,
        'tb-amount': {
          ...(store.value['tb-amount'] || {}),
          closingUnadjusted: tbValues.value.closing,
          openingUnadjusted: tbValues.value.opening,
        },
      }
    }
    suppressPersist = false
  }

  function hydrateTb(): void {
    const hd = opts.htmlData?.value ?? opts.htmlData
    const tb = hd?.tb_values ?? hd?.tbValues ?? hd?.trial_balance ?? null
    if (!tb) return
    tbValues.value = {
      opening: parseNum(tb.opening ?? tb.opening_balance ?? tb.begin),
      closing: parseNum(tb.closing ?? tb.closing_balance ?? tb.end ?? tb.balance),
    }
  }

  function updateField(
    rowKey: string,
    field:
      | 'openingUnadjusted'
      | 'openingAJE'
      | 'openingRJE'
      | 'closingUnadjusted'
      | 'closingAJE'
      | 'closingRJE'
      | 'reasonAnalysis',
    value: number | string,
  ): void {
    if (isReadonly.value) return
    const prev = store.value[rowKey] || {}
    if (field === 'reasonAnalysis') {
      store.value = { ...store.value, [rowKey]: { ...prev, reasonAnalysis: String(value ?? '') } }
    } else {
      store.value = { ...store.value, [rowKey]: { ...prev, [field]: parseNum(value) } }
    }
    persist()
  }

  function applyAdjustmentWriteback(
    netAje: number,
    netRje: number,
    rowKey = G5_ADJ_WRITEBACK_ROW_KEY,
  ): void {
    suppressPersist = true
    store.value = applyG5AdjustmentWriteback(store.value, parseNum(netAje), parseNum(netRje), rowKey)
    suppressPersist = false
    persist()
  }

  function handleAdjustmentConfirmed(e: Event): void {
    const d = (e as CustomEvent).detail || {}
    if (d.writebacks && typeof d.writebacks === 'object') {
      const wb = d.writebacks as Record<string, { aje?: number; rje?: number }>
      const keys: Array<{ bucket: string; rowKey: string }> = [
        { bucket: 'gross', rowKey: G5_ADJ_WRITEBACK_ROW_KEY },
        { bucket: 'provision', rowKey: 'provision-collective-business' },
        { bucket: 'oneYear', rowKey: 'gross-one-year' },
      ]
      for (const { bucket, rowKey } of keys) {
        const nets = wb[bucket]
        if (!nets) continue
        applyAdjustmentWriteback(parseNum(nets.aje), parseNum(nets.rje), rowKey)
      }
      return
    }
    // 兼容旧事件：仅原值桶
    if (d.accountCode && d.accountCode !== G5_ACCOUNT_CODE) return
    applyAdjustmentWriteback(
      parseNum(d.netAje),
      parseNum(d.netRje),
      d.rowId === 'gross-total' ? G5_ADJ_WRITEBACK_ROW_KEY : (d.rowId || G5_ADJ_WRITEBACK_ROW_KEY),
    )
  }

  /** ??G5-2 / G5-3 checklist ???????*/
  function applyFromDetailTotals(optsIn: {
    individualGross?: number
    businessGross?: number
    customerGross?: number
    individualProvision?: number
    businessProvision?: number
    customerProvision?: number
    oneYearGross?: number
    oneYearProvision?: number
  }): void {
    const patch = (key: string, closingUnadjusted: number | undefined) => {
      if (closingUnadjusted == null) return
      const prev = store.value[key] || {}
      store.value[key] = { ...prev, closingUnadjusted: parseNum(closingUnadjusted) }
    }
    suppressPersist = true
    patch('gross-individual', optsIn.individualGross)
    patch('gross-collective-business', optsIn.businessGross)
    patch('gross-collective-customer', optsIn.customerGross)
    patch('provision-individual', optsIn.individualProvision)
    patch('provision-collective-business', optsIn.businessProvision)
    patch('provision-collective-customer', optsIn.customerProvision)
    patch('gross-one-year', optsIn.oneYearGross)
    patch('provision-one-year', optsIn.oneYearProvision)
    store.value = { ...store.value }
    suppressPersist = false
    persist()
  }

  function publishAdjudicated(): void {
    const amount = adjudicatedAmount.value
    try {
      window.dispatchEvent(new CustomEvent('substantive:adjudicated', {
        detail: {
          wpCode: 'G5',
          accountCode: G5_ACCOUNT_CODE,
          adjudicatedAmount: amount,
          auditedAmount: amount,
        },
      }))
      window.dispatchEvent(new CustomEvent('g5:writeback-trial-balance', {
        detail: {
          accountCode: G5_ACCOUNT_CODE,
          auditedAmount: amount,
        },
      }))
    } catch { /* silent */ }
  }

  /** ???? 1531 */
  async function fetchTrialBalance(projectId?: string): Promise<number | null> {
    const _year = _auditYearRef.value
    if (_year == null) return null
    const pid = projectId || (typeof opts.projectId === 'object' ? opts.projectId?.value : opts.projectId)
    if (!pid) return null
    try {
      const res = await api.get(`/api/projects/${pid}/trial-balance`, {
        params: { year: _year, account_prefix: G5_ACCOUNT_CODE  },
        _silent: true,
      } as any)
      const list = Array.isArray(res?.data ?? res)
        ? (res?.data ?? res)
        : (res?.data?.items ?? [])
      const hit = list.find((r: any) =>
        String(r.standard_account_code ?? r.account_code ?? '').startsWith(G5_ACCOUNT_CODE),
      )
      if (!hit) return null
      const amount = parseNum(
        hit.audited_amount ?? hit.unadjusted_amount ?? hit.ending_balance
          ?? (Number(hit.debit_amount ?? 0) - Number(hit.credit_amount ?? 0)),
      )
      tbValues.value = { ...tbValues.value, closing: amount }
      updateField('tb-amount', 'closingUnadjusted', amount)
      return amount
    } catch {
      return null
    }
  }

  const needsReason = (row: G5AdjudicationRow) => row.reasonRequired

  watch(adjudicatedAmount, () => { publishAdjudicated() })

  watch(
    () => readCanonicalRaw(opts.allResponses?.value.get(STORAGE_KEY)),
    () => hydrateFromStore(),
  )

  onMounted(() => {
    hydrateTb()
    hydrateFromStore()
    window.addEventListener('g5:adjustment-confirmed', handleAdjustmentConfirmed)
  })

  onUnmounted(() => {
    window.removeEventListener('g5:adjustment-confirmed', handleAdjustmentConfirmed)
  })

  return {
    rows,
    store,
    tbValues,
    variance,
    adjudicatedAmount,
    updateField,
    needsReason,
    applyAdjustmentWriteback,
    applyFromDetailTotals,
    hydrateFromStore,
    publishAdjudicated,
    fetchTrialBalance,
    STORAGE_KEY,
    /** @deprecated ????UI ?? */
    allRows: rows,
    onCellChange: (_row: G5AdjudicationRow) => { persist() },
    recalcDerived: () => { /* computed ?? */ },
    groups: computed(() => []),
  }
}
