/**
 * useH3Depreciation — H3-7 折旧测算 composable（仅成本模式）
 *
 * 对齐 Excel「折旧测算表（成本模式不含/含减值）H3-7」：
 * - 按开始使用日期推算已提月数、本期月数、满折日
 * - 不含减值：测算月折旧 vs 账面月折旧；测算累计 vs 账面累计
 * - 含减值：减值日前后分段计提；与 H3-10 减值准备勾稽
 */
import { ref, computed, watch, type Ref } from 'vue'
import type { ChecklistItem } from './useH3FormData'
import {
  calcStraightLineTest,
  calcWithImpairmentTest,
  calcMultiImpairmentTest,
  type MultiImpairmentEventInput,
} from './useH3DepreciationEngine'

export type { MultiImpairmentEventInput }

// ─── Types ───────────────────────────────────────────────────────────────────

export type DepreciationBranch = 'noImpair' | 'withImpair'

/** 用户录入字段（持久化） */
export interface H3DepreciationRowInput {
  rowId: string
  assetNo?: string
  category?: string
  assetName: string
  department?: string
  originalCost: number
  bookAccDepEnd: number
  /** 单次减值（兼容旧数据；多次减值时由 impairmentEvents 计算汇总） */
  impairment?: number
  startDate?: string
  usefulLife: number
  salvageRate: number
  bookMonthly?: number
  bookDepreciation?: number
  /** 单次减值日期（兼容旧数据）*/
  impairmentDate?: string
  /** 单次减值时累计折旧（兼容旧数据） */
  accDepAtImpairment?: number
  /** 多次减值事件列表（事件数 ≥ 2 时启用分段折旧）*/
  impairmentEvents?: MultiImpairmentEventInput[]
  disposalDate?: string
  remark?: string
}

/** 测算结果字段（计算列） */
export interface H3DepreciationRow extends H3DepreciationRowInput {
  usefulLifeMonths: number
  fullDepDate: string
  monthsAtEnd: number
  periodMonths: number
  calcMonthly: number
  periodDep: number
  monthlyDiff: number
  calcAccDep: number
  accDepDiff: number
  difference: number
  // 含减值专用
  monthsAtImpairment?: number
  monthsBeforeImpairment?: number
  monthsAfterImpairment?: number
  preImpairmentMonthly?: number
  postImpairmentMonthly?: number
  /** 多次减值时，减值事件总计金额 */
  totalImpairment?: number
  /** 是否使用了多段折旧引擎 */
  isMultiImpair?: boolean
}

export interface H3DepReconcileResult {
  h31AuditedDepTotal: number
  h37BookAccTotal: number
  h37CalcAccTotal: number
  bookDiff: number
  calcDiff: number
  matched: boolean
}

const ITEM_ID = 'H3-7-dep-rows'
const BRANCH_ID = 'H3-7-branch'
const PERIOD_END_KEY = 'H3-7-period-end'
const PERIOD_BEGIN_KEY = 'H3-7-period-begin'
const RECALC_RATE_KEY = 'H3-7-dep-recalc-rate'
const RECALC_NOTE_KEY = 'H3-7-dep-recalc-note'
const H32_COST_ROWS_KEY = 'H3-2-cost-rows'
const H31_COST_DEP_ROWS_KEY = 'H3-1-cost-dep-rows'
const H310_CALC_ROWS_KEY = 'H3-10-calc-rows'

function defaultPeriodEnd(year?: number): string {
  const y = year && year > 1900 ? year : new Date().getFullYear()
  return `${y}-12-31`
}

function defaultPeriodBegin(periodEnd: string): string {
  const y = periodEnd.slice(0, 4)
  return `${y}-01-01`
}

function migrateRaw(raw: any): H3DepreciationRowInput {
  const events: MultiImpairmentEventInput[] | undefined = Array.isArray(raw.impairmentEvents)
    ? raw.impairmentEvents
        .filter((e: any) => Number(e?.amount) > 0)
        .map((e: any) => ({
          eventDate: e.eventDate ?? e.impairmentDate ?? null,
          amount: Number(e.amount) || 0,
          elapsedMonths: e.elapsedMonths != null ? Number(e.elapsedMonths) : undefined,
        }))
    : undefined

  return {
    rowId: raw.rowId ?? `dep-${Math.random().toString(36).slice(2, 8)}`,
    assetNo: raw.assetNo ?? '',
    category: raw.category ?? '',
    assetName: raw.assetName ?? '',
    department: raw.department ?? '',
    originalCost: Number(raw.originalCost) || 0,
    bookAccDepEnd: Number(raw.bookAccDepEnd ?? raw.accDepBook) || 0,
    impairment: Number(raw.impairment ?? raw.impairmentAmount) || 0,
    startDate: raw.startDate ?? '',
    usefulLife: Number(raw.usefulLife) || 20,
    salvageRate: Number(raw.salvageRate) || 0.05,
    bookMonthly: Number(raw.bookMonthly) || 0,
    bookDepreciation: Number(raw.bookDepreciation) || 0,
    impairmentDate: raw.impairmentDate ?? '',
    accDepAtImpairment: raw.accDepAtImpairment != null ? Number(raw.accDepAtImpairment) : undefined,
    impairmentEvents: events,
    disposalDate: raw.disposalDate ?? '',
    remark: raw.remark ?? '',
  }
}

function matchAssetName(a?: string, b?: string): boolean {
  const x = String(a || '').trim()
  const y = String(b || '').trim()
  if (!x || !y) return false
  return x === y || x.includes(y) || y.includes(x)
}

function normalizeSalvageRate(raw: any): number {
  const n = Number(raw)
  if (!Number.isFinite(n) || n <= 0) return 0.05
  return n > 1 ? n / 100 : n
}

function inferCategoryFromAssetType(assetType?: string): string {
  const t = String(assetType || '').trim()
  if (/土地|使用权/.test(t)) return '土地使用权'
  if (/房屋|建筑|楼宇/.test(t)) return '房屋及建筑物'
  return t || '其他'
}

function appendRemark(...parts: Array<string | undefined>): string {
  return parts
    .map((part) => String(part || '').trim())
    .filter(Boolean)
    .filter((part, index, arr) => arr.indexOf(part) === index)
    .join('；')
}

function recalcRow(
  input: H3DepreciationRowInput,
  branch: DepreciationBranch,
  periodBegin: string,
  periodEnd: string,
): H3DepreciationRow {
  const baseParams = {
    cost: input.originalCost,
    salvageRate: input.salvageRate,
    usefulLifeYears: input.usefulLife,
    startDate: input.startDate || null,
    periodBegin,
    periodEnd,
    disposalDate: input.disposalDate || null,
    bookMonthly: input.bookMonthly ?? 0,
    bookAccDepEnd: input.bookAccDepEnd,
  }

  if (branch === 'withImpair') {
    // 多次减值（事件数 ≥ 2）—— 分段折旧引擎
    const events = input.impairmentEvents?.filter((e) => (e.amount ?? 0) > 0) ?? []
    if (events.length >= 2) {
      const r = calcMultiImpairmentTest({
        ...baseParams,
        events,
      })
      const bookDep = input.bookDepreciation ?? 0
      const totalImpairment = events.reduce((s, e) => s + (e.amount ?? 0), 0)
      return {
        ...input,
        usefulLifeMonths: r.usefulLifeMonths,
        fullDepDate: r.fullDepDate,
        monthsAtEnd: r.monthsAtEnd,
        periodMonths: r.periodMonths,
        calcMonthly: r.preImpairmentMonthly,
        periodDep: r.periodDep,
        monthlyDiff: r.monthlyDiff,
        calcAccDep: r.calcAccDep,
        accDepDiff: r.accDepDiff,
        difference: bookDep - r.periodDep,
        monthsBeforeImpairment: r.monthsBeforeImpairmentInPeriod,
        monthsAfterImpairment: r.monthsAfterImpairmentInPeriod,
        preImpairmentMonthly: r.preImpairmentMonthly,
        postImpairmentMonthly: r.postImpairmentMonthly,
        accDepAtImpairment: r.accDepAtImpairment,
        totalImpairment,
        isMultiImpair: true,
        // 同步到单次兼容字段（取首次事件）
        impairment: totalImpairment,
        impairmentDate: events[0]?.eventDate ?? input.impairmentDate,
      }
    }
    // 单次减值（事件数 0 或 1）——沿用原有引擎
    const singleAmount = events.length === 1 ? events[0].amount : (input.impairment ?? 0)
    const singleDate = events.length === 1 ? (events[0].eventDate ?? input.impairmentDate) : input.impairmentDate
    if (singleAmount > 0) {
      const r = calcWithImpairmentTest({
        ...baseParams,
        impairmentAmount: singleAmount,
        impairmentDate: singleDate || null,
        accDepAtImpairment: input.accDepAtImpairment,
      })
      const bookDep = input.bookDepreciation ?? 0
      return {
        ...input,
        usefulLifeMonths: r.usefulLifeMonths,
        fullDepDate: r.fullDepDate,
        monthsAtEnd: r.monthsAtEnd,
        periodMonths: r.periodMonths,
        calcMonthly: r.preImpairmentMonthly,
        periodDep: r.periodDep,
        monthlyDiff: r.monthlyDiff,
        calcAccDep: r.calcAccDep,
        accDepDiff: r.accDepDiff,
        difference: bookDep - r.periodDep,
        monthsAtImpairment: r.accDepAtImpairment != null
          ? Math.round(r.accDepAtImpairment / (r.preImpairmentMonthly || 1))
          : 0,
        monthsBeforeImpairment: r.monthsBeforeImpairmentInPeriod,
        monthsAfterImpairment: r.monthsAfterImpairmentInPeriod,
        preImpairmentMonthly: r.preImpairmentMonthly,
        postImpairmentMonthly: r.postImpairmentMonthly,
        accDepAtImpairment: r.accDepAtImpairment,
        totalImpairment: singleAmount,
        isMultiImpair: false,
      }
    }
  }

  const r = calcStraightLineTest(baseParams)
  const bookDep = input.bookDepreciation ?? 0
  return {
    ...input,
    usefulLifeMonths: r.usefulLifeMonths,
    fullDepDate: r.fullDepDate,
    monthsAtEnd: r.monthsAtEnd,
    periodMonths: r.periodMonths,
    calcMonthly: r.calcMonthly,
    periodDep: r.periodDep,
    monthlyDiff: r.monthlyDiff,
    calcAccDep: r.calcAccDep,
    accDepDiff: r.accDepDiff,
    difference: bookDep - r.periodDep,
  }
}

export function useH3Depreciation(params: {
  allResponses: Ref<Map<string, ChecklistItem>>
  wpId: Ref<string>
  projectId: Ref<string>
  branch: Ref<DepreciationBranch>
  periodEnd?: Ref<string | undefined>
  auditYear?: Ref<number | undefined>
  getValue: (id: string) => any
  setValue: (id: string, value: any) => void
  saveImmediate: (id: string, value: any) => Promise<void>
}) {
  const { allResponses, getValue, setValue, branch, periodEnd: periodEndRef, auditYear } = params

  const rows = ref<H3DepreciationRow[]>([])
  const periodEnd = ref('')
  const periodBegin = ref('')
  /** 折旧整体重算：手工综合年折旧率(%)覆盖（null=用理论推导值）+ 差异说明 */
  const depRecalcRateOverride = ref<number | null>(null)
  const depRecalcExplanation = ref('')

  function readStored(itemId: string): any {
    const item = allResponses.value.get(itemId)
    if (item) {
      const raw = item.remark ?? item.conclusion
      if (raw != null) {
        try { return JSON.parse(raw) } catch { return raw }
      }
    }
    return getValue(itemId)
  }

  function resolvePeriodDates(): void {
    const storedEnd = readStored(PERIOD_END_KEY)
    const storedBegin = readStored(PERIOD_BEGIN_KEY)
    const extEnd = periodEndRef?.value
    const year = auditYear?.value
    periodEnd.value = storedEnd || extEnd || defaultPeriodEnd(year)
    periodBegin.value = storedBegin || defaultPeriodBegin(periodEnd.value)
  }

  function loadRows(): void {
    resolvePeriodDates()
    const raw = readStored(ITEM_ID)
    const list = Array.isArray(raw) ? raw : []
    rows.value = list.map((r: any) => recalcRow(migrateRaw(r), branch.value, periodBegin.value, periodEnd.value))
    const rawRate = readStored(RECALC_RATE_KEY)
    depRecalcRateOverride.value = rawRate === '' || rawRate == null ? null : Number(rawRate)
    depRecalcExplanation.value = String(readStored(RECALC_NOTE_KEY) ?? '')
  }

  const totalOriginalCost = computed(() => rows.value.reduce((s, r) => s + (Number(r.originalCost) || 0), 0))
  const totalPeriodDep = computed(() => rows.value.reduce((s, r) => s + (r.periodDep || 0), 0))
  const totalBookDep = computed(() => rows.value.reduce((s, r) => s + (r.bookDepreciation || 0), 0))
  const totalDifference = computed(() => totalBookDep.value - totalPeriodDep.value)
  const totalAccDepCalc = computed(() => rows.value.reduce((s, r) => s + (r.calcAccDep || 0), 0))
  const totalAccDepBook = computed(() => rows.value.reduce((s, r) => s + (r.bookAccDepEnd || 0), 0))
  const totalAccDepDiff = computed(() => totalAccDepBook.value - totalAccDepCalc.value)
  const h31DepReconcile = computed<H3DepReconcileResult>(() => {
    const h31 = readStored(H31_COST_DEP_ROWS_KEY)
    const h31AuditedDepTotal = Array.isArray(h31)
      ? h31.reduce((sum: number, r: any) => sum + (Number(r?.audited) || 0), 0)
      : 0
    const bookDiff = totalAccDepBook.value - h31AuditedDepTotal
    const calcDiff = totalAccDepCalc.value - h31AuditedDepTotal
    return {
      h31AuditedDepTotal,
      h37BookAccTotal: totalAccDepBook.value,
      h37CalcAccTotal: totalAccDepCalc.value,
      bookDiff,
      calcDiff,
      matched: Math.abs(bookDiff) <= 0.01 && Math.abs(calcDiff) <= 0.01,
    }
  })

  const hasDiscrepancy = computed(() =>
    rows.value.some((r) =>
      Math.abs(r.difference) > 0.01
      || Math.abs(r.monthlyDiff) > 0.01
      || Math.abs(r.accDepDiff) > 0.01,
    ),
  )

  const significantDiffRows = computed(() =>
    rows.value.filter((r) =>
      Math.abs(r.difference) > 0.01
      || Math.abs(r.accDepDiff) > 0.01,
    ),
  )

  /**
   * 理论综合年折旧率（独立于账面折旧）= Σ(原值×(1−残值率)/使用年限) / Σ原值。
   * 由资产参数直接推导，作为整体重算的独立预期基准。
   */
  const impliedCompositeRate = computed(() => {
    let num = 0
    let den = 0
    for (const r of rows.value) {
      const cost = Number(r.originalCost) || 0
      const life = Number(r.usefulLife) || 0
      const sal = Number(r.salvageRate) || 0
      if (cost > 0 && life > 0) {
        num += (cost * (1 - sal)) / life
        den += cost
      }
    }
    return den > 0 ? num / den : 0
  })

  /**
   * 折旧合理性整体重算（实质性分析程序）：
   * 预期本期折旧 = 原值合计 × 综合年折旧率（手工优先，否则理论推导），与账面本期折旧比较，
   * 差异率 >10% 触发关注。此为高层独立分析，与逐行测算互补。
   */
  const depreciationRecalc = computed(() => {
    const grossTotal = totalOriginalCost.value
    const rate = depRecalcRateOverride.value != null
      ? (Number(depRecalcRateOverride.value) || 0) / 100
      : impliedCompositeRate.value
    const expected = grossTotal * rate
    const booked = totalBookDep.value
    const diff = booked - expected
    const diffRate = expected > 0 ? diff / expected : (booked > 0 ? 1 : 0)
    return {
      grossTotal,
      rate,
      ratePct: rate * 100,
      isManualRate: depRecalcRateOverride.value != null,
      expected,
      booked,
      diff,
      diffRate,
      diffRatePct: diffRate * 100,
      flagged: Math.abs(diffRate) > 0.1,
      hasBasis: grossTotal > 0 && rate > 0,
    }
  })

  function setDepRecalcRate(pct: number | null): void {
    depRecalcRateOverride.value = pct == null || Number.isNaN(Number(pct)) ? null : Number(pct)
    const stored = depRecalcRateOverride.value == null ? '' : String(depRecalcRateOverride.value)
    allResponses.value.set(RECALC_RATE_KEY, { item_id: RECALC_RATE_KEY, conclusion: null, remark: stored })
    setValue(RECALC_RATE_KEY, depRecalcRateOverride.value)
    void params.saveImmediate(RECALC_RATE_KEY, depRecalcRateOverride.value)
  }

  function setDepRecalcExplanation(text: string): void {
    depRecalcExplanation.value = text ?? ''
    allResponses.value.set(RECALC_NOTE_KEY, { item_id: RECALC_NOTE_KEY, conclusion: null, remark: depRecalcExplanation.value })
    setValue(RECALC_NOTE_KEY, depRecalcExplanation.value)
    void params.saveImmediate(RECALC_NOTE_KEY, depRecalcExplanation.value)
  }

  function setPeriodDates(begin: string, end: string): void {
    periodBegin.value = begin
    periodEnd.value = end
    allResponses.value.set(PERIOD_BEGIN_KEY, { item_id: PERIOD_BEGIN_KEY, conclusion: null, remark: begin })
    allResponses.value.set(PERIOD_END_KEY, { item_id: PERIOD_END_KEY, conclusion: null, remark: end })
    setValue(PERIOD_BEGIN_KEY, begin)
    setValue(PERIOD_END_KEY, end)
    void params.saveImmediate(PERIOD_BEGIN_KEY, begin)
    void params.saveImmediate(PERIOD_END_KEY, end)
    rows.value = rows.value.map((r) => recalcRow(r, branch.value, begin, end))
    _persist()
  }

  function setBranch(b: DepreciationBranch): void {
    branch.value = b
    setValue(BRANCH_ID, b)
    rows.value = rows.value.map((r) => recalcRow(r, b, periodBegin.value, periodEnd.value))
    _persist()
  }

  function addRow(assetName = ''): void {
    const blank = migrateRaw({ assetName, rowId: `dep-${Date.now()}` })
    rows.value.push(recalcRow(blank, branch.value, periodBegin.value, periodEnd.value))
    _persist()
  }

  function removeRow(index: number): void {
    rows.value.splice(index, 1)
    _persist()
  }

  function updateRow(index: number): void {
    const row = rows.value[index]
    if (!row) return
    const recalced = recalcRow(row, branch.value, periodBegin.value, periodEnd.value)
    Object.assign(row, recalced)
    _persist()
  }

  function recalcAll(): void {
    rows.value = rows.value.map((r) => recalcRow(r, branch.value, periodBegin.value, periodEnd.value))
    _persist()
  }

  function importFromH32(replace = true): { imported: number; skipped: number; message: string } {
    const raw = readStored(H32_COST_ROWS_KEY)
    const list = Array.isArray(raw) ? raw : []
    const mapped = list
      .filter((r: any) => String(r?.assetName || '').trim())
      .filter((r: any) => {
        const imp = Number(r?.impairmentEnd ?? r?.impairment ?? 0) || 0
        return branch.value === 'withImpair' ? imp > 0.01 : imp <= 0.01
      })
      .map((r: any) => migrateRaw({
        rowId: `dep-${r.rowId || Math.random().toString(36).slice(2, 8)}`,
        assetNo: r.assetNo ?? r.assetCode ?? '',
        category: r.category ?? inferCategoryFromAssetType(r.assetType),
        assetName: r.assetName ?? '',
        department: r.department ?? r.purpose ?? '',
        originalCost: Number(r.costEnd ?? r.originalCost ?? r.costBegin) || 0,
        bookAccDepEnd: Number(r.accDepEnd ?? 0) || 0,
        impairment: Number(r.impairmentEnd ?? r.impairment ?? 0) || 0,
        startDate: r.startDate ?? r.acquireDate ?? r.acquisitionDate ?? '',
        usefulLife: Number(r.usefulLife ?? r.usefulLifeYears) || 20,
        salvageRate: normalizeSalvageRate(r.salvageRate ?? r.salvageRatePct),
        bookMonthly: Number(r.bookMonthly ?? 0) || 0,
        bookDepreciation: Number(r.depProvision ?? r.bookDepreciation ?? 0) || 0,
        impairmentDate: Number(r.impairmentProvision ?? 0) > 0 ? periodBegin.value : '',
        remark: appendRemark(r.remark, '来源:H3-2'),
      }))
    const next = mapped.map((r) => recalcRow(r, branch.value, periodBegin.value, periodEnd.value))
    rows.value = replace ? next : [...rows.value, ...next]
    _persist()
    const skipped = list.filter((r: any) => String(r?.assetName || '').trim()).length - mapped.length
    return {
      imported: mapped.length,
      skipped,
      message: `已从 H3-2 带入 ${mapped.length} 行${skipped > 0 ? `，按当前分支过滤 ${skipped} 行` : ''}`,
    }
  }

  function syncFromH310(addMissing = true): { linked: number; added: number; message: string } {
    const raw = readStored(H310_CALC_ROWS_KEY)
    const list = Array.isArray(raw) ? raw : []
    let linked = 0
    let added = 0
    const unmatched: any[] = []
    for (const imp of list) {
      const assetName = String(imp?.assetName || '').trim()
      if (!assetName) continue
      const impairment = Number(imp?.alreadyProvided ?? imp?.impairmentAmount ?? 0) || 0
      if (impairment <= 0.01) continue
      const idx = rows.value.findIndex((row) => matchAssetName(row.assetName, assetName))
      if (idx >= 0) {
        const row = rows.value[idx]
        row.impairment = impairment
        if (!row.impairmentDate) row.impairmentDate = periodBegin.value
        row.category = row.category || String(imp?.category || '')
        row.remark = appendRemark(row.remark, '已与H3-10联动')
        Object.assign(row, recalcRow(row, branch.value, periodBegin.value, periodEnd.value))
        linked++
      } else {
        unmatched.push(imp)
      }
    }
    if (addMissing && unmatched.length) {
      for (const imp of unmatched) {
        const next = migrateRaw({
          assetName: imp.assetName,
          category: imp.category ?? '',
          impairment: Number(imp.alreadyProvided ?? imp.impairmentAmount ?? 0) || 0,
          impairmentDate: periodBegin.value,
          remark: appendRemark(imp.remark, '来源:H3-10'),
        })
        rows.value.push(recalcRow(next, branch.value, periodBegin.value, periodEnd.value))
        added++
      }
    }
    _persist()
    return {
      linked,
      added,
      message: `已联动 H3-10：更新 ${linked} 行${added ? `，新增 ${added} 行` : ''}`,
    }
  }

  async function exportData(kind: 'template' | 'data'): Promise<void> {
    const XLSX = await import('xlsx')
    const templateHeaders = branch.value === 'withImpair'
      ? ['资产编号', '类别', '资产名称', '原值', '账面累计折旧', '减值准备', '开始使用日期', '使用年限', '残值率', '账面月折旧', '账面本期折旧', '减值日期', '减值时累计折旧', '备注']
      : ['资产编号', '类别', '资产名称', '管理部门', '原值', '账面累计折旧', '开始使用日期', '使用年限', '残值率', '账面月折旧', '账面本期折旧', '备注']
    const dataRows = kind === 'template'
      ? []
      : rows.value.map((row) => (branch.value === 'withImpair'
        ? {
            资产编号: row.assetNo || '',
            类别: row.category || '',
            资产名称: row.assetName || '',
            原值: row.originalCost || 0,
            账面累计折旧: row.bookAccDepEnd || 0,
            减值准备: row.impairment || 0,
            开始使用日期: row.startDate || '',
            使用年限: row.usefulLife || 0,
            残值率: row.salvageRate || 0,
            账面月折旧: row.bookMonthly || 0,
            账面本期折旧: row.bookDepreciation || 0,
            减值日期: row.impairmentDate || '',
            减值时累计折旧: row.accDepAtImpairment || 0,
            备注: row.remark || '',
          }
        : {
            资产编号: row.assetNo || '',
            类别: row.category || '',
            资产名称: row.assetName || '',
            管理部门: row.department || '',
            原值: row.originalCost || 0,
            账面累计折旧: row.bookAccDepEnd || 0,
            开始使用日期: row.startDate || '',
            使用年限: row.usefulLife || 0,
            残值率: row.salvageRate || 0,
            账面月折旧: row.bookMonthly || 0,
            账面本期折旧: row.bookDepreciation || 0,
            备注: row.remark || '',
          }))
    const ws = kind === 'template'
      ? XLSX.utils.aoa_to_sheet([templateHeaders])
      : XLSX.utils.json_to_sheet(dataRows, { header: templateHeaders })
    const wb = XLSX.utils.book_new()
    XLSX.utils.book_append_sheet(wb, ws, branch.value === 'withImpair' ? 'H3-7含减值' : 'H3-7不含减值')
    XLSX.writeFile(wb, `H3-7_${branch.value === 'withImpair' ? '含减值' : '不含减值'}_${kind === 'template' ? '模板' : '数据'}.xlsx`)
  }

  async function importData(file: File, replace = true): Promise<{ imported: number }> {
    const XLSX = await import('xlsx')
    const buffer = await file.arrayBuffer()
    const wb = XLSX.read(buffer, { type: 'array', cellDates: false })
    const sheet = wb.Sheets[wb.SheetNames[0]]
    const rowsRaw = XLSX.utils.sheet_to_json<Record<string, any>>(sheet, { defval: '' })
    const mapped = rowsRaw
      .filter((r) => String(r['资产名称'] || '').trim())
      .map((r) => migrateRaw({
        assetNo: r['资产编号'],
        category: r['类别'],
        assetName: r['资产名称'],
        department: r['管理部门'],
        originalCost: r['原值'],
        bookAccDepEnd: r['账面累计折旧'],
        impairment: r['减值准备'],
        startDate: r['开始使用日期'],
        usefulLife: r['使用年限'],
        salvageRate: normalizeSalvageRate(r['残值率']),
        bookMonthly: r['账面月折旧'],
        bookDepreciation: r['账面本期折旧'],
        impairmentDate: r['减值日期'],
        accDepAtImpairment: r['减值时累计折旧'],
        remark: r['备注'],
      }))
      .map((r) => recalcRow(r, branch.value, periodBegin.value, periodEnd.value))
    rows.value = replace ? mapped : [...rows.value, ...mapped]
    _persist()
    return { imported: mapped.length }
  }

  function _persist(): void {
    const toSave = rows.value.map((r) => ({
      rowId: r.rowId,
      assetNo: r.assetNo,
      category: r.category,
      assetName: r.assetName,
      department: r.department,
      originalCost: r.originalCost,
      bookAccDepEnd: r.bookAccDepEnd,
      impairment: r.impairment,
      startDate: r.startDate,
      usefulLife: r.usefulLife,
      salvageRate: r.salvageRate,
      bookMonthly: r.bookMonthly,
      bookDepreciation: r.bookDepreciation,
      impairmentDate: r.impairmentDate,
      accDepAtImpairment: r.accDepAtImpairment,
      impairmentEvents: r.impairmentEvents,
      disposalDate: r.disposalDate,
      remark: r.remark,
    }))
    allResponses.value.set(ITEM_ID, { item_id: ITEM_ID, conclusion: null, remark: JSON.stringify(toSave) })
    setValue(ITEM_ID, toSave)
    void params.saveImmediate(ITEM_ID, toSave)
  }

  watch([allResponses, branch, () => periodEndRef?.value, () => auditYear?.value], () => loadRows(), { immediate: true })

  return {
    rows,
    periodBegin,
    periodEnd,
    totalOriginalCost,
    totalPeriodDep,
    totalBookDep,
    totalDifference,
    totalAccDepCalc,
    totalAccDepBook,
    totalAccDepDiff,
    h31DepReconcile,
    hasDiscrepancy,
    significantDiffRows,
    impliedCompositeRate,
    depreciationRecalc,
    depRecalcRateOverride,
    depRecalcExplanation,
    setDepRecalcRate,
    setDepRecalcExplanation,
    setPeriodDates,
    setBranch,
    addRow,
    removeRow,
    updateRow,
    recalcAll,
    importFromH32,
    syncFromH310,
    exportData,
    importData,
    loadRows,
  }
}

export default useH3Depreciation
