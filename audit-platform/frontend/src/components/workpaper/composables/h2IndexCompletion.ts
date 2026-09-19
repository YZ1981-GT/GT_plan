/**
 * H2 底稿目录完成度 / 适用性（纯函数）
 * - completed：有实质内容或已填结论
 * - pending：适用但未完成
 * - na：互斥分支 / 无减值迹象等不适用
 */
import {
  resolveInterestCapBranch,
  type InterestCapBranch,
} from './h2InterestCapBranch'
import {
  resolveH2DisclosureVariantFromResponses,
} from './useH2ApplicableStandards'
import {
  isImpairmentGateBlocked,
  impairmentGateBlockReason,
  needsH216RecoverableTest,
  isH216RecoverableComplete,
  countImpairmentSignYes,
} from './h2ImpairmentGate'

export type H2SheetStatus = 'completed' | 'pending' | 'na'

export interface H2SheetStatusResult {
  status: H2SheetStatus
  reason?: string
}

const CONCLUSION_KEYS: Record<string, string[]> = {
  'H2-1': ['H2-1-audit-conclusion'],
  'H2-2': ['H2-2-audit-conclusion'],
  'H2-3': ['H2-3-audit-conclusion'],
  'H2-4': ['H2-4-audit-conclusion'],
  'H2-5': ['H2-5-audit-conclusion'],
  'H2-6': ['H2-6-audit-conclusion'],
  'H2-7': ['H2-7-audit-conclusion'],
  'H2-8': ['H2-8-audit-conclusion'],
  'H2-9': ['H2-9-audit-conclusion'],
  'H2-10': ['H2-10-audit-conclusion'],
  'H2-11': ['H2-11-audit-conclusion', 'H2-10-audit-conclusion'],
  'H2-12': ['H2-12-audit-conclusion'],
  'H2-13': ['H2-13-audit-conclusion'],
  'H2-14': ['H2-14-audit-conclusion'],
  'H2-15': ['H2-15-audit-conclusion'],
  'H2-16': ['H2-16-audit-conclusion'],
  'H2-17': ['H2-17-audit-conclusion'],
  'H2A': ['H2A-c7-prerequisite'],
  'H2-disc-L': ['H2-disclosure-listed-conclusion'],
  'H2-disc-S': ['H2-disclosure-soe-conclusion'],
}

const DATA_PREFIXES: Record<string, string[]> = {
  'H2-1': ['H2-1-rows', 'H2-1-impair-rows'],
  'H2-2': ['H2-2-rows'],
  'H2-3': ['H2-3-rows'],
  'H2-4': ['H2-4-'],
  'H2-5': ['H2-5-rows'],
  'H2-6': ['H2-6-'],
  'H2-7': ['H2-7-'],
  'H2-8': ['H2-8-'],
  'H2-9': ['H2-9-'],
  'H2-10': ['H2-10-'],
  'H2-11': ['H2-11-'],
  'H2-12': ['H2-12-'],
  'H2-13': ['H2-13-'],
  'H2-14': ['H2-14-'],
  'H2-15': ['H2-15-'],
  'H2-16': ['H2-16-'],
  'H2-17': ['H2-17-'],
  'H2A': ['H2A-', 'proc-'],
  'H2-disc-L': ['H2-disclosure-listed', 'H2-disc-L', 'H2-note-listed'],
  'H2-disc-S': ['H2-disclosure-soe', 'H2-disc-S', 'H2-note-soe'],
}

function _remark(map: Map<string, any>, key: string): string {
  const r = map.get(key)?.remark
  return r == null ? '' : String(r).trim()
}

function _conclusion(map: Map<string, any>, key: string): string {
  const c = map.get(key)?.conclusion
  return c == null ? '' : String(c).trim()
}

function _hasNonEmptyRemark(map: Map<string, any>, key: string): boolean {
  const r = _remark(map, key)
  if (!r) return false
  if (r === '[]' || r === '{}' || r === 'null') return false
  try {
    const parsed = JSON.parse(r)
    if (Array.isArray(parsed)) return parsed.length > 0
    if (parsed && typeof parsed === 'object') return Object.keys(parsed).length > 0
  } catch { /* plain text */ }
  return true
}

function _hasConclusion(map: Map<string, any>, code: string): boolean {
  for (const key of CONCLUSION_KEYS[code] || []) {
    if (_conclusion(map, key) || _hasNonEmptyRemark(map, key)) return true
  }
  return false
}

function _hasData(map: Map<string, any>, code: string): boolean {
  const prefixes = DATA_PREFIXES[code]
  if (!prefixes) {
    for (const [k] of map) {
      if (k.startsWith(code)) return _hasNonEmptyRemark(map, k) || !!_conclusion(map, k)
    }
    return false
  }
  for (const [k] of map) {
    if (prefixes.some(p => k.startsWith(p))) {
      if (_hasNonEmptyRemark(map, k) || !!_conclusion(map, k)) return true
    }
  }
  return false
}

function _disclosureVariant(map: Map<string, any>): 'listed' | 'soe' | null {
  return resolveH2DisclosureVariantFromResponses(map)
}

export function resolveH2SheetStatus(
  code: string,
  responses: Map<string, any>,
  branchOverride?: InterestCapBranch | null,
): H2SheetStatusResult {
  if (code === 'H2') {
    return { status: 'completed', reason: '目录导航' }
  }

  const branch = branchOverride !== undefined
    ? branchOverride
    : resolveInterestCapBranch(responses)

  if (code === 'H2-10' && branch === 'withBorrow') {
    return { status: 'na', reason: '已选有专门借款(H2-11)' }
  }
  if (code === 'H2-11' && branch === 'noBorrow') {
    return { status: 'na', reason: '已选无专门借款(H2-10)' }
  }

  if (code === 'H2-16') {
    const yes = countImpairmentSignYes(responses)
    if (yes < 2 && !_hasData(responses, 'H2-16')) {
      return { status: 'na', reason: `减值迹象 ${yes} 项（<2，可不做 H2-16）` }
    }
    if (needsH216RecoverableTest(responses) && !isH216RecoverableComplete(responses)) {
      return { status: 'pending', reason: impairmentGateBlockReason(responses) || '须完成可收回金额测试' }
    }
  }

  if (code === 'H2-15' && isImpairmentGateBlocked(responses)) {
    return {
      status: 'pending',
      reason: impairmentGateBlockReason(responses) || '待完成 H2-16',
    }
  }

  const disc = _disclosureVariant(responses)
  if (code === 'H2-disc-L' && disc === 'soe') {
    return { status: 'na', reason: '适用国企附注' }
  }
  if (code === 'H2-disc-S' && disc === 'listed') {
    return { status: 'na', reason: '适用上市附注' }
  }

  if (_hasConclusion(responses, code) || _hasData(responses, code)) {
    // 更严：关键表要求结论；其余有数据即算完成
    const needsConclusion = ['H2-1', 'H2-2', 'H2-5', 'H2-15'].includes(code)
    if (needsConclusion && !_hasConclusion(responses, code)) {
      return { status: 'pending', reason: '已有数据，待填审计结论' }
    }
    return { status: 'completed' }
  }

  return { status: 'pending' }
}

export function summarizeH2IndexProgress(
  codes: string[],
  responses: Map<string, any>,
): { completed: number; applicable: number; pct: number } {
  let completed = 0
  let applicable = 0
  const branch = resolveInterestCapBranch(responses)
  for (const code of codes) {
    const { status } = resolveH2SheetStatus(code, responses, branch)
    if (status === 'na') continue
    applicable++
    if (status === 'completed') completed++
  }
  const pct = applicable === 0 ? 0 : Math.round((completed / applicable) * 100)
  return { completed, applicable, pct }
}
