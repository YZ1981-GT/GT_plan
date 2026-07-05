/**
 * useG2BadDebtDetail — G2-3 坏账准备明细（20列）
 *
 * 公式链：
 *   ECL金额 = EAD × PD × LGD
 *     - Stage1 用 12个月PD
 *     - Stage2/3 用 整个存续期PD
 *   差异 = ECL金额 - 企业计提
 *   本期变动 = 期末ECL - 上期ECL
 *
 * 特性：阶段下拉(Stage1/2/3) + 转移方向下拉 + 合计 + 动态行增删
 *
 * Spec: .kiro/specs/g2-interest-receivable/ Task 5.3
 * Requirements: 6.1~6.7
 */
import { ref, computed, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import {
  parseNum,
  calcECL,
  calcECLVariance,
} from './useG2IntRecFormulaEngine'
import type { ChecklistResponse } from './useF1FormData'

// ─── Types ────────────────────────────────────────────────────────────────────

export type ECLStage = 'Stage1' | 'Stage2' | 'Stage3'
export type TransferDirection = 'none' | '1→2' | '2→3' | '2→1' | '3→2'

/** 存储行（不含公式计算字段） */
interface StoredBadDebtRow {
  id: string
  seq: number
  investTarget: string          // 投资标的
  closingBalance: number        // 期末应收余额
  eclStage: ECLStage            // 减值阶段
  transferDirection: TransferDirection // 阶段转移方向
  pd12Month: number             // 12个月PD
  pdLifetime: number            // 整个存续期PD
  lgd: number                   // LGD
  ead: number                   // EAD
  companyProvision: number      // 企业计提
  previousECL: number           // 上期ECL
  transferIn: number            // 转入金额
  transferOut: number           // 转出金额
  writeOff: number              // 核销
  recovery: number              // 收回
  remark: string                // 备注
  indexRef: string              // 索引
}

/** 展示行（含公式计算字段） */
export interface BadDebtDetailRow {
  id: string
  seq: number
  investTarget: string
  closingBalance: number
  eclStage: ECLStage
  transferDirection: TransferDirection
  pd12Month: number
  pdLifetime: number
  lgd: number
  ead: number
  eclAmount: number             // ECL金额(公式)
  companyProvision: number
  variance: number              // 差异(公式)
  previousECL: number
  periodChange: number          // 本期变动(公式)
  transferIn: number
  transferOut: number
  writeOff: number
  recovery: number
  remark: string
  indexRef: string
}

export interface BadDebtTotals {
  closingBalance: number
  eclAmount: number
  companyProvision: number
  variance: number
  periodChange: number
}

// ─── Constants ────────────────────────────────────────────────────────────────

const STORAGE_KEY = 'G2-3-bad-debt-rows'

export const STAGE_OPTIONS: { value: ECLStage; label: string }[] = [
  { value: 'Stage1', label: 'Stage1' },
  { value: 'Stage2', label: 'Stage2' },
  { value: 'Stage3', label: 'Stage3' },
]

export const TRANSFER_DIRECTION_OPTIONS: { value: TransferDirection; label: string }[] = [
  { value: 'none', label: '无变化' },
  { value: '1→2', label: '1→2' },
  { value: '2→3', label: '2→3' },
  { value: '2→1', label: '2→1' },
  { value: '3→2', label: '3→2' },
]

// ─── Helpers ──────────────────────────────────────────────────────────────────

function generateId(): string {
  return `bdebt-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function safeParseRows(jsonStr: string | null | undefined): StoredBadDebtRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

/** 从存储行计算展示行（含公式字段） */
function computeRow(stored: StoredBadDebtRow): BadDebtDetailRow {
  // Stage1用12个月PD，Stage2/3用整个存续期PD
  const applicablePD = stored.eclStage === 'Stage1' ? stored.pd12Month : stored.pdLifetime
  const eclAmount = calcECL(stored.ead, applicablePD, stored.lgd)
  const variance = calcECLVariance(eclAmount, stored.companyProvision)
  const periodChange = eclAmount - stored.previousECL

  return {
    ...stored,
    eclAmount,
    variance,
    periodChange,
  }
}

function createEmptyStoredRow(seq: number): StoredBadDebtRow {
  return {
    id: generateId(),
    seq,
    investTarget: '',
    closingBalance: 0,
    eclStage: 'Stage1',
    transferDirection: 'none',
    pd12Month: 0,
    pdLifetime: 0,
    lgd: 0,
    ead: 0,
    companyProvision: 0,
    previousECL: 0,
    transferIn: 0,
    transferOut: 0,
    writeOff: 0,
    recovery: 0,
    remark: '',
    indexRef: '',
  }
}

// ─── Composable ───────────────────────────────────────────────────────────────

export interface UseG2BadDebtDetailOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}

export function useG2BadDebtDetail(options: UseG2BadDebtDetailOptions) {
  const { allResponses, isReadonly } = options
  const readonly = isReadonly ?? ref(false)

  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  // ─── 从 allResponses 解析行数据 ──────────────────────────────────────

  const storedRows = computed<StoredBadDebtRow[]>(() => {
    const resp = allResponses.value.get(STORAGE_KEY)
    return safeParseRows(resp?.remark)
  })

  /** 数据行（公式自动计算） */
  const dataRows: ComputedRef<BadDebtDetailRow[]> = computed(() =>
    storedRows.value.map((s) => computeRow(s)),
  )

  /** 合计行 */
  const totals: ComputedRef<BadDebtTotals> = computed(() => {
    const rows = dataRows.value
    return {
      closingBalance: rows.reduce((sum, r) => sum + r.closingBalance, 0),
      eclAmount: rows.reduce((sum, r) => sum + r.eclAmount, 0),
      companyProvision: rows.reduce((sum, r) => sum + r.companyProvision, 0),
      variance: rows.reduce((sum, r) => sum + r.variance, 0),
      periodChange: rows.reduce((sum, r) => sum + r.periodChange, 0),
    }
  })

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

  function updateCell(rowId: string, field: keyof StoredBadDebtRow, value: string | number): void {
    if (readonly.value) return
    const current = safeParseRows(allResponses.value.get(STORAGE_KEY)?.remark)
    const idx = current.findIndex((r) => r.id === rowId)
    if (idx === -1) return

    const numericFields = [
      'closingBalance', 'pd12Month', 'pdLifetime', 'lgd', 'ead',
      'companyProvision', 'previousECL', 'transferIn', 'transferOut',
      'writeOff', 'recovery',
    ] as const
    if ((numericFields as readonly string[]).includes(field)) {
      ;(current[idx] as any)[field] = typeof value === 'number' ? value : parseNum(value)
    } else {
      ;(current[idx] as any)[field] = value
    }

    persistRows(current)
  }

  // ─── 持久化 ─────────────────────────────────────────────────────────────

  function persistRows(rows: StoredBadDebtRow[]): void {
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
    totals,
    addRow,
    removeRow,
    updateCell,
  }
}

export default useG2BadDebtDetail
