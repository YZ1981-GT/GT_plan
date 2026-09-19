/**
 * useE1Adjustment — E1-5 调整分录汇总 composable
 *
 * Spec: .kiro/specs/e1-monetary-fund-refactor/
 * Task: 6.1
 *
 * 职责：
 * - 动态行管理（调整事项说明/类别[报表调整/账项调整/其他]/报表项目/科目名称/附注项目/借方/贷方/索引/备注）
 * - 借贷平衡校验 isBalanced(rows, 'debit', 'credit')
 * - 底部借贷合计 + 差额显示（差额≠0红色）
 * - EventBus 发布 'adjustment:created'（CustomEvent）
 * - 按 reportItem/accountName 归集账项调整净额（借-贷），写入 allResponses 供 E1-1 取数
 *   key格式: 'E1-adjustment-by-item-{itemKey}-ending'
 * - "推送A2"按钮: dispatch CustomEvent 'e1:push-to-a2'
 * - 序列化到 'E1-adjustment-rows' in checklist_responses
 *
 * Requirements: 5.1-5.5
 */
import { ref, computed, watch, onBeforeUnmount, type ComputedRef } from 'vue'
import type { UseE1BaseOptions, ChecklistItem } from './useE1Adjudication'
import { parseNum, sumField, isBalanced } from './useE1FormulaEngine'
import { eventBus } from '@/utils/eventBus'

// ─── Types ───────────────────────────────────────────────────────────────────

export type AdjustmentCategory = '报表调整' | '账项调整' | '其他'

export interface AdjustmentRow {
  id: string
  description: string        // 调整事项说明
  category: AdjustmentCategory // 类别
  reportItem: string         // 报表项目
  accountName: string        // 科目名称
  noteItem: string           // 附注项目
  debit: number              // 借方调整金额
  credit: number             // 贷方调整金额
  indexNo: string            // 索引
  note: string               // 备注
}

// ─── Constants ───────────────────────────────────────────────────────────────

const STORAGE_KEY = 'E1-adjustment-rows'

/** 用户输入字段（序列化时保留） */
const USER_FIELDS: Array<keyof AdjustmentRow> = [
  'id', 'description', 'category', 'reportItem', 'accountName',
  'noteItem', 'debit', 'credit', 'indexNo', 'note',
]

/** 报表项目→审定表itemKey映射（用于归集净额写入allResponses供E1-1取数） */
const REPORT_ITEM_TO_ADJ_KEY: Record<string, string> = {
  '库存现金': 'cash',
  '银行存款': 'bank_principal',
  '存放财务公司款项': 'finance_co',
  '银行机构存款': 'bank_institution',
  '其他货币资金': 'other_mf',
  '数字货币': 'digital',
  '应计利息': 'accrued_interest',
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

/** 生成行 ID */
function generateRowId(): string {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return `adj-${crypto.randomUUID()}`
  }
  return `adj-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

/** 创建空白调整行 */
function createEmptyRow(): AdjustmentRow {
  return {
    id: generateRowId(),
    description: '',
    category: '账项调整',
    reportItem: '',
    accountName: '',
    noteItem: '',
    debit: 0,
    credit: 0,
    indexNo: '',
    note: '',
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useE1Adjustment(options: UseE1BaseOptions) {
  const { allResponses, saveImmediate, isReadonly } = options

  // ─── State ───────────────────────────────────────────────────────────────

  const rows = ref<AdjustmentRow[]>([])
  const isLoading = ref(false)

  // ─── Deserialization (Load from allResponses) ────────────────────────────

  function loadFromResponses(): void {
    const response = allResponses.value.get(STORAGE_KEY)
    const raw = response?.remark
    if (!raw) {
      rows.value = []
      return
    }
    try {
      const parsed = JSON.parse(raw)
      if (!Array.isArray(parsed)) {
        rows.value = []
        return
      }
      rows.value = parsed.map((r: Record<string, unknown>) => ({
        id: String(r.id || generateRowId()),
        description: String(r.description || ''),
        category: (['报表调整', '账项调整', '其他'].includes(String(r.category))
          ? String(r.category) as AdjustmentCategory
          : '账项调整'),
        reportItem: String(r.reportItem || ''),
        accountName: String(r.accountName || ''),
        noteItem: String(r.noteItem || ''),
        debit: parseNum(r.debit),
        credit: parseNum(r.credit),
        indexNo: String(r.indexNo || ''),
        note: String(r.note || ''),
      }))
    } catch {
      rows.value = []
    }
  }

  // Initial load
  loadFromResponses()

  // Watch allResponses for external changes
  watch(
    () => allResponses.value.get(STORAGE_KEY)?.remark,
    (newRemark, oldRemark) => {
      if (newRemark !== oldRemark && newRemark !== serializeRows()) {
        loadFromResponses()
      }
    },
  )

  // ─── Serialization ───────────────────────────────────────────────────────

  function serializeRows(): string {
    const data = rows.value.map(row => {
      const obj: Record<string, unknown> = {}
      for (const field of USER_FIELDS) {
        obj[field] = row[field]
      }
      return obj
    })
    return JSON.stringify(data)
  }

  // ─── Computed: Totals & Balance ──────────────────────────────────────────

  /** 借方合计 */
  const totalDebit: ComputedRef<number> = computed(() =>
    sumField(rows.value as unknown as Array<Record<string, unknown>>, 'debit'),
  )

  /** 贷方合计 */
  const totalCredit: ComputedRef<number> = computed(() =>
    sumField(rows.value as unknown as Array<Record<string, unknown>>, 'credit'),
  )

  /** 借贷差额（借方-贷方，≠0显示红色） */
  const balanceDiff: ComputedRef<number> = computed(() =>
    totalDebit.value - totalCredit.value,
  )

  /** 借贷是否平衡 */
  const balanced: ComputedRef<boolean> = computed(() =>
    isBalanced(rows.value as unknown as Array<Record<string, unknown>>, 'debit', 'credit'),
  )

  // ─── Cross-Sheet Write: 按项目归集账项调整净额 ───────────────────────────

  /**
   * 按 reportItem 归集"账项调整"类别的净额（debit - credit），
   * 写入 allResponses 供 E1-1 审定表账项调整列取数。
   * key格式: 'E1-adjustment-by-item-{itemKey}-ending'
   */
  function writeCrossSheetAdjustments(): void {
    // 只归集 category='账项调整' 的行
    const adjustmentRows = rows.value.filter(r => r.category === '账项调整')

    // 按 reportItem 分组求净额
    const netByItem: Record<string, number> = {}
    for (const row of adjustmentRows) {
      const itemKey = REPORT_ITEM_TO_ADJ_KEY[row.reportItem]
      if (!itemKey) continue
      if (!netByItem[itemKey]) netByItem[itemKey] = 0
      netByItem[itemKey] += row.debit - row.credit
    }

    // 先清除所有旧的 adjustment-by-item keys（确保删除的行不残留）
    for (const key of Object.values(REPORT_ITEM_TO_ADJ_KEY)) {
      const endingKey = `E1-adjustment-by-item-${key}-ending`
      const openingKey = `E1-adjustment-by-item-${key}-opening`
      const endingVal = String(netByItem[key] || 0)
      allResponses.value.set(endingKey, { item_id: endingKey, conclusion: null, remark: endingVal })
      // opening 暂用 0（期初调整需来源于历史数据或手工输入，此处默认0）
      if (!allResponses.value.has(openingKey)) {
        allResponses.value.set(openingKey, { item_id: openingKey, conclusion: null, remark: '0' })
      }
    }
  }

  // Watch rows to keep cross-sheet data in sync
  watch(
    () => rows.value.map(r => `${r.reportItem}:${r.category}:${r.debit}:${r.credit}`).join('|'),
    () => { writeCrossSheetAdjustments() },
    { immediate: true },
  )

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
    const serialized = serializeRows()
    const items: ChecklistItem[] = []

    // Save rows data
    const rowItem: ChecklistItem = { item_id: STORAGE_KEY, conclusion: null, remark: serialized }
    allResponses.value.set(STORAGE_KEY, { item_id: STORAGE_KEY, conclusion: null, remark: serialized })
    items.push(rowItem)

    // Also persist cross-sheet adjustment keys
    for (const key of Object.values(REPORT_ITEM_TO_ADJ_KEY)) {
      const endingKey = `E1-adjustment-by-item-${key}-ending`
      const resp = allResponses.value.get(endingKey)
      if (resp) {
        items.push({ item_id: endingKey, conclusion: null, remark: resp.remark })
      }
    }

    saveImmediate(items).catch(() => { /* silent */ })

    // Dispatch EventBus 'adjustment:created'
    dispatchAdjustmentCreated()
  }

  // ─── EventBus: dispatch adjustment:created ───────────────────────────────

  function dispatchAdjustmentCreated(): void {
    eventBus.emit('adjustment:created', {
      wpCode: 'E1',
      source: 'E1-5',
      totalDebit: totalDebit.value,
      totalCredit: totalCredit.value,
      balanced: balanced.value,
      rowCount: rows.value.length,
    })
  }

  // ─── 推送A13: dispatch a13:push-misstatement ────────────────────────────

  function pushToA2(): void {
    eventBus.emit('a13:push-misstatement', {
      wpCode: 'E1',
      source: 'E1-5',
      rows: rows.value.map(r => ({
        description: r.description,
        category: r.category,
        reportItem: r.reportItem,
        accountName: r.accountName,
        noteItem: r.noteItem,
        debit: r.debit,
        credit: r.credit,
        indexNo: r.indexNo,
        note: r.note,
      })),
      totalDebit: totalDebit.value,
      totalCredit: totalCredit.value,
      balanced: balanced.value,
    })
  }

  // ─── Row CRUD ────────────────────────────────────────────────────────────

  /** 末尾新增空白行 */
  function addRow(): void {
    if (isReadonly.value) return
    rows.value = [...rows.value, createEmptyRow()]
    scheduleSave()
  }

  /** 删除行 */
  function removeRow(rowId: string): void {
    if (isReadonly.value) return
    const idx = rows.value.findIndex(r => r.id === rowId)
    if (idx === -1) return
    rows.value = rows.value.filter(r => r.id !== rowId)
    scheduleSave()
  }

  /** 编辑单元格 → debounce 保存 */
  function updateCell(rowId: string, field: string, value: number | string): void {
    if (isReadonly.value) return
    const idx = rows.value.findIndex(r => r.id === rowId)
    if (idx === -1) return

    const row = { ...rows.value[idx] }

    // Update the field
    const numericFields: Array<keyof AdjustmentRow> = ['debit', 'credit']
    const textFields: Array<keyof AdjustmentRow> = [
      'description', 'category', 'reportItem', 'accountName', 'noteItem', 'indexNo', 'note',
    ]

    if (numericFields.includes(field as keyof AdjustmentRow)) {
      ;(row as any)[field] = parseNum(value)
    } else if (textFields.includes(field as keyof AdjustmentRow)) {
      ;(row as any)[field] = String(value)
    }

    // Validate category
    if (field === 'category') {
      const valid: AdjustmentCategory[] = ['报表调整', '账项调整', '其他']
      if (!valid.includes(row.category)) {
        row.category = '账项调整'
      }
    }

    // Update immutably
    const newRows = [...rows.value]
    newRows[idx] = row
    rows.value = newRows

    scheduleSave()
  }

  // ─── Hydration ───────────────────────────────────────────────────────────

  function hydrate(): void {
    isLoading.value = true
    try {
      loadFromResponses()
    } finally {
      isLoading.value = false
    }
  }

  // ─── Cleanup ─────────────────────────────────────────────────────────────

  onBeforeUnmount(() => {
    if (saveTimer) {
      clearTimeout(saveTimer)
      saveTimer = null
      persistToResponses()
    }
  })

  // ─── Return ──────────────────────────────────────────────────────────────

  return {
    rows,
    totalDebit,
    totalCredit,
    balanceDiff,
    balanced,
    isLoading,
    addRow,
    removeRow,
    updateCell,
    pushToA2,
    hydrate,
  }
}
