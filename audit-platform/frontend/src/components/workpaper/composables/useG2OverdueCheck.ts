/**
 * useG2OverdueCheck — G2-6 长期未收回检查（13列）
 *
 * 公式链：
 *   逾期天数 = MAX(0, 当前日期 - 约定收回日)
 *
 * 阶段转移建议：
 *   逾期>180天 → 建议转Stage3（红色高亮）
 *   逾期>90天  → 建议转Stage2（橙色高亮）
 *
 * 风险等级下拉：低/中/高/极高
 * 预计可收回性下拉：全额可收回/部分可收回/很可能无法收回/无法收回
 *
 * Spec: .kiro/specs/g2-interest-receivable/ Task 5.3
 * Requirements: 9.1~9.8
 */
import { ref, computed, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import {
  parseNum,
  calcOverdueDays,
} from './useG2IntRecFormulaEngine'
import type { ChecklistResponse } from './useF1FormData'

// ─── Types ────────────────────────────────────────────────────────────────────

export type Recoverability = 'full' | 'partial' | 'unlikely' | 'irrecoverable'
export type RiskLevel = 'low' | 'medium' | 'high' | 'extreme'

/** 存储行（不含公式计算字段） */
interface StoredOverdueRow {
  id: string
  seq: number
  investTarget: string          // 投资标的
  receivableAmount: number      // 应收金额
  agreedRecoveryDate: string    // 约定收回日
  overdueReason: string         // 逾期原因
  debtorCreditStatus: string    // 债务方信用状况
  collectionMeasures: string    // 催收措施
  recoverability: Recoverability // 预计可收回性
  needStageTransfer: string     // 是否需转Stage2/3
  riskLevel: RiskLevel          // 风险等级
  auditSuggestion: string       // 审计建议
  remark: string                // 备注
}

/** 展示行（含公式计算字段） */
export interface OverdueCheckRow {
  id: string
  seq: number
  investTarget: string
  receivableAmount: number
  agreedRecoveryDate: string
  overdueDays: number           // 逾期天数(公式)
  overdueReason: string
  debtorCreditStatus: string
  collectionMeasures: string
  recoverability: Recoverability
  needStageTransfer: string
  riskLevel: RiskLevel
  auditSuggestion: string
  remark: string
}

/** 阶段转移建议 */
export type StageSuggestion = 'stage3' | 'stage2' | 'none'

export interface OverdueCheckSummary {
  overdueCount: number          // 逾期笔数
  overdueTotalAmount: number    // 逾期总金额
  highRiskCount: number         // 高风险笔数
}

// ─── Constants ────────────────────────────────────────────────────────────────

const STORAGE_KEY = 'G2-6-overdue-rows'
const STAGE3_THRESHOLD = 180
const STAGE2_THRESHOLD = 90

export const RECOVERABILITY_OPTIONS: { value: Recoverability; label: string }[] = [
  { value: 'full', label: '全额可收回' },
  { value: 'partial', label: '部分可收回' },
  { value: 'unlikely', label: '很可能无法收回' },
  { value: 'irrecoverable', label: '无法收回' },
]

export const RISK_LEVEL_OPTIONS: { value: RiskLevel; label: string }[] = [
  { value: 'low', label: '低' },
  { value: 'medium', label: '中' },
  { value: 'high', label: '高' },
  { value: 'extreme', label: '极高' },
]

// ─── Helpers ──────────────────────────────────────────────────────────────────

function generateId(): string {
  return `overdue-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function safeParseRows(jsonStr: string | null | undefined): StoredOverdueRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

/** 从存储行计算展示行（含逾期天数公式） */
function computeRow(stored: StoredOverdueRow): OverdueCheckRow {
  const overdueDays = calcOverdueDays(stored.agreedRecoveryDate)

  return {
    ...stored,
    overdueDays,
  }
}

function createEmptyStoredRow(seq: number): StoredOverdueRow {
  return {
    id: generateId(),
    seq,
    investTarget: '',
    receivableAmount: 0,
    agreedRecoveryDate: '',
    overdueReason: '',
    debtorCreditStatus: '',
    collectionMeasures: '',
    recoverability: 'full',
    needStageTransfer: '',
    riskLevel: 'low',
    auditSuggestion: '',
    remark: '',
  }
}

// ─── Composable ───────────────────────────────────────────────────────────────

export interface UseG2OverdueCheckOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}

export function useG2OverdueCheck(options: UseG2OverdueCheckOptions) {
  const { allResponses, isReadonly } = options
  const readonly = isReadonly ?? ref(false)

  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  // ─── 从 allResponses 解析行数据 ──────────────────────────────────────

  const storedRows = computed<StoredOverdueRow[]>(() => {
    const resp = allResponses.value.get(STORAGE_KEY)
    return safeParseRows(resp?.remark)
  })

  /** 数据行（公式自动计算） */
  const dataRows: ComputedRef<OverdueCheckRow[]> = computed(() =>
    storedRows.value.map((s) => computeRow(s)),
  )

  /** 底部汇总 */
  const summary: ComputedRef<OverdueCheckSummary> = computed(() => {
    const rows = dataRows.value
    const overdueRows = rows.filter((r) => r.overdueDays > 0)
    return {
      overdueCount: overdueRows.length,
      overdueTotalAmount: overdueRows.reduce((sum, r) => sum + r.receivableAmount, 0),
      highRiskCount: rows.filter((r) => r.riskLevel === 'high' || r.riskLevel === 'extreme').length,
    }
  })

  // ─── 阶段转移建议判定 ──────────────────────────────────────────────────

  /** 根据逾期天数返回阶段转移建议 */
  function getStageSuggestion(row: OverdueCheckRow): StageSuggestion {
    if (row.overdueDays > STAGE3_THRESHOLD) return 'stage3'
    if (row.overdueDays > STAGE2_THRESHOLD) return 'stage2'
    return 'none'
  }

  /** 逾期>180天红色 / >90天橙色 */
  function getOverdueHighlight(row: OverdueCheckRow): 'red' | 'orange' | 'none' {
    if (row.overdueDays > STAGE3_THRESHOLD) return 'red'
    if (row.overdueDays > STAGE2_THRESHOLD) return 'orange'
    return 'none'
  }

  // ─── 动态行增删 ────────────────────────────────────────────────────────

  function addRow(): void {
    if (readonly.value) return
    const current = safeParseRows(allResponses.value.get(STORAGE_KEY)?.remark)
    const nextSeq = current.length > 0 ? Math.max(...current.map((r) => r.seq)) + 1 : 1
    const newRow = createEmptyStoredRow(nextSeq)
    current.push(newRow)
    persistRows(current)
  }

  function removeRow(id: string): void {
    if (readonly.value) return
    const current = safeParseRows(allResponses.value.get(STORAGE_KEY)?.remark)
    const filtered = current.filter((r) => r.id !== id)
    filtered.forEach((r, i) => { r.seq = i + 1 })
    persistRows(filtered)
  }

  // ─── 单元格编辑 ─────────────────────────────────────────────────────────

  function updateCell(rowId: string, field: keyof StoredOverdueRow, value: string | number): void {
    if (readonly.value) return
    const current = safeParseRows(allResponses.value.get(STORAGE_KEY)?.remark)
    const idx = current.findIndex((r) => r.id === rowId)
    if (idx === -1) return

    const numericFields = ['receivableAmount'] as const
    if ((numericFields as readonly string[]).includes(field)) {
      ;(current[idx] as any)[field] = typeof value === 'number' ? value : parseNum(value)
    } else {
      ;(current[idx] as any)[field] = value
    }

    persistRows(current)
  }

  // ─── 持久化 ─────────────────────────────────────────────────────────────

  function persistRows(rows: StoredOverdueRow[]): void {
    const json = JSON.stringify(rows)
    allResponses.value.set(STORAGE_KEY, {
      item_id: STORAGE_KEY,
      conclusion: null,
      remark: json,
    })
    debounceSave()
  }

  function debounceSave(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      flushSave()
    }, 2000)
  }

  function flushSave(): void {
    try {
      const items = [allResponses.value.get(STORAGE_KEY)].filter(Boolean)
      window.dispatchEvent(new CustomEvent('g2:save-items', { detail: { items } }))
    } catch { /* silent */ }
  }

  onBeforeUnmount(() => {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
      flushSave()
    }
  })

  return {
    dataRows,
    summary,
    getStageSuggestion,
    getOverdueHighlight,
    addRow,
    removeRow,
    updateCell,
  }
}

export default useG2OverdueCheck
