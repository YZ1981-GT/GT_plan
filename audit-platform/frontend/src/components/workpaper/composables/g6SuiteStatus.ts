/**
 * G6 ECL 套件编制状态（G6-11~G6-15）— 对齐 g4SuiteStatus 思路。
 */
import type { ChecklistResponse } from './useF1FormData'
import {
  G6_ITEM_IDS,
  parseCanonicalArray,
  parseCanonicalJson,
  readCanonicalRaw,
} from './g6StorageContract'

export type G6StatusTone = 'ok' | 'warn' | 'idle'

export interface G6SheetStatus {
  code: string
  label: string
  hasData: boolean
  conclusionComplete: boolean
  gate: boolean | null
  issues: string[]
  tone: G6StatusTone
}

const LABELS: Record<string, string> = {
  'G6-11': '三阶段划分',
  'G6-12': '减值测算',
  'G6-13': 'ECL 计量',
  'G6-14': '转回与核销',
  'G6-15': '凭证检查',
}

function num(value: unknown): number {
  const result = Number(value)
  return Number.isFinite(result) ? result : 0
}

function hasMeaningfulResponse(response: ChecklistResponse | undefined): boolean {
  const raw = readCanonicalRaw(response)
  if (!raw) return false
  try {
    const parsed = JSON.parse(raw)
    if (Array.isArray(parsed)) return parsed.length > 0
    if (parsed && typeof parsed === 'object') {
      if (Array.isArray(parsed.rows) && parsed.rows.length) return true
      if (Array.isArray(parsed.reversals) && parsed.reversals.length) return true
      if (Array.isArray(parsed.writeOffs) && parsed.writeOffs.length) return true
      return Object.keys(parsed).length > 0
    }
  } catch {
    return raw.length > 0
  }
  return false
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

function g611Rows(map: Map<string, ChecklistResponse>): any[] {
  return parseCanonicalArray(map.get(G6_ITEM_IDS.G6_11_ROWS))
}

function g612Rows(map: Map<string, ChecklistResponse>): any[] {
  const payload = parseCanonicalJson<any>(map.get(G6_ITEM_IDS.G6_12_DATA))
    || parseCanonicalJson<any>(map.get(G6_ITEM_IDS.G6_12_ROWS))
  if (Array.isArray(payload)) return payload
  if (Array.isArray(payload?.rows)) return payload.rows
  return parseCanonicalArray(map.get(G6_ITEM_IDS.G6_12_ROWS))
}

function g614Payload(map: Map<string, ChecklistResponse>): {
  reversals: any[]
  writeOffs: any[]
} {
  const data = parseCanonicalJson<any>(map.get(G6_ITEM_IDS.G6_14_DATA))
    || parseCanonicalJson<any>(map.get(G6_ITEM_IDS.G6_14_ROWS))
  if (data && typeof data === 'object') {
    return {
      reversals: Array.isArray(data.reversals) ? data.reversals : [],
      writeOffs: Array.isArray(data.writeOffs) ? data.writeOffs : [],
    }
  }
  return { reversals: [], writeOffs: [] }
}

/** G6-11：有行且不一致时须有差异说明；审计阶段必填 */
function g611Gate(map: Map<string, ChecklistResponse>): boolean | null {
  const rows = g611Rows(map)
  if (!rows.length) return null
  return rows.every((row) => {
    const stage = String(row.auditStage || row.stage || '').trim()
    if (!stage) return false
    const inconsistent = row.isConsistent === false
      || String(row.isConsistent) === '否'
      || (row.companyStage && row.auditStage && row.companyStage !== row.auditStage)
    if (inconsistent && !String(row.discrepancyNote || '').trim()) return false
    return true
  })
}

/** G6-12：有行时投资项目与阶段必填 */
function g612Gate(map: Map<string, ChecklistResponse>): boolean | null {
  const rows = g612Rows(map)
  if (!rows.length) return null
  return rows.every((row) =>
    Boolean(String(row.investProject || '').trim())
    && Boolean(String(row.stage || row.auditStage || '').trim()),
  )
}

/** G6-13：有计量数据时至少有一种方法行或结论 */
function g613Gate(map: Map<string, ChecklistResponse>): boolean | null {
  const payload = parseCanonicalJson<any>(map.get(G6_ITEM_IDS.G6_13_MEASUREMENT))
  if (!payload || typeof payload !== 'object') return null
  const hasRows = ['methodEvaluation', 'combinations', 'pdLgdRows', 'lossRateRows', 'parameters']
    .some((key) => Array.isArray(payload[key]) && payload[key].length > 0)
  if (!hasRows && !String(payload.conclusion || '').trim()) return null
  const hasMethod = Array.isArray(payload.methodEvaluation)
    ? payload.methodEvaluation.length > 0
    : true
  return hasMethod || Boolean(String(payload.conclusion || '').trim())
}

function g614Gate(map: Map<string, ChecklistResponse>): boolean | null {
  const { reversals, writeOffs } = g614Payload(map)
  if (!reversals.length && !writeOffs.length) return null
  const reversalsReady = reversals.every((row) =>
    num(row.reversalAmount) <= num(row.accumulatedProvision) + 0.005
    && row.isReasonable !== '不合理',
  )
  const writeOffsReady = writeOffs.every((row) =>
    row.isReasonable !== '不合理'
    && (!row.isRelatedParty || Boolean(String(row.reasonAnalysis || '').trim())),
  )
  return reversalsReady && writeOffsReady
}

function g615Gate(map: Map<string, ChecklistResponse>): boolean | null {
  const rows = parseCanonicalArray(map.get(G6_ITEM_IDS.G6_15_ROWS))
  if (!rows.length) return null
  return rows.every((row) => {
    const abnormal = Boolean(row.isAbnormal) || Boolean(row.manualAbnormal)
    return !abnormal || Boolean(String(row.abnormalNote || '').trim())
  })
}

function sheetHasData(map: Map<string, ChecklistResponse>, code: string): boolean {
  if (code === 'G6-11') return g611Rows(map).length > 0
  if (code === 'G6-12') return g612Rows(map).length > 0
  if (code === 'G6-13') return hasMeaningfulResponse(map.get(G6_ITEM_IDS.G6_13_MEASUREMENT))
  if (code === 'G6-14') {
    const { reversals, writeOffs } = g614Payload(map)
    return reversals.length > 0 || writeOffs.length > 0
  }
  if (code === 'G6-15') {
    return parseCanonicalArray(map.get(G6_ITEM_IDS.G6_15_ROWS)).length > 0
      || hasMeaningfulResponse(map.get(G6_ITEM_IDS.G6_15_CRITERIA))
  }
  return codeResponses(map, code).some(([, r]) => hasMeaningfulResponse(r))
}

export function evaluateG6EclSuiteStatus(
  map: Map<string, ChecklistResponse>,
): G6SheetStatus[] {
  return Object.entries(LABELS).map(([code, label]) => {
    const hasData = sheetHasData(map, code)
    let gate: boolean | null = null
    if (code === 'G6-11') gate = g611Gate(map)
    if (code === 'G6-12') gate = g612Gate(map)
    if (code === 'G6-13') gate = g613Gate(map)
    if (code === 'G6-14') gate = g614Gate(map)
    if (code === 'G6-15') gate = g615Gate(map)

    const issues: string[] = []
    if (gate === false) issues.push('质量闸门待处理')
    const completed = conclusionComplete(map, code)
    const checksReady = gate !== false
    const tone: G6StatusTone = !hasData ? 'idle' : checksReady && completed ? 'ok' : 'warn'
    return { code, label, hasData, conclusionComplete: completed, gate, issues, tone }
  })
}

/** 目录备注用短文案 */
export function formatG6EclStatusRemark(status: G6SheetStatus): string {
  if (!status.hasData) return '○ 未填'
  const parts = [
    status.conclusionComplete ? '结论✓' : '结论待补',
  ]
  if (status.gate === false) parts.push('闸门待办')
  else if (status.gate === true) parts.push('闸门✓')
  return parts.join(' · ')
}
