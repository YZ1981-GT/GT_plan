/**
 * H2-14 在建工程监盘小结 — 数据结构、读入归一、完工程度闸门、逻辑提示、回填与规则起草
 *
 * 结构逐段对齐致同模板「监盘小结H2-14」（backend/wp_templates/H/H2 在建工程.xlsx）：
 * 一、资产负债表日 → 二、察看前检查程序 → 三、人员及时间 → 四(一) 逐个工程形象进度 /
 * 四(二) 察看总体情况六问 → 五、异常 → 六、结束工作（评价 / 差异说明盖章 / 签字确认）→ 结论
 *
 * 🔴 原先 H2-14 页面绑定的这些字段与操作在 useH2Stocktake 里都不存在：页面渲染即读
 *    `state.completenessOk.value` 报错，且读入只保留 5 个字段 ⇒ 其余填写保存后再打开就丢。
 *    参照 H1-11（h1StocktakeSummaryModel）补齐。
 */
import type { H2StocktakeCheckRow } from './h2StocktakeCheckModel'
import type { H2StocktakePlanForm } from './h2StocktakePlanModel'

export interface StocktakeAbnormalItem {
  rowId: string
  name: string
  abnormalType: string
  description: string
  suggestion: string
}

export interface H2SummaryPersonnelRow {
  rowId: string
  department: string
  headcount: number
  names: string
  responsibleArea: string
}

export interface H2SummaryAuditorRow {
  rowId: string
  names: string
  responsibleArea: string
}

export interface H2SummaryObservationRow {
  rowId: string
  projectName: string
  diagramIndex: string
  location: string
  constructionStatus: string
  progressDescription: string
  photoIndex: string
}

export interface H2SummaryCheckItem {
  id: string
  label: string
  answer: string
  indexRef: string
}

export type YesNo = '' | 'Y' | 'N'

export interface H2StocktakeSummary {
  bsDateNote: string
  engDept: string
  engStaff: string
  policyDesignOk: string
  policyExecutedOk: string
  policyIndex: string
  clientPersonnel: H2SummaryPersonnelRow[]
  auditorPersonnel: H2SummaryAuditorRow[]
  actualDate: string
  startTime: string
  endTime: string
  projectObservations: H2SummaryObservationRow[]
  observationChecks: H2SummaryCheckItem[]
  overallSituation: string
  abnormalProjects: StocktakeAbnormalItem[]
  abnormalNote: string
  postWorkNote: string
  evalFamiliarity: string
  evalAttitude: string
  evalCooperation: string
  diffExplanationObtained: YesNo
  diffExplanationIndex: string
  clientSigned: YesNo
  clientSignIndex: string
  conclusion: string
  preparedBy: string
  preparedDate: string
  reviewedBy: string
  reviewedDate: string
  lastAutoSyncAt: string
}

/** 模板「四、（二）察看总体情况描述」六问（原文） */
export const OBSERVATION_CHECK_DEFS: { id: string; label: string }[] = [
  { id: 'qtyMatch', label: '实际观察到的在建工程是否与会计账簿记载数量一致' },
  { id: 'offBook', label: '是否存在会计账簿未记载的工程' },
  { id: 'diagramMatch', label: '获取的工程简图与现场是否一致' },
  { id: 'progressMatch', label: '现场察看的工程完工进度是否与账面记载一致，并与监理报告核对一致' },
  { id: 'readyNotTransferred', label: '有无已达到预计可使用状态但尚未办理竣工决算手续仍列于在建工程的情况' },
  { id: 'longStopped', label: '有无长期停工的工程' },
]

function _id(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

const _s = (v: unknown): string => (v == null ? '' : String(v))
const _yn = (v: unknown): YesNo => (v === 'Y' || v === 'N' ? v : '')

export function createEmptySummary(): H2StocktakeSummary {
  return {
    bsDateNote: '',
    engDept: '',
    engStaff: '',
    policyDesignOk: '',
    policyExecutedOk: '',
    policyIndex: '',
    clientPersonnel: [],
    auditorPersonnel: [],
    actualDate: '',
    startTime: '',
    endTime: '',
    projectObservations: [],
    observationChecks: OBSERVATION_CHECK_DEFS.map((d) => ({ ...d, answer: '', indexRef: '' })),
    overallSituation: '',
    abnormalProjects: [],
    abnormalNote: '',
    postWorkNote: '',
    evalFamiliarity: '',
    evalAttitude: '',
    evalCooperation: '',
    diffExplanationObtained: '',
    diffExplanationIndex: '',
    clientSigned: '',
    clientSignIndex: '',
    conclusion: '',
    preparedBy: '',
    preparedDate: '',
    reviewedBy: '',
    reviewedDate: '',
    lastAutoSyncAt: '',
  }
}

export function newClientPersonnelRow(partial?: Partial<H2SummaryPersonnelRow>): H2SummaryPersonnelRow {
  return { rowId: _id('cp'), department: '', headcount: 1, names: '', responsibleArea: '', ...partial }
}

export function newAuditorRow(partial?: Partial<H2SummaryAuditorRow>): H2SummaryAuditorRow {
  return { rowId: _id('ap'), names: '', responsibleArea: '', ...partial }
}

export function newObservationRow(partial?: Partial<H2SummaryObservationRow>): H2SummaryObservationRow {
  return {
    rowId: _id('ob'), projectName: '', diagramIndex: '', location: '',
    constructionStatus: '', progressDescription: '', photoIndex: '', ...partial,
  }
}

export function newAbnormalItem(partial?: Partial<StocktakeAbnormalItem>): StocktakeAbnormalItem {
  return { rowId: _id('row'), name: '', abnormalType: '', description: '', suggestion: '', ...partial }
}

/** 读入已存 JSON：全部字段按类型归一，缺省补齐（旧版只存了 5 个字段也能读） */
export function normalizeSummary(raw: any): H2StocktakeSummary {
  const base = createEmptySummary()
  if (!raw || typeof raw !== 'object') return base
  const rows = (v: unknown): any[] => (Array.isArray(v) ? v : [])
  const checks = rows(raw.observationChecks)
  return {
    ...base,
    bsDateNote: _s(raw.bsDateNote),
    engDept: _s(raw.engDept),
    engStaff: _s(raw.engStaff),
    policyDesignOk: _s(raw.policyDesignOk),
    policyExecutedOk: _s(raw.policyExecutedOk),
    policyIndex: _s(raw.policyIndex),
    clientPersonnel: rows(raw.clientPersonnel).map((r) => newClientPersonnelRow({
      rowId: r?.rowId || _id('cp'), department: _s(r?.department), headcount: Number(r?.headcount) || 0,
      names: _s(r?.names), responsibleArea: _s(r?.responsibleArea),
    })),
    auditorPersonnel: rows(raw.auditorPersonnel).map((r) => newAuditorRow({
      rowId: r?.rowId || _id('ap'), names: _s(r?.names), responsibleArea: _s(r?.responsibleArea),
    })),
    actualDate: _s(raw.actualDate),
    startTime: _s(raw.startTime),
    endTime: _s(raw.endTime),
    projectObservations: rows(raw.projectObservations).map((r) => newObservationRow({
      rowId: r?.rowId || _id('ob'), projectName: _s(r?.projectName), diagramIndex: _s(r?.diagramIndex),
      location: _s(r?.location), constructionStatus: _s(r?.constructionStatus),
      progressDescription: _s(r?.progressDescription), photoIndex: _s(r?.photoIndex),
    })),
    observationChecks: OBSERVATION_CHECK_DEFS.map((d) => {
      const found = checks.find((c) => c?.id === d.id)
      return { ...d, answer: _s(found?.answer), indexRef: _s(found?.indexRef) }
    }),
    overallSituation: _s(raw.overallSituation),
    abnormalProjects: rows(raw.abnormalProjects).map((a) => newAbnormalItem({
      rowId: a?.rowId || _id('row'), name: _s(a?.name), abnormalType: _s(a?.abnormalType),
      description: _s(a?.description), suggestion: _s(a?.suggestion),
    })),
    abnormalNote: _s(raw.abnormalNote),
    postWorkNote: _s(raw.postWorkNote),
    evalFamiliarity: _s(raw.evalFamiliarity),
    evalAttitude: _s(raw.evalAttitude),
    evalCooperation: _s(raw.evalCooperation),
    diffExplanationObtained: _yn(raw.diffExplanationObtained),
    diffExplanationIndex: _s(raw.diffExplanationIndex),
    clientSigned: _yn(raw.clientSigned),
    clientSignIndex: _s(raw.clientSignIndex),
    conclusion: _s(raw.conclusion),
    preparedBy: _s(raw.preparedBy),
    preparedDate: _s(raw.preparedDate),
    reviewedBy: _s(raw.reviewedBy),
    reviewedDate: _s(raw.reviewedDate),
    lastAutoSyncAt: _s(raw.lastAutoSyncAt),
  }
}

/** 结束时间须晚于开始时间（HH:mm；任一为空不判） */
export function isTimeRangeValid(start: string, end: string): boolean {
  const toMin = (t: string) => {
    const m = /^(\d{1,2}):(\d{2})$/.exec(t || '')
    return m ? Number(m[1]) * 60 + Number(m[2]) : null
  }
  const a = toMin(start)
  const b = toMin(end)
  return a == null || b == null || b > a
}

export interface CompletenessItem {
  id: string
  label: string
  ok: boolean
  hint: string
}

/** 完工程度闸门：签署前应补齐的项（不阻断签署，只提示） */
export function evaluateSummaryCompleteness(s: H2StocktakeSummary): CompletenessItem[] {
  const filled = (v: string) => v.trim().length > 0
  return [
    { id: 'bsDate', label: '资产负债表日说明', ok: filled(s.bsDateNote), hint: '说明察看日与资产负债表日的关系' },
    { id: 'pre', label: '察看前检查程序', ok: filled(s.engDept) && filled(s.policyDesignOk), hint: '填写工程管理部门与制度评价' },
    {
      id: 'people', label: '参与人员', ok: s.clientPersonnel.length > 0 && s.auditorPersonnel.length > 0,
      hint: '被审计单位人员与审计人员各至少一行',
    },
    {
      id: 'time', label: '实际察看日及时间',
      ok: filled(s.actualDate) && filled(s.startTime) && filled(s.endTime) && isTimeRangeValid(s.startTime, s.endTime),
      hint: '填写日期、开始与结束时间（结束须晚于开始）',
    },
    { id: 'obs', label: '逐个工程形象进度', ok: s.projectObservations.length > 0, hint: '可从 H2-13 回填' },
    {
      id: 'checks', label: '察看总体情况六问', ok: s.observationChecks.every((c) => filled(c.answer)),
      hint: `尚有 ${s.observationChecks.filter((c) => !filled(c.answer)).length} 问未答`,
    },
    {
      id: 'diff', label: '差异说明盖章与签字确认', ok: s.diffExplanationObtained === 'Y' && s.clientSigned === 'Y',
      hint: '取得盖章《工程现场察看差异说明》并请被审计单位人员签字',
    },
    { id: 'conclusion', label: '审计结论', ok: filled(s.conclusion), hint: '可点「规则起草」生成草稿' },
  ]
}

/** 与 H2-13 交叉的逻辑提示 */
export function summaryLogicWarnings(s: H2StocktakeSummary, checkRows: H2StocktakeCheckRow[],
  isStopped: (r: H2StocktakeCheckRow) => boolean): string[] {
  const out: string[] = []
  if (!isTimeRangeValid(s.startTime, s.endTime)) out.push('察看结束时间早于或等于开始时间')
  const stopped = checkRows.filter(isStopped).map((r) => r.name).filter(Boolean)
  const abnormalNames = new Set(s.abnormalProjects.map((a) => a.name.trim()))
  const missing = stopped.filter((n) => !abnormalNames.has(n.trim()))
  if (missing.length) out.push(`H2-13 停工工程未列入异常：${missing.slice(0, 5).join('、')}${missing.length > 5 ? ' 等' : ''}`)
  const ready = checkRows.filter((r) => r.readyForUse === '是').length
  const q5 = s.observationChecks.find((c) => c.id === 'readyNotTransferred')
  if (ready > 0 && q5 && !q5.answer.trim()) out.push(`H2-13 有 ${ready} 项已达预定可使用状态，第 5 问未作答（关注转固 H2-5）`)
  if (s.diffExplanationObtained === 'Y' && !s.diffExplanationIndex.trim()) out.push('已取得差异说明但未填索引')
  if (s.clientSigned === 'Y' && !s.clientSignIndex.trim()) out.push('被审计单位已签字但未填索引')
  return out
}

/** 由 H2-13 行生成逐个工程观察行 */
export function observationsFromCheckRows(rows: H2StocktakeCheckRow[]): H2SummaryObservationRow[] {
  return rows
    .filter((r) => r.name && r.name.trim())
    .map((r) => newObservationRow({
      projectName: r.name,
      location: r.location || '',
      constructionStatus: r.constructionStatus || '',
      progressDescription: r.progressDesc || '',
      photoIndex: r.photoUrl ? 'H2-13' : '',
    }))
}

/** 从 H2-12 计划 / H2-13 检查表回填：只填空字段，已填的不覆盖 */
export function fillSummaryFromUpstream(s: H2StocktakeSummary, plan: H2StocktakePlanForm,
  checkRows: H2StocktakeCheckRow[]): number {
  let n = 0
  const setIfEmpty = (key: 'actualDate' | 'engDept' | 'policyIndex', v: string) => {
    if (!s[key].trim() && v.trim()) { s[key] = v; n++ }
  }
  setIfEmpty('actualDate', plan.plannedDate || '')
  setIfEmpty('engDept', plan.icResponsible || '')
  setIfEmpty('policyIndex', plan.icSystemIndex || '')
  if (!s.projectObservations.length) {
    const obs = observationsFromCheckRows(checkRows)
    if (obs.length) { s.projectObservations = obs; n++ }
  }
  if (!s.auditorPersonnel.length && plan.plannedLead.trim()) {
    s.auditorPersonnel = [newAuditorRow({ names: plan.plannedLead, responsibleArea: '现场察看负责人' })]
    n++
  }
  return n
}

/** 把 H2-13 的停工 / 差异行并入异常（按工程名去重） */
export function mergeAbnormalFromCheckRows(s: H2StocktakeSummary, rows: H2StocktakeCheckRow[],
  isStopped: (r: H2StocktakeCheckRow) => boolean): number {
  const existing = new Set(s.abnormalProjects.map((a) => a.name.trim()))
  let n = 0
  for (const r of rows) {
    const name = (r.name || '').trim()
    if (!name || existing.has(name)) continue
    if (isStopped(r)) {
      s.abnormalProjects.push(newAbnormalItem({
        name, abnormalType: '停工', description: [r.stopReason, r.stopDuration].filter(Boolean).join('；'),
        suggestion: '关注减值',
      }))
    } else if (r.result === '盘盈' || r.result === '盘亏') {
      s.abnormalProjects.push(newAbnormalItem({
        name, abnormalType: '其他', description: `${r.result}${r.diffReason ? '：' + r.diffReason : ''}`,
        suggestion: '追加说明',
      }))
    } else if (r.readyForUse === '是') {
      s.abnormalProjects.push(newAbnormalItem({
        name, abnormalType: '应转未转', description: '已达到预定可使用状态', suggestion: '关注转固(H2-5)',
      }))
    } else {
      continue
    }
    existing.add(name)
    n++
  }
  return n
}

/** 规则起草结论（只用已填事实，不编造） */
export function draftSummaryConclusion(s: H2StocktakeSummary, stats: { total: number; stopped: number; completed: number }): string {
  const parts: string[] = []
  const when = s.actualDate ? `${s.actualDate}` : '实际察看日'
  parts.push(`我们于${when}对在建工程实施了现场察看，共察看 ${stats.total || s.projectObservations.length} 个工程项目。`)
  const stoppedCount = s.abnormalProjects.filter((a) => a.abnormalType === '停工').length || stats.stopped
  if (stoppedCount > 0) parts.push(`其中 ${stoppedCount} 项处于停工状态，已联动 H2-15 关注减值。`)
  const notTransferred = s.abnormalProjects.filter((a) => a.abnormalType === '应转未转').length
  if (notTransferred > 0) parts.push(`${notTransferred} 项已达到预定可使用状态尚未转固，已联动 H2-5 检查转固时点。`)
  const others = s.abnormalProjects.length - stoppedCount - notTransferred
  if (others > 0) parts.push(`另发现 ${others} 项其他异常，详见第五部分。`)
  if (s.abnormalProjects.length === 0) parts.push('未发现异常情况。')
  if (s.diffExplanationObtained === 'Y') parts.push('已取得盖章的《工程现场察看差异说明》。')
  parts.push('（以上为按已填写内容生成的草稿，请复核后据实修改。）')
  return parts.join('')
}
