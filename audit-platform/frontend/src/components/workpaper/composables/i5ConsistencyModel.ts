/**
 * i5ConsistencyModel — I5 其他非流动资产跨表编制校验 / 建议顺序
 */
import { reconcileI5DisclosureVsAdj } from './wpDisclosureAdjReconcile'

function _safeParseArray(raw: unknown): any[] {
  if (Array.isArray(raw)) return raw
  if (typeof raw === 'string' && raw) {
    try {
      const p = JSON.parse(raw)
      return Array.isArray(p) ? p : []
    } catch { return [] }
  }
  if (raw && typeof raw === 'object') {
    const remark = (raw as any).remark ?? (raw as any).conclusion
    if (remark != null) return _safeParseArray(remark)
  }
  return []
}

function _readText(raw: unknown): string {
  if (raw == null) return ''
  if (typeof raw === 'string') return raw
  if (typeof raw === 'object') return String((raw as any).remark ?? (raw as any).conclusion ?? '')
  return ''
}

function _num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function _round2(n: number): number {
  return Math.round(n * 100) / 100
}

export type I5ConsistencyLevel = 'ok' | 'warn' | 'error' | 'info'

export interface I5ConsistencyItem {
  id: string
  code: string
  area: string
  level: I5ConsistencyLevel
  message: string
  sheetHint?: string
}

export interface I5ConsistencyDashboard {
  items: I5ConsistencyItem[]
  issues: I5ConsistencyItem[]
  errorCount: number
  warnCount: number
  okCount: number
}

export const I5_PREP_ORDER = [
  { code: 'I5-2', step: 1, label: '明细表' },
  { code: 'I5-1', step: 2, label: '审定表（自明细带入）' },
  { code: 'I5-3', step: 3, label: '调整分录' },
  { code: 'I5-4', step: 4, label: '针对性抽凭' },
  { code: '附注', step: 5, label: '附注披露' },
] as const

export function buildI5ConsistencyDashboard(map: Map<string, any> | undefined | null): I5ConsistencyDashboard {
  const items: I5ConsistencyItem[] = []
  if (!map) {
    return { items: [], issues: [], errorCount: 0, warnCount: 0, okCount: 0 }
  }

  const i52 = _safeParseArray(map.get('I5-2-rows'))
  if (!i52.length) {
    items.push({
      id: 'i52-empty',
      code: 'I5-2',
      area: '明细表',
      level: 'warn',
      message: '明细表尚未填报，建议先完成 I5-2 再编制审定表',
      sheetHint: 'I5-2',
    })
  } else {
    items.push({
      id: 'i52-ok',
      code: 'I5-2',
      area: '明细表',
      level: 'ok',
      message: `明细已有 ${i52.length} 个项目`,
      sheetHint: 'I5-2',
    })
  }

  const i51 = _safeParseArray(map.get('I5-adj-rows')).length
    ? _safeParseArray(map.get('I5-adj-rows'))
    : _safeParseArray(map.get('I5-1-rows'))
  if (i52.length && !i51.length) {
    items.push({
      id: 'i51-empty',
      code: 'I5-1',
      area: '审定表',
      level: 'warn',
      message: '明细已有数据但审定表未带入，请打开 I5-1「从 I5-2 带入」',
      sheetHint: 'I5-1',
    })
  }

  let triangleBad = 0
  let ajeApproxCount = 0
  let adjEnd = 0
  for (const r of i51) {
    if (r.hasError || Math.abs(_num(r.triangleDiff)) > 0.01) triangleBad++
    if (r.ajeApprox) ajeApproxCount++
    adjEnd = _round2(adjEnd + _num(r.endBalance ?? r.期末))
  }
  if (triangleBad > 0) {
    items.push({
      id: 'i51-triangle',
      code: 'I5-1',
      area: '审定表',
      level: 'error',
      message: `${triangleBad} 行三角勾稽不平（期末≠期初+增−减），保存前须核对`,
      sheetHint: 'I5-1',
    })
  }
  if (ajeApproxCount > 0) {
    items.push({
      id: 'i51-aje-approx',
      code: 'I5-1',
      area: '审定表',
      level: 'warn',
      message: `${ajeApproxCount} 行 AJE/RJE 为比例分摊（近似），请按项目人工复核`,
      sheetHint: 'I5-1',
    })
  }

  if (i52.length && i51.length) {
    const detailEnd = _round2(i52.reduce((s: number, r: any) => {
      const name = String(r.projectName || r.name || '').trim()
      if (!name || name === '合计' || r.layer === 'impairment' || r.layer === 'net') return s
      if (r.gross && typeof r.gross === 'object') {
        return s + _num(r.gross.auditedEnding) - _num(r.impairment?.auditedEnding)
      }
      return s + _num(r.endBalance)
    }, 0))
    const endDiff = _round2(adjEnd - detailEnd)
    if (Math.abs(endDiff) > 0.01) {
      items.push({
        id: 'i51-vs-i52',
        code: 'I5-1',
        area: '审定↔明细',
        level: 'warn',
        message: `审定滚动期末与 I5-2 净值审定差 ${endDiff.toFixed(2)}，请复核带入`,
        sheetHint: 'I5-1',
      })
    }
  }

  const i53 = _safeParseArray(map.get('I5-3-rows'))
  if (i53.length) {
    items.push({
      id: 'i53-ok',
      code: 'I5-3',
      area: '调整分录',
      level: 'ok',
      message: `调整分录 ${i53.length} 行`,
      sheetHint: 'I5-3',
    })
  }

  const sampleMetaRaw = map.get('I5-4-sample-meta')
  let sampleMeta: any = null
  try {
    const t = _readText(sampleMetaRaw)
    sampleMeta = t ? JSON.parse(t) : (typeof sampleMetaRaw === 'object' ? sampleMetaRaw : null)
  } catch { sampleMeta = null }
  const i54Rows = _safeParseArray(map.get('I5-4-rows'))
  const pop = _num(sampleMeta?.populationAmount ?? sampleMeta?.periodDebitTotal)
  const threshold = _num(sampleMeta?.coverageThreshold) || 20
  if (i54Rows.length && pop > 0) {
    const checked = i54Rows.reduce((s: number, r: any) => s + _num(r.debitAmount), 0)
    const rate = Math.round((checked / pop) * 10000) / 100
    const note = _readText(map.get('I5-4-audit-note'))
    if (rate < threshold && !note.trim()) {
      items.push({
        id: 'i54-coverage',
        code: 'I5-4',
        area: '针对性检查',
        level: 'error',
        message: `检查比例 ${rate.toFixed(2)}% 低于阈值 ${threshold}%，且审计说明未解释`,
        sheetHint: 'I5-4',
      })
    } else if (rate < threshold) {
      items.push({
        id: 'i54-coverage-noted',
        code: 'I5-4',
        area: '针对性检查',
        level: 'warn',
        message: `检查比例 ${rate.toFixed(2)}% 偏低，已有说明`,
        sheetHint: 'I5-4',
      })
    } else {
      items.push({
        id: 'i54-ok',
        code: 'I5-4',
        area: '针对性检查',
        level: 'ok',
        message: `抽凭 ${i54Rows.length} 笔，覆盖率 ${rate.toFixed(2)}%`,
        sheetHint: 'I5-4',
      })
    }
  } else if (!i54Rows.length && i52.length) {
    items.push({
      id: 'i54-empty',
      code: 'I5-4',
      area: '针对性检查',
      level: 'info',
      message: '尚未执行针对性抽凭（有明细时建议抽查）',
      sheetHint: 'I5-4',
    })
  }

  const discR = reconcileI5DisclosureVsAdj(map)
  if (discR.hasBoth && !discR.matched) {
    items.push({
      id: 'i5-disc-vs-adj',
      code: '附注',
      area: '附注↔审定',
      level: 'error',
      message: `附注期末合计 ${discR.disclosureTotal.toFixed(2)} 与审定合计 ${discR.adjudicatedTotal.toFixed(2)} 不一致`,
      sheetHint: '附注(上市)',
    })
  } else if (discR.hasBoth && discR.matched) {
    items.push({
      id: 'i5-disc-ok',
      code: '附注',
      area: '附注↔审定',
      level: 'ok',
      message: '附注期末与审定合计勾稽一致',
      sheetHint: '附注(上市)',
    })
  } else if (i51.length && !discR.hasBoth) {
    items.push({
      id: 'i5-disc-empty',
      code: '附注',
      area: '附注披露',
      level: 'info',
      message: '审定已完成，建议同步编制附注披露',
      sheetHint: '附注(上市)',
    })
  }

  const issues = items.filter((i) => i.level === 'error' || i.level === 'warn')
  return {
    items,
    issues,
    errorCount: items.filter((i) => i.level === 'error').length,
    warnCount: items.filter((i) => i.level === 'warn').length,
    okCount: items.filter((i) => i.level === 'ok').length,
  }
}
