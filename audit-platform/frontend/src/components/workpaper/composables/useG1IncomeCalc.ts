/**
 * useG1IncomeCalc — G1-5 收益测算表
 *
 * 对齐 Excel 编制逻辑：
 * - 主路径：债息/固收按合同金额×年化利率×天数/基数，结息前/后分段
 * - 账面勾稽：测算合计 vs 账上投资收益 + 应计利息
 * - 分轨：股利测算、处置损益（补充程序）
 * - 编制闸门 + 旧版「数量×股利」行迁移到股利区段
 */
import { ref, computed, watch, type Ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import {
  parseNum,
  calcRealizedGain,
  calcNetGain,
  calcSubtotal,
  calcAccruedDays,
  calcInterestByBasis,
  minDateStr,
  maxDateStr,
} from './useG1TraFinFormulaEngine'
import type { ChecklistResponse } from './useF1FormData'
import type { TradingDetailRow } from './useG1Detail'
import {
  matchSecurityKey,
  findBySecurityKeys,
  loadDetailPartials,
  dispatchG1DetailUpdated,
  pushItemsToG1Adjustment,
} from './g1CrossHelpers'

// ─── Types ───────────────────────────────────────────────────────────────────

export type G1IncomeSegment = 'interest' | 'dividend' | 'disposal'
export type G1DayCountBasis = 360 | 365

/** 债息/固收测算行（Excel 主表） */
export interface G1InterestCalcRow {
  id: string
  seq: number
  securityName: string
  contractAmount: number
  annualRatePct: number
  startDate: string
  settlementDate: string
  maturityDate: string
  dayCountBasis: G1DayCountBasis
  /** 手工覆盖天数；null/undefined 表示按日期自动算 */
  daysBeforeManual: number | null
  daysAfterManual: number | null
  daysBefore: number
  daysAfter: number
  interestBefore: number
  interestAfter: number
  interestSubtotal: number
  remark: string
}

/** 股利测算行 */
export interface G1DividendCalcRow {
  id: string
  seq: number
  securityName: string
  holdingQuantity: number
  dividendPerShare: number
  receivableAmount: number
  receivedAmount: number
  incomeDiff: number
  confirmDate: string
  incomeSource: string
  incomeRemark: string
}

/** 处置损益行 */
export interface G1DisposalCalcRow {
  id: string
  seq: number
  securityName: string
  soldQuantity: number
  dealPrice: number
  dealAmount: number
  originalCost: number
  realizedGain: number
  fee: number
  netGain: number
  disposalRemark: string
}

/** 账面勾稽块 */
export interface G1IncomeBookRecon {
  /** 项目截止日，用于结息后计息截止 */
  cutoffDate: string
  bookInvestmentIncome: number
  bookAccruedInterest: number
  bookDividendIncome: number
}

export interface G1IncomeGates {
  sampleCovered: boolean
  basisConfirmed: boolean
  accruedBoundaryNoted: boolean
}

export interface G1IncomeCalcColumn {
  prop: string
  label: string
  width: number
  formula?: boolean
  type?: 'text' | 'number' | 'date' | 'basis'
}

/** @deprecated 兼容旧导出名：合并行形状（仅迁移用） */
export interface G1IncomeCalcRow extends G1DividendCalcRow {
  soldQuantity: number
  dealPrice: number
  dealAmount: number
  originalCost: number
  realizedGain: number
  fee: number
  netGain: number
  disposalRemark: string
}

const INTEREST_KEY = 'G1-5-interest-rows'
const DIVIDEND_KEY = 'G1-5-dividend-rows'
const DISPOSAL_KEY = 'G1-5-disposal-rows'
const RECON_KEY = 'G1-5-book-recon'
const GATES_KEY = 'G1-5-gates'
const CONCLUSION_KEY = 'G1-5-conclusion'
/** 旧版单表存储键 */
const LEGACY_DATA_KEY = 'G1-5-rows'

const BOND_LIKE = new Set(['bond', 'derivative', 'other'])
const EQUITY_LIKE = new Set(['stock', 'fund'])

function loadDetailRows(map: Map<string, ChecklistResponse>): Partial<TradingDetailRow>[] {
  return loadDetailPartials(map)
}

export const DEFAULT_G1_INCOME_GATES: G1IncomeGates = {
  sampleCovered: false,
  basisConfirmed: false,
  accruedBoundaryNoted: false,
}

export const DEFAULT_G1_BOOK_RECON: G1IncomeBookRecon = {
  cutoffDate: '',
  bookInvestmentIncome: 0,
  bookAccruedInterest: 0,
  bookDividendIncome: 0,
}

export const G1_INTEREST_COLUMNS: G1IncomeCalcColumn[] = [
  { prop: 'securityName', label: '金融投资名称', width: 150, type: 'text' },
  { prop: 'contractAmount', label: '合同金额', width: 120, type: 'number' },
  { prop: 'annualRatePct', label: '年化利率(%)', width: 110, type: 'number' },
  { prop: 'startDate', label: '起始日', width: 120, type: 'date' },
  { prop: 'settlementDate', label: '结息日', width: 120, type: 'date' },
  { prop: 'maturityDate', label: '到期日', width: 120, type: 'date' },
  { prop: 'dayCountBasis', label: '计息基数', width: 90, type: 'basis' },
  { prop: 'daysBefore', label: '结息前天数', width: 100, type: 'number', formula: true },
  { prop: 'daysAfter', label: '结息后天数', width: 100, type: 'number', formula: true },
  { prop: 'interestBefore', label: '结息前利息', width: 110, type: 'number', formula: true },
  { prop: 'interestAfter', label: '结息后利息', width: 110, type: 'number', formula: true },
  { prop: 'interestSubtotal', label: '应计利息小计', width: 120, type: 'number', formula: true },
  { prop: 'remark', label: '备注', width: 120, type: 'text' },
]

export const G1_DIVIDEND_COLUMNS: G1IncomeCalcColumn[] = [
  { prop: 'securityName', label: '证券名称', width: 150, type: 'text' },
  { prop: 'holdingQuantity', label: '持有数量', width: 110, type: 'number' },
  { prop: 'dividendPerShare', label: '每股股利', width: 110, type: 'number' },
  { prop: 'receivableAmount', label: '应收金额', width: 120, type: 'number', formula: true },
  { prop: 'receivedAmount', label: '实收金额', width: 120, type: 'number' },
  { prop: 'incomeDiff', label: '差异', width: 110, type: 'number', formula: true },
  { prop: 'confirmDate', label: '确认日期', width: 120, type: 'date' },
  { prop: 'incomeSource', label: '来源', width: 120, type: 'text' },
  { prop: 'incomeRemark', label: '备注', width: 120, type: 'text' },
]

export const G1_DISPOSAL_COLUMNS: G1IncomeCalcColumn[] = [
  { prop: 'securityName', label: '证券名称', width: 150, type: 'text' },
  { prop: 'soldQuantity', label: '卖出数量', width: 100, type: 'number' },
  { prop: 'dealPrice', label: '成交价', width: 100, type: 'number' },
  { prop: 'dealAmount', label: '成交金额', width: 110, type: 'number', formula: true },
  { prop: 'originalCost', label: '原始成本', width: 110, type: 'number' },
  { prop: 'realizedGain', label: '处置损益', width: 110, type: 'number', formula: true },
  { prop: 'fee', label: '手续费', width: 100, type: 'number' },
  { prop: 'netGain', label: '净损益', width: 110, type: 'number', formula: true },
  { prop: 'disposalRemark', label: '备注', width: 120, type: 'text' },
]

// ─── Helpers ─────────────────────────────────────────────────────────────────

function emptyInterest(id: string, seq: number): G1InterestCalcRow {
  return {
    id,
    seq,
    securityName: '',
    contractAmount: 0,
    annualRatePct: 0,
    startDate: '',
    settlementDate: '',
    maturityDate: '',
    dayCountBasis: 365,
    daysBeforeManual: null,
    daysAfterManual: null,
    daysBefore: 0,
    daysAfter: 0,
    interestBefore: 0,
    interestAfter: 0,
    interestSubtotal: 0,
    remark: '',
  }
}

function emptyDividend(id: string, seq: number): G1DividendCalcRow {
  return {
    id,
    seq,
    securityName: '',
    holdingQuantity: 0,
    dividendPerShare: 0,
    receivableAmount: 0,
    receivedAmount: 0,
    incomeDiff: 0,
    confirmDate: '',
    incomeSource: '',
    incomeRemark: '',
  }
}

function emptyDisposal(id: string, seq: number): G1DisposalCalcRow {
  return {
    id,
    seq,
    securityName: '',
    soldQuantity: 0,
    dealPrice: 0,
    dealAmount: 0,
    originalCost: 0,
    realizedGain: 0,
    fee: 0,
    netGain: 0,
    disposalRemark: '',
  }
}

/**
 * 结息前：起始日 → 结息日
 * 结息后：结息日 → min(到期日, 截止日)
 * 无结息日：整段起始日 → min(到期日, 截止日) 记入结息前
 */
export function enrichInterestRow(
  r: G1InterestCalcRow,
  cutoffDate: string,
): G1InterestCalcRow {
  const basis = (r.dayCountBasis === 360 ? 360 : 365) as G1DayCountBasis
  const endCap = minDateStr(r.maturityDate || cutoffDate, cutoffDate || r.maturityDate)

  let daysBefore = 0
  let daysAfter = 0

  if (r.settlementDate) {
    daysBefore = calcAccruedDays(r.startDate, r.settlementDate)
    const afterStart = maxDateStr(r.settlementDate, r.startDate)
    daysAfter = endCap ? calcAccruedDays(afterStart, endCap) : calcAccruedDays(afterStart, r.maturityDate)
  } else if (r.startDate && endCap) {
    daysBefore = calcAccruedDays(r.startDate, endCap)
    daysAfter = 0
  }

  if (r.daysBeforeManual != null && Number.isFinite(r.daysBeforeManual)) {
    daysBefore = Math.max(0, parseNum(r.daysBeforeManual))
  }
  if (r.daysAfterManual != null && Number.isFinite(r.daysAfterManual)) {
    daysAfter = Math.max(0, parseNum(r.daysAfterManual))
  }

  const principal = parseNum(r.contractAmount)
  const rate = parseNum(r.annualRatePct)
  const interestBefore = calcInterestByBasis(principal, rate, daysBefore, basis)
  const interestAfter = calcInterestByBasis(principal, rate, daysAfter, basis)
  const interestSubtotal = interestBefore + interestAfter

  return {
    ...r,
    dayCountBasis: basis,
    daysBefore,
    daysAfter,
    interestBefore,
    interestAfter,
    interestSubtotal,
  }
}

export function enrichDividendRow(r: G1DividendCalcRow): G1DividendCalcRow {
  const receivableAmount = parseNum(r.holdingQuantity) * parseNum(r.dividendPerShare)
  const incomeDiff = receivableAmount - parseNum(r.receivedAmount)
  return { ...r, receivableAmount, incomeDiff }
}

export function enrichDisposalRow(r: G1DisposalCalcRow): G1DisposalCalcRow {
  const qty = parseNum(r.soldQuantity)
  const price = parseNum(r.dealPrice)
  // 有数量与单价时自动算成交金额；否则沿用手工成交金额
  const dealAmount = qty !== 0 && price !== 0 ? qty * price : parseNum(r.dealAmount)
  const realizedGain = calcRealizedGain(dealAmount, parseNum(r.originalCost))
  const netGain = calcNetGain(realizedGain, parseNum(r.fee))
  return { ...r, dealAmount, realizedGain, netGain }
}

function parseJsonArray<T>(raw: string | undefined | null): Partial<T>[] | null {
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : null
  } catch {
    return null
  }
}

function loadInterestRows(map: Map<string, ChecklistResponse>, cutoff: string): G1InterestCalcRow[] {
  const raw = map.get(INTEREST_KEY)?.conclusion
  const parsed = parseJsonArray<G1InterestCalcRow>(raw)
  if (!parsed || parsed.length === 0) return [enrichInterestRow(emptyInterest('1', 1), cutoff)]
  return parsed.map((p, i) =>
    enrichInterestRow({ ...emptyInterest(p.id ?? String(i + 1), p.seq ?? i + 1), ...p }, cutoff),
  )
}

function loadDividendRows(map: Map<string, ChecklistResponse>): G1DividendCalcRow[] {
  const raw = map.get(DIVIDEND_KEY)?.conclusion
  const parsed = parseJsonArray<G1DividendCalcRow>(raw)
  if (parsed && parsed.length > 0) {
    return parsed.map((p, i) =>
      enrichDividendRow({ ...emptyDividend(p.id ?? String(i + 1), p.seq ?? i + 1), ...p }),
    )
  }
  // 旧版 G1-5-rows → 股利区
  const legacy = parseJsonArray<G1IncomeCalcRow>(map.get(LEGACY_DATA_KEY)?.conclusion)
  if (legacy && legacy.length > 0) {
    const hasDividend = legacy.some(
      (p) => parseNum(p.holdingQuantity) !== 0 || parseNum(p.dividendPerShare) !== 0 || !!p.securityName,
    )
    if (hasDividend) {
      return legacy.map((p, i) =>
        enrichDividendRow({
          ...emptyDividend(p.id ?? String(i + 1), p.seq ?? i + 1),
          securityName: p.securityName ?? '',
          holdingQuantity: parseNum(p.holdingQuantity),
          dividendPerShare: parseNum(p.dividendPerShare),
          receivedAmount: parseNum(p.receivedAmount),
          confirmDate: p.confirmDate ?? '',
          incomeSource: p.incomeSource ?? '',
          incomeRemark: p.incomeRemark ?? '',
        }),
      )
    }
  }
  return [enrichDividendRow(emptyDividend('1', 1))]
}

function loadDisposalRows(map: Map<string, ChecklistResponse>): G1DisposalCalcRow[] {
  const raw = map.get(DISPOSAL_KEY)?.conclusion
  const parsed = parseJsonArray<G1DisposalCalcRow>(raw)
  if (parsed && parsed.length > 0) {
    return parsed.map((p, i) =>
      enrichDisposalRow({ ...emptyDisposal(p.id ?? String(i + 1), p.seq ?? i + 1), ...p }),
    )
  }
  const legacy = parseJsonArray<G1IncomeCalcRow>(map.get(LEGACY_DATA_KEY)?.conclusion)
  if (legacy && legacy.length > 0) {
    const hasDisposal = legacy.some(
      (p) => parseNum(p.soldQuantity) !== 0 || parseNum(p.dealAmount) !== 0 || parseNum(p.originalCost) !== 0,
    )
    if (hasDisposal) {
      return legacy.map((p, i) =>
        enrichDisposalRow({
          ...emptyDisposal(p.id ?? `d-${i + 1}`, p.seq ?? i + 1),
          securityName: p.securityName ?? '',
          soldQuantity: parseNum(p.soldQuantity),
          dealPrice: parseNum(p.dealPrice),
          dealAmount: parseNum(p.dealAmount),
          originalCost: parseNum(p.originalCost),
          fee: parseNum(p.fee),
          disposalRemark: p.disposalRemark ?? '',
        }),
      )
    }
  }
  return [enrichDisposalRow(emptyDisposal('1', 1))]
}

function loadRecon(map: Map<string, ChecklistResponse>): G1IncomeBookRecon {
  const raw = map.get(RECON_KEY)?.conclusion
  if (!raw) return { ...DEFAULT_G1_BOOK_RECON }
  try {
    return { ...DEFAULT_G1_BOOK_RECON, ...(JSON.parse(raw) as Partial<G1IncomeBookRecon>) }
  } catch {
    return { ...DEFAULT_G1_BOOK_RECON }
  }
}

function loadGates(map: Map<string, ChecklistResponse>): G1IncomeGates {
  const raw = map.get(GATES_KEY)?.conclusion
  if (!raw) return { ...DEFAULT_G1_INCOME_GATES }
  try {
    return { ...DEFAULT_G1_INCOME_GATES, ...(JSON.parse(raw) as Partial<G1IncomeGates>) }
  } catch {
    return { ...DEFAULT_G1_INCOME_GATES }
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useG1IncomeCalc(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean>
}) {
  const bookRecon = ref<G1IncomeBookRecon>(loadRecon(opts.allResponses.value))
  const interestRows = ref<G1InterestCalcRow[]>(
    loadInterestRows(opts.allResponses.value, bookRecon.value.cutoffDate),
  )
  const dividendRows = ref<G1DividendCalcRow[]>(loadDividendRows(opts.allResponses.value))
  const disposalRows = ref<G1DisposalCalcRow[]>(loadDisposalRows(opts.allResponses.value))
  const gates = ref<G1IncomeGates>(loadGates(opts.allResponses.value))
  const auditConclusion = ref(opts.allResponses.value.get(CONCLUSION_KEY)?.conclusion ?? '')
  const segment = ref<G1IncomeSegment>('interest')

  function reenrichInterest() {
    const cutoff = bookRecon.value.cutoffDate
    interestRows.value = interestRows.value.map((r) => enrichInterestRow(r, cutoff))
  }

  function loadAll() {
    bookRecon.value = loadRecon(opts.allResponses.value)
    interestRows.value = loadInterestRows(opts.allResponses.value, bookRecon.value.cutoffDate)
    dividendRows.value = loadDividendRows(opts.allResponses.value)
    disposalRows.value = loadDisposalRows(opts.allResponses.value)
    gates.value = loadGates(opts.allResponses.value)
    auditConclusion.value = opts.allResponses.value.get(CONCLUSION_KEY)?.conclusion ?? ''
  }

  watch(
    () => opts.allResponses.value.get(INTEREST_KEY)?.conclusion,
    (raw) => {
      if (raw) interestRows.value = loadInterestRows(opts.allResponses.value, bookRecon.value.cutoffDate)
    },
  )

  const interestTotal = computed(() =>
    calcSubtotal(interestRows.value.map((r) => parseNum(r.interestSubtotal))),
  )
  const dividendReceivableTotal = computed(() =>
    calcSubtotal(dividendRows.value.map((r) => parseNum(r.receivableAmount))),
  )
  const dividendDiffTotal = computed(() =>
    calcSubtotal(dividendRows.value.map((r) => parseNum(r.incomeDiff))),
  )
  const disposalNetTotal = computed(() =>
    calcSubtotal(disposalRows.value.map((r) => parseNum(r.netGain))),
  )

  /** 账上利息相关合计 = 投资收益 + 应计利息 */
  const bookInterestTotal = computed(
    () => parseNum(bookRecon.value.bookInvestmentIncome) + parseNum(bookRecon.value.bookAccruedInterest),
  )
  /** 债息测算 vs 账面差异（主勾稽） */
  const interestBookDiff = computed(() => interestTotal.value - bookInterestTotal.value)
  /** 股利测算 vs 账上股利 */
  const dividendBookDiff = computed(
    () => dividendReceivableTotal.value - parseNum(bookRecon.value.bookDividendIncome),
  )

  const balanceOk = computed(() => Math.abs(interestBookDiff.value) < 0.01)

  const gatesReady = computed(
    () =>
      gates.value.sampleCovered &&
      gates.value.basisConfirmed &&
      gates.value.accruedBoundaryNoted,
  )

  function persistInterest() {
    if (!opts.isReadonly.value) {
      opts.debouncedSave(INTEREST_KEY, { conclusion: JSON.stringify(interestRows.value) })
    }
  }
  function persistDividend() {
    if (!opts.isReadonly.value) {
      opts.debouncedSave(DIVIDEND_KEY, { conclusion: JSON.stringify(dividendRows.value) })
    }
  }
  function persistDisposal() {
    if (!opts.isReadonly.value) {
      opts.debouncedSave(DISPOSAL_KEY, { conclusion: JSON.stringify(disposalRows.value) })
    }
  }
  function persistRecon() {
    if (!opts.isReadonly.value) {
      opts.debouncedSave(RECON_KEY, { conclusion: JSON.stringify(bookRecon.value) })
    }
  }
  function persistGates() {
    if (!opts.isReadonly.value) {
      opts.debouncedSave(GATES_KEY, { conclusion: JSON.stringify(gates.value) })
    }
  }

  watch(auditConclusion, (v) => {
    if (!opts.isReadonly.value) opts.debouncedSave(CONCLUSION_KEY, { conclusion: v })
  })

  function updateGates(patch: Partial<G1IncomeGates>) {
    if (opts.isReadonly.value) return
    gates.value = { ...gates.value, ...patch }
    persistGates()
  }

  function updateBookRecon(patch: Partial<G1IncomeBookRecon>) {
    if (opts.isReadonly.value) return
    const prevCutoff = bookRecon.value.cutoffDate
    bookRecon.value = { ...bookRecon.value, ...patch }
    persistRecon()
    if (patch.cutoffDate !== undefined && patch.cutoffDate !== prevCutoff) {
      reenrichInterest()
      persistInterest()
    }
  }

  function updateInterestRow(id: string, patch: Partial<G1InterestCalcRow>) {
    if (opts.isReadonly.value) return
    interestRows.value = interestRows.value.map((r) =>
      r.id === id ? enrichInterestRow({ ...r, ...patch }, bookRecon.value.cutoffDate) : r,
    )
    persistInterest()
  }

  function updateDividendRow(id: string, patch: Partial<G1DividendCalcRow>) {
    if (opts.isReadonly.value) return
    dividendRows.value = dividendRows.value.map((r) =>
      r.id === id ? enrichDividendRow({ ...r, ...patch }) : r,
    )
    persistDividend()
  }

  function updateDisposalRow(id: string, patch: Partial<G1DisposalCalcRow>) {
    if (opts.isReadonly.value) return
    disposalRows.value = disposalRows.value.map((r) =>
      r.id === id ? enrichDisposalRow({ ...r, ...patch }) : r,
    )
    persistDisposal()
  }

  async function addInterestRow() {
    if (opts.isReadonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('请输入金融投资名称', '新增债息测算行', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        inputPattern: /\S+/,
        inputErrorMessage: '名称不能为空',
      })
      const seq = interestRows.value.length + 1
      interestRows.value = [
        ...interestRows.value,
        enrichInterestRow(
          { ...emptyInterest(`int-${Date.now()}`, seq), securityName: value },
          bookRecon.value.cutoffDate,
        ),
      ]
      persistInterest()
    } catch {
      /* cancelled */
    }
  }

  async function addDividendRow() {
    if (opts.isReadonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('请输入证券名称', '新增股利测算行', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        inputPattern: /\S+/,
        inputErrorMessage: '名称不能为空',
      })
      const seq = dividendRows.value.length + 1
      dividendRows.value = [
        ...dividendRows.value,
        enrichDividendRow({ ...emptyDividend(`div-${Date.now()}`, seq), securityName: value }),
      ]
      persistDividend()
    } catch {
      /* cancelled */
    }
  }

  async function addDisposalRow() {
    if (opts.isReadonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('请输入证券名称', '新增处置测算行', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        inputPattern: /\S+/,
        inputErrorMessage: '名称不能为空',
      })
      const seq = disposalRows.value.length + 1
      disposalRows.value = [
        ...disposalRows.value,
        enrichDisposalRow({ ...emptyDisposal(`dis-${Date.now()}`, seq), securityName: value }),
      ]
      persistDisposal()
    } catch {
      /* cancelled */
    }
  }

  function removeInterestRow(id: string) {
    if (opts.isReadonly.value || interestRows.value.length <= 1) return
    interestRows.value = interestRows.value
      .filter((r) => r.id !== id)
      .map((r, i) => ({ ...r, seq: i + 1 }))
    persistInterest()
  }

  function removeDividendRow(id: string) {
    if (opts.isReadonly.value || dividendRows.value.length <= 1) return
    dividendRows.value = dividendRows.value
      .filter((r) => r.id !== id)
      .map((r, i) => ({ ...r, seq: i + 1 }))
    persistDividend()
  }

  function removeDisposalRow(id: string) {
    if (opts.isReadonly.value || disposalRows.value.length <= 1) return
    disposalRows.value = disposalRows.value
      .filter((r) => r.id !== id)
      .map((r, i) => ({ ...r, seq: i + 1 }))
    persistDisposal()
  }

  /**
   * 从 G1-2 带入：债类/衍生/其他 → 债息行；股票/基金 → 股利行。
   * 合同金额取期末审定成本（或期末成本）；账面利息/股利合计写入勾稽块参考。
   */
  function syncFromDetail(): { interest: number; dividend: number } {
    if (opts.isReadonly.value) return { interest: 0, dividend: 0 }
    const details = loadDetailRows(opts.allResponses.value)
    if (!details.length) return { interest: 0, dividend: 0 }

    const existingInt = new Map(
      interestRows.value.map((r) => [matchSecurityKey({ securityName: r.securityName }), r]),
    )
    const existingDiv = new Map(
      dividendRows.value.map((r) => [matchSecurityKey({ securityName: r.securityName }), r]),
    )

    const nextInt: G1InterestCalcRow[] = []
    const nextDiv: G1DividendCalcRow[] = []
    let bookInterestHint = 0
    let bookDividendHint = 0

    for (const d of details) {
      const name = (d.securityName || '').trim()
      if (!name) continue
      const investType = d.investType || 'other'
      const income = parseNum(d.dividendIncome)

      if (BOND_LIKE.has(investType)) {
        bookInterestHint += income
        const prev = existingInt.get(matchSecurityKey({ securityName: name }))
        const contractAmount =
          parseNum(d.auditedClosingCost) ||
          parseNum(d.closingCost) ||
          parseNum(d.openingCost) ||
          parseNum(d.initialCost)
        nextInt.push(
          enrichInterestRow(
            {
              ...(prev || emptyInterest(`int-${Date.now()}-${nextInt.length}`, nextInt.length + 1)),
              securityName: name,
              contractAmount: contractAmount || prev?.contractAmount || 0,
              // 保留已填利率与日期
              annualRatePct: prev?.annualRatePct ?? 0,
              startDate: prev?.startDate || d.acquisitionDate || '',
              settlementDate: prev?.settlementDate || '',
              maturityDate: prev?.maturityDate || '',
              dayCountBasis: prev?.dayCountBasis ?? 365,
              daysBeforeManual: prev?.daysBeforeManual ?? null,
              daysAfterManual: prev?.daysAfterManual ?? null,
              remark: prev?.remark || '',
            },
            bookRecon.value.cutoffDate,
          ),
        )
        existingInt.delete(matchSecurityKey({ securityName: name }))
      } else if (EQUITY_LIKE.has(investType)) {
        bookDividendHint += income
        const prev = existingDiv.get(matchSecurityKey({ securityName: name }))
        nextDiv.push(
          enrichDividendRow({
            ...(prev || emptyDividend(`div-${Date.now()}-${nextDiv.length}`, nextDiv.length + 1)),
            securityName: name,
            holdingQuantity: parseNum(d.closingQuantity) || prev?.holdingQuantity || 0,
            dividendPerShare: prev?.dividendPerShare ?? 0,
            receivedAmount: income || prev?.receivedAmount || 0,
            confirmDate: prev?.confirmDate || '',
            incomeSource: prev?.incomeSource || 'G1-2',
            incomeRemark: prev?.incomeRemark || '',
          }),
        )
        existingDiv.delete(matchSecurityKey({ securityName: name }))
      }
    }

    for (const leftover of existingInt.values()) {
      if (leftover.securityName || leftover.contractAmount) nextInt.push(leftover)
    }
    for (const leftover of existingDiv.values()) {
      if (leftover.securityName || leftover.holdingQuantity) nextDiv.push(leftover)
    }

    if (nextInt.length) {
      interestRows.value = nextInt.map((r, i) => ({ ...r, seq: i + 1 }))
      persistInterest()
    }
    if (nextDiv.length) {
      dividendRows.value = nextDiv.map((r, i) => ({ ...r, seq: i + 1 }))
      persistDividend()
    }

    // 仅在账面勾稽尚未填写时带入参考数，避免覆盖已核对金额
    const reconPatch: Partial<G1IncomeBookRecon> = {}
    if (!parseNum(bookRecon.value.bookInvestmentIncome) && bookInterestHint) {
      reconPatch.bookInvestmentIncome = bookInterestHint
    }
    if (!parseNum(bookRecon.value.bookDividendIncome) && bookDividendHint) {
      reconPatch.bookDividendIncome = bookDividendHint
    }
    if (Object.keys(reconPatch).length) updateBookRecon(reconPatch)

    return { interest: nextInt.length, dividend: nextDiv.length }
  }

  /** 将债息测算小计回写 G1-2 对应行的利息/股利字段（按代码/名称匹配） */
  function pushInterestToDetail(): { matched: number; unmatchedNames: string[] } {
    if (opts.isReadonly.value) return { matched: 0, unmatchedNames: [] }
    const details = loadDetailRows(opts.allResponses.value)
    if (!details.length) {
      return {
        matched: 0,
        unmatchedNames: interestRows.value.map((r) => String(r.securityName || '').trim()).filter(Boolean),
      }
    }

    const intMap = new Map<string, (typeof interestRows.value)[0]>()
    for (const r of interestRows.value) {
      const k1 = matchSecurityKey({ securityName: r.securityName })
      if (k1) intMap.set(k1, r)
    }

    const usedInterest = new Set<(typeof interestRows.value)[0]>()
    let matched = 0
    const next = details.map((d) => {
      const hit = findBySecurityKeys(intMap, {
        id: d.id,
        securityCode: d.securityCode,
        securityName: d.securityName,
      })
      if (!hit) return d
      matched += 1
      usedInterest.add(hit)
      return { ...d, dividendIncome: parseNum(hit.interestSubtotal) }
    })
    if (matched) {
      opts.debouncedSave('G1-2-rows', { conclusion: JSON.stringify(next) })
      dispatchG1DetailUpdated('G1-5')
    }
    const unmatchedNames = interestRows.value
      .filter((r) => !usedInterest.has(r) && String(r.securityName || '').trim())
      .map((r) => String(r.securityName).trim())
    return { matched, unmatchedNames: [...new Set(unmatchedNames)] }
  }

  /** 恢复某行结息天数自动计算 */
  function clearDaysManual(id: string, which: 'before' | 'after' | 'both' = 'both') {
    if (opts.isReadonly.value) return
    const patch: Partial<G1InterestCalcRow> = {}
    if (which === 'before' || which === 'both') patch.daysBeforeManual = null
    if (which === 'after' || which === 'both') patch.daysAfterManual = null
    updateInterestRow(id, patch)
  }

  /** 债息 / 股利账面差异 + 处置净损益（测算）推送 G1-3 */
  function pushDiffToAdjustment(): number {
    if (opts.isReadonly.value) return 0
    const items: Parameters<typeof pushItemsToG1Adjustment>[2] = []

    const intDiff = interestBookDiff.value
    if (Math.abs(intDiff) >= 0.01) {
      items.push({
        description: 'G1-5 债息测算与账面差异',
        amount: intDiff,
        indexRef: 'G1-5',
        remark: `测算 ${interestTotal.value} − 账上利息相关 ${bookInterestTotal.value}`,
        accountName: '投资收益',
      })
    }

    const divDiff = dividendBookDiff.value
    if (Math.abs(divDiff) >= 0.01) {
      items.push({
        description: 'G1-5 股利测算与账面差异',
        amount: divDiff,
        indexRef: 'G1-5',
        remark: `应收股利测算 ${dividendReceivableTotal.value} − 账上股利 ${parseNum(bookRecon.value.bookDividendIncome)}`,
        accountName: '投资收益',
      })
    }

    // 行级股利收入差异（测算应收 vs 已收）——仅当无账面股利勾稽差异时补充
    for (const r of dividendRows.value) {
      const d = parseNum(r.incomeDiff)
      if (Math.abs(d) < 0.01 || !r.securityName.trim()) continue
      if (Math.abs(divDiff) >= 0.01) continue
      items.push({
        description: `G1-5 股利行差异：${r.securityName}`,
        amount: d,
        indexRef: 'G1-5',
        remark: `应收 ${r.receivableAmount} − 已收 ${r.receivedAmount}`,
        accountName: '投资收益',
      })
    }

    if (!items.length) return 0
    return pushItemsToG1Adjustment(
      opts.allResponses.value,
      opts.debouncedSave,
      items,
      'G1-5',
    )
  }

  // ── 兼容旧 UI API（过渡） ──
  const rows = dividendRows
  const grandTotal = computed(() => ({
    receivableAmount: dividendReceivableTotal.value,
    receivedAmount: calcSubtotal(dividendRows.value.map((r) => parseNum(r.receivedAmount))),
    incomeDiff: dividendDiffTotal.value,
    dealAmount: calcSubtotal(disposalRows.value.map((r) => parseNum(r.dealAmount))),
    originalCost: calcSubtotal(disposalRows.value.map((r) => parseNum(r.originalCost))),
    realizedGain: calcSubtotal(disposalRows.value.map((r) => parseNum(r.realizedGain))),
    netGain: disposalNetTotal.value,
    interestSubtotal: interestTotal.value,
  }))

  return {
    segment,
    interestColumns: G1_INTEREST_COLUMNS,
    dividendColumns: G1_DIVIDEND_COLUMNS,
    disposalColumns: G1_DISPOSAL_COLUMNS,
    /** @deprecated */ incomeColumns: G1_DIVIDEND_COLUMNS,
    interestRows,
    dividendRows,
    disposalRows,
    bookRecon,
    gates,
    gatesReady,
    interestTotal,
    dividendReceivableTotal,
    dividendDiffTotal,
    disposalNetTotal,
    bookInterestTotal,
    interestBookDiff,
    dividendBookDiff,
    balanceOk,
    auditConclusion,
    loadAll,
    updateGates,
    updateBookRecon,
    updateInterestRow,
    updateDividendRow,
    updateDisposalRow,
    addInterestRow,
    addDividendRow,
    addDisposalRow,
    removeInterestRow,
    removeDividendRow,
    removeDisposalRow,
    syncFromDetail,
    pushInterestToDetail,
    clearDaysManual,
    pushDiffToAdjustment,
    // 旧 API 兼容
    rows,
    grandTotal,
    updateRow: updateDividendRow,
    addRow: addDividendRow,
    removeRow: removeDividendRow,
    persistAll: persistDividend,
  }
}

export default useG1IncomeCalc
