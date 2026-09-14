/**
 * useH1Depreciation — H1-12 折旧测算 composable
 *
 * 三分支(A不含减值 / B含减值 / C多次减值)共用行数据，按减值情况联动推荐分支。
 * 支持：从 H1-2 带入、企业原始台账一键导入+测算、按 CAS 日期推算期数。
 *
 * Spec: .kiro/specs/h1-fixed-assets/
 * Requirements: 11.1-11.13
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'

import { readSheetAoa } from '@/composables/useExcelIO'
import type { ChecklistItem } from './useH1FormData'
import {
  calcStraightLine,
  calcDoubleDeclining,
  calcSumOfYears,
  calcStraightLineTest,
  calcWithImpairmentTest,
  calcMultiImpairmentTest,
  recommendDepreciationBranch,
  calcMonthsDepreciated,
  type MultiImpairmentEventInput,
} from './useH1DepreciationEngine'
import { calcSubtotal } from './useH1FormulaEngine'
import {
  attributeDepreciationDiff,
  checkBeginAccumulatedDep,
  checkTaxMinLife,
  classifyDiffAmount,
  defaultMateriality,
  selectDepreciationSample,
  calcWithEstimateChangeTest,
  parseH18DisposalRows,
  parseH14ImpairmentRows,
  loadColumnMapping,
  saveColumnMapping,
  buildMappingFromFieldIndex,
  applyRememberedMapping,
  buildEngineWatermark,
  formatWatermarkLine,
  type MaterialityConfig,
  type DiffAttribution,
  type DiffSeverity,
  type BeginAccCheck,
  type SamplingResult,
  type EngineWatermark,
  type ColumnMapping,
  H1_12_ENGINE_VERSION,
} from './useH1DepreciationAdvanced'

// ─── Types ───────────────────────────────────────────────────────────────────

export type DepreciationBranch = 'A' | 'B' | 'C'  // A=不含减值直线 B=含减值 C=多次减值

/** 减值事件（C分支用） */
export interface ImpairmentEvent {
  eventDate: string
  amount: number
  remainingLife: number
  newMonthlyDep: number
  elapsedMonths?: number
}

/** 折旧测算行（对齐 Excel H1-12 三表核心列） */
export interface DepreciationRow {
  rowId: string
  category: string
  assetNo: string
  assetName: string
  department: string
  originalCost: number
  salvageRate: number
  usefulLife: number
  startDate: string
  disposalDate: string
  depMethod: string
  /** 账面月折旧 */
  bookMonthly: number
  /** 账面本期折旧 */
  bookDepreciation: number
  /** 账面累计折旧期末 */
  bookAccDepEnd: number
  /** 累计折旧期初（账面） */
  accDepBegin: number
  /** 减值期初/期末/本期计提 */
  impairmentBegin: number
  impairmentEnd: number
  impairmentProvision: number
  impairmentDate: string
  // 测算结果
  usefulLifeMonths: number
  calcMonthly: number
  fullDepDate: string
  monthsAtBegin: number
  monthsAtEnd: number
  periodMonths: number
  periodTotal: number
  calcAccDep: number
  monthlyDiff: number
  accDepDiff: number
  difference: number
  /** 兼容旧字段 */
  monthlyDep: number
  monthly: number[]
  accDepEnd: number
  elapsedMonths: number
  // B
  impairmentAmount: number
  postImpairmentNetValue: number
  postImpairmentMonthlyDep: number
  monthsBeforeImpairment: number
  monthsAfterImpairment: number
  accDepAtImpairment: number
  // C
  impairmentEvents: ImpairmentEvent[]
  recommendedBranch: DepreciationBranch
  remark: string
  // ── 高级：处置 / 估计变更 / 归因 / 税龄 / 抽样 ──
  /** 是否纳入本期测算样本 */
  inSample: boolean
  /** 估计变更日 */
  estimateChangeDate: string
  usefulLifeBefore: number
  salvageRateBefore: number
  usefulLifeAfter: number
  salvageRateAfter: number
  beginAccCheck: BeginAccCheck | null
  diffAttribution: DiffAttribution | null
  diffSeverity: DiffSeverity
  taxLifeWarning: string
  disposalAccDepFromH18: number
  linkedFromH14: boolean
  linkedFromH18: boolean
  /** 来自 H1-7 增加检查（折旧起算/暂估转固） */
  linkedFromH17: boolean
}

export interface DepreciationSummary {
  calculatedTotal: number
  bookTotal: number
  totalDifference: number
  diffRate: number
  calcAccDepTotal: number
  bookAccDepTotal: number
  accDepDiffTotal: number
}

export interface CategorySubtotal {
  category: string
  periodTotal: number
  bookDepreciation: number
  difference: number
  originalCost: number
  calcAccDep: number
  bookAccDepEnd: number
}

export interface BranchRecommendation {
  recommended: DepreciationBranch
  reason: string
  counts: { A: number; B: number; C: number }
}

export interface ImportPreview {
  rowCount: number
  branch: DepreciationBranch
  recommendation: BranchRecommendation
  sampleNames: string[]
  warnings: string[]
}

export interface AdvancedDashboard {
  beginAccFailCount: number
  materialDiffCount: number
  reviewDiffCount: number
  taxWarnCount: number
  nonStraightCount: number
  disposalLinkedCount: number
  impairLinkedCount: number
  additionLinkedCount: number
  sampleMode: boolean
  sampleCoverage: number
  watermarkLine: string
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_PREFIX = 'H1-12'

const CATEGORY_ORDER = ['房屋及建筑物', '机器设备', '运输设备', '办公设备', '其他设备', '其他']

/** 企业原始台账 → 标准字段的表头别名（大小写不敏感，去空格） */
const HEADER_ALIASES: Record<string, string[]> = {
  category: ['固定资产类别', '资产类别', '类别', '分类', 'category', 'assetcategory'],
  assetNo: ['固定资产编号', '资产编号', '资产编码', '编号', 'assetno', 'assetcode', 'code'],
  assetName: ['固定资产名称', '资产名称', '名称', 'assetname', 'name'],
  department: ['管理部门', '使用部门', '部门', 'department'],
  originalCost: ['原值', '原值(期末)', '原值期末', '账面原值', '期末原值', 'cost', 'originalcost'],
  accDepBegin: ['期初累计折旧', '累计折旧期初', 'accdepbegin'],
  bookAccDepEnd: ['累计折旧', '累计折旧(期末)', '累计折旧期末', '期末累计折旧', 'accdepend'],
  bookDepreciation: ['本期折旧', '本期计提折旧', '本年折旧', '折旧额', 'bookdepreciation'],
  bookMonthly: ['账面月折旧额', '月折旧额', '月折旧', 'bookmonthly'],
  startDate: ['开始使用日期', '启用日期', '入账日期', '购置日期', '转固日期', 'startdate', 'acquisitiondate'],
  usefulLife: ['使用年限', '折旧年限', '年限', 'usefullife', 'life'],
  salvageRate: ['残值率', '预计残值率', 'salvagerate'],
  impairmentBegin: ['期初减值准备', '减值准备期初', 'impairmentbegin'],
  impairmentEnd: ['减值准备', '减值准备(期末)', '减值准备期末', '期末减值准备', 'impairment'],
  impairmentProvision: ['本期计提减值', '本期减值', 'impairmentprovision'],
  impairmentDate: ['计提减值准备日期', '减值日期', '减值时点', 'impairmentdate'],
  disposalDate: ['处置日期', '减少日期', 'disposaldate'],
  depMethod: ['折旧方法', 'depmethod', 'method'],
  estimateChangeDate: ['估计变更日', '年限变更日', '残值变更日', 'estimatechangedate'],
  usefulLifeBefore: ['变更前年限', '原使用年限', 'usefullifebefore'],
  usefulLifeAfter: ['变更后年限', '新使用年限', 'usefullifeafter'],
  salvageRateBefore: ['变更前残值率', 'salvageratebefore'],
  salvageRateAfter: ['变更后残值率', 'salvagerateafter'],
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function _uid(): string {
  return `dep-${Math.random().toString(36).slice(2, 10)}`
}

function _num(v: unknown): number {
  if (v == null || v === '') return 0
  if (typeof v === 'number') return Number.isFinite(v) ? v : 0
  const s = String(v).replace(/,/g, '').replace(/%/g, '').trim()
  const n = Number(s)
  return Number.isFinite(n) ? n : 0
}

function _normHeader(h: unknown): string {
  return String(h ?? '').replace(/\s+/g, '').replace(/（/g, '(').replace(/）/g, ')').toLowerCase()
}

function _mapHeader(header: string): string | null {
  const n = _normHeader(header)
  for (const [field, aliases] of Object.entries(HEADER_ALIASES)) {
    if (aliases.some((a) => _normHeader(a) === n)) return field
  }
  return null
}

function _periodBeginFromEnd(periodEnd: string): string {
  const m = periodEnd.match(/^(\d{4})/)
  if (!m) return ''
  return `${m[1]}-01-01`
}

function _emptyRow(): DepreciationRow {
  return {
    rowId: _uid(),
    category: '',
    assetNo: '',
    assetName: '',
    department: '',
    originalCost: 0,
    salvageRate: 0,
    usefulLife: 0,
    startDate: '',
    disposalDate: '',
    depMethod: '直线法',
    bookMonthly: 0,
    bookDepreciation: 0,
    bookAccDepEnd: 0,
    accDepBegin: 0,
    impairmentBegin: 0,
    impairmentEnd: 0,
    impairmentProvision: 0,
    impairmentDate: '',
    usefulLifeMonths: 0,
    calcMonthly: 0,
    fullDepDate: '',
    monthsAtBegin: 0,
    monthsAtEnd: 0,
    periodMonths: 0,
    periodTotal: 0,
    calcAccDep: 0,
    monthlyDiff: 0,
    accDepDiff: 0,
    difference: 0,
    monthlyDep: 0,
    monthly: new Array(12).fill(0),
    accDepEnd: 0,
    elapsedMonths: 0,
    impairmentAmount: 0,
    postImpairmentNetValue: 0,
    postImpairmentMonthlyDep: 0,
    monthsBeforeImpairment: 0,
    monthsAfterImpairment: 0,
    accDepAtImpairment: 0,
    impairmentEvents: [],
    recommendedBranch: 'A',
    remark: '',
    inSample: true,
    estimateChangeDate: '',
    usefulLifeBefore: 0,
    salvageRateBefore: 0,
    usefulLifeAfter: 0,
    salvageRateAfter: 0,
    beginAccCheck: null,
    diffAttribution: null,
    diffSeverity: 'ok',
    taxLifeWarning: '',
    disposalAccDepFromH18: 0,
    linkedFromH14: false,
    linkedFromH18: false,
    linkedFromH17: false,
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH1Depreciation(
  wpId: Ref<string>,
  projectId: Ref<string>,
  allResponses: Ref<Map<string, ChecklistItem>>,
  options?: {
    periodEnd?: Ref<string> | ComputedRef<string>
    crossSheetDetailRows?: Ref<any[]>
    onSave?: (itemId: string, value: any) => void
    onPublishEvent?: (event: string, payload: any) => void
    onBranchChange?: (branch: DepreciationBranch) => void
  },
) {
  const branch = ref<DepreciationBranch>('A')
  const rows = ref<DepreciationRow[]>([])
  const auditNote = ref('')
  const auditConclusion = ref('')
  const importing = ref(false)
  const lastImportWarnings = ref<string[]>([])
  const sampleMode = ref(false)
  const lastSampling = ref<SamplingResult<DepreciationRow> | null>(null)
  const materiality = ref<MaterialityConfig>(defaultMateriality())
  const engineMeta = ref<EngineWatermark | null>(null)

  const periodEnd = computed(() => options?.periodEnd?.value || '')
  const periodBegin = computed(() => {
    const pe = periodEnd.value
    return pe ? _periodBeginFromEnd(pe) : ''
  })

  // ─── Load ──────────────────────────────────────────────────────────────────

  function _loadData(): void {
    const branchItem = allResponses.value.get(`${ITEM_PREFIX}-branch`)
    if (branchItem?.remark) {
      const b = String(branchItem.remark) as DepreciationBranch
      if (b === 'A' || b === 'B' || b === 'C') branch.value = b
    }

    rows.value = _loadBranchRows(branch.value)

    auditNote.value = _getString(`${ITEM_PREFIX}-audit-note`)
    auditConclusion.value = _getString(`${ITEM_PREFIX}-audit-conclusion`)

    const matItem = allResponses.value.get(`${ITEM_PREFIX}-materiality`)
    if (matItem?.remark) {
      try {
        const m = typeof matItem.remark === 'string' ? JSON.parse(matItem.remark) : matItem.remark
        if (m && typeof m === 'object') materiality.value = { ...defaultMateriality(), ...m }
      } catch { /* keep default */ }
    }
    const metaItem = allResponses.value.get(`${ITEM_PREFIX}-engine-meta`)
    if (metaItem?.remark) {
      try {
        engineMeta.value = typeof metaItem.remark === 'string' ? JSON.parse(metaItem.remark) : metaItem.remark
      } catch { /* ignore */ }
    }
  }

  /** 分支隔离：优先 H1-12-{A|B|C}-rows；A 分支兼容旧键 H1-12-rows */
  function _loadBranchRows(b: DepreciationBranch): DepreciationRow[] {
    const branchKey = `${ITEM_PREFIX}-${b}-rows`
    const branchItem = allResponses.value.get(branchKey)
    if (branchItem?.remark) {
      try {
        const parsed = JSON.parse(branchItem.remark)
        if (Array.isArray(parsed)) return parsed.map(_normalizeRow)
      } catch { /* fall through */ }
    }
    // 迁移：仅当前分支为 A 且无分支键时，读旧共享键
    if (b === 'A') {
      const legacy = allResponses.value.get(`${ITEM_PREFIX}-rows`)
      if (legacy?.remark) {
        try {
          const parsed = JSON.parse(legacy.remark)
          if (Array.isArray(parsed)) return parsed.map(_normalizeRow)
        } catch { /* ignore */ }
      }
    }
    return []
  }

  function _getString(itemId: string): string {
    const item = allResponses.value.get(itemId)
    return (item?.remark ?? item?.conclusion ?? '') as string
  }

  function _normalizeRow(raw: any): DepreciationRow {
    const row = _emptyRow()
    Object.assign(row, {
      rowId: raw.rowId ?? row.rowId,
      category: raw.category ?? '',
      assetNo: raw.assetNo ?? raw.assetCode ?? '',
      assetName: raw.assetName ?? raw.name ?? '',
      department: raw.department ?? '',
      originalCost: _num(raw.originalCost),
      salvageRate: _normalizeSalvage(_num(raw.salvageRate)),
      usefulLife: _num(raw.usefulLife),
      startDate: raw.startDate ?? raw.acquisitionDate ?? '',
      disposalDate: raw.disposalDate ?? '',
      depMethod: raw.depMethod ?? '直线法',
      bookMonthly: _num(raw.bookMonthly ?? raw.monthlyDepBook),
      bookDepreciation: _num(raw.bookDepreciation ?? raw.accDepProvision),
      bookAccDepEnd: _num(raw.bookAccDepEnd ?? raw.accDepEnd),
      accDepBegin: _num(raw.accDepBegin),
      impairmentBegin: _num(raw.impairmentBegin),
      impairmentEnd: _num(raw.impairmentEnd ?? raw.impairmentAmount),
      impairmentProvision: _num(raw.impairmentProvision),
      impairmentDate: raw.impairmentDate ?? '',
      elapsedMonths: _num(raw.elapsedMonths),
      impairmentAmount: _num(raw.impairmentAmount ?? raw.impairmentEnd),
      impairmentEvents: Array.isArray(raw.impairmentEvents) ? raw.impairmentEvents : [],
      remark: raw.remark ?? '',
      inSample: raw.inSample !== false,
      estimateChangeDate: raw.estimateChangeDate ?? '',
      usefulLifeBefore: _num(raw.usefulLifeBefore),
      salvageRateBefore: _normalizeSalvage(_num(raw.salvageRateBefore)),
      usefulLifeAfter: _num(raw.usefulLifeAfter),
      salvageRateAfter: _normalizeSalvage(_num(raw.salvageRateAfter)),
      disposalAccDepFromH18: _num(raw.disposalAccDepFromH18),
      linkedFromH14: !!raw.linkedFromH14,
      linkedFromH18: !!raw.linkedFromH18,
      linkedFromH17: !!raw.linkedFromH17,
    })
    // 残值率若以百分数存储（如 5），转为 0.05
    if (row.salvageRate > 1) row.salvageRate = row.salvageRate / 100
    row.recommendedBranch = recommendDepreciationBranch({
      impairmentBegin: row.impairmentBegin,
      impairmentEnd: row.impairmentEnd || row.impairmentAmount,
      impairmentProvision: row.impairmentProvision,
      impairmentEventCount: row.impairmentEvents?.length ?? 0,
    })
    return row
  }

  function _normalizeSalvage(v: number): number {
    if (v > 1) return v / 100
    return v
  }

  // ─── 单行测算（按当前分支） ────────────────────────────────────────────────

  function recalcRow(row: DepreciationRow): void {
    const pe = periodEnd.value || undefined
    const pb = periodBegin.value || undefined
    const life = row.usefulLife
    const cost = row.originalCost
    const rate = row.salvageRate > 1 ? row.salvageRate / 100 : row.salvageRate

    row.recommendedBranch = recommendDepreciationBranch({
      impairmentBegin: row.impairmentBegin,
      impairmentEnd: row.impairmentEnd || row.impairmentAmount,
      impairmentProvision: row.impairmentProvision,
      impairmentEventCount: row.impairmentEvents?.length ?? 0,
    })

    // 非直线法：保留原方法月额，仍输出期数对比
    if (row.depMethod && row.depMethod !== '直线法' && branch.value === 'A') {
      const totalMonths = life * 12
      let monthlyAmt = 0
      if (row.depMethod === '双倍余额递减法') {
        monthlyAmt = calcDoubleDeclining(cost - row.accDepBegin, life, row.elapsedMonths || row.monthsAtEnd, totalMonths)
      } else if (row.depMethod === '年数总和法') {
        const remainYears = Math.max(life - Math.floor((row.elapsedMonths || 0) / 12), 1)
        monthlyAmt = calcSumOfYears(cost, rate, life, remainYears)
      } else {
        monthlyAmt = calcStraightLine(cost, rate, life)
      }
      const monthsEnd = row.startDate && pe
        ? calcMonthsDepreciated(row.startDate, pe, totalMonths)
        : (row.elapsedMonths || 12)
      const monthsBegin = Math.max(monthsEnd - 12, 0)
      const periodM = Math.max(monthsEnd - monthsBegin, 0)
      row.usefulLifeMonths = totalMonths
      row.calcMonthly = round2(monthlyAmt)
      row.monthlyDep = row.calcMonthly
      row.monthsAtBegin = monthsBegin
      row.monthsAtEnd = monthsEnd
      row.elapsedMonths = monthsEnd
      row.periodMonths = periodM
      row.periodTotal = round2(monthlyAmt * periodM)
      row.calcAccDep = round2(monthlyAmt * monthsEnd)
      row.accDepEnd = row.accDepBegin + row.periodTotal
      row.monthly = _distributeMonthly(row.periodTotal, periodM)
      row.monthlyDiff = round2(row.bookMonthly - row.calcMonthly)
      row.accDepDiff = round2(row.bookAccDepEnd - row.calcAccDep)
      row.difference = round2(row.bookDepreciation - row.periodTotal)
      _applyAdvancedDiagnostics(row)
      return
    }

    if (branch.value === 'C' && (row.impairmentEvents?.length ?? 0) >= 1) {
      const events: MultiImpairmentEventInput[] = row.impairmentEvents.map((e) => ({
        eventDate: e.eventDate,
        amount: e.amount,
        elapsedMonths: e.elapsedMonths,
      }))
      // 若仅有期末减值无事件明细，合成一次事件
      if (events.length === 0 && (row.impairmentEnd || row.impairmentAmount) > 0) {
        events.push({
          eventDate: row.impairmentDate || pb,
          amount: row.impairmentEnd || row.impairmentAmount,
        })
      }
      const r = calcMultiImpairmentTest({
        cost,
        salvageRate: rate,
        usefulLifeYears: life,
        startDate: row.startDate || null,
        periodBegin: pb,
        periodEnd: pe,
        disposalDate: row.disposalDate || null,
        events,
        bookMonthly: row.bookMonthly,
        bookAccDepEnd: row.bookAccDepEnd,
      })
      _applyTestResult(row, r)
      row.postImpairmentMonthlyDep = r.postImpairmentMonthlyDep
      row.monthsBeforeImpairment = r.monthsBeforeImpairmentInPeriod
      row.monthsAfterImpairment = r.monthsAfterImpairmentInPeriod
      row.accDepAtImpairment = r.accDepAtImpairment
      row.impairmentAmount = events.reduce((s, e) => s + e.amount, 0)
      // 回写事件新月折旧
      row.impairmentEvents = events.map((e, idx) => {
        const seg = r.segments.find((s) => s.fromElapsed === (e.elapsedMonths ?? -1))
          ?? r.segments[Math.min(idx + 1, r.segments.length - 1)]
        const remainingLife = Math.max((life * 12 - (e.elapsedMonths ?? 0)) / 12, 0)
        return {
          eventDate: e.eventDate || '',
          amount: e.amount,
          remainingLife: round2(remainingLife),
          newMonthlyDep: seg?.monthly ?? r.postImpairmentMonthlyDep,
          elapsedMonths: e.elapsedMonths,
        }
      })
      _applyAdvancedDiagnostics(row)
      return
    }

    if (branch.value === 'B' || (branch.value === 'C' && (row.impairmentEnd || row.impairmentAmount) > 0)) {
      const impairAmt = row.impairmentAmount || row.impairmentEnd || 0
      const r = calcWithImpairmentTest({
        cost,
        salvageRate: rate,
        usefulLifeYears: life,
        startDate: row.startDate || null,
        periodBegin: pb,
        periodEnd: pe,
        disposalDate: row.disposalDate || null,
        impairmentAmount: impairAmt,
        impairmentDate: row.impairmentDate || null,
        bookMonthly: row.bookMonthly,
        bookAccDepEnd: row.bookAccDepEnd,
        accDepAtImpairment: row.accDepAtImpairment || undefined,
      })
      _applyTestResult(row, r)
      row.impairmentAmount = impairAmt
      row.postImpairmentMonthlyDep = r.postImpairmentMonthlyDep
      row.postImpairmentNetValue = round2(cost - r.accDepAtImpairment - impairAmt)
      row.monthsBeforeImpairment = r.monthsBeforeImpairmentInPeriod
      row.monthsAfterImpairment = r.monthsAfterImpairmentInPeriod
      row.accDepAtImpairment = r.accDepAtImpairment
      _applyAdvancedDiagnostics(row)
      return
    }

    // A: 不含减值 — 若有估计变更日则分段
    if (row.estimateChangeDate && (row.usefulLifeAfter > 0 || row.salvageRateAfter > 0)) {
      const lifeBefore = row.usefulLifeBefore || life
      const rateBefore = row.salvageRateBefore > 0 ? row.salvageRateBefore : rate
      const lifeAfter = row.usefulLifeAfter || life
      const rateAfter = row.salvageRateAfter > 0 ? row.salvageRateAfter : rate
      const er = calcWithEstimateChangeTest({
        cost,
        startDate: row.startDate || null,
        periodBegin: pb,
        periodEnd: pe,
        disposalDate: row.disposalDate || null,
        usefulLifeYearsBefore: lifeBefore,
        salvageRateBefore: rateBefore,
        usefulLifeYearsAfter: lifeAfter,
        salvageRateAfter: rateAfter,
        changeDate: row.estimateChangeDate,
        bookMonthly: row.bookMonthly,
        bookAccDepEnd: row.bookAccDepEnd,
      })
      _applyTestResult(row, er)
      row.calcMonthly = er.monthlyAfter
      row.monthlyDep = er.monthlyAfter
      row.postImpairmentMonthlyDep = er.monthlyAfter
      _applyAdvancedDiagnostics(row)
      return
    }

    const r = calcStraightLineTest({
      cost,
      salvageRate: rate,
      usefulLifeYears: life,
      startDate: row.startDate || null,
      periodBegin: pb,
      periodEnd: pe,
      disposalDate: row.disposalDate || null,
      bookMonthly: row.bookMonthly,
      bookAccDepEnd: row.bookAccDepEnd,
    })
    _applyTestResult(row, r)
    row.impairmentAmount = 0
    row.postImpairmentMonthlyDep = r.calcMonthly
    row.postImpairmentNetValue = round2(cost - r.calcAccDep)
    row.monthsBeforeImpairment = r.periodMonths
    row.monthsAfterImpairment = 0
    _applyAdvancedDiagnostics(row)
  }

  function _applyAdvancedDiagnostics(row: DepreciationRow): void {
    const pe = periodEnd.value || undefined
    const pb = periodBegin.value || undefined
    const rate = row.salvageRate > 1 ? row.salvageRate / 100 : row.salvageRate

    row.beginAccCheck = checkBeginAccumulatedDep({
      cost: row.originalCost,
      salvageRate: rate,
      usefulLifeYears: row.usefulLife,
      startDate: row.startDate,
      periodBegin: pb,
      bookAccDepBegin: row.accDepBegin,
      tolerance: materiality.value.roundingTolerance,
    })

    const tax = checkTaxMinLife(row.category, row.usefulLife)
    row.taxLifeWarning = tax.message

    row.diffAttribution = attributeDepreciationDiff({
      difference: row.difference,
      monthlyDiff: row.monthlyDiff,
      accDepDiff: row.accDepDiff,
      calcMonthly: row.calcMonthly,
      bookMonthly: row.bookMonthly,
      periodMonths: row.periodMonths,
      monthsAtEnd: row.monthsAtEnd,
      usefulLifeMonths: row.usefulLifeMonths,
      disposalDate: row.disposalDate,
      impairmentAmount: row.impairmentAmount || row.impairmentEnd,
      impairmentDate: row.impairmentDate,
      depMethod: row.depMethod,
      beginAccDiff: row.beginAccCheck ? Math.abs(row.beginAccCheck.diff) : 0,
      estimateChanged: !!row.estimateChangeDate,
      taxLifeWarning: row.taxLifeWarning,
      roundingTolerance: materiality.value.roundingTolerance,
    })

    row.diffSeverity = classifyDiffAmount(
      Math.max(Math.abs(row.difference), Math.abs(row.accDepDiff)),
      materiality.value,
    )
  }

  function _applyTestResult(row: DepreciationRow, r: ReturnType<typeof calcStraightLineTest>): void {
    row.usefulLifeMonths = r.usefulLifeMonths
    row.calcMonthly = r.calcMonthly
    row.monthlyDep = r.calcMonthly
    row.fullDepDate = r.fullDepDate
    row.monthsAtBegin = r.monthsAtBegin
    row.monthsAtEnd = r.monthsAtEnd
    row.elapsedMonths = r.monthsAtEnd
    row.periodMonths = r.periodMonths
    row.periodTotal = r.periodDep
    row.calcAccDep = r.calcAccDep
    row.accDepEnd = round2(row.accDepBegin + r.periodDep)
    row.monthlyDiff = r.monthlyDiff
    row.accDepDiff = r.accDepDiff
    row.difference = round2(row.bookDepreciation - r.periodDep)
    row.monthly = _distributeMonthly(r.periodDep, r.periodMonths)
  }

  /** 将本期折旧摊到 1~12 月（前 periodMonths 个月等额，其余 0） */
  function _distributeMonthly(periodDep: number, periodMonths: number): number[] {
    const arr = new Array(12).fill(0)
    if (periodMonths <= 0) return arr
    const m = periodDep / periodMonths
    const n = Math.min(Math.round(periodMonths), 12)
    for (let i = 0; i < n; i++) arr[i] = round2(m)
    // 尾差调到最后一个计提月
    const sum = arr.reduce((a, b) => a + b, 0)
    if (n > 0) arr[n - 1] = round2(arr[n - 1] + (periodDep - sum))
    return arr
  }

  function recalcAll(): void {
    for (const row of rows.value) recalcRow(row)
    _refreshEngineMeta()
    _persist()
    publishDepreciationCalculated()
  }

  function _refreshEngineMeta(): void {
    const selected = sampleMode.value
      ? rows.value.filter((r) => r.inSample)
      : rows.value
    const totalCost = rows.value.reduce((s, r) => s + r.originalCost, 0) || 1
    const sampleCost = selected.reduce((s, r) => s + r.originalCost, 0)
    engineMeta.value = buildEngineWatermark({
      branch: branch.value,
      periodEnd: periodEnd.value,
      rowCount: selected.length,
      sampleMode: sampleMode.value,
      sampleCoverage: sampleMode.value ? sampleCost / totalCost : 1,
    })
    options?.onSave?.(`${ITEM_PREFIX}-engine-meta`, engineMeta.value)
  }

  // ─── H1-7 增加检查：折旧起算 / 暂估转固 ─────────────────────────────────────

  function syncFromAdditionH7(): { linked: number; notes: string[] } {
    const item = allResponses.value.get('H1-7-rows')
    let additions: any[] = []
    if (item?.remark) {
      try {
        const p = JSON.parse(item.remark)
        additions = Array.isArray(p) ? p : []
      } catch {
        additions = []
      }
    }
    const notes: string[] = []
    let linked = 0
    for (const a of additions) {
      const start = String(a.depStartDate || a.acceptanceDate || a.acquisitionDate || '').trim()
      if (!start) continue
      const row = rows.value.find((r) =>
        (a.assetNo && r.assetNo && a.assetNo === r.assetNo)
        || (a.name && r.assetName && a.name === r.assetName),
      )
      if (!row) {
        notes.push(`H1-7「${a.name || a.assetNo}」未匹配到 H1-12 行`)
        continue
      }
      const prev = row.startDate
      row.startDate = start
      row.linkedFromH17 = true
      if (a.isProvisional === 'Y' && !row.remark.includes('暂估')) {
        row.remark = `${row.remark ? row.remark + '; ' : ''}H1-7暂估转固起算`
      } else if (!row.remark.includes('H1-7')) {
        row.remark = `${row.remark ? row.remark + '; ' : ''}来源勾稽:H1-7增加`
      }
      if (prev && prev !== start) {
        notes.push(`${row.assetName || row.assetNo}：起算日 ${prev} → ${start}`)
      }
      linked++
      recalcRow(row)
    }
    if (linked) _persist()
    return { linked, notes }
  }

  // ─── H1-8 处置联动 ─────────────────────────────────────────────────────────

  function syncFromDisposalH18(): { linked: number; notes: string[] } {
    const item = allResponses.value.get('H1-8-rows')
    const disposals = parseH18DisposalRows(item?.remark)
    const notes: string[] = []
    let linked = 0
    for (const d of disposals) {
      const row = rows.value.find((r) =>
        (d.assetNo && r.assetNo && d.assetNo === r.assetNo)
        || (d.name && r.assetName && d.name === r.assetName),
      )
      if (!row) {
        notes.push(`H1-8「${d.name || d.assetNo}」未匹配到 H1-12 行`)
        continue
      }
      if (d.disposalDate) row.disposalDate = d.disposalDate
      row.disposalAccDepFromH18 = d.accDep
      row.linkedFromH18 = true
      if (!row.remark.includes('H1-8')) {
        row.remark = `${row.remark ? row.remark + '; ' : ''}来源勾稽:H1-8处置`
      }
      linked++
      recalcRow(row)
    }
    _persist()
    return { linked, notes }
  }

  // ─── H1-14 减值时点带入 ────────────────────────────────────────────────────

  function syncFromImpairmentH14(): { linked: number; notes: string[] } {
    const item = allResponses.value.get('H1-14-rows')
    const impairs = parseH14ImpairmentRows(item?.remark)
    const notes: string[] = []
    let linked = 0
    const pb = periodBegin.value

    for (const imp of impairs) {
      if (imp.impairmentAmount <= 0 && imp.alreadyProvided <= 0 && imp.supplement <= 0) continue
      // 按名称/分类匹配；分类级汇总则匹配该分类下未单独减值的行
      let targets = rows.value.filter((r) =>
        (imp.assetGroup && (r.assetName === imp.assetGroup || r.assetNo === imp.assetGroup)),
      )
      if (!targets.length && imp.category) {
        targets = rows.value.filter((r) => r.category === imp.category && (r.impairmentEnd || r.impairmentAmount) <= 0.005)
      }
      if (!targets.length) {
        notes.push(`H1-14「${imp.assetGroup || imp.category}」未匹配到 H1-12 行`)
        continue
      }
      for (const row of targets) {
        const endAmt = imp.alreadyProvided || imp.impairmentAmount
        if (endAmt > 0) {
          row.impairmentEnd = endAmt
          row.impairmentAmount = endAmt
        }
        if (imp.supplement > 0) {
          row.impairmentProvision = imp.supplement
          row.impairmentDate = row.impairmentDate || pb
        }
        if (!row.impairmentDate && pb) row.impairmentDate = pb
        // 期初已有 + 本期补提 → 多次事件
        if (row.impairmentBegin > 0.005 && row.impairmentProvision > 0.005) {
          row.impairmentEvents = [
            { eventDate: '', amount: row.impairmentBegin, remainingLife: 0, newMonthlyDep: 0 },
            { eventDate: row.impairmentDate, amount: row.impairmentProvision, remainingLife: 0, newMonthlyDep: 0 },
          ]
        } else if (row.impairmentAmount > 0 && (!row.impairmentEvents || row.impairmentEvents.length === 0)) {
          row.impairmentEvents = [{
            eventDate: row.impairmentDate,
            amount: row.impairmentAmount,
            remainingLife: 0,
            newMonthlyDep: 0,
          }]
        }
        row.linkedFromH14 = true
        if (imp.indexRef && !row.remark.includes(imp.indexRef)) {
          row.remark = `${row.remark ? row.remark + '; ' : ''}H1-14:${imp.indexRef}`
        }
        linked++
        recalcRow(row)
      }
    }
    _persist()
    return { linked, notes }
  }

  // ─── 抽样 ──────────────────────────────────────────────────────────────────

  function applySampling(coverageTarget = 0.8): SamplingResult<DepreciationRow> {
    const result = selectDepreciationSample(rows.value, periodBegin.value, {
      costCoverageTarget: coverageTarget,
    })
    const idSet = result.selectedIds
    for (const row of rows.value) {
      row.inSample = idSet.has(row.rowId)
    }
    sampleMode.value = true
    lastSampling.value = result
    _refreshEngineMeta()
    _persist()
    options?.onSave?.(`${ITEM_PREFIX}-sampling-note`, {
      rationale: result.rationale,
      costCoverage: result.costCoverage,
      countCoverage: result.countCoverage,
      selectedCount: result.selected.length,
      totalCount: rows.value.length,
    })
    return result
  }

  function clearSampling(): void {
    sampleMode.value = false
    lastSampling.value = null
    for (const row of rows.value) row.inSample = true
    _refreshEngineMeta()
    _persist()
  }

  function setMateriality(cfg: Partial<MaterialityConfig>): void {
    materiality.value = { ...materiality.value, ...cfg }
    options?.onSave?.(`${ITEM_PREFIX}-materiality`, materiality.value)
    recalcAll()
  }

  /** 生成审计说明草稿（处置影响 + 抽样 + 水印） */
  function buildAuditNoteDraft(): string {
    const lines: string[] = []
    if (engineMeta.value) lines.push(formatWatermarkLine(engineMeta.value))
    const beginFails = rows.value.filter((r) => r.beginAccCheck && !r.beginAccCheck.ok)
    if (beginFails.length) {
      lines.push(`【期初累计】${beginFails.length} 项期初累计折旧与测算不符，应先完成期初测试后再依赖本期结论。`)
    }
    const disposals = rows.value.filter((r) => r.disposalDate)
    if (disposals.length) {
      const sum = disposals.reduce((s, r) => s + (r.disposalAccDepFromH18 || r.bookAccDepEnd), 0)
      lines.push(`【本期减少】${disposals.length} 项处置/减少，关联累计折旧约 ${sum.toFixed(2)} 元（勾稽 H1-8），已按处置日停提测算本期折旧。`)
    }
    if (sampleMode.value && lastSampling.value) {
      lines.push(`【抽样】原值覆盖 ${(lastSampling.value.costCoverage * 100).toFixed(1)}%，件数 ${lastSampling.value.selected.length}/${rows.value.length}。${lastSampling.value.rationale.join('；')}`)
    }
    const material = rows.value.filter((r) => r.diffSeverity === 'material' && (!sampleMode.value || r.inSample))
    if (material.length) {
      lines.push(`【重大差异】${material.length} 项超单笔重要性，归因示例：${material.slice(0, 3).map((r) => `${r.assetName || r.assetNo}:${r.diffAttribution?.primary || ''}`).join('；')}`)
    }
    const nonSL = rows.value.filter((r) => r.depMethod && r.depMethod !== '直线法')
    if (nonSL.length) {
      lines.push(`【非直线法】${nonSL.length} 项（双倍余额递减/年数总和/工作量等），已按该方法测算；直线法底稿仅作对照。`)
    }
    const tax = rows.value.filter((r) => r.taxLifeWarning)
    if (tax.length) {
      lines.push(`【税法年限提示】${tax.length} 项会计年限低于税法最低年限（提示性，不阻断）。`)
    }
    return lines.join('\n')
  }

  function applyAuditNoteDraft(): void {
    const draft = buildAuditNoteDraft()
    const merged = auditNote.value ? `${auditNote.value}\n\n——自动生成——\n${draft}` : draft
    saveNote(merged)
  }

  // ─── 分支推荐 ──────────────────────────────────────────────────────────────

  const branchRecommendation = computed<BranchRecommendation>(() => {
    const counts = { A: 0, B: 0, C: 0 }
    for (const row of rows.value) {
      counts[row.recommendedBranch]++
    }
    let recommended: DepreciationBranch = 'A'
    let reason = '账面均无减值准备，适用不含减值直线法测算'
    if (counts.C > 0) {
      recommended = 'C'
      reason = `有 ${counts.C} 项资产存在多次减值事件，建议使用「多次减值」测算表`
    } else if (counts.B > 0) {
      recommended = 'B'
      reason = `有 ${counts.B} 项资产存在减值余额/本期计提，建议使用「含减值」测算表`
    } else if (rows.value.length === 0) {
      reason = '尚无测算数据；可从 H1-2 带入或导入企业固定资产台账'
    }
    return { recommended, reason, counts }
  })

  /** 按行级推荐汇总后切换分支并重算 */
  function applyRecommendedBranch(): DepreciationBranch {
    const rec = branchRecommendation.value.recommended
    branch.value = rec
    recalcAll()
    options?.onSave?.(`${ITEM_PREFIX}-branch`, rec)
    options?.onBranchChange?.(rec)
    return rec
  }

  // ─── 从 H1-2 带入 ──────────────────────────────────────────────────────────

  function importFromDetail(): { imported: number; branch: DepreciationBranch } {
    const item = allResponses.value.get('H1-2-rows')
    let detailRows: any[] = []
    if (item?.remark) {
      try {
        const parsed = JSON.parse(item.remark)
        detailRows = Array.isArray(parsed) ? parsed : []
      } catch { detailRows = [] }
    }
    if (options?.crossSheetDetailRows?.value?.length) {
      detailRows = options.crossSheetDetailRows.value
    }

    const mapped = detailRows
      .filter((d) => _num(d.originalCostEnd ?? d.originalCost ?? d.originalCostBegin) > 0)
      .map((d) => {
        const row = _emptyRow()
        row.category = d.category ?? ''
        row.assetNo = d.assetNo ?? d.assetCode ?? ''
        row.assetName = d.name ?? d.assetName ?? ''
        row.department = d.department ?? ''
        row.originalCost = _num(d.originalCostEnd ?? d.originalCost)
        row.salvageRate = _normalizeSalvage(_num(d.salvageRate))
        row.usefulLife = _num(d.usefulLife)
        row.startDate = d.acquisitionDate ?? d.startDate ?? ''
        row.depMethod = d.depMethod ?? '直线法'
        row.accDepBegin = _num(d.accDepBegin)
        row.bookAccDepEnd = _num(d.accDepEnd)
        row.bookDepreciation = _num(d.accDepProvision ?? d.annualDep)
        row.bookMonthly = _num(d.monthlyDep)
        row.impairmentBegin = _num(d.impairmentBegin)
        row.impairmentEnd = _num(d.impairmentEnd)
        row.impairmentProvision = _num(d.impairmentProvision)
        row.impairmentAmount = row.impairmentEnd
        if (row.impairmentProvision > 0 && periodBegin.value) {
          row.impairmentDate = periodBegin.value
          row.impairmentEvents = [{
            eventDate: periodBegin.value,
            amount: row.impairmentProvision,
            remainingLife: 0,
            newMonthlyDep: 0,
          }]
        } else if (row.impairmentBegin > 0 && row.impairmentEnd > row.impairmentBegin + 0.005) {
          // 期初已有 + 本期新增 → 多次减值信号
          row.impairmentEvents = [
            { eventDate: '', amount: row.impairmentBegin, remainingLife: 0, newMonthlyDep: 0 },
            { eventDate: periodBegin.value || '', amount: row.impairmentEnd - row.impairmentBegin, remainingLife: 0, newMonthlyDep: 0 },
          ]
        }
        row.remark = '来源:H1-2'
        return row
      })

    rows.value = mapped
    const rec = branchRecommendation.value.recommended
    // 先按推荐切分支并重算落盘，再通知父级切换视图（避免卸载丢算）
    branch.value = rec
    recalcAll()
    options?.onSave?.(`${ITEM_PREFIX}-branch`, rec)
    options?.onBranchChange?.(rec)
    return { imported: mapped.length, branch: rec }
  }

  // ─── 企业原始表一键导入 ────────────────────────────────────────────────────

  /**
   * 解析企业固定资产台账（xlsx/csv 首表），表头自动映射后写入并测算。
   * 返回预览信息；实际写入由 confirm=true 控制。
   */
  async function importEnterpriseLedger(
    file: File,
    confirm = true,
  ): Promise<ImportPreview | null> {
    importing.value = true
    lastImportWarnings.value = []
    try {
      // 走 useExcelIO 低层入口（B3 批）。原实现 =
      //   read(buf, { type:'array', cellDates:true })
      //   + sheet_to_json(sheet, { header:1, defval:'', raw:false })
      // 三个选项都必须透传：cellDates 决定日期是 Date 还是序列号，raw:false 让数值/日期
      // 返回格式化字符串（下方 _fmtDateCell / _num 依赖此行为），defval:'' 决定空格填什么。
      //
      // 用 readSheetAoa 而非 parseFile —— 本函数自己在前 10 行里按映射字段数打分定位表头行，
      // parseFile 的「表头固定在某一行」模型表达不了。
      const { sheetName, rows: aoa } = await readSheetAoa(file, {
        cellDates: true,
        defval: '',
        raw: false,
      })
      if (!sheetName) {
        lastImportWarnings.value = ['文件中无工作表']
        return null
      }
      if (aoa.length < 2) {
        lastImportWarnings.value = ['工作表无数据行']
        return null
      }

      // 定位表头行：前 10 行中映射字段数最多的一行
      let headerRowIdx = 0
      let bestScore = 0
      for (let i = 0; i < Math.min(10, aoa.length); i++) {
        const score = (aoa[i] as any[]).reduce((s, cell) => s + (_mapHeader(cell) ? 1 : 0), 0)
        if (score > bestScore) {
          bestScore = score
          headerRowIdx = i
        }
      }

      const headers = aoa[headerRowIdx] as any[]
      let fieldIndex = new Map<string, number>()

      // 优先使用项目记忆的列映射
      const remembered = loadColumnMapping(projectId.value)
      if (remembered) {
        fieldIndex = applyRememberedMapping(headers, remembered)
        if (fieldIndex.size >= 3) {
          bestScore = Math.max(bestScore, fieldIndex.size)
        } else {
          fieldIndex = new Map()
        }
      }
      if (fieldIndex.size < 3) {
        if (bestScore < 3) {
          lastImportWarnings.value = [
            `未能识别表头（仅匹配 ${bestScore} 列）。请确保含有：资产名称/原值/开始使用日期/使用年限/残值率 等列`,
          ]
          return null
        }
        headers.forEach((h, idx) => {
          const f = _mapHeader(h)
          if (f && !fieldIndex.has(f)) fieldIndex.set(f, idx)
        })
      }

      // 记住本次映射
      saveColumnMapping(projectId.value, buildMappingFromFieldIndex(headers, fieldIndex))

      const warnings: string[] = []
      if (remembered && fieldIndex.size >= 3) warnings.push('已应用本项目上次保存的列映射')
      if (!fieldIndex.has('originalCost')) warnings.push('缺少原值列')
      if (!fieldIndex.has('startDate')) warnings.push('缺少开始使用日期列，期数将按默认12月估算')
      if (!fieldIndex.has('usefulLife')) warnings.push('缺少使用年限列')

      const mappedRows: DepreciationRow[] = []
      for (let r = headerRowIdx + 1; r < aoa.length; r++) {
        const line = aoa[r] as any[]
        if (!line || line.every((c) => c === '' || c == null)) continue
        const get = (f: string) => {
          const i = fieldIndex.get(f)
          return i == null ? '' : line[i]
        }
        const cost = _num(get('originalCost'))
        const name = String(get('assetName') || '').trim()
        const no = String(get('assetNo') || '').trim()
        if (cost <= 0 && !name && !no) continue

        const row = _emptyRow()
        row.category = String(get('category') || '其他').trim()
        row.assetNo = no
        row.assetName = name || no || `资产${mappedRows.length + 1}`
        row.department = String(get('department') || '').trim()
        row.originalCost = cost
        row.salvageRate = _normalizeSalvage(_num(get('salvageRate')))
        row.usefulLife = _num(get('usefulLife'))
        row.startDate = _fmtDateCell(get('startDate'))
        row.disposalDate = _fmtDateCell(get('disposalDate'))
        row.depMethod = String(get('depMethod') || '直线法').trim() || '直线法'
        row.accDepBegin = _num(get('accDepBegin'))
        row.bookAccDepEnd = _num(get('bookAccDepEnd'))
        row.bookDepreciation = _num(get('bookDepreciation'))
        row.bookMonthly = _num(get('bookMonthly'))
        row.impairmentBegin = _num(get('impairmentBegin'))
        row.impairmentEnd = _num(get('impairmentEnd'))
        row.impairmentProvision = _num(get('impairmentProvision'))
        row.impairmentDate = _fmtDateCell(get('impairmentDate'))
        row.impairmentAmount = row.impairmentEnd || row.impairmentProvision
        row.estimateChangeDate = _fmtDateCell(get('estimateChangeDate'))
        row.usefulLifeBefore = _num(get('usefulLifeBefore'))
        row.usefulLifeAfter = _num(get('usefulLifeAfter'))
        row.salvageRateBefore = _normalizeSalvage(_num(get('salvageRateBefore')))
        row.salvageRateAfter = _normalizeSalvage(_num(get('salvageRateAfter')))
        if (row.impairmentBegin > 0.005 && row.impairmentProvision > 0.005) {
          row.impairmentEvents = [
            { eventDate: '', amount: row.impairmentBegin, remainingLife: 0, newMonthlyDep: 0 },
            { eventDate: row.impairmentDate || periodBegin.value, amount: row.impairmentProvision, remainingLife: 0, newMonthlyDep: 0 },
          ]
        } else if (row.impairmentAmount > 0) {
          row.impairmentEvents = [{
            eventDate: row.impairmentDate || '',
            amount: row.impairmentAmount,
            remainingLife: 0,
            newMonthlyDep: 0,
          }]
        }
        row.remark = `来源:${file.name}`
        mappedRows.push(row)
      }

      if (mappedRows.length === 0) {
        warnings.push('未解析到有效资产行')
        lastImportWarnings.value = warnings
        return null
      }

      // 临时赋值以计算推荐
      const prev = rows.value
      rows.value = mappedRows
      const recommendation = branchRecommendation.value
      const preview: ImportPreview = {
        rowCount: mappedRows.length,
        branch: recommendation.recommended,
        recommendation,
        sampleNames: mappedRows.slice(0, 5).map((r) => r.assetName),
        warnings,
      }

      if (!confirm) {
        rows.value = prev
        return preview
      }

      branch.value = recommendation.recommended
      recalcAll()
      options?.onSave?.(`${ITEM_PREFIX}-branch`, recommendation.recommended)
      options?.onBranchChange?.(recommendation.recommended)
      lastImportWarnings.value = warnings
      return preview
    } finally {
      importing.value = false
    }
  }

  function _fmtDateCell(v: unknown): string {
    if (v == null || v === '') return ''
    if (v instanceof Date) {
      const y = v.getFullYear()
      const m = String(v.getMonth() + 1).padStart(2, '0')
      const d = String(v.getDate()).padStart(2, '0')
      return `${y}-${m}-${d}`
    }
    const s = String(v).trim()
    if (/^\d{4}/.test(s)) {
      return s.replace(/\./g, '-').replace(/\//g, '-').slice(0, 10)
    }
    return s
  }

  // ─── Computed ──────────────────────────────────────────────────────────────

  const summary = computed<DepreciationSummary>(() => {
    const calculatedTotal = calcSubtotal(rows.value.map((r) => r.periodTotal))
    const bookTotal = calcSubtotal(rows.value.map((r) => r.bookDepreciation))
    const totalDifference = bookTotal - calculatedTotal
    const diffRate = calculatedTotal > 0 ? (totalDifference / calculatedTotal * 100) : 0
    const calcAccDepTotal = calcSubtotal(rows.value.map((r) => r.calcAccDep))
    const bookAccDepTotal = calcSubtotal(rows.value.map((r) => r.bookAccDepEnd))
    return {
      calculatedTotal,
      bookTotal,
      totalDifference,
      diffRate,
      calcAccDepTotal,
      bookAccDepTotal,
      accDepDiffTotal: bookAccDepTotal - calcAccDepTotal,
    }
  })

  const categorySubtotals = computed<CategorySubtotal[]>(() => {
    const map = new Map<string, CategorySubtotal>()
    for (const row of rows.value) {
      const cat = row.category || '未分类'
      let agg = map.get(cat)
      if (!agg) {
        agg = {
          category: cat,
          periodTotal: 0,
          bookDepreciation: 0,
          difference: 0,
          originalCost: 0,
          calcAccDep: 0,
          bookAccDepEnd: 0,
        }
        map.set(cat, agg)
      }
      agg.periodTotal += row.periodTotal
      agg.bookDepreciation += row.bookDepreciation
      agg.difference += row.difference
      agg.originalCost += row.originalCost
      agg.calcAccDep += row.calcAccDep
      agg.bookAccDepEnd += row.bookAccDepEnd
    }
    const list = [...map.values()]
    list.sort((a, b) => {
      const ia = CATEGORY_ORDER.indexOf(a.category)
      const ib = CATEGORY_ORDER.indexOf(b.category)
      return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib)
    })
    return list
  })

  const mismatchBranchRows = computed(() =>
    rows.value.filter((r) => r.recommendedBranch !== branch.value).map((r) => r.rowId),
  )

  const significantDiffRows = computed(() =>
    rows.value.filter((r) => {
      if (sampleMode.value && !r.inSample) return false
      return r.diffSeverity === 'review' || r.diffSeverity === 'material'
        || Math.abs(r.difference) > materiality.value.roundingTolerance
        || Math.abs(r.accDepDiff) > materiality.value.roundingTolerance
    }),
  )

  const nonStraightRows = computed(() =>
    rows.value.filter((r) => r.depMethod && r.depMethod !== '直线法'),
  )

  const advancedDashboard = computed<AdvancedDashboard>(() => {
    const visible = sampleMode.value ? rows.value.filter((r) => r.inSample) : rows.value
    return {
      beginAccFailCount: visible.filter((r) => r.beginAccCheck && !r.beginAccCheck.ok).length,
      materialDiffCount: visible.filter((r) => r.diffSeverity === 'material').length,
      reviewDiffCount: visible.filter((r) => r.diffSeverity === 'review').length,
      taxWarnCount: visible.filter((r) => r.taxLifeWarning).length,
      nonStraightCount: nonStraightRows.value.length,
      disposalLinkedCount: rows.value.filter((r) => r.linkedFromH18).length,
      impairLinkedCount: rows.value.filter((r) => r.linkedFromH14).length,
      additionLinkedCount: rows.value.filter((r) => r.linkedFromH17).length,
      sampleMode: sampleMode.value,
      sampleCoverage: engineMeta.value?.sampleCoverage ?? 1,
      watermarkLine: engineMeta.value ? formatWatermarkLine(engineMeta.value) : H1_12_ENGINE_VERSION,
    }
  })

  const displayRows = computed(() =>
    sampleMode.value ? rows.value.filter((r) => r.inSample) : rows.value,
  )

  // ─── Mutations ─────────────────────────────────────────────────────────────

  function updateCell(rowId: string, field: keyof DepreciationRow, value: any): void {
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    if (field === 'salvageRate' && typeof value === 'number' && value > 1) {
      row.salvageRate = value / 100
    }
    recalcRow(row)
    _persist()
  }

  function setBranch(b: DepreciationBranch): void {
    if (b === branch.value) return
    // 切换前落盘当前分支，避免 A/B/C 互相覆盖
    _persist()
    branch.value = b
    rows.value = _loadBranchRows(b)
    recalcAll()
    options?.onSave?.(`${ITEM_PREFIX}-branch`, b)
    options?.onBranchChange?.(b)
    // 新分支若无数据，仍把空数组镜像到兼容键，避免 H1-13 读到过期 A 数据
    _persist()
  }

  function addRow(): void {
    const row = _emptyRow()
    rows.value.push(row)
    _persist()
  }

  function removeRow(rowId: string): void {
    rows.value = rows.value.filter((r) => r.rowId !== rowId)
    _persist()
  }

  function publishDepreciationCalculated(): void {
    options?.onPublishEvent?.('h1:depreciation-calculated', {
      wp_code: 'H1',
      branch: branch.value,
      calculatedTotal: summary.value.calculatedTotal,
      byCategory: _aggregateByCategory(),
    })
  }

  function _aggregateByCategory(): Record<string, number> {
    const map: Record<string, number> = {}
    for (const row of rows.value) {
      const cat = row.category || '未分类'
      map[cat] = (map[cat] || 0) + row.periodTotal
    }
    return map
  }

  function _persist(): void {
    const b = branch.value
    options?.onSave?.(`${ITEM_PREFIX}-${b}-rows`, rows.value)
    // 兼容：活动分支同步写 H1-12-rows，供 H1-13/H1-7/政策检查跨 sheet 消费
    options?.onSave?.(`${ITEM_PREFIX}-rows`, rows.value)
  }

  function saveNote(note: string): void {
    auditNote.value = note
    options?.onSave?.(`${ITEM_PREFIX}-audit-note`, note)
  }

  function saveConclusion(conclusion: string): void {
    auditConclusion.value = conclusion
    options?.onSave?.(`${ITEM_PREFIX}-audit-conclusion`, conclusion)
  }

  watch(allResponses, () => _loadData(), { immediate: true })
  watch(periodEnd, () => {
    if (rows.value.length) recalcAll()
  })

  return {
    branch,
    rows,
    displayRows,
    auditNote,
    auditConclusion,
    summary,
    categorySubtotals,
    branchRecommendation,
    mismatchBranchRows,
    significantDiffRows,
    nonStraightRows,
    advancedDashboard,
    sampleMode,
    lastSampling,
    materiality,
    engineMeta,
    importing,
    lastImportWarnings,
    periodEnd,
    periodBegin,
    setBranch,
    applyRecommendedBranch,
    updateCell,
    addRow,
    removeRow,
    recalcRow,
    recalcAll,
    importFromDetail,
    importEnterpriseLedger,
    syncFromDisposalH18,
    syncFromImpairmentH14,
    syncFromAdditionH7,
    applySampling,
    clearSampling,
    setMateriality,
    buildAuditNoteDraft,
    applyAuditNoteDraft,
    publishDepreciationCalculated,
    saveNote,
    saveConclusion,
    H1_12_ENGINE_VERSION,
  }
}

function round2(n: number): number {
  if (!Number.isFinite(n)) return 0
  return Math.round(n * 100) / 100
}

export default useH1Depreciation
