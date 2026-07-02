/**
 * useD1RelatedPartyCheck — D1-11 关联方关系及交易检查表 composable
 *
 * Spec: .kiro/specs/d1-inspection-check/
 * Task: 4.1
 *
 * 职责：
 * - 管理 13 列关联方检查表动态行 CRUD
 * - 逐行公式计算：F = computeClosingBalance(C, D, E)；H = computeBookValue(F, G)
 * - 合计行 Row14 computed（SUM C/D/E/F/G/H/K 七列）
 * - 跨Spec核对：审定表期末余额 → adjClosingBalance computed
 * - reconDifference computed（合计F - 审定表期末）
 * - 审计说明/结论（auditNote / auditConclusion）
 * - 动态行 CRUD（addRow / removeRow / updateRow）
 * - 序列化/反序列化（JSON ↔ checklist_responses remark），debounce 2s 自动保存
 * - select 类字段立即保存
 * - exportTemplate / exportData / importData 导入导出接口
 * - respect isReadonly
 *
 * 跨 Spec 数据契约：
 *   从 allResponses 读取 `D1-adj-notes-receivable-current-audited`（审定表期末余额）
 *   若 key 不存在 → adjDataLoaded = false, adjClosingBalance = 0
 *
 * Requirements: 4.1-4.6, 5.1-5.5, 6.1-6.5, 15.2, 15.6, 15.8
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import type { ChecklistItem, ChecklistResponse } from './useD1FormData'
import {
  sumColumn,
  computeClosingBalance,
  computeBookValue,
  type RelatedPartyRow,
} from './d1InspectionFormulas'
import { useD1ImportExport, type ImportResult } from './useD1ImportExport'
import http from '@/utils/http'

// ─── Types ───────────────────────────────────────────────────────────────────

export type SaveFn = (items: ChecklistItem[]) => Promise<void>
export type DebounceSaveFn = (item: ChecklistItem) => void

export interface UseD1RelatedPartyCheckOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  wpId: Ref<string>
  projectId: Ref<string>
  saveImmediate: SaveFn
  saveDebouncedText: DebounceSaveFn
  isReadonly: Ref<boolean>
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ROWS_KEY = 'D1-rp-rows'
const NOTE_KEY = 'D1-rp-note'
const CONCLUSION_KEY = 'D1-rp-conclusion'

/** 跨Spec审定表期末余额 key（来自 d1-adjudication-table Spec） */
const CROSS_SPEC_ADJ_KEY = 'D1-adj-notes-receivable-current-audited'

/** RelatedPartyRow 数值字段 */
const NUMERIC_FIELDS: Array<keyof RelatedPartyRow> = [
  'openingBalance',
  'debitOccurrence',
  'creditOccurrence',
  'closingBalance',
  'badDebtProvision',
  'bookValue',
  'postHonored',
]

/** RelatedPartyRow 字符串字段 */
const STRING_FIELDS: Array<keyof RelatedPartyRow> = [
  'partyName',
  'relationship',
  'agingInfo',
  'transactionNature',
  'indexRef',
  'remark',
]

/** select类字段（立即保存） */
const SELECT_FIELDS: Array<keyof RelatedPartyRow> = ['relationship']

// ─── Helpers ─────────────────────────────────────────────────────────────────

function generateRowId(): string {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID()
  }
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function parseNum(val: any): number {
  const n = Number(val)
  return Number.isFinite(n) ? n : 0
}

/** 空行工厂 */
export function emptyRelatedPartyRow(): RelatedPartyRow {
  return {
    id: generateRowId(),
    partyName: '',
    relationship: '',
    openingBalance: 0,
    debitOccurrence: 0,
    creditOccurrence: 0,
    closingBalance: 0,
    badDebtProvision: 0,
    bookValue: 0,
    agingInfo: '',
    transactionNature: '',
    postHonored: 0,
    indexRef: '',
    remark: '',
  }
}

/** 反序列化单行（含公式重算） */
function deserializeRow(raw: any): RelatedPartyRow {
  const row = emptyRelatedPartyRow()
  if (raw && typeof raw.id === 'string' && raw.id) row.id = raw.id
  for (const f of STRING_FIELDS) {
    if (raw && typeof raw[f] === 'string') (row as any)[f] = raw[f]
  }
  for (const f of NUMERIC_FIELDS) {
    if (raw && raw[f] !== undefined) (row as any)[f] = parseNum(raw[f])
  }
  // 重算公式列
  row.closingBalance = computeClosingBalance(row.openingBalance, row.debitOccurrence, row.creditOccurrence)
  row.bookValue = computeBookValue(row.closingBalance, row.badDebtProvision)
  return row
}

/** 序列化单行 */
function serializeRow(row: RelatedPartyRow): any {
  const data: any = { id: row.id }
  for (const f of STRING_FIELDS) data[f] = (row as any)[f]
  for (const f of NUMERIC_FIELDS) data[f] = (row as any)[f]
  return data
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD1RelatedPartyCheck(options: UseD1RelatedPartyCheckOptions) {
  const { allResponses, wpId, projectId: _projectId, saveImmediate, saveDebouncedText, isReadonly } = options

  // ─── State ───────────────────────────────────────────────────────────────

  const rows = ref<RelatedPartyRow[]>([])
  const auditNote = ref<string>('')
  const auditConclusion = ref<string>('')

  // ─── Deserialization (Load from allResponses) ────────────────────────────

  function loadRows(): RelatedPartyRow[] {
    const raw = allResponses.value.get(ROWS_KEY)?.remark
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
      if (newRows !== undefined && newRows !== serializeRows()) {
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

  function serializeRows(): string {
    return JSON.stringify(rows.value.map(serializeRow))
  }

  // ─── Save Helpers ────────────────────────────────────────────────────────

  let saveTimer: ReturnType<typeof setTimeout> | null = null

  function scheduleSave(): void {
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = setTimeout(() => {
      saveTimer = null
      persistRows()
    }, 2000)
  }

  /** 持久化行数据到 allResponses + API */
  function persistRows(): void {
    const item: ChecklistItem = {
      item_id: ROWS_KEY,
      conclusion: null,
      remark: serializeRows(),
    }
    allResponses.value.set(ROWS_KEY, item)
    saveImmediate([item])
  }

  /** 立即持久化行（select字段触发） */
  function persistRowsImmediate(): void {
    const item: ChecklistItem = {
      item_id: ROWS_KEY,
      conclusion: null,
      remark: serializeRows(),
    }
    allResponses.value.set(ROWS_KEY, item)
    saveImmediate([item])
  }

  // ─── Dynamic Row CRUD ────────────────────────────────────────────────────

  /** 添加空行 */
  function addRow(): void {
    if (isReadonly.value) return
    const newRow = emptyRelatedPartyRow()
    rows.value = [...rows.value, newRow]
    scheduleSave()
  }

  /** 按 id 删除行 */
  function removeRow(id: string): void {
    if (isReadonly.value) return
    const idx = rows.value.findIndex((r) => r.id === id)
    if (idx === -1) return
    rows.value = rows.value.filter((r) => r.id !== id)
    scheduleSave()
  }

  /** 更新指定行的某个字段（含公式重算 F 和 H） */
  function updateRow(id: string, field: keyof RelatedPartyRow, value: any): void {
    if (isReadonly.value) return
    const idx = rows.value.findIndex((r) => r.id === id)
    if (idx === -1) return

    const row = { ...rows.value[idx] }

    if (NUMERIC_FIELDS.includes(field)) {
      // F 和 H 是公式列，不允许直接赋值
      if (field === 'closingBalance' || field === 'bookValue') return
      ;(row as any)[field] = parseNum(value)
    } else if (STRING_FIELDS.includes(field) || field === 'id') {
      ;(row as any)[field] = String(value ?? '')
    } else {
      return
    }

    // 重算公式列 F = C + D - E；H = F - G
    row.closingBalance = computeClosingBalance(row.openingBalance, row.debitOccurrence, row.creditOccurrence)
    row.bookValue = computeBookValue(row.closingBalance, row.badDebtProvision)

    const newRows = [...rows.value]
    newRows[idx] = row
    rows.value = newRows

    // select类字段立即保存，其余 debounce 2s
    if (SELECT_FIELDS.includes(field)) {
      persistRowsImmediate()
    } else {
      scheduleSave()
    }
  }

  // ─── Computed: 合计行 Row14（SUM 7列） ───────────────────────────────────

  const summaryRow: ComputedRef<{
    openingBalance: number
    debitOccurrence: number
    creditOccurrence: number
    closingBalance: number
    badDebtProvision: number
    bookValue: number
    postHonored: number
  }> = computed(() => ({
    openingBalance: sumColumn(rows.value, 'openingBalance'),
    debitOccurrence: sumColumn(rows.value, 'debitOccurrence'),
    creditOccurrence: sumColumn(rows.value, 'creditOccurrence'),
    closingBalance: sumColumn(rows.value, 'closingBalance'),
    badDebtProvision: sumColumn(rows.value, 'badDebtProvision'),
    bookValue: sumColumn(rows.value, 'bookValue'),
    postHonored: sumColumn(rows.value, 'postHonored'),
  }))

  // ─── Computed: 跨Spec审定表期末余额 ──────────────────────────────────────

  const adjClosingBalance: ComputedRef<number> = computed(() => {
    const raw = allResponses.value.get(CROSS_SPEC_ADJ_KEY)?.remark
    if (raw == null) return 0
    return parseNum(raw)
  })

  const adjDataLoaded: ComputedRef<boolean> = computed(() => {
    return allResponses.value.has(CROSS_SPEC_ADJ_KEY)
  })

  // ─── Computed: 核对差异 ──────────────────────────────────────────────────

  const reconDifference: ComputedRef<number> = computed(() => {
    return summaryRow.value.closingBalance - adjClosingBalance.value
  })

  // ─── 审计说明/结论 ───────────────────────────────────────────────────────

  function saveAuditNote(text: string): void {
    if (isReadonly.value) return
    auditNote.value = text
    const item: ChecklistItem = {
      item_id: NOTE_KEY,
      conclusion: null,
      remark: text || null,
    }
    allResponses.value.set(NOTE_KEY, item)
    saveDebouncedText(item)
  }

  function saveAuditConclusion(text: string): void {
    if (isReadonly.value) return
    auditConclusion.value = text
    const item: ChecklistItem = {
      item_id: CONCLUSION_KEY,
      conclusion: null,
      remark: text || null,
    }
    allResponses.value.set(CONCLUSION_KEY, item)
    saveDebouncedText(item)
  }

  // ─── 导入导出接口（委托 useD1ImportExport 共享模块） ──────────────────────

  const {
    exportTemplate: _exportTemplate,
    exportData: _exportData,
  } = useD1ImportExport({ wpId, sheetCode: 'D1-11', sheetLabel: '关联方检查' })

  const exportTemplate = _exportTemplate
  const exportData = _exportData

  /** 导入 xlsx 数据（包装共享模块，额外处理行回写） */
  async function importData(file: File): Promise<ImportResult> {
    const formData = new FormData()
    formData.append('file', file)
    try {
      const res = await http.post(
        `/api/workpapers/${wpId.value}/d1-import-export/import-data`,
        formData,
        {
          params: { sheet: 'D1-11' },
          headers: { 'Content-Type': 'multipart/form-data' },
        },
      )
      const data = res.data?.data ?? res.data
      if (data?.rows && Array.isArray(data.rows)) {
        rows.value = data.rows.map((r: any) => deserializeRow(r))
        persistRowsImmediate()
      }
      return {
        success: true,
        rowCount: data?.row_count ?? rows.value.length,
        fieldCount: data?.field_count ?? 0,
      }
    } catch (err: any) {
      const msg = err?.response?.data?.message || err?.message || '导入失败'
      return {
        success: false,
        rowCount: 0,
        fieldCount: 0,
        errors: [msg],
      }
    }
  }

  // ─── Cleanup ─────────────────────────────────────────────────────────────

  onBeforeUnmount(() => {
    if (saveTimer) {
      clearTimeout(saveTimer)
      persistRows()
    }
  })

  // ─── Return ──────────────────────────────────────────────────────────────

  return {
    // 动态行
    rows,
    addRow,
    removeRow,
    updateRow,

    // 公式计算（暴露纯函数供外部调用/测试）
    computeClosingBalance,
    computeBookValue,

    // 合计行 Row14
    summaryRow,

    // 核对区
    adjClosingBalance,
    adjDataLoaded,
    reconDifference,

    // 审计说明/结论
    auditNote,
    auditConclusion,
    saveAuditNote,
    saveAuditConclusion,

    // 导入导出
    exportTemplate,
    exportData,
    importData,
  }
}

export default useD1RelatedPartyCheck
