/**
 * useI1AmortizationAlloc — I1-9 摊销分配分析表 composable
 *
 * 对齐 Excel「无形资产摊销分配分析表 I1-9」编制逻辑：
 * 1. 横：各资产本期摊销按用途分摊至费用科目，行合计须 = I1-10/11 摊销总额
 * 2. 纵：各费用列合计供对方底稿 =WP() 取数（D5/K8/K9/I6）
 * 3. 核对：累计摊销(1702)贷方本期发生 ≈ 各费用科目借方「无形资产摊销」之和
 * 4. 评估分配方法是否合理且与上期一致
 *
 * 费用列顺序对齐 Excel：生产成本 / 制造费用 / 销售费用 / 管理费用 / 研发费用 / 其他
 * 跨底稿：销售→K8、管理→K9、研发→I6、生产成本/制造→D5
 *
 * Spec: .kiro/specs/i1-intangible-assets/ | Requirements: 10.1-10.4, 11.7
 */
import { ref, computed, watch, type Ref } from 'vue'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface I1AllocRow {
  rowId: string
  name: string
  /** 资产类别（来自 I1-2/I1-10，供类别汇总视图） */
  category?: string
  /** 摊销总额（来自 I1-10/11，只读同步） */
  totalAmort: number
  /** 生产成本（Excel 列；并入营业成本核对 D5） */
  productionCost: number
  manufacturingCost: number
  sellingExpense: number
  managementExpense: number
  rdExpense: number
  otherExpense: number
  remark: string
  _isSummary?: boolean
}

export interface I1AllocCategorySummary {
  category: string
  totalAmort: number
  productionCost: number
  manufacturingCost: number
  sellingExpense: number
  managementExpense: number
  rdExpense: number
  otherExpense: number
  assetCount: number
}

export type I1ExpenseField =
  | 'productionCost'
  | 'manufacturingCost'
  | 'sellingExpense'
  | 'managementExpense'
  | 'rdExpense'
  | 'otherExpense'

export interface I1ExpenseColMeta {
  field: I1ExpenseField
  label: string
  /** =WP 语义标签 */
  wpLabel: string
  targetWpCode: string
  indexHint: string
}

export interface I1ReconciliationRow {
  label: string
  calculated: number
  counterpart: number | null
  difference: number | null
  targetWpCode: string
  indexHint: string
  statusText: string
  field?: I1ExpenseField | ''
  isManual?: boolean
}

export type I1PriorConsistency = 'Y' | 'N' | ''

export interface I1AllocColTotals {
  productionCost: number
  manufacturingCost: number
  sellingExpense: number
  managementExpense: number
  rdExpense: number
  otherExpense: number
  allocSum: number
  totalAmort: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

export const I1_ALLOC_ROWS_KEY = 'I1-9-rows'
export const I1_ALLOC_TOTALS_KEY = 'I1-9-alloc-totals'
export const I1_ALLOC_COUNTERPART_KEY = 'I1-9-counterpart-amounts'
export const I1_ALLOC_PRIOR_KEY = 'I1-9-prior-consistency'
export const I1_ALLOC_NOTE_KEY = 'I1-9-audit-note'
export const I1_ALLOC_CONCLUSION_KEY = 'I1-9-audit-conclusion'

/**
 * 费用列 ↔ 对方底稿
 * K8=销售费用，K9=管理费用，I6=研发，D5=营业成本/生产成本（制造费用并入生产侧核对）
 */
export const I1_EXPENSE_COLS: I1ExpenseColMeta[] = [
  { field: 'productionCost', label: '生产成本', wpLabel: '生产成本摊销', targetWpCode: 'D5', indexHint: 'D5' },
  { field: 'manufacturingCost', label: '制造费用', wpLabel: '制造费用摊销', targetWpCode: 'D5', indexHint: 'D5' },
  { field: 'sellingExpense', label: '销售费用', wpLabel: '销售费用摊销', targetWpCode: 'K8', indexHint: 'K8' },
  { field: 'managementExpense', label: '管理费用', wpLabel: '管理费用摊销', targetWpCode: 'K9', indexHint: 'K9' },
  { field: 'rdExpense', label: '研发费用', wpLabel: '研发费用摊销', targetWpCode: 'I6', indexHint: 'I6' },
  { field: 'otherExpense', label: '其他', wpLabel: '其他摊销', targetWpCode: '', indexHint: '—' },
]

const TOLERANCE = 0.01

type CounterpartSnapshot = Partial<Record<I1ExpenseField, number | null>> & {
  _meta?: Partial<Record<I1ExpenseField, { message?: string; matchedLabel?: string }>>
  _pulledAt?: string
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function _genRowId(): string {
  return `i1-alloc-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function _getNum(val: unknown): number {
  if (val == null) return 0
  const n = Number(val)
  return Number.isFinite(n) ? n : 0
}

function _blankRow(name: string, totalAmort = 0, category = ''): I1AllocRow {
  return {
    rowId: _genRowId(),
    name,
    category,
    totalAmort,
    productionCost: 0,
    manufacturingCost: 0,
    sellingExpense: 0,
    managementExpense: 0,
    rdExpense: 0,
    otherExpense: 0,
    remark: '',
  }
}

/** 从 I1-2 / I1-10/11 解析资产类别映射 */
export function parseAssetCategoryMap(allResponses: Map<string, any>): Record<string, string> {
  const map: Record<string, string> = {}
  for (const key of ['I1-2-rows', 'I1-11-rows', 'I1-10-rows']) {
    const raw = allResponses.get(key)?.remark ?? allResponses.get(key)?.conclusion
    if (!raw) continue
    try {
      const rows = typeof raw === 'string' ? JSON.parse(raw) : raw
      if (!Array.isArray(rows)) continue
      for (const r of rows) {
        const name = String(r?.name ?? r?.assetName ?? '').trim()
        const cat = String(r?.category ?? '').trim()
        if (name && cat && !map[name]) map[name] = cat
      }
    } catch { /* ignore */ }
  }
  return map
}

export function calcI1RowAllocSum(row: I1AllocRow): number {
  return (
    _getNum(row.productionCost) +
    _getNum(row.manufacturingCost) +
    _getNum(row.sellingExpense) +
    _getNum(row.managementExpense) +
    _getNum(row.rdExpense) +
    _getNum(row.otherExpense)
  )
}

export function isI1RowBalanced(row: I1AllocRow): boolean {
  if (row._isSummary) return true
  return Math.abs(calcI1RowAllocSum(row) - _getNum(row.totalAmort)) < TOLERANCE
}

export function calcI1RowRemainder(row: I1AllocRow): number {
  return _getNum(row.totalAmort) - calcI1RowAllocSum(row)
}

function _normalizeRow(raw: any): I1AllocRow {
  return {
    rowId: raw.rowId || _genRowId(),
    name: raw.name || '',
    category: raw.category ?? '',
    totalAmort: _getNum(raw.totalAmort),
    productionCost: _getNum(raw.productionCost ?? raw.operatingCost),
    manufacturingCost: _getNum(raw.manufacturingCost),
    sellingExpense: _getNum(raw.sellingExpense),
    managementExpense: _getNum(raw.managementExpense),
    rdExpense: _getNum(raw.rdExpense),
    otherExpense: _getNum(raw.otherExpense),
    remark: raw.remark ?? '',
  }
}

/** 从 I1-10 / I1-11 行聚合按资产摊销额 */
export function parseAmortizationByAsset(allResponses: Map<string, any>): {
  byAsset: Record<string, number>
  total: number
  sourceSheet: 'I1-11' | 'I1-10' | ''
} {
  const tryParse = (key: string): any[] => {
    const resp = allResponses.get(key)
    const raw = resp?.remark ?? resp?.conclusion
    if (!raw) return []
    try {
      const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw
      return Array.isArray(parsed) ? parsed : []
    } catch {
      return []
    }
  }

  let sourceSheet: 'I1-11' | 'I1-10' | '' = ''
  let rows = tryParse('I1-11-rows')
  if (rows.length > 0) sourceSheet = 'I1-11'
  else {
    rows = tryParse('I1-10-rows')
    if (rows.length > 0) sourceSheet = 'I1-10'
  }

  const byAsset: Record<string, number> = {}
  let total = 0
  for (const row of rows) {
    const name = String(row.name || '未命名资产')
    const amount = _getNum(row.periodAmortization)
    byAsset[name] = (byAsset[name] || 0) + amount
    total += amount
  }
  return { byAsset, total, sourceSheet }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useI1AmortizationAlloc(params: {
  allResponses: Ref<Map<string, any>>
  /** 外部注入的按资产摊销额（优先）；缺省时从 allResponses 自算 */
  amortizationByAsset?: Ref<Record<string, number> | undefined>
  onSave?: (itemId: string, value: any) => void
  onPublishEvent?: (event: string, payload: any) => void
}) {
  const { allResponses, onSave, onPublishEvent } = params

  const rows = ref<I1AllocRow[]>([])
  const counterpartSnapshot = ref<CounterpartSnapshot>({})
  const counterpartPulledAt = ref('')
  const priorConsistent = ref<I1PriorConsistency>('')
  const priorNote = ref('')

  // ─── Load helpers ──────────────────────────────────────────────────────────

  function _getString(itemId: string): string {
    const i = allResponses.value.get(itemId)
    return (i?.remark ?? i?.conclusion ?? '') as string
  }

  function loadRows(): void {
    const raw = _getString(I1_ALLOC_ROWS_KEY)
    if (!raw) {
      rows.value = []
      return
    }
    try {
      const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw
      if (!Array.isArray(parsed)) {
        rows.value = []
        return
      }
      rows.value = parsed.map(_normalizeRow)
    } catch {
      rows.value = []
    }
  }

  function loadCounterpart(): void {
    const raw = _getString(I1_ALLOC_COUNTERPART_KEY)
    if (!raw) {
      counterpartSnapshot.value = {}
      counterpartPulledAt.value = ''
      return
    }
    try {
      const parsed = JSON.parse(raw) as CounterpartSnapshot
      counterpartSnapshot.value = parsed ?? {}
      counterpartPulledAt.value = parsed?._pulledAt ?? ''
    } catch {
      counterpartSnapshot.value = {}
      counterpartPulledAt.value = ''
    }
  }

  function loadPrior(): void {
    const raw = _getString(I1_ALLOC_PRIOR_KEY)
    if (!raw) {
      priorConsistent.value = ''
      priorNote.value = ''
      return
    }
    try {
      const parsed = JSON.parse(raw) as { consistent?: string; note?: string }
      priorConsistent.value = (parsed.consistent as I1PriorConsistency) || ''
      priorNote.value = parsed.note || ''
    } catch {
      priorConsistent.value = ''
      priorNote.value = ''
    }
  }

  watch(
    () => allResponses.value,
    () => {
      loadRows()
      loadCounterpart()
      loadPrior()
    },
    { immediate: true },
  )

  // ─── Upstream sync: I1-10/11 → totalAmort ──────────────────────────────────

  const resolvedByAsset = computed(() => {
    const external = params.amortizationByAsset?.value
    if (external && Object.keys(external).length > 0) {
      return { byAsset: external, total: Object.values(external).reduce((s, n) => s + _getNum(n), 0), sourceSheet: '' as const }
    }
    return parseAmortizationByAsset(allResponses.value)
  })

  const sourceAmortTotal = computed(() => resolvedByAsset.value.total)
  const sourceSheetLabel = computed(() => {
    const s = resolvedByAsset.value.sourceSheet
    if (s) return s
    if (params.amortizationByAsset?.value && Object.keys(params.amortizationByAsset.value).length) return 'I1-10/11'
    return ''
  })

  const categoryByName = computed(() => parseAssetCategoryMap(allResponses.value))

  watch(
    resolvedByAsset,
    (src) => {
      const byAsset = src.byAsset
      if (!byAsset) return
      const cats = categoryByName.value

      for (const row of rows.value) {
        if (row.name && byAsset[row.name] != null) {
          row.totalAmort = byAsset[row.name]
        }
        if (row.name && cats[row.name] && !row.category) {
          row.category = cats[row.name]
        }
      }

      const existing = new Set(rows.value.map((r) => r.name))
      for (const [name, amount] of Object.entries(byAsset)) {
        if (!existing.has(name)) {
          rows.value.push(_blankRow(name, amount, cats[name] || ''))
        }
      }
    },
    { immediate: true, deep: true },
  )

  /** 按类别折叠汇总（只读，服务附注/Excel 类别披露） */
  const categorySummaryRows = computed<I1AllocCategorySummary[]>(() => {
    const bags = new Map<string, I1AllocCategorySummary>()
    for (const row of rows.value) {
      const cat = (row.category || '未分类').trim() || '未分类'
      let bag = bags.get(cat)
      if (!bag) {
        bag = {
          category: cat,
          totalAmort: 0,
          productionCost: 0,
          manufacturingCost: 0,
          sellingExpense: 0,
          managementExpense: 0,
          rdExpense: 0,
          otherExpense: 0,
          assetCount: 0,
        }
        bags.set(cat, bag)
      }
      bag.totalAmort += _getNum(row.totalAmort)
      bag.productionCost += _getNum(row.productionCost)
      bag.manufacturingCost += _getNum(row.manufacturingCost)
      bag.sellingExpense += _getNum(row.sellingExpense)
      bag.managementExpense += _getNum(row.managementExpense)
      bag.rdExpense += _getNum(row.rdExpense)
      bag.otherExpense += _getNum(row.otherExpense)
      bag.assetCount++
    }
    return [...bags.values()].sort((a, b) => a.category.localeCompare(b.category, 'zh-CN'))
  })

  // ─── Aggregates ────────────────────────────────────────────────────────────

  const colTotals = computed<I1AllocColTotals>(() => {
    let productionCost = 0
    let manufacturingCost = 0
    let sellingExpense = 0
    let managementExpense = 0
    let rdExpense = 0
    let otherExpense = 0
    let totalAmort = 0

    for (const row of rows.value) {
      productionCost += _getNum(row.productionCost)
      manufacturingCost += _getNum(row.manufacturingCost)
      sellingExpense += _getNum(row.sellingExpense)
      managementExpense += _getNum(row.managementExpense)
      rdExpense += _getNum(row.rdExpense)
      otherExpense += _getNum(row.otherExpense)
      totalAmort += _getNum(row.totalAmort)
    }

    const allocSum =
      productionCost + manufacturingCost + sellingExpense + managementExpense + rdExpense + otherExpense

    return {
      productionCost,
      manufacturingCost,
      sellingExpense,
      managementExpense,
      rdExpense,
      otherExpense,
      allocSum,
      totalAmort,
    }
  })

  const summaryRow = computed<I1AllocRow>(() => {
    const t = colTotals.value
    return {
      rowId: '__summary__',
      name: '合计',
      totalAmort: t.totalAmort,
      productionCost: t.productionCost,
      manufacturingCost: t.manufacturingCost,
      sellingExpense: t.sellingExpense,
      managementExpense: t.managementExpense,
      rdExpense: t.rdExpense,
      otherExpense: t.otherExpense,
      remark: '',
      _isSummary: true,
    }
  })

  const displayRows = computed(() => [...rows.value, summaryRow.value])

  const vsSourceDiff = computed(() => colTotals.value.allocSum - sourceAmortTotal.value)
  const isBalancedWithSource = computed(() => Math.abs(vsSourceDiff.value) < TOLERANCE)
  const unbalancedCount = computed(() => rows.value.filter((r) => !isI1RowBalanced(r)).length)

  // ─── Reconciliation ────────────────────────────────────────────────────────

  const reconciliationRows = computed<I1ReconciliationRow[]>(() => {
    const snap = counterpartSnapshot.value
    const t = colTotals.value

    // 生产成本+制造费用合并与 D5 核对（Excel 两列、对方底稿常合计）
    const d5Calculated = t.productionCost + t.manufacturingCost
    const linkedCols: Array<{
      field: I1ExpenseField | 'd5Combined'
      label: string
      calculated: number
      targetWpCode: string
      indexHint: string
      snapField?: I1ExpenseField
    }> = [
      {
        field: 'd5Combined',
        label: '生产成本+制造费用摊销',
        calculated: d5Calculated,
        targetWpCode: 'D5',
        indexHint: 'D5',
        snapField: 'productionCost',
      },
      {
        field: 'sellingExpense',
        label: '销售费用摊销',
        calculated: t.sellingExpense,
        targetWpCode: 'K8',
        indexHint: 'K8',
        snapField: 'sellingExpense',
      },
      {
        field: 'managementExpense',
        label: '管理费用摊销',
        calculated: t.managementExpense,
        targetWpCode: 'K9',
        indexHint: 'K9',
        snapField: 'managementExpense',
      },
      {
        field: 'rdExpense',
        label: '研发费用摊销',
        calculated: t.rdExpense,
        targetWpCode: 'I6',
        indexHint: 'I6',
        snapField: 'rdExpense',
      },
    ]

    const cols: I1ReconciliationRow[] = linkedCols.map((c) => {
      const field = c.snapField
      const counterpart = field && snap[field] !== undefined ? (snap[field] as number | null) : null
      const hasCounterpart = counterpart != null
      const difference = hasCounterpart ? c.calculated - counterpart : null
      const isManual = field ? snap._meta?.[field]?.matchedLabel === '手工覆盖' : false
      let statusText: string
      if (c.calculated === 0 && !hasCounterpart) {
        statusText = '本期无分配'
      } else if (!hasCounterpart) {
        statusText = snap._meta?.[field!]?.message || `待拉取对方数，详见${c.indexHint}`
      } else if (Math.abs(difference!) < TOLERANCE) {
        statusText = isManual
          ? `勾稽一致（手工），详见${c.indexHint}`
          : `勾稽一致，详见${c.indexHint}`
      } else {
        statusText = `差异 ${difference!.toFixed(2)}，详见${c.indexHint}`
      }
      return {
        label: c.label,
        calculated: c.calculated,
        counterpart,
        difference,
        targetWpCode: c.targetWpCode,
        indexHint: c.indexHint,
        statusText,
        field: field || '',
        isManual,
      }
    })

    cols.unshift({
      label: `分配合计 vs ${sourceSheetLabel.value || 'I1-10/11'}`,
      calculated: t.allocSum,
      counterpart: sourceAmortTotal.value,
      difference: vsSourceDiff.value,
      targetWpCode: sourceSheetLabel.value || 'I1-10',
      indexHint: sourceSheetLabel.value || 'I1-10/11',
      statusText: isBalancedWithSource.value
        ? `勾稽一致，详见${sourceSheetLabel.value || 'I1-10/11'}`
        : `差异 ${vsSourceDiff.value.toFixed(2)}，详见${sourceSheetLabel.value || 'I1-10/11'}`,
      field: '',
    })

    return cols
  })

  function setCounterpartManual(field: I1ExpenseField, amount: number | null): void {
    const next: CounterpartSnapshot = {
      ...counterpartSnapshot.value,
      _meta: { ...(counterpartSnapshot.value._meta ?? {}) },
    }
    next[field] = amount
    next._meta![field] = {
      message: amount == null ? '已清空手工数' : '手工录入对方底稿数',
      matchedLabel: amount == null ? '' : '手工覆盖',
    }
    next._pulledAt = new Date().toISOString()
    counterpartSnapshot.value = next
    counterpartPulledAt.value = next._pulledAt
    onSave?.(I1_ALLOC_COUNTERPART_KEY, next)
  }

  /**
   * 应用对方底稿反向拉取结果（对齐 H8-9）。
   * 已手工覆盖且本次拉取失败时保留手工数。
   */
  function applyCounterpartPull(
    pulled: Record<
      Extract<I1ExpenseField, 'productionCost' | 'sellingExpense' | 'managementExpense' | 'rdExpense'>,
      {
        amount: number | null
        message: string
        matchedLabel: string
        status: string
      }
    >,
  ): void {
    const prev = counterpartSnapshot.value
    const next: CounterpartSnapshot = {
      _pulledAt: new Date().toISOString(),
      _meta: {},
    }
    for (const [field, info] of Object.entries(pulled) as Array<
      [Extract<I1ExpenseField, 'productionCost' | 'sellingExpense' | 'managementExpense' | 'rdExpense'>, typeof pulled[keyof typeof pulled]]
    >) {
      const wasManual = prev._meta?.[field]?.matchedLabel === '手工覆盖'
      if (info.status !== 'ok' && wasManual && prev[field] != null) {
        next[field] = prev[field]
        next._meta![field] = {
          message: `拉取失败，保留手工数；${info.message}`,
          matchedLabel: '手工覆盖',
        }
        continue
      }
      next[field] = info.amount
      next._meta![field] = {
        message: info.message,
        matchedLabel: info.matchedLabel,
      }
    }
    counterpartSnapshot.value = next
    counterpartPulledAt.value = next._pulledAt!
    onSave?.(I1_ALLOC_COUNTERPART_KEY, next)
  }

  // ─── Persist ───────────────────────────────────────────────────────────────

  function persistRows(): void {
    onSave?.(I1_ALLOC_ROWS_KEY, rows.value)
    onSave?.(I1_ALLOC_TOTALS_KEY, {
      ...colTotals.value,
      sellingExpenseAmort: colTotals.value.sellingExpense,
      managementExpenseAmort: colTotals.value.managementExpense,
      rdExpenseAmort: colTotals.value.rdExpense,
      productionManufacturingAmort: colTotals.value.productionCost + colTotals.value.manufacturingCost,
      at: new Date().toISOString(),
    })
  }

  function updateCell(row: I1AllocRow, field: keyof I1AllocRow, value: unknown): void {
    if (row._isSummary) return
    ;(row as any)[field] = value
    persistRows()
  }

  function addRow(name: string): I1AllocRow {
    const totalAmort = resolvedByAsset.value.byAsset?.[name] ?? 0
    const row = _blankRow(name, totalAmort)
    rows.value.push(row)
    persistRows()
    return row
  }

  function removeRow(rowId: string): void {
    const idx = rows.value.findIndex((r) => r.rowId === rowId)
    if (idx >= 0) {
      rows.value.splice(idx, 1)
      persistRows()
    }
  }

  /** 将各行未分配差额一键并入指定费用列 */
  function allocateAllRemaindersTo(field: I1ExpenseField): number {
    let n = 0
    for (const row of rows.value) {
      const rem = calcI1RowRemainder(row)
      if (Math.abs(rem) < TOLERANCE) continue
      ;(row as any)[field] = _getNum((row as any)[field]) + rem
      n++
    }
    if (n) persistRows()
    return n
  }

  function savePriorAssessment(consistent: I1PriorConsistency, note: string): void {
    priorConsistent.value = consistent
    priorNote.value = note
    onSave?.(I1_ALLOC_PRIOR_KEY, { consistent, note })
  }

  function publishAllocated(): void {
    const payload = {
      sheet: '摊销分配分析表I1-9',
      totals: colTotals.value,
      销售费用摊销: colTotals.value.sellingExpense,
      管理费用摊销: colTotals.value.managementExpense,
      研发费用摊销: colTotals.value.rdExpense,
      生产成本摊销: colTotals.value.productionCost,
      制造费用摊销: colTotals.value.manufacturingCost,
      at: new Date().toISOString(),
    }
    onSave?.(I1_ALLOC_TOTALS_KEY, payload)
    onPublishEvent?.('i1:amortization-allocated', payload)
  }

  function fmtPercent(row: I1AllocRow): string {
    const totalAll = summaryRow.value.totalAmort
    if (!totalAll) return '—'
    const rowSum = row._isSummary ? calcI1RowAllocSum(summaryRow.value) : calcI1RowAllocSum(row)
    return `${((rowSum / totalAll) * 100).toFixed(2)}%`
  }

  return {
    rows,
    displayRows,
    summaryRow,
    colTotals,
    categorySummaryRows,
    sourceAmortTotal,
    sourceSheetLabel,
    vsSourceDiff,
    isBalancedWithSource,
    unbalancedCount,
    reconciliationRows,
    counterpartPulledAt,
    setCounterpartManual,
    applyCounterpartPull,
    priorConsistent,
    priorNote,
    savePriorAssessment,
    updateCell,
    addRow,
    removeRow,
    allocateAllRemaindersTo,
    persistRows,
    publishAllocated,
    calcRowAllocSum: calcI1RowAllocSum,
    isRowBalanced: isI1RowBalanced,
    calcRowRemainder: calcI1RowRemainder,
    fmtPercent,
    expenseCols: I1_EXPENSE_COLS,
  }
}

export default useI1AmortizationAlloc
