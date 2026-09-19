/**
 * i3ConsistencyModel — I3 商誉跨表编制校验 / 建议顺序
 */
import { reconcileI3DisclosureVsAdj } from './wpDisclosureAdjReconcile'

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

function _hasValue(raw: unknown): boolean {
  if (raw == null || raw === '') return false
  if (typeof raw === 'object') {
    const t = _readText(raw)
    return t !== '' && t !== 'null' && t !== '{}' && t !== '[]'
  }
  return true
}

function _num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

export type I3ConsistencyLevel = 'ok' | 'warn' | 'error' | 'info'

export interface I3ConsistencyItem {
  id: string
  code: string
  area: string
  level: I3ConsistencyLevel
  message: string
  sheetHint?: string
}

export interface I3ConsistencyDashboard {
  items: I3ConsistencyItem[]
  issues: I3ConsistencyItem[]
  errorCount: number
  warnCount: number
  okCount: number
}

/** 建议编制顺序（用于目录引导） */
export const I3_PREP_ORDER = [
  { code: 'I3-2', step: 1, label: '明细表' },
  { code: 'I3-4', step: 2, label: '入账价值测算' },
  { code: 'I3-1', step: 3, label: '审定表（自明细带入）' },
  { code: 'I3-3', step: 4, label: '调整分录' },
  { code: 'I3-5', step: 5, label: '针对性抽凭' },
  { code: 'I3-6', step: 6, label: '减值测试' },
  { code: 'I3-7', step: 7, label: '可收回金额 DCF' },
  { code: 'I3-8', step: 8, label: '复核公司减值过程' },
] as const

export function buildI3ConsistencyDashboard(map: Map<string, any> | undefined | null): I3ConsistencyDashboard {
  const items: I3ConsistencyItem[] = []
  if (!map) {
    return { items: [], issues: [], errorCount: 0, warnCount: 0, okCount: 0 }
  }

  const i32 = _safeParseArray(map.get('I3-2-rows'))
  if (!i32.length) {
    items.push({
      id: 'i32-empty',
      code: 'I3-2',
      area: '明细表',
      level: 'warn',
      message: '明细表尚未填报，建议先完成 I3-2 再编制审定表',
      sheetHint: 'I3-2',
    })
  } else {
    items.push({
      id: 'i32-ok',
      code: 'I3-2',
      area: '明细表',
      level: 'ok',
      message: `明细已有 ${i32.length} 个被投资单位`,
      sheetHint: 'I3-2',
    })
  }

  const i31 = _safeParseArray(map.get('I3-adj-rows')).length
    ? _safeParseArray(map.get('I3-adj-rows'))
    : _safeParseArray(map.get('I3-1-adj-rows')).length
      ? _safeParseArray(map.get('I3-1-adj-rows'))
      : _safeParseArray(map.get('I3-1-rows'))
  if (i32.length && !i31.length) {
    items.push({
      id: 'i31-empty',
      code: 'I3-1',
      area: '审定表',
      level: 'warn',
      message: '明细已有数据但审定表未带入，请打开 I3-1「从 I3-2 带入」',
      sheetHint: 'I3-1',
    })
  }

  // 审定勾稽：期末≠净额
  let endNetMismatch = 0
  let ajeApproxCount = 0
  for (const r of i31) {
    const end = _num(r.endBalance)
    const net = _num(r.netValue)
    if (Math.abs(end - net) > 0.01) endNetMismatch++
    if (r.ajeApprox) ajeApproxCount++
  }
  if (endNetMismatch > 0) {
    items.push({
      id: 'i31-end-net',
      code: 'I3-1',
      area: '审定表',
      level: 'error',
      message: `${endNetMismatch} 行期末余额与净额不一致，保存前须核对`,
      sheetHint: 'I3-1',
    })
  }
  if (ajeApproxCount > 0) {
    items.push({
      id: 'i31-aje-approx',
      code: 'I3-1',
      area: '审定表',
      level: 'warn',
      message: `${ajeApproxCount} 行 AJE/RJE 为比例分摊（近似），请按被投资单位人工复核`,
      sheetHint: 'I3-1',
    })
  }

  const i33 = _safeParseArray(map.get('I3-3-rows'))
  if (i33.length) {
    items.push({
      id: 'i33-ok',
      code: 'I3-3',
      area: '调整分录',
      level: 'ok',
      message: `调整分录 ${i33.length} 笔`,
      sheetHint: 'I3-3',
    })
  }

  // I3-5 覆盖率
  const sampleMetaRaw = map.get('I3-5-sample-meta')
  let sampleMeta: any = null
  try {
    const t = _readText(sampleMetaRaw)
    sampleMeta = t ? JSON.parse(t) : (typeof sampleMetaRaw === 'object' ? sampleMetaRaw : null)
  } catch { sampleMeta = null }
  const i35Rows = _safeParseArray(map.get('I3-5-rows'))
  const pop = _num(sampleMeta?.populationAmount)
  const threshold = _num(sampleMeta?.coverageThreshold) || 20
  if (i35Rows.length && pop > 0) {
    const checked = i35Rows.reduce((s: number, r: any) => s + _num(r.debitAmount), 0)
    const rate = Math.round((checked / pop) * 10000) / 100
    const note = _readText(map.get('I3-5-audit-note'))
    if (rate < threshold && !note.trim()) {
      items.push({
        id: 'i35-coverage',
        code: 'I3-5',
        area: '针对性检查',
        level: 'error',
        message: `检查比例 ${rate.toFixed(2)}% 低于阈值 ${threshold}%，且审计说明未解释`,
        sheetHint: 'I3-5',
      })
    } else if (rate < threshold) {
      items.push({
        id: 'i35-coverage-noted',
        code: 'I3-5',
        area: '针对性检查',
        level: 'warn',
        message: `检查比例 ${rate.toFixed(2)}% 偏低，已有说明`,
        sheetHint: 'I3-5',
      })
    } else {
      items.push({
        id: 'i35-ok',
        code: 'I3-5',
        area: '针对性检查',
        level: 'ok',
        message: `抽凭 ${i35Rows.length} 笔，覆盖率 ${rate.toFixed(2)}%`,
        sheetHint: 'I3-5',
      })
    }
  } else if (!i35Rows.length && i32.length) {
    items.push({
      id: 'i35-empty',
      code: 'I3-5',
      area: '针对性检查',
      level: 'info',
      message: '尚未执行针对性抽凭（有明细时建议抽查）',
      sheetHint: 'I3-5',
    })
  }

  const i36 = _safeParseArray(map.get('I3-6-rows'))
  if (!i36.length && i32.length) {
    items.push({
      id: 'i36-empty',
      code: 'I3-6',
      area: '减值测试',
      level: 'warn',
      message: '尚未填报商誉减值测试（CAS8 每年须测）',
      sheetHint: 'I3-6',
    })
  } else if (i36.length) {
    items.push({
      id: 'i36-ok',
      code: 'I3-6',
      area: '减值测试',
      level: 'ok',
      message: `减值测试 ${i36.length} 个 CGU`,
      sheetHint: 'I3-6',
    })
  }

  // I3-7 可收回金额
  const i37 = _safeParseArray(map.get('I3-7-rows'))
  if (i36.length && !i37.length) {
    items.push({
      id: 'i37-empty',
      code: 'I3-7',
      area: '可收回金额',
      level: 'warn',
      message: '已有 I3-6 减值测试但尚未编制 I3-7 可收回金额（DCF/公允）',
      sheetHint: 'I3-7',
    })
  } else if (i37.length) {
    const tested = i37.filter((r: any) => _num(r.recoverableAmount) > 0 || _num(r.valueInUse) > 0).length
    items.push({
      id: 'i37-ok',
      code: 'I3-7',
      area: '可收回金额',
      level: tested ? 'ok' : 'warn',
      message: tested
        ? `可收回金额测算 ${i37.length} 行（已测 ${tested}）`
        : `I3-7 有 ${i37.length} 行但可收回金额多为空`,
      sheetHint: 'I3-7',
    })
  }

  // I3-8 复核过程
  const i38Raw = map.get('I3-8-review-process')
  let i38Filled = 0
  let i38Total = 0
  try {
    const t = _readText(i38Raw)
    const parsed = t ? JSON.parse(t) : (typeof i38Raw === 'object' ? i38Raw : null)
    const answers = parsed?.answers || parsed?.items || parsed
    if (answers && typeof answers === 'object') {
      const vals = Array.isArray(answers) ? answers : Object.values(answers)
      i38Total = vals.length
      i38Filled = vals.filter((v: any) => {
        if (v == null || v === '') return false
        if (typeof v === 'object') {
          return Boolean(v.conclusion || v.result || v.evidence || v.remark)
        }
        return String(v).trim().length > 0
      }).length
    }
  } catch { /* ignore */ }
  if (i36.length && i38Total === 0 && !_hasValue(i38Raw)) {
    items.push({
      id: 'i38-empty',
      code: 'I3-8',
      area: '复核过程',
      level: 'info',
      message: '已有减值测试，建议完成 I3-8 过程复核（未利用专家时）',
      sheetHint: 'I3-8',
    })
  } else if (i38Total > 0 && i38Filled < i38Total) {
    items.push({
      id: 'i38-partial',
      code: 'I3-8',
      area: '复核过程',
      level: 'warn',
      message: `I3-8 复核进度 ${i38Filled}/${i38Total}，尚有未填项`,
      sheetHint: 'I3-8',
    })
  } else if (i38Filled > 0) {
    items.push({
      id: 'i38-ok',
      code: 'I3-8',
      area: '复核过程',
      level: 'ok',
      message: `I3-8 复核已填 ${i38Filled} 项`,
      sheetHint: 'I3-8',
    })
  }

  // 附注同步痕迹
  const discListed = _hasValue(map.get('I3-disc-listed-book'))
    || _hasValue(map.get('I3-disc-L-bookValue'))
    || _hasValue(map.get('I3-disc-listed-bookValue'))
  const discSoe = _hasValue(map.get('I3-disc-soe-book'))
    || _hasValue(map.get('I3-disc-S-bookValue'))
    || _hasValue(map.get('I3-disc-soe-bookValue'))
  if (i32.length && !discListed && !discSoe) {
    items.push({
      id: 'disc-empty',
      code: '附注',
      area: '附注披露',
      level: 'info',
      message: '明细已有数据，附注矩阵尚未取数（上市/国企择一编制）',
      sheetHint: '附注上市',
    })
  } else if (i31.length && (discListed || discSoe)) {
    const r = reconcileI3DisclosureVsAdj(map)
    if (r.hasBoth && !r.matched) {
      items.push({
        id: 'i3-disc-vs-adj',
        code: '附注',
        area: '附注↔审定',
        level: 'error',
        message: `附注合计 ${r.disclosureTotal.toFixed(2)} 与审定 ${r.adjudicatedTotal.toFixed(2)} 差 ${r.diff.toFixed(2)}`,
        sheetHint: '附注上市',
      })
    }
  }

  // I3-3 未指定被投资单位
  let unspecifiedAdj = 0
  for (const r of i33) {
    const code = String(r.accountCode || '')
    const name = String(r.accountName || '')
    const isGw = code.startsWith('1711') || name.includes('商誉')
    if (!isGw) continue
    if (!String(r.investee || '').trim()) unspecifiedAdj++
  }
  if (unspecifiedAdj > 0) {
    items.push({
      id: 'i33-unspecified',
      code: 'I3-3',
      area: '调整分录',
      level: 'warn',
      message: `${unspecifiedAdj} 笔商誉相关分录未填被投资单位，影响 I3-1/I3-2 精确回写`,
      sheetHint: 'I3-3',
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
