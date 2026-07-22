/**
 * useH8DepreciationAlloc — H8-9 折旧分配分析表 composable
 *
 * 矩阵结构对齐 Excel 模板「折旧分配分析表H8-9」：
 *   行 = 使用权资产类别（房屋及建筑物/机器设备/运输设备/办公设备/其他设备）
 *   列 = 费用科目（营业成本/制造费用/销售费用/管理费用/研发支出/其他）
 *
 * 编制逻辑：
 * 1. 横：各类别折旧按用途分摊至费用科目，行合计须 = H8-8 该类折旧总额
 * 2. 纵：各费用科目合计供对方底稿 =WP() 取数（D5/F2/K8/K9/I6）
 * 3. 勾稽行：列合计与对方科目底稿索引对照；可反向拉取对方数并自动算差异
 * 4. 与累计折旧贷方核对：分配合计应 ≈ H8-8 本期折旧合计（→ 费用科目借方）
 *
 * Spec: .kiro/specs/h8-right-of-use-assets/ | Requirements: 6.4-6.6
 */
import { ref, computed, watch, type Ref } from 'vue'
import type {
  H8CounterpartAmount,
  H8CounterpartField,
} from './h8DepAllocCounterpartPull'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface H8AllocRow {
  rowId: string
  category: string
  /** 折旧总额（来自 H8-8 按分类聚合，只读同步） */
  depTotal: number
  operatingCost: number
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
export interface H8ExpenseColMeta {
  field: 'operatingCost' | 'manufacturing' | 'selling' | 'admin' | 'rd' | 'other'
  label: string
  /** WP 语义标签（=WP 第三参 / ACNR label） */
  wpLabel: string
  /** 对方底稿编码 */
  targetWpCode: string
  /** 勾稽行展示文案中的索引 */
  indexHint: string
}

/** 勾稽核对行（纵向核对对方科目） */
export interface H8ReconciliationRow {
  label: string
  calculated: number
  counterpart: number | null
  difference: number | null
  targetWpCode: string
  indexHint: string
  statusText: string
  pullMessage?: string
  /** 费用列字段；H8-8 汇总行为空，不可手工改对方数 */
  field?: H8CounterpartField | ''
  /** 对方数是否为手工覆盖 */
  isManual?: boolean
}

export type H8ExpenseField =
  | 'operatingCost'
  | 'manufacturing'
  | 'selling'
  | 'admin'
  | 'rd'
  | 'other'

export type H8PriorConsistency = 'Y' | 'N' | ''

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_PREFIX = 'H8-9'
const ROWS_KEY = `${ITEM_PREFIX}-alloc-rows`
const ALLOC_TOTAL_KEY = `${ITEM_PREFIX}-alloc-total`
const COUNTERPART_KEY = `${ITEM_PREFIX}-counterpart-amounts`
const PRIOR_KEY = `${ITEM_PREFIX}-prior-consistency`
const LEGACY_ALLOC_KEY = 'H8-9-alloc-rows' // 与 ROWS_KEY 相同；旧比例结构需迁移

/** Excel 模板默认 5 类（实测 H8-9 红字类别） */
export const H8_DEFAULT_CATEGORIES = [
  '房屋及建筑物',
  '机器设备',
  '运输设备',
  '办公设备',
  '其他设备',
] as const

/**
 * 费用列 ↔ 对方底稿（对齐 Excel 表头：营业成本/制造费用/销售费用/管理费用/研发支出/…）
 * D5=营业成本，F2=制造费用，K8=销售，K9=管理，I6=研发
 */
export const H8_EXPENSE_COLS: H8ExpenseColMeta[] = [
  { field: 'operatingCost', label: '营业成本', wpLabel: '营业成本折旧', targetWpCode: 'D5', indexHint: 'D5' },
  { field: 'manufacturing', label: '制造费用', wpLabel: '制造费用折旧', targetWpCode: 'F2', indexHint: 'F2' },
  { field: 'selling', label: '销售费用', wpLabel: '销售费用折旧', targetWpCode: 'K8', indexHint: 'K8' },
  { field: 'admin', label: '管理费用', wpLabel: '管理费用折旧', targetWpCode: 'K9', indexHint: 'K9' },
  { field: 'rd', label: '研发支出', wpLabel: '研发支出折旧', targetWpCode: 'I6', indexHint: 'I6' },
  { field: 'other', label: '其他', wpLabel: '其他折旧', targetWpCode: '', indexHint: '—' },
]

const TOLERANCE = 0.01

type CounterpartSnapshot = Partial<Record<H8CounterpartField, number | null>> & {
  _meta?: Partial<Record<H8CounterpartField, { message?: string; matchedLabel?: string; status?: string }>>
  _pulledAt?: string
}

/** 旧版比例分配行 → 费用字段映射 */
const LEGACY_EXPENSE_MAP: Record<string, keyof H8AllocRow> = {
  营业成本: 'operatingCost',
  生产成本: 'operatingCost',
  制造费用: 'manufacturing',
  销售费用: 'selling',
  管理费用: 'admin',
  研发费用: 'rd',
  研发支出: 'rd',
  在建工程: 'other',
  其他: 'other',
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function _genRowId(): string {
  return `h8-alloc-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function _blankRow(category: string, depTotal = 0): H8AllocRow {
  return {
    rowId: _genRowId(),
    category,
    depTotal,
    operatingCost: 0,
    manufacturing: 0,
    selling: 0,
    admin: 0,
    rd: 0,
    other: 0,
    remark: '',
  }
}

export function calcH8RowAllocSum(row: H8AllocRow): number {
  return (
    (Number(row.operatingCost) || 0) +
    (Number(row.manufacturing) || 0) +
    (Number(row.selling) || 0) +
    (Number(row.admin) || 0) +
    (Number(row.rd) || 0) +
    (Number(row.other) || 0)
  )
}

export function isH8RowBalanced(row: H8AllocRow): boolean {
  if (row._isSummary || row._isReconcile) return true
  return Math.abs(calcH8RowAllocSum(row) - (Number(row.depTotal) || 0)) < TOLERANCE
}

function _isLegacyRatioRow(raw: any): boolean {
  return !!(raw?.expenseType && raw?.category == null && (raw?.allocRatio != null || raw?.allocAmount != null))
}

/** 旧比例结构 → 矩阵：金额落入「其他设备」对应费用列 */
function _migrateLegacyRows(legacy: any[]): H8AllocRow[] {
  const rows = H8_DEFAULT_CATEGORIES.map((c) => _blankRow(c))
  const catchAll = rows[rows.length - 1]!
  for (const raw of legacy) {
    if (!_isLegacyRatioRow(raw) && !raw?.expenseType) continue
    const field = LEGACY_EXPENSE_MAP[String(raw.expenseType).trim()] ?? 'other'
    const amt = Number(raw.allocAmount) || 0
    if (field === 'category' || field === 'rowId' || field === 'remark' || field === 'depTotal') continue
    ;(catchAll as any)[field] = ((catchAll as any)[field] || 0) + amt
  }
  catchAll.depTotal = calcH8RowAllocSum(catchAll)
  catchAll.remark = '由旧版比例分配结构自动迁移'
  return rows
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH8DepreciationAlloc(params: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  /** H8-8 → H8-9 按分类折旧额 */
  crossSheetByCategory?: Ref<Record<string, number>>
  crossSheetDepTotal?: Ref<number>
  onSave?: (itemId: string, value: any) => void
  onPublishEvent?: (event: string, payload: any) => void
}) {
  const { allResponses, onSave, onPublishEvent } = params

  const rows = ref<H8AllocRow[]>([])
  const counterpartSnapshot = ref<CounterpartSnapshot>({})
  const counterpartPulledAt = ref('')
  /** 分配方法与上期是否一致（Excel 提示第2点） */
  const priorConsistent = ref<H8PriorConsistency>('')
  const priorNote = ref('')

  // ─── Load ──────────────────────────────────────────────────────────────────

  function _getString(itemId: string): string {
    const i = allResponses.value.get(itemId)
    return (i?.remark ?? i?.conclusion ?? '') as string
  }

  function _getJson(itemId: string): any {
    const raw = _getString(itemId)
    if (!raw) return null
    try { return JSON.parse(raw) } catch { return raw }
  }

  function _normalizeRow(raw: any): H8AllocRow {
    return {
      rowId: raw.rowId ?? _genRowId(),
      category: raw.category ?? '',
      depTotal: Number(raw.depTotal) || 0,
      operatingCost: Number(raw.operatingCost ?? raw.productionCost) || 0,
      manufacturing: Number(raw.manufacturing) || 0,
      selling: Number(raw.selling) || 0,
      admin: Number(raw.admin) || 0,
      rd: Number(raw.rd) || 0,
      other: Number(raw.other) || 0,
      remark: raw.remark ?? '',
    }
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

  /** 从 H8-8 按分类同步折旧总额；新分类自动补行 */
  function _syncFromH88(): void {
    const byCat = params.crossSheetByCategory?.value
    if (!byCat || Object.keys(byCat).length === 0) {
      // 仅有总额时：若各类 depTotal 全 0，把总额摊到首行提示编制
      const total = params.crossSheetDepTotal?.value ?? 0
      if (total > 0 && rows.value.every((r) => !r.depTotal)) {
        // 不自动写入单行，避免误导；总额由 h88DepTotal 展示
      }
      return
    }

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

  function _loadData(): void {
    const data = _getJson(ROWS_KEY) ?? _getJson(LEGACY_ALLOC_KEY)

    if (Array.isArray(data) && data.length > 0) {
      if (data.some(_isLegacyRatioRow)) {
        rows.value = _migrateLegacyRows(data)
        // 迁移后立即持久化为新结构
        _persist()
      } else {
        rows.value = data.map(_normalizeRow).filter((r) => r.category)
      }
    } else {
      rows.value = []
    }

    if (rows.value.length === 0) {
      rows.value = H8_DEFAULT_CATEGORIES.map((c) => _blankRow(c))
    }

    const prior = _getJson(PRIOR_KEY)
    if (prior && typeof prior === 'object') {
      priorConsistent.value = (prior.consistent === 'Y' || prior.consistent === 'N') ? prior.consistent : ''
      priorNote.value = String(prior.note ?? '')
    } else {
      priorConsistent.value = ''
      priorNote.value = ''
    }

    _loadCounterpartSnapshot()
    _syncFromH88()
  }

  // ─── Computed: 列合计 ──────────────────────────────────────────────────────

  const colTotals = computed(() => {
    const t = {
      depTotal: 0,
      operatingCost: 0,
      manufacturing: 0,
      selling: 0,
      admin: 0,
      rd: 0,
      other: 0,
      allocSum: 0,
    }
    for (const r of rows.value) {
      t.depTotal += Number(r.depTotal) || 0
      t.operatingCost += Number(r.operatingCost) || 0
      t.manufacturing += Number(r.manufacturing) || 0
      t.selling += Number(r.selling) || 0
      t.admin += Number(r.admin) || 0
      t.rd += Number(r.rd) || 0
      t.other += Number(r.other) || 0
      t.allocSum += calcH8RowAllocSum(r)
    }
    return t
  })

  const summaryRow = computed<H8AllocRow>(() => ({
    rowId: '__summary__',
    category: '合计',
    depTotal: colTotals.value.depTotal,
    operatingCost: colTotals.value.operatingCost,
    manufacturing: colTotals.value.manufacturing,
    selling: colTotals.value.selling,
    admin: colTotals.value.admin,
    rd: colTotals.value.rd,
    other: colTotals.value.other,
    remark: '',
    _isSummary: true,
  }))

  const reconcileRow = computed<H8AllocRow>(() => ({
    rowId: '__reconcile__',
    category: '勾稽关系情况',
    depTotal: 0,
    operatingCost: 0,
    manufacturing: 0,
    selling: 0,
    admin: 0,
    rd: 0,
    other: 0,
    remark: '',
    _isReconcile: true,
  }))

  const displayRows = computed<H8AllocRow[]>(() => [
    ...rows.value,
    summaryRow.value,
    reconcileRow.value,
  ])

  // ─── 与 H8-8 横向平衡 ─────────────────────────────────────────────────────

  const h88DepTotal = computed(() => params.crossSheetDepTotal?.value ?? colTotals.value.depTotal)
  const vsH88Diff = computed(() => colTotals.value.allocSum - h88DepTotal.value)
  const isBalancedWithH88 = computed(() => Math.abs(vsH88Diff.value) < TOLERANCE)

  const categoryDiffs = computed(() => {
    const byCat = params.crossSheetByCategory?.value ?? {}
    return rows.value.map((r) => {
      const h88 = Number(byCat[r.category] ?? r.depTotal) || 0
      const alloc = calcH8RowAllocSum(r)
      const diff = alloc - h88
      return {
        category: r.category,
        h88,
        alloc,
        diff,
        balanced: Math.abs(diff) < TOLERANCE,
      }
    })
  })

  /**
   * 将分配未配平差额回写 H8-8 审计结论（闭环留痕）
   */
  function writeBackUnallocatedToH88(): string {
    const unbalanced = categoryDiffs.value.filter((c) => !c.balanced)
    const lines = [
      `[H8-9→H8-8 闭环] ${new Date().toISOString().slice(0, 19)}`,
      `分配合计 ${colTotals.value.allocSum.toFixed(2)} vs H8-8 ${h88DepTotal.value.toFixed(2)}，差额 ${vsH88Diff.value.toFixed(2)}`,
    ]
    if (unbalanced.length) {
      lines.push('分类未配平行：')
      for (const c of unbalanced) {
        lines.push(`  · ${c.category}：分配 ${c.alloc.toFixed(2)} / H8-8 ${c.h88.toFixed(2)} / 差 ${c.diff.toFixed(2)}`)
      }
    } else {
      lines.push('各类别分配与 H8-8 勾稽一致。')
    }
    const text = lines.join('\n')
    onSave?.('H8-8-audit-conclusion', text)
    onSave?.('H8-9-h88-writeback', {
      at: new Date().toISOString(),
      vsH88Diff: vsH88Diff.value,
      categoryDiffs: unbalanced,
    })
    return text
  }

  // ─── 勾稽核对表（纵向 → 对方科目）──────────────────────────────────────────

  const reconciliationRows = computed<H8ReconciliationRow[]>(() => {
    const snap = counterpartSnapshot.value
    const cols: H8ReconciliationRow[] = H8_EXPENSE_COLS.filter((c) => c.targetWpCode).map((c) => {
      const field = c.field as H8CounterpartField
      const calculated = colTotals.value[c.field]
      const counterpart = snap[field] !== undefined ? (snap[field] as number | null) : null
      const hasCounterpart = counterpart != null
      const difference = hasCounterpart ? calculated - counterpart : null
      const meta = snap._meta?.[field]
      const isManual = meta?.matchedLabel === '手工覆盖'
      let statusText: string
      if (calculated === 0 && !hasCounterpart) {
        statusText = '本期无分配'
      } else if (!hasCounterpart) {
        statusText = meta?.message || `待拉取对方数，详见${c.indexHint}`
      } else if (Math.abs(difference!) < TOLERANCE) {
        statusText = isManual
          ? `勾稽一致（手工），详见${c.indexHint}`
          : `勾稽一致，详见${c.indexHint}`
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
        field,
        isManual,
      }
    })

    cols.unshift({
      label: '分配合计 vs H8-8',
      calculated: colTotals.value.allocSum,
      counterpart: h88DepTotal.value,
      difference: vsH88Diff.value,
      targetWpCode: 'H8-8',
      indexHint: 'H8-8',
      statusText: isBalancedWithH88.value
        ? '勾稽一致，详见H8-8'
        : `差异 ${vsH88Diff.value.toFixed(2)}，详见H8-8`,
      field: '',
    })

    return cols
  })

  function applyCounterpartPull(pulled: Record<H8CounterpartField, H8CounterpartAmount>): void {
    const prev = counterpartSnapshot.value
    const next: CounterpartSnapshot = {
      _pulledAt: new Date().toISOString(),
      _meta: {},
    }
    for (const [field, info] of Object.entries(pulled) as [H8CounterpartField, H8CounterpartAmount][]) {
      // 已手工覆盖且拉取失败时保留手工数
      const wasManual = prev._meta?.[field]?.matchedLabel === '手工覆盖'
      if (info.status !== 'ok' && wasManual && prev[field] != null) {
        next[field] = prev[field]
        next._meta![field] = {
          message: `拉取失败，保留手工数；${info.message}`,
          matchedLabel: '手工覆盖',
          status: 'ok',
        }
        continue
      }
      next[field] = info.amount
      next._meta![field] = {
        message: info.message,
        matchedLabel: info.matchedLabel,
        status: info.status,
      }
    }
    counterpartSnapshot.value = next
    counterpartPulledAt.value = next._pulledAt!
    onSave?.(COUNTERPART_KEY, next)
  }

  /** 手工覆盖对方底稿数（拉取不到「使用权资产折旧」行时） */
  function setCounterpartManual(field: H8CounterpartField, amount: number | null): void {
    const next: CounterpartSnapshot = {
      ...counterpartSnapshot.value,
      _meta: { ...(counterpartSnapshot.value._meta ?? {}) },
    }
    next[field] = amount
    next._meta![field] = {
      message: amount == null ? '已清空手工数' : '手工录入对方底稿数',
      matchedLabel: amount == null ? '' : '手工覆盖',
      status: amount == null ? 'item_missing' : 'ok',
    }
    counterpartSnapshot.value = next
    onSave?.(COUNTERPART_KEY, next)
  }

  // ─── Mutations ─────────────────────────────────────────────────────────────

  function updateCell(rowId: string, field: keyof H8AllocRow, value: any): void {
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    _persist()
  }

  function addRow(category?: string): void {
    const cat = category?.trim() || `分类-${rows.value.length + 1}`
    const dep = params.crossSheetByCategory?.value?.[cat] ?? 0
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

  /**
   * 将某行未分配差额（depTotal − 已分配）一键并入指定费用列
   */
  function allocateRemainderTo(rowId: string, field: H8ExpenseField): number {
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row) return 0
    const rem = (Number(row.depTotal) || 0) - calcH8RowAllocSum(row)
    if (Math.abs(rem) < TOLERANCE) return 0
    ;(row as any)[field] = (Number((row as any)[field]) || 0) + rem
    _persist()
    return rem
  }

  /**
   * 所有未配平行的差额一并计入指定费用列，返回调整行数
   */
  function allocateAllRemaindersTo(field: H8ExpenseField): number {
    let n = 0
    for (const row of rows.value) {
      const rem = (Number(row.depTotal) || 0) - calcH8RowAllocSum(row)
      if (Math.abs(rem) < TOLERANCE) continue
      ;(row as any)[field] = (Number((row as any)[field]) || 0) + rem
      n++
    }
    if (n) _persist()
    return n
  }

  function savePriorAssessment(consistent: H8PriorConsistency, note: string): void {
    priorConsistent.value = consistent
    priorNote.value = note
    onSave?.(PRIOR_KEY, { consistent, note })
  }

  function publishAllocated(): void {
    const t = colTotals.value
    const payload = {
      wp_code: 'H8',
      sheet: '折旧分配分析表H8-9',
      labels: {
        营业成本折旧: t.operatingCost,
        制造费用折旧: t.manufacturing,
        销售费用折旧: t.selling,
        管理费用折旧: t.admin,
        研发支出折旧: t.rd,
        其他折旧: t.other,
        全年折旧总额: t.allocSum,
      },
      totalOperating: t.operatingCost,
      totalManufacture: t.manufacturing,
      totalSales: t.selling,
      totalAdmin: t.admin,
      totalRd: t.rd,
      totalOther: t.other,
      totalAlloc: t.allocSum,
      priorConsistent: priorConsistent.value,
      byCategory: rows.value.reduce((acc, r) => {
        acc[r.category] = {
          depTotal: r.depTotal,
          operating: r.operatingCost,
          manufacture: r.manufacturing,
          sales: r.selling,
          admin: r.admin,
          rd: r.rd,
          other: r.other,
        }
        return acc
      }, {} as Record<string, any>),
    }
    onPublishEvent?.('h8:depreciation-allocated', payload)
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('h8:depreciation-allocated', { detail: payload }))
    }
  }

  /** 客户端 xlsx 导入导出（对齐 H8-8/H8-10） */
  async function exportData(kind: 'template' | 'data'): Promise<void> {
    const XLSX = await import('xlsx')
    const headers = [
      '使用权资产类别', '折旧总额(H8-8)',
      '营业成本', '制造费用', '销售费用', '管理费用', '研发支出', '其他', '备注',
    ]
    const dataRows = kind === 'template'
      ? []
      : rows.value.map((r) => ({
          '使用权资产类别': r.category || '',
          '折旧总额(H8-8)': r.depTotal || 0,
          '营业成本': r.operatingCost || 0,
          '制造费用': r.manufacturing || 0,
          '销售费用': r.selling || 0,
          '管理费用': r.admin || 0,
          '研发支出': r.rd || 0,
          '其他': r.other || 0,
          '备注': r.remark || '',
        }))
    const ws = kind === 'template'
      ? XLSX.utils.aoa_to_sheet([headers])
      : XLSX.utils.json_to_sheet(dataRows, { header: headers })
    const wb = XLSX.utils.book_new()
    XLSX.utils.book_append_sheet(wb, ws, 'H8-9折旧分配')
    XLSX.writeFile(wb, `H8-9_折旧分配_${kind === 'template' ? '模板' : '数据'}.xlsx`)
  }

  async function importData(file: File, replace = true): Promise<{ imported: number }> {
    const XLSX = await import('xlsx')
    const buffer = await file.arrayBuffer()
    const wb = XLSX.read(buffer, { type: 'array', cellDates: false })
    const sheet = wb.Sheets[wb.SheetNames[0]]
    const rowsRaw = XLSX.utils.sheet_to_json<Record<string, any>>(sheet, { defval: '' })
    const mapped = rowsRaw
      .filter((r) => String(r['使用权资产类别'] || r['类别'] || '').trim())
      .map((r) => {
        const cat = String(r['使用权资产类别'] || r['类别'] || '').trim()
        const row = _blankRow(cat, Number(r['折旧总额(H8-8)'] || r['折旧总额'] || 0) || 0)
        row.operatingCost = Number(r['营业成本'] || 0) || 0
        row.manufacturing = Number(r['制造费用'] || 0) || 0
        row.selling = Number(r['销售费用'] || 0) || 0
        row.admin = Number(r['管理费用'] || 0) || 0
        row.rd = Number(r['研发支出'] || 0) || 0
        row.other = Number(r['其他'] || 0) || 0
        row.remark = String(r['备注'] || '')
        return row
      })
    if (!mapped.length) return { imported: 0 }
    rows.value = replace ? mapped : [...rows.value, ...mapped]
    _syncFromH88()
    _persist()
    return { imported: mapped.length }
  }

  function _persist(): void {
    onSave?.(ROWS_KEY, rows.value.map((r) => ({
      rowId: r.rowId,
      category: r.category,
      depTotal: r.depTotal,
      operatingCost: r.operatingCost,
      manufacturing: r.manufacturing,
      selling: r.selling,
      admin: r.admin,
      rd: r.rd,
      other: r.other,
      remark: r.remark,
    })))
    onSave?.(ALLOC_TOTAL_KEY, colTotals.value.allocSum)
  }

  // ─── Init ──────────────────────────────────────────────────────────────────

  watch(allResponses, () => _loadData(), { immediate: true })
  watch(
    () => params.crossSheetByCategory?.value,
    () => _syncFromH88(),
    { deep: true },
  )

  return {
    rows,
    displayRows,
    summaryRow,
    colTotals,
    vsH88Diff,
    isBalancedWithH88,
    h88DepTotal,
    categoryDiffs,
    writeBackUnallocatedToH88,
    reconciliationRows,
    counterpartPulledAt,
    applyCounterpartPull,
    setCounterpartManual,
    allocateRemainderTo,
    allocateAllRemaindersTo,
    priorConsistent,
    priorNote,
    savePriorAssessment,
    updateCell,
    addRow,
    removeRow,
    publishAllocated,
    exportData,
    importData,
    calcRowAllocSum: calcH8RowAllocSum,
    isRowBalanced: isH8RowBalanced,
  }
}

export default useH8DepreciationAlloc
