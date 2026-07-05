/**
 * useG2Adjudication — G2-1 审定表（借方科目 1132 应收利息）
 *
 * 借方公式链：
 *   期初审定 = 期初未审 + 期初AJE + 期初RJE
 *   期末未审 = 期初审定 + 借方发生额 - 贷方发生额
 *   期末审定 = 期末未审 + 期末AJE + 期末RJE
 *
 * 行结构：债权投资利息/其他债权投资利息/定期存款利息/其他 + 合计 + 试算表数 + 差异
 *
 * Spec: .kiro/specs/g2-interest-receivable/ Task 4.1
 * Requirements: 3.1~3.9
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import {
  parseNum,
  calcDebitBalance,
  calcAdjustedAmount,
  calcSubtotal,
} from './useG2IntRecFormulaEngine'
import type { ChecklistResponse } from './useF1FormData'

/** 科目：应收利息 */
export const G2_ACCOUNT_CODE = '1132'

/** 审定表行项目 */
export const G2_ROW_ITEMS = [
  { rowKey: 'bond-interest', label: '债权投资利息' },
  { rowKey: 'other-bond-interest', label: '其他债权投资利息' },
  { rowKey: 'deposit-interest', label: '定期存款利息' },
  { rowKey: 'other', label: '其他' },
] as const

export interface G2AdjudicationRow {
  id: string
  item: string
  openingUnadjusted: number
  openingAJE: number
  openingRJE: number
  openingAdjusted: number
  closingUnadjusted: number
  closingAJE: number
  closingRJE: number
  closingAdjusted: number
  indexRef: string
}

interface StoredG2AdjRow {
  rowKey: string
  label: string
  openingUnadjusted: number
  openingAJE: number
  openingRJE: number
  periodDebit: number
  periodCredit: number
  closingAJE: number
  closingRJE: number
  indexRef: string
}

const ADJ_STORAGE_KEY = 'G2-1-adj-rows'
const TB_STORAGE_KEY = 'G2-1-adj-tb-1132'
const NOTE_KEY = 'G2-1-adj-note'
const CONCLUSION_KEY = 'G2-1-adj-conclusion'

const DEFAULT_STORED: StoredG2AdjRow[] = G2_ROW_ITEMS.map((item) => ({
  rowKey: item.rowKey,
  label: item.label,
  openingUnadjusted: 0,
  openingAJE: 0,
  openingRJE: 0,
  periodDebit: 0,
  periodCredit: 0,
  closingAJE: 0,
  closingRJE: 0,
  indexRef: '',
}))

function safeParseRows(jsonStr: string | null | undefined): StoredG2AdjRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function ensureDefaultRows(stored: StoredG2AdjRow[]): StoredG2AdjRow[] {
  if (stored.length === 0) return DEFAULT_STORED.map((r) => ({ ...r }))
  const keys = new Set(stored.map((r) => r.rowKey))
  const merged = [...stored]
  for (const def of DEFAULT_STORED) {
    if (!keys.has(def.rowKey)) merged.push({ ...def })
  }
  return merged
}

/** 从存储行计算展示行（含公式字段） */
function computeRow(stored: StoredG2AdjRow): G2AdjudicationRow {
  const openingAdjusted = calcAdjustedAmount(stored.openingUnadjusted, stored.openingAJE, stored.openingRJE)
  // 借方科目：期末未审 = 期初审定 + 借方 - 贷方
  const closingUnadjusted = calcDebitBalance(openingAdjusted, stored.periodDebit, stored.periodCredit)
  const closingAdjusted = calcAdjustedAmount(closingUnadjusted, stored.closingAJE, stored.closingRJE)
  return {
    id: stored.rowKey,
    item: stored.label,
    openingUnadjusted: stored.openingUnadjusted,
    openingAJE: stored.openingAJE,
    openingRJE: stored.openingRJE,
    openingAdjusted,
    closingUnadjusted,
    closingAJE: stored.closingAJE,
    closingRJE: stored.closingRJE,
    closingAdjusted,
    indexRef: stored.indexRef,
  }
}

export interface UseG2AdjudicationOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}

export function useG2Adjudication(options: UseG2AdjudicationOptions) {
  const { wpId, projectId, allResponses, isReadonly } = options
  const readonly = isReadonly ?? ref(false)

  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  const auditNote = ref('')
  const auditConclusion = ref('')

  // ─── 从 allResponses 解析行数据 ────────────────────────────────────────
  const storedRows = computed<StoredG2AdjRow[]>(() => {
    const resp = allResponses.value.get(ADJ_STORAGE_KEY)
    return ensureDefaultRows(safeParseRows(resp?.remark))
  })

  /** 数据行（公式自动计算） */
  const dataRows: ComputedRef<G2AdjudicationRow[]> = computed(() =>
    storedRows.value.map((s) => computeRow(s)),
  )

  /** 合计行 */
  const subtotalRow: ComputedRef<G2AdjudicationRow> = computed(() => {
    const rows = dataRows.value
    const stored: StoredG2AdjRow = {
      rowKey: 'subtotal',
      label: '合计',
      openingUnadjusted: calcSubtotal(rows.map((r) => r.openingUnadjusted)),
      openingAJE: calcSubtotal(rows.map((r) => r.openingAJE)),
      openingRJE: calcSubtotal(rows.map((r) => r.openingRJE)),
      periodDebit: calcSubtotal(storedRows.value.map((r) => r.periodDebit)),
      periodCredit: calcSubtotal(storedRows.value.map((r) => r.periodCredit)),
      closingAJE: calcSubtotal(rows.map((r) => r.closingAJE)),
      closingRJE: calcSubtotal(rows.map((r) => r.closingRJE)),
      indexRef: '',
    }
    return computeRow(stored)
  })

  /** 试算表取数（科目1132） */
  const trialBalanceAmount: ComputedRef<number> = computed(() =>
    parseNum(allResponses.value.get(TB_STORAGE_KEY)?.remark),
  )

  /** 差异 = 审定 - 试算表数 */
  const variance: ComputedRef<number> = computed(() =>
    subtotalRow.value.closingAdjusted - trialBalanceAmount.value,
  )

  /** 差异≠0红色标记 */
  const hasVarianceHighlight: ComputedRef<boolean> = computed(() =>
    Math.abs(variance.value) > 0.005,
  )

  // ─── 审计备注/结论 同步 ─────────────────────────────────────────────
  watch(
    () => allResponses.value.get(NOTE_KEY)?.remark,
    (v) => { auditNote.value = v || '' },
    { immediate: true },
  )
  watch(
    () => allResponses.value.get(CONCLUSION_KEY)?.remark,
    (v) => { auditConclusion.value = v || '' },
    { immediate: true },
  )

  // ─── EventBus: publish substantive:adjudicated（科目1132）───────────────
  function publishAdjudicated(): void {
    const amount = subtotalRow.value.closingAdjusted
    const payload = {
      wpCode: 'G2',
      accountCode: G2_ACCOUNT_CODE,
      adjudicatedAmount: amount,
      auditedAmount: amount,
    }
    try {
      window.dispatchEvent(new CustomEvent('substantive:adjudicated', { detail: payload }))
    } catch { /* EventBus publish 失败不阻塞编辑 */ }
  }

  // 审定合计变化时自动发布
  watch(
    () => subtotalRow.value.closingAdjusted,
    () => { publishAdjudicated() },
  )

  // ─── 单元格编辑 ─────────────────────────────────────────────────────
  function updateCell(rowKey: string, field: string, value: number | string): void {
    if (readonly.value) return
    const stored = ensureDefaultRows(safeParseRows(allResponses.value.get(ADJ_STORAGE_KEY)?.remark))
    const idx = stored.findIndex((r) => r.rowKey === rowKey)
    if (idx === -1) return
    if (field === 'indexRef') {
      stored[idx].indexRef = String(value ?? '')
    } else {
      ;(stored[idx] as any)[field] = typeof value === 'number' ? value : parseNum(value)
    }
    persistRows(stored)
  }

  /** 设置试算表取数值 */
  function setTrialBalance(amount: number): void {
    allResponses.value.set(TB_STORAGE_KEY, {
      item_id: TB_STORAGE_KEY,
      conclusion: null,
      remark: String(amount),
    })
    debounceSave()
  }

  // ─── 持久化 ─────────────────────────────────────────────────────────
  function persistRows(rows: StoredG2AdjRow[]): void {
    const json = JSON.stringify(rows)
    allResponses.value.set(ADJ_STORAGE_KEY, {
      item_id: ADJ_STORAGE_KEY,
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
      const items = [
        allResponses.value.get(ADJ_STORAGE_KEY),
        allResponses.value.get(NOTE_KEY),
        allResponses.value.get(CONCLUSION_KEY),
        allResponses.value.get(TB_STORAGE_KEY),
      ].filter(Boolean)
      window.dispatchEvent(new CustomEvent('g2:save-items', { detail: { items } }))
    } catch { /* silent */ }
  }

  watch(auditNote, (val) => {
    allResponses.value.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: val })
    debounceSave()
  })

  watch(auditConclusion, (val) => {
    allResponses.value.set(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: null, remark: val })
    debounceSave()
  })

  onBeforeUnmount(() => {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
      flushSave()
    }
  })

  return {
    dataRows,
    subtotalRow,
    trialBalanceAmount,
    variance,
    hasVarianceHighlight,
    auditNote,
    auditConclusion,
    updateCell,
    setTrialBalance,
    publishAdjudicated,
  }
}

export default useG2Adjudication
