/**
 * useG2InterestCalc — G2-5 应收利息测算表
 *
 * 对齐 Excel「应收利息测算表 G2-5」列口径：
 *   ①账面金额 × ②票面年利率 × ③计息天数 / 365 = ④应计利息
 *   ⑦差异 = ④应计利息 − ⑥已计利息
 *   ⑤其中：已到期可收取 — 资产负债表「应收利息」仅反映已到期可收取尚未收到部分
 *
 * Spec: .kiro/specs/g2-interest-receivable/ Task 5.2
 * Requirements: 8.1~8.8
 */
import { ref, computed, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import {
  parseNum,
  calcAccruedDays,
  calcInterest365,
} from './useG2IntRecFormulaEngine'
import { extractAdjAmounts } from './g2SoeDisclosureRows'
import type { ChecklistResponse } from './useF1FormData'

/** 存储行（不含公式计算字段） */
export interface StoredInterestCalcRow {
  id: string
  seq: number
  /** 投资项目 */
  investTarget: string
  /** ① 账面金额（面值/本金） */
  faceValue: number
  /** ② 票面年利率(%) */
  couponRate: number
  accrualStart: string
  accrualEnd: string
  /** ⑤ 其中：已到期可收取 */
  maturedCollectible: number
  /** ⑥ 已计利息（企业账面已确认） */
  companyAccrual: number
  /** 差异原因 */
  varianceReason: string
  remark: string
  /**
   * 实际利率法：利息计入金融工具账面余额，不进科目 1132。
   * 勾选后⑤不计入「应收利息」合计数勾稽。
   */
  eirInInstrument: boolean
  /** 来源 G2-2 行 id（取数追溯） */
  sourceDetailId?: string
}

/** 展示行（含公式计算字段） */
export interface InterestCalcRow extends StoredInterestCalcRow {
  /** ③ 计息天数 */
  accruedDays: number
  /** ④ 应计利息 */
  calculatedInterest: number
  /** ⑦ 差异 = ④ − ⑥ */
  variance: number
}

export interface InterestCalcTotals {
  faceValue: number
  calculatedInterest: number
  maturedCollectible: number
  /** 计入 1132 的已到期可收取（排除实际利率法进工具余额的行） */
  maturedFor1132: number
  /** 实际利率法行：应计利息合计（进工具账面） */
  eirAccruedTotal: number
  eirRowCount: number
  companyAccrual: number
  variance: number
}

export interface InterestCalcCrossCheck {
  /** G2-2 应计利息合计（若有） */
  detailAccruedTotal: number | null
  /** 本表应计利息合计 */
  calcAccruedTotal: number
  diff: number
  matched: boolean
  detailRowCount: number
}

/** ⑤→G2-1 原值审定勾稽 */
export interface InterestCalcAdjTieOut {
  /** 本表计入 1132 的⑤合计 */
  maturedFor1132: number
  /** G2-1 原值期末审定（若有） */
  adjGrossEnd: number | null
  diff: number
  matched: boolean
  hasAdjData: boolean
}

const STORAGE_KEY = 'G2-5-interest-calc-rows'
const DETAIL_KEY = 'G2-2-detail-rows'
const ADJ_KEY = 'G2-1-rows'
const ADJ_KEY_LEGACY = 'G2-1-adj-rows'
const ADJ_NOTE_KEY = 'G2-1-note'
const ADJ_NOTE_KEY_LEGACY = 'G2-1-adj-note'
export const G2_INTEREST_VARIANCE_THRESHOLD = 100

/** G2-1 审计说明中的对照块锚点（重复推送时整块替换） */
export const G21_CALC_CROSS_REF_START = '【G2-5测算对照】'
export const G21_CALC_CROSS_REF_END = '【/G2-5测算对照】'

function fmtAmt(n: number): string {
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

/** 生成写入 G2-1 的对照说明块 */
export function buildG21CalcCrossRefNote(input: {
  maturedFor1132: number
  adjGrossEnd: number | null
  eirAccruedTotal: number
  eirRowCount: number
  calculatedInterest: number
  companyAccrual: number
  variance: number
}): string {
  const adj = input.adjGrossEnd
  const diff = adj == null ? null : Math.round((input.maturedFor1132 - adj) * 100) / 100
  const lines = [
    G21_CALC_CROSS_REF_START,
    `计入1132的已到期可收取⑤：${fmtAmt(input.maturedFor1132)}`,
    adj == null
      ? 'G2-1 原值审定：尚未取到（请先编制 G2-1）'
      : `G2-1 原值审定：${fmtAmt(adj)}`,
    diff == null
      ? '差额：—'
      : `差额（⑤−原值）：${fmtAmt(diff)}${Math.abs(diff) < 0.01 ? '（勾稽一致）' : '（须核查）'}`,
    `应计利息④合计：${fmtAmt(input.calculatedInterest)}；已计利息⑥合计：${fmtAmt(input.companyAccrual)}；差异⑦合计：${fmtAmt(input.variance)}`,
    input.eirRowCount > 0
      ? `实际利率法 ${input.eirRowCount} 行应计 ${fmtAmt(input.eirAccruedTotal)}（进工具账面，不进1132）`
      : '实际利率法：无',
    `更新时间：${new Date().toLocaleString('zh-CN', { hour12: false })}`,
    G21_CALC_CROSS_REF_END,
  ]
  return lines.join('\n')
}

/** 将对照块合并进既有审计说明（同锚点则替换） */
export function mergeG21CalcCrossRefNote(existing: string, block: string): string {
  const start = existing.indexOf(G21_CALC_CROSS_REF_START)
  const end = existing.indexOf(G21_CALC_CROSS_REF_END)
  if (start >= 0 && end > start) {
    const before = existing.slice(0, start).replace(/\n+$/, '')
    const after = existing.slice(end + G21_CALC_CROSS_REF_END.length).replace(/^\n+/, '')
    return [before, block, after].filter(Boolean).join('\n\n')
  }
  const base = (existing || '').trim()
  return base ? `${base}\n\n${block}` : block
}

function generateId(): string {
  return `intcalc-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

/** 导入兼容：是/否/true/false/1/0 */
export function parseEirFlag(raw: unknown): boolean {
  if (typeof raw === 'boolean') return raw
  if (typeof raw === 'number') return raw !== 0
  const s = String(raw ?? '').trim().toLowerCase()
  if (!s) return false
  if (['否', 'no', 'n', 'false', '0', 'f'].includes(s)) return false
  if (['是', 'yes', 'y', 'true', '1', 't'].includes(s)) return true
  return Boolean(raw)
}

/**
 * 按投资项目/种类推断是否实际利率法（利息进工具账面、不进1132）。
 * 债权投资/其他债权投资/摊余成本类 → true；定期存款/委托贷款 → false。
 */
export function inferEirInInstrument(investTarget: string, investType = ''): boolean {
  const text = `${investType} ${investTarget}`.toLowerCase()
  if (!text.trim()) return false
  // 明确排除
  if (/定期存款|定存|通知存款|委托贷款|entrusted|deposit/.test(text)) return false
  // 实际利率法常见工具
  if (
    /其他债权投资|债权投资|摊余成本|实际利率|amorti|aci\b|debt.?invest|bond.?invest|债券投资/.test(text)
  ) {
    return true
  }
  return false
}

function safeParseRows(jsonStr: string | null | undefined): StoredInterestCalcRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    if (!Array.isArray(parsed)) return []
    return parsed.map((r: any, i: number) => {
      const investTarget = String(r?.investTarget || '')
      const companyAccrual = parseNum(
        r?.companyAccrual ?? r?.companyInterest /* 旧导入列名 */,
      )
      let eirInInstrument = parseEirFlag(r?.eirInInstrument)
      // 未显式标记时按名称推断（导入旧模板无该列）
      if (r?.eirInInstrument == null || r?.eirInInstrument === '') {
        eirInInstrument = inferEirInInstrument(investTarget, String(r?.investType || ''))
      }
      return {
        id: String(r?.id || generateId()),
        seq: Number(r?.seq) || i + 1,
        investTarget,
        faceValue: parseNum(r?.faceValue),
        couponRate: parseNum(r?.couponRate),
        accrualStart: String(r?.accrualStart || ''),
        accrualEnd: String(r?.accrualEnd || ''),
        maturedCollectible: eirInInstrument
          ? 0
          : parseNum(r?.maturedCollectible),
        companyAccrual,
        varianceReason: String(r?.varianceReason || ''),
        remark: String(r?.remark || ''),
        eirInInstrument,
        sourceDetailId: r?.sourceDetailId ? String(r.sourceDetailId) : undefined,
      }
    })
  } catch {
    return []
  }
}

function computeRow(stored: StoredInterestCalcRow): InterestCalcRow {
  const accruedDays = calcAccruedDays(stored.accrualStart, stored.accrualEnd)
  const calculatedInterest = calcInterest365(stored.faceValue, stored.couponRate, accruedDays)
  const variance = calculatedInterest - stored.companyAccrual
  return {
    ...stored,
    accruedDays,
    calculatedInterest,
    variance,
  }
}

function createEmptyStoredRow(seq: number): StoredInterestCalcRow {
  return {
    id: generateId(),
    seq,
    investTarget: '',
    faceValue: 0,
    couponRate: 0,
    accrualStart: '',
    accrualEnd: '',
    maturedCollectible: 0,
    companyAccrual: 0,
    varianceReason: '',
    remark: '',
    eirInInstrument: false,
  }
}

/** 从 G2-2 明细原始 JSON 提取可测算行 */
export function extractCalcRowsFromDetail(detailRaw: string | null | undefined): StoredInterestCalcRow[] {
  if (!detailRaw) return []
  try {
    const parsed = JSON.parse(detailRaw)
    if (!Array.isArray(parsed)) return []
    const out: StoredInterestCalcRow[] = []
    let seq = 1
    for (const r of parsed) {
      const faceValue = parseNum(r?.faceValue)
      const couponRate = parseNum(r?.couponRate)
      const accrualStart = String(r?.accrualStart || '')
      const accrualEnd = String(r?.accrualEnd || '')
      const investTarget = String(r?.investTarget || r?.investType || '')
      const investType = String(r?.investType || '')
      // 无计息基础则跳过
      if (!faceValue && !couponRate && !accrualStart && !accrualEnd) continue
      const accruedDays = calcAccruedDays(accrualStart, accrualEnd)
      const calculatedInterest = calcInterest365(faceValue, couponRate, accruedDays)
      // 企业已计：优先用明细净应收/期末审定作为对照起点
      const companyAccrual =
        parseNum(r?.closingAudited)
        || parseNum(r?.netReceivable)
        || parseNum(r?.bookValue)
        || 0
      const eirInInstrument =
        r?.eirInInstrument != null && r?.eirInInstrument !== ''
          ? parseEirFlag(r.eirInInstrument)
          : inferEirInInstrument(investTarget, investType)
      out.push({
        id: generateId(),
        seq: seq++,
        investTarget,
        faceValue,
        couponRate,
        accrualStart,
        accrualEnd,
        maturedCollectible: eirInInstrument ? 0 : calculatedInterest,
        companyAccrual,
        varianceReason: eirInInstrument ? '实际利率法：利息计入金融工具账面余额' : '',
        remark: r?.id ? '来源G2-2' : '',
        eirInInstrument,
        sourceDetailId: r?.id ? String(r.id) : undefined,
      })
    }
    return out
  } catch {
    return []
  }
}

export function sumDetailAccrued(detailRaw: string | null | undefined): { total: number; count: number } {
  if (!detailRaw) return { total: 0, count: 0 }
  try {
    const parsed = JSON.parse(detailRaw)
    if (!Array.isArray(parsed)) return { total: 0, count: 0 }
    let total = 0
    let count = 0
    for (const r of parsed) {
      const faceValue = parseNum(r?.faceValue)
      const couponRate = parseNum(r?.couponRate)
      const days = calcAccruedDays(String(r?.accrualStart || ''), String(r?.accrualEnd || ''))
      if (!faceValue && !couponRate && !days) continue
      total += calcInterest365(faceValue, couponRate, days)
      count += 1
    }
    return { total, count }
  } catch {
    return { total: 0, count: 0 }
  }
}

export interface UseG2InterestCalcOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}

export function useG2InterestCalc(options: UseG2InterestCalcOptions) {
  const { allResponses, isReadonly } = options
  const readonly = isReadonly ?? ref(false)

  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  const storedRows = computed<StoredInterestCalcRow[]>(() => {
    const resp = allResponses.value.get(STORAGE_KEY)
    return safeParseRows(resp?.remark)
  })

  const dataRows: ComputedRef<InterestCalcRow[]> = computed(() =>
    storedRows.value.map((s) => computeRow(s)),
  )

  const totals: ComputedRef<InterestCalcTotals> = computed(() => {
    const rows = dataRows.value
    let maturedFor1132 = 0
    let eirAccruedTotal = 0
    let eirRowCount = 0
    for (const r of rows) {
      if (r.eirInInstrument) {
        eirAccruedTotal += r.calculatedInterest
        eirRowCount += 1
      } else {
        maturedFor1132 += r.maturedCollectible
      }
    }
    return {
      faceValue: rows.reduce((sum, r) => sum + r.faceValue, 0),
      calculatedInterest: rows.reduce((sum, r) => sum + r.calculatedInterest, 0),
      maturedCollectible: rows.reduce((sum, r) => sum + r.maturedCollectible, 0),
      maturedFor1132,
      eirAccruedTotal,
      eirRowCount,
      companyAccrual: rows.reduce((sum, r) => sum + r.companyAccrual, 0),
      variance: rows.reduce((sum, r) => sum + r.variance, 0),
    }
  })

  const crossCheck: ComputedRef<InterestCalcCrossCheck> = computed(() => {
    const detailRaw = allResponses.value.get(DETAIL_KEY)?.remark
    const { total, count } = sumDetailAccrued(detailRaw)
    const calcAccruedTotal = totals.value.calculatedInterest
    if (count === 0) {
      return {
        detailAccruedTotal: null,
        calcAccruedTotal,
        diff: 0,
        matched: true,
        detailRowCount: 0,
      }
    }
    const diff = Math.round((calcAccruedTotal - total) * 100) / 100
    return {
      detailAccruedTotal: total,
      calcAccruedTotal,
      diff,
      matched: Math.abs(diff) < 0.01,
      detailRowCount: count,
    }
  })

  const adjTieOut: ComputedRef<InterestCalcAdjTieOut> = computed(() => {
    const adjRaw =
      allResponses.value.get(ADJ_KEY)?.remark
      ?? allResponses.value.get(ADJ_KEY_LEGACY)?.remark
    const maturedFor1132 = totals.value.maturedFor1132
    if (!adjRaw) {
      return {
        maturedFor1132,
        adjGrossEnd: null,
        diff: 0,
        matched: true,
        hasAdjData: false,
      }
    }
    const adj = extractAdjAmounts(adjRaw)
    const hasAdjData =
      adj.grossEnd !== 0
      || adj.grossPrior !== 0
      || adj.provisionEnd !== 0
      || adj.netEnd !== 0
    if (!hasAdjData) {
      return {
        maturedFor1132,
        adjGrossEnd: null,
        diff: 0,
        matched: true,
        hasAdjData: false,
      }
    }
    const diff = Math.round((maturedFor1132 - adj.grossEnd) * 100) / 100
    return {
      maturedFor1132,
      adjGrossEnd: adj.grossEnd,
      diff,
      matched: Math.abs(diff) < 0.01,
      hasAdjData: true,
    }
  })

  /** |差异|>阈值 → 橙色；且差异原因应填 */
  function isVarianceWarning(row: InterestCalcRow): boolean {
    return Math.abs(row.variance) > G2_INTEREST_VARIANCE_THRESHOLD
  }

  function isVarianceReasonRequired(row: InterestCalcRow): boolean {
    return isVarianceWarning(row) && !String(row.varianceReason || '').trim()
  }

  /** 已到期可收取不应超过应计利息（实际利率法行豁免：⑤应为 0） */
  function isMaturedOverAccrued(row: InterestCalcRow): boolean {
    if (row.eirInInstrument) {
      return row.maturedCollectible > 0.005
    }
    return row.maturedCollectible > row.calculatedInterest + 0.005
  }

  const warningCount = computed(() =>
    dataRows.value.filter((r) => isVarianceWarning(r) || isMaturedOverAccrued(r)).length,
  )

  const missingReasonCount = computed(() =>
    dataRows.value.filter((r) => isVarianceReasonRequired(r)).length,
  )

  function addRow(): void {
    if (readonly.value) return
    const current = safeParseRows(allResponses.value.get(STORAGE_KEY)?.remark)
    const nextSeq = current.length > 0 ? Math.max(...current.map((r) => r.seq)) + 1 : 1
    current.push(createEmptyStoredRow(nextSeq))
    persistRows(current)
  }

  function removeRow(id: string): void {
    if (readonly.value) return
    const current = safeParseRows(allResponses.value.get(STORAGE_KEY)?.remark)
    const filtered = current.filter((r) => r.id !== id)
    filtered.forEach((r, i) => { r.seq = i + 1 })
    persistRows(filtered)
  }

  function updateCell(
    rowId: string,
    field: keyof StoredInterestCalcRow,
    value: string | number | boolean,
  ): void {
    if (readonly.value) return
    const current = safeParseRows(allResponses.value.get(STORAGE_KEY)?.remark)
    const idx = current.findIndex((r) => r.id === rowId)
    if (idx === -1) return

    const numericFields: (keyof StoredInterestCalcRow)[] = [
      'faceValue', 'couponRate', 'companyAccrual', 'maturedCollectible',
    ]
    if (field === 'eirInInstrument') {
      current[idx].eirInInstrument = Boolean(value)
      // 标记为进工具余额时，⑤清零（不进 1132）
      if (current[idx].eirInInstrument) {
        current[idx].maturedCollectible = 0
        if (!current[idx].varianceReason) {
          current[idx].varianceReason = '实际利率法：利息计入金融工具账面余额'
        }
      }
    } else if (numericFields.includes(field)) {
      ;(current[idx] as any)[field] = typeof value === 'number' ? value : parseNum(value)
    } else {
      ;(current[idx] as any)[field] = value
    }
    persistRows(current)
  }

  /** 批量标记/取消实际利率法 */
  function setEirInInstrument(rowId: string, flagged: boolean): void {
    updateCell(rowId, 'eirInInstrument', flagged)
  }

  /** 从 G2-2 明细灌入测算行（覆盖本表） */
  function pullFromDetail(replace = true): { pulled: number } {
    if (readonly.value) return { pulled: 0 }
    const detailRaw = allResponses.value.get(DETAIL_KEY)?.remark
    const pulled = extractCalcRowsFromDetail(detailRaw)
    if (!pulled.length) return { pulled: 0 }
    if (replace) {
      persistRows(pulled)
      return { pulled: pulled.length }
    }
    const current = safeParseRows(allResponses.value.get(STORAGE_KEY)?.remark)
    const existingSources = new Set(current.map((r) => r.sourceDetailId).filter(Boolean))
    const toAdd = pulled.filter((r) => !r.sourceDetailId || !existingSources.has(r.sourceDetailId))
    let seq = current.length > 0 ? Math.max(...current.map((r) => r.seq)) + 1 : 1
    for (const r of toAdd) {
      r.seq = seq++
      current.push(r)
    }
    persistRows(current)
    return { pulled: toAdd.length }
  }

  /**
   * 一键将⑤合计等对照信息写入 G2-1 审计说明（不改审定数）。
   * 重复推送时替换【G2-5测算对照】块。
   */
  function pushCrossRefToG21(): {
    ok: boolean
    note: string
    matched: boolean
    maturedFor1132: number
  } {
    if (readonly.value) {
      return { ok: false, note: '', matched: true, maturedFor1132: 0 }
    }
    const tie = adjTieOut.value
    const t = totals.value
    const block = buildG21CalcCrossRefNote({
      maturedFor1132: t.maturedFor1132,
      adjGrossEnd: tie.adjGrossEnd,
      eirAccruedTotal: t.eirAccruedTotal,
      eirRowCount: t.eirRowCount,
      calculatedInterest: t.calculatedInterest,
      companyAccrual: t.companyAccrual,
      variance: t.variance,
    })
    const existing =
      allResponses.value.get(ADJ_NOTE_KEY)?.remark
      ?? allResponses.value.get(ADJ_NOTE_KEY_LEGACY)?.remark
      ?? ''
    const merged = mergeG21CalcCrossRefNote(existing, block)
    allResponses.value.set(ADJ_NOTE_KEY, {
      item_id: ADJ_NOTE_KEY,
      conclusion: null,
      remark: merged,
    })
    // 立即落库（含 G2-1-note + 本表）
    try {
      const items = [
        allResponses.value.get(STORAGE_KEY),
        allResponses.value.get(ADJ_NOTE_KEY),
      ].filter(Boolean)
      window.dispatchEvent(new CustomEvent('g2:save-items', { detail: { items } }))
      window.dispatchEvent(
        new CustomEvent('g2:calc-cross-ref', {
          detail: {
            maturedFor1132: t.maturedFor1132,
            adjGrossEnd: tie.adjGrossEnd,
            diff: tie.diff,
            matched: tie.matched,
            note: merged,
          },
        }),
      )
    } catch { /* silent */ }
    return {
      ok: true,
      note: merged,
      matched: tie.matched || !tie.hasAdjData,
      maturedFor1132: t.maturedFor1132,
    }
  }

  function persistRows(rows: StoredInterestCalcRow[]): void {
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
    crossCheck,
    adjTieOut,
    warningCount,
    missingReasonCount,
    isVarianceWarning,
    isVarianceReasonRequired,
    isMaturedOverAccrued,
    addRow,
    removeRow,
    updateCell,
    setEirInInstrument,
    pullFromDetail,
    pushCrossRefToG21,
    VARIANCE_THRESHOLD: G2_INTEREST_VARIANCE_THRESHOLD,
  }
}

export default useG2InterestCalc
