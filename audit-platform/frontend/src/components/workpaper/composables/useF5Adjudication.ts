/**
 * useF5Adjudication — F5-1 审定表核心逻辑（借方/损益类科目 6401 营业成本）
 *
 * Spec: .kiro/specs/f5-cost-of-sales/ Task 4.1
 *
 * 损益类特点：无"期初期末"概念，只有"本期/上期"发生额对比。
 * 审定公式：审定 = 未审 + AJE(账项调整) + RJE(重分类)，本期/上期各自独立计算。
 * 结构：主营业务成本(品种1~N)/小计 + 其他业务成本(品种1~N)/小计 + 总计/试算表数/差异。
 * EventBus: publish substantive:adjudicated(accountCode='6401')
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import { parseNum, calcAdjustedAmount, calcChangeAmount, calcSubtotal } from './useF5CosOfFormulaEngine'
import type { ChecklistResponse } from './useF1FormData'

export interface UseF5AdjudicationOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}

/** 损益类审定行（本期/上期各含 未审/AJE/RJE/审定，无期初期末） */
export interface F5AdjudicationRow {
  rowKey: string
  label: string
  isFixed: boolean
  // 本期
  currentUnadjusted: number
  currentAje: number
  currentRje: number
  currentAdjusted: number // 公式 = 未审 + AJE + RJE
  // 上期
  priorUnadjusted: number
  priorAje: number
  priorRje: number
  priorAdjusted: number // 公式 = 未审 + AJE + RJE
  // 变动
  changeAmount: number // 公式 = 本期审定 - 上期审定
  indexRef: string
  isEditable: boolean
}

/** 持久化用（不含计算字段） */
interface StoredF5AdjRow {
  rowKey: string
  label: string
  isFixed: boolean
  currentUnadjusted: number
  currentAje: number
  currentRje: number
  priorUnadjusted: number
  priorAje: number
  priorRje: number
  indexRef: string
}

const MAIN_STORAGE_KEY = 'F5-1-adj-main-rows'
const OTHER_STORAGE_KEY = 'F5-1-adj-other-rows'
const TB_STORAGE_KEY = 'F5-1-adj-tb-6401'
const NOTE_STORAGE_KEY = 'F5-1-adj-note'
const CONCLUSION_STORAGE_KEY = 'F5-1-adj-conclusion'

const DEFAULT_MAIN_ROWS: StoredF5AdjRow[] = [
  { rowKey: 'main-product-1', label: '产品A', isFixed: false, currentUnadjusted: 0, currentAje: 0, currentRje: 0, priorUnadjusted: 0, priorAje: 0, priorRje: 0, indexRef: '' },
]

const DEFAULT_OTHER_ROWS: StoredF5AdjRow[] = [
  { rowKey: 'other-1', label: '材料销售成本', isFixed: false, currentUnadjusted: 0, currentAje: 0, currentRje: 0, priorUnadjusted: 0, priorAje: 0, priorRje: 0, indexRef: '' },
]

function safeParseRows<T>(jsonStr: string | null | undefined): T[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function computeRow(stored: StoredF5AdjRow): F5AdjudicationRow {
  const currentAdjusted = calcAdjustedAmount(stored.currentUnadjusted, stored.currentAje, stored.currentRje)
  const priorAdjusted = calcAdjustedAmount(stored.priorUnadjusted, stored.priorAje, stored.priorRje)
  return {
    rowKey: stored.rowKey,
    label: stored.label,
    isFixed: stored.isFixed,
    currentUnadjusted: stored.currentUnadjusted,
    currentAje: stored.currentAje,
    currentRje: stored.currentRje,
    currentAdjusted,
    priorUnadjusted: stored.priorUnadjusted,
    priorAje: stored.priorAje,
    priorRje: stored.priorRje,
    priorAdjusted,
    changeAmount: calcChangeAmount(currentAdjusted, priorAdjusted),
    indexRef: stored.indexRef,
    isEditable: true,
  }
}

function computeSubtotalRow(rows: F5AdjudicationRow[], label: string, rowKey: string): F5AdjudicationRow {
  const stored: StoredF5AdjRow = {
    rowKey,
    label,
    isFixed: true,
    currentUnadjusted: calcSubtotal(rows.map((r) => r.currentUnadjusted)),
    currentAje: calcSubtotal(rows.map((r) => r.currentAje)),
    currentRje: calcSubtotal(rows.map((r) => r.currentRje)),
    priorUnadjusted: calcSubtotal(rows.map((r) => r.priorUnadjusted)),
    priorAje: calcSubtotal(rows.map((r) => r.priorAje)),
    priorRje: calcSubtotal(rows.map((r) => r.priorRje)),
    indexRef: '',
  }
  const row = computeRow(stored)
  row.isEditable = false
  return row
}

export function useF5Adjudication(options: UseF5AdjudicationOptions) {
  const { projectId, allResponses, isReadonly } = options
  const readonly = isReadonly ?? ref(false)

  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  const auditNote = ref('')
  const auditConclusion = ref('')

  // ─── 主营业务成本行 ──────────────────────────────────────────────────────
  const storedMainRows = computed<StoredF5AdjRow[]>(() => {
    const resp = allResponses.value.get(MAIN_STORAGE_KEY)
    const parsed = safeParseRows<StoredF5AdjRow>(resp?.remark)
    return parsed.length ? parsed : DEFAULT_MAIN_ROWS.map((r) => ({ ...r }))
  })
  const mainBusinessRows: ComputedRef<F5AdjudicationRow[]> = computed(() =>
    storedMainRows.value.map(computeRow),
  )
  const mainSubtotal: ComputedRef<F5AdjudicationRow> = computed(() =>
    computeSubtotalRow(mainBusinessRows.value, '主营业务成本小计', 'main-subtotal'),
  )

  // ─── 其他业务成本行 ──────────────────────────────────────────────────────
  const storedOtherRows = computed<StoredF5AdjRow[]>(() => {
    const resp = allResponses.value.get(OTHER_STORAGE_KEY)
    const parsed = safeParseRows<StoredF5AdjRow>(resp?.remark)
    return parsed.length ? parsed : DEFAULT_OTHER_ROWS.map((r) => ({ ...r }))
  })
  const otherBusinessRows: ComputedRef<F5AdjudicationRow[]> = computed(() =>
    storedOtherRows.value.map(computeRow),
  )
  const otherSubtotal: ComputedRef<F5AdjudicationRow> = computed(() =>
    computeSubtotalRow(otherBusinessRows.value, '其他业务成本小计', 'other-subtotal'),
  )

  // ─── 总计 = 主营小计 + 其他小计 ──────────────────────────────────────────
  const grandTotal: ComputedRef<F5AdjudicationRow> = computed(() =>
    computeSubtotalRow([mainSubtotal.value, otherSubtotal.value], '营业成本合计', 'grand-total'),
  )

  // ─── 试算表数（科目6401发生额）+ 差异 ────────────────────────────────────
  const trialBalanceAmount: ComputedRef<number> = computed(() =>
    parseNum(allResponses.value.get(TB_STORAGE_KEY)?.remark),
  )
  const variance: ComputedRef<number> = computed(() =>
    grandTotal.value.currentAdjusted - trialBalanceAmount.value,
  )

  // ─── 审计说明/结论 watch ──────────────────────────────────────────────────
  watch(
    () => allResponses.value.get(NOTE_STORAGE_KEY)?.remark,
    (v) => { auditNote.value = v || '' },
    { immediate: true },
  )
  watch(
    () => allResponses.value.get(CONCLUSION_STORAGE_KEY)?.remark,
    (v) => { auditConclusion.value = v || '' },
    { immediate: true },
  )

  // ─── 编辑 ────────────────────────────────────────────────────────────────
  function updateCell(group: 'main' | 'other', rowKey: string, field: string, value: number | string): void {
    if (readonly.value) return
    const key = group === 'main' ? MAIN_STORAGE_KEY : OTHER_STORAGE_KEY
    const defaults = group === 'main' ? DEFAULT_MAIN_ROWS : DEFAULT_OTHER_ROWS
    const parsed = safeParseRows<StoredF5AdjRow>(allResponses.value.get(key)?.remark)
    const stored = parsed.length ? parsed : defaults.map((r) => ({ ...r }))
    const idx = stored.findIndex((r) => r.rowKey === rowKey)
    if (idx === -1) return
    if (field === 'indexRef' || field === 'label') {
      ;(stored[idx] as any)[field] = String(value ?? '')
    } else {
      ;(stored[idx] as any)[field] = typeof value === 'number' ? value : parseNum(value)
    }
    persistRows(key, stored)
  }

  function updateTrialBalance(value: number | string): void {
    if (readonly.value) return
    const numVal = typeof value === 'number' ? value : parseNum(value)
    allResponses.value.set(TB_STORAGE_KEY, { item_id: TB_STORAGE_KEY, conclusion: null, remark: String(numVal) })
    debounceSave()
  }

  /** 动态品种行增删（调用方通过 ElMessageBox.prompt 先取得品种名） */
  function addRow(group: 'main' | 'other', label: string): void {
    if (readonly.value || !label) return
    const key = group === 'main' ? MAIN_STORAGE_KEY : OTHER_STORAGE_KEY
    const defaults = group === 'main' ? DEFAULT_MAIN_ROWS : DEFAULT_OTHER_ROWS
    const parsed = safeParseRows<StoredF5AdjRow>(allResponses.value.get(key)?.remark)
    const stored = parsed.length ? parsed : defaults.map((r) => ({ ...r }))
    stored.push({
      rowKey: `${group}-${Date.now()}`,
      label,
      isFixed: false,
      currentUnadjusted: 0, currentAje: 0, currentRje: 0,
      priorUnadjusted: 0, priorAje: 0, priorRje: 0,
      indexRef: '',
    })
    persistRows(key, stored)
  }

  function removeRow(group: 'main' | 'other', rowKey: string): void {
    if (readonly.value) return
    const key = group === 'main' ? MAIN_STORAGE_KEY : OTHER_STORAGE_KEY
    const parsed = safeParseRows<StoredF5AdjRow>(allResponses.value.get(key)?.remark)
    const stored = parsed.filter((r) => r.rowKey !== rowKey)
    persistRows(key, stored)
  }

  function persistRows(key: string, rows: StoredF5AdjRow[]): void {
    allResponses.value.set(key, { item_id: key, conclusion: null, remark: JSON.stringify(rows) })
    debounceSave()
  }

  // ─── debounce 保存 ────────────────────────────────────────────────────────
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
        allResponses.value.get(MAIN_STORAGE_KEY),
        allResponses.value.get(OTHER_STORAGE_KEY),
        allResponses.value.get(TB_STORAGE_KEY),
        allResponses.value.get(NOTE_STORAGE_KEY),
        allResponses.value.get(CONCLUSION_STORAGE_KEY),
      ].filter(Boolean)
      window.dispatchEvent(new CustomEvent('f5:save-items', { detail: { items } }))
    } catch { /* silent */ }
  }

  // ─── EventBus: substantive:adjudicated(accountCode='6401') ────────────────
  function publishAdjudicated(): void {
    const amount = grandTotal.value.currentAdjusted
    const payload = { wpCode: 'F5', accountCode: '6401', auditedAmount: amount }
    try {
      window.dispatchEvent(new CustomEvent('substantive:adjudicated', { detail: payload }))
    } catch { /* silent */ }
    if (projectId.value) {
      try {
        window.dispatchEvent(new CustomEvent('f5:writeback-trial-balance', {
          detail: { projectId: projectId.value, accountCode: '6401', auditedAmount: amount },
        }))
      } catch { /* silent */ }
    }
  }

  watch(auditNote, (val) => {
    allResponses.value.set(NOTE_STORAGE_KEY, { item_id: NOTE_STORAGE_KEY, conclusion: null, remark: val })
    debounceSave()
  })
  watch(auditConclusion, (val) => {
    allResponses.value.set(CONCLUSION_STORAGE_KEY, { item_id: CONCLUSION_STORAGE_KEY, conclusion: null, remark: val })
    debounceSave()
  })

  // ─── 序列化/反序列化 ─────────────────────────────────────────────────────
  function serialize(): Record<string, string> {
    return {
      [MAIN_STORAGE_KEY]: JSON.stringify(storedMainRows.value),
      [OTHER_STORAGE_KEY]: JSON.stringify(storedOtherRows.value),
      [TB_STORAGE_KEY]: String(trialBalanceAmount.value),
      [NOTE_STORAGE_KEY]: auditNote.value,
      [CONCLUSION_STORAGE_KEY]: auditConclusion.value,
    }
  }

  function deserialize(data: Record<string, string>): void {
    for (const key of [MAIN_STORAGE_KEY, OTHER_STORAGE_KEY, TB_STORAGE_KEY]) {
      if (data[key] !== undefined) {
        allResponses.value.set(key, { item_id: key, conclusion: null, remark: data[key] })
      }
    }
    if (data[NOTE_STORAGE_KEY] !== undefined) auditNote.value = data[NOTE_STORAGE_KEY]
    if (data[CONCLUSION_STORAGE_KEY] !== undefined) auditConclusion.value = data[CONCLUSION_STORAGE_KEY]
  }

  onBeforeUnmount(() => {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
      flushSave()
    }
  })

  return {
    mainBusinessRows,
    mainSubtotal,
    otherBusinessRows,
    otherSubtotal,
    grandTotal,
    trialBalanceAmount,
    variance,
    updateCell,
    updateTrialBalance,
    addRow,
    removeRow,
    auditNote,
    auditConclusion,
    publishAdjudicated,
    serialize,
    deserialize,
  }
}

export default useF5Adjudication
