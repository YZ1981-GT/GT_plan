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
 * - 抽凭回填 / 挂凭导入 / 撤销 / 年审阶段预审行只读：共享回填函数 `useVoucherCheckFill`
 *   （按分录指纹去重，行元数据 `_gt` 随行 JSON 落库；spec voucher-identity-writeback-and-audit-phase 任务 10）
 * - Excel 导入的合并（mergeVoucherRows，按凭证编号）
 *
 * Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 10.1, 10.2, 10.3
 */
import { ref, computed, watch, onBeforeUnmount, inject, type Ref, type ComputedRef, type MaybeRefOrGetter } from 'vue'
import { D2_SAVE_ITEMS_KEY } from './d2InjectionKeys'
import { registerPendingFlusher } from '../sync/pendingWrites'
import { metaOf, useVoucherCheckFill, withRowMeta, type PreparedItem } from './shared/voucherCheckFill'

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
  /** 项目（读项目当前审计阶段：回填行按它标阶段，年审阶段预审行只读） */
  projectId?: MaybeRefOrGetter<string | null | undefined>
}

/** 抽凭引擎返回的采样凭证结构 */
export interface SampledVoucher {
  voucherNo: string
  voucherDate: string
  debitAmount?: number
  creditAmount?: number
  summary?: string
  counterpartAccount?: string
  counterpartAccountName?: string
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
    counterpartDetail: voucher.counterpartAccountName || voucher.accountCode || '',
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

/** 金额栏取数：两位小数字符串 / 数值 → 数值（带千分位的照样认，认不出记 0） */
function toAmount(value: unknown): number {
  const n = Number(String(value ?? '').replace(/,/g, '').trim() || 0)
  return Number.isFinite(n) ? n : 0
}

/**
 * 共享回填函数的待写入项 → 凭证检查行。
 * 对方科目取后端配对结果（配不上的写「多科目」），金额落在样本自己的借贷栏；
 * 对方明细科目只写对方科目名称（不再拿被抽科目自己的编码凑数）；来源：自动抽凭 / 挂凭导入。
 */
export function mapPreparedItem(item: PreparedItem): VoucherCheckRow {
  const s = item.sample as PreparedItem['sample'] & Partial<SampledVoucher>
  const row = mapSampledVoucher({
    voucherNo: String(s.voucherNo ?? ''),
    voucherDate: String(s.voucherDate ?? ''),
    summary: s.summary ?? undefined,
    customerName: s.customerName ?? undefined,
    counterpartAccount: item.counterpartAccount,
    counterpartAccountName: item.counterpartAccountName === item.counterpartAccount ? '' : item.counterpartAccountName,
    debitAmount: toAmount(item.debitAmount),
    creditAmount: toAmount(item.creditAmount),
  }, 0)
  if (item.meta.src.includes('attach')) row.source = '挂凭导入'
  return row
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
    return parsed.map((raw: any, idx: number) => withRowMeta<VoucherCheckRow>({
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
    }, raw))
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

  /** 已在某一区的分录（按指纹）：再次回填仍进那一区（期末日改过也不在另一区重复插入） */
  function zoneHolding(lfp: string | null): 'current' | 'post' | null {
    if (!lfp) return null
    if (currentRows.value.some(r => metaOf(r)?.lfp === lfp)) return 'current'
    if (postRows.value.some(r => metaOf(r)?.lfp === lfp)) return 'post'
    return null
  }

  // 抽凭回填 / 挂凭导入 / 撤销 / 年审阶段预审行只读：共享回填函数（两区各是一张表，按凭证日期分区）
  const voucherFill = useVoucherCheckFill<VoucherCheckRow>({
    projectId: options.projectId ?? null,
    tables: { current: currentRows, post: postRows },
    tableOf: item => zoneHolding(item.meta.lfp)
      ?? classifyVoucherToZone(String(item.sample.voucherDate ?? ''), bsDate.value),
    mapSampleToRow: item => mapPreparedItem(item),
    persist: () => saveToResponses(),
    hasUserContent: r => [r.check1, r.check2, r.check3, r.check4, r.check5, r.supportingDoc, r.indexRef, r.isAbnormal, r.remark]
      .some(v => String(v ?? '').trim() !== '') || (r.attachments?.length ?? 0) > 0,
    afterChange: (_key, rows) => rows.forEach((r, i) => { r.seq = i + 1 }),
    readonly: isReadonly,
  })

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
    voucherFill.markLoaded()
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
        remark: JSON.stringify(voucherFill.guardPersist(currentRows.value, 'current')),
      },
      {
        item_id: POST_ROWS_KEY,
        conclusion: null,
        remark: JSON.stringify(voucherFill.guardPersist(postRows.value, 'post')),
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
    // 年审阶段预审行只读（不可删）
    if (idx === -1 || voucherFill.isRowLocked(rows.value[idx])) return
    rows.value.splice(idx, 1)
    // Re-sequence
    rows.value.forEach((r, i) => { r.seq = i + 1 })
    debounceSave()
  }

  function updateRow(rowId: string, field: keyof VoucherCheckRow, value: any): void {
    if (isReadonly.value) return
    const rows = activeZone.value === 'current' ? currentRows.value : postRows.value
    const row = rows.find(r => r.rowId === rowId)
    // 年审阶段预审行只读（不可改）
    if (!row || voucherFill.isRowLocked(row)) return

    // Protect immutable fields
    if (field === 'rowId' || field === 'seq' || field === 'attachments' || field === 'ocrResult') return

    if (field === 'debitAmount' || field === 'creditAmount') {
      ;(row as any)[field] = Number(value) || 0
    } else {
      ;(row as any)[field] = String(value ?? '')
    }

    debounceSave()
  }

  // ─── Lifecycle ─────────────────────────────────────────────────────────

  // 🔴 R20（spec d2-online-edit-platform-closure）：切「在线编辑」前桥统一 flushPendingWrites()。
  //    防抖窗口里的编辑必须立即落库，否则宿主读到旧 store（见 sync/pendingWrites.ts）；
  //    语义与下面卸载时那段相同，写出口经宿主的 d2SaveItems 追踪在途。
  registerPendingFlusher(() => {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
      saveToResponses()
    }
  })

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
    // 抽凭回填 / 挂凭导入 / 撤销 / 年审阶段预审行只读（共享回填函数）
    onEngineFilled: voucherFill.onEngineFilled,
    onAttachImported: voucherFill.onAttachImported,
    onUndoRequest: voucherFill.onUndoRequest,
    voucherRowClass: voucherFill.rowClass,
    isVoucherRowLocked: voucherFill.isRowLocked,
    voucherFillReady: voucherFill.ready,
  }
}

export default useD2VoucherCheckEnhanced
