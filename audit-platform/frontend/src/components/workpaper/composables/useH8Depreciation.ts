/**
 * useH8Depreciation — H8-8 折旧测算 composable
 *
 * 对齐 Excel「折旧测算表（不含/含减值）H8-8」：
 * - 不含减值：测算月折旧 vs 账面月折旧；测算累计 vs 账面累计
 * - 含减值：减值日前后分段计提；与 H8-10 减值准备勾稽
 * - CAS21：折旧期 = min(租赁期月数, 使用寿命月数)
 *
 * 出口：depTotal / depreciationByCategory → H8-9；impairmentAmount → H8-10
 */
import { ref, computed, watch, type Ref } from 'vue'
import { calcDepreciationPeriod } from './useH8CAS21Engine'
import { calcSubtotal } from './useH8FormulaEngine'
import {
  calcStraightLine,
  calcStraightLineTest,
  calcWithImpairmentTest,
} from './useH8DepreciationEngine'
import {
  listLeaseTermsFromH85Raw,
  applyH85TermsToDepRows,
  type H85TermOption,
} from './useH8LeaseTerm'

// ─── Types ───────────────────────────────────────────────────────────────────

/** H8-8 折旧分支（与父入口 el-segmented / 持久化键一致） */
export type H8DepreciationBranch = '不含减值' | '含减值'

/** 用户录入字段（持久化） */
export interface H8DepreciationRowInput {
  rowId: string
  /** 合同号（优先匹配键） */
  contractNo: string
  /** 资产类别（供 H8-9 按类分配） */
  assetCategory: string
  /** 资产名称 / 使用权资产名称 */
  assetName: string
  /** 资产编号 */
  assetNo?: string
  /** 原值 / 入账值 */
  originalCost: number
  /** 账面累计折旧（期末） */
  bookAccDepEnd: number
  /** 减值准备（含减值分支；持久化时同步写 impairmentAmount 供 H8-10） */
  impairment: number
  /** 开始使用日期（租赁期开始日） */
  startDate?: string
  /** 使用年限（年）；引擎内部换算月限 */
  usefulLife: number
  /** 租赁期（月）；与使用寿命取短得折旧期 */
  leaseTermMonths: number
  /** 残值率 0~1；使用权资产无所有权转移预期时通常为 0 */
  salvageRate: number
  /** 账面月折旧额 */
  bookMonthly?: number
  /** 账面本期折旧 */
  bookDepreciation?: number
  /** 减值日期 */
  impairmentDate?: string
  /** 减值时累计折旧（可选；缺省按原直线法推算） */
  accDepAtImpairment?: number
  /** 处置/终止日（提前退租停提） */
  disposalDate?: string
  /**
   * 兼容旧数据：无开始日期时，直接指定本期折旧月数
   * @deprecated 新编制应填 startDate + 期初日/截止日
   */
  monthsInPeriod?: number
  remark?: string
}

/** 测算结果字段（计算列） */
export interface H8DepreciationRow extends H8DepreciationRowInput {
  /** 折旧期月数 = min(租赁期, 使用寿命月数) */
  depPeriodMonths: number
  usefulLifeMonths: number
  fullDepDate: string
  monthsAtEnd: number
  periodMonths: number
  /** 测算月折旧（不含减值=直线；含减值=减值前月折旧，便于对照） */
  calcMonthly: number
  /** 本期测算折旧费用 */
  periodDep: number
  monthlyDiff: number
  calcAccDep: number
  accDepDiff: number
  /** 账面本期 − 测算本期 */
  difference: number
  // 含减值专用
  monthsBeforeImpairment?: number
  monthsAfterImpairment?: number
  preImpairmentMonthly?: number
  postImpairmentMonthly?: number
  /** 兼容旧 UI / H8-10：= impairment */
  impairmentAmount: number
  /** 兼容旧字段别名 */
  rouAmount: number
  currentPeriodDep: number
  accumulatedDep: number
  monthlyDep: number
  monthsInPeriod: number
}

/**
 * @deprecated H8-9 已改为类别×费用矩阵（见 useH8DepreciationAlloc）。
 */
export interface H8DepAllocRow {
  rowId: string
  expenseType: string
  allocRatio: number
  allocAmount: number
}

/** H8-9 默认资产类别（与 Excel 模板红字一致） */
export const H8_DEP_ASSET_CATEGORIES = [
  '房屋及建筑物',
  '机器设备',
  '运输设备',
  '办公设备',
  '其他设备',
] as const

export interface H8DepReconcileResult {
  h81AuditedDepProvision: number
  h88PeriodDepTotal: number
  diff: number
  matched: boolean
}

// ─── Constants ───────────────────────────────────────────────────────────────

export const BRANCH_KEY = 'H8-8-branch'
export const DEP_ROWS_KEY = 'H8-8-dep-rows'
const ALLOC_ROWS_KEY = 'H8-9-alloc-rows'
const DEP_TOTAL_KEY = 'H8-8-depreciation-total'
const DEP_TOTAL_ALIAS = 'H8-8-dep-total'
const PERIOD_END_KEY = 'H8-8-period-end'
const PERIOD_BEGIN_KEY = 'H8-8-period-begin'
const H82_ROWS_KEY = 'H8-2-rows'
const H810_ROWS_KEY = 'H8-10-rows'
const H81_DEP_PROVISION_KEY = 'H8-1-dep-provision'
const H85_RECORDS_KEY = 'H8-5-records'

export interface H88SyncFromH85Result {
  ok: boolean
  reason?: string
  updated: number
  mismatchedBefore: number
  unmatchedContracts: string[]
  details: Array<{ contractNo: string; months: number; rowCount: number }>
}

function defaultPeriodEnd(year?: number): string {
  const y = year && year > 1900 ? year : new Date().getFullYear()
  return `${y}-12-31`
}

function defaultPeriodBegin(periodEnd: string): string {
  const y = periodEnd.slice(0, 4)
  return `${y}-01-01`
}

function normalizeSalvageRate(raw: any): number {
  const n = Number(raw)
  if (!Number.isFinite(n) || n < 0) return 0
  return n > 1 ? n / 100 : n
}

function matchName(a?: string, b?: string): boolean {
  const x = String(a || '').trim()
  const y = String(b || '').trim()
  if (!x || !y) return false
  return x === y || x.includes(y) || y.includes(x)
}

function appendRemark(...parts: Array<string | undefined>): string {
  return parts
    .map((part) => String(part || '').trim())
    .filter(Boolean)
    .filter((part, index, arr) => arr.indexOf(part) === index)
    .join('；')
}

function round2(n: number): number {
  return Math.round((n + Number.EPSILON) * 100) / 100
}

/** 解析有效折旧年限（年）：优先 usefulLife；兼容旧 usefulLifeMonths / leaseTermMonths */
function resolveUsefulLifeYears(raw: any): number {
  if (raw.usefulLife != null && Number(raw.usefulLife) > 0) return Number(raw.usefulLife)
  if (raw.usefulLifeMonths != null && Number(raw.usefulLifeMonths) > 0) {
    return Number(raw.usefulLifeMonths) / 12
  }
  if (raw.leaseTermMonths != null && Number(raw.leaseTermMonths) > 0) {
    return Number(raw.leaseTermMonths) / 12
  }
  if (raw.depPeriodMonths != null && Number(raw.depPeriodMonths) > 0) {
    return Number(raw.depPeriodMonths) / 12
  }
  return 0
}

/** 迁移旧行 / 导入行 → 录入结构 */
export function migrateH8DepRaw(raw: any): H8DepreciationRowInput {
  const usefulLife = resolveUsefulLifeYears(raw)
  const leaseTermMonths = Number(raw.leaseTermMonths) || Math.round(usefulLife * 12) || 0
  return {
    rowId: raw.rowId ?? `dep-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
    contractNo: String(raw.contractNo ?? ''),
    assetCategory: String(raw.assetCategory ?? raw.category ?? ''),
    assetName: String(raw.assetName ?? ''),
    assetNo: String(raw.assetNo ?? ''),
    originalCost: Number(raw.originalCost ?? raw.rouAmount) || 0,
    bookAccDepEnd: Number(raw.bookAccDepEnd ?? raw.accumulatedDep) || 0,
    impairment: Number(raw.impairment ?? raw.impairmentAmount) || 0,
    startDate: raw.startDate ?? '',
    usefulLife,
    leaseTermMonths,
    salvageRate: normalizeSalvageRate(raw.salvageRate),
    bookMonthly: Number(raw.bookMonthly) || 0,
    bookDepreciation: Number(raw.bookDepreciation ?? raw.depCurrentPeriod) || 0,
    impairmentDate: raw.impairmentDate ?? '',
    accDepAtImpairment: raw.accDepAtImpairment != null ? Number(raw.accDepAtImpairment) : undefined,
    disposalDate: raw.disposalDate ?? raw.terminationDate ?? '',
    monthsInPeriod: raw.monthsInPeriod != null ? Number(raw.monthsInPeriod) : undefined,
    remark: raw.remark ?? '',
  }
}

/** CAS21 有效折旧期（月） */
export function resolveH8DepPeriodMonths(input: H8DepreciationRowInput): number {
  const lifeMonths = Math.max(Math.round((Number(input.usefulLife) || 0) * 12), 0)
  const leaseMonths = Math.max(Number(input.leaseTermMonths) || 0, 0)
  if (leaseMonths > 0 && lifeMonths > 0) return calcDepreciationPeriod(leaseMonths, lifeMonths)
  return leaseMonths || lifeMonths
}

function withAliases(
  input: H8DepreciationRowInput,
  calc: {
    depPeriodMonths: number
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
    monthsBeforeImpairment?: number
    monthsAfterImpairment?: number
    preImpairmentMonthly?: number
    postImpairmentMonthly?: number
    accDepAtImpairment?: number
  },
): H8DepreciationRow {
  const impairment = Number(input.impairment) || 0
  return {
    ...input,
    impairment,
    impairmentAmount: impairment,
    rouAmount: input.originalCost,
    currentPeriodDep: calc.periodDep,
    accumulatedDep: input.bookAccDepEnd,
    monthlyDep: calc.calcMonthly,
    monthsInPeriod: calc.periodMonths,
    ...calc,
  }
}

/** 行级重算（纯函数，可单测） */
export function recalcH8DepRow(
  input: H8DepreciationRowInput,
  branch: H8DepreciationBranch,
  periodBegin: string,
  periodEnd: string,
): H8DepreciationRow {
  const depPeriodMonths = resolveH8DepPeriodMonths(input)
  const usefulLifeYears = depPeriodMonths > 0 ? depPeriodMonths / 12 : 0
  const cost = Number(input.originalCost) || 0
  const salvage = normalizeSalvageRate(input.salvageRate)
  const bookMonthly = Number(input.bookMonthly) || 0
  const bookAcc = Number(input.bookAccDepEnd) || 0
  const bookDep = Number(input.bookDepreciation) || 0

  // 无开始日期时的简化路径（兼容旧手工录入）
  if (!input.startDate) {
    const monthly = usefulLifeYears > 0 ? calcStraightLine(cost, salvage, usefulLifeYears) : 0
    const periodMonths = Math.max(Number(input.monthsInPeriod) || 12, 0)
    let periodDep = round2(monthly * periodMonths)
    let calcMonthly = round2(monthly)
    let monthsBefore = periodMonths
    let monthsAfter = 0
    let preMonthly = calcMonthly
    let postMonthly = calcMonthly
    let accAtImp = 0

    if (branch === '含减值' && (Number(input.impairment) || 0) > 0) {
      // 无日期时默认期初已减值：本期全用新率
      const remaining = Math.max(depPeriodMonths - 0, 0)
      const carrying = cost - Math.max(Number(input.impairment) || 0)
      const remainingDepreciable = Math.max(carrying - cost * salvage, 0)
      postMonthly = remaining > 0 ? round2(remainingDepreciable / remaining) : 0
      preMonthly = calcMonthly
      monthsBefore = 0
      monthsAfter = periodMonths
      periodDep = round2(postMonthly * periodMonths)
      calcMonthly = preMonthly
      accAtImp = 0
    }

    const calcAccDep = round2(
      branch === '含减值' && (Number(input.impairment) || 0) > 0
        ? postMonthly * periodMonths
        : monthly * periodMonths,
    )

    return withAliases(input, {
      depPeriodMonths,
      usefulLifeMonths: depPeriodMonths,
      fullDepDate: '',
      monthsAtEnd: periodMonths,
      periodMonths,
      calcMonthly,
      periodDep,
      monthlyDiff: round2(bookMonthly - (branch === '含减值' && (Number(input.impairment) || 0) > 0 ? postMonthly : calcMonthly)),
      calcAccDep,
      accDepDiff: round2(bookAcc - calcAccDep),
      difference: round2(bookDep - periodDep),
      monthsBeforeImpairment: monthsBefore,
      monthsAfterImpairment: monthsAfter,
      preImpairmentMonthly: preMonthly,
      postImpairmentMonthly: postMonthly,
      accDepAtImpairment: accAtImp,
    })
  }

  const baseParams = {
    cost,
    salvageRate: salvage,
    usefulLifeYears,
    startDate: input.startDate || null,
    periodBegin,
    periodEnd,
    disposalDate: input.disposalDate || null,
    bookMonthly,
    bookAccDepEnd: bookAcc,
  }

  if (branch === '含减值' && (Number(input.impairment) || 0) > 0) {
    const r = calcWithImpairmentTest({
      ...baseParams,
      impairmentAmount: Number(input.impairment) || 0,
      impairmentDate: input.impairmentDate || null,
      accDepAtImpairment: input.accDepAtImpairment,
    })
    return withAliases(input, {
      depPeriodMonths,
      usefulLifeMonths: r.usefulLifeMonths,
      fullDepDate: r.fullDepDate,
      monthsAtEnd: r.monthsAtEnd,
      periodMonths: r.periodMonths,
      calcMonthly: r.preImpairmentMonthly,
      periodDep: r.periodDep,
      monthlyDiff: r.monthlyDiff,
      calcAccDep: r.calcAccDep,
      accDepDiff: r.accDepDiff,
      difference: round2(bookDep - r.periodDep),
      monthsBeforeImpairment: r.monthsBeforeImpairmentInPeriod,
      monthsAfterImpairment: r.monthsAfterImpairmentInPeriod,
      preImpairmentMonthly: r.preImpairmentMonthly,
      postImpairmentMonthly: r.postImpairmentMonthly,
      accDepAtImpairment: r.accDepAtImpairment,
    })
  }

  const r = calcStraightLineTest(baseParams)
  return withAliases(input, {
    depPeriodMonths,
    usefulLifeMonths: r.usefulLifeMonths,
    fullDepDate: r.fullDepDate,
    monthsAtEnd: r.monthsAtEnd,
    periodMonths: r.periodMonths,
    calcMonthly: r.calcMonthly,
    periodDep: r.periodDep,
    monthlyDiff: r.monthlyDiff,
    calcAccDep: r.calcAccDep,
    accDepDiff: r.accDepDiff,
    difference: round2(bookDep - r.periodDep),
  })
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH8Depreciation(params: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  onSave?: (itemId: string, value: any) => void
  /** 外部强制分支（父入口 segmented）；缺省读持久化 */
  externalBranch?: Ref<H8DepreciationBranch | string | undefined>
  auditYear?: Ref<number | undefined>
}) {
  const { allResponses, onSave, externalBranch, auditYear } = params

  const branch = ref<H8DepreciationBranch>('不含减值')
  const depRows = ref<H8DepreciationRow[]>([])
  const allocRows = ref<H8DepAllocRow[]>([])
  const periodBegin = ref('')
  const periodEnd = ref('')

  function _getRaw(itemId: string): any {
    const item = allResponses.value.get(itemId)
    if (!item) return null
    return item.remark ?? item.conclusion ?? null
  }

  function _getJson(itemId: string): any {
    const raw = _getRaw(itemId)
    if (raw == null) return null
    if (typeof raw === 'object') return raw
    try { return JSON.parse(raw) } catch { return raw }
  }

  function _getString(itemId: string): string {
    const raw = _getRaw(itemId)
    return raw == null ? '' : String(raw)
  }

  function resolvePeriodDates(): void {
    const storedEnd = _getString(PERIOD_END_KEY)
    const storedBegin = _getString(PERIOD_BEGIN_KEY)
    const year = auditYear?.value
    periodEnd.value = storedEnd || defaultPeriodEnd(year)
    periodBegin.value = storedBegin || defaultPeriodBegin(periodEnd.value)
  }

  function resolveBranch(): H8DepreciationBranch {
    const ext = externalBranch?.value
    if (ext === '含减值' || ext === '不含减值') return ext
    const stored = _getString(BRANCH_KEY)
    return stored === '含减值' ? '含减值' : '不含减值'
  }

  function _normalizeAllocRow(raw: any): H8DepAllocRow {
    return {
      rowId: raw.rowId ?? `alloc-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
      expenseType: raw.expenseType ?? '',
      allocRatio: Number(raw.allocRatio) || 0,
      allocAmount: Number(raw.allocAmount) || 0,
    }
  }

  function load(): void {
    resolvePeriodDates()
    branch.value = resolveBranch()
    const depData = _getJson(DEP_ROWS_KEY)
    depRows.value = Array.isArray(depData)
      ? depData.map((r: any) => recalcH8DepRow(migrateH8DepRaw(r), branch.value, periodBegin.value, periodEnd.value))
      : []
    const allocData = _getJson(ALLOC_ROWS_KEY)
    allocRows.value = Array.isArray(allocData) ? allocData.map(_normalizeAllocRow) : []
  }

  watch(allResponses, () => load(), { immediate: true })
  if (externalBranch) {
    watch(externalBranch, () => {
      const next = resolveBranch()
      if (next !== branch.value) {
        branch.value = next
        depRows.value = depRows.value.map((r) =>
          recalcH8DepRow(r, next, periodBegin.value, periodEnd.value),
        )
        _persistDep()
      }
    })
  }

  // ─── Computed ──────────────────────────────────────────────────────────────

  const depTotal = computed(() => calcSubtotal(depRows.value.map((r) => r.periodDep)))
  const accDepTotal = computed(() => calcSubtotal(depRows.value.map((r) => r.bookAccDepEnd)))
  const calcAccDepTotal = computed(() => calcSubtotal(depRows.value.map((r) => r.calcAccDep)))
  const totalBookDep = computed(() => calcSubtotal(depRows.value.map((r) => r.bookDepreciation || 0)))
  const totalDifference = computed(() => round2(totalBookDep.value - depTotal.value))
  const totalAccDepDiff = computed(() => round2(accDepTotal.value - calcAccDepTotal.value))
  const totalImpairment = computed(() => calcSubtotal(depRows.value.map((r) => r.impairment)))

  const allocTotal = computed(() => calcSubtotal(allocRows.value.map((r) => r.allocAmount)))
  const allocRatioTotal = computed(() => calcSubtotal(allocRows.value.map((r) => r.allocRatio)))

  const depreciationByCategory = computed(() => {
    const map: Record<string, number> = {}
    for (const r of depRows.value) {
      const cat = (r.assetCategory || '其他设备').trim() || '其他设备'
      map[cat] = (map[cat] || 0) + (Number(r.periodDep) || 0)
    }
    return map
  })

  const categorySubtotals = computed(() => {
    const cats = [...H8_DEP_ASSET_CATEGORIES]
    return cats.map((cat) => {
      const rows = depRows.value.filter((r) => (r.assetCategory || '').trim() === cat)
      return {
        category: cat,
        originalCost: calcSubtotal(rows.map((r) => r.originalCost)),
        bookAccDepEnd: calcSubtotal(rows.map((r) => r.bookAccDepEnd)),
        impairment: calcSubtotal(rows.map((r) => r.impairment)),
        periodDep: calcSubtotal(rows.map((r) => r.periodDep)),
        calcAccDep: calcSubtotal(rows.map((r) => r.calcAccDep)),
        monthlyDiff: calcSubtotal(rows.map((r) => r.monthlyDiff)),
        accDepDiff: calcSubtotal(rows.map((r) => r.accDepDiff)),
        rowCount: rows.length,
      }
    }).filter((c) => c.rowCount > 0 || c.periodDep > 0)
  })

  const significantDiffRows = computed(() =>
    depRows.value.filter((r) =>
      Math.abs(r.difference) > 0.01
      || Math.abs(r.monthlyDiff) > 0.01
      || Math.abs(r.accDepDiff) > 0.01,
    ),
  )

  /** H8-5 合同有效租赁期索引 */
  const h85TermByContract = computed(() => {
    const opts = listLeaseTermsFromH85Raw(_getJson(H85_RECORDS_KEY))
    const map = new Map<string, H85TermOption>()
    for (const o of opts) {
      if (o.months > 0) map.set(o.contractNo.trim(), o)
    }
    return map
  })

  /** 折旧行租赁期与 H8-5 不一致的行 */
  const h85LeaseTermMismatches = computed(() => {
    const terms = h85TermByContract.value
    if (!terms.size) return [] as Array<{
      rowId: string
      contractNo: string
      h88Months: number
      h85Months: number
    }>
    const out: Array<{ rowId: string; contractNo: string; h88Months: number; h85Months: number }> = []
    for (const row of depRows.value) {
      const cn = row.contractNo.trim()
      if (!cn) continue
      const term = terms.get(cn)
      if (!term) continue
      if (row.leaseTermMonths !== term.months) {
        out.push({
          rowId: row.rowId,
          contractNo: cn,
          h88Months: row.leaseTermMonths,
          h85Months: term.months,
        })
      }
    }
    return out
  })

  const h81DepReconcile = computed<H8DepReconcileResult>(() => {
    const provision = Number(_getRaw(H81_DEP_PROVISION_KEY)) || 0
    const diff = round2(depTotal.value - provision)
    return {
      h81AuditedDepProvision: provision,
      h88PeriodDepTotal: depTotal.value,
      diff,
      matched: provision === 0 ? Math.abs(depTotal.value) < 0.01 : Math.abs(diff) <= 0.01,
    }
  })

  // ─── Actions ───────────────────────────────────────────────────────────────

  function setBranch(b: H8DepreciationBranch): void {
    branch.value = b
    onSave?.(BRANCH_KEY, b)
    depRows.value = depRows.value.map((r) =>
      recalcH8DepRow(r, b, periodBegin.value, periodEnd.value),
    )
    _persistDep()
  }

  function setPeriodDates(begin: string, end: string): void {
    periodBegin.value = begin
    periodEnd.value = end
    onSave?.(PERIOD_BEGIN_KEY, begin)
    onSave?.(PERIOD_END_KEY, end)
    depRows.value = depRows.value.map((r) =>
      recalcH8DepRow(r, branch.value, begin, end),
    )
    _persistDep()
  }

  function addDepRow(contractNo = ''): void {
    const blank = migrateH8DepRaw({ contractNo: contractNo.trim(), salvageRate: 0 })
    depRows.value.push(recalcH8DepRow(blank, branch.value, periodBegin.value, periodEnd.value))
    _persistDep()
  }

  function deleteDepRow(rowId: string): void {
    const idx = depRows.value.findIndex((r) => r.rowId === rowId)
    if (idx === -1) return
    depRows.value.splice(idx, 1)
    _persistDep()
  }

  function removeRow(index: number): void {
    depRows.value.splice(index, 1)
    _persistDep()
  }

  function updateRow(index: number): void {
    const row = depRows.value[index]
    if (!row) return
    Object.assign(row, recalcH8DepRow(row, branch.value, periodBegin.value, periodEnd.value))
    _persistDep()
  }

  function updateDepCell(rowId: string, field: string, value: any): void {
    const row = depRows.value.find((r) => r.rowId === rowId)
    if (!row) return

    const textFields = [
      'contractNo', 'assetName', 'assetCategory', 'assetNo',
      'startDate', 'impairmentDate', 'disposalDate', 'remark',
    ]
    if (textFields.includes(field)) {
      ;(row as any)[field] = String(value ?? '')
      Object.assign(row, recalcH8DepRow(row, branch.value, periodBegin.value, periodEnd.value))
      _persistDep()
      return
    }

    const numVal = Number(value) || 0
    switch (field) {
      case 'originalCost':
      case 'rouAmount':
        row.originalCost = numVal
        break
      case 'bookAccDepEnd':
      case 'accumulatedDep':
        row.bookAccDepEnd = numVal
        break
      case 'impairment':
      case 'impairmentAmount':
        row.impairment = numVal
        break
      case 'usefulLife':
        row.usefulLife = numVal
        break
      case 'usefulLifeMonths':
        row.usefulLife = numVal / 12
        break
      case 'leaseTermMonths':
        row.leaseTermMonths = numVal
        break
      case 'salvageRate':
        row.salvageRate = normalizeSalvageRate(numVal)
        break
      case 'bookMonthly':
        row.bookMonthly = numVal
        break
      case 'bookDepreciation':
        row.bookDepreciation = numVal
        break
      case 'monthsInPeriod':
        row.monthsInPeriod = numVal
        break
      case 'accDepAtImpairment':
        row.accDepAtImpairment = numVal
        break
      default:
        return
    }
    Object.assign(row, recalcH8DepRow(row, branch.value, periodBegin.value, periodEnd.value))
    _persistDep()
  }

  function recalcAll(): void {
    depRows.value = depRows.value.map((r) =>
      recalcH8DepRow(r, branch.value, periodBegin.value, periodEnd.value),
    )
    _persistDep()
  }

  function importFromH82(replace = true): { imported: number; skipped: number; message: string } {
    const raw = _getJson(H82_ROWS_KEY)
    const list = Array.isArray(raw) ? raw : []
    const h85Terms = h85TermByContract.value
    const mapped = list
      .filter((r: any) => String(r?.assetName || r?.contractNo || '').trim())
      .map((r: any) => {
        const start = r.startDate ?? ''
        const end = r.endDate ?? ''
        const cn = String(r.contractNo ?? '').trim()
        const fromH85 = cn ? h85Terms.get(cn) : undefined
        let leaseMonths = Number(r.leaseTermMonths) || 0
        // 优先 H8-5 已确定有效租赁期
        if (fromH85 && fromH85.months > 0) {
          leaseMonths = fromH85.months
        } else if (!leaseMonths && start && end) {
          const s = new Date(start)
          const e = new Date(end)
          if (!Number.isNaN(s.getTime()) && !Number.isNaN(e.getTime())) {
            leaseMonths = Math.max(
              (e.getFullYear() - s.getFullYear()) * 12 + (e.getMonth() - s.getMonth()),
              0,
            )
          }
        }
        const startDate = start || fromH85?.commencementDate || ''
        return migrateH8DepRaw({
          rowId: `dep-${r.rowId || Math.random().toString(36).slice(2, 8)}`,
          contractNo: r.contractNo ?? '',
          assetName: r.assetName ?? '',
          assetCategory: r.assetCategory ?? r.category ?? '其他设备',
          originalCost: Number(r.initialAmount ?? r.costEndAud ?? r.rouAmount ?? r.originalCost) || 0,
          bookAccDepEnd: Number(r.accDepEnd ?? r.depEndAud ?? r.bookAccDepEnd) || 0,
          bookDepreciation: Number(r.depCurrentPeriod ?? r.depProvUnadj ?? r.bookDepreciation) || 0,
          startDate,
          leaseTermMonths: leaseMonths,
          usefulLife: leaseMonths > 0 ? leaseMonths / 12 : Number(r.usefulLife) || 0,
          salvageRate: 0,
          disposalDate: r.terminationDate ?? '',
          remark: appendRemark(
            r.remark,
            '来源:H8-2',
            fromH85 ? '租赁期取自H8-5' : undefined,
          ),
        })
      })
    const next = mapped.map((r) => recalcH8DepRow(r, branch.value, periodBegin.value, periodEnd.value))
    depRows.value = replace ? next : [...depRows.value, ...next]
    _persistDep()
    return {
      imported: mapped.length,
      skipped: 0,
      message: `已从 H8-2 带入 ${mapped.length} 行`
        + (h85Terms.size ? '（已匹配 H8-5 租赁期）' : ''),
    }
  }

  /** 按合同号从 H8-5 同步租赁期到现有折旧行，并重算 */
  function syncLeaseTermFromH85(contractNo?: string): H88SyncFromH85Result {
    const terms = h85TermByContract.value
    if (!terms.size) {
      return {
        ok: false,
        reason: 'H8-5 尚无有效租赁期记录',
        updated: 0,
        mismatchedBefore: h85LeaseTermMismatches.value.length,
        unmatchedContracts: [],
        details: [],
      }
    }
    if (!depRows.value.length) {
      return {
        ok: false,
        reason: 'H8-8 尚无折旧行，请先从 H8-2 带入',
        updated: 0,
        mismatchedBefore: 0,
        unmatchedContracts: [...terms.keys()],
        details: [],
      }
    }

    const mismatchedBefore = h85LeaseTermMismatches.value.length
    const applied = applyH85TermsToDepRows(
      depRows.value.map((r) => ({ ...r })),
      terms,
      { onlyContractNo: contractNo },
    )

    if (applied.updated === 0) {
      return {
        ok: applied.unmatchedContracts.length === 0,
        reason: applied.unmatchedContracts.length
          ? `无匹配合同：${applied.unmatchedContracts.join('、')}`
          : '租赁期已与 H8-5 一致',
        updated: 0,
        mismatchedBefore,
        unmatchedContracts: applied.unmatchedContracts,
        details: [],
      }
    }

    depRows.value = applied.rows.map((r) =>
      recalcH8DepRow(r as H8DepreciationRowInput, branch.value, periodBegin.value, periodEnd.value),
    )
    _persistDep()

    return {
      ok: true,
      updated: applied.updated,
      mismatchedBefore,
      unmatchedContracts: applied.unmatchedContracts,
      details: applied.details,
    }
  }

  function syncFromH810(addMissing = true): { linked: number; added: number; message: string } {
    const raw = _getJson(H810_ROWS_KEY)
    const list = Array.isArray(raw) ? raw : []
    let linked = 0
    let added = 0
    const unmatched: any[] = []

    for (const imp of list) {
      const assetName = String(imp?.assetName || '').trim()
      const contractNo = String(imp?.contractNo || '').trim()
      // ⑦已计提优先；否则用⑥应计提
      const impairment = Number(imp?.alreadyProvided ?? imp?.impairmentAmount ?? 0) || 0
      if (impairment <= 0.01) continue

      const idx = depRows.value.findIndex((row) =>
        (contractNo && row.contractNo.trim() === contractNo)
        || matchName(row.assetName, assetName),
      )
      if (idx >= 0) {
        const row = depRows.value[idx]
        row.impairment = impairment
        if (!row.impairmentDate) row.impairmentDate = periodBegin.value
        row.remark = appendRemark(row.remark, '已与H8-10联动')
        Object.assign(row, recalcH8DepRow(row, branch.value, periodBegin.value, periodEnd.value))
        linked++
      } else {
        unmatched.push(imp)
      }
    }

    if (addMissing && unmatched.length && branch.value === '含减值') {
      for (const imp of unmatched) {
        const next = migrateH8DepRaw({
          assetName: imp.assetName,
          contractNo: imp.contractNo ?? '',
          impairment: Number(imp.alreadyProvided ?? imp.impairmentAmount ?? 0) || 0,
          impairmentDate: periodBegin.value,
          originalCost: Number(imp.bookValue) || 0,
          salvageRate: 0,
          remark: appendRemark(imp.remark, '来源:H8-10'),
        })
        depRows.value.push(recalcH8DepRow(next, branch.value, periodBegin.value, periodEnd.value))
        added++
      }
    }

    if (linked + added > 0 && branch.value !== '含减值') {
      setBranch('含减值')
    } else {
      _persistDep()
    }

    return {
      linked,
      added,
      message: `已联动 H8-10：更新 ${linked} 行${added ? `，新增 ${added} 行` : ''}`,
    }
  }

  async function exportData(kind: 'template' | 'data'): Promise<void> {
    const XLSX = await import('xlsx')
    const withImpair = branch.value === '含减值'
    const headers = withImpair
      ? ['合同号', '类别', '资产名称', '编号', '原值', '账面累计折旧', '减值准备', '开始使用日期', '使用年限', '租赁期月数', '残值率', '账面月折旧', '账面本期折旧', '减值日期', '备注']
      : ['合同号', '类别', '资产名称', '编号', '原值', '账面累计折旧', '开始使用日期', '使用年限', '租赁期月数', '残值率', '账面月折旧', '账面本期折旧', '备注']
    const dataRows = kind === 'template'
      ? []
      : depRows.value.map((row) => (withImpair
        ? {
            合同号: row.contractNo || '',
            类别: row.assetCategory || '',
            资产名称: row.assetName || '',
            编号: row.assetNo || '',
            原值: row.originalCost || 0,
            账面累计折旧: row.bookAccDepEnd || 0,
            减值准备: row.impairment || 0,
            开始使用日期: row.startDate || '',
            使用年限: row.usefulLife || 0,
            租赁期月数: row.leaseTermMonths || 0,
            残值率: row.salvageRate || 0,
            账面月折旧: row.bookMonthly || 0,
            账面本期折旧: row.bookDepreciation || 0,
            减值日期: row.impairmentDate || '',
            备注: row.remark || '',
          }
        : {
            合同号: row.contractNo || '',
            类别: row.assetCategory || '',
            资产名称: row.assetName || '',
            编号: row.assetNo || '',
            原值: row.originalCost || 0,
            账面累计折旧: row.bookAccDepEnd || 0,
            开始使用日期: row.startDate || '',
            使用年限: row.usefulLife || 0,
            租赁期月数: row.leaseTermMonths || 0,
            残值率: row.salvageRate || 0,
            账面月折旧: row.bookMonthly || 0,
            账面本期折旧: row.bookDepreciation || 0,
            备注: row.remark || '',
          }))
    const ws = kind === 'template'
      ? XLSX.utils.aoa_to_sheet([headers])
      : XLSX.utils.json_to_sheet(dataRows, { header: headers })
    const wb = XLSX.utils.book_new()
    XLSX.utils.book_append_sheet(wb, ws, withImpair ? 'H8-8含减值' : 'H8-8不含减值')
    XLSX.writeFile(wb, `H8-8_${withImpair ? '含减值' : '不含减值'}_${kind === 'template' ? '模板' : '数据'}.xlsx`)
  }

  async function importData(file: File, replace = true): Promise<{ imported: number }> {
    const XLSX = await import('xlsx')
    const buffer = await file.arrayBuffer()
    const wb = XLSX.read(buffer, { type: 'array', cellDates: false })
    const sheet = wb.Sheets[wb.SheetNames[0]]
    const rowsRaw = XLSX.utils.sheet_to_json<Record<string, any>>(sheet, { defval: '' })
    const mapped = rowsRaw
      .filter((r) => String(r['资产名称'] || r['合同号'] || '').trim())
      .map((r) => migrateH8DepRaw({
        contractNo: r['合同号'],
        assetCategory: r['类别'],
        assetName: r['资产名称'],
        assetNo: r['编号'],
        originalCost: r['原值'],
        bookAccDepEnd: r['账面累计折旧'],
        impairment: r['减值准备'],
        startDate: r['开始使用日期'],
        usefulLife: r['使用年限'],
        leaseTermMonths: r['租赁期月数'],
        salvageRate: normalizeSalvageRate(r['残值率']),
        bookMonthly: r['账面月折旧'],
        bookDepreciation: r['账面本期折旧'],
        impairmentDate: r['减值日期'],
        remark: r['备注'],
      }))
      .map((r) => recalcH8DepRow(r, branch.value, periodBegin.value, periodEnd.value))
    depRows.value = replace ? mapped : [...depRows.value, ...mapped]
    _persistDep()
    return { imported: mapped.length }
  }

  function addAllocRow(expenseType: string): void {
    if (!expenseType?.trim()) return
    allocRows.value.push(_normalizeAllocRow({ expenseType: expenseType.trim() }))
    _persistAlloc()
  }

  function deleteAllocRow(rowId: string): void {
    const idx = allocRows.value.findIndex((r) => r.rowId === rowId)
    if (idx === -1) return
    allocRows.value.splice(idx, 1)
    _persistAlloc()
  }

  function updateAllocCell(rowId: string, field: string, value: any): void {
    const row = allocRows.value.find((r) => r.rowId === rowId)
    if (!row) return
    if (field === 'expenseType') {
      row.expenseType = String(value ?? '')
    } else if (field === 'allocRatio') {
      row.allocRatio = Number(value) || 0
      row.allocAmount = depTotal.value * row.allocRatio / 100
    } else if (field === 'allocAmount') {
      row.allocAmount = Number(value) || 0
    }
    _persistAlloc()
  }

  function save(): void {
    _persistDep()
    _persistAlloc()
  }

  function _persistDep(): void {
    if (!onSave) return
    onSave(DEP_ROWS_KEY, depRows.value.map((r) => ({
      rowId: r.rowId,
      contractNo: r.contractNo,
      assetCategory: r.assetCategory,
      assetName: r.assetName,
      assetNo: r.assetNo,
      originalCost: r.originalCost,
      rouAmount: r.originalCost,
      bookAccDepEnd: r.bookAccDepEnd,
      accumulatedDep: r.bookAccDepEnd,
      impairment: r.impairment,
      impairmentAmount: r.impairment,
      startDate: r.startDate,
      usefulLife: r.usefulLife,
      leaseTermMonths: r.leaseTermMonths,
      salvageRate: r.salvageRate,
      bookMonthly: r.bookMonthly,
      bookDepreciation: r.bookDepreciation,
      impairmentDate: r.impairmentDate,
      accDepAtImpairment: r.accDepAtImpairment,
      disposalDate: r.disposalDate,
      monthsInPeriod: r.monthsInPeriod,
      remark: r.remark,
    })))
    onSave(DEP_TOTAL_KEY, depTotal.value)
    onSave(DEP_TOTAL_ALIAS, depTotal.value)
    onSave(BRANCH_KEY, branch.value)
  }

  function _persistAlloc(): void {
    if (!onSave) return
    onSave(ALLOC_ROWS_KEY, allocRows.value.map((r) => ({
      rowId: r.rowId,
      expenseType: r.expenseType,
      allocRatio: r.allocRatio,
      allocAmount: r.allocAmount,
    })))
  }

  return {
    branch,
    depRows,
    /** 别名：与 H3 对齐 */
    rows: depRows,
    allocRows,
    periodBegin,
    periodEnd,
    depTotal,
    accDepTotal,
    calcAccDepTotal,
    totalBookDep,
    totalDifference,
    totalAccDepDiff,
    totalImpairment,
    allocTotal,
    allocRatioTotal,
    depreciationByCategory,
    categorySubtotals,
    significantDiffRows,
    h85LeaseTermMismatches,
    h81DepReconcile,
    setBranch,
    setPeriodDates,
    addDepRow,
    addRow: addDepRow,
    deleteDepRow,
    removeRow,
    updateRow,
    updateDepCell,
    recalcAll,
    importFromH82,
    syncLeaseTermFromH85,
    syncFromH810,
    exportData,
    importData,
    addAllocRow,
    deleteAllocRow,
    updateAllocCell,
    save,
    load,
  }
}

export default useH8Depreciation
