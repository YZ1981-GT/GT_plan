/**
 * i2CapitalizationModel — I2-6 研发项目资本化时点判断纯模型
 *
 * 对齐致同/事务所 Excel「研发项目资本化时点判断 I2-6」：
 *   项目信息 → 研究/开发阶段 → 预算构成 → 人员 → 资本化时点/依据
 *   → CAS6 五条件 → 确认无形资产金额/勾稽/进度/证据/索引
 */
import {
  type CAS6Condition,
  type CapitalizationResult,
  createEmptyCAS6Conditions,
  evaluateCapitalization,
  CAS6_CONDITION_NAMES,
} from './useI2CapitalizationEngine'

export type I2Yn = 'Y' | 'N' | ''

export interface I2CapitalizationProjectRow {
  rowId: string
  /** 项目编号 */
  projectNo: string
  /** 研发项目名称 */
  projectName: string
  /** 研究阶段支出 */
  researchAmount: number
  /** 开发阶段支出 */
  developmentAmount: number
  /** 研发项目具体内容 */
  projectContent: string
  /** 预算：直接材料 */
  budgetMaterial: number
  /** 预算：直接人工 */
  budgetLabor: number
  /** 预算：其他费用 */
  budgetOther: number
  /** 研发人员构成 */
  personnelComposition: string
  /** 资本化开始时点 */
  capStartDate: string
  /** 资本化的具体依据 */
  capBasis: string
  /** CAS6 五条件 */
  conditions: CAS6Condition[]
  /** 确认为无形资产金额 */
  recognizedIaAmount: number
  /** 是否与无形资产明细勾稽一致 */
  ledgerConsistent: I2Yn
  /** 截至期末的研发进度 */
  progress: string
  /** 支持性证据 */
  supportingEvidence: string
  /** 索引 */
  indexRef: string
  /** 立项/计划开始日（时点校验用） */
  projectStartDate: string
  /** 验收/完成日（时点校验用） */
  acceptanceDate: string
  /** 转入无形资产日期（可自 I2-2 带入） */
  transferDate: string
  /** 条件级附件总览（可选） */
  attachments: string[]
  /** 行备注 */
  remark: string
}

export interface I2CapitalizationSummary {
  projectCount: number
  metCount: number
  notMetCount: number
  pendingCount: number
  totalResearch: number
  totalDevelopment: number
  totalRecognizedIa: number
  ledgerInconsistentCount: number
}

function _num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function _str(v: unknown): string {
  return v == null ? '' : String(v)
}

function _yn(v: unknown): I2Yn {
  const s = String(v ?? '').trim().toUpperCase()
  if (s === 'Y' || s === '是' || s === '√' || s === '一致') return 'Y'
  if (s === 'N' || s === '否' || s === '×' || s === '不一致') return 'N'
  return ''
}

export function genI26RowId(): string {
  return `i26-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
}

export function emptyI2CapitalizationRow(
  partial?: Partial<I2CapitalizationProjectRow>,
): I2CapitalizationProjectRow {
  const { conditions: partialConditions, ...rest } = partial ?? {}
  return {
    rowId: rest.rowId || genI26RowId(),
    projectNo: '',
    projectName: '',
    researchAmount: 0,
    developmentAmount: 0,
    projectContent: '',
    budgetMaterial: 0,
    budgetLabor: 0,
    budgetOther: 0,
    personnelComposition: '',
    capStartDate: '',
    capBasis: '',
    recognizedIaAmount: 0,
    ledgerConsistent: '',
    progress: '',
    supportingEvidence: '',
    indexRef: '',
    projectStartDate: '',
    acceptanceDate: '',
    transferDate: '',
    attachments: [],
    remark: '',
    ...rest,
    conditions: partialConditions?.length
      ? normalizeConditions(partialConditions)
      : createEmptyCAS6Conditions(),
  }
}

export function normalizeConditions(raw: any[]): CAS6Condition[] {
  const base = createEmptyCAS6Conditions()
  if (!Array.isArray(raw)) return base
  for (const c of raw) {
    const id = Number(c?.id) as 1 | 2 | 3 | 4 | 5
    if (![1, 2, 3, 4, 5].includes(id)) continue
    const idx = id - 1
    const result = (c?.result === 'yes' || c?.result === 'no' || c?.result === 'na')
      ? c.result
      : ''
    base[idx] = {
      id,
      name: CAS6_CONDITION_NAMES[id],
      result,
      evidence: _str(c?.evidence),
      attachments: Array.isArray(c?.attachments) ? c.attachments.map(_str).filter(Boolean) : [],
    }
  }
  return base
}

export function normalizeI2CapitalizationRow(raw: any): I2CapitalizationProjectRow {
  return emptyI2CapitalizationRow({
    rowId: _str(raw?.rowId) || undefined,
    projectNo: _str(raw?.projectNo),
    projectName: _str(raw?.projectName || raw?.name),
    researchAmount: _num(raw?.researchAmount),
    developmentAmount: _num(raw?.developmentAmount),
    projectContent: _str(raw?.projectContent || raw?.content),
    budgetMaterial: _num(raw?.budgetMaterial),
    budgetLabor: _num(raw?.budgetLabor),
    budgetOther: _num(raw?.budgetOther),
    personnelComposition: _str(raw?.personnelComposition || raw?.personnel),
    capStartDate: _str(raw?.capStartDate || raw?.date),
    capBasis: _str(raw?.capBasis || raw?.basis),
    conditions: normalizeConditions(raw?.conditions),
    recognizedIaAmount: _num(raw?.recognizedIaAmount || raw?.iaAmount),
    ledgerConsistent: _yn(raw?.ledgerConsistent),
    progress: _str(raw?.progress),
    supportingEvidence: _str(raw?.supportingEvidence || raw?.evidence),
    indexRef: _str(raw?.indexRef),
    projectStartDate: _str(raw?.projectStartDate),
    acceptanceDate: _str(raw?.acceptanceDate),
    transferDate: _str(raw?.transferDate),
    attachments: Array.isArray(raw?.attachments) ? raw.attachments.map(_str).filter(Boolean) : [],
    remark: _str(raw?.remark),
  })
}

/** 旧版 Map 持久化：{ [projectName]: { conditions, date } } → 行数组 */
export function migrateLegacyCapitalizationMap(raw: unknown): I2CapitalizationProjectRow[] {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return []
  const out: I2CapitalizationProjectRow[] = []
  for (const [name, data] of Object.entries(raw as Record<string, any>)) {
    if (!name || name === '合计') continue
    if (!data || typeof data !== 'object') continue
    // 跳过像 sections 这类非项目 key
    if (!('conditions' in data) && !('date' in data)) continue
    out.push(emptyI2CapitalizationRow({
      projectName: name,
      capStartDate: _str(data.date),
      conditions: normalizeConditions(data.conditions),
    }))
  }
  return out
}

export function getRowCapResult(row: I2CapitalizationProjectRow): CapitalizationResult {
  return evaluateCapitalization(row.conditions)
}

export function summarizeI2Capitalization(rows: I2CapitalizationProjectRow[]): I2CapitalizationSummary {
  let metCount = 0
  let notMetCount = 0
  let pendingCount = 0
  let totalResearch = 0
  let totalDevelopment = 0
  let totalRecognizedIa = 0
  let ledgerInconsistentCount = 0

  for (const r of rows) {
    if (!r.projectName && !r.developmentAmount && !r.researchAmount) continue
    const result = getRowCapResult(r)
    const filled = r.conditions.some((c) => c.result === 'yes' || c.result === 'no')
    if (result.isMet) metCount++
    else if (!filled) pendingCount++
    else notMetCount++
    totalResearch += r.researchAmount
    totalDevelopment += r.developmentAmount
    totalRecognizedIa += r.recognizedIaAmount
    if (r.ledgerConsistent === 'N') ledgerInconsistentCount++
  }

  return {
    projectCount: rows.filter((r) => r.projectName || r.developmentAmount || r.researchAmount).length,
    metCount,
    notMetCount,
    pendingCount,
    totalResearch: Math.round(totalResearch * 100) / 100,
    totalDevelopment: Math.round(totalDevelopment * 100) / 100,
    totalRecognizedIa: Math.round(totalRecognizedIa * 100) / 100,
    ledgerInconsistentCount,
  }
}

/** 从 I2-2 明细带入项目名与资本化起点 */
export function seedRowsFromI2Detail(detailRows: any[]): I2CapitalizationProjectRow[] {
  const out: I2CapitalizationProjectRow[] = []
  for (const r of detailRows ?? []) {
    const name = _str(r?.projectName || r?.name).trim()
    if (!name || name === '合计') continue
    out.push(emptyI2CapitalizationRow({
      projectName: name,
      projectNo: _str(r?.projectNo || r?.code),
      capStartDate: _str(r?.capStartDate),
      transferDate: _str(r?.transferDate),
      developmentAmount: _num(r?.capIncrease) || _num(r?.capEndAmount),
      researchAmount: _num(r?.expensedAmount),
      recognizedIaAmount: _num(r?.transferToI1) || _num(r?.capDecrease),
      remark: '自I2-2带入',
    }))
  }
  return out
}

export function buildI26ConclusionDraft(summary: I2CapitalizationSummary): string {
  const parts = [
    `经检查，共评价研发项目 ${summary.projectCount} 项：`,
    `五条件同时满足可资本化 ${summary.metCount} 项，`,
    `不满足 ${summary.notMetCount} 项，待评价 ${summary.pendingCount} 项。`,
  ]
  if (summary.metCount > 0) {
    parts.push(`可资本化项目开发阶段支出合计 ${summary.totalDevelopment.toFixed(2)} 元；`)
  }
  if (summary.ledgerInconsistentCount > 0) {
    parts.push(`其中 ${summary.ledgerInconsistentCount} 项与无形资产明细勾稽不一致，需跟进。`)
  } else if (summary.notMetCount === 0 && summary.pendingCount === 0 && summary.projectCount > 0) {
    parts.push('资本化时点判断与 CAS6 第9条要求相符，研究/开发阶段划分未见重大异常。')
  } else {
    parts.push('请对未满足及待评价项目补充证据或调整费用化/资本化归集。')
  }
  return parts.join('')
}

export interface I26GateIssue {
  projectName: string
  level: 'error' | 'warning'
  message: string
}

/** 资本化闸门：有资本化金额/时点但五条件未齐 → error */
export function validateI26CapGate(rows: I2CapitalizationProjectRow[]): I26GateIssue[] {
  const out: I26GateIssue[] = []
  for (const r of rows) {
    const name = (r.projectName || '').trim() || '未命名'
    const met = getRowCapResult(r).isMet
    if ((r.recognizedIaAmount > 0.01 || (r.capStartDate && r.developmentAmount > 0.01)) && !met) {
      out.push({
        projectName: name,
        level: 'error',
        message: `已填资本化时点或确认无形资产金额，但五条件未同时满足，不得资本化/回写 I2-2`,
      })
    }
    if (r.developmentAmount > 0.01 && !met && !r.conditions.some((c) => c.result === 'yes' || c.result === 'no')) {
      out.push({
        projectName: name,
        level: 'warning',
        message: `有开发阶段金额 ${r.developmentAmount.toFixed(2)} 但尚未评价五条件`,
      })
    }
  }
  return out
}

/** 时点合理性：立项 ≤ 资本化 ≤ 验收/转入 */
export function validateI26CapTiming(row: I2CapitalizationProjectRow): string[] {
  const msgs: string[] = []
  const cap = row.capStartDate
  if (!cap) return msgs
  if (row.projectStartDate && cap < row.projectStartDate) {
    msgs.push(`资本化时点(${cap})早于立项/计划开始日(${row.projectStartDate})`)
  }
  if (row.acceptanceDate && cap > row.acceptanceDate) {
    msgs.push(`资本化时点(${cap})晚于验收日(${row.acceptanceDate})，请核实是否应为费用化或调整时点`)
  }
  if (row.transferDate && cap > row.transferDate) {
    msgs.push(`资本化时点(${cap})晚于转入无形资产日(${row.transferDate})`)
  }
  return msgs
}

export interface I26AmountReconcile {
  projectName: string
  i26Development: number
  i27Capitalized: number
  i22CapIncrease: number
  i26RecognizedIa: number
  i22Transfer: number
  messages: string[]
}

/** 与 I2-7 / I2-2 金额勾稽（按项目名） */
export function reconcileI26Amounts(
  rows: I2CapitalizationProjectRow[],
  i27Rows: any[],
  i22Rows: any[],
): I26AmountReconcile[] {
  const i27Map = new Map<string, number>()
  for (const r of i27Rows ?? []) {
    const name = _str(r?.projectName).trim()
    if (!name || name === '合计') continue
    const cap = _num(r?.increase?.capitalized ?? r?.audited?.capitalized ?? r?.capitalized)
    i27Map.set(name, (i27Map.get(name) || 0) + cap)
  }
  const i22Map = new Map<string, { increase: number; transfer: number; transferDate: string; capStart: string }>()
  for (const r of i22Rows ?? []) {
    const name = _str(r?.projectName || r?.name).trim()
    if (!name || name === '合计') continue
    i22Map.set(name, {
      increase: _num(r?.capIncrease ?? r?.unadjIncrease ?? r?.capitalizedIncrease),
      transfer: _num(r?.transferToI1 ?? r?.transferToIntangible ?? r?.capDecrease),
      transferDate: _str(r?.transferDate),
      capStart: _str(r?.capStartDate ?? r?.capitalizeDate),
    })
  }

  const out: I26AmountReconcile[] = []
  for (const row of rows) {
    const name = (row.projectName || '').trim()
    if (!name) continue
    const i27 = i27Map.get(name) ?? 0
    const i22 = i22Map.get(name)
    const messages: string[] = []
    if (i27 > 0 && Math.abs(row.developmentAmount - i27) > 0.01) {
      messages.push(`开发阶段 ${row.developmentAmount.toFixed(2)} ≠ I2-7资本化 ${i27.toFixed(2)}`)
    }
    if (i22 && i22.increase > 0 && Math.abs(row.developmentAmount - i22.increase) > 0.01) {
      messages.push(`开发阶段 ${row.developmentAmount.toFixed(2)} ≠ I2-2本期增加 ${i22.increase.toFixed(2)}`)
    }
    if (i22 && i22.transfer > 0 && row.recognizedIaAmount > 0
      && Math.abs(row.recognizedIaAmount - i22.transfer) > 0.01) {
      messages.push(`确认无形资产 ${row.recognizedIaAmount.toFixed(2)} ≠ I2-2转入 ${i22.transfer.toFixed(2)}`)
    }
    if (messages.length) {
      out.push({
        projectName: name,
        i26Development: row.developmentAmount,
        i27Capitalized: i27,
        i22CapIncrease: i22?.increase ?? 0,
        i26RecognizedIa: row.recognizedIaAmount,
        i22Transfer: i22?.transfer ?? 0,
        messages,
      })
    }
  }
  return out
}

export {
  evaluateCapitalization,
  createEmptyCAS6Conditions,
  suggestCas6ConditionsFromText,
  CAS6_CONDITION_NAMES,
  CAS6_CONDITION_ANALYSIS,
  CAS6_CONDITION_EXAMPLES,
  CAS6_OBJECTIVES,
  CAS6_PROCEDURE_HINTS,
  type CAS6Condition,
  type CapitalizationResult,
} from './useI2CapitalizationEngine'
