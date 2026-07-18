/**
 * useF4SubstantiveAnalysis — F4-4 应付账款实质性分析
 *
 * 对齐源表两个区块：
 * 1. 应付账款周转率（支付期）：采购成本口径 / 平均应付账款；
 * 2. 期末应付账款前十名：从F4-2按债权人归集并按期末审定数动态排序。
 */
import { computed, onBeforeUnmount, ref, watch, type Ref } from 'vue'
import { parseNum, calcChangeAmount, calcChangeRate, calcSubtotal } from './useF4AccPayFormulaEngine'
import {
  computeF4DetailRow,
  migrateF4DetailRows,
} from './useF4Detail'
import {
  aggregateF4Detail,
  computeF4AdjudicationRow,
  F4_NATURE_DEFAULTS,
  migrateF4AdjRows,
} from './useF4Adjudication'
import { readRowJson, type ChecklistResponse } from './useF4FormData'

export interface UseF4SubstantiveAnalysisOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}

export type F4TurnoverInputKey =
  | 'priorOpeningPayable'
  | 'currentOperatingCost'
  | 'priorOperatingCost'
  | 'currentOpeningInventory'
  | 'priorOpeningInventory'
  | 'currentClosingInventory'
  | 'priorClosingInventory'
  | 'currentIndustryTurnover'
  | 'priorIndustryTurnover'

export type F4TurnoverRowKey =
  | 'openingPayable'
  | 'closingPayable'
  | 'operatingCost'
  | 'openingInventory'
  | 'closingInventory'
  | 'turnoverRate'
  | 'paymentDays'
  | 'industryTurnover'
  | 'industryDifference'

export interface F4TurnoverRow {
  rowKey: F4TurnoverRowKey
  item: string
  currentAmount: number | null
  priorAmount: number | null
  remark: string
  formula?: string
  currentInput?: F4TurnoverInputKey
  priorInput?: F4TurnoverInputKey
}

export interface F4TopCreditorRow {
  rowId: string
  creditor: string
  currentBalance: number
  priorBalance: number
  changeAmount: number
  changeRate: number | 'N/A'
  reason: string
  sourcePaymentNature: string
  isHighChange: boolean
}

interface StoredTurnover {
  inputs: Record<F4TurnoverInputKey, number>
  remarks: Partial<Record<F4TurnoverRowKey, string>>
}

interface CreditorReasonOverride {
  rowId: string
  reason: string
}

const TURNOVER_KEY = 'F4-4-turnover'
const CREDITOR_OVERRIDE_KEY = 'F4-4-creditor-overrides'
const TURNOVER_NOTE_KEY = 'F4-4-turnover-note'
const CREDITOR_NOTE_KEY = 'F4-4-creditor-note'
const CONCLUSION_KEY = 'F4-4-conclusion'
const LEGACY_NOTE_KEY = 'F4-4-note'
const DETAIL_KEY = 'F4-2-rows'
const ADJ_NATURE_KEY = 'F4-1-adj-nature-rows'
const CHANGE_THRESHOLD = 20
const TOLERANCE = 0.005

function defaultTurnover(): StoredTurnover {
  return {
    inputs: {
      priorOpeningPayable: 0,
      currentOperatingCost: 0,
      priorOperatingCost: 0,
      currentOpeningInventory: 0,
      priorOpeningInventory: 0,
      currentClosingInventory: 0,
      priorClosingInventory: 0,
      currentIndustryTurnover: 0,
      priorIndustryTurnover: 0,
    },
    remarks: {},
  }
}

function safeJson(value: string | null | undefined): any {
  if (!value) return null
  try { return JSON.parse(value) } catch { return null }
}

export function parseF4Turnover(value: string | null | undefined): StoredTurnover {
  const defaults = defaultTurnover()
  const raw = safeJson(value)
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return defaults
  for (const key of Object.keys(defaults.inputs) as F4TurnoverInputKey[]) {
    defaults.inputs[key] = parseNum(raw?.inputs?.[key] ?? raw?.[key])
  }
  if (raw.remarks && typeof raw.remarks === 'object') {
    defaults.remarks = Object.fromEntries(
      Object.entries(raw.remarks).map(([key, text]) => [key, String(text ?? '')]),
    )
  }
  return defaults
}

function parseOverrides(value: string | null | undefined): CreditorReasonOverride[] {
  const raw = safeJson(value)
  if (!Array.isArray(raw)) return []
  return raw
    .map((item: any) => ({
      rowId: String(item?.rowId ?? ''),
      reason: String(item?.reason ?? ''),
    }))
    .filter((item) => item.rowId)
}

/** 采购成本口径：主营业务成本 + 期末存货 - 期初存货。 */
export function calcF4Purchases(
  operatingCost: number,
  openingInventory: number,
  closingInventory: number,
): number {
  return operatingCost + closingInventory - openingInventory
}

/** 应付账款周转率 = 采购成本 / 平均应付账款；分母为0时返回null。 */
export function calcF4PayableTurnover(
  operatingCost: number,
  openingInventory: number,
  closingInventory: number,
  openingPayable: number,
  closingPayable: number,
): number | null {
  const averagePayable = (openingPayable + closingPayable) / 2
  if (Math.abs(averagePayable) < TOLERANCE) return null
  return calcF4Purchases(operatingCost, openingInventory, closingInventory) / averagePayable
}

export function calcF4PaymentDays(turnover: number | null): number | null {
  if (turnover == null || Math.abs(turnover) < TOLERANCE) return null
  return 365 / turnover
}

export function extractF4TopCreditors(
  value: string | null | undefined,
  limit = 10,
): Array<Omit<F4TopCreditorRow, 'reason' | 'isHighChange'>> {
  const rows = migrateF4DetailRows(value).map(computeF4DetailRow)
  const grouped = new Map<string, {
    rowIds: string[]
    creditor: string
    currentBalance: number
    priorBalance: number
    natures: Set<string>
  }>()
  for (const row of rows) {
    const creditor = row.creditor.trim()
    if (!creditor) continue
    const key = creditor.toLocaleLowerCase('zh-CN')
    const target = grouped.get(key) ?? {
      rowIds: [],
      creditor,
      currentBalance: 0,
      priorBalance: 0,
      natures: new Set<string>(),
    }
    target.rowIds.push(row.rowId)
    target.currentBalance += row.closingAdjusted
    target.priorBalance += row.openingAdjusted
    if (row.paymentNature) target.natures.add(row.paymentNature)
    grouped.set(key, target)
  }

  return [...grouped.values()]
    .filter((row) => Math.abs(row.currentBalance) >= TOLERANCE || Math.abs(row.priorBalance) >= TOLERANCE)
    .sort((a, b) =>
      Math.abs(b.currentBalance) - Math.abs(a.currentBalance)
      || a.creditor.localeCompare(b.creditor, 'zh-CN'),
    )
    .slice(0, limit)
    .map((row) => ({
      rowId: row.rowIds.sort().join('|') || row.creditor,
      creditor: row.creditor,
      currentBalance: row.currentBalance,
      priorBalance: row.priorBalance,
      changeAmount: calcChangeAmount(row.currentBalance, row.priorBalance),
      changeRate: calcChangeRate(row.currentBalance, row.priorBalance),
      sourcePaymentNature: [...row.natures].join('、'),
    }))
}

export function useF4SubstantiveAnalysis(options: UseF4SubstantiveAnalysisOptions) {
  const { allResponses, isReadonly } = options
  const readonly = isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  const turnoverStored = ref<StoredTurnover>(defaultTurnover())
  const creditorOverrides = ref<CreditorReasonOverride[]>([])
  const turnoverNote = ref('')
  const creditorNote = ref('')
  const auditConclusion = ref('')

  function load(): void {
    turnoverStored.value = parseF4Turnover(readRowJson(allResponses.value.get(TURNOVER_KEY)))
    creditorOverrides.value = parseOverrides(readRowJson(allResponses.value.get(CREDITOR_OVERRIDE_KEY)))
  }

  watch(
    () => [
      readRowJson(allResponses.value.get(TURNOVER_KEY)),
      readRowJson(allResponses.value.get(CREDITOR_OVERRIDE_KEY)),
    ],
    load,
    { immediate: true },
  )

  // 兼容旧版单一结论键：无新结论时迁移到最终结论。
  watch(
    () => [
      allResponses.value.get(TURNOVER_NOTE_KEY)?.remark,
      allResponses.value.get(CREDITOR_NOTE_KEY)?.remark,
      allResponses.value.get(CONCLUSION_KEY)?.remark,
      allResponses.value.get(LEGACY_NOTE_KEY)?.remark,
    ],
    ([turnover, creditor, conclusion, legacy]) => {
      turnoverNote.value = turnover || ''
      creditorNote.value = creditor || ''
      auditConclusion.value = conclusion || legacy || ''
    },
    { immediate: true },
  )

  const adjudicationTotals = computed(() => {
    const detail = aggregateF4Detail(readRowJson(allResponses.value.get(DETAIL_KEY)))
    const rows = migrateF4AdjRows(
      readRowJson(allResponses.value.get(ADJ_NATURE_KEY)),
      F4_NATURE_DEFAULTS,
    ).map((row) => computeF4AdjudicationRow(
      row,
      detail.hasData ? detail.nature[row.rowKey] : undefined,
    ))
    return {
      opening: calcSubtotal(rows.map((row) => row.openingAdjusted)),
      closing: calcSubtotal(rows.map((row) => row.closingAdjusted)),
    }
  })

  const turnoverRows = computed<F4TurnoverRow[]>(() => {
    const input = turnoverStored.value.inputs
    const currentTurnover = calcF4PayableTurnover(
      input.currentOperatingCost,
      input.currentOpeningInventory,
      input.currentClosingInventory,
      adjudicationTotals.value.opening,
      adjudicationTotals.value.closing,
    )
    const priorTurnover = calcF4PayableTurnover(
      input.priorOperatingCost,
      input.priorOpeningInventory,
      input.priorClosingInventory,
      input.priorOpeningPayable,
      adjudicationTotals.value.opening,
    )
    const row = (
      rowKey: F4TurnoverRowKey,
      item: string,
      currentAmount: number | null,
      priorAmount: number | null,
      options: Partial<F4TurnoverRow> = {},
    ): F4TurnoverRow => ({
      rowKey,
      item,
      currentAmount,
      priorAmount,
      remark: turnoverStored.value.remarks[rowKey] || '',
      ...options,
    })
    return [
      row('openingPayable', '期初应付账款', adjudicationTotals.value.opening, input.priorOpeningPayable, {
        priorInput: 'priorOpeningPayable',
      }),
      row('closingPayable', '期末应付账款', adjudicationTotals.value.closing, adjudicationTotals.value.opening),
      row('operatingCost', '主营业务成本', input.currentOperatingCost, input.priorOperatingCost, {
        currentInput: 'currentOperatingCost',
        priorInput: 'priorOperatingCost',
      }),
      row('openingInventory', '存货期初余额', input.currentOpeningInventory, input.priorOpeningInventory, {
        currentInput: 'currentOpeningInventory',
        priorInput: 'priorOpeningInventory',
      }),
      row('closingInventory', '存货期末余额', input.currentClosingInventory, input.priorClosingInventory, {
        currentInput: 'currentClosingInventory',
        priorInput: 'priorClosingInventory',
      }),
      row('turnoverRate', '应付账款周转率', currentTurnover, priorTurnover, {
        formula: '(主营业务成本+存货期末-存货期初)/平均应付账款',
      }),
      row('paymentDays', '平均周转（支付）天数（天）', calcF4PaymentDays(currentTurnover), calcF4PaymentDays(priorTurnover), {
        formula: '365/应付账款周转率',
      }),
      row('industryTurnover', '同行业应付账款平均周转率', input.currentIndustryTurnover, input.priorIndustryTurnover, {
        currentInput: 'currentIndustryTurnover',
        priorInput: 'priorIndustryTurnover',
      }),
      row(
        'industryDifference',
        '与同行业应付账款周转率的差异',
        currentTurnover == null ? null : currentTurnover - input.currentIndustryTurnover,
        priorTurnover == null ? null : priorTurnover - input.priorIndustryTurnover,
        { formula: '企业周转率-同行业平均周转率' },
      ),
    ]
  })

  const topCreditors = computed<F4TopCreditorRow[]>(() => {
    const overrides = new Map(creditorOverrides.value.map((item) => [item.rowId, item.reason]))
    return extractF4TopCreditors(readRowJson(allResponses.value.get(DETAIL_KEY))).map((row) => {
      const reason = overrides.get(row.rowId) || row.sourcePaymentNature
      return {
        ...row,
        reason,
        isHighChange: row.changeRate !== 'N/A' && Math.abs(row.changeRate) > CHANGE_THRESHOLD,
      }
    })
  })

  const creditorSubtotal = computed(() => {
    const currentBalance = calcSubtotal(topCreditors.value.map((row) => row.currentBalance))
    const priorBalance = calcSubtotal(topCreditors.value.map((row) => row.priorBalance))
    const changeAmount = currentBalance - priorBalance
    return {
      currentBalance,
      priorBalance,
      changeAmount,
      changeRate: calcChangeRate(currentBalance, priorBalance),
    }
  })

  const summary = computed(() => ({
    creditorCount: topCreditors.value.length,
    highChangeCount: topCreditors.value.filter((row) => row.isHighChange).length,
    currentTopTenTotal: creditorSubtotal.value.currentBalance,
    priorTopTenTotal: creditorSubtotal.value.priorBalance,
  }))

  function updateTurnoverInput(key: F4TurnoverInputKey, value: unknown): void {
    if (readonly.value) return
    turnoverStored.value.inputs[key] = parseNum(value as string | number | null | undefined)
    persistTurnover()
  }

  function updateTurnoverRemark(rowKey: F4TurnoverRowKey, value: string): void {
    if (readonly.value) return
    turnoverStored.value.remarks[rowKey] = String(value ?? '')
    persistTurnover()
  }

  function updateCreditorReason(rowId: string, value: string): void {
    if (readonly.value) return
    const existing = creditorOverrides.value.find((item) => item.rowId === rowId)
    if (existing) existing.reason = String(value ?? '')
    else creditorOverrides.value.push({ rowId, reason: String(value ?? '') })
    persistOverrides()
  }

  function setItem(key: string, remark: string): void {
    allResponses.value.set(key, { item_id: key, conclusion: null, remark })
    debounceSave()
  }

  function persistTurnover(): void {
    setItem(TURNOVER_KEY, JSON.stringify(turnoverStored.value))
  }

  function persistOverrides(): void {
    setItem(CREDITOR_OVERRIDE_KEY, JSON.stringify(creditorOverrides.value))
  }

  function saveTurnoverNote(value: string): void {
    if (readonly.value) return
    turnoverNote.value = value
    setItem(TURNOVER_NOTE_KEY, value)
  }

  function saveCreditorNote(value: string): void {
    if (readonly.value) return
    creditorNote.value = value
    setItem(CREDITOR_NOTE_KEY, value)
  }

  function saveConclusion(value: string): void {
    if (readonly.value) return
    auditConclusion.value = value
    setItem(CONCLUSION_KEY, value)
  }

  function debounceSave(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      flushSave()
    }, 1200)
  }

  function flushSave(): void {
    const items = [
      TURNOVER_KEY,
      CREDITOR_OVERRIDE_KEY,
      TURNOVER_NOTE_KEY,
      CREDITOR_NOTE_KEY,
      CONCLUSION_KEY,
    ].map((key) => allResponses.value.get(key)).filter(Boolean)
    if (items.length) {
      window.dispatchEvent(new CustomEvent('f4:save-items', { detail: { items } }))
    }
  }

  onBeforeUnmount(() => {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
      flushSave()
    }
  })

  return {
    turnoverRows,
    topCreditors,
    creditorSubtotal,
    summary,
    turnoverNote,
    creditorNote,
    auditConclusion,
    updateTurnoverInput,
    updateTurnoverRemark,
    updateCreditorReason,
    saveTurnoverNote,
    saveCreditorNote,
    saveConclusion,
  }
}

export default useF4SubstantiveAnalysis
