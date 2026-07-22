/** G11-5 凭证检查 — 核对项与抽样（对齐 Excel「样本选取方法与规模」） */

export const G11_VOUCHER_CHECK_DEFS = [
  { key: 'check1', label: '①完整', title: '原始凭证是否完整' },
  { key: 'check2', label: '②授权', title: '记账凭证是否经过适当的批准' },
  { key: 'check3', label: '③金额', title: '投资收益金额的计算是否正确' },
  { key: 'check4', label: '④期间', title: '会计处理是否计入恰当的会计期间' },
  { key: 'check5', label: '⑤账务', title: '会计处理是否正确' },
] as const

export type G11VoucherCheckKey = (typeof G11_VOUCHER_CHECK_DEFS)[number]['key']

/** null=未测 / true=通过 / false=不通过 */
export type G11CheckState = boolean | null

export const G11_CHECK_STATE_OPTIONS = [
  { value: 'null', label: '未测' },
  { value: 'true', label: '通过' },
  { value: 'false', label: '不通过' },
] as const

export function parseG11CheckState(v: unknown): G11CheckState {
  if (v === null || v === undefined || v === '') return null
  if (v === true || v === 1) return true
  if (v === false || v === 0) return false
  const s = String(v).trim().toLowerCase()
  if (!s || s === '未测' || s === 'n/a' || s === 'na' || s === '-' || s === '—' || s === 'null') return null
  if (s === 'true' || s === '是' || s === 'yes' || s === 'y' || s === '✓' || s === '√' || s === '通过') return true
  if (s === 'false' || s === '否' || s === 'no' || s === 'n' || s === '✗' || s === '×' || s === '不通过') return false
  return null
}

export function formatG11CheckState(v: G11CheckState): string {
  if (v === true) return '✓'
  if (v === false) return '✗'
  return '未测'
}

export function g11CheckSelectValue(v: G11CheckState): string {
  if (v === true) return 'true'
  if (v === false) return 'false'
  return 'null'
}

export function parseG11CheckSelect(v: string): G11CheckState {
  if (v === 'true') return true
  if (v === 'false') return false
  return null
}

export const G11_SAMPLING_METHOD_OPTIONS = [
  { value: 'random', label: '随机抽样' },
  { value: 'systematic', label: '系统抽样' },
  { value: 'judgmental', label: '判断抽样' },
  { value: 'mus', label: '货币单位抽样(MUS)' },
  { value: 'full', label: '全部项目检查' },
] as const

export function formatG11SamplingMethodLabel(value: string): string {
  const s = String(value ?? '').trim()
  if (!s) return '—'
  const hit = G11_SAMPLING_METHOD_OPTIONS.find((o) => o.value === s || o.label === s)
  return hit?.label ?? s
}

function normalizeG11SamplingMethod(raw: unknown): string {
  const s = String(raw ?? '').trim()
  if (!s) return ''
  const exact = G11_SAMPLING_METHOD_OPTIONS.find((o) => o.value === s || o.label === s)
  if (exact) return exact.value
  if (/随机/.test(s)) return 'random'
  if (/系统/.test(s)) return 'systematic'
  if (/判断|特定/.test(s)) return 'judgmental'
  if (/MUS|货币单位/i.test(s)) return 'mus'
  if (/全部|全查/.test(s)) return 'full'
  return s
}

/** 误受风险 → 扩展系数 */
export const G11_SAMPLE_EXPANSION_FACTORS: Record<string, number> = {
  '0.01': 1.9,
  '0.05': 1.6,
  '0.10': 1.5,
}

export interface G11SamplingParams {
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

export function defaultG11SamplingParams(): G11SamplingParams {
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

export function parseG11SamplingParams(json: string | null | undefined): G11SamplingParams {
  const defaults = defaultG11SamplingParams()
  if (!json) return defaults
  try {
    const raw = JSON.parse(json)
    if (!raw || typeof raw !== 'object') return defaults
    const risk = Number(raw.riskOfIncorrectAcceptance)
    return {
      testPopulation: String(raw.testPopulation ?? ''),
      specificSamples: String(raw.specificSamples ?? ''),
      samplingPopulation: String(raw.samplingPopulation ?? ''),
      samplingMethod: normalizeG11SamplingMethod(raw.samplingMethod),
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

export function g11ExpansionFactor(risk: 1 | 5 | 10): number {
  return G11_SAMPLE_EXPANSION_FACTORS[String(risk / 100)] ?? 1.6
}

/** 样本量 = 账面价值×风险系数 / (可容忍错报 − 预计错报×扩展系数) */
export function calcG11AuditSampleSize(opts: {
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

export function calcG11SuggestedSampleSize(params: G11SamplingParams): number | null {
  const bookValue = params.bookValue || params.populationAmount
  if (bookValue <= 0 || params.tolerableMisstatement <= 0) return null
  return calcG11AuditSampleSize({
    bookValue,
    riskFactor: params.riskFactor || 1,
    tolerableMisstatement: params.tolerableMisstatement,
    expectedMisstatement: params.expectedMisstatement,
    expansionFactor: g11ExpansionFactor(params.riskOfIncorrectAcceptance),
  })
}

/** 检查比例 = 已查样本金额 ÷ 本期发生额（总体金额） */
export function g11VoucherInspectionRatio(sampledAmount: number, populationAmount: number): number | null {
  if (populationAmount <= 0.005) return null
  return sampledAmount / populationAmount
}

export function calcG11SampleAbsAmount(rows: Array<{ creditAmount?: number }>): number {
  return rows.reduce((s, r) => s + Math.abs(Number(r.creditAmount) || 0), 0)
}

export const G11_RISK_LEVEL_OPTIONS = [
  { label: '高', value: 'high' },
  { label: '中', value: 'medium' },
  { label: '低', value: 'low' },
] as const

/** 检查比例低于此阈值时提示扩样 */
export const G11_LOW_INSPECTION_RATIO = 0.3
