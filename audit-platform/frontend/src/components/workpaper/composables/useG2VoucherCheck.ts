/**
 * useG2VoucherCheck — G2-8 凭证检查表（借方/贷方独立区块）
 *
 * 对齐 Excel《凭证检查表 G2-8》：
 * 目标 → 样本选取 → 本期发生额(借方利息确认) / 期后回笼(贷方) → 五项核对 → 检查比例 → 说明/结论 A/B/C
 *
 * 借方保留利息测算：测算利息 = 面值 × 利率/100 × 天数/365；差异 = 测算 − 凭证金额
 */
import { ref, computed, watch, onBeforeUnmount, getCurrentInstance, type Ref, type ComputedRef } from 'vue'
import { parseNum, calcInterest365, calcOverdueDays } from './useG2IntRecFormulaEngine'
import type { ChecklistResponse } from './useF1FormData'
import type { SampledVoucher, FillMode } from './useSamplingAlgorithms'

/** Excel 红色测试提示 1–5（应收利息） */
export const G2_VOUCHER_CHECK_ITEMS = [
  { key: 'check1DocsComplete', label: '①原始单据齐全', hint: '计息合同/存款证实书/对账单/银行回单等是否齐全' },
  { key: 'check2VoucherMatch', label: '②凭证与单据相符', hint: '记账凭证与原始单据金额、日期、对方单位一致' },
  { key: 'check3Accounting', label: '③账务处理正确', hint: '科目、借贷方向、金额符合准则与合同约定' },
  { key: 'check4Period', label: '④期间正确', hint: '记入正确会计期间（截止测试）' },
  { key: 'check5InterestCalc', label: '⑤利息测算一致', hint: '面值×利率×天数测算与入账金额勾稽（或合同利率法）' },
] as const

export type G2CheckKey = (typeof G2_VOUCHER_CHECK_ITEMS)[number]['key']

export interface G2VoucherSamplingPlan {
  populationDebit: number
  populationCredit: number
  populationCount: number
  amountThreshold: string
  includeRelatedParty: boolean
  method: 'random' | 'systematic' | 'judgmental' | 'mus' | 'full' | ''
  methodNote: string
  criteriaNote: string
  /** 样本选取过程简述（如 IDEA / Excel） */
  processNote: string
  /** 误受风险 %：1 / 5 / 10（对应扩展系数表） */
  riskOfIncorrectAcceptance: 1 | 5 | 10
  /** 可容忍错报（用于建议样本量） */
  tolerableMisstatement: number
}

export const DEFAULT_G2_SAMPLING_PLAN: G2VoucherSamplingPlan = {
  populationDebit: 0,
  populationCredit: 0,
  populationCount: 0,
  amountThreshold: '',
  includeRelatedParty: true,
  method: 'random',
  methodNote: '',
  criteriaNote: '',
  processNote: '',
  riskOfIncorrectAcceptance: 5,
  tolerableMisstatement: 0,
}

export const G2_SAMPLING_METHOD_OPTIONS = [
  { value: 'full', label: '全部项目检查' },
  { value: 'judgmental', label: '选取特定项目（大额/关键）' },
  { value: 'random', label: '随机抽样' },
  { value: 'systematic', label: '系统抽样' },
  { value: 'mus', label: '货币单位抽样(MUS)' },
] as const

/** Excel 编制说明中的预计错报扩展系数 */
export const G2_EXPANSION_FACTORS = [
  { riskPct: 1, factor: 1.9 },
  { riskPct: 5, factor: 1.6 },
  { riskPct: 10, factor: 1.5 },
] as const

export const G2_CONCLUSION_TEMPLATES = {
  A: '经检查，未见异常。',
  B: '经检查，除已调整（或拟调整）事项外，未见其他异常。',
  C: '因重要项目无法获取充分、适当的审计证据（审计范围受限），无法对相关认定发表结论。',
} as const

interface CheckFlags {
  check1DocsComplete: boolean | null
  check2VoucherMatch: boolean | null
  check3Accounting: boolean | null
  check4Period: boolean | null
  check5InterestCalc: boolean | null
  supportingDocs: string
  indexRef: string
  isAbnormal: boolean
  abnormalDesc: string
}

interface StoredDebitCheckRow extends CheckFlags {
  id: string
  seq: number
  summary: string
  counterAccount: string
  amount: number
  voucherDate: string
  voucherNo: string
  investTarget: string
  faceValue: number
  rate: number
  accruedDays: number
  auditConclusion: string
  remark: string
  source?: string
}

export interface DebitCheckRow extends StoredDebitCheckRow {
  calculatedInterest: number
  variance: number
}

interface StoredCreditCheckRow extends CheckFlags {
  id: string
  seq: number
  summary: string
  counterAccount: string
  amount: number
  voucherDate: string
  voucherNo: string
  receivingBank: string
  receiptDate: string
  isOnTimeRecovery: string
  auditConclusion: string
  remark: string
  source?: string
}

export interface CreditCheckRow extends StoredCreditCheckRow {
  overdueDays: number
}

export interface DebitCheckTotals {
  amount: number
  calculatedInterest: number
  variance: number
}

export interface CreditCheckTotals {
  amount: number
  overdueCount: number
}

const DEBIT_STORAGE_KEY = 'G2-8-debit-check-rows'
const CREDIT_STORAGE_KEY = 'G2-8-credit-check-rows'
const PLAN_STORAGE_KEY = 'G2-8-sampling-plan'
/** 与后端 IE item_id 对齐的扁平导出键 */
const FLAT_STORAGE_KEY = 'G2-8-rows'

function generateDebitId(): string {
  return `dchk-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}
function generateCreditId(): string {
  return `cchk-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function emptyChecks(): CheckFlags {
  return {
    check1DocsComplete: null,
    check2VoucherMatch: null,
    check3Accounting: null,
    check4Period: null,
    check5InterestCalc: null,
    supportingDocs: '',
    indexRef: '',
    isAbnormal: false,
    abnormalDesc: '',
  }
}

function migrateChecks(raw: Partial<CheckFlags> | undefined): CheckFlags {
  const base = emptyChecks()
  if (!raw) return base
  return {
    ...base,
    ...raw,
    check1DocsComplete: raw.check1DocsComplete ?? null,
    check2VoucherMatch: raw.check2VoucherMatch ?? null,
    check3Accounting: raw.check3Accounting ?? null,
    check4Period: raw.check4Period ?? null,
    check5InterestCalc: raw.check5InterestCalc ?? null,
    isAbnormal: !!raw.isAbnormal || !!(raw.abnormalDesc && String(raw.abnormalDesc).trim()),
  }
}

function anyCheckFailed(flags: CheckFlags): boolean {
  return G2_VOUCHER_CHECK_ITEMS.some((item) => flags[item.key] === false)
}

function safeParseDebitRows(jsonStr: string | null | undefined): StoredDebitCheckRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    if (!Array.isArray(parsed)) return []
    return parsed.map((p: Partial<StoredDebitCheckRow>, i: number) => ({
      ...createEmptyDebitRow(i + 1),
      ...p,
      ...migrateChecks(p),
      id: p.id || generateDebitId(),
      seq: p.seq ?? i + 1,
    }))
  } catch {
    return []
  }
}

function safeParseCreditRows(jsonStr: string | null | undefined): StoredCreditCheckRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    if (!Array.isArray(parsed)) return []
    return parsed.map((p: Partial<StoredCreditCheckRow>, i: number) => ({
      ...createEmptyCreditRow(i + 1),
      ...p,
      ...migrateChecks(p),
      id: p.id || generateCreditId(),
      seq: p.seq ?? i + 1,
    }))
  } catch {
    return []
  }
}

function parsePlan(raw: string | null | undefined): G2VoucherSamplingPlan {
  if (!raw) return { ...DEFAULT_G2_SAMPLING_PLAN }
  try {
    return { ...DEFAULT_G2_SAMPLING_PLAN, ...JSON.parse(raw) }
  } catch {
    return { ...DEFAULT_G2_SAMPLING_PLAN }
  }
}

function computeDebitRow(stored: StoredDebitCheckRow): DebitCheckRow {
  const calculatedInterest = calcInterest365(stored.faceValue, stored.rate, stored.accruedDays)
  const variance = calculatedInterest - stored.amount
  const isAbnormal = stored.isAbnormal || anyCheckFailed(stored) || Math.abs(variance) >= 0.01
  return { ...stored, calculatedInterest, variance, isAbnormal }
}

function computeCreditRow(stored: StoredCreditCheckRow): CreditCheckRow {
  const overdueDays = stored.isOnTimeRecovery === '否' ? calcOverdueDays(stored.voucherDate) : 0
  const isAbnormal = stored.isAbnormal || anyCheckFailed(stored) || overdueDays > 0
  return { ...stored, overdueDays, isAbnormal }
}

function createEmptyDebitRow(seq: number): StoredDebitCheckRow {
  return {
    id: generateDebitId(),
    seq,
    summary: '',
    counterAccount: '',
    amount: 0,
    voucherDate: '',
    voucherNo: '',
    investTarget: '',
    faceValue: 0,
    rate: 0,
    accruedDays: 0,
    auditConclusion: '',
    remark: '',
    ...emptyChecks(),
  }
}

function createEmptyCreditRow(seq: number): StoredCreditCheckRow {
  return {
    id: generateCreditId(),
    seq,
    summary: '',
    counterAccount: '',
    amount: 0,
    voucherDate: '',
    voucherNo: '',
    receivingBank: '',
    receiptDate: '',
    isOnTimeRecovery: '',
    auditConclusion: '',
    remark: '',
    ...emptyChecks(),
  }
}

/** 检查比例 = 样本金额合计 / 总体金额；总体为 0 返回 null */
export function calcInspectionRatio(sampleAmount: number, populationAmount: number): number | null {
  if (!populationAmount || populationAmount === 0) return null
  return sampleAmount / populationAmount
}

/**
 * Excel 编制说明：样本规模 ≈ 账面价值 / (可容忍错报 / 扩展系数)
 * 即 n = ceil(BV × 扩展系数 / TM)；缺 TM 或总体时返回 null
 */
export function suggestSampleSizeByExpansion(
  populationAmount: number,
  tolerableMisstatement: number,
  riskPct: 1 | 5 | 10,
): number | null {
  if (!populationAmount || populationAmount <= 0) return null
  if (!tolerableMisstatement || tolerableMisstatement <= 0) return null
  const row = G2_EXPANSION_FACTORS.find((r) => r.riskPct === riskPct)
  const factor = row?.factor ?? 1.6
  return Math.ceil((populationAmount * factor) / tolerableMisstatement)
}

/** 异常行默认交叉索引至调整分录汇总 */
export const G2_ABNORMAL_INDEX_DEFAULT = 'G2-4'

export interface UseG2VoucherCheckOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}

export function useG2VoucherCheck(options: UseG2VoucherCheckOptions) {
  const { allResponses, isReadonly } = options
  const readonly = isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  const samplingPlan = ref<G2VoucherSamplingPlan>(
    parsePlan(allResponses.value.get(PLAN_STORAGE_KEY)?.remark),
  )

  watch(
    () => allResponses.value.get(PLAN_STORAGE_KEY)?.remark,
    (raw) => {
      if (raw == null) return
      const next = parsePlan(raw)
      // 避免自身 persist 回写造成抖动：序列化相等则跳过
      if (JSON.stringify(next) === JSON.stringify(samplingPlan.value)) return
      samplingPlan.value = next
    },
  )

  // ─── Debit ─────────────────────────────────────────────────────────────────

  const storedDebitRows = computed<StoredDebitCheckRow[]>(() =>
    safeParseDebitRows(allResponses.value.get(DEBIT_STORAGE_KEY)?.remark),
  )
  const debitRows: ComputedRef<DebitCheckRow[]> = computed(() =>
    storedDebitRows.value.map((s) => computeDebitRow(s)),
  )
  const debitTotals: ComputedRef<DebitCheckTotals> = computed(() => {
    const rows = debitRows.value
    return {
      amount: rows.reduce((sum, r) => sum + r.amount, 0),
      calculatedInterest: rows.reduce((sum, r) => sum + r.calculatedInterest, 0),
      variance: rows.reduce((sum, r) => sum + r.variance, 0),
    }
  })

  function persistDebitRows(rows: StoredDebitCheckRow[]): void {
    const json = JSON.stringify(rows)
    allResponses.value.set(DEBIT_STORAGE_KEY, { item_id: DEBIT_STORAGE_KEY, conclusion: null, remark: json })
    persistFlatExport()
    debounceSave()
  }

  function addDebitRow(): void {
    if (readonly.value) return
    const current = safeParseDebitRows(allResponses.value.get(DEBIT_STORAGE_KEY)?.remark)
    const nextSeq = current.length > 0 ? Math.max(...current.map((r) => r.seq)) + 1 : 1
    current.push(createEmptyDebitRow(nextSeq))
    persistDebitRows(current)
  }

  function removeDebitRow(id: string): void {
    if (readonly.value) return
    const current = safeParseDebitRows(allResponses.value.get(DEBIT_STORAGE_KEY)?.remark)
    const filtered = current.filter((r) => r.id !== id)
    filtered.forEach((r, i) => { r.seq = i + 1 })
    persistDebitRows(filtered)
  }

  function updateDebitCell(rowId: string, field: keyof StoredDebitCheckRow, value: string | number | boolean | null): void {
    if (readonly.value) return
    const current = safeParseDebitRows(allResponses.value.get(DEBIT_STORAGE_KEY)?.remark)
    const idx = current.findIndex((r) => r.id === rowId)
    if (idx === -1) return
    const numericFields = ['amount', 'faceValue', 'rate', 'accruedDays'] as const
    if ((numericFields as readonly string[]).includes(field as string)) {
      ;(current[idx] as any)[field] = typeof value === 'number' ? value : parseNum(value)
    } else {
      ;(current[idx] as any)[field] = value
    }
    if (field === 'abnormalDesc' && value) current[idx].isAbnormal = true
    if (G2_VOUCHER_CHECK_ITEMS.some((c) => c.key === field) && value === false) {
      current[idx].isAbnormal = true
    }
    persistDebitRows(current)
  }

  function setDebitCheck(rowId: string, key: G2CheckKey, passed: boolean): void {
    updateDebitCell(rowId, key, passed)
  }

  function insertDebitSamples(samples: Partial<StoredDebitCheckRow>[]): void {
    if (readonly.value) return
    const current = safeParseDebitRows(allResponses.value.get(DEBIT_STORAGE_KEY)?.remark)
    let nextSeq = current.length > 0 ? Math.max(...current.map((r) => r.seq)) + 1 : 1
    for (const sample of samples) {
      current.push({
        ...createEmptyDebitRow(nextSeq),
        ...sample,
        ...migrateChecks(sample),
        id: generateDebitId(),
        seq: nextSeq,
      })
      nextSeq++
    }
    persistDebitRows(current)
  }

  // ─── Credit ────────────────────────────────────────────────────────────────

  const storedCreditRows = computed<StoredCreditCheckRow[]>(() =>
    safeParseCreditRows(allResponses.value.get(CREDIT_STORAGE_KEY)?.remark),
  )
  const creditRows: ComputedRef<CreditCheckRow[]> = computed(() =>
    storedCreditRows.value.map((s) => computeCreditRow(s)),
  )
  const creditTotals: ComputedRef<CreditCheckTotals> = computed(() => {
    const rows = creditRows.value
    return {
      amount: rows.reduce((sum, r) => sum + r.amount, 0),
      overdueCount: rows.filter((r) => r.overdueDays > 0).length,
    }
  })

  function persistCreditRows(rows: StoredCreditCheckRow[]): void {
    const json = JSON.stringify(rows)
    allResponses.value.set(CREDIT_STORAGE_KEY, { item_id: CREDIT_STORAGE_KEY, conclusion: null, remark: json })
    persistFlatExport()
    debounceSave()
  }

  function addCreditRow(): void {
    if (readonly.value) return
    const current = safeParseCreditRows(allResponses.value.get(CREDIT_STORAGE_KEY)?.remark)
    const nextSeq = current.length > 0 ? Math.max(...current.map((r) => r.seq)) + 1 : 1
    current.push(createEmptyCreditRow(nextSeq))
    persistCreditRows(current)
  }

  function removeCreditRow(id: string): void {
    if (readonly.value) return
    const current = safeParseCreditRows(allResponses.value.get(CREDIT_STORAGE_KEY)?.remark)
    const filtered = current.filter((r) => r.id !== id)
    filtered.forEach((r, i) => { r.seq = i + 1 })
    persistCreditRows(filtered)
  }

  function updateCreditCell(rowId: string, field: keyof StoredCreditCheckRow, value: string | number | boolean | null): void {
    if (readonly.value) return
    const current = safeParseCreditRows(allResponses.value.get(CREDIT_STORAGE_KEY)?.remark)
    const idx = current.findIndex((r) => r.id === rowId)
    if (idx === -1) return
    if (field === 'amount') {
      current[idx].amount = typeof value === 'number' ? value : parseNum(value)
    } else {
      ;(current[idx] as any)[field] = value
    }
    if (field === 'abnormalDesc' && value) current[idx].isAbnormal = true
    if (G2_VOUCHER_CHECK_ITEMS.some((c) => c.key === field) && value === false) {
      current[idx].isAbnormal = true
    }
    persistCreditRows(current)
  }

  function setCreditCheck(rowId: string, key: G2CheckKey, passed: boolean): void {
    updateCreditCell(rowId, key, passed)
  }

  function insertCreditSamples(samples: Partial<StoredCreditCheckRow>[]): void {
    if (readonly.value) return
    const current = safeParseCreditRows(allResponses.value.get(CREDIT_STORAGE_KEY)?.remark)
    let nextSeq = current.length > 0 ? Math.max(...current.map((r) => r.seq)) + 1 : 1
    for (const sample of samples) {
      current.push({
        ...createEmptyCreditRow(nextSeq),
        ...sample,
        ...migrateChecks(sample),
        id: generateCreditId(),
        seq: nextSeq,
      })
      nextSeq++
    }
    persistCreditRows(current)
  }

  // ─── Sampling plan & ratio ─────────────────────────────────────────────────

  function persistPlan(): void {
    if (readonly.value) return
    const json = JSON.stringify(samplingPlan.value)
    allResponses.value.set(PLAN_STORAGE_KEY, { item_id: PLAN_STORAGE_KEY, conclusion: null, remark: json })
    debounceSave()
  }

  function updateSamplingPlan(patch: Partial<G2VoucherSamplingPlan>): void {
    if (readonly.value) return
    samplingPlan.value = { ...samplingPlan.value, ...patch }
    persistPlan()
  }

  /** 从 G2-2 明细借贷发生额预填总体（有数时才覆盖） */
  function seedPopulationFromDetail(force = false): void {
    if (readonly.value) return
    const raw = allResponses.value.get('G2-2-detail-rows')?.remark
    if (!raw) return
    try {
      const rows = JSON.parse(raw)
      if (!Array.isArray(rows) || !rows.length) return
      let debit = 0
      let credit = 0
      for (const r of rows) {
        debit += parseNum(r.debit)
        credit += parseNum(r.credit)
      }
      const plan = samplingPlan.value
      if (force || !plan.populationDebit) plan.populationDebit = debit
      if (force || !plan.populationCredit) plan.populationCredit = credit
      if (force || !plan.populationCount) plan.populationCount = rows.length
      samplingPlan.value = { ...plan }
      persistPlan()
    } catch { /* ignore */ }
  }

  const sampleAmountTotal = computed(
    () => debitTotals.value.amount + creditTotals.value.amount,
  )
  const populationAmount = computed(
    () => samplingPlan.value.populationDebit + samplingPlan.value.populationCredit,
  )
  const inspectionRatio = computed(() =>
    calcInspectionRatio(sampleAmountTotal.value, populationAmount.value),
  )

  const suggestedSampleSize = computed(() =>
    suggestSampleSizeByExpansion(
      populationAmount.value,
      samplingPlan.value.tolerableMisstatement,
      samplingPlan.value.riskOfIncorrectAcceptance || 5,
    ),
  )

  const abnormalCount = computed(
    () =>
      debitRows.value.filter((r) => r.isAbnormal).length
      + creditRows.value.filter((r) => r.isAbnormal).length,
  )

  const pendingCheckCount = computed(() => {
    const pending = (r: CheckFlags) =>
      G2_VOUCHER_CHECK_ITEMS.some((item) => r[item.key] === null)
    return (
      debitRows.value.filter(pending).length
      + creditRows.value.filter(pending).length
    )
  })

  /** 将异常行索引号统一填为 G2-4（已有索引则保留） */
  function fillAbnormalIndexToAdjustment(force = false): number {
    if (readonly.value) return 0
    let n = 0
    const debit = safeParseDebitRows(allResponses.value.get(DEBIT_STORAGE_KEY)?.remark)
    for (const r of debit) {
      const row = computeDebitRow(r)
      if (!row.isAbnormal) continue
      if (!force && r.indexRef) continue
      r.indexRef = G2_ABNORMAL_INDEX_DEFAULT
      n++
    }
    if (n) persistDebitRows(debit)

    let m = 0
    const credit = safeParseCreditRows(allResponses.value.get(CREDIT_STORAGE_KEY)?.remark)
    for (const r of credit) {
      const row = computeCreditRow(r)
      if (!row.isAbnormal) continue
      if (!force && r.indexRef) continue
      r.indexRef = G2_ABNORMAL_INDEX_DEFAULT
      m++
    }
    if (m) persistCreditRows(credit)
    return n + m
  }

  /** 抽凭引擎样本按借贷方向分配 */
  function applySamplingResults(samples: SampledVoucher[], fillMode: FillMode = 'append'): void {
    if (readonly.value) return
    const debitSamples: Partial<StoredDebitCheckRow>[] = []
    const creditSamples: Partial<StoredCreditCheckRow>[] = []
    for (const s of samples) {
      const debitAmt = parseNum(s.debitAmount)
      const creditAmt = parseNum(s.creditAmount)
      const common = {
        summary: s.summary || '',
        voucherDate: s.voucherDate || '',
        voucherNo: s.voucherNo || '',
        source: `抽凭${s.selectionReason ? ` · ${s.selectionReason}` : ''}`,
        isAbnormal: !!s.abnormal,
        abnormalDesc: s.abnormal ? (s.remark || '抽凭标记异常') : '',
        remark: s.remark || '',
      }
      if (creditAmt > 0 && debitAmt <= 0) {
        creditSamples.push({
          ...common,
          amount: creditAmt,
          counterAccount: s.counterpartAccount || '',
        })
      } else {
        debitSamples.push({
          ...common,
          amount: debitAmt || creditAmt,
          counterAccount: s.counterpartAccount || '',
        })
      }
    }
    if (fillMode === 'replace') {
      persistDebitRows([])
      persistCreditRows([])
    }
    if (debitSamples.length) insertDebitSamples(debitSamples)
    if (creditSamples.length) insertCreditSamples(creditSamples)
  }

  // ─── Persist batch ─────────────────────────────────────────────────────────

  /** 扁平化写入 G2-8-rows，供后端导入导出 round-trip */
  function persistFlatExport(): void {
    if (readonly.value) return
    const debit = safeParseDebitRows(allResponses.value.get(DEBIT_STORAGE_KEY)?.remark)
    const credit = safeParseCreditRows(allResponses.value.get(CREDIT_STORAGE_KEY)?.remark)
    const flat: Record<string, unknown>[] = []
    for (const r of debit) {
      const calc = calcInterest365(r.faceValue, r.rate, r.accruedDays)
      flat.push({
        seq: r.seq,
        checkZone: 'debit',
        summary: r.summary,
        counterAccount: r.counterAccount,
        amount: r.amount,
        voucherDate: r.voucherDate,
        voucherNo: r.voucherNo,
        investTarget: r.investTarget,
        faceValue: r.faceValue,
        rate: r.rate,
        accruedDays: r.accruedDays,
        calculatedInterest: calc,
        receivingBank: '',
        receiptDate: '',
        isOnTimeRecovery: '',
        overdueDays: 0,
        variance: calc - r.amount,
        auditConclusion: r.auditConclusion,
        attachment: r.supportingDocs,
        remark: r.remark,
        sampleSource: r.source || '',
        check1DocsComplete: r.check1DocsComplete,
        check2VoucherMatch: r.check2VoucherMatch,
        check3Accounting: r.check3Accounting,
        check4Period: r.check4Period,
        check5InterestCalc: r.check5InterestCalc,
        indexRef: r.indexRef,
        isAbnormal: r.isAbnormal,
        abnormalDesc: r.abnormalDesc,
        id: r.id,
      })
    }
    for (const r of credit) {
      const overdueDays = r.isOnTimeRecovery === '否' ? calcOverdueDays(r.voucherDate) : 0
      flat.push({
        seq: r.seq,
        checkZone: 'credit',
        summary: r.summary,
        counterAccount: r.counterAccount,
        amount: r.amount,
        voucherDate: r.voucherDate,
        voucherNo: r.voucherNo,
        investTarget: '',
        faceValue: 0,
        rate: 0,
        accruedDays: 0,
        calculatedInterest: 0,
        receivingBank: r.receivingBank,
        receiptDate: r.receiptDate,
        isOnTimeRecovery: r.isOnTimeRecovery,
        overdueDays,
        variance: 0,
        auditConclusion: r.auditConclusion,
        attachment: r.supportingDocs,
        remark: r.remark,
        sampleSource: r.source || '',
        check1DocsComplete: r.check1DocsComplete,
        check2VoucherMatch: r.check2VoucherMatch,
        check3Accounting: r.check3Accounting,
        check4Period: r.check4Period,
        check5InterestCalc: r.check5InterestCalc,
        indexRef: r.indexRef,
        isAbnormal: r.isAbnormal,
        abnormalDesc: r.abnormalDesc,
        id: r.id,
      })
    }
    const json = JSON.stringify(flat)
    allResponses.value.set(FLAT_STORAGE_KEY, {
      item_id: FLAT_STORAGE_KEY,
      conclusion: null,
      remark: json,
    })
  }

  /** 从扁平 G2-8-rows 还原借/贷区（导入后调用） */
  function hydrateFromFlat(flatRaw: string | null | undefined): boolean {
    if (!flatRaw) return false
    try {
      const flat = JSON.parse(flatRaw)
      if (!Array.isArray(flat) || !flat.length) return false
      const debit: StoredDebitCheckRow[] = []
      const credit: StoredCreditCheckRow[] = []
      for (const row of flat) {
        const zone = String(row.checkZone || row.zone || '').toLowerCase()
        if (zone === 'credit' || zone === '贷方') {
          credit.push({
            ...createEmptyCreditRow(credit.length + 1),
            id: String(row.id || generateCreditId()),
            seq: Number(row.seq) || credit.length + 1,
            summary: String(row.summary || ''),
            counterAccount: String(row.counterAccount || ''),
            amount: parseNum(row.amount),
            voucherDate: String(row.voucherDate || ''),
            voucherNo: String(row.voucherNo || ''),
            receivingBank: String(row.receivingBank || ''),
            receiptDate: String(row.receiptDate || ''),
            isOnTimeRecovery: String(row.isOnTimeRecovery || ''),
            auditConclusion: String(row.auditConclusion || ''),
            remark: String(row.remark || ''),
            source: String(row.sampleSource || row.source || ''),
            ...migrateChecks(row),
            supportingDocs: String(row.attachment || row.supportingDocs || ''),
            indexRef: String(row.indexRef || ''),
          })
        } else {
          debit.push({
            ...createEmptyDebitRow(debit.length + 1),
            id: String(row.id || generateDebitId()),
            seq: Number(row.seq) || debit.length + 1,
            summary: String(row.summary || ''),
            counterAccount: String(row.counterAccount || ''),
            amount: parseNum(row.amount),
            voucherDate: String(row.voucherDate || ''),
            voucherNo: String(row.voucherNo || ''),
            investTarget: String(row.investTarget || ''),
            faceValue: parseNum(row.faceValue),
            rate: parseNum(row.rate),
            accruedDays: parseNum(row.accruedDays),
            auditConclusion: String(row.auditConclusion || ''),
            remark: String(row.remark || ''),
            source: String(row.sampleSource || row.source || ''),
            ...migrateChecks(row),
            supportingDocs: String(row.attachment || row.supportingDocs || ''),
            indexRef: String(row.indexRef || ''),
          })
        }
      }
      debit.forEach((r, i) => { r.seq = i + 1 })
      credit.forEach((r, i) => { r.seq = i + 1 })
      allResponses.value.set(DEBIT_STORAGE_KEY, {
        item_id: DEBIT_STORAGE_KEY,
        conclusion: null,
        remark: JSON.stringify(debit),
      })
      allResponses.value.set(CREDIT_STORAGE_KEY, {
        item_id: CREDIT_STORAGE_KEY,
        conclusion: null,
        remark: JSON.stringify(credit),
      })
      allResponses.value.set(FLAT_STORAGE_KEY, {
        item_id: FLAT_STORAGE_KEY,
        conclusion: null,
        remark: JSON.stringify(flat),
      })
      debounceSave()
      return true
    } catch {
      return false
    }
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
      persistFlatExport()
      const items = [
        allResponses.value.get(DEBIT_STORAGE_KEY),
        allResponses.value.get(CREDIT_STORAGE_KEY),
        allResponses.value.get(PLAN_STORAGE_KEY),
        allResponses.value.get(FLAT_STORAGE_KEY),
      ].filter(Boolean)
      window.dispatchEvent(new CustomEvent('g2:save-items', { detail: { items } }))
    } catch { /* silent */ }
  }

  // 仅在组件 setup 内注册生命周期，避免单测/非组件调用告警
  if (getCurrentInstance()) {
    onBeforeUnmount(() => {
      if (debounceTimer) {
        clearTimeout(debounceTimer)
        debounceTimer = null
        flushSave()
      }
    })
  }

  return {
    CHECK_ITEMS: G2_VOUCHER_CHECK_ITEMS,
    samplingPlan,
    updateSamplingPlan,
    seedPopulationFromDetail,
    inspectionRatio,
    suggestedSampleSize,
    sampleAmountTotal,
    populationAmount,
    abnormalCount,
    pendingCheckCount,
    fillAbnormalIndexToAdjustment,
    debitRows,
    debitTotals,
    addDebitRow,
    removeDebitRow,
    updateDebitCell,
    setDebitCheck,
    insertDebitSamples,
    creditRows,
    creditTotals,
    addCreditRow,
    removeCreditRow,
    updateCreditCell,
    setCreditCheck,
    insertCreditSamples,
    applySamplingResults,
    hydrateFromFlat,
    persistFlatExport,
    FLAT_STORAGE_KEY,
  }
}

export default useG2VoucherCheck
