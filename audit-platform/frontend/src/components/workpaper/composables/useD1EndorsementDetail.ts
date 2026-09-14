/**
 * useD1EndorsementDetail — D1-8 贴现背书明细 composable
 *
 * Spec: .kiro/specs/d1-endorsement-discount/
 * Task: 5.1
 *
 * 职责：
 * - 管理"已贴现尚未到期票据检查表"(discountRows) 与"已背书尚未到期票据检查表"(endorseRows)
 *   两张 16 列检查表的动态行数据
 * - 合计行 computed（discountTotal / endorseTotal，SUM 各数值列，rowType='summary'）
 * - 动态行 CRUD（addDiscountRow / removeDiscountRow / addEndorseRow / removeEndorseRow）
 * - 编辑单元格（updateCell，数值字段 parseNum、其余 String）
 * - 从备查簿 D1-7 按状态筛选导入（importFromMemo）——
 *   discount 表取 status==='已贴现'、endorse 表取 status==='已背书'，
 *   映射 MemoRow → EndorsementRow，替换目标表全部行（导入后可编辑，见 Req 17.5）
 * - 审计说明 / 审计结论（auditNote / auditConclusion）双向绑定 + 保存
 * - 序列化/反序列化（JSON ↔ checklist_responses remark），debounce 2s 自动保存
 * - respect isReadonly（只读时所有写操作 no-op）
 *
 * Requirements: 7.1-7.5, 8.1-8.5, 9.1-9.4, 13.3, 13.5, 13.6, 13.8, 17.1-17.5
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import type { ChecklistItem, ChecklistResponse } from './useD1FormData'
import { parseNum, calcSubtotal } from './useD1FormulaEngine'
import type { MemoRow } from './useD1MemoReconciliation'

// ─── Types ───────────────────────────────────────────────────────────────────

export type SaveFn = (items: ChecklistItem[]) => Promise<void>

export interface EndorsementRow {
  rowId: string
  rowType: 'dynamic' | 'summary'
  noteType: string        // 票据种类
  receivedDate: string    // 收到日期
  issuer: string          // 出票人
  noteNumber: string      // 票据号
  billAmount: number      // 汇票金额
  accruedInterest: number // 已计利息
  issueDate: string       // 出票日
  maturityDate: string    // 到期日
  acceptorBank: string    // 承兑银行
  creditRating: string    // 信用等级
  discountBank: string    // 贴现银行
  discountAmount: number  // 贴现金额
  discountInterest: number // 贴现息
  isDerecognized: string  // 是否终止确认
  isCorrect: string       // 会计处理是否正确
  indexRef: string        // 索引号
}

export interface UseD1EndorsementDetailOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  wpId: Ref<string>
  projectId: Ref<string>
  saveImmediate: SaveFn
  isReadonly: Ref<boolean>
}

// ─── Constants ───────────────────────────────────────────────────────────────

const DISCOUNT_ROWS_KEY = 'D1-endorse-discount-rows'
const TRANSFER_ROWS_KEY = 'D1-endorse-transfer-rows'
const NOTE_KEY = 'D1-endorse-note'
const CONCLUSION_KEY = 'D1-endorse-conclusion'

/** EndorsementRow 全部数值字段（用于 SUM / parseNum / 空行工厂） */
const NUMERIC_FIELDS: Array<keyof EndorsementRow> = [
  'billAmount',
  'accruedInterest',
  'discountAmount',
  'discountInterest',
]

/** EndorsementRow 全部字符串字段（rowId / rowType 单独处理） */
const STRING_FIELDS: Array<keyof EndorsementRow> = [
  'noteType',
  'receivedDate',
  'issuer',
  'noteNumber',
  'issueDate',
  'maturityDate',
  'acceptorBank',
  'creditRating',
  'discountBank',
  'isDerecognized',
  'isCorrect',
  'indexRef',
]

// ─── Helpers ─────────────────────────────────────────────────────────────────

/** 生成动态行 ID */
function generateRowId(): string {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return `dynamic-${crypto.randomUUID()}`
  }
  return `dynamic-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

/** 空 EndorsementRow 工厂：所有数值字段 0、字符串字段 ''、全新 rowId、rowType='dynamic' */
export function emptyEndorsementRow(): EndorsementRow {
  return {
    rowId: generateRowId(),
    rowType: 'dynamic',
    noteType: '',
    receivedDate: '',
    issuer: '',
    noteNumber: '',
    billAmount: 0,
    accruedInterest: 0,
    issueDate: '',
    maturityDate: '',
    acceptorBank: '',
    creditRating: '',
    discountBank: '',
    discountAmount: 0,
    discountInterest: 0,
    isDerecognized: '',
    isCorrect: '',
    indexRef: '',
  }
}

/** 反序列化单行：安全转换所有字段类型 */
function deserializeRow(raw: any): EndorsementRow {
  const row = emptyEndorsementRow()
  if (raw && typeof raw.rowId === 'string' && raw.rowId) row.rowId = raw.rowId
  for (const f of STRING_FIELDS) {
    if (raw && typeof raw[f] === 'string') (row as any)[f] = raw[f]
  }
  for (const f of NUMERIC_FIELDS) {
    if (raw && raw[f] !== undefined) (row as any)[f] = parseNum(raw[f])
  }
  return row
}

/** 序列化单行：保留全部字段（数值+字符串） */
function serializeRow(row: EndorsementRow): any {
  const data: any = {
    rowId: row.rowId,
    rowType: row.rowType,
  }
  for (const f of STRING_FIELDS) data[f] = (row as any)[f]
  for (const f of NUMERIC_FIELDS) data[f] = (row as any)[f]
  return data
}

/** 构建合计行（SUM 所有数值列，rowType='summary'，noteType 列填 '合计'） */
function buildTotalRow(rows: EndorsementRow[]): EndorsementRow {
  const total = emptyEndorsementRow()
  total.rowId = 'summary-total'
  total.rowType = 'summary'
  total.noteType = '合计'
  for (const f of NUMERIC_FIELDS) {
    ;(total as any)[f] = calcSubtotal(rows.map((r) => (r as any)[f] as number))
  }
  return total
}

/** 将 MemoRow 映射为 EndorsementRow（从备查簿导入） */
function mapMemoRow(memo: MemoRow, table: 'discount' | 'endorse'): EndorsementRow {
  const row = emptyEndorsementRow()
  row.noteType = memo.noteType ?? ''
  row.receivedDate = memo.receivedDate ?? ''
  row.issuer = memo.issuer ?? ''
  row.noteNumber = memo.noteNumber ?? ''
  row.billAmount = parseNum(memo.amount)
  row.issueDate = memo.issueDate ?? ''
  row.maturityDate = memo.maturityDate ?? ''
  row.acceptorBank = memo.acceptor ?? ''
  row.creditRating = memo.creditRating ?? ''
  row.discountBank = memo.discountBank ?? ''
  row.discountInterest = parseNum(memo.discountInterest)
  // 贴现表贴现金额取备查簿本期贴现额，无则回退汇票金额；背书表取汇票金额
  row.discountAmount =
    table === 'discount'
      ? parseNum(memo.currentDiscounted) || parseNum(memo.amount)
      : parseNum(memo.amount)
  row.isDerecognized = memo.isDerecognized ?? ''
  // 导入后由用户填写的字段
  row.accruedInterest = 0
  row.isCorrect = ''
  row.indexRef = ''
  return row
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD1EndorsementDetail(options: UseD1EndorsementDetailOptions) {
  const { allResponses, saveImmediate, isReadonly } = options

  // ─── State ───────────────────────────────────────────────────────────────

  const discountRows = ref<EndorsementRow[]>([])
  const endorseRows = ref<EndorsementRow[]>([])
  const auditNote = ref<string>('')
  const auditConclusion = ref<string>('')

  // ─── Deserialization (Load from allResponses) ────────────────────────────

  function loadRows(key: string): EndorsementRow[] {
    const raw = allResponses.value.get(key)?.remark
    if (!raw) return []
    try {
      const parsed = JSON.parse(raw)
      if (!Array.isArray(parsed)) return []
      return parsed.map((r: any) => deserializeRow(r))
    } catch {
      return []
    }
  }

  function loadFromResponses(): void {
    discountRows.value = loadRows(DISCOUNT_ROWS_KEY)
    endorseRows.value = loadRows(TRANSFER_ROWS_KEY)
    auditNote.value = allResponses.value.get(NOTE_KEY)?.remark ?? ''
    auditConclusion.value = allResponses.value.get(CONCLUSION_KEY)?.remark ?? ''
  }

  // Initial load
  loadFromResponses()

  // Watch allResponses for external changes (other tabs / OO sync)
  watch(
    () => [
      allResponses.value.get(DISCOUNT_ROWS_KEY)?.remark,
      allResponses.value.get(TRANSFER_ROWS_KEY)?.remark,
      allResponses.value.get(NOTE_KEY)?.remark,
      allResponses.value.get(CONCLUSION_KEY)?.remark,
    ],
    ([newDiscount, newTransfer, newNote, newConclusion]) => {
      if (newDiscount !== undefined && newDiscount !== serializeRows(discountRows.value)) {
        discountRows.value = loadRows(DISCOUNT_ROWS_KEY)
      }
      if (newTransfer !== undefined && newTransfer !== serializeRows(endorseRows.value)) {
        endorseRows.value = loadRows(TRANSFER_ROWS_KEY)
      }
      if (newNote !== undefined && newNote !== auditNote.value) {
        auditNote.value = newNote ?? ''
      }
      if (newConclusion !== undefined && newConclusion !== auditConclusion.value) {
        auditConclusion.value = newConclusion ?? ''
      }
    },
  )

  // ─── Serialization ───────────────────────────────────────────────────────

  function serializeRows(rows: EndorsementRow[]): string {
    return JSON.stringify(rows.map(serializeRow))
  }

  // ─── Debounce Save ───────────────────────────────────────────────────────

  let saveTimer: ReturnType<typeof setTimeout> | null = null

  function scheduleSave(): void {
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = setTimeout(() => {
      saveTimer = null
      persistToResponses()
    }, 2000)
  }

  function persistToResponses(): void {
    const items: ChecklistItem[] = [
      { item_id: DISCOUNT_ROWS_KEY, conclusion: null, remark: serializeRows(discountRows.value) },
      { item_id: TRANSFER_ROWS_KEY, conclusion: null, remark: serializeRows(endorseRows.value) },
      { item_id: NOTE_KEY, conclusion: null, remark: auditNote.value || null },
      { item_id: CONCLUSION_KEY, conclusion: null, remark: auditConclusion.value || null },
    ]
    for (const item of items) {
      allResponses.value.set(item.item_id, item)
    }
    saveImmediate(items)
  }

  // ─── Totals (computed) ───────────────────────────────────────────────────

  const discountTotal: ComputedRef<EndorsementRow> = computed(() =>
    buildTotalRow(discountRows.value),
  )

  const endorseTotal: ComputedRef<EndorsementRow> = computed(() =>
    buildTotalRow(endorseRows.value),
  )

  // ─── Row CRUD ────────────────────────────────────────────────────────────

  function addDiscountRow(): void {
    if (isReadonly.value) return
    discountRows.value = [...discountRows.value, emptyEndorsementRow()]
    scheduleSave()
  }

  function removeDiscountRow(rowId: string): void {
    if (isReadonly.value) return
    if (discountRows.value.some((r) => r.rowId === rowId)) {
      discountRows.value = discountRows.value.filter((r) => r.rowId !== rowId)
      scheduleSave()
    }
  }

  function addEndorseRow(): void {
    if (isReadonly.value) return
    endorseRows.value = [...endorseRows.value, emptyEndorsementRow()]
    scheduleSave()
  }

  function removeEndorseRow(rowId: string): void {
    if (isReadonly.value) return
    if (endorseRows.value.some((r) => r.rowId === rowId)) {
      endorseRows.value = endorseRows.value.filter((r) => r.rowId !== rowId)
      scheduleSave()
    }
  }

  /** 编辑单元格 → 数值字段 parseNum、其余 String → debounce 保存 */
  function updateCell(
    table: 'discount' | 'endorse',
    rowId: string,
    field: string,
    value: string | number,
  ): void {
    if (isReadonly.value) return

    const list = table === 'discount' ? discountRows : endorseRows
    const idx = list.value.findIndex((r) => r.rowId === rowId)
    if (idx === -1) return

    const row = { ...list.value[idx] }
    if (NUMERIC_FIELDS.includes(field as keyof EndorsementRow)) {
      ;(row as any)[field] = parseNum(value)
    } else if (STRING_FIELDS.includes(field as keyof EndorsementRow)) {
      ;(row as any)[field] = String(value)
    } else {
      return
    }
    const newRows = [...list.value]
    newRows[idx] = row
    list.value = newRows
    scheduleSave()
  }

  // ─── 从备查簿 D1-7 导入 ───────────────────────────────────────────────────

  /**
   * 从备查簿按状态筛选导入并替换目标表全部行（Req 17.1/17.2/17.5）：
   * - table='discount' 保留 status==='已贴现'
   * - table='endorse'  保留 status==='已背书'
   * 导入后为可编辑动态行（rowType='dynamic'，新 rowId）。
   */
  function importFromMemo(table: 'discount' | 'endorse', memoRows: MemoRow[]): void {
    if (isReadonly.value) return
    const targetStatus = table === 'discount' ? '已贴现' : '已背书'
    const mapped = (memoRows ?? [])
      .filter((m) => m.status === targetStatus)
      .map((m) => mapMemoRow(m, table))

    if (table === 'discount') {
      discountRows.value = mapped
    } else {
      endorseRows.value = mapped
    }
    scheduleSave()
  }

  // ─── 审计说明 / 审计结论 ───────────────────────────────────────────────────

  function saveAuditNote(text: string): void {
    if (isReadonly.value) return
    auditNote.value = text
    scheduleSave()
  }

  function saveAuditConclusion(text: string): void {
    if (isReadonly.value) return
    auditConclusion.value = text
    scheduleSave()
  }

  // ─── Cleanup ─────────────────────────────────────────────────────────────

  onBeforeUnmount(() => {
    if (saveTimer) {
      clearTimeout(saveTimer)
      persistToResponses()
    }
  })

  // ─── Return ──────────────────────────────────────────────────────────────

  return {
    discountRows,
    endorseRows,
    discountTotal,
    endorseTotal,
    auditNote,
    auditConclusion,
    addDiscountRow,
    removeDiscountRow,
    addEndorseRow,
    removeEndorseRow,
    updateCell,
    importFromMemo,
    saveAuditNote,
    saveAuditConclusion,
  }
}

export default useD1EndorsementDetail
