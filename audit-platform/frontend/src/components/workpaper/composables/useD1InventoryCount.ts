/**
 * useD1InventoryCount — D1-10 应收票据监盘表 composable
 *
 * Spec: .kiro/specs/d1-inspection-check/
 * Task: 3.1
 *
 * 职责：
 * - 管理 15 列监盘日结存票据宽表动态行 CRUD
 * - 合计行 computed（H21 = SUM rows.amount）
 * - 核对区 computed（监盘合计 vs 账面余额 → 差异）
 *   - 账面余额通过纯 computed 从同一 allResponses Map 跨 Spec 取 D1-adj-* 数据
 * - 差异检测 computed（hasDifference）
 * - 审计说明/结论（auditNote / auditConclusion）
 * - 动态行 CRUD（addRow / removeRow / updateRow）
 * - 序列化/反序列化（JSON ↔ checklist_responses remark），debounce 2s 自动保存
 * - select 类字段立即保存
 * - exportTemplate / exportData / importData 导入导出接口（stub 调后端 API）
 * - respect isReadonly（只读时所有写操作 no-op）
 *
 * 跨 Spec 数据契约：
 *   从 allResponses 读取 `D1-adj-notes-receivable-current-audited`（审定表期末余额）
 *   若 key 不存在 → bookBalanceLoaded = false, bookBalance = 0
 *
 * Requirements: 1.1-1.6, 2.1-2.5, 3.1-3.5, 15.1, 15.5, 15.7
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import type { ChecklistItem, ChecklistResponse } from './useD1FormData'
import { sumColumn, type InventoryCountRow } from './d1InspectionFormulas'
import { useD1ImportExport, type ImportResult } from './useD1ImportExport'
import http from '@/utils/http'

// ─── Types ───────────────────────────────────────────────────────────────────

export type SaveFn = (items: ChecklistItem[]) => Promise<void>
export type DebounceSaveFn = (item: ChecklistItem) => void

/** 核对区聚合 */
export interface InventoryReconArea {
  sumAmount: number           // A25: 监盘日票据结存合计 (=SUM H列)
  bookBalance: number         // D25: 账面应收票据余额 (跨sheet)
  differenceAmount: number    // F25: 差异金额 (=A25-D25)
  explanation: string         // I25: 监盘差异说明
  conclusion: string          // L25: 审计结论
  indexRef: string            // N25: 索引号
}

export interface UseD1InventoryCountOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  wpId: Ref<string>
  projectId: Ref<string>
  saveImmediate: SaveFn
  saveDebouncedText: DebounceSaveFn
  isReadonly: Ref<boolean>
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ROWS_KEY = 'D1-inventory-rows'
const RECON_EXPLANATION_KEY = 'D1-inventory-recon-explanation'
const RECON_CONCLUSION_KEY = 'D1-inventory-recon-conclusion'
const RECON_INDEX_KEY = 'D1-inventory-recon-indexRef'
const NOTE_KEY = 'D1-inventory-note'
const CONCLUSION_KEY = 'D1-inventory-conclusion'

/** 跨Spec审定表期末余额 key（来自 d1-adjudication-table Spec） */
const CROSS_SPEC_BOOK_BALANCE_KEY = 'D1-adj-notes-receivable-current-audited'

/** InventoryCountRow 数值字段 */
const NUMERIC_FIELDS: Array<keyof InventoryCountRow> = ['amount']

/** InventoryCountRow 字符串字段 */
const STRING_FIELDS: Array<keyof InventoryCountRow> = [
  'noteType',
  'noteNo',
  'issueDate',
  'drawer',
  'acceptor',
  'maturityDate',
  'predecessor',
  'receiveDate',
  'endorseDate',
  'endorsee',
  'noteStatus',
  'hasDifference',
  'differenceReason',
  'indexRef',
]

/** select类字段（立即保存） */
const SELECT_FIELDS: Array<keyof InventoryCountRow> = [
  'noteType',
  'noteStatus',
  'hasDifference',
]

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
export function emptyInventoryCountRow(): InventoryCountRow {
  return {
    id: generateRowId(),
    noteType: '',
    noteNo: '',
    issueDate: '',
    drawer: '',
    acceptor: '',
    amount: 0,
    maturityDate: '',
    predecessor: '',
    receiveDate: '',
    endorseDate: '',
    endorsee: '',
    noteStatus: '',
    hasDifference: '',
    differenceReason: '',
    indexRef: '',
  }
}

/** 反序列化单行 */
function deserializeRow(raw: any): InventoryCountRow {
  const row = emptyInventoryCountRow()
  if (raw && typeof raw.id === 'string' && raw.id) row.id = raw.id
  for (const f of STRING_FIELDS) {
    if (raw && typeof raw[f] === 'string') (row as any)[f] = raw[f]
  }
  for (const f of NUMERIC_FIELDS) {
    if (raw && raw[f] !== undefined) (row as any)[f] = parseNum(raw[f])
  }
  return row
}

/** 序列化单行 */
function serializeRow(row: InventoryCountRow): any {
  const data: any = { id: row.id }
  for (const f of STRING_FIELDS) data[f] = (row as any)[f]
  for (const f of NUMERIC_FIELDS) data[f] = (row as any)[f]
  return data
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD1InventoryCount(options: UseD1InventoryCountOptions) {
  const { allResponses, wpId, projectId: _projectId, saveImmediate, saveDebouncedText, isReadonly } = options
  // _projectId reserved for future cross-workpaper API calls (e.g. loadSubWorkpaperData)

  // ─── State ───────────────────────────────────────────────────────────────

  const rows = ref<InventoryCountRow[]>([])
  const auditNote = ref<string>('')
  const auditConclusion = ref<string>('')

  // ─── Deserialization (Load from allResponses) ────────────────────────────

  function loadRows(): InventoryCountRow[] {
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
    const newRow = emptyInventoryCountRow()
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

  /** 更新指定行的某个字段 */
  function updateRow(id: string, field: keyof InventoryCountRow, value: any): void {
    if (isReadonly.value) return
    const idx = rows.value.findIndex((r) => r.id === id)
    if (idx === -1) return

    const row = { ...rows.value[idx] }
    if (NUMERIC_FIELDS.includes(field)) {
      ;(row as any)[field] = parseNum(value)
    } else if (STRING_FIELDS.includes(field) || field === 'id') {
      ;(row as any)[field] = String(value ?? '')
    } else {
      return
    }

    const newRows = [...rows.value]
    newRows[idx] = row
    rows.value = newRows

    // select类字段立即保存，金额/文本字段debounce 2s
    if (SELECT_FIELDS.includes(field)) {
      persistRowsImmediate()
    } else {
      scheduleSave()
    }
  }

  // ─── Computed: 合计行 H21 ────────────────────────────────────────────────

  const sumAmount: ComputedRef<number> = computed(() => {
    return sumColumn(rows.value, 'amount')
  })

  // ─── Computed: 跨Spec账面余额 ────────────────────────────────────────────

  const bookBalance: ComputedRef<number> = computed(() => {
    const raw = allResponses.value.get(CROSS_SPEC_BOOK_BALANCE_KEY)?.remark
    if (raw == null) return 0
    return parseNum(raw)
  })

  const bookBalanceLoaded: ComputedRef<boolean> = computed(() => {
    return allResponses.value.has(CROSS_SPEC_BOOK_BALANCE_KEY)
  })

  // ─── Computed: 差异 ──────────────────────────────────────────────────────

  const differenceAmount: ComputedRef<number> = computed(() => {
    return sumAmount.value - bookBalance.value
  })

  const hasDifference: ComputedRef<boolean> = computed(() => {
    return differenceAmount.value !== 0
  })

  // ─── Computed: 核对区聚合 ────────────────────────────────────────────────

  const reconArea: ComputedRef<InventoryReconArea> = computed(() => {
    return {
      sumAmount: sumAmount.value,
      bookBalance: bookBalance.value,
      differenceAmount: differenceAmount.value,
      explanation: allResponses.value.get(RECON_EXPLANATION_KEY)?.remark ?? '',
      conclusion: allResponses.value.get(RECON_CONCLUSION_KEY)?.conclusion ?? '',
      indexRef: allResponses.value.get(RECON_INDEX_KEY)?.remark ?? '',
    }
  })

  // ─── 核对区字段保存 ──────────────────────────────────────────────────────

  /** 更新核对区差异说明（debounce 2s） */
  function updateReconExplanation(text: string): void {
    if (isReadonly.value) return
    const item: ChecklistItem = {
      item_id: RECON_EXPLANATION_KEY,
      conclusion: null,
      remark: text || null,
    }
    allResponses.value.set(RECON_EXPLANATION_KEY, item)
    saveDebouncedText(item)
  }

  /** 更新核对区审计结论（立即保存，select类） */
  function updateReconConclusion(value: string): void {
    if (isReadonly.value) return
    const item: ChecklistItem = {
      item_id: RECON_CONCLUSION_KEY,
      conclusion: value || null,
      remark: null,
    }
    allResponses.value.set(RECON_CONCLUSION_KEY, item)
    saveImmediate([item])
  }

  /** 更新核对区索引号（debounce 2s） */
  function updateReconIndexRef(text: string): void {
    if (isReadonly.value) return
    const item: ChecklistItem = {
      item_id: RECON_INDEX_KEY,
      conclusion: null,
      remark: text || null,
    }
    allResponses.value.set(RECON_INDEX_KEY, item)
    saveDebouncedText(item)
  }

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
  } = useD1ImportExport({ wpId, sheetCode: 'D1-10', sheetLabel: '监盘表' })

  const exportTemplate = _exportTemplate
  const exportData = _exportData

  /** 导入 xlsx 数据（包装共享模块，额外处理行回写） */
  async function importData(file: File): Promise<ImportResult> {
    // 先通过共享模块发送请求获取结果
    const formData = new FormData()
    formData.append('file', file)
    try {
      const res = await http.post(
        `/api/workpapers/${wpId.value}/d1-import-export/import-data`,
        formData,
        {
          params: { sheet: 'D1-10' },
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

    // 合计行
    sumAmount,

    // 核对区
    reconArea,
    bookBalance,
    bookBalanceLoaded,
    differenceAmount,
    hasDifference,

    // 核对区字段操作
    updateReconExplanation,
    updateReconConclusion,
    updateReconIndexRef,

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

export default useD1InventoryCount
