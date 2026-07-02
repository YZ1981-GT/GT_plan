/**
 * useD4WalkthroughTest — D4-14 营业收入发生检查表（穿行测试）composable
 *
 * 多维穿行测试矩阵：每笔交易 × 7个证据链维度
 * 支持维度级OCR、自动一致性校验、D4-12联动、序时账导入、AI穿行分析
 *
 * Spec: .kiro/specs/d4-14-walkthrough-test/
 */
import { ref, computed, watch, onBeforeUnmount, type Ref } from 'vue'
import { parseNum } from './useD4FormulaEngine'

// ═══════════════════════════════════════════════════════════════════════════════
// 1.1.1 — Types
// ═══════════════════════════════════════════════════════════════════════════════

export interface VoucherDimension {
  month: string
  date: string
  number: string
  productName: string
  quantity: string
  amount: number
  accountingDate: string
  attachmentId?: string
  attachmentName?: string
  ocrStatus?: 'none' | 'processing' | 'done' | 'failed'
}

export interface ContractDimension {
  number: string
  productName: string
  amount: number
  approver: string
  confirmor: string
  refD4ContractId?: string
  attachmentId?: string
  attachmentName?: string
  ocrStatus?: 'none' | 'processing' | 'done' | 'failed'
}

export interface DeliveryDimension {
  date: string
  productName: string
  amount: number
  warehouseKeeper: string
  attachmentId?: string
  attachmentName?: string
  ocrStatus?: 'none' | 'processing' | 'done' | 'failed'
}

export interface ShippingDimension {
  date: string
  productName: string
  amount: number
  attachmentId?: string
  attachmentName?: string
  ocrStatus?: 'none' | 'processing' | 'done' | 'failed'
}

export interface ReceiptDimension {
  date: string
  productName: string
  amount: number
  attachmentId?: string
  attachmentName?: string
  ocrStatus?: 'none' | 'processing' | 'done' | 'failed'
}

export interface InvoiceDimension {
  date: string
  number: string
  amount: number
  attachmentId?: string
  attachmentName?: string
  ocrStatus?: 'none' | 'processing' | 'done' | 'failed'
}

export interface OtherDimension {
  description: string
  indexNo: string
  attachmentId?: string
  attachmentName?: string
  ocrStatus?: 'none' | 'processing' | 'done' | 'failed'
}

export interface FieldMatchStatus {
  isConsistent: boolean
  values: { dimension: string; value: string | number }[]
  mismatchDimensions: string[]
}

export interface ConsistencyResult {
  amountMatch: FieldMatchStatus
  productNameMatch: FieldMatchStatus
  dateMatch: FieldMatchStatus
  score: number
}

export interface TransactionItem {
  id: string
  indexNo: string
  label: string
  voucher: VoucherDimension
  contract: ContractDimension
  delivery: DeliveryDimension
  shipping: ShippingDimension
  receipt: ReceiptDimension
  invoice: InvoiceDimension
  other: OtherDimension
  consistencyScore: number
  consistencyDetails: ConsistencyResult | null
  conclusion: '无异常' | '存在差异已解释' | '存在重大异常' | ''
  isAnomalous: boolean
  aiAnalysis?: string
}

export interface SamplingParams {
  testPopulation: string
  specificItems: string
  samplingPopulation: string
  samplingMethod: string
  targetSampleSize: number
}

export interface UseD4WalkthroughTestOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  isReadonly: Ref<boolean>
}

// ═══════════════════════════════════════════════════════════════════════════════
// 1.1.2 — DIMENSION_GROUPS 常量
// ═══════════════════════════════════════════════════════════════════════════════

export const DIMENSION_GROUPS = [
  {
    key: 'voucher',
    label: '记账凭证',
    fields: [
      { key: 'month', label: '月份', type: 'text' },
      { key: 'date', label: '日期', type: 'date' },
      { key: 'number', label: '编号', type: 'text' },
      { key: 'productName', label: '品名', type: 'text' },
      { key: 'quantity', label: '数量', type: 'text' },
      { key: 'amount', label: '金额', type: 'number' },
      { key: 'accountingDate', label: '记账日期', type: 'date' },
    ],
  },
  {
    key: 'contract',
    label: '销售合同',
    fields: [
      { key: 'number', label: '编号', type: 'text' },
      { key: 'productName', label: '品名', type: 'text' },
      { key: 'amount', label: '金额', type: 'number' },
      { key: 'approver', label: '签发审批', type: 'text' },
      { key: 'confirmor', label: '签收确认', type: 'text' },
    ],
  },
  {
    key: 'delivery',
    label: '出库单',
    fields: [
      { key: 'date', label: '日期', type: 'date' },
      { key: 'productName', label: '品名', type: 'text' },
      { key: 'amount', label: '金额', type: 'number' },
      { key: 'warehouseKeeper', label: '仓库保管员', type: 'text' },
    ],
  },

  {
    key: 'shipping',
    label: '运输单',
    fields: [
      { key: 'date', label: '日期', type: 'date' },
      { key: 'productName', label: '品名', type: 'text' },
      { key: 'amount', label: '金额', type: 'number' },
    ],
  },
  {
    key: 'receipt',
    label: '签收单',
    fields: [
      { key: 'date', label: '日期', type: 'date' },
      { key: 'productName', label: '品名', type: 'text' },
      { key: 'amount', label: '金额', type: 'number' },
    ],
  },
  {
    key: 'invoice',
    label: '发票',
    fields: [
      { key: 'date', label: '日期', type: 'date' },
      { key: 'number', label: '编号', type: 'text' },
      { key: 'amount', label: '金额', type: 'number' },
    ],
  },
  {
    key: 'other',
    label: '其他支持性文件',
    fields: [
      { key: 'description', label: '文件描述', type: 'textarea' },
      { key: 'indexNo', label: '索引号', type: 'text' },
    ],
  },
] as const


// ═══════════════════════════════════════════════════════════════════════════════
// 1.1.5 — 一致性引擎纯函数
// ═══════════════════════════════════════════════════════════════════════════════

/** 维度 key 与金额字段的映射（other 无 amount） */
const AMOUNT_DIMENSIONS: { key: keyof TransactionItem; label: string }[] = [
  { key: 'voucher', label: '记账凭证' },
  { key: 'contract', label: '销售合同' },
  { key: 'delivery', label: '出库单' },
  { key: 'shipping', label: '运输单' },
  { key: 'receipt', label: '签收单' },
  { key: 'invoice', label: '发票' },
]

/** 维度 key 与品名字段的映射 */
const PRODUCT_NAME_DIMENSIONS: { key: keyof TransactionItem; label: string }[] = [
  { key: 'voucher', label: '记账凭证' },
  { key: 'contract', label: '销售合同' },
  { key: 'delivery', label: '出库单' },
  { key: 'shipping', label: '运输单' },
  { key: 'receipt', label: '签收单' },
]

/** 维度 key 与日期字段的映射 */
const DATE_DIMENSIONS: { key: keyof TransactionItem; dimDateField: string; label: string }[] = [
  { key: 'voucher', dimDateField: 'date', label: '记账凭证' },
  { key: 'delivery', dimDateField: 'date', label: '出库单' },
  { key: 'shipping', dimDateField: 'date', label: '运输单' },
  { key: 'receipt', dimDateField: 'date', label: '签收单' },
  { key: 'invoice', dimDateField: 'date', label: '发票' },
]

/**
 * 比较各维度的金额字段。只比较已填充（amount > 0）的维度。
 * 需要 2+ 个维度有金额才进行比对。
 */
export function compareAmounts(item: TransactionItem): FieldMatchStatus {
  const values: { dimension: string; value: number }[] = []
  for (const dim of AMOUNT_DIMENSIONS) {
    const amount = (item[dim.key] as any).amount as number
    if (amount && amount !== 0) {
      values.push({ dimension: dim.label, value: amount })
    }
  }
  if (values.length < 2) {
    return { isConsistent: true, values, mismatchDimensions: [] }
  }
  const baseValue = values[0].value
  const mismatchDimensions: string[] = []
  for (const v of values) {
    if (v.value !== baseValue) {
      mismatchDimensions.push(v.dimension)
    }
  }

  // 如果有不一致的维度，把第一个维度也加入（因为不确定谁是"正确的"）
  if (mismatchDimensions.length > 0 && !mismatchDimensions.includes(values[0].dimension)) {
    // 检查是否所有非第一个值都相同但与第一个不同
    const otherValues = values.slice(1)
    const allOthersSame = otherValues.every(v => v.value === otherValues[0].value)
    if (allOthersSame && otherValues[0].value !== baseValue) {
      mismatchDimensions.unshift(values[0].dimension)
    }
  }
  return {
    isConsistent: mismatchDimensions.length === 0,
    values: values as { dimension: string; value: string | number }[],
    mismatchDimensions,
  }
}

/**
 * 比较各维度的品名字段。只比较已填充（非空字符串）的维度。
 */
export function compareProductNames(item: TransactionItem): FieldMatchStatus {
  const values: { dimension: string; value: string }[] = []
  for (const dim of PRODUCT_NAME_DIMENSIONS) {
    const productName = (item[dim.key] as any).productName as string
    if (productName && productName.trim() !== '') {
      values.push({ dimension: dim.label, value: productName.trim() })
    }
  }
  if (values.length < 2) {
    return { isConsistent: true, values, mismatchDimensions: [] }
  }
  const baseValue = values[0].value
  const mismatchDimensions: string[] = []
  for (const v of values) {
    if (v.value !== baseValue) {
      mismatchDimensions.push(v.dimension)
    }
  }
  if (mismatchDimensions.length > 0 && !mismatchDimensions.includes(values[0].dimension)) {
    const otherValues = values.slice(1)
    const allOthersSame = otherValues.every(v => v.value === otherValues[0].value)
    if (allOthersSame && otherValues[0].value !== baseValue) {
      mismatchDimensions.unshift(values[0].dimension)
    }
  }
  return {
    isConsistent: mismatchDimensions.length === 0,
    values: values as { dimension: string; value: string | number }[],
    mismatchDimensions,
  }
}


/**
 * 比较各维度的日期字段。只比较已填充（非空字符串）的维度。
 */
export function compareDates(item: TransactionItem): FieldMatchStatus {
  const values: { dimension: string; value: string }[] = []
  for (const dim of DATE_DIMENSIONS) {
    const dateVal = (item[dim.key] as any)[dim.dimDateField] as string
    if (dateVal && dateVal.trim() !== '') {
      values.push({ dimension: dim.label, value: dateVal.trim() })
    }
  }
  if (values.length < 2) {
    return { isConsistent: true, values, mismatchDimensions: [] }
  }
  const baseValue = values[0].value
  const mismatchDimensions: string[] = []
  for (const v of values) {
    if (v.value !== baseValue) {
      mismatchDimensions.push(v.dimension)
    }
  }
  if (mismatchDimensions.length > 0 && !mismatchDimensions.includes(values[0].dimension)) {
    const otherValues = values.slice(1)
    const allOthersSame = otherValues.every(v => v.value === otherValues[0].value)
    if (allOthersSame && otherValues[0].value !== baseValue) {
      mismatchDimensions.unshift(values[0].dimension)
    }
  }
  return {
    isConsistent: mismatchDimensions.length === 0,
    values: values as { dimension: string; value: string | number }[],
    mismatchDimensions,
  }
}

/**
 * 综合计算一致性结果。分数 = (匹配的字段类型数 / 可比较的字段类型总数) * 100
 * 字段类型共3种：amount, productName, date
 */
export function computeConsistency(item: TransactionItem): ConsistencyResult {
  const amountMatch = compareAmounts(item)
  const productNameMatch = compareProductNames(item)
  const dateMatch = compareDates(item)

  let comparableCount = 0
  let matchingCount = 0

  // 只有有2+维度有值的字段类型才参与评分
  if (amountMatch.values.length >= 2) {
    comparableCount++
    if (amountMatch.isConsistent) matchingCount++
  }
  if (productNameMatch.values.length >= 2) {
    comparableCount++
    if (productNameMatch.isConsistent) matchingCount++
  }
  if (dateMatch.values.length >= 2) {
    comparableCount++
    if (dateMatch.isConsistent) matchingCount++
  }

  const score = comparableCount === 0 ? 0 : Math.round((matchingCount / comparableCount) * 100)

  return { amountMatch, productNameMatch, dateMatch, score }
}


// ═══════════════════════════════════════════════════════════════════════════════
// 1.1.6 — isDimensionComplete 纯函数
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * 判断维度是否已填完所有必填字段（排除附件字段）。
 * 字符串类型字段：非空
 * 数字类型字段：非零
 */
export function isDimensionComplete(dimension: any, dimensionKey: string): boolean {
  const group = DIMENSION_GROUPS.find(g => g.key === dimensionKey)
  if (!group) return false

  for (const field of group.fields) {
    const val = dimension[field.key]
    if (field.type === 'number') {
      if (!val || val === 0) return false
    } else {
      if (!val || (typeof val === 'string' && val.trim() === '')) return false
    }
  }
  return true
}

// ═══════════════════════════════════════════════════════════════════════════════
// 1.1.10 — mapD4ContractToDimension（D4-12 合同 → 销售合同维度映射）
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * 从 D4-12 ContractInspectionItem 映射到销售合同维度字段。
 * 只填充 number, productName, amount，不影响其他字段。
 */
export function mapD4ContractToDimension(contract: {
  id?: string
  contractNo?: string
  serviceContent?: string
  contractAmount?: number
}): Partial<ContractDimension> {
  return {
    number: contract.contractNo || '',
    productName: contract.serviceContent || '',
    amount: parseNum(contract.contractAmount),
    refD4ContractId: contract.id || '',
  }
}


// ═══════════════════════════════════════════════════════════════════════════════
// 1.1.11 — mapLedgerToTransaction（序时账条目 → TransactionItem 映射）
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * 从序时账条目创建 TransactionItem，预填充记账凭证维度。
 * 其他维度保持默认空值。
 */
export function mapLedgerToTransaction(entry: {
  date?: string
  voucherNo?: string
  summary?: string
  amount?: number
}): TransactionItem {
  return {
    id: `t-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`,
    indexNo: '',  // 由 reindexItems 统一编号
    label: entry.summary || '',
    voucher: {
      month: '',
      date: entry.date || '',
      number: entry.voucherNo || '',
      productName: '',
      quantity: '',
      amount: parseNum(entry.amount),
      accountingDate: '',
    },
    contract: { number: '', productName: '', amount: 0, approver: '', confirmor: '' },
    delivery: { date: '', productName: '', amount: 0, warehouseKeeper: '' },
    shipping: { date: '', productName: '', amount: 0 },
    receipt: { date: '', productName: '', amount: 0 },
    invoice: { date: '', number: '', amount: 0 },
    other: { description: '', indexNo: '' },
    consistencyScore: 0,
    consistencyDetails: null,
    conclusion: '',
    isAnomalous: false,
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// 1.1.12 — mapOcrToDimension（OCR extracted_fields → 指定维度字段映射）
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * 将 OCR 提取的字段映射到指定维度，只填属于该维度的字段。
 * 不属于目标维度的字段被忽略。
 */
export function mapOcrToDimension(
  extractedFields: Record<string, any>,
  dimensionKey: string,
): Record<string, any> {
  const group = DIMENSION_GROUPS.find(g => g.key === dimensionKey)
  if (!group) return {}

  const validKeys = new Set(group.fields.map(f => f.key))
  const result: Record<string, any> = {}

  for (const [key, val] of Object.entries(extractedFields)) {
    if (validKeys.has(key) && val != null && val !== '') {
      result[key] = val
    }
  }
  return result
}


// ═══════════════════════════════════════════════════════════════════════════════
// 1.1.13 — collectAiContext（收集所有已填维度数据用于 AI 分析）
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * 收集 TransactionItem 中所有已填充维度的数据用于 AI 分析。
 * 一个维度被视为"已填充"当至少有一个非附件字段有值。
 */
export function collectAiContext(item: TransactionItem): Record<string, any> {
  const context: Record<string, any> = {
    indexNo: item.indexNo,
    label: item.label,
    dimensions: {} as Record<string, any>,
  }

  for (const group of DIMENSION_GROUPS) {
    const dim = item[group.key as keyof TransactionItem] as any
    if (!dim) continue

    // 检查维度是否有任何已填充的非附件字段
    let hasData = false
    const dimData: Record<string, any> = {}

    for (const field of group.fields) {
      const val = dim[field.key]
      if (field.type === 'number') {
        if (val && val !== 0) {
          hasData = true
          dimData[field.key] = val
        }
      } else {
        if (val && typeof val === 'string' && val.trim() !== '') {
          hasData = true
          dimData[field.key] = val
        }
      }
    }

    if (hasData) {
      context.dimensions[group.key] = {
        label: group.label,
        ...dimData,
      }
    }
  }

  // 附加一致性结果（如果有）
  if (item.consistencyDetails) {
    context.consistency = {
      score: item.consistencyScore,
      amountConsistent: item.consistencyDetails.amountMatch.isConsistent,
      productNameConsistent: item.consistencyDetails.productNameMatch.isConsistent,
      dateConsistent: item.consistencyDetails.dateMatch.isConsistent,
    }
  }

  if (item.conclusion) {
    context.conclusion = item.conclusion
  }

  return context
}


// ═══════════════════════════════════════════════════════════════════════════════
// Composable 主体
// ═══════════════════════════════════════════════════════════════════════════════

export function useD4WalkthroughTest(options: UseD4WalkthroughTestOptions) {
  const { wpId, projectId, allResponses, isReadonly } = options

  const transactions = ref<TransactionItem[]>([])
  const samplingParams = ref<SamplingParams>({
    testPopulation: '',
    specificItems: '',
    samplingPopulation: '',
    samplingMethod: '',
    targetSampleSize: 0,
  })
  const auditNote = ref('')
  const auditConclusion = ref('')

  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  // ─── 1.1.3 Load ────────────────────────────────────────────────────────

  function loadTransactions() {
    const resp = allResponses.value.get('D4-14-transactions')
    if (resp?.remark) {
      try {
        const parsed = JSON.parse(resp.remark)
        if (Array.isArray(parsed) && parsed.length) {
          transactions.value = parsed
          return
        }
      } catch { /* ignore parse errors, fallback to empty */ }
    }
    transactions.value = []
  }

  function loadSampling() {
    const resp = allResponses.value.get('D4-14-sampling')
    if (resp?.remark) {
      try {
        const parsed = JSON.parse(resp.remark)
        if (parsed && typeof parsed === 'object') {
          samplingParams.value = { ...samplingParams.value, ...parsed }
          return
        }
      } catch { /* ignore */ }
    }
  }

  // ─── 1.1.9 Audit Note / Conclusion ─────────────────────────────────────

  function loadNoteConclusion() {
    auditNote.value = allResponses.value.get('D4-14-note')?.remark || ''
    auditConclusion.value = allResponses.value.get('D4-14-conclusion')?.remark || ''
  }


  watch(() => allResponses.value.get('D4-14-transactions')?.remark, () => loadTransactions(), { immediate: true })
  watch(() => allResponses.value.get('D4-14-sampling')?.remark, () => loadSampling(), { immediate: true })
  watch(() => allResponses.value.get('D4-14-note')?.remark, () => loadNoteConclusion(), { immediate: true })

  // ─── 1.1.4 reindexItems ────────────────────────────────────────────────

  function reindexItems() {
    transactions.value.forEach((item, i) => {
      item.indexNo = `D4-14-${i + 1}`
    })
  }

  // ─── 1.1.3 CRUD ────────────────────────────────────────────────────────

  function addTransaction(label: string): TransactionItem {
    const item: TransactionItem = {
      id: `t-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`,
      indexNo: '',
      label,
      voucher: { month: '', date: '', number: '', productName: '', quantity: '', amount: 0, accountingDate: '' },
      contract: { number: '', productName: '', amount: 0, approver: '', confirmor: '' },
      delivery: { date: '', productName: '', amount: 0, warehouseKeeper: '' },
      shipping: { date: '', productName: '', amount: 0 },
      receipt: { date: '', productName: '', amount: 0 },
      invoice: { date: '', number: '', amount: 0 },
      other: { description: '', indexNo: '' },
      consistencyScore: 0,
      consistencyDetails: null,
      conclusion: '',
      isAnomalous: false,
    }
    transactions.value.push(item)
    reindexItems()
    persistAll()
    return item
  }

  function removeTransaction(id: string) {
    if (isReadonly.value) return
    transactions.value = transactions.value.filter(t => t.id !== id)
    reindexItems()
    persistAll()
  }

  function updateDimension(id: string, dimKey: string, field: string, value: any) {
    if (isReadonly.value) return
    const item = transactions.value.find(t => t.id === id)
    if (!item) return
    const dim = item[dimKey as keyof TransactionItem] as any
    if (!dim) return
    dim[field] = value

    // 重新计算一致性
    const result = computeConsistency(item)
    item.consistencyScore = result.score
    item.consistencyDetails = result

    persistAll()
  }


  // ─── 1.1.9 Audit note/conclusion update ────────────────────────────────

  function updateAuditNote(val: string) {
    if (isReadonly.value) return
    auditNote.value = val
    persistMeta()
  }

  function updateAuditConclusion(val: string) {
    if (isReadonly.value) return
    auditConclusion.value = val
    persistMeta()
  }

  function updateSamplingParams(params: Partial<SamplingParams>) {
    if (isReadonly.value) return
    Object.assign(samplingParams.value, params)
    persistAll()
  }

  // ─── 1.1.7 Computed stats ──────────────────────────────────────────────

  const totalVoucherAmount = computed(() =>
    transactions.value.reduce((sum, t) => sum + parseNum(t.voucher.amount), 0),
  )

  const coverageRate = computed(() => {
    const revenueResp = allResponses.value.get('D4-adj-revenue-total')
    const periodRevenue = parseNum(revenueResp?.remark)
    if (periodRevenue <= 0) return 0
    return Math.min((totalVoucherAmount.value / periodRevenue) * 100, 100)
  })

  const anomalyRate = computed(() => {
    const total = transactions.value.length
    if (total === 0) return 0
    const anomalous = transactions.value.filter(t => t.isAnomalous).length
    return (anomalous / total) * 100
  })

  const samplingProgress = computed(() => {
    const target = samplingParams.value.targetSampleSize
    if (!target || target <= 0) return 0
    return Math.min((transactions.value.length / target) * 100, 100)
  })


  // ─── 1.1.8 Persistence (debounce 2s) ───────────────────────────────────

  function persistAll() {
    allResponses.value.set('D4-14-transactions', {
      item_id: 'D4-14-transactions',
      conclusion: null,
      remark: JSON.stringify(transactions.value),
    })
    allResponses.value.set('D4-14-sampling', {
      item_id: 'D4-14-sampling',
      conclusion: null,
      remark: JSON.stringify(samplingParams.value),
    })
    persistMeta()
  }

  function persistMeta() {
    allResponses.value.set('D4-14-note', {
      item_id: 'D4-14-note',
      conclusion: null,
      remark: auditNote.value,
    })
    allResponses.value.set('D4-14-conclusion', {
      item_id: 'D4-14-conclusion',
      conclusion: null,
      remark: auditConclusion.value,
    })
    debounceSave()
  }

  function debounceSave() {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 2000)
  }

  function flushSave() {
    const keys = ['D4-14-transactions', 'D4-14-sampling', 'D4-14-note', 'D4-14-conclusion']
    const items = keys.map(k => allResponses.value.get(k)).filter(Boolean)
    window.dispatchEvent(new CustomEvent('d4:save-items', { detail: { items } }))
  }

  onBeforeUnmount(() => {
    if (debounceTimer) { clearTimeout(debounceTimer); flushSave() }
  })

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    transactions,
    samplingParams,
    auditNote,
    auditConclusion,
    totalVoucherAmount,
    coverageRate,
    anomalyRate,
    samplingProgress,
    addTransaction,
    removeTransaction,
    updateDimension,
    updateAuditNote,
    updateAuditConclusion,
    updateSamplingParams,
    reindexItems,
    loadTransactions,
  }
}

export default useD4WalkthroughTest
