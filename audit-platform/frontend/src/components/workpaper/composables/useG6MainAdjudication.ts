/**
 * useG6MainAdjudication — G6-1 审定表（对齐 Excel《审定表G6-1》）
 *
 * 公式：
 *   审定 = 未审 + 账项调整
 *   账面余额叶子 = 对应成本审定 + 利息调整审定
 *   账面价值叶子 = 账面余额审定 − 减值审定
 *   层小计净额 = 小计 − 一年内到期
 *   账面一年内到期 = 成本一年内 + 利息一年内
 *   账面价值一年内到期 = 账面一年内 − 减值一年内
 *   差异数 = 账面价值合计期末审定 − 试算平衡表数
 *
 * EventBus: substantive:adjudicated(accountCode='1503')
 */
import { ref, computed, watch, onMounted, onBeforeUnmount, getCurrentInstance, type Ref } from 'vue'
import {
  G6_ACCOUNT_CODE,
  G6_CHANGE_RATE_THRESHOLD,
  G6_ADJUDICATION_ITEMS,
  G6_FV_LEAF_KEYS,
  parseG6AdjStore,
  applyG6AdjustmentWriteback,
  applyG6SplitAdjustmentWriteback,
  applyG6MultiAdjustmentWriteback,
  listG6WritebackAllocTargets,
  type G6AdjRowDef,
  type G6AdjRowStore,
  type G6AdjSection,
} from './g6AdjudicationItems'
import {
  parseNum,
  calcChangeRate,
  calcAdjustedAmount,
  calcSubtotal,
  calcAdjustedBookValue,
} from '@/composables/useG6MainFormulaEngine'
import { api } from '@/services/apiProxy'
import type { ChecklistResponse } from './useF1FormData'

export {
  G6_ACCOUNT_CODE,
  G6_CHANGE_RATE_THRESHOLD,
  applyG6AdjustmentWriteback,
  applyG6SplitAdjustmentWriteback,
  applyG6MultiAdjustmentWriteback,
  listG6WritebackAllocTargets,
}

const ITEM_ID_ROWS = 'G6-1-rows'
const ITEM_ID_TB = 'G6-1-adj-tb-1503'
const ITEM_ID_NOTE = 'G6-1-adjudication-audit-note'
const ITEM_ID_CONCLUSION = 'G6-1-adjudication-audit-conclusion'

export type G6AdjEditableField =
  | 'openingUnadjusted'
  | 'openingAdjustment'
  | 'closingUnadjusted'
  | 'closingAdjustment'
  | 'reasonAnalysis'
  | 'itemLabel'

export interface G6AdjudicationRow {
  rowKey: string
  label: string
  kind: G6AdjRowDef['kind']
  section?: G6AdjSection
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
}

function audited(unadj: number, adj: number): number {
  return calcAdjustedAmount(unadj, adj)
}

function rateFlags(rate: number | null) {
  const highlight = rate != null && Math.abs(rate) > G6_CHANGE_RATE_THRESHOLD
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
    G6AdjudicationRow,
    | 'openingAudited'
    | 'closingAudited'
    | 'changeAmount'
    | 'changeRate'
    | 'changeRateHighlight'
    | 'reasonRequired'
  > & { openingAudited?: number; closingAudited?: number },
): G6AdjudicationRow {
  const openingAudited =
    base.openingAudited ?? audited(base.openingUnadjusted, base.openingAdjustment)
  const closingAudited =
    base.closingAudited ?? audited(base.closingUnadjusted, base.closingAdjustment)
  const changeAmount = Math.round((closingAudited - openingAudited) * 100) / 100
  const changeRate = calcChangeRate(openingAudited, closingAudited)
  return {
    ...base,
    openingAudited,
    closingAudited,
    changeAmount,
    changeRate,
    ...rateFlags(changeRate),
  }
}

function cellOf(store: G6AdjRowStore, key: string) {
  const c = store[key] ?? {}
  return {
    openingUnadjusted: parseNum(c.openingUnadjusted),
    openingAdjustment: parseNum(c.openingAdjustment),
    closingUnadjusted: parseNum(c.closingUnadjusted),
    closingAdjustment: parseNum(c.closingAdjustment),
    reasonAnalysis: String(c.reasonAnalysis || ''),
    itemLabel: c.itemLabel,
  }
}

function amortLeafKeys(section: 'cost' | 'interest' | 'impairment' | 'book' | 'carrying') {
  return [`${section}-individual`, `${section}-portfolio`] as const
}

export interface UseG6MainAdjudicationOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
  htmlData?: Ref<Record<string, any> | null>
}

export function useG6MainAdjudication(options: UseG6MainAdjudicationOptions) {
  const { projectId, allResponses, isReadonly, htmlData } = options
  const readonly = isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  const auditNote = ref('')
  const auditConclusion = ref('')
  const lastWritebackNet = ref(0)

  function readRawStore(): G6AdjRowStore {
    const primary = allResponses.value.get(ITEM_ID_ROWS)
    const primaryRaw = primary?.conclusion || primary?.remark
    if (primaryRaw) return parseG6AdjStore(primaryRaw)

    // htmlData 旧版 sections
    const data = htmlData?.value
    if (data) {
      const fromHtml = parseG6AdjStore(JSON.stringify(data.sections ?? data))
      if (Object.keys(fromHtml).length) return fromHtml
    }
    return {}
  }

  const store = computed(() => readRawStore())

  const trialBalanceAmount = computed(() =>
    parseNum(allResponses.value.get(ITEM_ID_TB)?.remark),
  )

  function buildEditableLeaf(def: G6AdjRowDef, s: G6AdjRowStore): G6AdjudicationRow {
    const cell = cellOf(s, def.rowKey)
    const label =
      def.section === 'fv' && cell.itemLabel
        ? String(cell.itemLabel)
        : def.label
    return withDerived({
      rowKey: def.rowKey,
      label,
      kind: def.kind,
      section: def.section,
      indent: def.indent ?? 0,
      editable: !!def.editable,
      openingUnadjusted: cell.openingUnadjusted,
      openingAdjustment: cell.openingAdjustment,
      closingUnadjusted: cell.closingUnadjusted,
      closingAdjustment: cell.closingAdjustment,
      reasonAnalysis: cell.reasonAnalysis,
    })
  }

  /** 账面余额叶子 = 成本 + 利息 */
  function buildBookLeaf(suffix: 'individual' | 'portfolio', s: G6AdjRowStore): G6AdjudicationRow {
    const cost = cellOf(s, `cost-${suffix}`)
    const interest = cellOf(s, `interest-${suffix}`)
    const open = calcSubtotal(
      audited(cost.openingUnadjusted, cost.openingAdjustment),
      audited(interest.openingUnadjusted, interest.openingAdjustment),
      0,
    )
    const close = calcSubtotal(
      audited(cost.closingUnadjusted, cost.closingAdjustment),
      audited(interest.closingUnadjusted, interest.closingAdjustment),
      0,
    )
    return withDerived({
      rowKey: `book-${suffix}`,
      label: suffix === 'individual' ? '单项计提坏账准备' : '按组合计提坏账准备',
      kind: 'leaf',
      section: 'book',
      indent: 1,
      editable: false,
      openingUnadjusted: open,
      openingAdjustment: 0,
      closingUnadjusted: close,
      closingAdjustment: 0,
      reasonAnalysis: '',
      openingAudited: open,
      closingAudited: close,
    })
  }

  /** 账面价值叶子 = 账面余额 − 减值 */
  function buildCarryingLeaf(suffix: 'individual' | 'portfolio', s: G6AdjRowStore): G6AdjudicationRow {
    const book = buildBookLeaf(suffix, s)
    const imp = cellOf(s, `impairment-${suffix}`)
    const open = calcAdjustedBookValue(
      book.openingAudited,
      audited(imp.openingUnadjusted, imp.openingAdjustment),
    )
    const close = calcAdjustedBookValue(
      book.closingAudited,
      audited(imp.closingUnadjusted, imp.closingAdjustment),
    )
    return withDerived({
      rowKey: `carrying-${suffix}`,
      label: suffix === 'individual' ? '单项计提坏账准备' : '按组合计提坏账准备',
      kind: 'leaf',
      section: 'carrying',
      indent: 1,
      editable: false,
      openingUnadjusted: open,
      openingAdjustment: 0,
      closingUnadjusted: close,
      closingAdjustment: 0,
      reasonAnalysis: '',
      openingAudited: open,
      closingAudited: close,
    })
  }

  function sumFvLeaves(s: G6AdjRowStore) {
    const leaves = G6_FV_LEAF_KEYS.map((k) => {
      const def = G6_ADJUDICATION_ITEMS.find((d) => d.rowKey === k)!
      return buildEditableLeaf(def, s)
    })
    return {
      openingUnadjusted: leaves.reduce((a, r) => a + r.openingUnadjusted, 0),
      openingAdjustment: leaves.reduce((a, r) => a + r.openingAdjustment, 0),
      closingUnadjusted: leaves.reduce((a, r) => a + r.closingUnadjusted, 0),
      closingAdjustment: leaves.reduce((a, r) => a + r.closingAdjustment, 0),
      openingAudited: leaves.reduce((a, r) => a + r.openingAudited, 0),
      closingAudited: leaves.reduce((a, r) => a + r.closingAudited, 0),
    }
  }

  function sumAmortLeaves(
    section: 'cost' | 'interest' | 'impairment' | 'book' | 'carrying',
    s: G6AdjRowStore,
  ) {
    const leaves =
      section === 'book'
        ? [buildBookLeaf('individual', s), buildBookLeaf('portfolio', s)]
        : section === 'carrying'
          ? [buildCarryingLeaf('individual', s), buildCarryingLeaf('portfolio', s)]
          : amortLeafKeys(section).map((k) => {
              const def = G6_ADJUDICATION_ITEMS.find((d) => d.rowKey === k)!
              return buildEditableLeaf(def, s)
            })
    return {
      openingUnadjusted: leaves.reduce((a, r) => a + r.openingUnadjusted, 0),
      openingAdjustment: leaves.reduce((a, r) => a + r.openingAdjustment, 0),
      closingUnadjusted: leaves.reduce((a, r) => a + r.closingUnadjusted, 0),
      closingAdjustment: leaves.reduce((a, r) => a + r.closingAdjustment, 0),
      openingAudited: leaves.reduce((a, r) => a + r.openingAudited, 0),
      closingAudited: leaves.reduce((a, r) => a + r.closingAudited, 0),
    }
  }

  /** 账面一年内到期 = 成本一年内 + 利息一年内 */
  function buildBookOneYear(s: G6AdjRowStore): G6AdjudicationRow {
    const costOy = cellOf(s, 'cost__one-year')
    const intOy = cellOf(s, 'interest__one-year')
    const open = calcSubtotal(
      audited(costOy.openingUnadjusted, costOy.openingAdjustment),
      audited(intOy.openingUnadjusted, intOy.openingAdjustment),
      0,
    )
    const close = calcSubtotal(
      audited(costOy.closingUnadjusted, costOy.closingAdjustment),
      audited(intOy.closingUnadjusted, intOy.closingAdjustment),
      0,
    )
    return withDerived({
      rowKey: 'book__one-year',
      label: '减：一年内到期的部分',
      kind: 'one_year_deduct',
      section: 'book',
      indent: 0,
      editable: false,
      openingUnadjusted: open,
      openingAdjustment: 0,
      closingUnadjusted: close,
      closingAdjustment: 0,
      reasonAnalysis: '',
      openingAudited: open,
      closingAudited: close,
    })
  }

  /** 账面价值一年内到期 = 账面一年内 − 减值一年内 */
  function buildCarryingOneYear(s: G6AdjRowStore): G6AdjudicationRow {
    const bookOy = buildBookOneYear(s)
    const impOy = cellOf(s, 'impairment__one-year')
    const open = calcAdjustedBookValue(
      bookOy.openingAudited,
      audited(impOy.openingUnadjusted, impOy.openingAdjustment),
    )
    const close = calcAdjustedBookValue(
      bookOy.closingAudited,
      audited(impOy.closingUnadjusted, impOy.closingAdjustment),
    )
    return withDerived({
      rowKey: 'carrying__one-year',
      label: '减：一年内到期的部分',
      kind: 'one_year_deduct',
      section: 'carrying',
      indent: 0,
      editable: false,
      openingUnadjusted: open,
      openingAdjustment: 0,
      closingUnadjusted: close,
      closingAdjustment: 0,
      reasonAnalysis: '',
      openingAudited: open,
      closingAudited: close,
    })
  }

  const rows = computed<G6AdjudicationRow[]>(() => {
    const s = store.value
    const out: G6AdjudicationRow[] = []

    for (const def of G6_ADJUDICATION_ITEMS) {
      if (def.kind === 'section_header' || def.kind === 'subsection_header') {
        out.push(
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

      if (def.kind === 'leaf' && def.section === 'book') {
        const suffix = def.rowKey.endsWith('individual') ? 'individual' : 'portfolio'
        out.push(buildBookLeaf(suffix, s))
        continue
      }

      if (def.kind === 'leaf' && def.section === 'carrying') {
        const suffix = def.rowKey.endsWith('individual') ? 'individual' : 'portfolio'
        out.push(buildCarryingLeaf(suffix, s))
        continue
      }

      if (def.kind === 'leaf') {
        out.push(buildEditableLeaf(def, s))
        continue
      }

      if (def.kind === 'subtotal' && def.section) {
        const sum =
          def.section === 'fv'
            ? sumFvLeaves(s)
            : sumAmortLeaves(def.section as 'cost' | 'interest' | 'impairment' | 'book' | 'carrying', s)
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

      if (def.kind === 'one_year_deduct' && def.section === 'book') {
        out.push(buildBookOneYear(s))
        continue
      }

      if (def.kind === 'one_year_deduct' && def.section === 'carrying') {
        out.push(buildCarryingOneYear(s))
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
            editable: !!def.editable,
            openingUnadjusted: cell.openingUnadjusted,
            openingAdjustment: cell.openingAdjustment,
            closingUnadjusted: cell.closingUnadjusted,
            closingAdjustment: cell.closingAdjustment,
            reasonAnalysis: cell.reasonAnalysis,
          }),
        )
        continue
      }

      if (def.kind === 'section_net' && def.section) {
        const sub = out.find((r) => r.rowKey === `${def.section}__subtotal`)
        const oneYear = out.find((r) => r.rowKey === `${def.section}__one-year`)
        const openingAudited =
          Math.round(((sub?.openingAudited ?? 0) - (oneYear?.openingAudited ?? 0)) * 100) / 100
        const closingAudited =
          Math.round(((sub?.closingAudited ?? 0) - (oneYear?.closingAudited ?? 0)) * 100) / 100
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
        // Excel: 差异 = 账面价值合计 − 试算平衡表数
        const carrying = out.find((r) => r.rowKey === 'carrying__net')
        const tb = trialBalanceAmount.value
        const openVar =
          Math.round(((carrying?.openingAudited ?? 0) - 0) * 100) / 100
        const closeVar =
          Math.round(((carrying?.closingAudited ?? 0) - tb) * 100) / 100
        out.push(
          withDerived({
            rowKey: def.rowKey,
            label: def.label,
            kind: def.kind,
            indent: 0,
            editable: false,
            openingUnadjusted: openVar,
            openingAdjustment: 0,
            closingUnadjusted: closeVar,
            closingAdjustment: 0,
            reasonAnalysis: '',
            openingAudited: openVar,
            closingAudited: closeVar,
          }),
        )
      }
    }

    return out
  })

  const carryingNetRow = computed(() => rows.value.find((r) => r.rowKey === 'carrying__net'))
  const fvNetRow = computed(() => rows.value.find((r) => r.rowKey === 'fv__net'))
  const variance = computed(
    () => rows.value.find((r) => r.rowKey === 'footer-variance')?.closingAudited ?? 0,
  )
  const hasVarianceHighlight = computed(() => Math.abs(variance.value) > 0.005)

  /** 公允价值合计本期变动率（审计说明引用 Excel R64） */
  const fvChangeRate = computed(() => fvNetRow.value?.changeRate ?? null)

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

  function debounceSave(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      try {
        const items: ChecklistResponse[] = []
        const rowsItem = allResponses.value.get(ITEM_ID_ROWS)
        if (rowsItem) items.push(rowsItem)
        const tbItem = allResponses.value.get(ITEM_ID_TB)
        if (tbItem) items.push(tbItem)
        const noteItem = allResponses.value.get(ITEM_ID_NOTE)
        if (noteItem) items.push(noteItem)
        const concItem = allResponses.value.get(ITEM_ID_CONCLUSION)
        if (concItem) items.push(concItem)
        if (items.length) {
          window.dispatchEvent(new CustomEvent('g6:save-items', { detail: { items } }))
        }
      } catch { /* silent */ }
    }, 400)
  }

  function persistStore(next: G6AdjRowStore): void {
    const json = JSON.stringify(next)
    allResponses.value.set(ITEM_ID_ROWS, {
      item_id: ITEM_ID_ROWS,
      conclusion: json,
      remark: json,
    })
    debounceSave()
  }

  function setTrialBalance(amount: number): void {
    if (readonly.value) return
    allResponses.value.set(ITEM_ID_TB, {
      item_id: ITEM_ID_TB,
      conclusion: null,
      remark: String(amount),
    })
    debounceSave()
  }

  function updateCell(rowKey: string, field: G6AdjEditableField, value: number | string): void {
    if (readonly.value) return
    if (rowKey === 'footer-tb') {
      setTrialBalance(typeof value === 'number' ? value : parseNum(value))
      return
    }
    const next = { ...store.value }
    const prev = { ...(next[rowKey] ?? {}) }
    if (field === 'reasonAnalysis' || field === 'itemLabel') {
      ;(prev as any)[field] = String(value ?? '')
    } else {
      ;(prev as any)[field] = typeof value === 'number' ? value : parseNum(value)
    }
    next[rowKey] = prev
    persistStore(next)
  }

  watch(
    () => carryingNetRow.value?.closingAudited,
    (val) => {
      if (val == null) return
      try {
        api.post('/api/event-bus/publish', {
          event: 'substantive:adjudicated',
          payload: { accountCode: G6_ACCOUNT_CODE, adjudicatedAmount: val },
        }, { _silent: true } as any).catch(() => {})
      } catch { /* best-effort */ }
    },
  )

  watch(auditNote, (val) => {
    if (readonly.value) return
    allResponses.value.set(ITEM_ID_NOTE, {
      item_id: ITEM_ID_NOTE,
      conclusion: null,
      remark: val,
    })
    debounceSave()
  })

  watch(auditConclusion, (val) => {
    if (readonly.value) return
    allResponses.value.set(ITEM_ID_CONCLUSION, {
      item_id: ITEM_ID_CONCLUSION,
      conclusion: null,
      remark: val,
    })
    debounceSave()
  })

  async function fetchTrialBalance(): Promise<void> {
    if (!projectId.value) return
    if (trialBalanceAmount.value !== 0) return
    try {
      const res = await api.get('/api/trial-balance/query', {
        params: { project_id: projectId.value, account_code: G6_ACCOUNT_CODE },
        _silent: true,
      } as any)
      const items = res?.data?.items ?? res?.data ?? res?.items ?? []
      if (Array.isArray(items) && items.length > 0) {
        const sum = items.reduce(
          (acc: number, it: any) => acc + parseNum(it.audited_amount ?? it.unadjusted_amount),
          0,
        )
        setTrialBalance(sum)
      } else if (typeof res?.data === 'number') {
        setTrialBalance(res.data)
      }
    } catch {
      console.warn('[useG6MainAdjudication] fetchTrialBalance failed')
    }
  }

  function applyWriteback(net: number, rowKey?: string): void {
    const next = applyG6AdjustmentWriteback(store.value, net, rowKey)
    lastWritebackNet.value = net
    persistStore(next)
  }

  function applyMultiWriteback(nets: {
    cost?: number
    interest?: number
    impairment?: number
    fv?: number
  }): void {
    const next = applyG6MultiAdjustmentWriteback(store.value, nets)
    lastWritebackNet.value = parseNum(nets.cost) + parseNum(nets.interest)
    persistStore(next)
  }

  function onAdjustmentWriteback(e: Event): void {
    const detail = (e as CustomEvent).detail
    if (
      detail?.costNet != null
      || detail?.interestNet != null
      || detail?.impairmentNet != null
      || detail?.fvNet != null
    ) {
      applyMultiWriteback({
        cost: parseNum(detail.costNet),
        interest: parseNum(detail.interestNet),
        impairment: parseNum(detail.impairmentNet),
        fv: parseNum(detail.fvNet),
      })
      return
    }
    const summaries = detail?.summaries as
      | Array<{ accountCode: string; ajeNet?: number; rjeNet?: number; net?: number }>
      | undefined
    if (Array.isArray(summaries)) {
      let costNet = 0
      let interestNet = 0
      let impairmentNet = 0
      let fvNet = 0
      for (const item of summaries) {
        const code = String(item.accountCode || '')
        const aje = parseNum(item.ajeNet)
        if (code === '150305' || code.startsWith('150305')) {
          impairmentNet += -aje
        } else if (code === '150302' || code.startsWith('150302')) {
          interestNet += aje
        } else if (code === '150304' || code.startsWith('150304')) {
          fvNet += aje
        } else if (code.startsWith('1503')) {
          costNet += aje
        }
      }
      applyMultiWriteback({ cost: costNet, interest: interestNet, impairment: impairmentNet, fv: fvNet })
      return
    }
    if (detail?.totalAdjustment != null || detail?.ajeTotal != null) {
      applyWriteback(parseNum(detail.totalAdjustment ?? detail.ajeTotal))
    }
  }

  function attachListeners(): void {
    window.addEventListener('g6:adjustment-writeback', onAdjustmentWriteback)
    window.addEventListener('g6:adjustment-confirmed', onAdjustmentWriteback)
  }
  function detachListeners(): void {
    window.removeEventListener('g6:adjustment-writeback', onAdjustmentWriteback)
    window.removeEventListener('g6:adjustment-confirmed', onAdjustmentWriteback)
  }

  if (getCurrentInstance()) {
    onMounted(() => {
      attachListeners()
      fetchTrialBalance()
    })
    onBeforeUnmount(() => {
      detachListeners()
      if (debounceTimer) clearTimeout(debounceTimer)
    })
  } else {
    // 单测直调 composable 时仍挂载监听，并暴露 dispose 便于清理
    attachListeners()
  }

  return {
    rows,
    store,
    auditNote,
    auditConclusion,
    trialBalanceAmount,
    variance,
    hasVarianceHighlight,
    carryingNetRow,
    fvNetRow,
    fvChangeRate,
    lastWritebackNet,
    updateCell,
    setTrialBalance,
    applyWriteback,
    applyMultiWriteback,
    fetchTrialBalance,
    dispose: detachListeners,
  }
}
