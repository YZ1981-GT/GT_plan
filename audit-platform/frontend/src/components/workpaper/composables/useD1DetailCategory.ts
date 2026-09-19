/**
 * useD1DetailCategory — D1-2 原值明细表(按类别) composable
 *
 * Spec: .kiro/specs/d1-adjudication-table/
 * Task: 4.1
 *
 * 职责：
 * - 管理按票据种类分类的动态行数据
 * - 预设固定行（银行承兑汇票 + 商业承兑汇票）
 * - 动态行 CRUD（添加/删除/编辑）
 * - 自动计算公式字段（priorAudited / currentUnadjusted / currentAudited）
 * - 小计行 computed（SUM 所有明细行）
 * - 序列化/反序列化（JSON ↔ checklist_responses remark）
 * - Debounce 2s 自动保存
 *
 * Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 8.2, 8.5, 8.7
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import type { ChecklistItem, ChecklistResponse } from './useD1FormData'
import {
  parseNum,
  calcAuditedAmount,
  calcSubtotal,
  calcCurrentUnadjusted,
} from './useD1FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export type SaveFn = (items: ChecklistItem[]) => Promise<void>

export interface CategoryRow {
  rowId: string          // 'fixed-bank' | 'fixed-commercial' | 'dynamic-{uuid}'
  category: string       // 票据种类名称
  isFixed: boolean       // 固定行不可删除
  priorUnadjusted: number
  priorAje: number
  priorRje: number
  priorAudited: number   // = prior + aje + rje (自动计算)
  currentIncrease: number
  currentDecrease: number
  currentUnadjusted: number  // 自动计算: = priorAudited + currentIncrease - currentDecrease
  currentAje: number
  currentRje: number
  currentAudited: number // = currentUnadjusted + aje + rje (自动计算)
}

export interface UseD1DetailCategoryOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  wpId: Ref<string>
  projectId: Ref<string>
  saveImmediate: SaveFn
  isReadonly: Ref<boolean>
}

// ─── Constants ───────────────────────────────────────────────────────────────

const STORAGE_KEY = 'D1-cat-rows'
const PROCEDURES_KEY = 'D1-cat-procedures'
const NOTE_KEY = 'D1-cat-note'
const CONCLUSION_KEY = 'D1-cat-conclusion'

const DEFAULT_FIXED_ROWS: CategoryRow[] = [
  {
    rowId: 'fixed-bank',
    category: '银行承兑汇票',
    isFixed: true,
    priorUnadjusted: 0,
    priorAje: 0,
    priorRje: 0,
    priorAudited: 0,
    currentIncrease: 0,
    currentDecrease: 0,
    currentUnadjusted: 0,
    currentAje: 0,
    currentRje: 0,
    currentAudited: 0,
  },
  {
    rowId: 'fixed-commercial',
    category: '商业承兑汇票',
    isFixed: true,
    priorUnadjusted: 0,
    priorAje: 0,
    priorRje: 0,
    priorAudited: 0,
    currentIncrease: 0,
    currentDecrease: 0,
    currentUnadjusted: 0,
    currentAje: 0,
    currentRje: 0,
    currentAudited: 0,
  },
]

// ─── Helpers ─────────────────────────────────────────────────────────────────

/** 重算行内公式字段 */
function recalcRow(row: CategoryRow): CategoryRow {
  const priorAudited = calcAuditedAmount(row.priorUnadjusted, row.priorAje, row.priorRje)
  const currentUnadjusted = calcCurrentUnadjusted(priorAudited, row.currentIncrease, row.currentDecrease)
  const currentAudited = calcAuditedAmount(currentUnadjusted, row.currentAje, row.currentRje)
  return {
    ...row,
    priorAudited,
    currentUnadjusted,
    currentAudited,
  }
}

/** 生成动态行 ID */
function generateRowId(): string {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return `dynamic-${crypto.randomUUID()}`
  }
  // Fallback for environments without crypto.randomUUID
  return `dynamic-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD1DetailCategory(options: UseD1DetailCategoryOptions) {
  const { allResponses, saveImmediate, isReadonly } = options

  // ─── State ───────────────────────────────────────────────────────────────

  const rows = ref<CategoryRow[]>([...DEFAULT_FIXED_ROWS.map(r => ({ ...r }))])
  const auditProcedures = ref<string>('')
  const auditNote = ref<string>('')
  const auditConclusion = ref<string>('')

  // ─── Deserialization (Load from allResponses) ────────────────────────────

  function loadMetaFromResponses(): void {
    auditProcedures.value = allResponses.value.get(PROCEDURES_KEY)?.remark ?? ''
    auditNote.value = allResponses.value.get(NOTE_KEY)?.remark ?? ''
    auditConclusion.value = allResponses.value.get(CONCLUSION_KEY)?.remark ?? ''
  }

  function loadFromResponses(): void {
    loadMetaFromResponses()
    const response = allResponses.value.get(STORAGE_KEY)
    const raw = response?.remark
    if (!raw) {
      // No stored data, use default fixed rows
      rows.value = DEFAULT_FIXED_ROWS.map(r => recalcRow({ ...r }))
      return
    }
    try {
      const parsed = JSON.parse(raw)
      if (!Array.isArray(parsed) || parsed.length === 0) {
        rows.value = DEFAULT_FIXED_ROWS.map(r => recalcRow({ ...r }))
        return
      }
      // Parse and ensure all numeric fields are proper numbers
      const loadedRows: CategoryRow[] = parsed.map((r: any) => recalcRow({
        rowId: r.rowId || generateRowId(),
        category: r.category || '',
        isFixed: Boolean(r.isFixed),
        priorUnadjusted: parseNum(r.priorUnadjusted),
        priorAje: parseNum(r.priorAje),
        priorRje: parseNum(r.priorRje),
        priorAudited: 0, // will be recalculated
        currentIncrease: parseNum(r.currentIncrease),
        currentDecrease: parseNum(r.currentDecrease),
        currentUnadjusted: 0, // will be recalculated
        currentAje: parseNum(r.currentAje),
        currentRje: parseNum(r.currentRje),
        currentAudited: 0, // will be recalculated
      }))

      // Ensure fixed rows are present
      const hasBank = loadedRows.some(r => r.rowId === 'fixed-bank')
      const hasCommercial = loadedRows.some(r => r.rowId === 'fixed-commercial')
      if (!hasBank) {
        loadedRows.unshift(recalcRow({ ...DEFAULT_FIXED_ROWS[0] }))
      }
      if (!hasCommercial) {
        const bankIdx = loadedRows.findIndex(r => r.rowId === 'fixed-bank')
        loadedRows.splice(bankIdx + 1, 0, recalcRow({ ...DEFAULT_FIXED_ROWS[1] }))
      }

      rows.value = loadedRows
    } catch {
      // JSON parse failed, fall back to defaults
      rows.value = DEFAULT_FIXED_ROWS.map(r => recalcRow({ ...r }))
    }
  }

  // Initial load
  loadFromResponses()

  // Watch allResponses for external changes (e.g., from other tabs or OO sync)
  watch(
    () => [
      allResponses.value.get(STORAGE_KEY)?.remark,
      allResponses.value.get(PROCEDURES_KEY)?.remark,
      allResponses.value.get(NOTE_KEY)?.remark,
      allResponses.value.get(CONCLUSION_KEY)?.remark,
    ],
    ([newRows, newProcedures, newNote, newConclusion], [oldRows, oldProcedures, oldNote, oldConclusion]) => {
      if (newProcedures !== oldProcedures && newProcedures !== auditProcedures.value) {
        auditProcedures.value = newProcedures ?? ''
      }
      if (newNote !== oldNote && newNote !== auditNote.value) {
        auditNote.value = newNote ?? ''
      }
      if (newConclusion !== oldConclusion && newConclusion !== auditConclusion.value) {
        auditConclusion.value = newConclusion ?? ''
      }
      if (newRows !== oldRows && newRows !== serializeRows()) {
        const response = allResponses.value.get(STORAGE_KEY)
        const raw = response?.remark
        if (!raw) {
          rows.value = DEFAULT_FIXED_ROWS.map(r => recalcRow({ ...r }))
          return
        }
        try {
          const parsed = JSON.parse(raw)
          if (!Array.isArray(parsed) || parsed.length === 0) {
            rows.value = DEFAULT_FIXED_ROWS.map(r => recalcRow({ ...r }))
            return
          }
          const loadedRows: CategoryRow[] = parsed.map((r: any) => recalcRow({
            rowId: r.rowId || generateRowId(),
            category: r.category || '',
            isFixed: Boolean(r.isFixed),
            priorUnadjusted: parseNum(r.priorUnadjusted),
            priorAje: parseNum(r.priorAje),
            priorRje: parseNum(r.priorRje),
            priorAudited: 0,
            currentIncrease: parseNum(r.currentIncrease),
            currentDecrease: parseNum(r.currentDecrease),
            currentUnadjusted: 0,
            currentAje: parseNum(r.currentAje),
            currentRje: parseNum(r.currentRje),
            currentAudited: 0,
          }))
          const hasBank = loadedRows.some(r => r.rowId === 'fixed-bank')
          const hasCommercial = loadedRows.some(r => r.rowId === 'fixed-commercial')
          if (!hasBank) loadedRows.unshift(recalcRow({ ...DEFAULT_FIXED_ROWS[0] }))
          if (!hasCommercial) {
            const bankIdx = loadedRows.findIndex(r => r.rowId === 'fixed-bank')
            loadedRows.splice(bankIdx + 1, 0, recalcRow({ ...DEFAULT_FIXED_ROWS[1] }))
          }
          rows.value = loadedRows
        } catch {
          rows.value = DEFAULT_FIXED_ROWS.map(r => recalcRow({ ...r }))
        }
      }
    },
  )

  // ─── Serialization ───────────────────────────────────────────────────────

  function serializeRows(): string {
    // Only serialize user-editable fields (computed fields will be recalculated on load)
    const data = rows.value.map(r => ({
      rowId: r.rowId,
      category: r.category,
      isFixed: r.isFixed,
      priorUnadjusted: r.priorUnadjusted,
      priorAje: r.priorAje,
      priorRje: r.priorRje,
      currentIncrease: r.currentIncrease,
      currentDecrease: r.currentDecrease,
      currentAje: r.currentAje,
      currentRje: r.currentRje,
    }))
    return JSON.stringify(data)
  }

  // ─── Debounce Save ───────────────────────────────────────────────────────

  let saveTimer: ReturnType<typeof setTimeout> | null = null
  let metaSaveTimer: ReturnType<typeof setTimeout> | null = null

  function scheduleSave(): void {
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = setTimeout(() => {
      saveTimer = null
      persistRows()
    }, 2000)
  }

  function scheduleMetaSave(): void {
    if (metaSaveTimer) clearTimeout(metaSaveTimer)
    metaSaveTimer = setTimeout(() => {
      metaSaveTimer = null
      persistMeta()
    }, 2000)
  }

  function persistRows(): void {
    const serialized = serializeRows()
    const item: ChecklistItem = {
      item_id: STORAGE_KEY,
      conclusion: null,
      remark: serialized,
    }
    allResponses.value.set(STORAGE_KEY, item)
    saveImmediate([item])
  }

  function persistMeta(): void {
    const items: ChecklistItem[] = [
      { item_id: PROCEDURES_KEY, conclusion: null, remark: auditProcedures.value || null },
      { item_id: NOTE_KEY, conclusion: null, remark: auditNote.value || null },
      { item_id: CONCLUSION_KEY, conclusion: null, remark: auditConclusion.value || null },
    ]
    for (const item of items) {
      allResponses.value.set(item.item_id, item)
    }
    saveImmediate(items)
  }

  function persistToResponses(): void {
    persistRows()
  }

  // ─── Subtotal Row (computed) ─────────────────────────────────────────────

  const subtotalRow: ComputedRef<CategoryRow> = computed(() => {
    const currentRows = rows.value
    return {
      rowId: 'subtotal',
      category: '小计',
      isFixed: true,
      priorUnadjusted: calcSubtotal(currentRows.map(r => r.priorUnadjusted)),
      priorAje: calcSubtotal(currentRows.map(r => r.priorAje)),
      priorRje: calcSubtotal(currentRows.map(r => r.priorRje)),
      priorAudited: calcSubtotal(currentRows.map(r => r.priorAudited)),
      currentIncrease: calcSubtotal(currentRows.map(r => r.currentIncrease)),
      currentDecrease: calcSubtotal(currentRows.map(r => r.currentDecrease)),
      currentUnadjusted: calcSubtotal(currentRows.map(r => r.currentUnadjusted)),
      currentAje: calcSubtotal(currentRows.map(r => r.currentAje)),
      currentRje: calcSubtotal(currentRows.map(r => r.currentRje)),
      currentAudited: calcSubtotal(currentRows.map(r => r.currentAudited)),
    }
  })

  // ─── Row CRUD ────────────────────────────────────────────────────────────

  /** 在小计行上方新增空行 */
  function addRow(): void {
    if (isReadonly.value) return
    const newRow: CategoryRow = recalcRow({
      rowId: generateRowId(),
      category: '',
      isFixed: false,
      priorUnadjusted: 0,
      priorAje: 0,
      priorRje: 0,
      priorAudited: 0,
      currentIncrease: 0,
      currentDecrease: 0,
      currentUnadjusted: 0,
      currentAje: 0,
      currentRje: 0,
      currentAudited: 0,
    })
    rows.value = [...rows.value, newRow]
    scheduleSave()
  }

  /** 删除动态行（仅允许删除 isFixed=false 的行） */
  function removeRow(rowId: string): void {
    if (isReadonly.value) return
    const target = rows.value.find(r => r.rowId === rowId)
    if (!target || target.isFixed) return
    rows.value = rows.value.filter(r => r.rowId !== rowId)
    scheduleSave()
  }

  /** 编辑单元格 → 公式重算 → debounce 保存 */
  function updateCell(rowId: string, field: string, value: number | string): void {
    if (isReadonly.value) return
    const idx = rows.value.findIndex(r => r.rowId === rowId)
    if (idx === -1) return

    const row = { ...rows.value[idx] }

    // Update the field
    if (field === 'category') {
      row.category = String(value)
    } else {
      // Numeric field
      const numericFields: Array<keyof CategoryRow> = [
        'priorUnadjusted', 'priorAje', 'priorRje',
        'currentIncrease', 'currentDecrease',
        'currentAje', 'currentRje',
      ]
      if (numericFields.includes(field as keyof CategoryRow)) {
        ;(row as any)[field] = parseNum(value)
      }
    }

    // Recalculate computed fields
    const recalculated = recalcRow(row)

    // Update the rows array immutably
    const newRows = [...rows.value]
    newRows[idx] = recalculated
    rows.value = newRows

    scheduleSave()
  }

  // ─── Cleanup ─────────────────────────────────────────────────────────────

  function saveAuditProcedures(text: string): void {
    if (isReadonly.value) return
    auditProcedures.value = text
    scheduleMetaSave()
  }

  function saveAuditNote(text: string): void {
    if (isReadonly.value) return
    auditNote.value = text
    scheduleMetaSave()
  }

  function saveAuditConclusion(text: string): void {
    if (isReadonly.value) return
    auditConclusion.value = text
    scheduleMetaSave()
  }

  onBeforeUnmount(() => {
    if (saveTimer) {
      clearTimeout(saveTimer)
      persistRows()
    }
    if (metaSaveTimer) {
      clearTimeout(metaSaveTimer)
      persistMeta()
    }
  })

  // ─── Return ──────────────────────────────────────────────────────────────

  return {
    rows,
    subtotalRow,
    auditProcedures,
    auditNote,
    auditConclusion,
    addRow,
    removeRow,
    updateCell,
    saveAuditProcedures,
    saveAuditNote,
    saveAuditConclusion,
  }
}
