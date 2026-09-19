import type { ChecklistResponse } from './useF1FormData'
import { G5_ITEM_IDS, parseCanonicalArray, parseCanonicalJson, readCanonicalRaw } from './g5StorageContract'
import { computeMovement } from './useG5BadDebtDetail'

export type G5StatusTone = 'ok' | 'warn' | 'idle'

export interface G5SheetStatus {
  code: string
  label: string
  hasData: boolean
  conclusionComplete: boolean
  gate: boolean | null
  balance: boolean | null
  issues: string[]
  tone: G5StatusTone
}

const LABELS: Record<string, string> = {
  G5A: '审计程序',
  'G5-1': '审定表',
  'G5-2': '余额明细',
  'G5-3': '坏账明细',
  'G5-4': '调整分录',
  'G5-5': '融资租赁',
  'G5-6': '分期销售',
  'G5-7': '保理核查',
  'G5-8': 'ECL政策',
  'G5-9': '阶段划分',
  'G5-10': '减值测算',
  'G5-11': '转回核销',
  'G5-12': '凭证检查',
}

function num(value: unknown): number {
  const result = Number(value)
  return Number.isFinite(result) ? result : 0
}

function hasMeaningfulResponse(response: ChecklistResponse): boolean {
  const raw = readCanonicalRaw(response)
  if (!raw) return false
  try {
    const parsed = JSON.parse(raw)
    if (Array.isArray(parsed)) return parsed.length > 0
    if (parsed && typeof parsed === 'object') return Object.keys(parsed).length > 0
  } catch {
    return raw.trim().length > 0
  }
  return Boolean(raw.trim())
}

function codeResponses(map: Map<string, ChecklistResponse>, code: string) {
  return [...map.entries()].filter(([key]) => key === code || key.startsWith(`${code}-`))
}

function conclusionComplete(map: Map<string, ChecklistResponse>, code: string): boolean {
  return codeResponses(map, code).some(([key, response]) => {
    if (!/(?:audit-)?conclusion$/.test(key) && !key.endsWith('-overall-conclusion')) return false
    return Boolean(readCanonicalRaw(response)?.trim())
  })
}

function g54Balance(map: Map<string, ChecklistResponse>): boolean | null {
  const rows = parseCanonicalArray(map.get(G5_ITEM_IDS.G5_4_ROWS))
  if (!rows.length) return null
  const debit = rows.reduce((sum, row) => sum + num(row.debitAmount), 0)
  const credit = rows.reduce((sum, row) => sum + num(row.creditAmount), 0)
  return Math.abs(debit - credit) < 0.01
}

function g511Gate(map: Map<string, ChecklistResponse>): boolean | null {
  const data = parseCanonicalJson<any>(map.get(G5_ITEM_IDS.G5_11_ROWS))
  const reversals = Array.isArray(data?.reversal) ? data.reversal : []
  const writeoffs = Array.isArray(data?.writeoff) ? data.writeoff : []
  if (!reversals.length && !writeoffs.length) return null
  const reversalsReady = reversals.every(
    (row: any) => num(row.reversalAmount) <= num(row.accumulatedProvision),
  )
  const writeoffsReady = writeoffs.every(
    (row: any) =>
      !row.isRelatedParty
      || Boolean(String(row.reasonAnalysis || row.reason || '').trim()),
  )
  return reversalsReady && writeoffsReady
}

function g512Gate(map: Map<string, ChecklistResponse>): boolean | null {
  const data = parseCanonicalJson<any>(map.get(G5_ITEM_IDS.G5_12_VOUCHER))
    ?? parseCanonicalJson<any>(map.get(G5_ITEM_IDS.G5_12_ROWS))
  const rows = [
    ...(Array.isArray(data?.occurrenceRows) ? data.occurrenceRows : []),
    ...(Array.isArray(data?.postPeriodRows) ? data.postPeriodRows : []),
  ]
  if (!rows.length && Array.isArray(data)) {
    if (!data.length) return null
    return data.every(
      (row: any) => !row.abnormal && row.isAbnormal !== '是'
        || Boolean(String(row.remark || row.abnormalNote || '').trim()),
    )
  }
  if (!rows.length) return null
  return rows.every(
    (row: any) => !row.abnormal || Boolean(String(row.remark || '').trim()),
  )
}

function g52AgingGate(map: Map<string, ChecklistResponse>): boolean | null {
  const rows = parseCanonicalArray(map.get(G5_ITEM_IDS.G5_2_ROWS))
  if (!rows.length) return null
  return rows.every((row) => {
    const net = num(row.netAmount)
    const aging = row.agingAudited
    if (!aging || typeof aging !== 'object') return Math.abs(net) < 0.01
    const aged = Object.values(aging as Record<string, unknown>).reduce((s, v) => s + num(v), 0)
    const agingTotal = num(row.agingTotal) || aged
    return Math.abs(agingTotal - net) < 0.01
  })
}

export function evaluateG5SuiteStatus(
  map: Map<string, ChecklistResponse>,
): G5SheetStatus[] {
  return Object.entries(LABELS).map(([code, label]) => {
    const hasData = codeResponses(map, code).some(([, response]) => hasMeaningfulResponse(response))
    let gate: boolean | null = null
    let balance: boolean | null = null
    if (code === 'G5-2') gate = g52AgingGate(map)
    if (code === 'G5-4') balance = g54Balance(map)
    if (code === 'G5-11') gate = g511Gate(map)
    if (code === 'G5-12') gate = g512Gate(map)
    const issues: string[] = []
    if (gate === false) issues.push('质量闸门待处理')
    if (balance === false) issues.push('勾稽不平')
    const completed = conclusionComplete(map, code)
    const checksReady = gate !== false && balance !== false
    const tone: G5StatusTone = !hasData ? 'idle' : checksReady && completed ? 'ok' : 'warn'
    return { code, label, hasData, conclusionComplete: completed, gate, balance, issues, tone }
  })
}

/** 供上年结转复用：由 leaf 推期末审定 */
export function closingAuditedOfLeaf(leaf: any): number {
  return computeMovement({
    openingUnadjusted: num(leaf?.openingUnadjusted),
    openingAdjustment: num(leaf?.openingAdjustment),
    provisionIncrease: num(leaf?.provisionIncrease),
    otherIncrease: num(leaf?.otherIncrease),
    reversal: num(leaf?.reversal),
    writeOff: num(leaf?.writeOff),
    otherDecrease: num(leaf?.otherDecrease),
    closingAdjustment: num(leaf?.closingAdjustment),
  }).closingAudited
}
