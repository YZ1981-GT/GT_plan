/**
 * useF5Adjudication — F5-1 营业成本审定表（借方/损益类科目 6401）
 *
 * 源表编制逻辑：
 * 1. 损益类无期初期末，按本期/上期发生额列示；审定 = 未审 + 账项调整 + 重分类。
 * 2. 主营业务成本品种行动态（可从 F5-2 月度明细引用）→ 小计；其他业务成本动态行 → 小计。
 * 3. 合计 = 主营小计 + 其他小计；与试算平衡表 6401 核对，差异 = 审定 − 试算。
 * 4. 审计说明须分析本期较上期增减，变动比例超过 30% 的品种说明主要原因。
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import {
  parseNum,
  calcAdjustedAmount,
  calcChangeAmount,
  calcChangeRate,
  calcSubtotal,
} from './useF5CosOfFormulaEngine'
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
  currentUnadjusted: number
  currentAje: number
  currentRje: number
  currentAdjusted: number
  priorUnadjusted: number
  priorAje: number
  priorRje: number
  priorAdjusted: number
  changeAmount: number
  changeRate: number | 'N/A'
  indexRef: string
  isEditable: boolean
}

export interface F5SignificantChangeItem {
  group: 'main' | 'other' | 'subtotal'
  label: string
  priorAdjusted: number
  currentAdjusted: number
  changeAmount: number
  changeRate: number
}

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
const PRIOR_TB_STORAGE_KEY = 'F5-1-adj-tb-6401-prior'
const NOTE_STORAGE_KEY = 'F5-1-adj-note'
const CONCLUSION_STORAGE_KEY = 'F5-1-adj-conclusion'
const MONTHLY_DETAIL_KEY = 'F5-2-monthly-rows'
const OTHER_COST_KEY = 'F5-3-other-cost-rows'
const OTHER_COST_LEGACY_KEY = 'F5-3-rows'
const ADJUSTMENT_KEY = 'F5-4-rows'
const F54_SYNC_ROW_KEY = 'main-sync-f54'
const F54_SYNC_LABEL = '审计调整（F5-4）'

/** 源表：变动比例超过 30% 须说明主要原因 */
export const F5_ADJ_CHANGE_RATE_THRESHOLD = 30

const DEFAULT_MAIN_ROWS: StoredF5AdjRow[] = [
  {
    rowKey: 'main-product-1', label: '品种1', isFixed: false,
    currentUnadjusted: 0, currentAje: 0, currentRje: 0,
    priorUnadjusted: 0, priorAje: 0, priorRje: 0, indexRef: '',
  },
]

const DEFAULT_OTHER_ROWS: StoredF5AdjRow[] = [
  {
    rowKey: 'other-1', label: '其他业务成本1', isFixed: false,
    currentUnadjusted: 0, currentAje: 0, currentRje: 0,
    priorUnadjusted: 0, priorAje: 0, priorRje: 0, indexRef: '',
  },
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
  const changeAmount = calcChangeAmount(currentAdjusted, priorAdjusted)
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
    changeAmount,
    changeRate: calcChangeRate(currentAdjusted, priorAdjusted),
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

/** 从 F5-2 月度明细提取品种（全年合计→本期未审，上期合计→上期未审） */
export function extractF5AdjudicationCandidatesFromMonthly(
  monthlyJson: string | null | undefined,
): Array<{ product: string; currentUnadjusted: number; priorUnadjusted: number }> {
  if (!monthlyJson) return []
  try {
    const parsed = JSON.parse(monthlyJson)
    if (!Array.isArray(parsed)) return []
    return parsed
      .map((raw: any) => {
        const product = String(raw?.product || '').trim()
        const months: number[] = Array.isArray(raw?.months)
          ? raw.months.map((m: unknown) => parseNum(m as any))
          : []
        const yearTotal = months.length
          ? calcSubtotal(months)
          : parseNum(raw?.yearTotal ?? raw?.currentUnadjusted ?? raw?.currentUnaudited)
        return {
          product,
          currentUnadjusted: yearTotal,
          priorUnadjusted: parseNum(raw?.priorYearTotal ?? raw?.priorUnaudited ?? raw?.priorUnadjusted),
        }
      })
      .filter((item) => item.product)
  } catch {
    return []
  }
}

/** 从 F5-3 其他业务成本提取项目（审定口径对应未审+调整，同步时取未审） */
export function extractF5AdjudicationCandidatesFromOtherCost(
  otherJson: string | null | undefined,
): Array<{ item: string; currentUnadjusted: number; priorUnadjusted: number }> {
  if (!otherJson) return []
  try {
    const parsed = JSON.parse(otherJson)
    if (!Array.isArray(parsed)) return []
    return parsed
      .map((raw: any) => {
        const item = String(raw?.item || raw?.label || '').trim()
        return {
          item,
          currentUnadjusted: parseNum(raw?.currentUnaudited ?? raw?.currentUnadjusted),
          priorUnadjusted: parseNum(raw?.priorUnaudited ?? raw?.priorUnadjusted),
        }
      })
      .filter((row) => row.item)
  } catch {
    return []
  }
}

function isCogsAccount(code: string, name: string): boolean {
  const c = code.trim()
  const n = name.trim()
  return c.startsWith('6401') || n.includes('营业成本') || n.includes('主营业务成本')
}

/** 汇总 F5-4 中影响 6401 的 AJE/RJE 净额（借−贷，费用类借方增加成本） */
export function aggregateF54AdjustmentImpact(
  adjustmentJson: string | null | undefined,
): { aje: number; rje: number; lineCount: number } {
  if (!adjustmentJson) return { aje: 0, rje: 0, lineCount: 0 }
  try {
    const parsed = JSON.parse(adjustmentJson)
    if (!Array.isArray(parsed)) return { aje: 0, rje: 0, lineCount: 0 }
    let aje = 0
    let rje = 0
    let lineCount = 0
    for (const raw of parsed) {
      const code = String(raw?.accountCode ?? '')
      const name = String(raw?.accountName ?? '')
      if (!isCogsAccount(code, name)) continue
      const net = parseNum(raw?.debitAmount) - parseNum(raw?.creditAmount)
      const type = String(raw?.entryType || 'AJE').toUpperCase()
      if (type === 'RJE') rje += net
      else aje += net
      lineCount += 1
    }
    return { aje, rje, lineCount }
  } catch {
    return { aje: 0, rje: 0, lineCount: 0 }
  }
}

export function useF5Adjudication(options: UseF5AdjudicationOptions) {
  const { projectId, allResponses, isReadonly } = options
  const readonly = isReadonly ?? ref(false)

  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  const auditNote = ref('')
  const auditConclusion = ref('')

  const storedMainRows = computed<StoredF5AdjRow[]>(() => {
    const resp = allResponses.value.get(MAIN_STORAGE_KEY)
    const parsed = safeParseRows<StoredF5AdjRow>(resp?.remark)
    return parsed.length ? parsed : DEFAULT_MAIN_ROWS.map((r) => ({ ...r }))
  })
  const mainBusinessRows: ComputedRef<F5AdjudicationRow[]> = computed(() =>
    storedMainRows.value.map(computeRow),
  )
  const mainSubtotal: ComputedRef<F5AdjudicationRow> = computed(() =>
    computeSubtotalRow(mainBusinessRows.value, '小计', 'main-subtotal'),
  )

  const storedOtherRows = computed<StoredF5AdjRow[]>(() => {
    const resp = allResponses.value.get(OTHER_STORAGE_KEY)
    const parsed = safeParseRows<StoredF5AdjRow>(resp?.remark)
    return parsed.length ? parsed : DEFAULT_OTHER_ROWS.map((r) => ({ ...r }))
  })
  const otherBusinessRows: ComputedRef<F5AdjudicationRow[]> = computed(() =>
    storedOtherRows.value.map(computeRow),
  )
  const otherSubtotal: ComputedRef<F5AdjudicationRow> = computed(() =>
    computeSubtotalRow(otherBusinessRows.value, '小计', 'other-subtotal'),
  )

  const grandTotal: ComputedRef<F5AdjudicationRow> = computed(() =>
    computeSubtotalRow([mainSubtotal.value, otherSubtotal.value], '合计', 'grand-total'),
  )

  const trialBalanceAmount: ComputedRef<number> = computed(() =>
    parseNum(allResponses.value.get(TB_STORAGE_KEY)?.remark),
  )
  const priorTrialBalanceAmount: ComputedRef<number> = computed(() =>
    parseNum(allResponses.value.get(PRIOR_TB_STORAGE_KEY)?.remark),
  )
  /** 本期差异 = 本期审定合计 − 本期试算 */
  const variance: ComputedRef<number> = computed(() =>
    Math.round((grandTotal.value.currentAdjusted - trialBalanceAmount.value) * 100) / 100,
  )
  /** 上期差异 = 上期审定合计 − 上期试算 */
  const priorVariance: ComputedRef<number> = computed(() =>
    Math.round((grandTotal.value.priorAdjusted - priorTrialBalanceAmount.value) * 100) / 100,
  )

  /** 主营业务成本合计变动（源表审计说明关注点） */
  const mainCostChange = computed(() => ({
    changeAmount: mainSubtotal.value.changeAmount,
    changeRate: mainSubtotal.value.changeRate,
    currentAdjusted: mainSubtotal.value.currentAdjusted,
    priorAdjusted: mainSubtotal.value.priorAdjusted,
  }))

  /** 变动率绝对值超过 30% 的品种/小计，供审计说明与 AI 使用 */
  const significantChanges: ComputedRef<F5SignificantChangeItem[]> = computed(() => {
    const items: F5SignificantChangeItem[] = []
    const push = (group: F5SignificantChangeItem['group'], row: F5AdjudicationRow) => {
      if (typeof row.changeRate !== 'number') return
      if (Math.abs(row.changeRate) < F5_ADJ_CHANGE_RATE_THRESHOLD) return
      items.push({
        group,
        label: row.label,
        priorAdjusted: row.priorAdjusted,
        currentAdjusted: row.currentAdjusted,
        changeAmount: row.changeAmount,
        changeRate: row.changeRate,
      })
    }
    for (const row of mainBusinessRows.value) push('main', row)
    push('subtotal', { ...mainSubtotal.value, label: '主营业务成本小计' })
    for (const row of otherBusinessRows.value) push('other', row)
    return items
  })

  const pendingSyncCount = computed(() => {
    const existing = new Set(mainBusinessRows.value.map((r) => r.label.trim()).filter(Boolean))
    return extractF5AdjudicationCandidatesFromMonthly(
      allResponses.value.get(MONTHLY_DETAIL_KEY)?.remark,
    ).filter((c) => !existing.has(c.product)).length
  })

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

  function updatePriorTrialBalance(value: number | string): void {
    if (readonly.value) return
    const numVal = typeof value === 'number' ? value : parseNum(value)
    allResponses.value.set(PRIOR_TB_STORAGE_KEY, {
      item_id: PRIOR_TB_STORAGE_KEY, conclusion: null, remark: String(numVal),
    })
    debounceSave()
  }

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
    persistRows(key, stored.length ? stored : defaultsFor(group))
  }

  function defaultsFor(group: 'main' | 'other'): StoredF5AdjRow[] {
    return (group === 'main' ? DEFAULT_MAIN_ROWS : DEFAULT_OTHER_ROWS).map((r) => ({ ...r }))
  }

  /** 从 F5-2 同步品种到主营区，并回填/刷新未审数 */
  function syncFromMonthlyDetail(): number {
    if (readonly.value) return 0
    const candidates = extractF5AdjudicationCandidatesFromMonthly(
      allResponses.value.get(MONTHLY_DETAIL_KEY)?.remark,
    )
    const parsed = safeParseRows<StoredF5AdjRow>(allResponses.value.get(MAIN_STORAGE_KEY)?.remark)
    const stored = parsed.length ? parsed : DEFAULT_MAIN_ROWS.map((r) => ({ ...r }))
    const byLabel = new Map(stored.map((r) => [r.label.trim(), r]))
    let added = 0
    for (const candidate of candidates) {
      const existing = byLabel.get(candidate.product)
      if (existing) {
        existing.currentUnadjusted = candidate.currentUnadjusted
        existing.priorUnadjusted = candidate.priorUnadjusted
        if (!existing.indexRef) existing.indexRef = 'wp:F5-2'
        continue
      }
      stored.push({
        rowKey: `main-sync-${Date.now()}-${added}`,
        label: candidate.product,
        isFixed: false,
        currentUnadjusted: candidate.currentUnadjusted,
        currentAje: 0,
        currentRje: 0,
        priorUnadjusted: candidate.priorUnadjusted,
        priorAje: 0,
        priorRje: 0,
        indexRef: 'wp:F5-2',
      })
      byLabel.set(candidate.product, stored[stored.length - 1])
      added += 1
    }
    if (stored.length === 1 && stored[0].label === '品种1' && !stored[0].currentUnadjusted && added > 0) {
      stored.splice(0, 1)
    }
    persistRows(MAIN_STORAGE_KEY, stored)
    return added
  }

  /** 从 F5-3 同步其他业务成本项目到其他区 */
  function syncFromOtherCost(): number {
    if (readonly.value) return 0
    const candidates = extractF5AdjudicationCandidatesFromOtherCost(
      allResponses.value.get(OTHER_COST_KEY)?.remark
        ?? allResponses.value.get(OTHER_COST_LEGACY_KEY)?.remark,
    )
    const parsed = safeParseRows<StoredF5AdjRow>(allResponses.value.get(OTHER_STORAGE_KEY)?.remark)
    const stored = parsed.length ? parsed : DEFAULT_OTHER_ROWS.map((r) => ({ ...r }))
    const byLabel = new Map(stored.map((r) => [r.label.trim(), r]))
    let added = 0
    for (const candidate of candidates) {
      const existing = byLabel.get(candidate.item)
      if (existing) {
        existing.currentUnadjusted = candidate.currentUnadjusted
        existing.priorUnadjusted = candidate.priorUnadjusted
        if (!existing.indexRef) existing.indexRef = 'wp:F5-3'
        continue
      }
      stored.push({
        rowKey: `other-sync-${Date.now()}-${added}`,
        label: candidate.item,
        isFixed: false,
        currentUnadjusted: candidate.currentUnadjusted,
        currentAje: 0,
        currentRje: 0,
        priorUnadjusted: candidate.priorUnadjusted,
        priorAje: 0,
        priorRje: 0,
        indexRef: 'wp:F5-3',
      })
      byLabel.set(candidate.item, stored[stored.length - 1])
      added += 1
    }
    if (
      stored.length === 1
      && stored[0].label === '其他业务成本1'
      && !stored[0].currentUnadjusted
      && added > 0
    ) {
      stored.splice(0, 1)
    }
    persistRows(OTHER_STORAGE_KEY, stored)
    return added
  }

  /** 将 F5-4 中 6401 相关 AJE/RJE 净额同步到主营区专用汇总行 */
  function syncFromAdjustment(): { aje: number; rje: number; lineCount: number } {
    if (readonly.value) return { aje: 0, rje: 0, lineCount: 0 }
    const impact = aggregateF54AdjustmentImpact(allResponses.value.get(ADJUSTMENT_KEY)?.remark)
    const parsed = safeParseRows<StoredF5AdjRow>(allResponses.value.get(MAIN_STORAGE_KEY)?.remark)
    const stored = parsed.length ? parsed.filter((r) => r.rowKey !== F54_SYNC_ROW_KEY) : []
    if (impact.lineCount > 0 || Math.abs(impact.aje) >= 0.005 || Math.abs(impact.rje) >= 0.005) {
      stored.push({
        rowKey: F54_SYNC_ROW_KEY,
        label: F54_SYNC_LABEL,
        isFixed: true,
        currentUnadjusted: 0,
        currentAje: impact.aje,
        currentRje: impact.rje,
        priorUnadjusted: 0,
        priorAje: 0,
        priorRje: 0,
        indexRef: 'wp:F5-4',
      })
    }
    persistRows(MAIN_STORAGE_KEY, stored.length ? stored : DEFAULT_MAIN_ROWS.map((r) => ({ ...r })))
    return impact
  }

  function persistRows(key: string, rows: StoredF5AdjRow[]): void {
    allResponses.value.set(key, { item_id: key, conclusion: null, remark: JSON.stringify(rows) })
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
        allResponses.value.get(MAIN_STORAGE_KEY),
        allResponses.value.get(OTHER_STORAGE_KEY),
        allResponses.value.get(TB_STORAGE_KEY),
        allResponses.value.get(PRIOR_TB_STORAGE_KEY),
        allResponses.value.get(NOTE_STORAGE_KEY),
        allResponses.value.get(CONCLUSION_STORAGE_KEY),
      ].filter(Boolean)
      window.dispatchEvent(new CustomEvent('f5:save-items', { detail: { items } }))
    } catch { /* silent */ }
  }

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

  function saveAuditNote(value: string): void {
    if (readonly.value) return
    auditNote.value = value
    allResponses.value.set(NOTE_STORAGE_KEY, { item_id: NOTE_STORAGE_KEY, conclusion: null, remark: value })
    debounceSave()
  }

  function saveAuditConclusion(value: string): void {
    if (readonly.value) return
    auditConclusion.value = value
    allResponses.value.set(CONCLUSION_STORAGE_KEY, {
      item_id: CONCLUSION_STORAGE_KEY, conclusion: null, remark: value,
    })
    debounceSave()
  }

  // 兼容旧 v-model 绑定：仍 watch 本地 ref
  watch(auditNote, (val) => {
    const existing = allResponses.value.get(NOTE_STORAGE_KEY)?.remark
    if (existing === val) return
    allResponses.value.set(NOTE_STORAGE_KEY, { item_id: NOTE_STORAGE_KEY, conclusion: null, remark: val })
    debounceSave()
  })
  watch(auditConclusion, (val) => {
    const existing = allResponses.value.get(CONCLUSION_STORAGE_KEY)?.remark
    if (existing === val) return
    allResponses.value.set(CONCLUSION_STORAGE_KEY, {
      item_id: CONCLUSION_STORAGE_KEY, conclusion: null, remark: val,
    })
    debounceSave()
  })

  function serialize(): Record<string, string> {
    return {
      [MAIN_STORAGE_KEY]: JSON.stringify(storedMainRows.value),
      [OTHER_STORAGE_KEY]: JSON.stringify(storedOtherRows.value),
      [TB_STORAGE_KEY]: String(trialBalanceAmount.value),
      [PRIOR_TB_STORAGE_KEY]: String(priorTrialBalanceAmount.value),
      [NOTE_STORAGE_KEY]: auditNote.value,
      [CONCLUSION_STORAGE_KEY]: auditConclusion.value,
    }
  }

  function deserialize(data: Record<string, string>): void {
    for (const key of [MAIN_STORAGE_KEY, OTHER_STORAGE_KEY, TB_STORAGE_KEY, PRIOR_TB_STORAGE_KEY]) {
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
    priorTrialBalanceAmount,
    variance,
    priorVariance,
    mainCostChange,
    significantChanges,
    pendingSyncCount,
    updateCell,
    updateTrialBalance,
    updatePriorTrialBalance,
    addRow,
    removeRow,
    syncFromMonthlyDetail,
    syncFromOtherCost,
    syncFromAdjustment,
    auditNote,
    auditConclusion,
    saveAuditNote,
    saveAuditConclusion,
    publishAdjudicated,
    serialize,
    deserialize,
  }
}

export default useF5Adjudication
