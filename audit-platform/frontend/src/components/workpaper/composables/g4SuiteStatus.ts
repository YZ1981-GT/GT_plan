import type { ChecklistResponse } from './useF1FormData'
import { G4_ITEM_IDS, parseCanonicalArray, parseCanonicalJson, readCanonicalRaw } from './g4StorageContract'

export type G4StatusTone = 'ok' | 'warn' | 'idle'

export interface G4SheetStatus {
  code: string
  label: string
  hasData: boolean
  conclusionComplete: boolean
  gate: boolean | null
  balance: boolean | null
  issues: string[]
  tone: G4StatusTone
}

const LABELS: Record<string, string> = {
  G4A: '审计程序',
  'G4-1': '审定表',
  'G4-2': '明细表',
  'G4-3': '调整分录',
  'G4-4': '利息测算',
  'G4-5': '业务模式',
  'G4-6': 'SPPI 测试',
  'G4-7': '证券盘点',
  'G4-8': '盘点倒轧',
  'G4-9': '阶段划分',
  'G4-10': '减值测算',
  'G4-11': 'ECL 计量',
  'G4-12': '转回与核销',
  'G4-13': '凭证检查',
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

function g43Balance(map: Map<string, ChecklistResponse>): boolean | null {
  const rows = parseCanonicalArray(map.get(G4_ITEM_IDS.G4_3_ROWS))
  if (!rows.length) return null
  const debit = rows.reduce((sum, row) => sum + num(row.debitAmount), 0)
  const credit = rows.reduce((sum, row) => sum + num(row.creditAmount), 0)
  return Math.abs(debit - credit) < 0.01
}

function g47HeaderGate(map: Map<string, ChecklistResponse>): boolean | null {
  const header = parseCanonicalJson<any>(map.get(G4_ITEM_IDS.G4_7_HEADER))
  if (!header) return null
  return Boolean(
    String(header.countDate || header.inventoryDate || '').trim()
    && String(header.balanceSheetDate || header.reportDate || '').trim(),
  )
}

function g48VarianceGate(map: Map<string, ChecklistResponse>): boolean | null {
  const rows = parseCanonicalArray(map.get(G4_ITEM_IDS.G4_8_ITEMS))
  if (!rows.length) return null
  return rows.every((row) => {
    const hasVariance = Math.abs(num(row.variance)) >= 0.01
      || Math.abs(num(row.varianceQuantity)) >= 0.01
    return !hasVariance || Boolean(String(row.remark || row.varianceReason || '').trim())
  })
}

function g412Gate(map: Map<string, ChecklistResponse>): boolean | null {
  const data = parseCanonicalJson<any>(map.get(G4_ITEM_IDS.G4_12_ROWS))
  const reversals = Array.isArray(data?.reversals)
    ? data.reversals
    : parseCanonicalArray(map.get(G4_ITEM_IDS.G4_12_REVERSALS))
  const writeOffs = Array.isArray(data?.writeOffs)
    ? data.writeOffs
    : parseCanonicalArray(map.get(G4_ITEM_IDS.G4_12_WRITEOFFS))
  if (!reversals.length && !writeOffs.length) return null
  const reversalsReady = reversals.every((row) =>
    num(row.reversalAmount) <= num(row.accumulatedProvision)
    && row.isReasonable !== '不合理',
  )
  const writeOffsReady = writeOffs.every((row) =>
    row.isReasonable !== '不合理'
    && (!row.isRelatedParty || Boolean(String(row.reasonAnalysis || '').trim())),
  )
  return reversalsReady && writeOffsReady
}

function g413Checks(map: Map<string, ChecklistResponse>): {
  gate: boolean | null
  balance: boolean | null
} {
  const rows = parseCanonicalArray(map.get(G4_ITEM_IDS.G4_13_ROWS))
  if (!rows.length) return { gate: null, balance: null }
  const debit = rows.reduce((sum, row) => sum + num(row.debitAmount), 0)
  const credit = rows.reduce((sum, row) => sum + num(row.creditAmount), 0)
  return {
    balance: Math.abs(debit - credit) < 0.01,
    gate: rows.every((row) => !row.isAbnormal || Boolean(String(row.abnormalNote || '').trim())),
  }
}

export function evaluateG4SuiteStatus(
  map: Map<string, ChecklistResponse>,
): G4SheetStatus[] {
  const checks413 = g413Checks(map)
  return Object.entries(LABELS).map(([code, label]) => {
    const hasData = codeResponses(map, code).some(([, response]) => hasMeaningfulResponse(response))
    let gate: boolean | null = null
    let balance: boolean | null = null
    if (code === 'G4-3') balance = g43Balance(map)
    if (code === 'G4-7') gate = g47HeaderGate(map)
    if (code === 'G4-8') gate = g48VarianceGate(map)
    if (code === 'G4-12') gate = g412Gate(map)
    if (code === 'G4-13') {
      gate = checks413.gate
      balance = checks413.balance
    }
    const issues: string[] = []
    if (gate === false) issues.push('质量闸门待处理')
    if (balance === false) issues.push('勾稽不平')
    const completed = conclusionComplete(map, code)
    const checksReady = gate !== false && balance !== false
    const tone: G4StatusTone = !hasData ? 'idle' : checksReady && completed ? 'ok' : 'warn'
    return { code, label, hasData, conclusionComplete: completed, gate, balance, issues, tone }
  })
}

