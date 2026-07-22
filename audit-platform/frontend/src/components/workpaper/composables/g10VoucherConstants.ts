/** G10-7 凭证检查 — 核对项与抽样（对齐 Excel 编制说明） */

export type G10VoucherPeriodScope = 'current' | 'subsequent'

export const G10_VOUCHER_CHECK_DEFS = [
  { key: 'check1OriginalComplete', label: '①齐全', title: '原始单据齐全' },
  { key: 'check2Authorization', label: '②授权', title: '审批授权恰当' },
  { key: 'check3Accounting', label: '③账务', title: '会计处理正确' },
  { key: 'check4InitialCost', label: '④成本', title: '初始成本计算正确' },
  { key: 'check5Interest', label: '⑤利息', title: '利息计算正确' },
  { key: 'check6FairValueCorrect', label: '⑥公允', title: '公允价值符合准则' },
] as const

export type G10VoucherCheckKey = (typeof G10_VOUCHER_CHECK_DEFS)[number]['key']

export const G10_VOUCHER_PERIOD_OPTIONS = [
  { label: '本期发生额检查', value: 'current' as const },
  { label: '期后处置/新增检查', value: 'subsequent' as const },
]

/** 误受风险 → 扩展系数（编制说明） */
export const G10_SAMPLE_EXPANSION_FACTORS: Record<string, number> = {
  '0.01': 1.9,
  '0.05': 1.6,
  '0.10': 1.5,
}

/** 样本量 = 账面价值×风险系数 / (可容忍错报 − 预计错报×扩展系数) */
export function calcG10AuditSampleSize(opts: {
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

export function g10VoucherInspectionRatio(sampledAmount: number, populationAmount: number): number | null {
  if (populationAmount <= 0.005) return null
  return sampledAmount / populationAmount
}

export const G10_SAMPLING_METHOD_OPTIONS = [
  { value: 'random', label: '随机抽样' },
  { value: 'systematic', label: '系统抽样' },
  { value: 'judgmental', label: '判断抽样' },
  { value: 'mus', label: '货币单位抽样(MUS)' },
  { value: 'full', label: '全部项目检查' },
] as const

export function formatG10SamplingMethodLabel(value: string): string {
  const s = String(value ?? '').trim()
  if (!s) return '—'
  const hit = G10_SAMPLING_METHOD_OPTIONS.find((o) => o.value === s || o.label === s)
  return hit?.label ?? s
}

/** 单张凭证检查表（本期 / 期后）的抽样参数 */
export interface G10ScopeSamplingParams {
  testPopulation: string
  specificSamples: string
  samplingPopulation: string
  samplingMethod: string
  samplingProcess: string
  targetSampleSize: number
  populationCount: number
  populationAmount: number
  bookValue: number
  riskFactor: number
  tolerableMisstatement: number
  expectedMisstatement: number
  /** 误受风险 1 / 5 / 10 → 扩展系数 */
  riskOfIncorrectAcceptance: 1 | 5 | 10
}

export interface G10SamplingParams {
  current: G10ScopeSamplingParams
  subsequent: G10ScopeSamplingParams
}

export function defaultG10ScopeSamplingParams(): G10ScopeSamplingParams {
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

export function defaultG10SamplingParams(): G10SamplingParams {
  return {
    current: defaultG10ScopeSamplingParams(),
    subsequent: defaultG10ScopeSamplingParams(),
  }
}

export function parseG10SamplingParams(json: string | null | undefined): G10SamplingParams {
  const defaults = defaultG10SamplingParams()
  if (!json) return defaults
  try {
    const raw = JSON.parse(json)
    if (!raw || typeof raw !== 'object') return defaults
    const mergeScope = (scope: G10VoucherPeriodScope, patch: Partial<G10ScopeSamplingParams> | undefined) => ({
      ...defaults[scope],
      ...(patch ?? {}),
      riskOfIncorrectAcceptance: ([1, 5, 10] as const).includes(Number(patch?.riskOfIncorrectAcceptance) as 1 | 5 | 10)
        ? (Number(patch?.riskOfIncorrectAcceptance) as 1 | 5 | 10)
        : defaults[scope].riskOfIncorrectAcceptance,
    })
    if (raw.current || raw.subsequent) {
      return {
        current: mergeScope('current', raw.current),
        subsequent: mergeScope('subsequent', raw.subsequent),
      }
    }
    return { current: mergeScope('current', raw), subsequent: defaults.subsequent }
  } catch {
    return defaults
  }
}

export function g10ExpansionFactor(risk: 1 | 5 | 10): number {
  return G10_SAMPLE_EXPANSION_FACTORS[String(risk / 100)] ?? 1.6
}

export function calcG10SuggestedSampleSize(scope: G10ScopeSamplingParams): number | null {
  const bookValue = scope.bookValue || scope.populationAmount
  if (bookValue <= 0 || scope.tolerableMisstatement <= 0) return null
  return calcG10AuditSampleSize({
    bookValue,
    riskFactor: scope.riskFactor || 1,
    tolerableMisstatement: scope.tolerableMisstatement,
    expectedMisstatement: scope.expectedMisstatement,
    expansionFactor: g10ExpansionFactor(scope.riskOfIncorrectAcceptance),
  })
}

export function calcG10SampleAbsAmount(rows: Array<{ debitAmount: number; creditAmount: number }>): number {
  return rows.reduce((s, r) => s + Math.max(Math.abs(r.debitAmount || 0), Math.abs(r.creditAmount || 0)), 0)
}
