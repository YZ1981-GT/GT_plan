/**
 * useF2InspectionCheck — F2-33 采购入库 / F2-34 材料领用（账→单细节测试）
 *
 * 抽凭回填 / 挂凭导入 / 撤销 / 年审阶段预审行只读走共享回填函数 `useVoucherCheckFill`：一个对方科目一行
 * （后端配对），按分录指纹去重，行元数据 `_gt` 随行 JSON 落库（spec voucher-identity-writeback-and-audit-phase 任务 11）。
 */
import { ref, computed, watch, onBeforeUnmount, getCurrentInstance, type MaybeRefOrGetter, type Ref } from 'vue'
import { readValRowJson, type ChecklistResponse } from './useF2ValuationFormData'
import {
  emptyPurchaseInboundRow,
  emptyMaterialUsageRow,
  calcInspectionCoverage,
  readBookTotal,
  assessPurchaseAbnormal,
  assessMaterialAbnormal,
  buildCoverageByCategory,
  migrateLegacyInspectionRow,
  calcSubtotal,
  type PurchaseInboundRow,
  type MaterialUsageRow,
  type CoverageLine,
} from './useF2InspectionCheckFormulas'
import type { SamplingMethod } from './useSamplingAlgorithms'
import {
  metaOf, useVoucherCheckFill, withRowMeta,
  type EngineFilledPayload, type PreparedItem,
} from './shared/voucherCheckFill'

type Kind = 'purchase' | 'material'

/**
 * 共享回填函数的待写入项 → 检查行：金额取样本自己那一栏（采购入库优先借方、材料领用优先贷方，沿用原口径），
 * 对方科目 = 编码、对方明细科目 = 名称（配不上写「多科目」）。原实现把对方科目写进供应商 / 领用部门，已改正。
 */
export function mapPreparedToInspectionRow(
  item: PreparedItem, seq: number, kind: Kind, preferDebit: boolean,
): PurchaseInboundRow | MaterialUsageRow {
  const s = item.sample as PreparedItem['sample'] & {
    summary?: string | null; remark?: string | null; samplingMethod?: string | null
  }
  const debit = Number(item.debitAmount ?? 0) || 0
  const credit = Number(item.creditAmount ?? 0) || 0
  const amount = preferDebit ? (debit > 0 ? debit : credit) : (credit > 0 ? credit : debit)
  const algo = s.samplingMethod || (s.remark?.includes('stratified') ? 'stratified' : 'random')
  const source = item.meta.src.includes('attach') ? '来自挂凭' : `来自抽凭引擎 ${algo}`
  const code = item.counterpartAccount
  const name = item.counterpartAccountName
  const common = {
    voucherNo: s.voucherNo || '',
    businessContent: s.summary || '',
    itemName: s.summary || '',
    amount,
    counterpartAccount: code,
    counterpartDetail: name && name !== code ? name : '',
    remark: s.remark || '',
  }
  return kind === 'purchase'
    ? { ...emptyPurchaseInboundRow(seq, source), ...common }
    : { ...emptyMaterialUsageRow(seq, source), ...common }
}

/** 空白占位行：没有行元数据，凭证号、内容、品名、金额、备注与核对内容都没填 */
export function isBlankInspectionRow(r: PurchaseInboundRow | MaterialUsageRow): boolean {
  return !metaOf(r) && !hasInspectionContent(r)
    && [r.voucherNo, r.businessContent, r.itemName, r.remark].every((v) => String(v ?? '').trim() === '')
    && !Number(r.amount)
}

/** 行上已填数量 / 单位 / 入库验收物流发票 / 领用单据、索引、异常判断（替换与撤销抽凭时据此先确认） */
export function hasInspectionContent(r: PurchaseInboundRow | MaterialUsageRow): boolean {
  const texts: unknown[] = [r.party, r.unit, r.indexRef]
  const nums: unknown[] = [r.qty]
  if ('recvDateNo' in r) {
    texts.push(r.recvDateNo, r.inspectDateNo, r.logisticsDateNo, r.logisticsProvider, r.invoiceDateNo, r.invoiceParty)
    nums.push(r.recvQty, r.invoiceQty, r.invoiceAmount)
  } else {
    texts.push(r.docDateNo)
    nums.push(r.docQty)
  }
  return r.abnormalOverride !== null
    || texts.some((v) => String(v ?? '').trim() !== '')
    || nums.some((n) => Number(n) !== 0)
}

function useInspectionSheet<T extends PurchaseInboundRow | MaterialUsageRow>(
  sheetCode: 'F2-33' | 'F2-34',
  kind: Kind,
  title: string,
  partyLabel: string,
  preferDebit: boolean,
  opts: {
    allResponses: Ref<Map<string, ChecklistResponse>>
    isReadonly?: Ref<boolean>
    /** 项目 id（抽凭回填按项目当前审计阶段标行阶段，年审阶段预审行只读） */
    projectId?: MaybeRefOrGetter<string | null | undefined>
  },
) {
  const readonly = opts.isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  const dataKey = `${sheetCode}-rows`
  const metaKey = `${sheetCode}-meta`
  const coverageKey = `${sheetCode}-coverage-book`

  const rows = ref<T[]>([
    (kind === 'purchase' ? emptyPurchaseInboundRow(1) : emptyMaterialUsageRow(1)) as T,
  ])
  const bookTotal = ref(0)
  const bookByCategory = ref<Record<string, number>>({})
  const auditNote = ref('')
  const meta = ref<Record<string, string>>({
    entityName: '',
    cutoffDate: '',
    populationDesc: '',
    specificSamples: '',
    samplingPopulation: '',
    sampleSize: '',
    samplingMethod: '',
    samplingProcess: '',
  })

  function enrich(r: T): T {
    if (kind === 'purchase') {
      const p = r as PurchaseInboundRow
      return { ...p, isAbnormal: assessPurchaseAbnormal(p) } as T
    }
    const m = r as MaterialUsageRow
    return { ...m, isAbnormal: assessMaterialAbnormal(m) } as T
  }

  // 抽凭回填 / 挂凭导入 / 撤销 / 年审阶段预审行只读：共享回填函数
  /**
   * 抽凭回填用的表：写入时去掉空白占位行（表初始有一行空行，原实现追加时留着它），表空了补一行空白行
   * （删行入口不许删到 0 行），序号按写入后的顺序重排
   */
  const fillTable = computed<T[]>({
    get: () => rows.value as T[],
    set: (list) => {
      const kept = list.filter((r) => !isBlankInspectionRow(r))
      const next = kept.length ? kept : [(kind === 'purchase' ? emptyPurchaseInboundRow(1) : emptyMaterialUsageRow(1)) as T]
      next.forEach((r, i) => { r.seq = i + 1 })
      rows.value = next
    },
  })
  const voucherFill = useVoucherCheckFill<T>({
    projectId: opts.projectId ?? null,
    tables: fillTable,
    mapSampleToRow: (item) => enrich(mapPreparedToInspectionRow(item, rows.value.length + 1, kind, preferDebit) as T),
    persist: () => persist(),
    hasUserContent: (r) => hasInspectionContent(r),
    readonly: () => readonly.value,
  })
  /** 年审阶段的预审行只读（不可改、不可删） */
  function lockedId(id: string): boolean {
    const row = rows.value.find((r) => r.id === id)
    return !!row && voucherFill.isRowLocked(row as T)
  }

  function load(): void {
    const raw = readValRowJson(opts.allResponses.value.get(dataKey))
    if (raw) {
      try {
        const parsed = JSON.parse(raw) as Record<string, unknown>[]
        if (Array.isArray(parsed) && parsed.length) {
          rows.value = parsed.map((r) => withRowMeta(enrich(migrateLegacyInspectionRow(r, kind) as T), r))
        }
      } catch { /* ignore */ }
    }
    voucherFill.markLoaded()
    bookTotal.value = readBookTotal(opts.allResponses.value, sheetCode)
    auditNote.value = opts.allResponses.value.get(`${sheetCode}-note`)?.remark || ''
    try {
      const mr = opts.allResponses.value.get(metaKey)?.remark
      if (mr) meta.value = { ...meta.value, ...JSON.parse(mr) }
    } catch { /* ignore */ }
    try {
      const cr = opts.allResponses.value.get(coverageKey)?.remark
      if (cr) bookByCategory.value = JSON.parse(cr) as Record<string, number>
    } catch { /* ignore */ }
  }

  watch(() => opts.allResponses.value.get(dataKey)?.remark, load, { immediate: true })

  const checkedTotal = computed(() => calcSubtotal(rows.value.map((r) => r.amount)))
  const coverageRatio = computed(() => calcInspectionCoverage(checkedTotal.value, bookTotal.value))
  const isCoverageLow = computed(() => coverageRatio.value > 0 && coverageRatio.value < 50)
  const abnormalCount = computed(() => rows.value.filter((r) => r.isAbnormal).length)

  const coverageLines = computed((): CoverageLine[] => {
    if (kind === 'purchase') {
      return buildCoverageByCategory(rows.value as PurchaseInboundRow[], bookByCategory.value)
    }
    const checked = checkedTotal.value
    const book = bookTotal.value || Number(bookByCategory.value['原材料贷方'] || 0)
    return [{
      category: '原材料贷方',
      bookAmount: book,
      checkedAmount: checked,
      ratio: calcInspectionCoverage(checked, book),
    }]
  })

  function flushSave(): void {
    const items = [
      opts.allResponses.value.get(dataKey),
      opts.allResponses.value.get(`${sheetCode}-book-total`),
      opts.allResponses.value.get(`${sheetCode}-note`),
      opts.allResponses.value.get(metaKey),
      opts.allResponses.value.get(coverageKey),
    ].filter(Boolean)
    if (items.length) window.dispatchEvent(new CustomEvent('f2-val:save-items', { detail: { items } }))
  }

  function persist(): void {
    opts.allResponses.value.set(dataKey, {
      item_id: dataKey, conclusion: null, remark: JSON.stringify(voucherFill.guardPersist(rows.value as T[])),
    })
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 2000)
  }

  function persistMeta(): void {
    if (readonly.value) return
    opts.allResponses.value.set(metaKey, { item_id: metaKey, conclusion: null, remark: JSON.stringify(meta.value) })
    persist()
  }

  function updateMeta(patch: Record<string, string>): void {
    if (readonly.value) return
    meta.value = { ...meta.value, ...patch }
    persistMeta()
  }

  function updateBookTotal(v: number): void {
    if (readonly.value) return
    bookTotal.value = v
    opts.allResponses.value.set(`${sheetCode}-book-total`, {
      item_id: `${sheetCode}-book-total`, conclusion: null, remark: String(v),
    })
    persist()
  }

  function updateBookByCategory(category: string, amount: number): void {
    if (readonly.value) return
    bookByCategory.value = { ...bookByCategory.value, [category]: amount }
    opts.allResponses.value.set(coverageKey, {
      item_id: coverageKey, conclusion: null, remark: JSON.stringify(bookByCategory.value),
    })
    persist()
  }

  function addRow(): void {
    if (readonly.value) return
    const next = kind === 'purchase'
      ? emptyPurchaseInboundRow(rows.value.length + 1)
      : emptyMaterialUsageRow(rows.value.length + 1)
    rows.value = [...rows.value, next as T]
    persist()
  }

  function removeRow(id: string): void {
    if (readonly.value || rows.value.length <= 1 || lockedId(id)) return
    rows.value = rows.value.filter((r) => r.id !== id).map((r, i) => ({ ...r, seq: i + 1 }))
    persist()
  }

  function updateRow(id: string, patch: Partial<T>): void {
    if (readonly.value || lockedId(id)) return
    rows.value = rows.value.map((r) => {
      if (r.id !== id) return r
      return withRowMeta(enrich({ ...r, ...patch } as T), r)
    })
    persist()
  }

  /**
   * 抽凭引擎回填：一个对方科目一行（后端配对），按分录指纹去重；「替换本阶段抽凭行」只删本阶段抽凭填入的行
   * （原实现整表替换 / 按凭证号去重，已删除）。抽样方法记在行的样本来源上。
   */
  function onEngineFilled(payload: EngineFilledPayload & { method?: SamplingMethod }) {
    const samples = (payload.samples ?? []).map(s => ({
      ...s, samplingMethod: (s as { samplingMethod?: string }).samplingMethod ?? payload.method,
    }))
    return voucherFill.onEngineFilled({ ...payload, samples })
  }

  watch(auditNote, (val) => {
    if (readonly.value) return
    opts.allResponses.value.set(`${sheetCode}-note`, { item_id: `${sheetCode}-note`, conclusion: null, remark: val })
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 2000)
  })

  if (getCurrentInstance()) {
    onBeforeUnmount(() => { if (debounceTimer) { clearTimeout(debounceTimer); flushSave() } })
  }

  return {
    sheetCode,
    title,
    partyLabel,
    rows,
    bookTotal,
    bookByCategory,
    meta,
    updateMeta,
    checkedTotal,
    coverageRatio,
    isCoverageLow,
    abnormalCount,
    coverageLines,
    auditNote,
    addRow,
    removeRow,
    updateRow,
    updateBookTotal,
    updateBookByCategory,
    // 抽凭回填 / 挂凭导入 / 撤销 / 年审阶段预审行只读（共享回填函数）
    onEngineFilled,
    onAttachImported: voucherFill.onAttachImported,
    onUndoRequest: voucherFill.onUndoRequest,
    voucherRowClass: voucherFill.rowClass,
    isVoucherRowLocked: voucherFill.isRowLocked,
    voucherFillReady: voucherFill.ready,
  }
}

export function useF2PurchaseInboundCheck(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
  projectId?: MaybeRefOrGetter<string | null | undefined>
}) {
  return useInspectionSheet<PurchaseInboundRow>(
    'F2-33', 'purchase', '存货采购入库检查表', '供应商', true, opts,
  )
}

export function useF2MaterialUsageCheck(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
  projectId?: MaybeRefOrGetter<string | null | undefined>
}) {
  return useInspectionSheet<MaterialUsageRow>(
    'F2-34', 'material', '材料领用检查表', '领用部门', false, opts,
  )
}

export default useF2PurchaseInboundCheck
