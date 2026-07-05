/**
 * useF4UnrecordedCheck — F4-7 未入账检查逻辑（反向截止测试）
 *
 * Spec: .kiro/specs/f4-accounts-payable/ Task 5.5
 * 3区域：期后采购/入库/收票，各自独立动态行增删+小计
 * useCutoffAutoSampling集成：序时账±5天提取→按凭证类型分配到3区域
 * "应入当期"="是" 橙色高亮
 * 底部总结：未入账合计/建议调整金额
 * Requirements: 10.1~10.8
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import { parseNum, calcSubtotal } from './useF4AccPayFormulaEngine'
import type { ChecklistResponse } from './useF4FormData'

// ─── 类型定义 ─────────────────────────────────────────────────────────────────

export interface UnrecordedCheckRow {
  rowId: string
  seq: number
  date: string                     // 采购日期/入库日期/收票日期
  counterparty: string             // 供应商/开票方
  amount: number
  documentNo: string               // 采购单号/入库单号/发票号
  description: string              // 商品/服务名称
  shouldRecordCurrent: '' | '是' | '否'  // 是否应入当期
  suggestion: string               // 入账建议
  remark: string
  // 标记
  isHighlight: boolean
}

export type UnrecordedRegion = 'purchase' | 'receipt' | 'invoice'

export interface RegionConfig {
  key: UnrecordedRegion
  label: string
  storageKey: string
  dateLabel: string
  counterpartyLabel: string
  documentLabel: string
  descriptionLabel: string
}

export const REGION_CONFIGS: RegionConfig[] = [
  {
    key: 'purchase',
    label: '期后采购检查',
    storageKey: 'F4-7-purchase',
    dateLabel: '采购日期',
    counterpartyLabel: '供应商',
    documentLabel: '采购单号',
    descriptionLabel: '商品/服务',
  },
  {
    key: 'receipt',
    label: '期后入库检查',
    storageKey: 'F4-7-receipt',
    dateLabel: '入库日期',
    counterpartyLabel: '供应商',
    documentLabel: '入库单号',
    descriptionLabel: '商品名称',
  },
  {
    key: 'invoice',
    label: '期后收票检查',
    storageKey: 'F4-7-invoice',
    dateLabel: '收票日期',
    counterpartyLabel: '开票方',
    documentLabel: '发票号',
    descriptionLabel: '服务期间',
  },
]

export interface F4UnrecordedColumn {
  prop: keyof UnrecordedCheckRow | string
  label: string
  width?: number
  minWidth?: number
  editable?: boolean
}

/** 通用列配置（dateLabel/counterpartyLabel等在Vue层根据region替换） */
export const F4_UNRECORDED_BASE_COLUMNS: F4UnrecordedColumn[] = [
  { prop: 'seq', label: '序号', width: 60 },
  { prop: 'date', label: '日期', minWidth: 110, editable: true },
  { prop: 'counterparty', label: '对方', minWidth: 130, editable: true },
  { prop: 'amount', label: '金额', minWidth: 120, editable: true },
  { prop: 'documentNo', label: '单据号', minWidth: 120, editable: true },
  { prop: 'description', label: '描述', minWidth: 140, editable: true },
  { prop: 'shouldRecordCurrent', label: '应入当期', minWidth: 90, editable: true },
  { prop: 'suggestion', label: '入账建议', minWidth: 140, editable: true },
  { prop: 'remark', label: '备注', minWidth: 120, editable: true },
]

// ─── 内部存储类型 ─────────────────────────────────────────────────────────────

interface StoredUnrecordedRow {
  rowId: string
  seq: number
  date: string
  counterparty: string
  amount: number
  documentNo: string
  description: string
  shouldRecordCurrent: '' | '是' | '否'
  suggestion: string
  remark: string
}

export interface UseF4UnrecordedCheckOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}

export interface RegionSubtotal {
  totalAmount: number
  shouldRecordCount: number
  shouldRecordAmount: number
}

// ─── 工具函数 ─────────────────────────────────────────────────────────────────

const NOTE_KEY = 'F4-7-note'

function generateRowId(): string {
  return `f4uc-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`
}

function emptyStored(seq: number): StoredUnrecordedRow {
  return {
    rowId: generateRowId(),
    seq,
    date: '',
    counterparty: '',
    amount: 0,
    documentNo: '',
    description: '',
    shouldRecordCurrent: '',
    suggestion: '',
    remark: '',
  }
}

function computeRow(stored: StoredUnrecordedRow): UnrecordedCheckRow {
  const isHighlight = stored.shouldRecordCurrent === '是'
  return { ...stored, isHighlight }
}

function safeParseRows(jsonStr: string | null | undefined): StoredUnrecordedRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    if (!Array.isArray(parsed)) return []
    return parsed.map((raw: any, i: number) => ({
      ...emptyStored(i + 1),
      rowId: raw.rowId || raw.id || generateRowId(),
      seq: raw.seq ?? i + 1,
      date: raw.date || '',
      counterparty: raw.counterparty || '',
      amount: parseNum(raw.amount),
      documentNo: raw.documentNo || '',
      description: raw.description || '',
      shouldRecordCurrent: raw.shouldRecordCurrent || '',
      suggestion: raw.suggestion || '',
      remark: raw.remark || '',
    }))
  } catch {
    return []
  }
}

function calcRegionSubtotal(rows: UnrecordedCheckRow[]): RegionSubtotal {
  const totalAmount = calcSubtotal(rows.map((r) => r.amount))
  const shouldRecordRows = rows.filter((r) => r.shouldRecordCurrent === '是')
  return {
    totalAmount,
    shouldRecordCount: shouldRecordRows.length,
    shouldRecordAmount: calcSubtotal(shouldRecordRows.map((r) => r.amount)),
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useF4UnrecordedCheck(options: UseF4UnrecordedCheckOptions) {
  const { allResponses, isReadonly } = options
  const readonly = isReadonly ?? ref(false)

  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  // 3区域各自独立存储
  const purchaseStored = ref<StoredUnrecordedRow[]>([])
  const receiptStored = ref<StoredUnrecordedRow[]>([])
  const invoiceStored = ref<StoredUnrecordedRow[]>([])
  const auditConclusion = ref('')

  function getStoredRef(region: UnrecordedRegion) {
    if (region === 'purchase') return purchaseStored
    if (region === 'receipt') return receiptStored
    return invoiceStored
  }

  function getStorageKey(region: UnrecordedRegion): string {
    return REGION_CONFIGS.find((c) => c.key === region)!.storageKey
  }

  // ─── 加载 ─────────────────────────────────────────────────────────────────

  function loadRegion(region: UnrecordedRegion): void {
    const key = getStorageKey(region)
    const storedRef = getStoredRef(region)
    storedRef.value = safeParseRows(allResponses.value.get(key)?.remark)
    if (storedRef.value.length === 0) storedRef.value = [emptyStored(1)]
  }

  for (const cfg of REGION_CONFIGS) {
    watch(() => allResponses.value.get(cfg.storageKey)?.remark, () => {
      const storedRef = getStoredRef(cfg.key)
      if (storedRef.value.length === 0) loadRegion(cfg.key)
    }, { immediate: true })
  }

  watch(() => allResponses.value.get(NOTE_KEY)?.remark, (v) => {
    auditConclusion.value = v || ''
  }, { immediate: true })

  // ─── 计算行 ───────────────────────────────────────────────────────────────

  const purchaseRows: ComputedRef<UnrecordedCheckRow[]> = computed(() => purchaseStored.value.map(computeRow))
  const receiptRows: ComputedRef<UnrecordedCheckRow[]> = computed(() => receiptStored.value.map(computeRow))
  const invoiceRows: ComputedRef<UnrecordedCheckRow[]> = computed(() => invoiceStored.value.map(computeRow))

  function getRows(region: UnrecordedRegion): ComputedRef<UnrecordedCheckRow[]> {
    if (region === 'purchase') return purchaseRows
    if (region === 'receipt') return receiptRows
    return invoiceRows
  }

  // ─── 各区域小计 ───────────────────────────────────────────────────────────

  const purchaseSubtotal = computed(() => calcRegionSubtotal(purchaseRows.value))
  const receiptSubtotal = computed(() => calcRegionSubtotal(receiptRows.value))
  const invoiceSubtotal = computed(() => calcRegionSubtotal(invoiceRows.value))

  function getSubtotal(region: UnrecordedRegion) {
    if (region === 'purchase') return purchaseSubtotal
    if (region === 'receipt') return receiptSubtotal
    return invoiceSubtotal
  }

  // ─── 底部总结 ─────────────────────────────────────────────────────────────

  const overallSummary = computed(() => {
    const totalUnrecorded =
      purchaseSubtotal.value.shouldRecordAmount +
      receiptSubtotal.value.shouldRecordAmount +
      invoiceSubtotal.value.shouldRecordAmount
    const totalCount =
      purchaseSubtotal.value.shouldRecordCount +
      receiptSubtotal.value.shouldRecordCount +
      invoiceSubtotal.value.shouldRecordCount
    return {
      unrecordedTotal: totalUnrecorded,
      unrecordedCount: totalCount,
      suggestedAdjustment: totalUnrecorded,
    }
  })

  // ─── 动态行操作 ───────────────────────────────────────────────────────────

  function addRow(region: UnrecordedRegion): void {
    if (readonly.value) return
    const storedRef = getStoredRef(region)
    storedRef.value.push(emptyStored(storedRef.value.length + 1))
    persistRegion(region)
  }

  function removeRow(region: UnrecordedRegion, rowId: string): void {
    if (readonly.value) return
    const storedRef = getStoredRef(region)
    if (storedRef.value.length <= 1) return
    const idx = storedRef.value.findIndex((r) => r.rowId === rowId)
    if (idx === -1) return
    storedRef.value.splice(idx, 1)
    storedRef.value.forEach((r, i) => { r.seq = i + 1 })
    persistRegion(region)
  }

  function updateCell(region: UnrecordedRegion, rowId: string, field: string, value: any): void {
    if (readonly.value) return
    const storedRef = getStoredRef(region)
    const row = storedRef.value.find((r) => r.rowId === rowId)
    if (!row) return
    const strFields = ['date', 'counterparty', 'documentNo', 'description', 'shouldRecordCurrent', 'suggestion', 'remark']
    if (strFields.includes(field)) (row as any)[field] = String(value ?? '')
    else (row as any)[field] = parseNum(value)
    persistRegion(region)
  }

  // ─── useCutoffAutoSampling 集成 ──────────────────────────────────────────

  /**
   * 接收截止自动提取的结果，按凭证类型分配到3区域
   * voucherType映射：
   * - '付'/'转'(含采购摘要) → purchase区域
   * - '收'(入库相关) → receipt区域
   * - 其他(发票相关) → invoice区域
   */
  function distributeCutoffSamples(
    vouchers: Array<{
      voucherNo: string
      voucherDate: string
      summary: string | null
      debitAmount: string | null
      creditAmount: string | null
      voucherType: string | null
    }>,
  ): void {
    if (readonly.value || !vouchers.length) return

    const purchaseNew: StoredUnrecordedRow[] = []
    const receiptNew: StoredUnrecordedRow[] = []
    const invoiceNew: StoredUnrecordedRow[] = []

    for (const v of vouchers) {
      const amount = parseNum(v.creditAmount) || parseNum(v.debitAmount)
      const base: StoredUnrecordedRow = {
        rowId: generateRowId(),
        seq: 0,
        date: v.voucherDate || '',
        counterparty: '',
        amount,
        documentNo: v.voucherNo || '',
        description: v.summary || '',
        shouldRecordCurrent: '',
        suggestion: '',
        remark: `截止自动提取`,
      }

      const type = (v.voucherType || '').trim()
      const summary = (v.summary || '').toLowerCase()

      if (type === '付' || type === '转' || summary.includes('采购') || summary.includes('购')) {
        purchaseNew.push(base)
      } else if (type === '收' || summary.includes('入库') || summary.includes('验收')) {
        receiptNew.push(base)
      } else {
        invoiceNew.push(base)
      }
    }

    // 追加到各区域（清除仅一个空行的初始状态）
    if (purchaseNew.length) {
      if (purchaseStored.value.length === 1 && !purchaseStored.value[0].counterparty && purchaseStored.value[0].amount === 0) {
        purchaseStored.value = []
      }
      purchaseStored.value.push(...purchaseNew)
      purchaseStored.value.forEach((r, i) => { r.seq = i + 1 })
      persistRegion('purchase')
    }
    if (receiptNew.length) {
      if (receiptStored.value.length === 1 && !receiptStored.value[0].counterparty && receiptStored.value[0].amount === 0) {
        receiptStored.value = []
      }
      receiptStored.value.push(...receiptNew)
      receiptStored.value.forEach((r, i) => { r.seq = i + 1 })
      persistRegion('receipt')
    }
    if (invoiceNew.length) {
      if (invoiceStored.value.length === 1 && !invoiceStored.value[0].counterparty && invoiceStored.value[0].amount === 0) {
        invoiceStored.value = []
      }
      invoiceStored.value.push(...invoiceNew)
      invoiceStored.value.forEach((r, i) => { r.seq = i + 1 })
      persistRegion('invoice')
    }
  }

  // ─── 持久化 ───────────────────────────────────────────────────────────────

  function persistRegion(region: UnrecordedRegion): void {
    const key = getStorageKey(region)
    const storedRef = getStoredRef(region)
    allResponses.value.set(key, {
      item_id: key,
      conclusion: null,
      remark: JSON.stringify(storedRef.value),
    })
    debounceSave()
  }

  function debounceSave(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 2000)
  }

  function flushSave(): void {
    const items: ChecklistResponse[] = []
    for (const cfg of REGION_CONFIGS) {
      const item = allResponses.value.get(cfg.storageKey)
      if (item) items.push(item)
    }
    const noteItem = allResponses.value.get(NOTE_KEY)
    if (noteItem) items.push(noteItem)
    if (items.length) window.dispatchEvent(new CustomEvent('f4:save-items', { detail: { items } }))
  }

  watch(auditConclusion, (val) => {
    allResponses.value.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: val })
    debounceSave()
  })

  // ─── 样式 ─────────────────────────────────────────────────────────────────

  function rowClassName({ row }: { row: UnrecordedCheckRow }): string {
    return row.isHighlight ? 'should-record-highlight' : ''
  }

  // ─── 清理 ─────────────────────────────────────────────────────────────────

  onBeforeUnmount(() => {
    if (debounceTimer) { clearTimeout(debounceTimer); debounceTimer = null; flushSave() }
  })

  return {
    // 各区域行
    purchaseRows,
    receiptRows,
    invoiceRows,
    getRows,
    // 各区域小计
    purchaseSubtotal,
    receiptSubtotal,
    invoiceSubtotal,
    getSubtotal,
    // 总结
    overallSummary,
    auditConclusion,
    // 操作
    addRow,
    removeRow,
    updateCell,
    distributeCutoffSamples,
    rowClassName,
    // 配置
    regionConfigs: REGION_CONFIGS,
    baseColumns: F4_UNRECORDED_BASE_COLUMNS,
  }
}

export default useF4UnrecordedCheck
