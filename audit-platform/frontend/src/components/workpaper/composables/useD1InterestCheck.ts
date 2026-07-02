/**
 * useD1InterestCheck — D1-9 贴息检查 composable
 *
 * Spec: .kiro/specs/d1-endorsement-discount/
 * Task: 6.1
 *
 * 职责：
 * - 管理贴息计算表（rows）的动态行数据（13 列）
 * - 每行自动计算三个派生字段（recalcRow，仿 useD1BadDebt.recalcRow）：
 *   - discountDays = calcDiscountDays(maturityDate, discountDate)
 *   - calculatedInterest = calcDiscountInterest(faceValue, discountRate, discountDays)
 *   - difference = calcInterestDifference(calculatedInterest, bookedInterest)
 *   派生字段在加载时和每次 updateCell 后必须重算（不信任持久化值）
 * - 合计行 computed（totalRow，SUM 票面金额/到期日票据价值/应计利息/账面利息/差异，rowType='summary'）
 * - 差异统计 computed（totalDifference / differenceCount / maxDifference）
 * - 动态行 CRUD（addRow / removeRow / updateCell）
 * - 审计说明 / 审计结论（auditNote / auditConclusion）双向绑定 + 保存
 * - 序列化只存可编辑字段（派生字段加载时重算），debounce 2s 自动保存
 * - respect isReadonly（只读时所有写操作 no-op）
 *
 * Requirements: 10.1-10.9, 11.1-11.4, 13.4, 13.5, 13.6, 13.9
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import type { ChecklistItem, ChecklistResponse } from './useD1FormData'
import {
  parseNum,
  calcSubtotal,
  calcDiscountDays,
  calcDiscountInterest,
  calcInterestDifference,
} from './useD1FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export type SaveFn = (items: ChecklistItem[]) => Promise<void>

export interface InterestCheckRow {
  rowId: string
  rowType: 'dynamic' | 'summary'
  noteType: string           // 票据类型
  faceValue: number          // 票面金额
  faceRate: number           // 票面利率
  issueDate: string          // 出票日期
  maturityDate: string       // 到期日
  maturityValue: number      // 到期日票据价值
  discountDate: string       // 贴现日期
  discountDays: number       // 贴息天数（自动计算，只读派生）
  discountRate: number       // 贴现率
  calculatedInterest: number // 应计贴现利息（自动计算，只读派生）
  bookedInterest: number     // 账面贴现利息
  difference: number         // 差异（自动计算，只读派生）
  remark: string             // 备注
}

export interface UseD1InterestCheckOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  wpId: Ref<string>
  projectId: Ref<string>
  saveImmediate: SaveFn
  isReadonly: Ref<boolean>
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ROWS_KEY = 'D1-interest-rows'
const NOTE_KEY = 'D1-interest-note'
const CONCLUSION_KEY = 'D1-interest-conclusion'

/** 可编辑数值字段（parseNum、序列化存储） */
const NUMERIC_EDITABLE_FIELDS: Array<keyof InterestCheckRow> = [
  'faceValue',
  'faceRate',
  'maturityValue',
  'discountRate',
  'bookedInterest',
]

/** 可编辑字符串字段（String、序列化存储） */
const STRING_EDITABLE_FIELDS: Array<keyof InterestCheckRow> = [
  'noteType',
  'issueDate',
  'maturityDate',
  'discountDate',
  'remark',
]

/** 派生数值字段（recalcRow 重算，不信任持久化值，SUM 用） */
const DERIVED_NUMERIC_FIELDS: Array<keyof InterestCheckRow> = [
  'discountDays',
  'calculatedInterest',
  'difference',
]

/** 合计行汇总的数值列（Req 10.8：票面金额/应计利息/账面利息/差异，另含到期日票据价值） */
const TOTAL_SUM_FIELDS: Array<keyof InterestCheckRow> = [
  'faceValue',
  'maturityValue',
  'calculatedInterest',
  'bookedInterest',
  'difference',
]

// ─── Helpers ─────────────────────────────────────────────────────────────────

/** 生成动态行 ID */
function generateRowId(): string {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return `dynamic-${crypto.randomUUID()}`
  }
  return `dynamic-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

/** 空 InterestCheckRow 工厂：所有数值字段 0、字符串字段 ''、全新 rowId、rowType='dynamic' */
export function emptyInterestRow(): InterestCheckRow {
  return {
    rowId: generateRowId(),
    rowType: 'dynamic',
    noteType: '',
    faceValue: 0,
    faceRate: 0,
    issueDate: '',
    maturityDate: '',
    maturityValue: 0,
    discountDate: '',
    discountDays: 0,
    discountRate: 0,
    calculatedInterest: 0,
    bookedInterest: 0,
    difference: 0,
    remark: '',
  }
}

/**
 * 重算行内派生字段（仿 useD1BadDebt.recalcRow）：
 * - discountDays = calcDiscountDays(maturityDate, discountDate)
 * - calculatedInterest = calcDiscountInterest(faceValue, discountRate, discountDays)
 * - difference = calcInterestDifference(calculatedInterest, bookedInterest)
 *
 * 这三个字段为纯派生，加载时与每次编辑后都必须重算（不信任持久化值）。
 */
function recalcRow(row: InterestCheckRow): InterestCheckRow {
  const discountDays = calcDiscountDays(row.maturityDate, row.discountDate)
  const calculatedInterest = calcDiscountInterest(row.faceValue, row.discountRate, discountDays)
  const difference = calcInterestDifference(calculatedInterest, row.bookedInterest)
  return {
    ...row,
    discountDays,
    calculatedInterest,
    difference,
  }
}

/** 反序列化单行：仅读取可编辑字段，派生字段随后由 recalcRow 重算 */
function deserializeRow(raw: any): InterestCheckRow {
  const row = emptyInterestRow()
  if (raw && typeof raw.rowId === 'string' && raw.rowId) row.rowId = raw.rowId
  for (const f of STRING_EDITABLE_FIELDS) {
    if (raw && typeof raw[f] === 'string') (row as any)[f] = raw[f]
  }
  for (const f of NUMERIC_EDITABLE_FIELDS) {
    if (raw && raw[f] !== undefined) (row as any)[f] = parseNum(raw[f])
  }
  return recalcRow(row)
}

/** 序列化单行：仅保留可编辑字段（派生字段加载时重算，不持久化） */
function serializeRow(row: InterestCheckRow): any {
  const data: any = {
    rowId: row.rowId,
    rowType: row.rowType,
  }
  for (const f of STRING_EDITABLE_FIELDS) data[f] = (row as any)[f]
  for (const f of NUMERIC_EDITABLE_FIELDS) data[f] = (row as any)[f]
  return data
}

/** 构建合计行（SUM 汇总数值列，rowType='summary'，noteType 列填 '合计'） */
function buildTotalRow(rows: InterestCheckRow[]): InterestCheckRow {
  const total = emptyInterestRow()
  total.rowId = 'summary-total'
  total.rowType = 'summary'
  total.noteType = '合计'
  for (const f of TOTAL_SUM_FIELDS) {
    ;(total as any)[f] = calcSubtotal(rows.map((r) => (r as any)[f] as number))
  }
  return total
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD1InterestCheck(options: UseD1InterestCheckOptions) {
  const { allResponses, saveImmediate, isReadonly } = options

  // ─── State ───────────────────────────────────────────────────────────────

  const rows = ref<InterestCheckRow[]>([])
  const auditNote = ref<string>('')
  const auditConclusion = ref<string>('')

  // ─── Deserialization (Load from allResponses) ────────────────────────────

  function loadRows(): InterestCheckRow[] {
    const raw = allResponses.value.get(ROWS_KEY)?.remark
    if (!raw) return []
    try {
      const parsed = JSON.parse(raw)
      if (!Array.isArray(parsed)) return []
      // 每行反序列化后 recalcRow 重算派生字段（不信任持久化值）
      return parsed.map((r: any) => deserializeRow(r))
    } catch {
      return []
    }
  }

  function loadFromResponses(): void {
    rows.value = loadRows()
    auditNote.value = allResponses.value.get(NOTE_KEY)?.remark ?? ''
    auditConclusion.value = allResponses.value.get(CONCLUSION_KEY)?.remark ?? ''
  }

  // Initial load
  loadFromResponses()

  // Watch allResponses for external changes (other tabs / OO sync)
  watch(
    () => [
      allResponses.value.get(ROWS_KEY)?.remark,
      allResponses.value.get(NOTE_KEY)?.remark,
      allResponses.value.get(CONCLUSION_KEY)?.remark,
    ],
    ([newRows, newNote, newConclusion]) => {
      if (newRows !== undefined && newRows !== serializeRows(rows.value)) {
        rows.value = loadRows()
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

  function serializeRows(list: InterestCheckRow[]): string {
    return JSON.stringify(list.map(serializeRow))
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
      { item_id: ROWS_KEY, conclusion: null, remark: serializeRows(rows.value) },
      { item_id: NOTE_KEY, conclusion: null, remark: auditNote.value || null },
      { item_id: CONCLUSION_KEY, conclusion: null, remark: auditConclusion.value || null },
    ]
    for (const item of items) {
      allResponses.value.set(item.item_id, item)
    }
    saveImmediate(items)
  }

  // ─── Totals & 差异统计 (computed) ─────────────────────────────────────────

  const totalRow: ComputedRef<InterestCheckRow> = computed(() => buildTotalRow(rows.value))

  /** 差异合计（= totalRow.difference） */
  const totalDifference: ComputedRef<number> = computed(() =>
    calcSubtotal(rows.value.map((r) => r.difference)),
  )

  /** 有差异的笔数（difference !== 0） */
  const differenceCount: ComputedRef<number> = computed(
    () => rows.value.filter((r) => r.difference !== 0).length,
  )

  /** 最大单笔差异（绝对值），无行时为 0 */
  const maxDifference: ComputedRef<number> = computed(() => {
    if (rows.value.length === 0) return 0
    return rows.value.reduce((max, r) => Math.max(max, Math.abs(r.difference)), 0)
  })

  // ─── Row CRUD ────────────────────────────────────────────────────────────

  function addRow(): void {
    if (isReadonly.value) return
    rows.value = [...rows.value, recalcRow(emptyInterestRow())]
    scheduleSave()
  }

  function removeRow(rowId: string): void {
    if (isReadonly.value) return
    if (rows.value.some((r) => r.rowId === rowId)) {
      rows.value = rows.value.filter((r) => r.rowId !== rowId)
      scheduleSave()
    }
  }

  /**
   * 编辑单元格 → 应用可编辑字段（数值 parseNum、字符串 String）→ recalcRow 重算派生字段 → debounce 保存。
   * 派生字段（discountDays/calculatedInterest/difference）为只读，直接编辑将被忽略。
   */
  function updateCell(rowId: string, field: string, value: string | number): void {
    if (isReadonly.value) return

    const idx = rows.value.findIndex((r) => r.rowId === rowId)
    if (idx === -1) return

    const row = { ...rows.value[idx] }
    if (NUMERIC_EDITABLE_FIELDS.includes(field as keyof InterestCheckRow)) {
      ;(row as any)[field] = parseNum(value)
    } else if (STRING_EDITABLE_FIELDS.includes(field as keyof InterestCheckRow)) {
      ;(row as any)[field] = String(value)
    } else {
      // 派生字段（discountDays/calculatedInterest/difference）或未知字段 → 忽略
      return
    }
    const recalculated = recalcRow(row)
    const newRows = [...rows.value]
    newRows[idx] = recalculated
    rows.value = newRows
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
    rows,
    totalRow,
    totalDifference,
    differenceCount,
    maxDifference,
    auditNote,
    auditConclusion,
    addRow,
    removeRow,
    updateCell,
    saveAuditNote,
    saveAuditConclusion,
  }
}

export default useD1InterestCheck
