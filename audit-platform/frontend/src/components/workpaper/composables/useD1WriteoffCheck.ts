/**
 * useD1WriteoffCheck — D1-16 坏账准备转回/核销检查表 composable
 *
 * Spec: .kiro/specs/d1-writeoff-check/
 * Task: 1.1, 1.2
 *
 * 职责：
 * - 管理 Section 1 转回检查表（8列）动态行 CRUD + SUM 合计
 * - 管理 Section 2 核销检查表（5列）动态行 CRUD + SUM 合计
 * - 跨Spec校验：D1-4转回/核销变动合计对比 + ECL计提总额预警
 * - 预警判断：转回超原计提(E>F)、核销超计提、必填字段缺失
 * - 审计说明/结论（Section 3/4）双向绑定 + debounce 保存
 * - 汇总写出：D1-writeoff-reversal-total / D1-writeoff-writeoff-total
 * - 持久化复用 checklist_responses 表 + useD1FormData 基础设施
 *
 * 跨 Spec 数据契约：
 *   读入 D1-adj-bad-debt-reversal（D1-4转回变动合计）
 *   读入 D1-adj-bad-debt-writeoff（D1-4核销变动合计）
 *   读入 D1-ecl-total-current（ECL本期计提总额）
 *   写出 D1-writeoff-reversal-total（本表转回合计）
 *   写出 D1-writeoff-writeoff-total（本表核销合计）
 *
 * Requirements: 1.1-1.5, 2.1-2.6, 3.1-3.4, 4.1-4.5, 5.1-5.6, 6.1-6.4,
 *              9.5-9.7, 10.1-10.5, 11.2-11.4, 12.1-12.3
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import type { ChecklistItem, ChecklistResponse } from './useD1FormData'

// ═══════════════════════════════════════════════════════════════════════════
// 类型定义
// ═══════════════════════════════════════════════════════════════════════════

/** D1-16 Section 1 转回明细行（8列） */
export interface ReversalRow {
  id: string                    // uuid
  unitName: string              // A: 单位名称
  reason: string                // B: 转回原因
  recoveryMethod: string        // C: 收回方式（现金收回/银行转账/票据兑现/以物抵债/债务重组/其他）
  originalBasis: string         // D: 原确定坏账准备的依据
  reversalAmount: number        // E: 收回或转回金额
  priorProvisionAmount: number  // F: 收回或转回前累计已计提坏账准备金额
  reasonabilityAnalysis: string // G: 合理性分析
  indexRef: string              // H: 索引号
}

/** D1-16 Section 2 核销明细行（5列） */
export interface WriteoffRow {
  id: string                    // uuid
  unitName: string              // A: 单位名称
  noteNature: string            // B: 应收票据的性质（银行承兑汇票/商业承兑汇票/其他）
  writeoffAmount: number        // C: 核销金额
  writeoffReason: string        // D: 核销原因
  writeoffProcedure: string     // E: 履行的核销程序
}

/** 收回方式枚举 */
export type RecoveryMethod = '现金收回' | '银行转账' | '票据兑现' | '以物抵债' | '债务重组' | '其他'

/** 应收票据性质枚举 */
export type NoteNature = '银行承兑汇票' | '商业承兑汇票' | '其他'

// ═══════════════════════════════════════════════════════════════════════════
// 常量
// ═══════════════════════════════════════════════════════════════════════════

/** 收回方式选项 */
export const RECOVERY_METHODS: RecoveryMethod[] = [
  '现金收回', '银行转账', '票据兑现', '以物抵债', '债务重组', '其他',
]

/** 应收票据性质选项 */
export const NOTE_NATURES: NoteNature[] = [
  '银行承兑汇票', '商业承兑汇票', '其他',
]

// ═══════════════════════════════════════════════════════════════════════════
// 纯函数
// ═══════════════════════════════════════════════════════════════════════════

/**
 * 解析数值（安全）: null / undefined / 空串 / NaN → 0
 *
 * 用于从 allResponses remark 字符串或 input 控件值安全解析为数字。
 * 非有限数（Infinity / NaN）均降级为 0。
 */
export function parseNum(val: string | number | null | undefined): number {
  if (val == null || val === '') return 0
  const n = typeof val === 'number' ? val : Number(val)
  return Number.isFinite(n) ? n : 0
}

/**
 * SUM 数组求和
 *
 * 对传入的 number[] 累加求和。空数组返回 0。
 * 覆盖 reversalTotalE / reversalTotalF / writeoffTotalC 计算。
 */
export function sumArray(values: number[]): number {
  return values.reduce((acc, v) => acc + v, 0)
}

/**
 * 转回金额超原计提判定: E > F 且 E > 0
 *
 * 当转回金额大于已计提坏账准备时触发橙色预警。
 * E=0 或 E<=F 时不预警（无转回或在合理范围）。
 *
 * Requirements: 3.1
 */
export function isReversalExceedsProvision(reversalAmount: number, priorProvision: number): boolean {
  return reversalAmount > 0 && reversalAmount > priorProvision
}

/**
 * 核销超计提判定: writeoffTotal > eclTotal 且 eclTotal > 0
 *
 * 当核销金额合计超过 ECL 本期计提总额时触发橙色预警。
 * eclTotal 为 null（未加载）或 ≤0 时不预警（缺乏对比基准）。
 *
 * Requirements: 6.1, 6.2
 */
export function isWriteoffExceedsProvision(writeoffTotal: number, eclTotal: number | null): boolean {
  if (eclTotal == null || eclTotal <= 0) return false
  return writeoffTotal > eclTotal
}

/**
 * 缺失必填字段检查（转回行）: amount > 0 时 reason 和 reasonabilityAnalysis 必填
 *
 * 返回缺失的字段名数组。空数组表示无缺失。
 * amount ≤ 0 时无必填要求（空行/占位行不强制填写）。
 *
 * Requirements: 3.2, 3.3
 */
export function getMissingReversalFields(row: ReversalRow): string[] {
  const missing: string[] = []
  if (row.reversalAmount > 0) {
    if (!row.reason.trim()) missing.push('reason')
    if (!row.reasonabilityAnalysis.trim()) missing.push('reasonabilityAnalysis')
  }
  return missing
}

/**
 * 缺失必填字段检查（核销行）: amount > 0 时 writeoffReason 和 writeoffProcedure 必填
 *
 * 返回缺失的字段名数组。空数组表示无缺失。
 * amount ≤ 0 时无必填要求（空行/占位行不强制填写）。
 *
 * Requirements: 6.1, 6.2
 */
export function getMissingWriteoffFields(row: WriteoffRow): string[] {
  const missing: string[] = []
  if (row.writeoffAmount > 0) {
    if (!row.writeoffReason.trim()) missing.push('writeoffReason')
    if (!row.writeoffProcedure.trim()) missing.push('writeoffProcedure')
  }
  return missing
}

// ═══════════════════════════════════════════════════════════════════════════
// Types — Composable Options
// ═══════════════════════════════════════════════════════════════════════════

export type SaveFn = (items: ChecklistItem[]) => Promise<void>
export type DebounceSaveFn = (item: ChecklistItem) => void

export interface UseD1WriteoffCheckOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  wpId: Ref<string>
  projectId: Ref<string>
  saveImmediate: SaveFn
  saveDebouncedText: DebounceSaveFn
  isReadonly: Ref<boolean>
}

// ═══════════════════════════════════════════════════════════════════════════
// Constants — Item Keys
// ═══════════════════════════════════════════════════════════════════════════

const REVERSAL_ROWS_KEY = 'D1-writeoff-reversal-rows'
const WRITEOFF_ROWS_KEY = 'D1-writeoff-writeoff-rows'
const AUDIT_NOTE_KEY = 'D1-writeoff-audit-note'
const AUDIT_CONCLUSION_KEY = 'D1-writeoff-audit-conclusion'
const REVERSAL_TOTAL_KEY = 'D1-writeoff-reversal-total'
const WRITEOFF_TOTAL_KEY = 'D1-writeoff-writeoff-total'

/** select 类字段（立即保存） */
const REVERSAL_SELECT_FIELDS: Array<keyof ReversalRow> = ['recoveryMethod']
const WRITEOFF_SELECT_FIELDS: Array<keyof WriteoffRow> = ['noteNature']

// ═══════════════════════════════════════════════════════════════════════════
// Helpers
// ═══════════════════════════════════════════════════════════════════════════

function generateRowId(): string {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID()
  }
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function emptyReversalRow(): ReversalRow {
  return {
    id: generateRowId(),
    unitName: '',
    reason: '',
    recoveryMethod: '',
    originalBasis: '',
    reversalAmount: 0,
    priorProvisionAmount: 0,
    reasonabilityAnalysis: '',
    indexRef: '',
  }
}

function emptyWriteoffRow(): WriteoffRow {
  return {
    id: generateRowId(),
    unitName: '',
    noteNature: '',
    writeoffAmount: 0,
    writeoffReason: '',
    writeoffProcedure: '',
  }
}

/** ReversalRow 数值字段 */
const REVERSAL_NUMERIC_FIELDS: Array<keyof ReversalRow> = ['reversalAmount', 'priorProvisionAmount']

/** WriteoffRow 数值字段 */
const WRITEOFF_NUMERIC_FIELDS: Array<keyof WriteoffRow> = ['writeoffAmount']

function deserializeReversalRow(raw: any): ReversalRow {
  const row = emptyReversalRow()
  if (raw && typeof raw.id === 'string' && raw.id) row.id = raw.id
  if (raw) {
    if (typeof raw.unitName === 'string') row.unitName = raw.unitName
    if (typeof raw.reason === 'string') row.reason = raw.reason
    if (typeof raw.recoveryMethod === 'string') row.recoveryMethod = raw.recoveryMethod
    if (typeof raw.originalBasis === 'string') row.originalBasis = raw.originalBasis
    if (typeof raw.reasonabilityAnalysis === 'string') row.reasonabilityAnalysis = raw.reasonabilityAnalysis
    if (typeof raw.indexRef === 'string') row.indexRef = raw.indexRef
    if (raw.reversalAmount !== undefined) row.reversalAmount = parseNum(raw.reversalAmount)
    if (raw.priorProvisionAmount !== undefined) row.priorProvisionAmount = parseNum(raw.priorProvisionAmount)
  }
  return row
}

function deserializeWriteoffRow(raw: any): WriteoffRow {
  const row = emptyWriteoffRow()
  if (raw && typeof raw.id === 'string' && raw.id) row.id = raw.id
  if (raw) {
    if (typeof raw.unitName === 'string') row.unitName = raw.unitName
    if (typeof raw.noteNature === 'string') row.noteNature = raw.noteNature
    if (typeof raw.writeoffReason === 'string') row.writeoffReason = raw.writeoffReason
    if (typeof raw.writeoffProcedure === 'string') row.writeoffProcedure = raw.writeoffProcedure
    if (raw.writeoffAmount !== undefined) row.writeoffAmount = parseNum(raw.writeoffAmount)
  }
  return row
}

// ═══════════════════════════════════════════════════════════════════════════
// Composable
// ═══════════════════════════════════════════════════════════════════════════

export function useD1WriteoffCheck(options: UseD1WriteoffCheckOptions) {
  const { allResponses, saveImmediate, saveDebouncedText, isReadonly } = options

  // ─── State ─────────────────────────────────────────────────────────────

  const reversalRows = ref<ReversalRow[]>([])
  const writeoffRows = ref<WriteoffRow[]>([])
  const auditNote = ref<string>('')
  const auditConclusion = ref<string>('')
  const isLoading = ref<boolean>(false)

  // ─── Deserialization (Load from allResponses) ──────────────────────────

  function loadReversalRows(): ReversalRow[] {
    const raw = allResponses.value.get(REVERSAL_ROWS_KEY)?.remark
    if (!raw) return []
    try {
      const parsed = JSON.parse(raw)
      if (!Array.isArray(parsed)) return []
      return parsed.map((r: any) => deserializeReversalRow(r))
    } catch {
      console.warn('[useD1WriteoffCheck] Failed to parse reversal rows JSON')
      return []
    }
  }

  function loadWriteoffRows(): WriteoffRow[] {
    const raw = allResponses.value.get(WRITEOFF_ROWS_KEY)?.remark
    if (!raw) return []
    try {
      const parsed = JSON.parse(raw)
      if (!Array.isArray(parsed)) return []
      return parsed.map((r: any) => deserializeWriteoffRow(r))
    } catch {
      console.warn('[useD1WriteoffCheck] Failed to parse writeoff rows JSON')
      return []
    }
  }

  function loadFromResponses(): void {
    reversalRows.value = loadReversalRows()
    writeoffRows.value = loadWriteoffRows()
    auditNote.value = allResponses.value.get(AUDIT_NOTE_KEY)?.remark ?? ''
    auditConclusion.value = allResponses.value.get(AUDIT_CONCLUSION_KEY)?.remark ?? ''
  }

  // Initial load
  loadFromResponses()

  // Watch allResponses for external changes (other tabs / OO sync)
  watch(
    () => [
      allResponses.value.get(REVERSAL_ROWS_KEY)?.remark,
      allResponses.value.get(WRITEOFF_ROWS_KEY)?.remark,
      allResponses.value.get(AUDIT_NOTE_KEY)?.remark,
      allResponses.value.get(AUDIT_CONCLUSION_KEY)?.remark,
    ],
    ([newReversalRaw, newWriteoffRaw, newNote, newConclusion]) => {
      if (newReversalRaw !== undefined && newReversalRaw !== serializeReversalRows()) {
        reversalRows.value = loadReversalRows()
      }
      if (newWriteoffRaw !== undefined && newWriteoffRaw !== serializeWriteoffRows()) {
        writeoffRows.value = loadWriteoffRows()
      }
      if (newNote !== undefined && newNote !== auditNote.value) {
        auditNote.value = newNote ?? ''
      }
      if (newConclusion !== undefined && newConclusion !== auditConclusion.value) {
        auditConclusion.value = newConclusion ?? ''
      }
    },
  )

  // ─── Serialization ─────────────────────────────────────────────────────

  function serializeReversalRows(): string {
    return JSON.stringify(reversalRows.value)
  }

  function serializeWriteoffRows(): string {
    return JSON.stringify(writeoffRows.value)
  }

  // ─── Save Helpers ──────────────────────────────────────────────────────

  let reversalSaveTimer: ReturnType<typeof setTimeout> | null = null
  let writeoffSaveTimer: ReturnType<typeof setTimeout> | null = null
  let totalsSaveTimer: ReturnType<typeof setTimeout> | null = null

  function scheduleReversalSave(): void {
    if (reversalSaveTimer) clearTimeout(reversalSaveTimer)
    reversalSaveTimer = setTimeout(() => {
      reversalSaveTimer = null
      persistReversalRows()
    }, 2000)
  }

  function scheduleWriteoffSave(): void {
    if (writeoffSaveTimer) clearTimeout(writeoffSaveTimer)
    writeoffSaveTimer = setTimeout(() => {
      writeoffSaveTimer = null
      persistWriteoffRows()
    }, 2000)
  }

  function scheduleTotalsSave(): void {
    if (totalsSaveTimer) clearTimeout(totalsSaveTimer)
    totalsSaveTimer = setTimeout(() => {
      totalsSaveTimer = null
      persistTotals()
    }, 2000)
  }

  /** 持久化转回行数据 */
  function persistReversalRows(): void {
    const item: ChecklistItem = {
      item_id: REVERSAL_ROWS_KEY,
      conclusion: null,
      remark: serializeReversalRows(),
    }
    allResponses.value.set(REVERSAL_ROWS_KEY, item)
    saveImmediate([item])
  }

  /** 持久化核销行数据 */
  function persistWriteoffRows(): void {
    const item: ChecklistItem = {
      item_id: WRITEOFF_ROWS_KEY,
      conclusion: null,
      remark: serializeWriteoffRows(),
    }
    allResponses.value.set(WRITEOFF_ROWS_KEY, item)
    saveImmediate([item])
  }

  /** 持久化汇总写出 */
  function persistTotals(): void {
    const reversalTotalItem: ChecklistItem = {
      item_id: REVERSAL_TOTAL_KEY,
      conclusion: null,
      remark: String(reversalTotalE.value),
    }
    const writeoffTotalItem: ChecklistItem = {
      item_id: WRITEOFF_TOTAL_KEY,
      conclusion: null,
      remark: String(writeoffTotalC.value),
    }
    allResponses.value.set(REVERSAL_TOTAL_KEY, reversalTotalItem)
    allResponses.value.set(WRITEOFF_TOTAL_KEY, writeoffTotalItem)
    saveImmediate([reversalTotalItem, writeoffTotalItem])
  }

  // ─── Section 1: 转回检查 CRUD ─────────────────────────────────────────

  function addReversalRow(): void {
    if (isReadonly.value) return
    reversalRows.value = [...reversalRows.value, emptyReversalRow()]
    scheduleReversalSave()
  }

  function removeReversalRow(id: string): void {
    if (isReadonly.value) return
    const idx = reversalRows.value.findIndex((r) => r.id === id)
    if (idx === -1) return
    reversalRows.value = reversalRows.value.filter((r) => r.id !== id)
    scheduleReversalSave()
  }

  function updateReversalRow(id: string, field: keyof ReversalRow, value: string | number): void {
    if (isReadonly.value) return
    const idx = reversalRows.value.findIndex((r) => r.id === id)
    if (idx === -1) return

    const row = { ...reversalRows.value[idx] }
    if (REVERSAL_NUMERIC_FIELDS.includes(field as any)) {
      ;(row as any)[field] = parseNum(value)
    } else {
      ;(row as any)[field] = String(value ?? '')
    }

    const newRows = [...reversalRows.value]
    newRows[idx] = row
    reversalRows.value = newRows

    // select 类字段立即保存
    if (REVERSAL_SELECT_FIELDS.includes(field as any)) {
      persistReversalRows()
    } else {
      scheduleReversalSave()
    }
  }

  // ─── Section 2: 核销检查 CRUD ─────────────────────────────────────────

  function addWriteoffRow(): void {
    if (isReadonly.value) return
    writeoffRows.value = [...writeoffRows.value, emptyWriteoffRow()]
    scheduleWriteoffSave()
  }

  function removeWriteoffRow(id: string): void {
    if (isReadonly.value) return
    const idx = writeoffRows.value.findIndex((r) => r.id === id)
    if (idx === -1) return
    writeoffRows.value = writeoffRows.value.filter((r) => r.id !== id)
    scheduleWriteoffSave()
  }

  function updateWriteoffRow(id: string, field: keyof WriteoffRow, value: string | number): void {
    if (isReadonly.value) return
    const idx = writeoffRows.value.findIndex((r) => r.id === id)
    if (idx === -1) return

    const row = { ...writeoffRows.value[idx] }
    if (WRITEOFF_NUMERIC_FIELDS.includes(field as any)) {
      ;(row as any)[field] = parseNum(value)
    } else {
      ;(row as any)[field] = String(value ?? '')
    }

    const newRows = [...writeoffRows.value]
    newRows[idx] = row
    writeoffRows.value = newRows

    // select 类字段立即保存
    if (WRITEOFF_SELECT_FIELDS.includes(field as any)) {
      persistWriteoffRows()
    } else {
      scheduleWriteoffSave()
    }
  }

  // ─── Computed: SUM 合计 ────────────────────────────────────────────────

  /** E列合计: SUM(reversalAmount) */
  const reversalTotalE: ComputedRef<number> = computed(() => {
    return sumArray(reversalRows.value.map((r) => r.reversalAmount))
  })

  /** F列合计: SUM(priorProvisionAmount) */
  const reversalTotalF: ComputedRef<number> = computed(() => {
    return sumArray(reversalRows.value.map((r) => r.priorProvisionAmount))
  })

  /** C列合计: SUM(writeoffAmount) */
  const writeoffTotalC: ComputedRef<number> = computed(() => {
    return sumArray(writeoffRows.value.map((r) => r.writeoffAmount))
  })

  // ─── 跨Spec校验 ─────────────────────────────────────────────────────────

  /** D1-4坏账准备转回变动合计（null=未加载） */
  const d14ReversalTotal: ComputedRef<number | null> = computed(() => {
    const raw = allResponses.value.get('D1-adj-bad-debt-reversal')?.remark
    return raw == null ? null : parseNum(raw)
  })

  /** D1-4坏账准备核销变动合计（null=未加载） */
  const d14WriteoffTotal: ComputedRef<number | null> = computed(() => {
    const raw = allResponses.value.get('D1-adj-bad-debt-writeoff')?.remark
    return raw == null ? null : parseNum(raw)
  })

  /** ECL本期计提总额（null=未加载） */
  const eclCurrentTotal: ComputedRef<number | null> = computed(() => {
    const raw = allResponses.value.get('D1-ecl-total-current')?.remark
    return raw == null ? null : parseNum(raw)
  })

  /** 本表转回合计 - D1-4转回变动合计（null=D1-4未加载） */
  const reversalDiff: ComputedRef<number | null> = computed(() => {
    return d14ReversalTotal.value === null ? null : reversalTotalE.value - d14ReversalTotal.value
  })

  /** 本表核销合计 - D1-4核销变动合计（null=D1-4未加载） */
  const writeoffDiff: ComputedRef<number | null> = computed(() => {
    return d14WriteoffTotal.value === null ? null : writeoffTotalC.value - d14WriteoffTotal.value
  })

  /** 转回金额超原计提判定（method: per row） */
  function reversalExceedsProvision(row: ReversalRow): boolean {
    return isReversalExceedsProvision(row.reversalAmount, row.priorProvisionAmount)
  }

  /** 核销超计提判定（computed: 核销合计 vs ECL本期计提总额） */
  const writeoffExceedsProvision: ComputedRef<boolean> = computed(() => {
    return isWriteoffExceedsProvision(writeoffTotalC.value, eclCurrentTotal.value)
  })

  /** 缺失必填字段检查（转回行）: method */
  function missingReversalFields(row: ReversalRow): string[] {
    return getMissingReversalFields(row)
  }

  /** 缺失必填字段检查（核销行）: method */
  function missingWriteoffFields(row: WriteoffRow): string[] {
    return getMissingWriteoffFields(row)
  }

  // ─── Watch: 汇总写出 debounce ─────────────────────────────────────────

  watch(
    [reversalTotalE, writeoffTotalC],
    () => {
      scheduleTotalsSave()
    },
  )

  // ─── Section 3/4: 审计说明/结论 ───────────────────────────────────────

  function saveAuditNote(text: string): void {
    if (isReadonly.value) return
    auditNote.value = text
    const item: ChecklistItem = {
      item_id: AUDIT_NOTE_KEY,
      conclusion: null,
      remark: text || null,
    }
    allResponses.value.set(AUDIT_NOTE_KEY, item)
    saveDebouncedText(item)
  }

  function saveAuditConclusion(text: string): void {
    if (isReadonly.value) return
    auditConclusion.value = text
    const item: ChecklistItem = {
      item_id: AUDIT_CONCLUSION_KEY,
      conclusion: null,
      remark: text || null,
    }
    allResponses.value.set(AUDIT_CONCLUSION_KEY, item)
    saveDebouncedText(item)
  }

  // ─── P1: 同步到D1-4 ─────────────────────────────────────────────────────

  /** 将本表转回合计同步写入 D1-4 坏账准备明细表转回变动列 */
  function syncReversalToD14(): void {
    if (isReadonly.value) return
    const item: ChecklistItem = {
      item_id: 'D1-adj-bad-debt-reversal',
      conclusion: null,
      remark: String(reversalTotalE.value),
    }
    allResponses.value.set('D1-adj-bad-debt-reversal', item)
    saveImmediate([item])
  }

  /** 将本表核销合计同步写入 D1-4 坏账准备明细表核销变动列 */
  function syncWriteoffToD14(): void {
    if (isReadonly.value) return
    const item: ChecklistItem = {
      item_id: 'D1-adj-bad-debt-writeoff',
      conclusion: null,
      remark: String(writeoffTotalC.value),
    }
    allResponses.value.set('D1-adj-bad-debt-writeoff', item)
    saveImmediate([item])
  }

  // ─── Cleanup ───────────────────────────────────────────────────────────

  onBeforeUnmount(() => {
    if (reversalSaveTimer) {
      clearTimeout(reversalSaveTimer)
      persistReversalRows()
    }
    if (writeoffSaveTimer) {
      clearTimeout(writeoffSaveTimer)
      persistWriteoffRows()
    }
    if (totalsSaveTimer) {
      clearTimeout(totalsSaveTimer)
      persistTotals()
    }
  })

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // Section 1: 转回检查
    reversalRows,
    addReversalRow,
    removeReversalRow,
    updateReversalRow,
    reversalTotalE,
    reversalTotalF,

    // Section 2: 核销检查
    writeoffRows,
    addWriteoffRow,
    removeWriteoffRow,
    updateWriteoffRow,
    writeoffTotalC,

    // 跨Spec校验
    d14ReversalTotal,
    d14WriteoffTotal,
    eclCurrentTotal,
    reversalDiff,
    writeoffDiff,

    // 预警判断
    reversalExceedsProvision,
    writeoffExceedsProvision,
    missingReversalFields,
    missingWriteoffFields,

    // P1: 同步到D1-4
    syncReversalToD14,
    syncWriteoffToD14,

    // Section 3/4: 审计说明/结论
    auditNote,
    auditConclusion,
    saveAuditNote,
    saveAuditConclusion,

    // 加载状态
    isLoading,
  }
}
