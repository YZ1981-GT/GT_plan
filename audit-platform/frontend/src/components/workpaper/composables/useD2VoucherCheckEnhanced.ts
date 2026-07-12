/**
 * useD2VoucherCheckEnhanced — D2-7 凭证检查表增强 composable
 *
 * Spec: .kiro/specs/d2-7-voucher-check-enhancement/
 * Task: 1.1
 *
 * 职责：
 * - 双区数据管理（currentRows / postRows 独立 ref 数组）
 * - activeZone / viewMode 切换逻辑
 * - classifyVoucherToZone 纯函数（日期分区）
 * - 行级 CRUD（addRow / removeRow / updateRow）
 * - 持久化（loadFromResponses / saveToResponses）
 * - SampledVoucher → VoucherCheckRow 字段映射
 * - 合并模式填充（mergeVoucherRows）
 *
 * Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 10.1, 10.2, 10.3
 */
import { ref, computed, watch, onBeforeUnmount, inject, type Ref, type ComputedRef } from 'vue'
import { D2_SAVE_ITEMS_KEY } from './d2InjectionKeys'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface VoucherCheckRow {
  rowId: string
  seq: number
  customerName: string        // 客户名称
  voucherDate: string         // 日期
  voucherNo: string           // 凭证编号
  businessContent: string     // 业务内容
  counterpartAccount: string  // 对方科目
  counterpartDetail: string   // 对方明细科目
  debitAmount: number         // 借方金额
  creditAmount: number        // 贷方金额
  supportingDoc: string       // 支持性文件（附件引用）
  check1: string              // 核对内容1：金额一致性
  check2: string              // 核对内容2：日期一致性
  check3: string              // 核对内容3：对方科目匹配
  check4: string              // 核对内容4：业务内容相符
  check5: string              // 核对内容5：附件完整性
  indexRef: string            // 索引号
  isAbnormal: string          // 是否异常
  remark: string              // 备注说明
  // 元数据
  attachments: AttachmentMeta[]
  ocrResult?: OcrExtractedData
  source?: string             // 来源标记：手动/自动抽凭
}

export interface AttachmentMeta {
  fileId: string
  fileName: string
  uploadTime: string
  thumbnailUrl?: string
  ocrStatus: 'pending' | 'success' | 'failed'
}

export interface OcrExtractedData {
  amount?: number
  date?: string
  counterparty?: string
  contractNo?: string
  rawText?: string
}

export interface DualZoneState {
  currentRows: Ref<VoucherCheckRow[]>
  postRows: Ref<VoucherCheckRow[]>
  activeZone: Ref<'current' | 'post'>
  viewMode: Ref<'matrix' | 'card'>
}

export interface UseD2VoucherCheckEnhancedOptions {
  allResponses: Ref<Map<string, any>>
  isReadonly: Ref<boolean>
  bsDate: Ref<string>
}

/** 抽凭引擎返回的采样凭证结构 */
export interface SampledVoucher {
  voucherNo: string
  voucherDate: string
  debitAmount?: number
  creditAmount?: number
  summary?: string
  counterpartAccount?: string
  accountCode?: string
  customerName?: string
}

// ─── Constants ───────────────────────────────────────────────────────────────

const CURRENT_ROWS_KEY = 'D2-vc-current-rows'
const POST_ROWS_KEY = 'D2-vc-post-rows'

// ─── Pure Functions (exported for PBT) ───────────────────────────────────────

/**
 * 分类凭证到对应区块
 * voucherDate <= bsDate → 'current'（区1本期增减变动）
 * voucherDate > bsDate → 'post'（区2期后收款调整）
 * 空值默认 'current'
 */
export function classifyVoucherToZone(voucherDate: string, bsDate: string): 'current' | 'post' {
  if (!voucherDate || !bsDate) return 'current'
  return voucherDate <= bsDate ? 'current' : 'post'
}

/**
 * SampledVoucher → VoucherCheckRow 字段映射
 */
export function mapSampledVoucher(voucher: SampledVoucher, seq: number): VoucherCheckRow {
  return {
    rowId: generateRowId(),
    seq,
    customerName: voucher.customerName || '',
    voucherDate: voucher.voucherDate || '',
    voucherNo: voucher.voucherNo || '',
    businessContent: voucher.summary || '',
    counterpartAccount: voucher.counterpartAccount || '',
    counterpartDetail: voucher.accountCode || '',
    debitAmount: voucher.debitAmount ?? 0,
    creditAmount: voucher.creditAmount ?? 0,
    supportingDoc: '',
    check1: '',
    check2: '',
    check3: '',
    check4: '',
    check5: '',
    indexRef: '',
    isAbnormal: '',
    remark: '',
    attachments: [],
    source: '自动抽凭',
  }
}

/**
 * 合并模式填充：按凭证编号去重，已有行保留 check1~check5
 *
 * 规则：
 * 1. 已存在的凭证（按 voucherNo 匹配）→ 保留原行的 check1~check5 不覆盖
 * 2. 新凭证 → 追加到末尾
 * 3. 总行数 = |existing| + |incoming 中 voucherNo 不在 existing 中的|
 */
export function mergeVoucherRows(
  existingRows: VoucherCheckRow[],
  incomingRows: VoucherCheckRow[]
): VoucherCheckRow[] {
  const existingNos = new Set(existingRows.map(r => r.voucherNo).filter(Boolean))
  const result = [...existingRows]

  for (const incoming of incomingRows) {
    if (!incoming.voucherNo || !existingNos.has(incoming.voucherNo)) {
      // 新凭证，追加
      result.push({
        ...incoming,
        seq: result.length + 1,
      })
      if (incoming.voucherNo) {
        existingNos.add(incoming.voucherNo)
      }
    }
    // 已存在的凭证 → 保留原有 check1~check5，不覆盖
  }

  // 重新编号 seq
  result.forEach((r, i) => { r.seq = i + 1 })
  return result
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function generateRowId(): string {
  return `vcr-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`
}

function createEmptyRow(seq: number): VoucherCheckRow {
  return {
    rowId: generateRowId(),
    seq,
    customerName: '',
    voucherDate: '',
    voucherNo: '',
    businessContent: '',
    counterpartAccount: '',
    counterpartDetail: '',
    debitAmount: 0,
    creditAmount: 0,
    supportingDoc: '',
    check1: '',
    check2: '',
    check3: '',
    check4: '',
    check5: '',
    indexRef: '',
    isAbnormal: '',
    remark: '',
    attachments: [],
    source: '手动',
  }
}

function parseRows(jsonStr: string | null | undefined): VoucherCheckRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    if (!Array.isArray(parsed)) return []
    return parsed.map((raw: any, idx: number) => ({
      rowId: raw.rowId || generateRowId(),
      seq: raw.seq ?? (idx + 1),
      customerName: raw.customerName || '',
      voucherDate: raw.voucherDate || '',
      voucherNo: raw.voucherNo || '',
      businessContent: raw.businessContent || '',
      counterpartAccount: raw.counterpartAccount || '',
      counterpartDetail: raw.counterpartDetail || '',
      debitAmount: Number(raw.debitAmount) || 0,
      creditAmount: Number(raw.creditAmount) || 0,
      supportingDoc: raw.supportingDoc || '',
      check1: raw.check1 || '',
      check2: raw.check2 || '',
      check3: raw.check3 || '',
      check4: raw.check4 || '',
      check5: raw.check5 || '',
      indexRef: raw.indexRef || '',
      isAbnormal: raw.isAbnormal || '',
      remark: raw.remark || '',
      attachments: Array.isArray(raw.attachments) ? raw.attachments : [],
      ocrResult: raw.ocrResult || undefined,
      source: raw.source || '',
    }))
  } catch {
    return []
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD2VoucherCheckEnhanced(options: UseD2VoucherCheckEnhancedOptions) {
  const { allResponses, isReadonly, bsDate } = options

  // ─── State ─────────────────────────────────────────────────────────────

  const currentRows = ref<VoucherCheckRow[]>([])
  const postRows = ref<VoucherCheckRow[]>([])
  const activeZone = ref<'current' | 'post'>('current')
  const viewMode = ref<'matrix' | 'card'>('matrix')

  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  // Inject save function from parent (provide/inject pattern)
  const saveItems = inject(D2_SAVE_ITEMS_KEY, null)

  // ─── Computed ──────────────────────────────────────────────────────────

  /** 当前活动区的行数组 */
  const activeRows: ComputedRef<VoucherCheckRow[]> = computed(() => {
    return activeZone.value === 'current' ? currentRows.value : postRows.value
  })

  // ─── Zone Switch ───────────────────────────────────────────────────────

  function switchZone(zone: 'current' | 'post'): void {
    activeZone.value = zone
  }

  function switchViewMode(mode: 'matrix' | 'card'): void {
    viewMode.value = mode
  }

  // ─── Load from allResponses ────────────────────────────────────────────

  function loadFromResponses(): void {
    const currentResp = allResponses.value.get(CURRENT_ROWS_KEY)
    currentRows.value = parseRows(currentResp?.remark)

    const postResp = allResponses.value.get(POST_ROWS_KEY)
    postRows.value = parseRows(postResp?.remark)
  }

  // Watch for initial data load
  watch(
    () => [
      allResponses.value.get(CURRENT_ROWS_KEY)?.remark,
      allResponses.value.get(POST_ROWS_KEY)?.remark,
    ],
    () => {
      // Only auto-load if both arrays are empty (initial load)
      if (currentRows.value.length === 0 && postRows.value.length === 0) {
        loadFromResponses()
      }
    },
    { immediate: true }
  )

  // ─── Save to allResponses ──────────────────────────────────────────────

  function saveToResponses(): void {
    const items = [
      {
        item_id: CURRENT_ROWS_KEY,
        conclusion: null,
        remark: JSON.stringify(currentRows.value),
      },
      {
        item_id: POST_ROWS_KEY,
        conclusion: null,
        remark: JSON.stringify(postRows.value),
      },
    ]

    // Update local allResponses map
    for (const item of items) {
      allResponses.value.set(item.item_id, item)
    }

    // Persist via inject'd save function
    if (saveItems) {
      saveItems(items)
    }
  }

  function debounceSave(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      saveToResponses()
    }, 2000)
  }

  // ─── Row CRUD ──────────────────────────────────────────────────────────

  function addRow(): void {
    if (isReadonly.value) return
    const rows = activeZone.value === 'current' ? currentRows.value : postRows.value
    const seq = rows.length + 1
    rows.push(createEmptyRow(seq))
    debounceSave()
  }

  function removeRow(rowId: string): void {
    if (isReadonly.value) return
    const rows = activeZone.value === 'current' ? currentRows : postRows
    const idx = rows.value.findIndex(r => r.rowId === rowId)
    if (idx === -1) return
    rows.value.splice(idx, 1)
    // Re-sequence
    rows.value.forEach((r, i) => { r.seq = i + 1 })
    debounceSave()
  }

  function updateRow(rowId: string, field: keyof VoucherCheckRow, value: any): void {
    if (isReadonly.value) return
    const rows = activeZone.value === 'current' ? currentRows.value : postRows.value
    const row = rows.find(r => r.rowId === rowId)
    if (!row) return

    // Protect immutable fields
    if (field === 'rowId' || field === 'seq' || field === 'attachments' || field === 'ocrResult') return

    if (field === 'debitAmount' || field === 'creditAmount') {
      ;(row as any)[field] = Number(value) || 0
    } else {
      ;(row as any)[field] = String(value ?? '')
    }

    debounceSave()
  }

  // ─── Fill from Sampling Engine ─────────────────────────────────────────

  /**
   * 接收抽凭引擎结果，按日期分类到双区，支持合并模式
   */
  function fillFromSampledVouchers(vouchers: SampledVoucher[], mode: 'replace' | 'merge' = 'merge'): void {
    if (isReadonly.value) return

    // 按日期分类
    const currentVouchers: SampledVoucher[] = []
    const postVouchers: SampledVoucher[] = []

    for (const v of vouchers) {
      const zone = classifyVoucherToZone(v.voucherDate, bsDate.value)
      if (zone === 'current') {
        currentVouchers.push(v)
      } else {
        postVouchers.push(v)
      }
    }

    // 映射为 VoucherCheckRow
    const mappedCurrent = currentVouchers.map((v, i) => mapSampledVoucher(v, i + 1))
    const mappedPost = postVouchers.map((v, i) => mapSampledVoucher(v, i + 1))

    if (mode === 'merge') {
      currentRows.value = mergeVoucherRows(currentRows.value, mappedCurrent)
      postRows.value = mergeVoucherRows(postRows.value, mappedPost)
    } else {
      currentRows.value = mappedCurrent
      postRows.value = mappedPost
    }

    // Re-sequence
    currentRows.value.forEach((r, i) => { r.seq = i + 1 })
    postRows.value.forEach((r, i) => { r.seq = i + 1 })

    saveToResponses()
  }

  // ─── Lifecycle ─────────────────────────────────────────────────────────

  onBeforeUnmount(() => {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
      saveToResponses()
    }
  })

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // State
    currentRows,
    postRows,
    activeZone,
    viewMode,
    activeRows,
    // Zone & View
    switchZone,
    switchViewMode,
    // CRUD
    addRow,
    removeRow,
    updateRow,
    // Persistence
    loadFromResponses,
    saveToResponses,
    debounceSave,
    // Fill
    fillFromSampledVouchers,
  }
}

export default useD2VoucherCheckEnhanced
