/**
 * useH1DepreciationAlloc — H1-13 折旧分配分析表 composable
 *
 * 矩阵结构对齐 Excel 模板「折旧分配分析表H1-13」：
 *   行 = 固定资产类别（房屋及建筑物/机器设备/…）
 *   列 = 费用科目（生产成本/制造费用/销售费用/管理费用/研发费用/其他）
 *
 * 编制逻辑：
 * 1. 横：各类别折旧按用途分摊至费用科目，行合计须 = H1-12 该类折旧总额
 * 2. 纵：各费用科目合计供对方底稿 =WP() 取数（F5/F2/K8/K9/I6）
 * 3. 勾稽行：列合计与对方科目底稿索引对照；可反向拉取对方数并自动算差异
 *
 * Spec: .kiro/specs/h1-fixed-assets/ | Requirements: 12.1-12.8
 */
import { ref, computed, watch, type Ref } from 'vue'
import type { ChecklistItem } from './useH1FormData'
import type { CounterpartAmount, CounterpartField } from './h1DepAllocCounterpartPull'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface AllocRow {
  rowId: string
  category: string
  /** 折旧总额（来自 H1-12 按分类聚合，只读同步） */
  depTotal: number
  productionCost: number
  manufacturing: number
  selling: number
  admin: number
  rd: number
  other: number
  remark: string
  _isSummary?: boolean
  _isReconcile?: boolean
}

/** 费用列元数据：合计对外发布 + 勾稽跳转 */
export interface ExpenseColMeta {
  field: 'productionCost' | 'manufacturing' | 'selling' | 'admin' | 'rd' | 'other'
  label: string
  /** WP 语义标签（=WP 第三参 / ACNR label） */
  wpLabel: string
  /** 对方底稿编码 */
  targetWpCode: string
  /** 勾稽行展示文案中的索引 */
  indexHint: string
}

/** 勾稽核对行（纵向核对对方科目） */
export interface ReconciliationRow {
  label: string
  calculated: number
  /** 对方底稿数；未拉取时为 null */
  counterpart: number | null
  difference: number | null
  targetWpCode: string
  indexHint: string
  statusText: string
  /** 对方拉取诊断信息 */
  pullMessage?: string
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_PREFIX = 'H1-13'
const COUNTERPART_KEY = `${ITEM_PREFIX}-counterpart-amounts`

/** Excel 模板默认 5 类（实测 H1_13_asset_categories） */
export const DEFAULT_CATEGORIES = [
  '房屋及建筑物',
  '机器设备',
  '运输设备',
  '办公设备',
  '其他设备',
] as const

/**
 * 费用列 ↔ 对方底稿
 * K8=销售费用，K9=管理费用；制造费用→F2-43；生产成本→F5；研发→I6
 */
export const EXPENSE_COLS: ExpenseColMeta[] = [
  { field: 'productionCost', label: '生产成本', wpLabel: '生产成本折旧', targetWpCode: 'F5', indexHint: 'F5' },
  { field: 'manufacturing', label: '制造费用', wpLabel: '制造费用折旧', targetWpCode: 'F2', indexHint: 'F2' },
  { field: 'selling', label: '销售费用', wpLabel: '销售费用折旧', targetWpCode: 'K8', indexHint: 'K8' },
  { field: 'admin', label: '管理费用', wpLabel: '管理费用折旧', targetWpCode: 'K9', indexHint: 'K9' },
  { field: 'rd', label: '研发费用', wpLabel: '研发费用折旧', targetWpCode: 'I6', indexHint: 'I6' },
  { field: 'other', label: '其他', wpLabel: '其他折旧', targetWpCode: '', indexHint: '—' },
]

const TOLERANCE = 0.01

type CounterpartSnapshot = Partial<Record<CounterpartField, number | null>> & {
  _meta?: Partial<Record<CounterpartField, { message?: string; matchedLabel?: string; status?: string }>>
  _pulledAt?: string
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function _genRowId(): string {
  return `alloc-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function _blankRow(category: string, depTotal = 0): AllocRow {
  return {
    rowId: _genRowId(),
    category,
    depTotal,
    productionCost: 0,
    manufacturing: 0,
    selling: 0,
    admin: 0,
    rd: 0,
    other: 0,
    remark: '',
  }
}

export function calcRowAllocSum(row: AllocRow): number {
  return (
    (Number(row.productionCost) || 0) +
    (Number(row.manufacturing) || 0) +
    (Number(row.selling) || 0) +
    (Number(row.admin) || 0) +
    (Number(row.rd) || 0) +
    (Number(row.other) || 0)
  )
}

export function isRowBalanced(row: AllocRow): boolean {
  if (row._isSummary || row._isReconcile) return true
  return Math.abs(calcRowAllocSum(row) - (Number(row.depTotal) || 0)) < TOLERANCE
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH1DepreciationAlloc(
  wpId: Ref<string>,
  projectId: Ref<string>,
  allResponses: Ref<Map<string, ChecklistItem>>,
  options?: {
    /** H1-12 → H1-13 按分类折旧额 */
    crossSheetByCategory?: Ref<Record<string, number>>
    crossSheetDepTotal?: Ref<number>
    onSave?: (itemId: string, value: any) => void
    onPublishEvent?: (event: string, payload: any) => void
  },
) {
  const rows = ref<AllocRow[]>([])
  const auditNote = ref('')
  const auditConclusion = ref('')
  /** 对方底稿回填数（按费用列） */
  const counterpartSnapshot = ref<CounterpartSnapshot>({})
  const counterpartPulledAt = ref('')

  // ─── Load ──────────────────────────────────────────────────────────────────

  function _loadData(): void {
    const item = allResponses.value.get(`${ITEM_PREFIX}-rows`)
    if (item?.remark) {
      try {
        const parsed = JSON.parse(item.remark)
        rows.value = Array.isArray(parsed) ? parsed.map(_normalizeRow).filter((r) => r.category) : []
      } catch {
        rows.value = []
      }
    } else {
      rows.value = []
    }

    if (rows.value.length === 0) {
      rows.value = DEFAULT_CATEGORIES.map((c) => _blankRow(c))
    }

    auditNote.value = _getString(`${ITEM_PREFIX}-audit-note`)
    auditConclusion.value = _getString(`${ITEM_PREFIX}-audit-conclusion`)
    _loadCounterpartSnapshot()
    _syncFromH12()
  }

  function _loadCounterpartSnapshot(): void {
    const raw = _getString(COUNTERPART_KEY)
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

  function _getString(itemId: string): string {
    const i = allResponses.value.get(itemId)
    return (i?.remark ?? i?.conclusion ?? '') as string
  }

  function _normalizeRow(raw: any): AllocRow {
    // 兼容旧版「部门行」结构：有 expenseAccount 无 category 时丢弃（结构已变更）
    if (raw?.expenseAccount && !raw?.category && !raw?.productionCost && raw?.allocToManufacture != null) {
      return _blankRow('')
    }
    return {
      rowId: raw.rowId ?? _genRowId(),
      category: raw.category ?? '',
      depTotal: Number(raw.depTotal) || 0,
      productionCost: Number(raw.productionCost) || 0,
      manufacturing: Number(raw.manufacturing ?? raw.allocToManufacture) || 0,
      selling: Number(raw.selling ?? raw.allocToSales) || 0,
      admin: Number(raw.admin ?? raw.allocToAdmin) || 0,
      rd: Number(raw.rd) || 0,
      other: Number(raw.other) || 0,
      remark: raw.remark ?? '',
    }
  }

  /** 从 H1-12 按分类同步折旧总额；新分类自动补行 */
  function _syncFromH12(): void {
    const byCat = options?.crossSheetByCategory?.value
    if (!byCat || Object.keys(byCat).length === 0) return

    for (const row of rows.value) {
      if (row.category && byCat[row.category] != null) {
        row.depTotal = byCat[row.category]
      }
    }

    const existing = new Set(rows.value.map((r) => r.category))
    for (const [cat, amt] of Object.entries(byCat)) {
      if (!existing.has(cat)) {
        rows.value.push(_blankRow(cat, amt))
      }
    }
  }

  // ─── Computed: 列合计 ──────────────────────────────────────────────────────

  const colTotals = computed(() => {
    const t = {
      depTotal: 0,
      productionCost: 0,
      manufacturing: 0,
      selling: 0,
      admin: 0,
      rd: 0,
      other: 0,
      allocSum: 0,
    }
    for (const r of rows.value) {
      t.depTotal += Number(r.depTotal) || 0
      t.productionCost += Number(r.productionCost) || 0
      t.manufacturing += Number(r.manufacturing) || 0
      t.selling += Number(r.selling) || 0
      t.admin += Number(r.admin) || 0
      t.rd += Number(r.rd) || 0
      t.other += Number(r.other) || 0
      t.allocSum += calcRowAllocSum(r)
    }
    return t
  })

  const summaryRow = computed<AllocRow>(() => ({
    rowId: '__summary__',
    category: '合计',
    depTotal: colTotals.value.depTotal,
    productionCost: colTotals.value.productionCost,
    manufacturing: colTotals.value.manufacturing,
    selling: colTotals.value.selling,
    admin: colTotals.value.admin,
    rd: colTotals.value.rd,
    other: colTotals.value.other,
    remark: '',
    _isSummary: true,
  }))

  /** 勾稽关系情况行（展示用，不入持久化） */
  const reconcileRow = computed<AllocRow>(() => ({
    rowId: '__reconcile__',
    category: '勾稽关系情况',
    depTotal: 0,
    productionCost: 0,
    manufacturing: 0,
    selling: 0,
    admin: 0,
    rd: 0,
    other: 0,
    remark: '',
    _isReconcile: true,
  }))

  const displayRows = computed<AllocRow[]>(() => [
    ...rows.value,
    summaryRow.value,
    reconcileRow.value,
  ])

  // ─── 与 H1-12 横向平衡 ─────────────────────────────────────────────────────

  const h12DepTotal = computed(() => options?.crossSheetDepTotal?.value ?? colTotals.value.depTotal)
  const vsH12Diff = computed(() => colTotals.value.allocSum - h12DepTotal.value)
  const isBalancedWithH12 = computed(() => Math.abs(vsH12Diff.value) < TOLERANCE)

  /** 各类别：H1-12 折旧 vs 本表分配合计 */
  const categoryDiffs = computed(() => {
    const byCat = options?.crossSheetByCategory?.value ?? {}
    return rows.value.map((r) => {
      const h12 = Number(byCat[r.category] ?? r.depTotal) || 0
      const alloc = calcRowAllocSum(r)
      const diff = alloc - h12
      return {
        category: r.category,
        h12,
        alloc,
        diff,
        balanced: Math.abs(diff) < TOLERANCE,
      }
    })
  })

  /**
   * 将分配未配平差额回写 H1-12 审计结论（闭环留痕）
   */
  function writeBackUnallocatedToH12(): string {
    const unbalanced = categoryDiffs.value.filter((c) => !c.balanced)
    const lines = [
      `[H1-13→H1-12 闭环] ${new Date().toISOString().slice(0, 19)}`,
      `分配合计 ${colTotals.value.allocSum.toFixed(2)} vs H1-12 ${h12DepTotal.value.toFixed(2)}，差额 ${vsH12Diff.value.toFixed(2)}`,
    ]
    if (unbalanced.length) {
      lines.push('分类未配平行：')
      for (const c of unbalanced) {
        lines.push(`  · ${c.category}：分配 ${c.alloc.toFixed(2)} / H1-12 ${c.h12.toFixed(2)} / 差 ${c.diff.toFixed(2)}`)
      }
    } else {
      lines.push('各类别分配与 H1-12 勾稽一致。')
    }
    const text = lines.join('\n')
    options?.onSave?.('H1-12-audit-conclusion', text)
    options?.onSave?.('H1-13-h12-writeback', {
      at: new Date().toISOString(),
      vsH12Diff: vsH12Diff.value,
      categoryDiffs: unbalanced,
    })
    return text
  }

  // ─── 勾稽核对表（纵向 → 对方科目）──────────────────────────────────────────

  const reconciliationRows = computed<ReconciliationRow[]>(() => {
    const snap = counterpartSnapshot.value
    const cols: ReconciliationRow[] = EXPENSE_COLS.filter((c) => c.targetWpCode).map((c) => {
      const field = c.field as CounterpartField
      const calculated = colTotals.value[c.field]
      const counterpart = snap[field] !== undefined ? (snap[field] as number | null) : null
      const hasCounterpart = counterpart != null
      const difference = hasCounterpart ? calculated - counterpart : null
      const meta = snap._meta?.[field]
      let statusText: string
      if (calculated === 0 && !hasCounterpart) {
        statusText = '本期无分配'
      } else if (!hasCounterpart) {
        statusText = meta?.message || `待拉取对方数，详见${c.indexHint}`
      } else if (Math.abs(difference!) < TOLERANCE) {
        statusText = `勾稽一致，详见${c.indexHint}`
      } else {
        statusText = `差异 ${difference!.toFixed(2)}，详见${c.indexHint}`
      }
      return {
        label: `${c.label}折旧`,
        calculated,
        counterpart,
        difference,
        targetWpCode: c.targetWpCode,
        indexHint: c.indexHint,
        statusText,
        pullMessage: meta?.message,
      }
    })

    cols.unshift({
      label: '分配合计 vs H1-12',
      calculated: colTotals.value.allocSum,
      counterpart: h12DepTotal.value,
      difference: vsH12Diff.value,
      targetWpCode: 'H1-12',
      indexHint: 'H1-12',
      statusText: isBalancedWithH12.value
        ? '勾稽一致，详见H1-12'
        : `差异 ${vsH12Diff.value.toFixed(2)}，详见H1-12`,
    })

    return cols
  })

  /**
   * 汇总跨科目勾稽差异为审计说明文本（闭环留痕）。
   * 仅列出已拉取对方数且差异超容差的项，供写入 H1-13 审计说明。
   */
  function buildCounterpartDiffNote(): string {
    const rows = reconciliationRows.value
    const diffRows = rows.filter((r) => r.difference != null && Math.abs(r.difference) > TOLERANCE)
    const lines = [`[H1-13 跨科目勾稽] ${new Date().toISOString().slice(0, 19)}`]
    if (!diffRows.length) {
      lines.push('本表各费用列分配合计与对方底稿（F5/F2/K8/K9/I6）勾稽一致，未见重大差异。')
      return lines.join('\n')
    }
    lines.push(`发现 ${diffRows.length} 项与对方底稿存在差异，需核实分配口径或对方计提：`)
    for (const r of diffRows) {
      lines.push(
        `  · ${r.label}：本表 ${r.calculated.toFixed(2)} / 对方(${r.indexHint}) ${(r.counterpart ?? 0).toFixed(2)} / 差异 ${r.difference!.toFixed(2)}`,
      )
    }
    return lines.join('\n')
  }

  /** 应用对方底稿拉取结果并持久化 */
  function applyCounterpartPull(pulled: Record<CounterpartField, CounterpartAmount>): void {
    const next: CounterpartSnapshot = {
      _pulledAt: new Date().toISOString(),
      _meta: {},
    }
    for (const [field, info] of Object.entries(pulled) as [CounterpartField, CounterpartAmount][]) {
      next[field] = info.amount
      next._meta![field] = {
        message: info.message,
        matchedLabel: info.matchedLabel,
        status: info.status,
      }
    }
    counterpartSnapshot.value = next
    counterpartPulledAt.value = next._pulledAt!
    options?.onSave?.(COUNTERPART_KEY, next)
  }

  // 兼容旧 API 命名
  const totalDepAmount = computed(() => colTotals.value.depTotal)
  const totalManufacture = computed(() => colTotals.value.manufacturing)
  const totalAdmin = computed(() => colTotals.value.admin)
  const totalSales = computed(() => colTotals.value.selling)
  const totalProduction = computed(() => colTotals.value.productionCost)
  const totalRd = computed(() => colTotals.value.rd)
  const totalOther = computed(() => colTotals.value.other)
  const totalDifference = computed(() => vsH12Diff.value)

  // ─── Mutations ─────────────────────────────────────────────────────────────

  function updateCell(rowId: string, field: keyof AllocRow, value: any): void {
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    _persist()
  }

  function addRow(category?: string): void {
    const cat = category?.trim() || `分类-${rows.value.length + 1}`
    const dep = options?.crossSheetByCategory?.value?.[cat] ?? 0
    rows.value.push(_blankRow(cat, dep))
    _persist()
  }

  function removeRow(rowId: string): void {
    const idx = rows.value.findIndex((r) => r.rowId === rowId)
    if (idx >= 0) {
      rows.value.splice(idx, 1)
      _persist()
    }
  }

  function publishAllocated(): void {
    const t = colTotals.value
    options?.onPublishEvent?.('h1:depreciation-allocated', {
      wp_code: 'H1',
      sheet: '折旧分配分析表H1-13',
      /** 语义标签 → 金额，供 =WP / EventBus 消费 */
      labels: {
        生产成本折旧: t.productionCost,
        制造费用折旧: t.manufacturing,
        销售费用折旧: t.selling,
        管理费用折旧: t.admin,
        研发费用折旧: t.rd,
        其他折旧: t.other,
        全年折旧总额: t.allocSum,
      },
      totalProduction: t.productionCost,
      totalManufacture: t.manufacturing,
      totalSales: t.selling,
      totalAdmin: t.admin,
      totalRd: t.rd,
      totalOther: t.other,
      totalAlloc: t.allocSum,
      byCategory: rows.value.reduce((acc, r) => {
        acc[r.category] = {
          depTotal: r.depTotal,
          production: r.productionCost,
          manufacture: r.manufacturing,
          sales: r.selling,
          admin: r.admin,
          rd: r.rd,
          other: r.other,
        }
        return acc
      }, {} as Record<string, any>),
    })
  }

  function _persist(): void {
    options?.onSave?.(`${ITEM_PREFIX}-rows`, rows.value)
  }

  function saveNote(note: string): void {
    auditNote.value = note
    options?.onSave?.(`${ITEM_PREFIX}-audit-note`, note)
  }

  function saveConclusion(conclusion: string): void {
    auditConclusion.value = conclusion
    options?.onSave?.(`${ITEM_PREFIX}-audit-conclusion`, conclusion)
  }

  // ─── Init ──────────────────────────────────────────────────────────────────

  watch(allResponses, () => _loadData(), { immediate: true })
  watch(
    () => options?.crossSheetByCategory?.value,
    () => _syncFromH12(),
    { deep: true },
  )

  return {
    rows,
    displayRows,
    summaryRow,
    auditNote,
    auditConclusion,
    colTotals,
    totalDepAmount,
    totalProduction,
    totalManufacture,
    totalAdmin,
    totalSales,
    totalRd,
    totalOther,
    totalDifference,
    vsH12Diff,
    isBalancedWithH12,
    h12DepTotal,
    categoryDiffs,
    writeBackUnallocatedToH12,
    buildCounterpartDiffNote,
    reconciliationRows,
    counterpartPulledAt,
    applyCounterpartPull,
    updateCell,
    addRow,
    removeRow,
    publishAllocated,
    saveNote,
    saveConclusion,
    calcRowAllocSum,
    isRowBalanced,
  }
}

export default useH1DepreciationAlloc
