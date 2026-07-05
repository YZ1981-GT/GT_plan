/**
 * useF4Adjudication — F4-1 审定表核心逻辑（贷方科目 2202 应付账款）
 *
 * Spec: .kiro/specs/f4-accounts-payable/ Task 4.1
 * 两级结构：按性质(货款/工程款/服务费/其他) + 按账龄(1年以内/1-2年/2-3年/3年以上)
 * 交叉校验：按性质小计 === 按账龄小计
 * EventBus: publish substantive:adjudicated(accountCode='2202')
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import {
  parseNum,
  calcAdjustedAmount,
  calcCreditBalance,
  calcSubtotal,
} from './useF4AccPayFormulaEngine'
import type { ChecklistResponse } from './useF4FormData'

// ─── 类型定义 ─────────────────────────────────────────────────────────────────

export interface UseF4AdjudicationOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}

export interface F4AdjudicationRow {
  rowKey: string
  label: string
  isFixed: boolean
  /** 期初未审 */
  openingUnadjusted: number
  /** 期初 AJE */
  openingAje: number
  /** 期初 RJE */
  openingRje: number
  /** 期初审定 = 期初未审 + AJE + RJE */
  openingAdjusted: number
  /** 本期贷方发生额 */
  periodCredit: number
  /** 本期借方发生额 */
  periodDebit: number
  /** 期末未审 = 期初审定 + 贷方 - 借方 */
  closingUnadjusted: number
  /** 期末 AJE */
  closingAje: number
  /** 期末 RJE */
  closingRje: number
  /** 期末审定 = 期末未审 + AJE + RJE */
  closingAdjusted: number
  /** 索引 */
  indexRef: string
  /** 是否可编辑 */
  isEditable: boolean
}

/** 持久化用（不含计算字段） */
interface StoredF4AdjRow {
  rowKey: string
  label: string
  isFixed: boolean
  openingUnadjusted: number
  openingAje: number
  openingRje: number
  periodCredit: number
  periodDebit: number
  closingAje: number
  closingRje: number
  indexRef: string
}

export interface F4AdjudicationTwoLevel {
  byNature: ComputedRef<F4AdjudicationRow[]>
  byAging: ComputedRef<F4AdjudicationRow[]>
  natureSubtotal: ComputedRef<F4AdjudicationRow>
  agingSubtotal: ComputedRef<F4AdjudicationRow>
  total: ComputedRef<F4AdjudicationRow>
  trialBalanceAmount: ComputedRef<number>
  variance: ComputedRef<number>
  crossCheckPassed: ComputedRef<boolean>
}

// ─── 存储键 ──────────────────────────────────────────────────────────────────

const NATURE_STORAGE_KEY = 'F4-1-adj-nature-rows'
const AGING_STORAGE_KEY = 'F4-1-adj-aging-rows'
const TB_STORAGE_KEY = 'F4-1-adj-tb-2202'
const NOTE_STORAGE_KEY = 'F4-1-adj-note'
const CONCLUSION_STORAGE_KEY = 'F4-1-adj-conclusion'

const BALANCE_TOLERANCE = 0.005

// ─── 默认行定义 ──────────────────────────────────────────────────────────────

const DEFAULT_NATURE_ROWS: StoredF4AdjRow[] = [
  { rowKey: 'goods', label: '货款', isFixed: true, openingUnadjusted: 0, openingAje: 0, openingRje: 0, periodCredit: 0, periodDebit: 0, closingAje: 0, closingRje: 0, indexRef: '' },
  { rowKey: 'construction', label: '工程款', isFixed: true, openingUnadjusted: 0, openingAje: 0, openingRje: 0, periodCredit: 0, periodDebit: 0, closingAje: 0, closingRje: 0, indexRef: '' },
  { rowKey: 'service', label: '服务费', isFixed: true, openingUnadjusted: 0, openingAje: 0, openingRje: 0, periodCredit: 0, periodDebit: 0, closingAje: 0, closingRje: 0, indexRef: '' },
  { rowKey: 'other', label: '其他', isFixed: true, openingUnadjusted: 0, openingAje: 0, openingRje: 0, periodCredit: 0, periodDebit: 0, closingAje: 0, closingRje: 0, indexRef: '' },
]

const DEFAULT_AGING_ROWS: StoredF4AdjRow[] = [
  { rowKey: 'within1year', label: '1年以内', isFixed: true, openingUnadjusted: 0, openingAje: 0, openingRje: 0, periodCredit: 0, periodDebit: 0, closingAje: 0, closingRje: 0, indexRef: '' },
  { rowKey: '1to2year', label: '1-2年', isFixed: true, openingUnadjusted: 0, openingAje: 0, openingRje: 0, periodCredit: 0, periodDebit: 0, closingAje: 0, closingRje: 0, indexRef: '' },
  { rowKey: '2to3year', label: '2-3年', isFixed: true, openingUnadjusted: 0, openingAje: 0, openingRje: 0, periodCredit: 0, periodDebit: 0, closingAje: 0, closingRje: 0, indexRef: '' },
  { rowKey: '3yearplus', label: '3年以上', isFixed: true, openingUnadjusted: 0, openingAje: 0, openingRje: 0, periodCredit: 0, periodDebit: 0, closingAje: 0, closingRje: 0, indexRef: '' },
]

// ─── 工具函数 ─────────────────────────────────────────────────────────────────

function safeParseRows<T>(jsonStr: string | null | undefined): T[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function computeRow(stored: StoredF4AdjRow): F4AdjudicationRow {
  const openingAdjusted = calcAdjustedAmount(stored.openingUnadjusted, stored.openingAje, stored.openingRje)
  const closingUnadjusted = calcCreditBalance(openingAdjusted, stored.periodCredit, stored.periodDebit)
  const closingAdjusted = calcAdjustedAmount(closingUnadjusted, stored.closingAje, stored.closingRje)
  return {
    rowKey: stored.rowKey,
    label: stored.label,
    isFixed: stored.isFixed,
    openingUnadjusted: stored.openingUnadjusted,
    openingAje: stored.openingAje,
    openingRje: stored.openingRje,
    openingAdjusted,
    periodCredit: stored.periodCredit,
    periodDebit: stored.periodDebit,
    closingUnadjusted,
    closingAje: stored.closingAje,
    closingRje: stored.closingRje,
    closingAdjusted,
    indexRef: stored.indexRef,
    isEditable: true,
  }
}

function computeSubtotalRow(rows: F4AdjudicationRow[], label: string, rowKey: string): F4AdjudicationRow {
  const stored: StoredF4AdjRow = {
    rowKey,
    label,
    isFixed: true,
    openingUnadjusted: calcSubtotal(rows.map((r) => r.openingUnadjusted)),
    openingAje: calcSubtotal(rows.map((r) => r.openingAje)),
    openingRje: calcSubtotal(rows.map((r) => r.openingRje)),
    periodCredit: calcSubtotal(rows.map((r) => r.periodCredit)),
    periodDebit: calcSubtotal(rows.map((r) => r.periodDebit)),
    closingAje: calcSubtotal(rows.map((r) => r.closingAje)),
    closingRje: calcSubtotal(rows.map((r) => r.closingRje)),
    indexRef: '',
  }
  const row = computeRow(stored)
  row.isEditable = false
  return row
}

function ensureDefaultRows(stored: StoredF4AdjRow[], defaults: StoredF4AdjRow[]): StoredF4AdjRow[] {
  if (stored.length === 0) return defaults.map((r) => ({ ...r }))
  const keys = new Set(stored.map((r) => r.rowKey))
  const merged = [...stored]
  for (const def of defaults) {
    if (!keys.has(def.rowKey)) merged.push({ ...def })
  }
  return merged
}

// ─── 主 composable ───────────────────────────────────────────────────────────

export function useF4Adjudication(options: UseF4AdjudicationOptions) {
  const { wpId, projectId, allResponses, isReadonly } = options
  const readonly = isReadonly ?? ref(false)

  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  const auditNote = ref('')
  const auditConclusion = ref('')

  // ─── 按性质行 ────────────────────────────────────────────────────────────

  const storedNatureRows = computed<StoredF4AdjRow[]>(() => {
    const resp = allResponses.value.get(NATURE_STORAGE_KEY)
    return ensureDefaultRows(safeParseRows<StoredF4AdjRow>(resp?.remark), DEFAULT_NATURE_ROWS)
  })

  const natureDataRows: ComputedRef<F4AdjudicationRow[]> = computed(() =>
    storedNatureRows.value.map((s) => computeRow(s)),
  )

  const natureSubtotalRow: ComputedRef<F4AdjudicationRow> = computed(() =>
    computeSubtotalRow(natureDataRows.value, '按性质小计', 'nature-subtotal'),
  )

  // ─── 按账龄行 ────────────────────────────────────────────────────────────

  const storedAgingRows = computed<StoredF4AdjRow[]>(() => {
    const resp = allResponses.value.get(AGING_STORAGE_KEY)
    return ensureDefaultRows(safeParseRows<StoredF4AdjRow>(resp?.remark), DEFAULT_AGING_ROWS)
  })

  const agingDataRows: ComputedRef<F4AdjudicationRow[]> = computed(() =>
    storedAgingRows.value.map((s) => computeRow(s)),
  )

  const agingSubtotalRow: ComputedRef<F4AdjudicationRow> = computed(() =>
    computeSubtotalRow(agingDataRows.value, '按账龄小计', 'aging-subtotal'),
  )

  // ─── 交叉校验：按性质小计 === 按账龄小计 ─────────────────────────────────

  const crossCheckPassed: ComputedRef<boolean> = computed(() =>
    Math.abs(natureSubtotalRow.value.closingAdjusted - agingSubtotalRow.value.closingAdjusted) < BALANCE_TOLERANCE,
  )

  // ─── 合计行（取按性质小计，两者相等时一致） ────────────────────────────────

  const totalRow: ComputedRef<F4AdjudicationRow> = computed(() => {
    const row = { ...natureSubtotalRow.value }
    row.rowKey = 'total'
    row.label = '合计'
    return row
  })

  // ─── 试算表数 + 差异 ─────────────────────────────────────────────────────

  const trialBalanceAmount: ComputedRef<number> = computed(() =>
    parseNum(allResponses.value.get(TB_STORAGE_KEY)?.remark),
  )

  const variance: ComputedRef<number> = computed(() =>
    totalRow.value.closingAdjusted - trialBalanceAmount.value,
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

  // ─── 编辑 + 保存 ─────────────────────────────────────────────────────────

  function updateNatureCell(rowKey: string, field: string, value: number | string): void {
    if (readonly.value) return
    const stored = ensureDefaultRows(
      safeParseRows<StoredF4AdjRow>(allResponses.value.get(NATURE_STORAGE_KEY)?.remark),
      DEFAULT_NATURE_ROWS,
    )
    const idx = stored.findIndex((r) => r.rowKey === rowKey)
    if (idx === -1) return
    if (field === 'indexRef') {
      stored[idx].indexRef = String(value ?? '')
    } else {
      ;(stored[idx] as any)[field] = typeof value === 'number' ? value : parseNum(value)
    }
    persistNatureRows(stored)
  }

  function updateAgingCell(rowKey: string, field: string, value: number | string): void {
    if (readonly.value) return
    const stored = ensureDefaultRows(
      safeParseRows<StoredF4AdjRow>(allResponses.value.get(AGING_STORAGE_KEY)?.remark),
      DEFAULT_AGING_ROWS,
    )
    const idx = stored.findIndex((r) => r.rowKey === rowKey)
    if (idx === -1) return
    if (field === 'indexRef') {
      stored[idx].indexRef = String(value ?? '')
    } else {
      ;(stored[idx] as any)[field] = typeof value === 'number' ? value : parseNum(value)
    }
    persistAgingRows(stored)
  }

  function updateTrialBalance(value: number | string): void {
    if (readonly.value) return
    const numVal = typeof value === 'number' ? value : parseNum(value)
    allResponses.value.set(TB_STORAGE_KEY, {
      item_id: TB_STORAGE_KEY,
      conclusion: null,
      remark: String(numVal),
    })
    debounceSave()
  }

  function persistNatureRows(rows: StoredF4AdjRow[]): void {
    const json = JSON.stringify(rows)
    allResponses.value.set(NATURE_STORAGE_KEY, {
      item_id: NATURE_STORAGE_KEY,
      conclusion: null,
      remark: json,
    })
    debounceSave()
  }

  function persistAgingRows(rows: StoredF4AdjRow[]): void {
    const json = JSON.stringify(rows)
    allResponses.value.set(AGING_STORAGE_KEY, {
      item_id: AGING_STORAGE_KEY,
      conclusion: null,
      remark: json,
    })
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
        allResponses.value.get(NATURE_STORAGE_KEY),
        allResponses.value.get(AGING_STORAGE_KEY),
        allResponses.value.get(TB_STORAGE_KEY),
        allResponses.value.get(NOTE_STORAGE_KEY),
        allResponses.value.get(CONCLUSION_STORAGE_KEY),
      ].filter(Boolean)
      window.dispatchEvent(new CustomEvent('f4:save-items', { detail: { items } }))
    } catch { /* silent */ }
  }

  // ─── EventBus: substantive:adjudicated ────────────────────────────────────

  function publishAdjudicated(): void {
    const amount = totalRow.value.closingAdjusted
    const payload = {
      wpCode: 'F4',
      accountCode: '2202',
      auditedAmount: amount,
    }
    try {
      window.dispatchEvent(new CustomEvent('substantive:adjudicated', { detail: payload }))
    } catch { /* silent */ }

    // 试算表回写通知
    if (projectId.value) {
      try {
        window.dispatchEvent(new CustomEvent('f4:writeback-trial-balance', {
          detail: { projectId: projectId.value, accountCode: '2202', auditedAmount: amount },
        }))
      } catch { /* silent */ }
    }
  }

  // ─── 审计说明/结论 watch → 保存 ──────────────────────────────────────────

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
      [NATURE_STORAGE_KEY]: JSON.stringify(storedNatureRows.value),
      [AGING_STORAGE_KEY]: JSON.stringify(storedAgingRows.value),
      [TB_STORAGE_KEY]: String(trialBalanceAmount.value),
      [NOTE_STORAGE_KEY]: auditNote.value,
      [CONCLUSION_STORAGE_KEY]: auditConclusion.value,
    }
  }

  function deserialize(data: Record<string, string>): void {
    if (data[NATURE_STORAGE_KEY]) {
      allResponses.value.set(NATURE_STORAGE_KEY, {
        item_id: NATURE_STORAGE_KEY,
        conclusion: null,
        remark: data[NATURE_STORAGE_KEY],
      })
    }
    if (data[AGING_STORAGE_KEY]) {
      allResponses.value.set(AGING_STORAGE_KEY, {
        item_id: AGING_STORAGE_KEY,
        conclusion: null,
        remark: data[AGING_STORAGE_KEY],
      })
    }
    if (data[TB_STORAGE_KEY]) {
      allResponses.value.set(TB_STORAGE_KEY, {
        item_id: TB_STORAGE_KEY,
        conclusion: null,
        remark: data[TB_STORAGE_KEY],
      })
    }
    if (data[NOTE_STORAGE_KEY]) {
      auditNote.value = data[NOTE_STORAGE_KEY]
    }
    if (data[CONCLUSION_STORAGE_KEY]) {
      auditConclusion.value = data[CONCLUSION_STORAGE_KEY]
    }
  }

  // ─── cleanup ──────────────────────────────────────────────────────────────

  onBeforeUnmount(() => {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
      flushSave()
    }
  })

  return {
    // 按性质
    natureDataRows,
    natureSubtotalRow,
    // 按账龄
    agingDataRows,
    agingSubtotalRow,
    // 合计 / 试算表 / 差异
    totalRow,
    trialBalanceAmount,
    variance,
    // 交叉校验
    crossCheckPassed,
    // 编辑
    updateNatureCell,
    updateAgingCell,
    updateTrialBalance,
    // 审计说明/结论
    auditNote,
    auditConclusion,
    // EventBus
    publishAdjudicated,
    // 序列化
    serialize,
    deserialize,
  }
}

export default useF4Adjudication
