/**
 * H2-8 / H2-9 抽凭证据缺口 → H2-3 索引说明行（可替换自动草稿）
 */

export const H28_EVIDENCE_GAP_MARKER = 'H2-8-evidence-gap-auto'
export const H29_EVIDENCE_GAP_MARKER = 'H2-9-evidence-gap-auto'
export const H23_ROWS_KEY = 'H2-3-rows'

const ADDITION_EVIDENCE_FIELDS = {
  contractNo: '合同/协议/订单',
  progressDoc: '监理/进度(出包)',
  materialDoc: '领料单(自营)',
  invoiceNo: '发票/验收(设备)',
  acceptanceDoc: '验收/结算',
  paymentRef: '付款回单',
} as const

type AdditionEvidenceField = keyof typeof ADDITION_EVIDENCE_FIELDS
type AdditionMethod = '出包' | '自营' | '设备购置' | '其他' | ''

const EVIDENCE_BY_METHOD: Record<Exclude<AdditionMethod, ''>, AdditionEvidenceField[]> = {
  出包: ['contractNo', 'progressDoc', 'invoiceNo', 'paymentRef'],
  自营: ['contractNo', 'materialDoc', 'invoiceNo', 'paymentRef'],
  设备购置: ['contractNo', 'invoiceNo', 'acceptanceDoc', 'paymentRef'],
  其他: ['contractNo', 'progressDoc', 'materialDoc', 'invoiceNo', 'acceptanceDoc', 'paymentRef'],
}

function isEvidenceApplicable(method: AdditionMethod, field: AdditionEvidenceField): boolean {
  if (!method) return true
  return EVIDENCE_BY_METHOD[method].includes(field)
}

export interface H2AdditionEvidenceGapRow {
  amount: number
  additionMethod?: string
  name?: string
  summary?: string
  seq: number
  contractNo?: string
  progressDoc?: string
  materialDoc?: string
  invoiceNo?: string
  acceptanceDoc?: string
  paymentRef?: string
  approvalDoc?: string
  capitalizable?: string
  measurementConfirmed?: string
  progressConfirmed?: string
  auditConclusion?: string
}

export interface H2DecreaseEvidenceGapFlags {
  missingApproval: boolean
  missingStamps: boolean
}

export interface H2EvidenceGapPushRow {
  rowId: string
  seq: number
  description: string
  category: '其他'
  entryType: ''
  reportItem: string
  accountCode: string
  accountName: string
  noteItem: string
  debitAmount: number
  creditAmount: number
  debit: number
  credit: number
  indexRef: string
  remark: string
  summary: string
}

function _confirmed(val: string | undefined, yesValues: string[] = ['Y', '是']): boolean {
  const v = String(val ?? '').trim()
  return yesValues.includes(v)
}

/** H2-8：按增加方式检查适用证据列与关键确认项 */
export function evaluateAdditionEvidenceGaps(row: H2AdditionEvidenceGapRow): string[] {
  if ((Number(row.amount) || 0) <= 0) return []
  const gaps: string[] = []
  const method = (row.additionMethod || '') as AdditionMethod
  for (const [field, label] of Object.entries(ADDITION_EVIDENCE_FIELDS)) {
    const f = field as AdditionEvidenceField
    if (!isEvidenceApplicable(method, f)) continue
    const val = String((row as Record<string, unknown>)[field] ?? '').trim()
    if (!val || val.toUpperCase() === 'N/A') gaps.push(`缺少${label}`)
  }
  if (!_confirmed(row.approvalDoc)) gaps.push('审批文件未确认')
  const cap = String(row.capitalizable ?? '').trim()
  if (!cap || (cap !== 'Y' && cap !== 'N' && cap !== 'N/A' && cap !== '是' && cap !== '否')) {
    gaps.push('资本化判断未填')
  }
  const meas = String(row.measurementConfirmed ?? '').trim()
  if (meas !== 'Y' && meas !== 'N' && meas !== '是' && meas !== '否') gaps.push('计量未确认')
  const prog = String(row.progressConfirmed ?? '').trim()
  if (prog !== 'Y' && prog !== 'N' && prog !== '是' && prog !== '否') gaps.push('进度未确认')
  return gaps
}

/** H2-9：转固样本审批/验收盖章缺口 */
export function collectDecreaseEvidenceGaps(flags: H2DecreaseEvidenceGapFlags): string[] {
  const gaps: string[] = []
  if (flags.missingApproval) gaps.push('审批未确认恰当')
  if (flags.missingStamps) gaps.push('验收盖章不全')
  return gaps
}

export function buildEvidenceGapH23Row(opts: {
  sourceSheet: 'H2-8' | 'H2-9'
  projectName: string
  sampleLabel: string
  gaps: string[]
  seq: number
  marker: string
}): H2EvidenceGapPushRow {
  const gapsText = opts.gaps.join('；')
  const name = opts.projectName.trim() || '样本'
  const desc = `证据缺口跟进（${opts.sourceSheet}）：${name}（${opts.sampleLabel}）— ${gapsText}`
  return {
    rowId: `h2-ev-gap-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
    seq: opts.seq,
    description: desc,
    category: '其他',
    entryType: '',
    reportItem: '在建工程',
    accountCode: '1604',
    accountName: '在建工程',
    noteItem: '在建工程',
    debitAmount: 0,
    creditAmount: 0,
    debit: 0,
    credit: 0,
    indexRef: opts.sourceSheet,
    remark: opts.marker,
    summary: desc,
  }
}

export function mergeEvidenceGapRowsToH23(
  existing: unknown[],
  newRows: H2EvidenceGapPushRow[],
  marker: string,
): H2EvidenceGapPushRow[] {
  const filtered = (existing || []).filter((r: any) => r?.remark !== marker) as H2EvidenceGapPushRow[]
  return [...filtered, ...newRows]
}
