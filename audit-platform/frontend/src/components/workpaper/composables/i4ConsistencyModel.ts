/**
 * i4ConsistencyModel — I4 长期待摊跨表编制校验 / 建议顺序
 *
 * Spec（归档）: .kiro/specs/_archive/05-business-features/i4-long-term-prepaid/
 */
import { reconcileI4DisclosureVsAdj } from './wpDisclosureAdjReconcile'

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

export type I4ConsistencyLevel = 'ok' | 'warn' | 'error' | 'info'

export interface I4ConsistencyItem {
  id: string
  code: string
  area: string
  level: I4ConsistencyLevel
  message: string
  sheetHint?: string
}

export interface I4ConsistencyDashboard {
  items: I4ConsistencyItem[]
  issues: I4ConsistencyItem[]
  errorCount: number
  warnCount: number
  okCount: number
}

export const I4_PREP_ORDER = [
  { code: 'I4-2', step: 1, label: '明细表' },
  { code: 'I4-1', step: 2, label: '审定表（自明细带入）' },
  { code: 'I4-3', step: 3, label: '调整分录' },
  { code: 'I4-4', step: 4, label: '摊销政策检查' },
  { code: 'I4-5', step: 5, label: '针对性抽凭' },
  { code: 'I4-6', step: 6, label: '摊销测算（直线/工作量）' },
  { code: '附注', step: 7, label: '附注披露' },
] as const

/** 审定合计（优先 I4-adj-rows，兼容 I4-1-rows） */
export function sumI4Adjudicated(map: Map<string, any>): number {
  const adj = _safeParseArray(map.get('I4-adj-rows'))
  const list = adj.length ? adj : _safeParseArray(map.get('I4-1-rows'))
  return _round2(list.reduce((s: number, r: any) => s + _num(r.audited ?? r.审定), 0))
}

/** 附注期末合计（上市/国企任一有数据即可） */
export function sumI4DisclosureEnding(map: Map<string, any>): number {
  const listed = _safeParseArray(map.get('I4-disc-listed-rows'))
  const soe = _safeParseArray(map.get('I4-disc-soe-rows'))
  const rows = listed.length ? listed : soe
  return _round2(rows.reduce((s: number, r: any) => s + _num(r.endBalance ?? r.期末余额 ?? r.closingBalance), 0))
}

/** 明细行期末（审定别名优先） */
function _detailEndOf(r: any): number {
  return _num(
    r.auditedEnding
    ?? r.auditedEnd
    ?? r.endBalance
    ?? r.期末
    ?? r.unadjEnding,
  )
}

export function buildI4ConsistencyDashboard(map: Map<string, any> | undefined | null): I4ConsistencyDashboard {
  const items: I4ConsistencyItem[] = []
  if (!map) {
    return { items: [], issues: [], errorCount: 0, warnCount: 0, okCount: 0 }
  }

  const i42 = _safeParseArray(map.get('I4-2-rows'))
  if (!i42.length) {
    items.push({
      id: 'i42-empty',
      code: 'I4-2',
      area: '明细表',
      level: 'warn',
      message: '明细表尚未填报，建议先完成 I4-2 再编制审定表',
      sheetHint: 'I4-2',
    })
  } else {
    items.push({
      id: 'i42-ok',
      code: 'I4-2',
      area: '明细表',
      level: 'ok',
      message: `明细已有 ${i42.length} 个项目`,
      sheetHint: 'I4-2',
    })
  }

  const i41Adj = _safeParseArray(map.get('I4-adj-rows'))
  const i41 = i41Adj.length ? i41Adj : _safeParseArray(map.get('I4-1-rows'))
  if (i42.length && !i41.length) {
    items.push({
      id: 'i41-empty',
      code: 'I4-1',
      area: '审定表',
      level: 'warn',
      message: '明细已有数据但审定表未带入，请打开 I4-1「从 I4-2 带入」',
      sheetHint: 'I4-1',
    })
  }

  let triangleBad = 0
  let ajeApproxCount = 0
  let adjEnd = 0
  let adjAmort = 0
  for (const r of i41) {
    if (r.hasError || Math.abs(_num(r.triangleDiff)) > 0.01) triangleBad++
    if (r.ajeApprox) ajeApproxCount++
    adjEnd = _round2(adjEnd + _num(r.endBalance ?? r.期末 ?? r.auditedEnding))
    adjAmort = _round2(adjAmort + _num(r.amortization ?? r.摊销 ?? r.auditedAmortization))
  }
  if (triangleBad > 0) {
    items.push({
      id: 'i41-triangle',
      code: 'I4-1',
      area: '审定表',
      level: 'error',
      message: `${triangleBad} 行三角勾稽不平（期末≠期初+增−摊−减），保存前须核对`,
      sheetHint: 'I4-1',
    })
  }
  if (ajeApproxCount > 0) {
    items.push({
      id: 'i41-aje-approx',
      code: 'I4-1',
      area: '审定表',
      level: 'warn',
      message: `${ajeApproxCount} 行 AJE/RJE 为比例分摊（近似），请按项目人工复核`,
      sheetHint: 'I4-1',
    })
  }

  // 明细期末 vs 审定滚动期末（审定别名兜底）
  if (i42.length && i41.length) {
    const detailEnd = _round2(i42.reduce((s: number, r: any) => {
      const name = String(r.projectName || r.name || '').trim()
      if (name === '合计') return s
      return s + _detailEndOf(r)
    }, 0))
    const endDiff = _round2(adjEnd - detailEnd)
    if (Math.abs(endDiff) > 0.01) {
      items.push({
        id: 'i41-vs-i42',
        code: 'I4-1',
        area: '审定↔明细',
        level: 'warn',
        message: `审定滚动期末与 I4-2 期末差 ${endDiff.toFixed(2)}，请复核带入`,
        sheetHint: 'I4-1',
      })
    }
  }

  const i43 = _safeParseArray(map.get('I4-3-rows'))
  if (i43.length) {
    items.push({
      id: 'i43-ok',
      code: 'I4-3',
      area: '调整分录',
      level: 'ok',
      message: `调整分录 ${i43.length} 行`,
      sheetHint: 'I4-3',
    })
  }

  // I4-4 有估计变更 → 提示 I4-5 抽「受益期变更」
  let policyParams: any[] = []
  try {
    const t = _readText(map.get('I4-4-policy-params'))
    policyParams = t ? JSON.parse(t) : _safeParseArray(map.get('I4-4-policy-params'))
  } catch { policyParams = [] }
  const changeCats = policyParams.filter((r) => r?.hasChange === 'Y')
  if (changeCats.length) {
    let sampleMetaEarly: any = null
    try {
      const t = _readText(map.get('I4-5-sample-meta'))
      sampleMetaEarly = t ? JSON.parse(t) : null
    } catch { sampleMetaEarly = null }
    const reasons: string[] = Array.isArray(sampleMetaEarly?.testReasons) ? sampleMetaEarly.testReasons : []
    if (!reasons.includes('受益期变更')) {
      items.push({
        id: 'i44-to-i45-change',
        code: 'I4-5',
        area: '政策→抽凭',
        level: 'warn',
        message: `I4-4 有 ${changeCats.length} 类估计变更，建议在 I4-5 勾选测试原因「受益期变更」并抽查`,
        sheetHint: 'I4-5',
      })
    }
  }

  // I4-5 借方覆盖率
  const sampleMetaRaw = map.get('I4-5-sample-meta')
  let sampleMeta: any = null
  try {
    const t = _readText(sampleMetaRaw)
    sampleMeta = t ? JSON.parse(t) : (typeof sampleMetaRaw === 'object' ? sampleMetaRaw : null)
  } catch { sampleMeta = null }
  const i45Rows = _safeParseArray(map.get('I4-5-rows'))
  const pop = _num(sampleMeta?.populationAmount ?? sampleMeta?.periodDebitTotal)
  const threshold = _num(sampleMeta?.coverageThreshold) || 20
  const note = _readText(map.get('I4-5-audit-note'))
  if (i45Rows.length && pop > 0) {
    const checked = i45Rows.reduce((s: number, r: any) => s + _num(r.debitAmount), 0)
    const rate = Math.round((checked / pop) * 10000) / 100
    if (rate < threshold && !note.trim()) {
      items.push({
        id: 'i45-coverage',
        code: 'I4-5',
        area: '针对性检查',
        level: 'error',
        message: `借方检查比例 ${rate.toFixed(2)}% 低于阈值 ${threshold}%，且审计说明未解释`,
        sheetHint: 'I4-5',
      })
    } else if (rate < threshold) {
      items.push({
        id: 'i45-coverage-noted',
        code: 'I4-5',
        area: '针对性检查',
        level: 'warn',
        message: `借方检查比例 ${rate.toFixed(2)}% 偏低，已有说明`,
        sheetHint: 'I4-5',
      })
    } else {
      items.push({
        id: 'i45-ok',
        code: 'I4-5',
        area: '针对性检查',
        level: 'ok',
        message: `抽凭 ${i45Rows.length} 笔，借方覆盖率 ${rate.toFixed(2)}%`,
        sheetHint: 'I4-5',
      })
    }
  } else if (!i45Rows.length && i42.length) {
    items.push({
      id: 'i45-empty',
      code: 'I4-5',
      area: '针对性检查',
      level: 'info',
      message: '尚未执行针对性抽凭（有明细时建议抽查）',
      sheetHint: 'I4-5',
    })
  }

  // I4-5 贷方覆盖率
  const popCredit = _num(sampleMeta?.populationCreditAmount)
  if (i45Rows.length && popCredit > 0) {
    const checkedCredit = i45Rows.reduce((s: number, r: any) => s + _num(r.creditAmount), 0)
    const creditRate = Math.round((checkedCredit / popCredit) * 10000) / 100
    if (creditRate < threshold) {
      const creditNoted = /贷方|转出|终止/.test(note)
      items.push({
        id: creditNoted ? 'i45-credit-coverage-noted' : 'i45-credit-coverage',
        code: 'I4-5',
        area: '针对性检查',
        level: creditNoted ? 'warn' : 'error',
        message: creditNoted
          ? `贷方检查比例 ${creditRate.toFixed(2)}% 偏低，已有说明`
          : `贷方检查比例 ${creditRate.toFixed(2)}% 低于阈值 ${threshold}%，且说明未回应贷方/转出/终止`,
        sheetHint: 'I4-5',
      })
    }
  }

  // I4-6/7 双填警告
  const i46 = _safeParseArray(map.get('I4-6-rows'))
  const i47 = _safeParseArray(map.get('I4-7-rows'))
  if (i46.length && i47.length) {
    items.push({
      id: 'i46-i47-both',
      code: 'I4-6',
      area: '摊销测算',
      level: 'warn',
      message: `I4-6（${i46.length} 行）与 I4-7（${i47.length} 行）均有数据，跨表同步以 I4-6 为准；请清空未选用分支`,
      sheetHint: 'I4-6',
    })
  }

  const amortRows = i46.length ? i46 : i47
  if (!amortRows.length && i42.length) {
    items.push({
      id: 'i46-empty',
      code: 'I4-6',
      area: '摊销测算',
      level: 'warn',
      message: '尚未编制摊销测算（I4-6 直线法或 I4-7 工作量法）',
      sheetHint: 'I4-6',
    })
  } else if (amortRows.length && i41.length) {
    let calcAmort = 0
    for (const r of amortRows) {
      const annual = _num(r.yearTotal ?? r.annualTotal ?? r.calcPeriodAmort)
      if (annual > 0) {
        calcAmort += annual
        continue
      }
      const monthly = Array.isArray(r.monthlyAmorts)
        ? (r.monthlyAmorts as number[]).reduce((s, v) => s + _num(v), 0)
        : Array.isArray(r.monthlyAmort)
          ? (r.monthlyAmort as number[]).reduce((s, v) => s + _num(v), 0)
          : 0
      calcAmort += monthly
    }
    calcAmort = _round2(calcAmort)
    const amortDiff = _round2(adjAmort - calcAmort)
    if (Math.abs(amortDiff) > 0.01 && calcAmort > 0) {
      items.push({
        id: 'i41-vs-amort',
        code: 'I4-1',
        area: '审定↔测算',
        level: 'warn',
        message: `审定本期摊销与 I4-6/7 测算差 ${amortDiff.toFixed(2)}（可点「从 I4-6/7 同步摊销」或生成补提草稿）`,
        sheetHint: 'I4-1',
      })
    } else if (calcAmort > 0) {
      items.push({
        id: 'i46-ok',
        code: 'I4-6',
        area: '摊销测算',
        level: 'ok',
        message: `摊销测算 ${amortRows.length} 行，与审定摊销勾稽一致`,
        sheetHint: i46.length ? 'I4-6' : 'I4-7',
      })
    }
  }

  // 附注 vs 审定（统一走 shared reconcile）
  const discRec = reconcileI4DisclosureVsAdj(map)
  if (discRec.hasBoth && !discRec.matched) {
    items.push({
      id: 'i4-disc-vs-adj',
      code: '附注',
      area: '附注↔审定',
      level: 'error',
      message: `附注期末合计 ${discRec.disclosureTotal.toFixed(2)} 与审定合计 ${discRec.adjudicatedTotal.toFixed(2)} 差 ${discRec.diff.toFixed(2)}`,
      sheetHint: '附注上市',
    })
  } else if (discRec.hasBoth && discRec.matched) {
    items.push({
      id: 'i4-disc-ok',
      code: '附注',
      area: '附注↔审定',
      level: 'ok',
      message: '附注期末与审定合计勾稽一致',
      sheetHint: '附注上市',
    })
  } else if (i41.length && !discRec.hasBoth) {
    items.push({
      id: 'i4-disc-empty',
      code: '附注',
      area: '附注披露',
      level: 'info',
      message: '审定已完成，建议同步编制附注披露',
      sheetHint: '附注上市',
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
