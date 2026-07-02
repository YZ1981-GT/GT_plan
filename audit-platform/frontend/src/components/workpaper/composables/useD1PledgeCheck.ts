/**
 * useD1PledgeCheck — D1-12 应收票据质押检查表 composable
 *
 * Spec: .kiro/specs/d1-inspection-check/
 * Task: 5.1
 *
 * 职责：
 * - 管理 16 列质押检查表动态行 CRUD
 * - 合计行 Row18 computed（H18 = SUM票据金额列, J18 = SUM质押金额列）
 * - 跨Spec取数：从 allResponses 读取 D1-adj-book-value-current → adjBookValue computed
 * - 质押比例计算：pledgeRatio = computePledgeRatio(sumPledgeAmount, adjBookValue)
 * - 质押比例显示：pledgeRatioDisplay（百分比格式或"N/A"）
 * - 质押预警：isPledgeWarning（pledgeRatio > 0.5）
 * - 审计说明/结论（auditNote / auditConclusion）
 * - 动态行 CRUD（addRow / removeRow / updateRow）
 * - 序列化/反序列化（JSON ↔ checklist_responses remark），debounce 2s 自动保存
 * - select 类字段立即保存
 * - exportTemplate / exportData / importData 导入导出接口
 * - respect isReadonly
 * - 票据类型/号码列 fixed 定位（横向滚动时可见）— 通过返回值注释提示Vue组件层实现
 *
 * 跨 Spec 数据契约：
 *   从 allResponses 读取 `D1-adj-book-value-current`（审定表净值）
 *   若 key 不存在 → adjDataLoaded = false, adjBookValue = null
 *
 * Requirements: 7.1-7.6, 8.1-8.6, 9.1-9.5, 15.3, 15.6, 15.9
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import type { ChecklistItem, ChecklistResponse } from './useD1FormData'
import { sumColumn, computePledgeRatio, type PledgeRow } from './d1InspectionFormulas'
import { useD1ImportExport, type ImportResult } from './useD1ImportExport'
import http from '@/utils/http'

// ─── Types ───────────────────────────────────────────────────────────────────

export type SaveFn = (items: ChecklistItem[]) => Promise<void>
export type DebounceSaveFn = (item: ChecklistItem) => void

export interface UseD1PledgeCheckOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  wpId: Ref<string>
  projectId: Ref<string>
  saveImmediate: SaveFn
  saveDebouncedText: DebounceSaveFn
  isReadonly: Ref<boolean>
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ROWS_KEY = 'D1-pledge-rows'
const NOTE_KEY = 'D1-pledge-note'
const CONCLUSION_KEY = 'D1-pledge-conclusion'

/** 跨Spec审定表净值 key（来自 d1-adjudication-table Spec） */
const CROSS_SPEC_ADJ_BOOK_VALUE_KEY = 'D1-adj-book-value-current'

/** PledgeRow 数值字段 */
const NUMERIC_FIELDS: Array<keyof PledgeRow> = ['noteAmount', 'pledgeAmount']

/** PledgeRow 字符串字段 */
const STRING_FIELDS: Array<keyof PledgeRow> = [
  'noteType',
  'noteNo',
  'receiveDate',
  'predecessor',
  'issueDate',
  'drawer',
  'acceptor',
  'maturityDate',
  'pledgee',
  'pledgeReason',
  'pledgeCondition',
  'pledgePeriod',
  'pledgeAgreement',
  'indexRef',
]

/** select类字段（立即保存） */
const SELECT_FIELDS: Array<keyof PledgeRow> = ['noteType']

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
export function emptyPledgeRow(): PledgeRow {
  return {
    id: generateRowId(),
    noteType: '',
    noteNo: '',
    receiveDate: '',
    predecessor: '',
    issueDate: '',
    drawer: '',
    acceptor: '',
    noteAmount: 0,
    maturityDate: '',
    pledgeAmount: 0,
    pledgee: '',
    pledgeReason: '',
    pledgeCondition: '',
    pledgePeriod: '',
    pledgeAgreement: '',
    indexRef: '',
  }
}

/** 反序列化单行 */
function deserializeRow(raw: any): PledgeRow {
  const row = emptyPledgeRow()
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
function serializeRow(row: PledgeRow): any {
  const data: any = { id: row.id }
  for (const f of STRING_FIELDS) data[f] = (row as any)[f]
  for (const f of NUMERIC_FIELDS) data[f] = (row as any)[f]
  return data
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD1PledgeCheck(options: UseD1PledgeCheckOptions) {
  const { allResponses, wpId, projectId: _projectId, saveImmediate, saveDebouncedText, isReadonly } = options

  // ─── State ───────────────────────────────────────────────────────────────

  const rows = ref<PledgeRow[]>([])
  const auditNote = ref<string>('')
  const auditConclusion = ref<string>('')

  // ─── Deserialization (Load from allResponses) ────────────────────────────

  function loadRows(): PledgeRow[] {
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
    const newRow = emptyPledgeRow()
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
  function updateRow(id: string, field: keyof PledgeRow, value: any): void {
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

    // select类字段立即保存，金额/文本字段 debounce 2s
    if (SELECT_FIELDS.includes(field)) {
      persistRowsImmediate()
    } else {
      scheduleSave()
    }
  }

  // ─── Computed: 合计行 Row18 ──────────────────────────────────────────────

  /** H18 = SUM(票据金额列) */
  const sumNoteAmount: ComputedRef<number> = computed(() => {
    return sumColumn(rows.value, 'noteAmount')
  })

  /** J18 = SUM(质押金额列) */
  const sumPledgeAmount: ComputedRef<number> = computed(() => {
    return sumColumn(rows.value, 'pledgeAmount')
  })

  // ─── Computed: 跨Spec审定表净值 ──────────────────────────────────────────

  /** 审定表净值（跨Spec取数）— null表示未加载 */
  const adjBookValue: ComputedRef<number | null> = computed(() => {
    const raw = allResponses.value.get(CROSS_SPEC_ADJ_BOOK_VALUE_KEY)?.remark
    if (raw == null) return null
    const n = parseNum(raw)
    return n
  })

  /** 审定表净值数据是否已加载 */
  const adjDataLoaded: ComputedRef<boolean> = computed(() => {
    return allResponses.value.has(CROSS_SPEC_ADJ_BOOK_VALUE_KEY)
  })

  // ─── Computed: 质押比例 ──────────────────────────────────────────────────

  /** 质押比例 = J18 / adjBookValue，零值守卫 */
  const pledgeRatio: ComputedRef<number | null> = computed(() => {
    return computePledgeRatio(sumPledgeAmount.value, adjBookValue.value)
  })

  /** 质押比例显示（百分比格式或"N/A"） */
  const pledgeRatioDisplay: ComputedRef<string> = computed(() => {
    if (pledgeRatio.value === null) return 'N/A'
    return `${(pledgeRatio.value * 100).toFixed(2)}%`
  })

  /** 质押比例超过50%预警 */
  const isPledgeWarning: ComputedRef<boolean> = computed(() => {
    return pledgeRatio.value !== null && pledgeRatio.value > 0.5
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
  } = useD1ImportExport({ wpId, sheetCode: 'D1-12', sheetLabel: '质押检查' })

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
          params: { sheet: 'D1-12' },
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

  // ─── 从备查簿D1-7导入已质押票据 ──────────────────────────────────────────

  /** D1-memo-rows 存储 key（来自 d1-endorsement-discount Spec③ 备查簿 D1-7） */
  const MEMO_ROWS_KEY = 'D1-memo-rows'

  /**
   * 从备查簿 D1-7 读取已质押票据行并映射为 PledgeRow[]
   *
   * D1-memo-rows 存储格式: { bankRows: MemoRow[], commercialRows: MemoRow[] }
   * 筛选条件: isPledged === '是'
   * 映射: MemoRow → PledgeRow (A-I 票据基本信息自动填充, J-P 质押详情留空)
   *
   * Requirements: 19.1, 19.2, 19.3
   */
  function importFromMemo(): { rows: PledgeRow[]; count: number } {
    const raw = allResponses.value.get(MEMO_ROWS_KEY)?.remark
    if (!raw) return { rows: [], count: 0 }

    try {
      const parsed = JSON.parse(raw)
      // D1-memo-rows 格式: { bankRows: [...], commercialRows: [...] }
      let allMemoRows: any[] = []
      if (parsed && typeof parsed === 'object') {
        if (Array.isArray(parsed.bankRows)) allMemoRows = allMemoRows.concat(parsed.bankRows)
        if (Array.isArray(parsed.commercialRows)) allMemoRows = allMemoRows.concat(parsed.commercialRows)
        // 兼容：如果直接是数组格式
        if (Array.isArray(parsed)) allMemoRows = parsed
      }

      // 筛选已质押行
      const pledgedRows = allMemoRows.filter((r: any) => r && r.isPledged === '是')

      if (pledgedRows.length === 0) return { rows: [], count: 0 }

      // 映射为 PledgeRow（A-I 自动填充，J-P 留空）
      const mappedRows: PledgeRow[] = pledgedRows.map((memo: any) => ({
        id: generateRowId(),
        noteType: String(memo.noteType ?? ''),        // A: 票据类型
        noteNo: String(memo.noteNumber ?? ''),        // B: 票据号码
        receiveDate: String(memo.receivedDate ?? ''), // C: 收到票据日期
        predecessor: String(memo.endorser ?? ''),     // D: 票据前手名称
        issueDate: String(memo.issueDate ?? ''),      // E: 出票日期
        drawer: String(memo.issuer ?? ''),            // F: 出票人名称
        acceptor: String(memo.acceptor ?? ''),        // G: 承兑人名称
        noteAmount: parseNum(memo.amount),            // H: 票据金额
        maturityDate: String(memo.maturityDate ?? ''),// I: 票据到期日
        // J-P 质押详情留空供用户手填
        pledgeAmount: 0,
        pledgee: '',
        pledgeReason: '',
        pledgeCondition: '',
        pledgePeriod: '',
        pledgeAgreement: '',
        indexRef: '',
      }))

      return { rows: mappedRows, count: mappedRows.length }
    } catch {
      return { rows: [], count: 0 }
    }
  }

  /**
   * 从备查簿导入并追加已质押票据到现有行
   *
   * 1. 调用 importFromMemo() 获取已质押行
   * 2. 如果有行：追加到 rows 数组末尾并触发保存
   * 3. 返回导入行数（供 UI 显示消息）
   *
   * Requirements: 19.4, 19.5, 19.6
   */
  function appendFromMemo(): number {
    if (isReadonly.value) return 0
    const result = importFromMemo()
    if (result.count === 0) return 0

    rows.value = [...rows.value, ...result.rows]
    persistRowsImmediate()
    return result.count
  }

  // ─── Cleanup ─────────────────────────────────────────────────────────────

  onBeforeUnmount(() => {
    if (saveTimer) {
      clearTimeout(saveTimer)
      persistRows()
    }
  })

  // ─── Return ──────────────────────────────────────────────────────────────
  // NOTE: 票据类型(noteType)+票据号码(noteNo)列应在Vue组件层使用 el-table-column fixed="left"
  //       实现横向滚动时保持可见。此 composable 不涉及 UI 层 fixed 定位。

  return {
    // 动态行
    rows,
    addRow,
    removeRow,
    updateRow,

    // 合计行 Row18
    sumNoteAmount,
    sumPledgeAmount,

    // 质押比例
    adjBookValue,
    adjDataLoaded,
    pledgeRatio,
    pledgeRatioDisplay,
    isPledgeWarning,

    // 审计说明/结论
    auditNote,
    auditConclusion,
    saveAuditNote,
    saveAuditConclusion,

    // 导入导出
    exportTemplate,
    exportData,
    importData,

    // 从备查簿D1-7导入已质押票据
    importFromMemo,
    appendFromMemo,
  }
}

export default useD1PledgeCheck
