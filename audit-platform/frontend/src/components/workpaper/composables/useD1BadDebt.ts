/**
 * useD1BadDebt — D1-4 坏账准备明细表 composable
 *
 * Spec: .kiro/specs/d1-adjudication-table/
 * Task: 6.1
 *
 * 职责：
 * - 管理坏账准备按单项/按组合分类的动态行数据
 * - 预设固定父行（按单项计提 + 按组合计提），各自可展开子行
 * - 子行增删（addSubRow / removeSubRow）
 * - 自动计算公式字段（priorAudited / currentUnadjusted / currentAudited）
 * - 小计行 computed（SUM 全部行）
 * - ECL差异警告 computed（与ECL测试结果对比）
 * - 序列化/反序列化（JSON ↔ checklist_responses remark）
 * - Debounce 2s 自动保存
 *
 * Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 8.4, 8.5
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import type { ChecklistItem, ChecklistResponse } from './useD1FormData'
import {
  parseNum,
  calcAuditedAmount,
  calcSubtotal,
  calcBadDebtEndBalance,
} from './useD1FormulaEngine'
import { calcSourceEclProfitLoss, publishGCycleSourceEcl } from './gCycleSourceEcl'

// ─── Types ───────────────────────────────────────────────────────────────────

export type SaveFn = (items: ChecklistItem[]) => Promise<void>

export interface BadDebtRow {
  rowId: string
  category: 'individual' | 'portfolio'  // 按单项 | 按组合
  label: string
  isSubRow: boolean      // 是否为展开子行
  priorUnadjusted: number
  priorAje: number
  priorRje: number
  priorAudited: number   // = prior + aje + rje (自动计算)
  currentProvision: number
  currentRecovery: number
  currentReversal: number
  currentWriteOff: number
  currentOther: number
  currentUnadjusted: number  // 自动计算
  currentAje: number
  currentRje: number
  currentAudited: number     // 自动计算
}

export interface UseD1BadDebtOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  wpId: Ref<string>
  projectId: Ref<string>
  saveImmediate: SaveFn
  isReadonly: Ref<boolean>
  eclTestTotal: Ref<number>  // ECL测试Tab结果，用于差异警告
}

// ─── Constants ───────────────────────────────────────────────────────────────

const INDIVIDUAL_STORAGE_KEY = 'D1-bd-individual-rows'
const PORTFOLIO_STORAGE_KEY = 'D1-bd-portfolio-rows'
const PROCEDURES_KEY = 'D1-bd-procedures'
const NOTE_KEY = 'D1-bd-note'
const CONCLUSION_KEY = 'D1-bd-conclusion'

const DEFAULT_INDIVIDUAL_ROW: BadDebtRow = {
  rowId: 'fixed-individual',
  category: 'individual',
  label: '按单项计提',
  isSubRow: false,
  priorUnadjusted: 0,
  priorAje: 0,
  priorRje: 0,
  priorAudited: 0,
  currentProvision: 0,
  currentRecovery: 0,
  currentReversal: 0,
  currentWriteOff: 0,
  currentOther: 0,
  currentUnadjusted: 0,
  currentAje: 0,
  currentRje: 0,
  currentAudited: 0,
}

const DEFAULT_PORTFOLIO_ROW: BadDebtRow = {
  rowId: 'fixed-portfolio',
  category: 'portfolio',
  label: '按组合计提',
  isSubRow: false,
  priorUnadjusted: 0,
  priorAje: 0,
  priorRje: 0,
  priorAudited: 0,
  currentProvision: 0,
  currentRecovery: 0,
  currentReversal: 0,
  currentWriteOff: 0,
  currentOther: 0,
  currentUnadjusted: 0,
  currentAje: 0,
  currentRje: 0,
  currentAudited: 0,
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

/** 重算行内公式字段 */
function recalcRow(row: BadDebtRow): BadDebtRow {
  const priorAudited = calcAuditedAmount(row.priorUnadjusted, row.priorAje, row.priorRje)
  const currentUnadjusted = calcBadDebtEndBalance(
    priorAudited,
    row.currentProvision,
    row.currentRecovery,
    row.currentReversal,
    row.currentWriteOff,
    row.currentOther,
  )
  const currentAudited = calcAuditedAmount(currentUnadjusted, row.currentAje, row.currentRje)
  return {
    ...row,
    priorAudited,
    currentUnadjusted,
    currentAudited,
  }
}

/** 生成动态子行 ID */
function generateRowId(): string {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return `sub-${crypto.randomUUID()}`
  }
  return `sub-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD1BadDebt(options: UseD1BadDebtOptions) {
  const { allResponses, saveImmediate, isReadonly, eclTestTotal } = options

  // ─── State ───────────────────────────────────────────────────────────────

  const individualRows = ref<BadDebtRow[]>([recalcRow({ ...DEFAULT_INDIVIDUAL_ROW })])
  const portfolioRows = ref<BadDebtRow[]>([recalcRow({ ...DEFAULT_PORTFOLIO_ROW })])
  const auditProcedures = ref('')
  const auditNote = ref('')
  const auditConclusion = ref('')

  // ─── Deserialization (Load from allResponses) ────────────────────────────

  function loadRows(storageKey: string, defaultRow: BadDebtRow, category: 'individual' | 'portfolio'): BadDebtRow[] {
    const response = allResponses.value.get(storageKey)
    const raw = response?.remark
    if (!raw) {
      return [recalcRow({ ...defaultRow })]
    }
    try {
      const parsed = JSON.parse(raw)
      if (!Array.isArray(parsed) || parsed.length === 0) {
        return [recalcRow({ ...defaultRow })]
      }
      const loadedRows: BadDebtRow[] = parsed.map((r: any) => recalcRow({
        rowId: r.rowId || generateRowId(),
        category,
        label: r.label || '',
        isSubRow: Boolean(r.isSubRow),
        priorUnadjusted: parseNum(r.priorUnadjusted),
        priorAje: parseNum(r.priorAje),
        priorRje: parseNum(r.priorRje),
        priorAudited: 0, // will be recalculated
        currentProvision: parseNum(r.currentProvision),
        currentRecovery: parseNum(r.currentRecovery),
        currentReversal: parseNum(r.currentReversal),
        currentWriteOff: parseNum(r.currentWriteOff),
        currentOther: parseNum(r.currentOther),
        currentUnadjusted: 0, // will be recalculated
        currentAje: parseNum(r.currentAje),
        currentRje: parseNum(r.currentRje),
        currentAudited: 0, // will be recalculated
      }))

      // Ensure fixed parent row exists
      const fixedId = category === 'individual' ? 'fixed-individual' : 'fixed-portfolio'
      const hasFixed = loadedRows.some(r => r.rowId === fixedId)
      if (!hasFixed) {
        loadedRows.unshift(recalcRow({ ...defaultRow }))
      }

      return loadedRows
    } catch {
      return [recalcRow({ ...defaultRow })]
    }
  }

  function loadFromResponses(): void {
    individualRows.value = loadRows(INDIVIDUAL_STORAGE_KEY, DEFAULT_INDIVIDUAL_ROW, 'individual')
    portfolioRows.value = loadRows(PORTFOLIO_STORAGE_KEY, DEFAULT_PORTFOLIO_ROW, 'portfolio')
  }

  function loadMetaFromResponses(): void {
    auditProcedures.value = allResponses.value.get(PROCEDURES_KEY)?.remark || ''
    auditNote.value = allResponses.value.get(NOTE_KEY)?.remark || ''
    auditConclusion.value = allResponses.value.get(CONCLUSION_KEY)?.remark || ''
  }

  // Initial load
  loadFromResponses()
  loadMetaFromResponses()

  // Watch allResponses for external changes
  watch(
    () => [
      allResponses.value.get(INDIVIDUAL_STORAGE_KEY)?.remark,
      allResponses.value.get(PORTFOLIO_STORAGE_KEY)?.remark,
    ],
    ([newIndividual, newPortfolio], [oldIndividual, oldPortfolio]) => {
      if (newIndividual !== oldIndividual && newIndividual !== serializeRows(individualRows.value)) {
        individualRows.value = loadRows(INDIVIDUAL_STORAGE_KEY, DEFAULT_INDIVIDUAL_ROW, 'individual')
      }
      if (newPortfolio !== oldPortfolio && newPortfolio !== serializeRows(portfolioRows.value)) {
        portfolioRows.value = loadRows(PORTFOLIO_STORAGE_KEY, DEFAULT_PORTFOLIO_ROW, 'portfolio')
      }
    },
  )

  watch(
    () => [
      allResponses.value.get(PROCEDURES_KEY)?.remark,
      allResponses.value.get(NOTE_KEY)?.remark,
      allResponses.value.get(CONCLUSION_KEY)?.remark,
    ],
    () => {
      loadMetaFromResponses()
    },
  )

  // ─── Serialization ───────────────────────────────────────────────────────

  function serializeRows(rows: BadDebtRow[]): string {
    const data = rows.map(r => ({
      rowId: r.rowId,
      category: r.category,
      label: r.label,
      isSubRow: r.isSubRow,
      priorUnadjusted: r.priorUnadjusted,
      priorAje: r.priorAje,
      priorRje: r.priorRje,
      currentProvision: r.currentProvision,
      currentRecovery: r.currentRecovery,
      currentReversal: r.currentReversal,
      currentWriteOff: r.currentWriteOff,
      currentOther: r.currentOther,
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
      persistToResponses()
    }, 2000)
  }

  function scheduleMetaSave(): void {
    if (metaSaveTimer) clearTimeout(metaSaveTimer)
    metaSaveTimer = setTimeout(() => {
      metaSaveTimer = null
      persistMeta()
    }, 2000)
  }

  function persistToResponses(): void {
    const individualSerialized = serializeRows(individualRows.value)
    const portfolioSerialized = serializeRows(portfolioRows.value)

    const items: ChecklistItem[] = [
      { item_id: INDIVIDUAL_STORAGE_KEY, conclusion: null, remark: individualSerialized },
      { item_id: PORTFOLIO_STORAGE_KEY, conclusion: null, remark: portfolioSerialized },
    ]

    allResponses.value.set(INDIVIDUAL_STORAGE_KEY, items[0])
    allResponses.value.set(PORTFOLIO_STORAGE_KEY, items[1])
    saveImmediate(items)
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

  // ─── Subtotal Row (computed) ─────────────────────────────────────────────

  const subtotalRow: ComputedRef<BadDebtRow> = computed(() => {
    const allRows = [...individualRows.value, ...portfolioRows.value]
    return {
      rowId: 'subtotal',
      category: 'individual' as const,
      label: '小计',
      isSubRow: false,
      priorUnadjusted: calcSubtotal(allRows.map(r => r.priorUnadjusted)),
      priorAje: calcSubtotal(allRows.map(r => r.priorAje)),
      priorRje: calcSubtotal(allRows.map(r => r.priorRje)),
      priorAudited: calcSubtotal(allRows.map(r => r.priorAudited)),
      currentProvision: calcSubtotal(allRows.map(r => r.currentProvision)),
      currentRecovery: calcSubtotal(allRows.map(r => r.currentRecovery)),
      currentReversal: calcSubtotal(allRows.map(r => r.currentReversal)),
      currentWriteOff: calcSubtotal(allRows.map(r => r.currentWriteOff)),
      currentOther: calcSubtotal(allRows.map(r => r.currentOther)),
      currentUnadjusted: calcSubtotal(allRows.map(r => r.currentUnadjusted)),
      currentAje: calcSubtotal(allRows.map(r => r.currentAje)),
      currentRje: calcSubtotal(allRows.map(r => r.currentRje)),
      currentAudited: calcSubtotal(allRows.map(r => r.currentAudited)),
    }
  })

  // ─── ECL Difference & Warning ────────────────────────────────────────────

  const eclDifference: ComputedRef<number> = computed(() => {
    return subtotalRow.value.currentAudited - eclTestTotal.value
  })

  const eclWarning: ComputedRef<string | null> = computed(() => {
    const diff = eclDifference.value
    if (diff === 0) return null
    const sign = diff > 0 ? '+' : '-'
    return `与ECL测试差异: ${sign}${Math.abs(diff)}元`
  })

  // ─── Sub-Row CRUD ────────────────────────────────────────────────────────

  /** 在指定分类的固定父行后面新增一个子行 */
  function addSubRow(category: 'individual' | 'portfolio'): void {
    if (isReadonly.value) return

    const newRow: BadDebtRow = recalcRow({
      rowId: generateRowId(),
      category,
      label: '',
      isSubRow: true,
      priorUnadjusted: 0,
      priorAje: 0,
      priorRje: 0,
      priorAudited: 0,
      currentProvision: 0,
      currentRecovery: 0,
      currentReversal: 0,
      currentWriteOff: 0,
      currentOther: 0,
      currentUnadjusted: 0,
      currentAje: 0,
      currentRje: 0,
      currentAudited: 0,
    })

    if (category === 'individual') {
      individualRows.value = [...individualRows.value, newRow]
    } else {
      portfolioRows.value = [...portfolioRows.value, newRow]
    }
    scheduleSave()
  }

  /** 删除子行（仅允许删除 isSubRow=true 的行） */
  function removeSubRow(rowId: string): void {
    if (isReadonly.value) return

    // Search in individual rows
    const indTarget = individualRows.value.find(r => r.rowId === rowId)
    if (indTarget && indTarget.isSubRow) {
      individualRows.value = individualRows.value.filter(r => r.rowId !== rowId)
      scheduleSave()
      return
    }

    // Search in portfolio rows
    const portTarget = portfolioRows.value.find(r => r.rowId === rowId)
    if (portTarget && portTarget.isSubRow) {
      portfolioRows.value = portfolioRows.value.filter(r => r.rowId !== rowId)
      scheduleSave()
    }
  }

  // ─── Update Cell ─────────────────────────────────────────────────────────

  /** 编辑单元格 → 公式重算 → debounce 保存 */
  function updateCell(rowId: string, field: string, value: number): void {
    if (isReadonly.value) return

    // Try individual rows first
    let idx = individualRows.value.findIndex(r => r.rowId === rowId)
    if (idx !== -1) {
      const row = { ...individualRows.value[idx] }
      applyFieldUpdate(row, field, value)
      const recalculated = recalcRow(row)
      const newRows = [...individualRows.value]
      newRows[idx] = recalculated
      individualRows.value = newRows
      scheduleSave()
      return
    }

    // Try portfolio rows
    idx = portfolioRows.value.findIndex(r => r.rowId === rowId)
    if (idx !== -1) {
      const row = { ...portfolioRows.value[idx] }
      applyFieldUpdate(row, field, value)
      const recalculated = recalcRow(row)
      const newRows = [...portfolioRows.value]
      newRows[idx] = recalculated
      portfolioRows.value = newRows
      scheduleSave()
    }
  }

  function applyFieldUpdate(row: BadDebtRow, field: string, value: number): void {
    const numericFields: Array<keyof BadDebtRow> = [
      'priorUnadjusted', 'priorAje', 'priorRje',
      'currentProvision', 'currentRecovery', 'currentReversal',
      'currentWriteOff', 'currentOther',
      'currentAje', 'currentRje',
    ]
    if (field === 'label') {
      row.label = String(value)
    } else if (numericFields.includes(field as keyof BadDebtRow)) {
      ;(row as any)[field] = parseNum(value)
    }
  }

  // ─── Cleanup ─────────────────────────────────────────────────────────────

  /** 向 G14 广播本期坏账净计提（计入损益） */
  watch(
    () => calcSourceEclProfitLoss(subtotalRow.value.currentProvision, subtotalRow.value.currentReversal),
    (amount) => { publishGCycleSourceEcl('D1', amount) },
    { immediate: true },
  )

  onBeforeUnmount(() => {
    if (saveTimer) {
      clearTimeout(saveTimer)
      persistToResponses()
    }
    if (metaSaveTimer) {
      clearTimeout(metaSaveTimer)
      persistMeta()
    }
  })

  // ─── Return ──────────────────────────────────────────────────────────────

  return {
    individualRows,
    portfolioRows,
    subtotalRow,
    eclDifference,
    eclWarning,
    auditProcedures,
    auditNote,
    auditConclusion,
    addSubRow,
    removeSubRow,
    updateCell,
    saveAuditProcedures,
    saveAuditNote,
    saveAuditConclusion,
  }
}
