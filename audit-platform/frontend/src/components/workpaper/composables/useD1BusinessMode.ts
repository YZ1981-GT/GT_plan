/**
 * useD1BusinessMode — D1-6 业务模式分析 composable
 *
 * Spec: .kiro/specs/d1-endorsement-discount/
 * Task: 3.1
 *
 * 职责：
 * - 管理"业务模式及依据"表（basisRows）：3个固定行（高信用银行/低信用银行/商业承兑）
 *   支持编辑业务模式/依据/索引号/备注，debounce 2s 保存
 * - 管理"分类判断"QA矩阵（qaMatrix）：4问题 × 3组合，每格 Y/N/空
 *   切换 Y/N 为选择类字段，立即保存
 * - 自动判定：businessModeResults（对每列调用 determineBusinessMode）
 * - 自动判定：reportItemResults（对每列调用 determineReportItem）
 * - 审计说明/结论（auditNote/auditConclusion）：debounce 2s 保存
 * - 序列化/反序列化（JSON ↔ checklist_responses remark）
 * - respect isReadonly（只读时所有写操作 no-op）
 *
 * Requirements: 1.1-1.6, 2.1-2.8, 3.1-3.5, 13.1, 13.5, 13.6
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import type { ChecklistItem, ChecklistResponse } from './useD1FormData'
import { determineBusinessMode, determineReportItem } from './useD1FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface BusinessModeRow {
  rowId: string          // 'fixed-high-bank' | 'fixed-low-bank' | 'fixed-commercial'
  combinationName: string // 组合名称
  businessMode: string   // 业务模式（下拉）
  basis: string          // 具体依据
  indexRef: string       // 索引号
  remark: string         // 备注
  isFixed: boolean
}

export interface QACell {
  answer: 'Y' | 'N' | ''  // 是/否/未填
}

export interface QAMatrix {
  questions: string[]      // 4个问题文本（固定）
  columns: string[]        // 3个组合名（固定）
  cells: QACell[][]        // [4行][3列]
}

export type SaveFn = (items: ChecklistItem[]) => Promise<void>

export interface UseD1BusinessModeOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  wpId: Ref<string>
  projectId: Ref<string>
  saveImmediate: SaveFn
  isReadonly: Ref<boolean>
}

// ─── Constants ───────────────────────────────────────────────────────────────

const BASIS_STORAGE_KEY = 'D1-bm-basis-rows'
const QA_STORAGE_KEY = 'D1-bm-qa-matrix'
const PROCEDURES_KEY = 'D1-bm-procedures'
const NOTE_KEY = 'D1-bm-note'
const CONCLUSION_KEY = 'D1-bm-conclusion'

/** 3个固定业务模式依据行（对齐 Excel 模板组合名称） */
const FIXED_BASIS_ROWS: BusinessModeRow[] = [
  {
    rowId: 'fixed-high-bank',
    combinationName: '信用等级高的银行承兑汇票',
    businessMode: '',
    basis: '',
    indexRef: '',
    remark: '',
    isFixed: true,
  },
  {
    rowId: 'fixed-low-bank',
    combinationName: '信用等级低的银行承兑汇票',
    businessMode: '',
    basis: '',
    indexRef: '',
    remark: '',
    isFixed: true,
  },
  {
    rowId: 'fixed-commercial',
    combinationName: '商业承兑汇票',
    businessMode: '',
    basis: '',
    indexRef: '',
    remark: '',
    isFixed: true,
  },
]

/** QA矩阵固定问题（4行） */
const QA_QUESTIONS: string[] = [
  'Q1: 是否以收取合同现金流量为目标（持有至到期为主）？',
  'Q2: 是否存在较频繁的贴现或背书转让行为？',
  'Q3: 贴现/背书转让是否占该组合总额的重要比例？',
  'Q4: 是否同时以收取合同现金流量和出售金融资产为目标？',
]

/** QA矩阵固定列头（3组合，对齐 Excel） */
const QA_COLUMNS: string[] = [
  '信用等级高的银行承兑汇票',
  '信用等级低的银行承兑汇票',
  '商业承兑汇票',
]

/** 生成 4×3 全空的 QA cells 网格 */
function emptyCells(): QACell[][] {
  return QA_QUESTIONS.map(() => QA_COLUMNS.map(() => ({ answer: '' as const })))
}

/** 生成默认 QA 矩阵 */
function defaultQAMatrix(): QAMatrix {
  return {
    questions: [...QA_QUESTIONS],
    columns: [...QA_COLUMNS],
    cells: emptyCells(),
  }
}

/** 深拷贝固定依据行 */
function cloneFixedBasisRows(): BusinessModeRow[] {
  return FIXED_BASIS_ROWS.map((r) => ({ ...r }))
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD1BusinessMode(options: UseD1BusinessModeOptions) {
  const { allResponses, saveImmediate, isReadonly } = options

  // ─── State ───────────────────────────────────────────────────────────────

  const basisRows = ref<BusinessModeRow[]>(cloneFixedBasisRows())
  const qaMatrix = ref<QAMatrix>(defaultQAMatrix())
  const auditProcedures = ref<string>('')
  const auditNote = ref<string>('')
  const auditConclusion = ref<string>('')

  // ─── Deserialization (Load from allResponses) ────────────────────────────

  /** 加载业务模式依据表：默认3固定行，将已保存的编辑按 rowId 合并到固定行上 */
  function loadBasisRows(): BusinessModeRow[] {
    const base = cloneFixedBasisRows()
    const raw = allResponses.value.get(BASIS_STORAGE_KEY)?.remark
    if (!raw) return base
    try {
      const parsed = JSON.parse(raw)
      if (!Array.isArray(parsed)) return base
      for (const saved of parsed) {
        if (!saved || typeof saved.rowId !== 'string') continue
        const target = base.find((r) => r.rowId === saved.rowId)
        if (target) {
          target.combinationName = typeof saved.combinationName === 'string' ? saved.combinationName : target.combinationName
          target.businessMode = typeof saved.businessMode === 'string' ? saved.businessMode : ''
          target.basis = typeof saved.basis === 'string' ? saved.basis : ''
          target.indexRef = typeof saved.indexRef === 'string' ? saved.indexRef : ''
          target.remark = typeof saved.remark === 'string' ? saved.remark : ''
        }
      }
      return base
    } catch {
      return base
    }
  }

  /** 加载 QA 矩阵：仅 cells 持久化，questions/columns 为静态默认 */
  function loadQAMatrix(): QAMatrix {
    const matrix = defaultQAMatrix()
    const raw = allResponses.value.get(QA_STORAGE_KEY)?.remark
    if (!raw) return matrix
    try {
      const parsed = JSON.parse(raw)
      const cells = parsed?.cells
      if (!Array.isArray(cells)) return matrix
      for (let q = 0; q < QA_QUESTIONS.length; q++) {
        const rowCells = cells[q]
        if (!Array.isArray(rowCells)) continue
        for (let c = 0; c < QA_COLUMNS.length; c++) {
          const val = rowCells[c]
          // 兼容两种存储：'Y'/'N'/'' 字符串 或 {answer:'Y'} 对象
          let answer: 'Y' | 'N' | '' = ''
          if (val === 'Y' || val === 'N') answer = val
          else if (val && (val.answer === 'Y' || val.answer === 'N')) answer = val.answer
          matrix.cells[q][c] = { answer }
        }
      }
      return matrix
    } catch {
      return matrix
    }
  }

  function loadFromResponses(): void {
    basisRows.value = loadBasisRows()
    qaMatrix.value = loadQAMatrix()
    auditProcedures.value = allResponses.value.get(PROCEDURES_KEY)?.remark ?? ''
    auditNote.value = allResponses.value.get(NOTE_KEY)?.remark ?? ''
    auditConclusion.value = allResponses.value.get(CONCLUSION_KEY)?.remark ?? ''
  }

  // Initial load
  loadFromResponses()

  // Watch allResponses for external changes
  watch(
    () => [
      allResponses.value.get(BASIS_STORAGE_KEY)?.remark,
      allResponses.value.get(QA_STORAGE_KEY)?.remark,
      allResponses.value.get(PROCEDURES_KEY)?.remark,
      allResponses.value.get(NOTE_KEY)?.remark,
      allResponses.value.get(CONCLUSION_KEY)?.remark,
    ],
    ([newBasis, newQa, newProcedures, newNote, newConclusion]) => {
      if (newBasis !== undefined && newBasis !== serializeBasisRows(basisRows.value)) {
        basisRows.value = loadBasisRows()
      }
      if (newQa !== undefined && newQa !== serializeQAMatrix(qaMatrix.value)) {
        qaMatrix.value = loadQAMatrix()
      }
      if (newProcedures !== undefined && newProcedures !== auditProcedures.value) {
        auditProcedures.value = newProcedures ?? ''
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

  function serializeBasisRows(rows: BusinessModeRow[]): string {
    const data = rows.map((r) => ({
      rowId: r.rowId,
      combinationName: r.combinationName,
      businessMode: r.businessMode,
      basis: r.basis,
      indexRef: r.indexRef,
      remark: r.remark,
      isFixed: r.isFixed,
    }))
    return JSON.stringify(data)
  }

  function serializeQAMatrix(matrix: QAMatrix): string {
    // 仅持久化 cells（answer 字符串二维数组）
    const cells = matrix.cells.map((row) => row.map((cell) => cell.answer))
    return JSON.stringify({ cells })
  }

  // ─── Debounce Save (basisRows + note + conclusion) ───────────────────────

  let saveTimer: ReturnType<typeof setTimeout> | null = null

  function scheduleSave(): void {
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = setTimeout(() => {
      saveTimer = null
      persistToResponses()
    }, 2000)
  }

  /** 持久化 basisRows / note / conclusion（QA矩阵单独立即保存，不在此处） */
  function persistToResponses(): void {
    const basisSerialized = serializeBasisRows(basisRows.value)
    const items: ChecklistItem[] = [
      { item_id: BASIS_STORAGE_KEY, conclusion: null, remark: basisSerialized },
      { item_id: PROCEDURES_KEY, conclusion: null, remark: auditProcedures.value || null },
      { item_id: NOTE_KEY, conclusion: null, remark: auditNote.value || null },
      { item_id: CONCLUSION_KEY, conclusion: null, remark: auditConclusion.value || null },
    ]
    for (const item of items) {
      allResponses.value.set(item.item_id, item)
    }
    saveImmediate(items)
  }

  // ─── Auto-Judgment (computed) ────────────────────────────────────────────

  /** 对每列（3组合）调用 determineBusinessMode(Q1,Q2,Q3,Q4) */
  const businessModeResults: ComputedRef<string[]> = computed(() => {
    const cells = qaMatrix.value.cells
    return QA_COLUMNS.map((_, col) =>
      determineBusinessMode(
        cells[0]?.[col]?.answer ?? '',
        cells[1]?.[col]?.answer ?? '',
        cells[2]?.[col]?.answer ?? '',
        cells[3]?.[col]?.answer ?? '',
      ),
    )
  })

  /** 对每列的业务模式判定结果映射列报项目 */
  const reportItemResults: ComputedRef<string[]> = computed(() =>
    businessModeResults.value.map((mode) => determineReportItem(mode)),
  )

  // ─── Operations ──────────────────────────────────────────────────────────

  /** 编辑业务模式依据行 → debounce 保存 */
  function updateBasisRow(rowId: string, field: string, value: string): void {
    if (isReadonly.value) return
    const idx = basisRows.value.findIndex((r) => r.rowId === rowId)
    if (idx === -1) return
    const editableFields: Array<keyof BusinessModeRow> = [
      'combinationName', 'businessMode', 'basis', 'indexRef', 'remark',
    ]
    if (!editableFields.includes(field as keyof BusinessModeRow)) return
    const row = { ...basisRows.value[idx], [field]: String(value) }
    const newRows = [...basisRows.value]
    newRows[idx] = row
    basisRows.value = newRows
    scheduleSave()
  }

  /** 切换 QA 格子 Y/N/空 → 立即保存（选择类字段）→ 触发 computed 重算 */
  function updateQACell(questionIdx: number, columnIdx: number, answer: 'Y' | 'N' | ''): void {
    if (isReadonly.value) return
    if (questionIdx < 0 || questionIdx >= QA_QUESTIONS.length) return
    if (columnIdx < 0 || columnIdx >= QA_COLUMNS.length) return

    const newCells = qaMatrix.value.cells.map((row) => row.map((cell) => ({ ...cell })))
    newCells[questionIdx][columnIdx] = { answer }
    qaMatrix.value = { ...qaMatrix.value, cells: newCells }

    const serialized = serializeQAMatrix(qaMatrix.value)
    const item: ChecklistItem = { item_id: QA_STORAGE_KEY, conclusion: null, remark: serialized }
    allResponses.value.set(QA_STORAGE_KEY, item)
    saveImmediate([item])
  }

  /** 保存审计过程 → debounce 保存 */
  function saveAuditProcedures(text: string): void {
    if (isReadonly.value) return
    auditProcedures.value = text
    scheduleSave()
  }

  /** 保存审计说明 → debounce 保存 */
  function saveAuditNote(text: string): void {
    if (isReadonly.value) return
    auditNote.value = text
    scheduleSave()
  }

  /** 保存审计结论 → debounce 保存 */
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
    basisRows,
    qaMatrix,
    businessModeResults,
    reportItemResults,
    auditProcedures,
    auditNote,
    auditConclusion,
    updateBasisRow,
    updateQACell,
    saveAuditProcedures,
    saveAuditNote,
    saveAuditConclusion,
  }
}

export default useD1BusinessMode
