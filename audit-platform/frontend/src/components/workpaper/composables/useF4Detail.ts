/**
 * useF4Detail — F4-2 应付账款明细表（源表27列）
 *
 * 公式严格对齐 Excel：
 * H 期初审定余额 = E期初未审 + F期初AJE + G期初RJE
 * K 期末余额 = E期初未审 + J贷方发生 - I借方发生
 * M 期末未审余额 = K期末余额 + L被审计单位重分类
 * T 审定数 = M期末未审 + R账项调整 + S重分类调整
 * N:Q 未审账龄合计应等于 M；U:X 审定账龄合计应等于 T。
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import {
  parseNum,
  calcCreditBalance,
  calcAuditedAmount,
  calcAgingTotal,
  calcAgingCrossCheck,
  calcSubtotal,
} from './useF4AccPayFormulaEngine'
import { readRowJson, type ChecklistResponse } from './useF4FormData'

// ─── 类型定义 ─────────────────────────────────────────────────────────────────

export interface APDetailRow {
  rowId: string
  seq: number
  // A:D 基础信息
  creditor: string
  companyCode: string
  relatedPartyType: string
  paymentNature: string
  // E:M 期初、本期发生及期末未审
  openingUnadjusted: number
  openingAje: number
  openingRje: number
  openingAdjusted: number
  currentDebit: number
  currentCredit: number
  closingBalance: number
  entityReclassification: number
  closingUnadjusted: number
  // N:Q 未审账龄
  unadjustedAgingLt1: number
  unadjustedAging1to2: number
  unadjustedAging2to3: number
  unadjustedAgingGt3: number
  unadjustedAgingTotal: number
  // R:T 调整与审定
  closingAje: number
  closingRje: number
  closingAdjusted: number
  // U:X 审定账龄
  auditedAgingLt1: number
  auditedAging1to2: number
  auditedAging2to3: number
  auditedAgingGt3: number
  auditedAgingTotal: number
  // Y:AA 其他审计信息
  isConfirmed: string
  subsequentPayment: number
  remark: string
  unadjustedAgingMismatch: boolean
  auditedAgingMismatch: boolean
  subsequentPaymentExceedsBalance: boolean
}

export type F4DetailInputType = 'text' | 'number' | 'select'

export interface F4DetailColumn {
  prop: keyof APDetailRow | string
  label: string
  group: 'identity' | 'movement' | 'unadjusted-aging' | 'audit' | 'other'
  width?: number
  minWidth?: number
  formula?: string
  editable?: boolean
  inputType?: F4DetailInputType
  options?: readonly string[]
}

export const F4_RELATED_PARTY_OPTIONS = [
  '合并范围内关联方',
  '合并范围外关联方',
  '非关联方',
] as const

export const F4_PAYMENT_NATURE_OPTIONS = ['货款', '工程款', '设备款', '服务费', '其他'] as const
export const F4_CONFIRMATION_OPTIONS = ['是', '否', '不适用'] as const
export const F4_AGING_BUCKET_OPTIONS = [
  { value: 'lt1', label: '1年以下' },
  { value: '1to2', label: '1～2年' },
  { value: '2to3', label: '2～3年' },
  { value: 'gt3', label: '3年以上' },
] as const
export type F4AgingBucket = typeof F4_AGING_BUCKET_OPTIONS[number]['value']

/** A:M 身份、期初及本期变动（13列） */
export const F4_DETAIL_BASIC_COLUMNS: F4DetailColumn[] = [
  { prop: 'creditor', label: '债权人名称', group: 'identity', minWidth: 150, editable: true, inputType: 'text' },
  { prop: 'companyCode', label: '公司代码', group: 'identity', minWidth: 110, editable: true, inputType: 'text' },
  { prop: 'relatedPartyType', label: '关联方类型', group: 'identity', minWidth: 150, editable: true, inputType: 'select', options: F4_RELATED_PARTY_OPTIONS },
  { prop: 'paymentNature', label: '款项性质', group: 'identity', minWidth: 110, editable: true, inputType: 'select', options: F4_PAYMENT_NATURE_OPTIONS },
  { prop: 'openingUnadjusted', label: '期初未审余额', group: 'movement', minWidth: 120, editable: true, inputType: 'number' },
  { prop: 'openingAje', label: '期初账项调整', group: 'movement', minWidth: 120, editable: true, inputType: 'number' },
  { prop: 'openingRje', label: '期初重分类调整', group: 'movement', minWidth: 130, editable: true, inputType: 'number' },
  { prop: 'openingAdjusted', label: '期初审定余额', group: 'movement', minWidth: 120, formula: '期初未审+期初AJE+期初RJE', editable: false },
  { prop: 'currentDebit', label: '借方发生', group: 'movement', minWidth: 110, editable: true, inputType: 'number' },
  { prop: 'currentCredit', label: '贷方发生', group: 'movement', minWidth: 110, editable: true, inputType: 'number' },
  { prop: 'closingBalance', label: '期末余额', group: 'movement', minWidth: 110, formula: '期初未审+贷方-借方', editable: false },
  { prop: 'entityReclassification', label: '被审计单位重分类调整', group: 'movement', minWidth: 160, editable: true, inputType: 'number' },
  { prop: 'closingUnadjusted', label: '期末未审余额', group: 'movement', minWidth: 120, formula: '期末余额+被审计单位重分类', editable: false },
]

/** N:Q + Y:AA 未审账龄及其他审计信息（7列） */
export const F4_DETAIL_AGING_COLUMNS: F4DetailColumn[] = [
  { prop: 'unadjustedAgingLt1', label: '未审账龄·1年以下', group: 'unadjusted-aging', minWidth: 125, editable: true, inputType: 'number' },
  { prop: 'unadjustedAging1to2', label: '未审账龄·1～2年', group: 'unadjusted-aging', minWidth: 125, editable: true, inputType: 'number' },
  { prop: 'unadjustedAging2to3', label: '未审账龄·2～3年', group: 'unadjusted-aging', minWidth: 125, editable: true, inputType: 'number' },
  { prop: 'unadjustedAgingGt3', label: '未审账龄·3年以上', group: 'unadjusted-aging', minWidth: 130, editable: true, inputType: 'number' },
  { prop: 'isConfirmed', label: '是否函证', group: 'other', minWidth: 100, editable: true, inputType: 'select', options: F4_CONFIRMATION_OPTIONS },
  { prop: 'subsequentPayment', label: '期后付款', group: 'other', minWidth: 115, editable: true, inputType: 'number' },
  { prop: 'remark', label: '备注', group: 'other', minWidth: 180, editable: true, inputType: 'text' },
]

/** R:X 调整、审定及审定账龄（7列） */
export const F4_DETAIL_AUDIT_COLUMNS: F4DetailColumn[] = [
  { prop: 'closingAje', label: '账项调整', group: 'audit', minWidth: 110, editable: true, inputType: 'number' },
  { prop: 'closingRje', label: '重分类调整', group: 'audit', minWidth: 120, editable: true, inputType: 'number' },
  { prop: 'closingAdjusted', label: '审定数', group: 'audit', minWidth: 115, formula: '期末未审+AJE+RJE', editable: false },
  { prop: 'auditedAgingLt1', label: '审定账龄·1年以下', group: 'audit', minWidth: 125, editable: true, inputType: 'number' },
  { prop: 'auditedAging1to2', label: '审定账龄·1～2年', group: 'audit', minWidth: 125, editable: true, inputType: 'number' },
  { prop: 'auditedAging2to3', label: '审定账龄·2～3年', group: 'audit', minWidth: 125, editable: true, inputType: 'number' },
  { prop: 'auditedAgingGt3', label: '审定账龄·3年以上', group: 'audit', minWidth: 130, editable: true, inputType: 'number' },
]

/** 严格按 Excel A:AA 排列的27列。 */
export const F4_DETAIL_ALL_COLUMNS: F4DetailColumn[] = [
  ...F4_DETAIL_BASIC_COLUMNS,
  ...F4_DETAIL_AGING_COLUMNS.slice(0, 4),
  ...F4_DETAIL_AUDIT_COLUMNS,
  ...F4_DETAIL_AGING_COLUMNS.slice(4),
]

export interface StoredAPDetailRow {
  rowId: string
  seq: number
  creditor: string
  companyCode: string
  relatedPartyType: string
  paymentNature: string
  openingUnadjusted: number
  openingAje: number
  openingRje: number
  currentDebit: number
  currentCredit: number
  entityReclassification: number
  unadjustedAgingLt1: number
  unadjustedAging1to2: number
  unadjustedAging2to3: number
  unadjustedAgingGt3: number
  closingAje: number
  closingRje: number
  auditedAgingLt1: number
  auditedAging1to2: number
  auditedAging2to3: number
  auditedAgingGt3: number
  isConfirmed: string
  subsequentPayment: number
  remark: string
}

export interface UseF4DetailOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}

// ─── 工具函数 ─────────────────────────────────────────────────────────────────

const STORAGE_KEY = 'F4-2-rows'

function generateRowId(): string {
  return `f4d-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`
}

function emptyStored(seq: number): StoredAPDetailRow {
  return {
    rowId: generateRowId(),
    seq,
    creditor: '',
    companyCode: '',
    relatedPartyType: '',
    paymentNature: '',
    openingUnadjusted: 0,
    openingAje: 0,
    openingRje: 0,
    currentDebit: 0,
    currentCredit: 0,
    entityReclassification: 0,
    unadjustedAgingLt1: 0,
    unadjustedAging1to2: 0,
    unadjustedAging2to3: 0,
    unadjustedAgingGt3: 0,
    closingAje: 0,
    closingRje: 0,
    auditedAgingLt1: 0,
    auditedAging1to2: 0,
    auditedAging2to3: 0,
    auditedAgingGt3: 0,
    isConfirmed: '',
    subsequentPayment: 0,
    remark: '',
  }
}

export function computeF4DetailRow(stored: StoredAPDetailRow): APDetailRow {
  const openingAdjusted = calcAuditedAmount(
    stored.openingUnadjusted,
    stored.openingAje,
    stored.openingRje,
  )
  // 源表 K 列以期初未审余额（E）为起点，而非期初审定余额（H）。
  const closingBalance = calcCreditBalance(
    stored.openingUnadjusted,
    stored.currentCredit,
    stored.currentDebit,
  )
  const closingUnadjusted = closingBalance + stored.entityReclassification
  const unadjustedAgingTotal = calcAgingTotal(
    stored.unadjustedAgingLt1,
    stored.unadjustedAging1to2,
    stored.unadjustedAging2to3,
    stored.unadjustedAgingGt3,
  )
  const closingAdjusted = calcAuditedAmount(
    closingUnadjusted,
    stored.closingAje,
    stored.closingRje,
  )
  const auditedAgingTotal = calcAgingTotal(
    stored.auditedAgingLt1,
    stored.auditedAging1to2,
    stored.auditedAging2to3,
    stored.auditedAgingGt3,
  )
  return {
    ...stored,
    openingAdjusted,
    closingBalance,
    closingUnadjusted,
    unadjustedAgingTotal,
    closingAdjusted,
    auditedAgingTotal,
    unadjustedAgingMismatch: !calcAgingCrossCheck(unadjustedAgingTotal, closingUnadjusted),
    auditedAgingMismatch: !calcAgingCrossCheck(auditedAgingTotal, closingAdjusted),
    subsequentPaymentExceedsBalance:
      stored.subsequentPayment - Math.abs(closingAdjusted) >= 0.01,
  }
}

function joinLegacyRemark(raw: any): string {
  const parts = [String(raw?.remark ?? '').trim()]
  if (raw?.confirmationResult) parts.push(`函证结果：${raw.confirmationResult}`)
  if (raw?.subsequentPaymentDate) parts.push(`期后付款日期：${raw.subsequentPaymentDate}`)
  if (raw?.indexRef) parts.push(`原索引：${raw.indexRef}`)
  return parts.filter(Boolean).join('；')
}

export function migrateF4DetailRows(jsonStr: string | null | undefined): StoredAPDetailRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    if (!Array.isArray(parsed)) return []
    return parsed.map((raw: any, i: number) => ({
      ...emptyStored(i + 1),
      rowId: raw.rowId || raw.id || generateRowId(),
      seq: raw.seq ?? i + 1,
      creditor: raw.creditor || '',
      companyCode: raw.companyCode || '',
      relatedPartyType: raw.relatedPartyType || '',
      paymentNature: raw.paymentNature || '',
      openingUnadjusted: parseNum(raw.openingUnadjusted ?? raw.openingAdjusted),
      openingAje: parseNum(raw.openingAje),
      openingRje: parseNum(raw.openingRje),
      currentDebit: parseNum(raw.currentDebit ?? raw.debit),
      currentCredit: parseNum(raw.currentCredit ?? raw.credit),
      entityReclassification: parseNum(raw.entityReclassification),
      unadjustedAgingLt1: parseNum(raw.unadjustedAgingLt1 ?? raw.aging1Year ?? raw.agingLt1),
      unadjustedAging1to2: parseNum(raw.unadjustedAging1to2 ?? raw.aging1to2Year ?? raw.aging1to2),
      unadjustedAging2to3: parseNum(raw.unadjustedAging2to3 ?? raw.aging2to3Year ?? raw.aging2to3),
      unadjustedAgingGt3: parseNum(raw.unadjustedAgingGt3 ?? raw.aging3YearPlus ?? raw.agingGt3),
      closingAje: parseNum(raw.closingAje ?? raw.ajeAdjustment ?? raw.aje),
      closingRje: parseNum(raw.closingRje ?? raw.rjeReclassification ?? raw.rje),
      auditedAgingLt1: parseNum(raw.auditedAgingLt1 ?? raw.adjustedAging1),
      auditedAging1to2: parseNum(raw.auditedAging1to2 ?? raw.adjustedAging2),
      auditedAging2to3: parseNum(raw.auditedAging2to3 ?? raw.adjustedAging3),
      auditedAgingGt3: parseNum(raw.auditedAgingGt3 ?? raw.adjustedAging4),
      isConfirmed: raw.isConfirmed || '',
      subsequentPayment: parseNum(raw.subsequentPayment),
      remark: joinLegacyRemark(raw),
    }))
  } catch {
    return []
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useF4Detail(options: UseF4DetailOptions) {
  const { allResponses, isReadonly } = options
  const readonly = isReadonly ?? ref(false)

  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  const activeSegment = ref<'basic' | 'aging' | 'audit'>('basic')
  const storedData = ref<StoredAPDetailRow[]>([])
  const searchQuery = ref('')

  // ─── 加载 ─────────────────────────────────────────────────────────────────

  function loadRows(): void {
    storedData.value = migrateF4DetailRows(readRowJson(allResponses.value.get(STORAGE_KEY)))
    if (storedData.value.length === 0) storedData.value = [emptyStored(1)]
  }

  watch(() => readRowJson(allResponses.value.get(STORAGE_KEY)), () => {
    if (storedData.value.length === 0) loadRows()
  }, { immediate: true })

  // ─── 计算行 ───────────────────────────────────────────────────────────────

  const rows: ComputedRef<APDetailRow[]> = computed(() => storedData.value.map(computeF4DetailRow))

  const filteredRows: ComputedRef<APDetailRow[]> = computed(() => {
    const q = searchQuery.value.trim().toLowerCase()
    if (!q) return rows.value
    return rows.value.filter(
      (r) =>
        r.creditor.toLowerCase().includes(q) ||
        r.companyCode.toLowerCase().includes(q) ||
        r.paymentNature.toLowerCase().includes(q) ||
        r.relatedPartyType.toLowerCase().includes(q),
    )
  })

  // ─── 合计行 ───────────────────────────────────────────────────────────────

  const subtotalRow: ComputedRef<APDetailRow> = computed(() =>
    computeF4DetailRow({
      ...emptyStored(0),
      rowId: 'subtotal',
      creditor: '合计',
      openingUnadjusted: calcSubtotal(rows.value.map((r) => r.openingUnadjusted)),
      openingAje: calcSubtotal(rows.value.map((r) => r.openingAje)),
      openingRje: calcSubtotal(rows.value.map((r) => r.openingRje)),
      currentDebit: calcSubtotal(rows.value.map((r) => r.currentDebit)),
      currentCredit: calcSubtotal(rows.value.map((r) => r.currentCredit)),
      entityReclassification: calcSubtotal(rows.value.map((r) => r.entityReclassification)),
      unadjustedAgingLt1: calcSubtotal(rows.value.map((r) => r.unadjustedAgingLt1)),
      unadjustedAging1to2: calcSubtotal(rows.value.map((r) => r.unadjustedAging1to2)),
      unadjustedAging2to3: calcSubtotal(rows.value.map((r) => r.unadjustedAging2to3)),
      unadjustedAgingGt3: calcSubtotal(rows.value.map((r) => r.unadjustedAgingGt3)),
      closingAje: calcSubtotal(rows.value.map((r) => r.closingAje)),
      closingRje: calcSubtotal(rows.value.map((r) => r.closingRje)),
      auditedAgingLt1: calcSubtotal(rows.value.map((r) => r.auditedAgingLt1)),
      auditedAging1to2: calcSubtotal(rows.value.map((r) => r.auditedAging1to2)),
      auditedAging2to3: calcSubtotal(rows.value.map((r) => r.auditedAging2to3)),
      auditedAgingGt3: calcSubtotal(rows.value.map((r) => r.auditedAgingGt3)),
      subsequentPayment: calcSubtotal(rows.value.map((r) => r.subsequentPayment)),
    }),
  )

  const filledCount = computed(() => rows.value.filter((row) =>
    row.creditor.trim()
    || Math.abs(row.openingUnadjusted) >= 0.01
    || Math.abs(row.closingUnadjusted) >= 0.01,
  ).length)
  const abnormalCount = computed(() => rows.value.filter((row) =>
    row.unadjustedAgingMismatch
    || row.auditedAgingMismatch
    || row.subsequentPaymentExceedsBalance,
  ).length)

  // ─── 动态行操作 ───────────────────────────────────────────────────────────

  function addRow(): void {
    if (readonly.value) return
    storedData.value.push(emptyStored(storedData.value.length + 1))
    persistRows()
  }

  function removeRow(rowId: string): void {
    if (readonly.value || storedData.value.length <= 1) return
    const idx = storedData.value.findIndex((r) => r.rowId === rowId)
    if (idx === -1) return
    storedData.value.splice(idx, 1)
    storedData.value.forEach((r, i) => { r.seq = i + 1 })
    persistRows()
  }

  function updateCell(rowId: string, field: string, value: any): void {
    if (readonly.value) return
    const row = storedData.value.find((r) => r.rowId === rowId)
    if (!row) return
    const strFields = [
      'creditor', 'companyCode', 'relatedPartyType', 'paymentNature',
      'isConfirmed', 'remark',
    ]
    if (strFields.includes(field)) (row as any)[field] = String(value ?? '')
    else (row as any)[field] = parseNum(value)
    persistRows()
  }

  function allocateAging(
    rowId: string,
    stage: 'unadjusted' | 'audited',
    bucket: F4AgingBucket,
  ): void {
    if (readonly.value) return
    const row = storedData.value.find((item) => item.rowId === rowId)
    if (!row) return
    const fields = stage === 'unadjusted'
      ? ['unadjustedAgingLt1', 'unadjustedAging1to2', 'unadjustedAging2to3', 'unadjustedAgingGt3'] as const
      : ['auditedAgingLt1', 'auditedAging1to2', 'auditedAging2to3', 'auditedAgingGt3'] as const
    const fieldByBucket: Record<F4AgingBucket, typeof fields[number]> = {
      lt1: fields[0],
      '1to2': fields[1],
      '2to3': fields[2],
      gt3: fields[3],
    }
    for (const field of fields) row[field] = 0
    const computed = computeF4DetailRow(row)
    row[fieldByBucket[bucket]] = stage === 'unadjusted'
      ? computed.closingUnadjusted
      : computed.closingAdjusted
    persistRows()
  }

  // ─── 持久化 ───────────────────────────────────────────────────────────────

  function persistRows(): void {
    allResponses.value.set(STORAGE_KEY, {
      item_id: STORAGE_KEY,
      conclusion: null,
      // 同时存入公式快照，保证导出和F4-1联动无需重复猜测公式。
      remark: JSON.stringify(storedData.value.map(computeF4DetailRow)),
    })
    debounceSave()
  }

  function debounceSave(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 2000)
  }

  function flushSave(): void {
    const item = allResponses.value.get(STORAGE_KEY)
    if (item) window.dispatchEvent(new CustomEvent('f4:save-items', { detail: { items: [item] } }))
  }

  // ─── 样式 ─────────────────────────────────────────────────────────────────

  function rowClassName({ row }: { row: APDetailRow }): string {
    return row.unadjustedAgingMismatch || row.auditedAgingMismatch
      ? 'aging-mismatch-row'
      : row.subsequentPaymentExceedsBalance
        ? 'subsequent-warning-row'
        : ''
  }

  // ─── 清理 ─────────────────────────────────────────────────────────────────

  onBeforeUnmount(() => {
    if (debounceTimer) { clearTimeout(debounceTimer); debounceTimer = null; flushSave() }
  })

  return {
    activeSegment,
    rows,
    filteredRows,
    subtotalRow,
    filledCount,
    abnormalCount,
    searchQuery,
    loadRows,
    addRow,
    removeRow,
    updateCell,
    allocateAging,
    rowClassName,
    basicColumns: F4_DETAIL_BASIC_COLUMNS,
    agingColumns: F4_DETAIL_AGING_COLUMNS,
    auditColumns: F4_DETAIL_AUDIT_COLUMNS,
    allColumns: F4_DETAIL_ALL_COLUMNS,
  }
}

export default useF4Detail
