/**
 * useG3Adjudication — G3-1 审定表（借方科目 1131 应收股利）
 *
 * 借方公式链：
 *   期初审定 = 期初未审 + 期初AJE + 期初RJE
 *   期末未审 = 期初审定 + 本期宣告(借方) - 本期收回(贷方)
 *   期末审定 = 期末未审 + 期末AJE + 期末RJE
 *
 * 行结构：按被投资方逐行（动态增删）+ 合计 + 试算表数 + 差异
 *
 * Spec: .kiro/specs/g3-dividend-receivable/ Task 4.1
 * Requirements: 3.1~3.10
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import {
  parseNum,
  calcDebitBalance,
  calcAdjustedAmount,
  calcSubtotal,
} from './useG3DivRecFormulaEngine'
import type { ChecklistResponse } from './useF1FormData'

/** 科目：应收股利 */
export const G3_ACCOUNT_CODE = '1131'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface G3AdjudicationRow {
  id: string
  investeeName: string          // 被投资方
  shareholdingRatio: number     // 持股比例
  openingUnadjusted: number
  openingAJE: number
  openingRJE: number
  openingAdjusted: number       // 公式：期初未审 + AJE + RJE
  closingUnadjusted: number     // 借方公式：期初审定 + 本期宣告 - 本期收回
  closingAJE: number
  closingRJE: number
  closingAdjusted: number       // 公式：期末未审 + AJE + RJE
  currentDeclared: number       // 本期宣告(借方)
  currentReceived: number       // 本期收回(贷方)
  remark: string
  indexRef: string
}

/** 存储在 checklist_responses 中的行原始数据 */
interface StoredG3AdjRow {
  id: string
  investeeName: string
  shareholdingRatio: number
  openingUnadjusted: number
  openingAJE: number
  openingRJE: number
  currentDeclared: number
  currentReceived: number
  closingAJE: number
  closingRJE: number
  remark: string
  indexRef: string
}

// ─── Storage keys ────────────────────────────────────────────────────────────

const ADJ_STORAGE_KEY = 'G3-1-adj-rows'
const TB_STORAGE_KEY = 'G3-1-adj-tb-1131'
const NOTE_KEY = 'G3-1-adj-note'
const CONCLUSION_KEY = 'G3-1-adj-conclusion'

// ─── Helpers ─────────────────────────────────────────────────────────────────

function safeParseRows(jsonStr: string | null | undefined): StoredG3AdjRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

/** 从存储行计算展示行（含公式字段） */
function computeRow(stored: StoredG3AdjRow): G3AdjudicationRow {
  const openingAdjusted = calcAdjustedAmount(stored.openingUnadjusted, stored.openingAJE, stored.openingRJE)
  // 借方科目：期末未审 = 期初审定 + 本期宣告(借方) - 本期收回(贷方)
  const closingUnadjusted = calcDebitBalance(openingAdjusted, stored.currentDeclared, stored.currentReceived)
  const closingAdjusted = calcAdjustedAmount(closingUnadjusted, stored.closingAJE, stored.closingRJE)
  return {
    id: stored.id,
    investeeName: stored.investeeName,
    shareholdingRatio: stored.shareholdingRatio,
    openingUnadjusted: stored.openingUnadjusted,
    openingAJE: stored.openingAJE,
    openingRJE: stored.openingRJE,
    openingAdjusted,
    closingUnadjusted,
    closingAJE: stored.closingAJE,
    closingRJE: stored.closingRJE,
    closingAdjusted,
    currentDeclared: stored.currentDeclared,
    currentReceived: stored.currentReceived,
    remark: stored.remark,
    indexRef: stored.indexRef,
  }
}

function makeEmptyStoredRow(id: string, investeeName: string): StoredG3AdjRow {
  return {
    id,
    investeeName,
    shareholdingRatio: 0,
    openingUnadjusted: 0,
    openingAJE: 0,
    openingRJE: 0,
    currentDeclared: 0,
    currentReceived: 0,
    closingAJE: 0,
    closingRJE: 0,
    remark: '',
    indexRef: '',
  }
}

// ─── Composable options ──────────────────────────────────────────────────────

export interface UseG3AdjudicationOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useG3Adjudication(options: UseG3AdjudicationOptions) {
  const { wpId, projectId, allResponses, isReadonly } = options
  const readonly = isReadonly ?? ref(false)

  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  const auditNote = ref('')
  const auditConclusion = ref('')

  // ─── 从 allResponses 解析行数据 ────────────────────────────────────────
  const storedRows = computed<StoredG3AdjRow[]>(() => {
    const resp = allResponses.value.get(ADJ_STORAGE_KEY)
    return safeParseRows(resp?.remark)
  })

  /** 数据行（公式自动计算） */
  const dataRows: ComputedRef<G3AdjudicationRow[]> = computed(() =>
    storedRows.value.map((s) => computeRow(s)),
  )

  /** 合计行 */
  const subtotalRow: ComputedRef<G3AdjudicationRow> = computed(() => {
    const rows = dataRows.value
    const stored: StoredG3AdjRow = {
      id: 'subtotal',
      investeeName: '合计',
      shareholdingRatio: 0,
      openingUnadjusted: calcSubtotal(rows.map((r) => r.openingUnadjusted)),
      openingAJE: calcSubtotal(rows.map((r) => r.openingAJE)),
      openingRJE: calcSubtotal(rows.map((r) => r.openingRJE)),
      currentDeclared: calcSubtotal(rows.map((r) => r.currentDeclared)),
      currentReceived: calcSubtotal(rows.map((r) => r.currentReceived)),
      closingAJE: calcSubtotal(rows.map((r) => r.closingAJE)),
      closingRJE: calcSubtotal(rows.map((r) => r.closingRJE)),
      remark: '',
      indexRef: '',
    }
    return computeRow(stored)
  })

  /** 试算表取数（科目1131） */
  const trialBalanceAmount: ComputedRef<number> = computed(() =>
    parseNum(allResponses.value.get(TB_STORAGE_KEY)?.remark),
  )

  /** 差异 = 期末审定合计 - 试算表数 */
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

  // ─── EventBus: publish substantive:adjudicated（科目1131）───────────────
  function publishAdjudicated(): void {
    const amount = subtotalRow.value.closingAdjusted
    const payload = {
      wpCode: 'G3',
      accountCode: G3_ACCOUNT_CODE,
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
  function updateCell(rowId: string, field: string, value: number | string): void {
    if (readonly.value) return
    const stored = safeParseRows(allResponses.value.get(ADJ_STORAGE_KEY)?.remark)
    const idx = stored.findIndex((r) => r.id === rowId)
    if (idx === -1) return
    if (field === 'indexRef' || field === 'remark' || field === 'investeeName') {
      ;(stored[idx] as any)[field] = String(value ?? '')
    } else {
      ;(stored[idx] as any)[field] = typeof value === 'number' ? value : parseNum(value)
    }
    persistRows(stored)
  }

  // ─── 动态行增删（新增弹ElMessageBox.prompt输入被投资方名称）────────────
  async function addRow(): Promise<void> {
    if (readonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('请输入被投资方名称', '新增被投资方', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        inputPattern: /\S+/,
        inputErrorMessage: '名称不能为空',
      })
      const stored = safeParseRows(allResponses.value.get(ADJ_STORAGE_KEY)?.remark)
      const newRow = makeEmptyStoredRow(String(Date.now()), value.trim())
      stored.push(newRow)
      persistRows(stored)
    } catch { /* 用户取消 */ }
  }

  function removeRow(rowId: string): void {
    if (readonly.value) return
    const stored = safeParseRows(allResponses.value.get(ADJ_STORAGE_KEY)?.remark)
    const filtered = stored.filter((r) => r.id !== rowId)
    persistRows(filtered)
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
  function persistRows(rows: StoredG3AdjRow[]): void {
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
      window.dispatchEvent(new CustomEvent('g3:save-items', { detail: { items } }))
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
    addRow,
    removeRow,
    setTrialBalance,
    publishAdjudicated,
  }
}

export default useG3Adjudication
