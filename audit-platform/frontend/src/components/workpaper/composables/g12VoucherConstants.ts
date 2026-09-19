/** G12-6 凭证检查 — 核对项与抽样（对齐 Excel「样本选取方法与规模」+ CAS24 套期会计） */

export const G12_VOUCHER_CHECK_DEFS = [
  { key: 'check1OriginalComplete', label: '①完整', title: '原始凭证内容完整' },
  { key: 'check2Authorization', label: '②授权', title: '授权批准恰当' },
  { key: 'check3Accounting', label: '③账务', title: '账务处理正确' },
  { key: 'check4HedgeDesignation', label: '④指定', title: '套期指定文档齐备' },
  { key: 'check5HedgeAccounting', label: '⑤套期', title: '符合套期会计要求（CAS24）' },
  { key: 'check6FVValuation', label: '⑥公允', title: '公允价值计量符合准则' },
] as const

export type G12VoucherCheckKey = (typeof G12_VOUCHER_CHECK_DEFS)[number]['key']

/** null=未测 / true=通过 / false=不通过 */
export type G12CheckState = boolean | null

export const G12_CHECK_STATE_OPTIONS = [
  { value: 'null', label: '未测' },
  { value: 'true', label: '通过' },
  { value: 'false', label: '不通过' },
] as const

export function parseG12CheckState(v: unknown): G12CheckState {
  if (v === null || v === undefined || v === '') return null
  if (v === true || v === 1) return true
  if (v === false || v === 0) return false
  const s = String(v).trim().toLowerCase()
  if (!s || s === '未测' || s === 'n/a' || s === 'na' || s === '-' || s === '—' || s === 'null') return null
  if (s === 'true' || s === '是' || s === 'yes' || s === 'y' || s === '✓' || s === '√' || s === '通过') return true
  if (s === 'false' || s === '否' || s === 'no' || s === 'n' || s === '✗' || s === '×' || s === '不通过') return false
  return null
}

export function formatG12CheckState(v: G12CheckState): string {
  if (v === true) return '✓'
  if (v === false) return '✗'
  return '未测'
}

export function g12CheckSelectValue(v: G12CheckState): string {
  if (v === true) return 'true'
  if (v === false) return 'false'
  return 'null'
}

export function parseG12CheckSelect(v: string): G12CheckState {
  if (v === 'true') return true
  if (v === 'false') return false
  return null
}

export const G12_SAMPLING_METHOD_OPTIONS = [
  { value: 'random', label: '随机抽样' },
  { value: 'systematic', label: '系统抽样' },
  { value: 'judgmental', label: '判断抽样' },
  { value: 'mus', label: '货币单位抽样(MUS)' },
  { value: 'full', label: '全部项目检查' },
] as const

export function formatG12SamplingMethodLabel(value: string): string {
  const s = String(value ?? '').trim()
  if (!s) return '—'
  const hit = G12_SAMPLING_METHOD_OPTIONS.find((o) => o.value === s || o.label === s)
  return hit?.label ?? s
}

function normalizeG12SamplingMethod(raw: unknown): string {
  const s = String(raw ?? '').trim()
  if (!s) return ''
  const exact = G12_SAMPLING_METHOD_OPTIONS.find((o) => o.value === s || o.label === s)
  if (exact) return exact.value
  if (/随机/.test(s)) return 'random'
  if (/系统/.test(s)) return 'systematic'
  if (/判断|特定/.test(s)) return 'judgmental'
  if (/MUS|货币单位/i.test(s)) return 'mus'
  if (/全部|全查/.test(s)) return 'full'
  return s
}

export const G12_SAMPLE_EXPANSION_FACTORS: Record<string, number> = {
  '0.01': 1.9,
  '0.05': 1.6,
  '0.10': 1.5,
}

export interface G12SamplingParams {
  testPopulation: string
  specificSamples: string
  samplingPopulation: string
  samplingMethod: string
  samplingProcess: string
  targetSampleSize: number
  populationCount: number
  /** 本期发生额（总体金额），用于检查比例分母 */
  populationAmount: number
  bookValue: number
  riskFactor: number
  tolerableMisstatement: number
  expectedMisstatement: number
  riskOfIncorrectAcceptance: 1 | 5 | 10
}

export function defaultG12SamplingParams(): G12SamplingParams {
  return {
    testPopulation: '',
    specificSamples: '',
    samplingPopulation: '',
    samplingMethod: '',
    samplingProcess: '',
    targetSampleSize: 0,
    populationCount: 0,
    populationAmount: 0,
    bookValue: 0,
    riskFactor: 1,
    tolerableMisstatement: 0,
    expectedMisstatement: 0,
    riskOfIncorrectAcceptance: 5,
  }
}

export function parseG12SamplingParams(json: string | null | undefined): G12SamplingParams {
  const defaults = defaultG12SamplingParams()
  if (!json) return defaults
  try {
    const raw = JSON.parse(json)
    if (!raw || typeof raw !== 'object') return defaults
    const risk = Number(raw.riskOfIncorrectAcceptance)
    return {
      testPopulation: String(raw.testPopulation ?? ''),
      specificSamples: String(raw.specificSamples ?? ''),
      samplingPopulation: String(raw.samplingPopulation ?? ''),
      samplingMethod: normalizeG12SamplingMethod(raw.samplingMethod),
      samplingProcess: String(raw.samplingProcess ?? ''),
      targetSampleSize: Number(raw.targetSampleSize) || 0,
      populationCount: Number(raw.populationCount) || 0,
      populationAmount: Number(raw.populationAmount) || 0,
      bookValue: Number(raw.bookValue) || 0,
      riskFactor: Number(raw.riskFactor) || 1,
      tolerableMisstatement: Number(raw.tolerableMisstatement) || 0,
      expectedMisstatement: Number(raw.expectedMisstatement) || 0,
      riskOfIncorrectAcceptance: ([1, 5, 10] as const).includes(risk as 1 | 5 | 10)
        ? (risk as 1 | 5 | 10)
        : defaults.riskOfIncorrectAcceptance,
    }
  } catch {
    return defaults
  }
}

export function g12ExpansionFactor(risk: 1 | 5 | 10): number {
  return G12_SAMPLE_EXPANSION_FACTORS[String(risk / 100)] ?? 1.6
}

export function calcG12AuditSampleSize(opts: {
  bookValue: number
  riskFactor: number
  tolerableMisstatement: number
  expectedMisstatement: number
  expansionFactor: number
}): number {
  const denom = opts.tolerableMisstatement - opts.expectedMisstatement * opts.expansionFactor
  if (denom <= 0.005 || opts.bookValue <= 0) return 0
  return Math.max(1, Math.ceil((opts.bookValue * opts.riskFactor) / denom))
}

export function calcG12SuggestedSampleSize(params: G12SamplingParams): number | null {
  const bookValue = params.bookValue || params.populationAmount
  if (bookValue <= 0 || params.tolerableMisstatement <= 0) return null
  return calcG12AuditSampleSize({
    bookValue,
    riskFactor: params.riskFactor || 1,
    tolerableMisstatement: params.tolerableMisstatement,
    expectedMisstatement: params.expectedMisstatement,
    expansionFactor: g12ExpansionFactor(params.riskOfIncorrectAcceptance),
  })
}

/** 检查比例 = 已查样本金额 ÷ 本期发生额 */
export function g12VoucherInspectionRatio(sampledAmount: number, populationAmount: number): number | null {
  if (populationAmount <= 0.005) return null
  return sampledAmount / populationAmount
}

export function calcG12SampleAbsAmount(rows: Array<{ debitAmount?: number; creditAmount?: number }>): number {
  return rows.reduce((s, r) => {
    const amt = Math.max(Math.abs(Number(r.debitAmount) || 0), Math.abs(Number(r.creditAmount) || 0))
    return s + amt
  }, 0)
}

/** 检查比例低于此阈值时提示扩样 */
export const G12_LOW_INSPECTION_RATIO = 0.3
