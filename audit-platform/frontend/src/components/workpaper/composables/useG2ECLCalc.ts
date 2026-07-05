/**
 * useG2ECLCalc — G2-7 坏账准备测算（72行×18列→2区段Tab）
 *
 * 2区段共享行数据（单数组）：
 *   - 阶段划分(9列)：序号|投资标的|期末余额|信用等级|显著增加|已减值|划分阶段(公式)|上期阶段|变动说明
 *   - ECL测算(9列)：12个月PD|存续期PD|适用PD(公式)|LGD|EAD|ECL金额(公式)|企业计提|差异(公式)|测算结论
 *
 * 公式链：
 *   划分阶段 = determineStage(isImpaired, significantIncrease)
 *   适用PD = Stage1→12个月PD / Stage2,3→整个存续期PD
 *   ECL金额 = EAD × 适用PD × LGD
 *   差异 = ECL金额 - 企业计提
 *
 * 特性：2区段Tab行同步 + 阶段判定公式 + 差异>10%橙色 + 合计 + 动态行增删
 *
 * Spec: .kiro/specs/g2-interest-receivable/ Task 5.4
 * Requirements: 10.1~10.10
 */
import { ref, computed, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import {
  parseNum,
  calcECL,
  calcECLVariance,
  determineStage,
} from './useG2IntRecFormulaEngine'
import type { ChecklistResponse } from './useF1FormData'

// ─── Types ────────────────────────────────────────────────────────────────────

/** 存储行（不含公式计算字段，两区段共享） */
interface StoredECLCalcRow {
  id: string
  seq: number
  // 阶段划分区段
  investTarget: string          // 投资标的
  closingBalance: number        // 期末余额
  creditRating: string          // 信用风险等级
  significantIncrease: boolean  // 是否信用风险显著增加
  isImpaired: boolean           // 是否已发生减值
  previousStage: 1 | 2 | 3     // 上期阶段
  stageChangeNote: string       // 阶段变动说明
  // ECL测算区段
  pd12Month: number             // 12个月PD
  pdLifetime: number            // 整个存续期PD
  lgd: number                   // LGD
  ead: number                   // EAD
  companyProvision: number      // 企业计提
  conclusion: string            // 测算结论
}

/** 展示行（含公式计算字段） */
export interface ECLCalcRow {
  id: string
  seq: number
  // 阶段划分区段
  investTarget: string
  closingBalance: number
  creditRating: string
  significantIncrease: boolean
  isImpaired: boolean
  determinedStage: 1 | 2 | 3   // 划分阶段(公式)
  previousStage: 1 | 2 | 3
  stageChangeNote: string
  // ECL测算区段
  pd12Month: number
  pdLifetime: number
  applicablePD: number          // 适用PD(公式)
  lgd: number
  ead: number
  eclAmount: number             // ECL金额(公式)
  companyProvision: number
  eclVariance: number           // 差异(公式)
  conclusion: string
}

export interface ECLCalcTotals {
  closingBalance: number
  ead: number
  eclAmount: number
  companyProvision: number
  eclVariance: number
}

// ─── Constants ────────────────────────────────────────────────────────────────

const STORAGE_KEY = 'G2-7-ecl-calc-rows'
const VARIANCE_RATIO_THRESHOLD = 0.10 // 差异/企业计提>10%时橙色

// ─── Helpers ──────────────────────────────────────────────────────────────────

function generateId(): string {
  return `eclcalc-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function safeParseRows(jsonStr: string | null | undefined): StoredECLCalcRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

/** 从存储行计算展示行（含公式字段） */
function computeRow(stored: StoredECLCalcRow): ECLCalcRow {
  const determinedStage = determineStage(stored.isImpaired, stored.significantIncrease)
  // Stage1用12个月PD，Stage2/3用整个存续期PD
  const applicablePD = determinedStage === 1 ? stored.pd12Month : stored.pdLifetime
  const eclAmount = calcECL(stored.ead, applicablePD, stored.lgd)
  const eclVariance = calcECLVariance(eclAmount, stored.companyProvision)

  return {
    ...stored,
    determinedStage,
    applicablePD,
    eclAmount,
    eclVariance,
  }
}

function createEmptyStoredRow(seq: number): StoredECLCalcRow {
  return {
    id: generateId(),
    seq,
    investTarget: '',
    closingBalance: 0,
    creditRating: '',
    significantIncrease: false,
    isImpaired: false,
    previousStage: 1,
    stageChangeNote: '',
    pd12Month: 0,
    pdLifetime: 0,
    lgd: 0,
    ead: 0,
    companyProvision: 0,
    conclusion: '',
  }
}

// ─── Composable ───────────────────────────────────────────────────────────────

export interface UseG2ECLCalcOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}

export function useG2ECLCalc(options: UseG2ECLCalcOptions) {
  const { allResponses, isReadonly } = options
  const readonly = isReadonly ?? ref(false)

  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  // ─── 从 allResponses 解析行数据 ──────────────────────────────────────

  const storedRows = computed<StoredECLCalcRow[]>(() => {
    const resp = allResponses.value.get(STORAGE_KEY)
    return safeParseRows(resp?.remark)
  })

  /** 数据行（公式自动计算，两区段共享同一数组） */
  const dataRows: ComputedRef<ECLCalcRow[]> = computed(() =>
    storedRows.value.map((s) => computeRow(s)),
  )

  /** 合计行 */
  const totals: ComputedRef<ECLCalcTotals> = computed(() => {
    const rows = dataRows.value
    return {
      closingBalance: rows.reduce((sum, r) => sum + r.closingBalance, 0),
      ead: rows.reduce((sum, r) => sum + r.ead, 0),
      eclAmount: rows.reduce((sum, r) => sum + r.eclAmount, 0),
      companyProvision: rows.reduce((sum, r) => sum + r.companyProvision, 0),
      eclVariance: rows.reduce((sum, r) => sum + r.eclVariance, 0),
    }
  })

  // ─── 差异高亮判断 ──────────────────────────────────────────────────────

  /** |差异|/企业计提 > 10% → 橙色标记 */
  function isVarianceWarning(row: ECLCalcRow): boolean {
    if (row.companyProvision === 0) {
      // 企业计提为0但ECL不为0，视为异常
      return row.eclAmount > 0
    }
    return Math.abs(row.eclVariance) / Math.abs(row.companyProvision) > VARIANCE_RATIO_THRESHOLD
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

  function updateCell(rowId: string, field: keyof StoredECLCalcRow, value: string | number | boolean): void {
    if (readonly.value) return
    const current = safeParseRows(allResponses.value.get(STORAGE_KEY)?.remark)
    const idx = current.findIndex((r) => r.id === rowId)
    if (idx === -1) return

    const numericFields = [
      'closingBalance', 'pd12Month', 'pdLifetime', 'lgd', 'ead', 'companyProvision',
    ] as const
    const booleanFields = ['significantIncrease', 'isImpaired'] as const

    if ((numericFields as readonly string[]).includes(field)) {
      ;(current[idx] as any)[field] = typeof value === 'number' ? value : parseNum(String(value))
    } else if ((booleanFields as readonly string[]).includes(field)) {
      ;(current[idx] as any)[field] = Boolean(value)
    } else if (field === 'previousStage') {
      const stage = typeof value === 'number' ? value : Number(value)
      ;(current[idx] as any)[field] = [1, 2, 3].includes(stage) ? stage : 1
    } else {
      ;(current[idx] as any)[field] = value
    }

    persistRows(current)
  }

  // ─── 持久化 ─────────────────────────────────────────────────────────────

  function persistRows(rows: StoredECLCalcRow[]): void {
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
    isVarianceWarning,
    addRow,
    removeRow,
    updateCell,
  }
}

export default useG2ECLCalc
