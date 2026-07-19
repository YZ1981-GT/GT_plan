/**
 * useG1VoucherCheck — G1-13 交易性金融资产检查表
 *
 * 对齐 Excel《交易性金融资产检查表 G1-13》：
 * 目标 → 抽样计划 → 本期发生额检查 / 期后处置新售 → 六项核对 → 检查比例 → 说明/结论
 *
 * 保留：抽凭引擎填入、OCR 附件、旧行字段迁移
 */
import { ref, computed, watch, type Ref } from 'vue'
import { parseNum, calcSubtotal } from './useG1TraFinFormulaEngine'
import type { ChecklistResponse } from './useF1FormData'
import type { SampledVoucher, FillMode } from './useSamplingAlgorithms'

export type G1VoucherPeriod = 'current' | 'subsequent'
export type G1VoucherTab = 'basic' | 'check' | 'result'

/** 六项核对说明（Excel 红色提示 1–6） */
export const G1_VOUCHER_CHECK_ITEMS = [
  { key: 'check1DocsComplete', label: '①原始单据齐全', hint: '合同、交割单、银行回单、审批单等' },
  { key: 'check2VoucherMatch', label: '②凭证与单据相符', hint: '记账凭证与原始单据金额、内容一致' },
  { key: 'check3Accounting', label: '③账务处理正确', hint: '科目、方向、金额符合准则' },
  { key: 'check4Period', label: '④期间正确', hint: '记入正确会计期间（截止测试）' },
  { key: 'check5FairValue', label: '⑤公允价值计量正确', hint: '估值/市价取数与入账一致' },
  { key: 'check6Approval', label: '⑥授权审批恰当', hint: '投资决策与支付授权完整' },
] as const

export type G1CheckKey = (typeof G1_VOUCHER_CHECK_ITEMS)[number]['key']

export interface G1VoucherSamplingPlan {
  /** 测试总体 — 借方发生额 */
  populationDebit: number
  /** 测试总体 — 贷方发生额 */
  populationCredit: number
  /** 测试总体 — 笔数 */
  populationCount: number
  /** 金额门槛说明，如「单笔 50 万以上」 */
  amountThreshold: string
  /** 是否覆盖全部关联方 */
  includeRelatedParty: boolean
  /** 抽样方法 */
  method: 'random' | 'systematic' | 'judgmental' | 'mus' | ''
  methodNote: string
  criteriaNote: string
}

export interface G1VoucherCheckRow {
  id: string
  seq: number
  /** 本期发生额 / 期后处置新售 */
  period: G1VoucherPeriod
  voucherDate: string
  voucherNo: string
  businessContent: string
  debitAccount: string
  creditAccount: string
  debitAmount: number
  creditAmount: number
  /** 兼容旧「金额」列 = max(借,贷) */
  amount: number
  supportingDocs: string
  check1DocsComplete: boolean | null
  check2VoucherMatch: boolean | null
  check3Accounting: boolean | null
  check4Period: boolean | null
  check5FairValue: boolean | null
  check6Approval: boolean | null
  indexRef: string
  isAbnormal: boolean
  abnormalDesc: string
  remark: string
  attachment: string
  sampleSource: string
  // 旧字段兼容（导入/测试）
  summary: string
  securityName: string
  investType: string
  counterAccount: string
  contractCheck: string
  settlementCheck: string
  quoteCheck: string
  approvalCheck: string
  bookkeepingCheck: string
  auditConclusion: string
}

export interface G1VoucherCheckColumn {
  prop: keyof G1VoucherCheckRow
  label: string
  width: number
  type: 'text' | 'number'
}

/** 兼容集成测试：仍导出「核对列」名（映射到新六项 + 结论） */
export const G1_VOUCHER_CHECK_COLUMNS: G1VoucherCheckColumn[] = [
  { prop: 'seq', label: '序号', width: 60, type: 'number' },
  { prop: 'voucherDate', label: '凭证日期', width: 120, type: 'text' },
  { prop: 'voucherNo', label: '凭证号', width: 110, type: 'text' },
  { prop: 'amount', label: '金额', width: 120, type: 'number' },
  { prop: 'contractCheck', label: '合同核对', width: 110, type: 'text' },
  { prop: 'settlementCheck', label: '结算单核对', width: 120, type: 'text' },
  { prop: 'quoteCheck', label: '报价/估值核对', width: 130, type: 'text' },
  { prop: 'approvalCheck', label: '授权审批核对', width: 130, type: 'text' },
  { prop: 'bookkeepingCheck', label: '账务处理核对', width: 130, type: 'text' },
  { prop: 'auditConclusion', label: '审计结论', width: 140, type: 'text' },
]

const DATA_KEY = 'G1-13-rows'
const PLAN_KEY = 'G1-13-sampling-plan'
const CONCLUSION_KEY = 'G1-13-conclusion'

export const DEFAULT_SAMPLING_PLAN: G1VoucherSamplingPlan = {
  populationDebit: 0,
  populationCredit: 0,
  populationCount: 0,
  amountThreshold: '',
  includeRelatedParty: true,
  method: 'random',
  methodNote: '',
  criteriaNote: '',
}

export const G1_SAMPLING_METHOD_OPTIONS = [
  { value: 'random', label: '随机抽样' },
  { value: 'systematic', label: '系统抽样' },
  { value: 'judgmental', label: '判断抽样' },
  { value: 'mus', label: '货币单位抽样(MUS)' },
] as const

function genId(): string {
  return `g1v-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`
}

function toTriBool(v: unknown): boolean | null {
  if (v === true || v === '✓' || v === '是' || v === 'yes' || v === 'Y' || v === '1' || v === 'true') return true
  if (v === false || v === '✗' || v === '否' || v === 'no' || v === 'N' || v === '0' || v === 'false') return false
  if (v === null || v === undefined || v === '') return null
  // 旧文本「相符/无异常」视为通过
  const s = String(v).trim()
  if (!s) return null
  if (/不符|异常|错误|失败|否/.test(s)) return false
  return true
}

function checkToLegacy(v: boolean | null): string {
  if (v === true) return '相符'
  if (v === false) return '不符'
  return ''
}

/** 检查比例 = 样本金额 / 总体金额；总体为 0 时返回 null（避免 DIV/0） */
export function calcInspectionRatio(sampleAmount: number, populationAmount: number): number | null {
  const pop = parseNum(populationAmount)
  if (pop === 0) return null
  return parseNum(sampleAmount) / pop
}

export function enrichVoucherRow(raw: Partial<G1VoucherCheckRow> & { id?: string }, seq: number): G1VoucherCheckRow {
  const debit = parseNum(raw.debitAmount)
  const credit = parseNum(raw.creditAmount ?? (debit ? 0 : raw.amount))
  const amount = Math.max(debit, credit, parseNum(raw.amount))

  // 旧五列文本 → 六项布尔
  let c1 = toTriBool(raw.check1DocsComplete)
  let c2 = toTriBool(raw.check2VoucherMatch)
  let c3 = toTriBool(raw.check3Accounting ?? raw.bookkeepingCheck)
  let c4 = toTriBool(raw.check4Period)
  let c5 = toTriBool(raw.check5FairValue ?? raw.quoteCheck)
  let c6 = toTriBool(raw.check6Approval ?? raw.approvalCheck)
  if (c1 === null && raw.contractCheck != null && raw.contractCheck !== '') c1 = toTriBool(raw.contractCheck)
  if (c2 === null && raw.settlementCheck != null && raw.settlementCheck !== '') c2 = toTriBool(raw.settlementCheck)

  const checks = [c1, c2, c3, c4, c5, c6]
  const hasFail = checks.some((c) => c === false)
  let isAbnormal = raw.isAbnormal === true || raw.isAbnormal === ('是' as unknown)
  if (raw.isAbnormal === false || raw.isAbnormal === ('否' as unknown)) isAbnormal = false
  else if (hasFail) isAbnormal = true

  const businessContent = raw.businessContent || raw.summary || ''
  const counterAccount = raw.counterAccount || raw.creditAccount || raw.debitAccount || ''

  return {
    id: raw.id || genId(),
    seq,
    period: raw.period === 'subsequent' ? 'subsequent' : 'current',
    voucherDate: raw.voucherDate || '',
    voucherNo: raw.voucherNo || '',
    businessContent,
    debitAccount: raw.debitAccount || '',
    creditAccount: raw.creditAccount || '',
    debitAmount: debit,
    creditAmount: credit || (debit === 0 ? amount : 0),
    amount,
    supportingDocs: raw.supportingDocs || '',
    check1DocsComplete: c1,
    check2VoucherMatch: c2,
    check3Accounting: c3,
    check4Period: c4,
    check5FairValue: c5,
    check6Approval: c6,
    indexRef: raw.indexRef || '',
    isAbnormal,
    abnormalDesc: raw.abnormalDesc || '',
    remark: raw.remark || '',
    attachment: raw.attachment || '',
    sampleSource: raw.sampleSource || '',
    summary: businessContent,
    securityName: raw.securityName || '',
    investType: raw.investType || '',
    counterAccount,
    contractCheck: checkToLegacy(c1),
    settlementCheck: checkToLegacy(c2),
    quoteCheck: checkToLegacy(c5),
    approvalCheck: checkToLegacy(c6),
    bookkeepingCheck: checkToLegacy(c3),
    auditConclusion: raw.auditConclusion || (isAbnormal ? '异常' : hasFail ? '异常' : checks.every((c) => c === true) ? '无异常' : ''),
  }
}

function emptyRow(seq: number, period: G1VoucherPeriod = 'current'): G1VoucherCheckRow {
  return enrichVoucherRow({ period }, seq)
}

function loadRows(map: Map<string, ChecklistResponse>): G1VoucherCheckRow[] {
  const raw = map.get(DATA_KEY)?.conclusion || map.get(DATA_KEY)?.remark
  if (!raw) return [emptyRow(1, 'current'), emptyRow(1, 'subsequent')]
  try {
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed) || !parsed.length) return [emptyRow(1, 'current'), emptyRow(1, 'subsequent')]
    return parsed.map((p: Partial<G1VoucherCheckRow>, i: number) => enrichVoucherRow(p, i + 1))
  } catch {
    return [emptyRow(1, 'current'), emptyRow(1, 'subsequent')]
  }
}

function loadPlan(map: Map<string, ChecklistResponse>): G1VoucherSamplingPlan {
  const raw = map.get(PLAN_KEY)?.conclusion || map.get(PLAN_KEY)?.remark
  if (!raw) return { ...DEFAULT_SAMPLING_PLAN }
  try {
    return { ...DEFAULT_SAMPLING_PLAN, ...JSON.parse(raw) }
  } catch {
    return { ...DEFAULT_SAMPLING_PLAN }
  }
}

export function useG1VoucherCheck(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean>
}) {
  const rows = ref<G1VoucherCheckRow[]>(loadRows(opts.allResponses.value))
  const samplingPlan = ref<G1VoucherSamplingPlan>(loadPlan(opts.allResponses.value))
  const auditConclusion = ref(opts.allResponses.value.get(CONCLUSION_KEY)?.conclusion ?? '')
  const activePeriod = ref<G1VoucherPeriod>('current')
  const activeTab = ref<G1VoucherTab>('basic')

  function loadAll() {
    rows.value = loadRows(opts.allResponses.value)
    samplingPlan.value = loadPlan(opts.allResponses.value)
    auditConclusion.value = opts.allResponses.value.get(CONCLUSION_KEY)?.conclusion ?? ''
  }

  watch(
    () => opts.allResponses.value.get(DATA_KEY)?.conclusion,
    (raw) => {
      if (raw) rows.value = loadRows(opts.allResponses.value)
    },
  )

  const periodRows = computed(() =>
    rows.value.filter((r) => r.period === activePeriod.value),
  )

  const currentRows = computed(() => rows.value.filter((r) => r.period === 'current'))
  const subsequentRows = computed(() => rows.value.filter((r) => r.period === 'subsequent'))

  const sampleDebit = computed(() =>
    calcSubtotal(periodRows.value.map((r) => parseNum(r.debitAmount))),
  )
  const sampleCredit = computed(() =>
    calcSubtotal(periodRows.value.map((r) => parseNum(r.creditAmount))),
  )
  const sampleAmount = computed(() =>
    calcSubtotal(periodRows.value.map((r) => parseNum(r.amount))),
  )

  const populationAmount = computed(() => {
    const d = parseNum(samplingPlan.value.populationDebit)
    const c = parseNum(samplingPlan.value.populationCredit)
    return Math.max(d + c, d, c)
  })

  /** 检查比例；无总体时为 null */
  const inspectionRatio = computed(() =>
    calcInspectionRatio(sampleAmount.value, populationAmount.value),
  )

  const total = computed(() => calcSubtotal(rows.value.map((r) => parseNum(r.amount))))
  const abnormalCount = computed(() => rows.value.filter((r) => r.isAbnormal).length)
  const sampledCount = computed(() => rows.value.filter((r) => !!r.sampleSource).length)
  const pendingCheckCount = computed(() =>
    rows.value.filter((r) => {
      const checks = [
        r.check1DocsComplete, r.check2VoucherMatch, r.check3Accounting,
        r.check4Period, r.check5FairValue, r.check6Approval,
      ]
      return checks.some((c) => c === null) && (r.voucherNo || r.amount)
    }).length,
  )

  function persistAll() {
    if (opts.isReadonly.value) return
    const payload = JSON.stringify(rows.value)
    opts.debouncedSave(DATA_KEY, { conclusion: payload, remark: payload })
  }

  function persistPlan() {
    if (opts.isReadonly.value) return
    const payload = JSON.stringify(samplingPlan.value)
    opts.debouncedSave(PLAN_KEY, { conclusion: payload, remark: payload })
  }

  watch(auditConclusion, (v) => {
    if (!opts.isReadonly.value) opts.debouncedSave(CONCLUSION_KEY, { conclusion: v })
  })

  function updateSamplingPlan(patch: Partial<G1VoucherSamplingPlan>) {
    if (opts.isReadonly.value) return
    samplingPlan.value = { ...samplingPlan.value, ...patch }
    persistPlan()
  }

  function updateRow(id: string, patch: Partial<G1VoucherCheckRow>) {
    if (opts.isReadonly.value) return
    rows.value = rows.value.map((r) => {
      if (r.id !== id) return r
      return enrichVoucherRow({ ...r, ...patch, id: r.id }, r.seq)
    })
    persistAll()
  }

  function setCheck(id: string, key: G1CheckKey, value: boolean | null) {
    updateRow(id, { [key]: value } as Partial<G1VoucherCheckRow>)
  }

  function addRow(period?: G1VoucherPeriod) {
    if (opts.isReadonly.value) return
    const p = period || activePeriod.value
    const seq = rows.value.filter((r) => r.period === p).length + 1
    rows.value = [...rows.value, emptyRow(seq, p)].map((r, i) => ({ ...r, seq: i + 1 }))
    persistAll()
  }

  function removeRow(id: string) {
    if (opts.isReadonly.value) return
    const next = rows.value.filter((r) => r.id !== id)
    const cur = next.filter((r) => r.period === 'current')
    const sub = next.filter((r) => r.period === 'subsequent')
    if (!cur.length) cur.push(emptyRow(1, 'current'))
    if (!sub.length) sub.push(emptyRow(1, 'subsequent'))
    rows.value = [...cur, ...sub].map((r, i) => ({ ...r, seq: i + 1 }))
    persistAll()
  }

  function mapVoucherToRow(v: SampledVoucher, seq: number, period: G1VoucherPeriod = 'current'): G1VoucherCheckRow {
    const debit = v.debitAmount ? parseNum(v.debitAmount) : 0
    const credit = v.creditAmount ? parseNum(v.creditAmount) : 0
    return enrichVoucherRow(
      {
        period,
        voucherDate: v.voucherDate || '',
        voucherNo: v.voucherNo || '',
        businessContent: v.summary || '',
        debitAmount: debit,
        creditAmount: credit,
        amount: Math.max(debit, credit),
        counterAccount: v.counterpartAccount || '',
        creditAccount: v.counterpartAccount || '',
        sampleSource: '抽凭引擎',
      },
      seq,
    )
  }

  function mergeSamples(vouchers: SampledVoucher[], period: G1VoucherPeriod = 'current') {
    if (opts.isReadonly.value) return
    const mapped = vouchers.map((v, i) => mapVoucherToRow(v, rows.value.length + i + 1, period))
    rows.value = [...rows.value, ...mapped].map((r, i) => ({ ...r, seq: i + 1 }))
    persistAll()
  }

  function applySamplingResults(vouchers: SampledVoucher[], fillMode: FillMode) {
    if (opts.isReadonly.value) return
    const period = activePeriod.value
    if (fillMode === 'replace') {
      const other = rows.value.filter((r) => r.period !== period)
      const mapped = vouchers.length
        ? vouchers.map((v, i) => mapVoucherToRow(v, i + 1, period))
        : [emptyRow(1, period)]
      rows.value = [...other, ...mapped].map((r, i) => ({ ...r, seq: i + 1 }))
      persistAll()
      return
    }
    if (fillMode === 'merge') {
      const existingNos = new Set(rows.value.map((r) => r.voucherNo).filter(Boolean))
      const deduped = vouchers.filter((v) => !v.voucherNo || !existingNos.has(v.voucherNo))
      mergeSamples(deduped, period)
      return
    }
    mergeSamples(vouchers, period)
  }

  return {
    columns: G1_VOUCHER_CHECK_COLUMNS,
    rows,
    periodRows,
    currentRows,
    subsequentRows,
    samplingPlan,
    auditConclusion,
    activePeriod,
    activeTab,
    total,
    sampleDebit,
    sampleCredit,
    sampleAmount,
    populationAmount,
    inspectionRatio,
    abnormalCount,
    sampledCount,
    pendingCheckCount,
    loadAll,
    persistAll,
    updateSamplingPlan,
    updateRow,
    setCheck,
    addRow,
    removeRow,
    mergeSamples,
    applySamplingResults,
    mapVoucherToRow,
    CHECK_ITEMS: G1_VOUCHER_CHECK_ITEMS,
  }
}

export default useG1VoucherCheck
