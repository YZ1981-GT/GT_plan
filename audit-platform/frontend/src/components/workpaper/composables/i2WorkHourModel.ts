/**
 * I2-10 研发人员工时检查表 — 纯模型
 * 对齐致同源表：项目→人员→工时→分配依据→薪酬计提→附件索引
 * 数字增强：同期总工时/占比（对应编制说明中兼职分功能工时统计）
 *
 * 持久化字段位于 I2TabWorkHourCheck.vue（未抽取独立 composable，逻辑量较小）：
 * load/save/normalize 直接内联；此处集中导出 STORAGE_KEY 供该 Vue 及跨sheet引用共用，避免字符串硬编码分裂。
 */

/** checklist_responses item_id：行数据 / 审计说明 / 审计结论（供 I2TabWorkHourCheck.vue 共用） */
export const I2_WORKHOUR_STORAGE_KEY = 'I2-10-rows'
export const I2_WORKHOUR_AUDIT_NOTE_KEY = 'I2-10-audit-note'
export const I2_WORKHOUR_AUDIT_CONCLUSION_KEY = 'I2-10-audit-conclusion'

export const I2_WORKHOUR_OBJECTIVES = [
  '确认利润表中记录的研发费用已发生，与被审计单位有关，且已记录于恰当的账户（发生、权利和义务、分类）。',
  '确认与研发费用有关的金额及其他数据已恰当记录，相关披露已得到恰当计量和描述（准确性、计价和分摊、列报）。',
] as const

/** 编制说明（源表底部蓝色提示） */
export const I2_WORKHOUR_PREP_NOTES = [
  '发行人为非全时研发人员的，应按不同岗位功能清晰统计工时，并按工时占比将薪酬准确、合理分摊计入研发支出；分摊依据应可复核（工时表、考勤、项目任务书等）。',
  '研发人员薪酬计提应与工时记录、工资表及科目归集勾稽；资本化项目人工费应能追溯至具体人员与项目期间。',
  '若研发费用中包含股份支付，应有清晰、合理的分摊基础，并关注是否借股份支付调节研发投入指标。',
  '检查要素可根据实际情况自行增减；结论应与 I2-9 人员认定交叉印证（未认定人员原则上不应大额计入研发工时/薪酬）。',
] as const

export const I2_WORKHOUR_CONCLUSION_OPTIONS = [
  '合理',
  '偏高',
  '偏低',
  '待核实',
] as const

export const I2_WORKHOUR_BASIS_OPTIONS = [
  '工时表',
  '考勤记录',
  '项目任务书',
  '工时系统导出',
  '访谈+工时表',
  '其他',
] as const

/** 占比警戒：≥95% 视为偏高风险；≤20% 且有薪酬视为偏低关注 */
export const I2_WH_HIGH_RATIO = 0.95
export const I2_WH_LOW_RATIO = 0.2

export type I2WorkHourConclusion = (typeof I2_WORKHOUR_CONCLUSION_OPTIONS)[number] | string

export interface I2WorkHourCheckRow {
  rowId: string
  /** 项目名称 */
  projectName: string
  /** 项目号 */
  projectCode: string
  /** 项目起止时间 */
  projectPeriod: string
  /** 研发人员姓名 */
  staffName: string
  /** 月份 YYYY-MM（可选，便于分月抽查） */
  month: string
  /** 研发工时 */
  hours: number
  /** 同期总工时（分功能统计用） */
  totalHours: number
  /** 占比 = 研发工时/总工时（公式） */
  ratio: number
  /** 研发工时分配依据 */
  allocationBasis: string
  /** 研发薪酬计提 */
  salaryAccrual: number
  /** 可增减检查要素（对应 Excel「…」列） */
  customCheck: string
  /** 是否含股份支付 */
  hasShareBasedPay: 'Y' | 'N' | ''
  /** 附件索引号 */
  attachmentIndex: string
  /** 系统建议结论 */
  suggestedConclusion: I2WorkHourConclusion
  /** 人工结论 */
  conclusion: I2WorkHourConclusion
  /** 备注 */
  remark: string
}

export interface I2WorkHourSummary {
  totalCount: number
  totalHours: number
  totalSalary: number
  highRatioCount: number
  lowRatioCount: number
  missingBasisCount: number
  sharePayCount: number
  pendingCount: number
  abnormalCount: number
}

export interface I2WorkHourPrepValidation {
  ok: boolean
  messages: string[]
}

export interface I2WorkHourGateResult {
  ok: boolean
  messages: string[]
}

export interface I2WorkHourReconcileResult {
  ok: boolean
  diff: number
  diffRate: number | null
  message: string
}

function _num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function _genId(): string {
  return `i210-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
}

export function calcWorkHourRatio(hours: number, totalHours: number): number {
  if (totalHours <= 0) return 0
  return hours / totalHours
}

/** 隐含时薪（复核合理性，非 Excel 列） */
export function calcImpliedHourlyRate(salaryAccrual: number, hours: number): number | null {
  if (hours <= 0) return null
  return salaryAccrual / hours
}

/**
 * 建议结论：
 * - 工时>总工时 → 偏高（硬错误）
 * - 有工时无分配依据 → 待核实
 * - 占比≤20% 且有薪酬 → 偏低（兼职分摊不足关注）
 * - 占比≥95% 无依据 → 待核实；有依据则可为合理（全时研发）
 * - 有核心数据 → 合理
 */
export function suggestWorkHourConclusion(row: Pick<
  I2WorkHourCheckRow,
  'staffName' | 'hours' | 'totalHours' | 'ratio' | 'allocationBasis' | 'salaryAccrual'
>): I2WorkHourConclusion {
  if (!row.staffName?.trim() && row.hours <= 0 && row.salaryAccrual <= 0) return '待核实'

  const ratio = row.ratio > 0
    ? row.ratio
    : calcWorkHourRatio(row.hours, row.totalHours)
  const hasBasis = !!String(row.allocationBasis || '').trim()

  if (row.totalHours > 0 && row.hours > row.totalHours + 0.05) return '偏高'
  if (row.hours > 0 && !hasBasis) return '待核实'
  if (row.totalHours > 0 && ratio > 0 && ratio <= I2_WH_LOW_RATIO && row.salaryAccrual > 0.01) {
    return '偏低'
  }
  if (row.totalHours > 0 && ratio >= I2_WH_HIGH_RATIO && !hasBasis) return '待核实'
  if (row.hours > 0 || row.salaryAccrual > 0) return '合理'
  return '待核实'
}

export function recomputeI2WorkHourRow(row: I2WorkHourCheckRow, opts?: { refreshSuggested?: boolean }): I2WorkHourCheckRow {
  const hours = _num(row.hours)
  const totalHours = _num(row.totalHours)
  const salaryAccrual = _num(row.salaryAccrual)
  const ratio = calcWorkHourRatio(hours, totalHours)
  const next = {
    ...row,
    hours,
    totalHours,
    salaryAccrual,
    ratio,
  }
  const suggested = suggestWorkHourConclusion(next)
  next.suggestedConclusion = suggested
  if (opts?.refreshSuggested !== false) {
    if (!row.conclusion || row.conclusion === row.suggestedConclusion) {
      next.conclusion = suggested
    }
  }
  return next
}

export function emptyI2WorkHourRow(partial?: Partial<I2WorkHourCheckRow>): I2WorkHourCheckRow {
  return recomputeI2WorkHourRow({
    rowId: partial?.rowId || _genId(),
    projectName: '',
    projectCode: '',
    projectPeriod: '',
    staffName: '',
    month: '',
    hours: 0,
    totalHours: 0,
    ratio: 0,
    allocationBasis: '',
    salaryAccrual: 0,
    customCheck: '',
    hasShareBasedPay: '',
    attachmentIndex: '',
    suggestedConclusion: '待核实',
    conclusion: '',
    remark: '',
    ...partial,
  })
}

/** 兼容旧版：人员/项目/月份/工时/总工时/结论 */
export function normalizeI2WorkHourRow(raw: any): I2WorkHourCheckRow {
  const hours = _num(raw.hours)
  const totalHours = _num(raw.totalHours)
  return recomputeI2WorkHourRow({
    rowId: raw.rowId || _genId(),
    projectName: String(raw.projectName ?? ''),
    projectCode: String(raw.projectCode ?? ''),
    projectPeriod: String(raw.projectPeriod ?? ''),
    staffName: String(raw.staffName ?? ''),
    month: String(raw.month ?? ''),
    hours,
    totalHours,
    ratio: 0,
    allocationBasis: String(raw.allocationBasis ?? ''),
    salaryAccrual: _num(raw.salaryAccrual),
    customCheck: String(raw.customCheck ?? ''),
    hasShareBasedPay: (raw.hasShareBasedPay === 'Y' || raw.hasShareBasedPay === 'N')
      ? raw.hasShareBasedPay
      : '',
    attachmentIndex: String(raw.attachmentIndex ?? ''),
    suggestedConclusion: String(raw.suggestedConclusion ?? ''),
    conclusion: String(raw.conclusion ?? ''),
    remark: String(raw.remark ?? ''),
  }, { refreshSuggested: !raw.conclusion })
}

export function persistI2WorkHourRow(row: I2WorkHourCheckRow): Omit<I2WorkHourCheckRow, 'ratio'> & { ratio?: number } {
  const { ratio: _r, ...rest } = row
  return { ...rest, ratio: row.ratio }
}

export function summarizeI2WorkHourRows(rows: I2WorkHourCheckRow[]): I2WorkHourSummary {
  const s: I2WorkHourSummary = {
    totalCount: rows.length,
    totalHours: 0,
    totalSalary: 0,
    highRatioCount: 0,
    lowRatioCount: 0,
    missingBasisCount: 0,
    sharePayCount: 0,
    pendingCount: 0,
    abnormalCount: 0,
  }
  for (const r of rows) {
    s.totalHours += r.hours
    s.totalSalary += r.salaryAccrual
    if (r.totalHours > 0 && r.ratio >= I2_WH_HIGH_RATIO) s.highRatioCount++
    if (r.totalHours > 0 && r.ratio > 0 && r.ratio <= I2_WH_LOW_RATIO) s.lowRatioCount++
    if (r.hours > 0 && !r.allocationBasis.trim()) s.missingBasisCount++
    if (r.hasShareBasedPay === 'Y') s.sharePayCount++
    if (r.conclusion === '待核实' || r.suggestedConclusion === '待核实') s.pendingCount++
    if (r.conclusion === '偏高' || r.conclusion === '偏低' || r.suggestedConclusion === '偏高' || r.suggestedConclusion === '偏低') {
      s.abnormalCount++
    }
  }
  return s
}

export function validateI2WorkHourPrep(rows: I2WorkHourCheckRow[]): I2WorkHourPrepValidation {
  const messages: string[] = []
  for (const r of rows) {
    if (!r.staffName && !r.projectName && r.hours <= 0) continue
    const label = `「${r.staffName || '未命名'} / ${r.projectName || '未填项目'}」`
    if (r.hours > 0 && !r.allocationBasis.trim()) {
      messages.push(`${label}有研发工时但未填写分配依据`)
    }
    if (r.totalHours > 0 && r.hours > r.totalHours + 0.05) {
      messages.push(`${label}研发工时大于同期总工时`)
    }
    if (r.hasShareBasedPay === 'Y' && !r.customCheck.trim() && !r.remark.trim()) {
      messages.push(`${label}含股份支付，请在检查要素/备注说明分摊基础`)
    }
    if (r.salaryAccrual > 0 && r.hours <= 0) {
      messages.push(`${label}有薪酬计提但工时为 0，请核实`)
    }
  }
  return { ok: messages.length === 0, messages }
}

/** 从 I2-9 已认定人员带入（按参与项目拆行） */
export function seedWorkHourFromStaff(staffRows: any[]): I2WorkHourCheckRow[] {
  const out: I2WorkHourCheckRow[] = []
  for (const s of staffRows ?? []) {
    const name = String(s.staffName || '').trim()
    if (!name) continue
    const conclusion = String(s.conclusion || '')
    if (conclusion === '不予认定') continue

    const projectsRaw = String(s.projects || '').trim()
    const projects = projectsRaw
      ? projectsRaw.split(/[,，;；、/|]/).map((p: string) => p.trim()).filter(Boolean)
      : ['']

    const ratioPct = s.rdHourRatio != null && s.rdHourRatio !== '' ? _num(s.rdHourRatio) : null

    for (const projectName of projects) {
      out.push(emptyI2WorkHourRow({
        staffName: name,
        projectName,
        totalHours: ratioPct != null && ratioPct > 0 ? 100 : 0,
        hours: ratioPct != null && ratioPct > 0 ? ratioPct : 0,
        remark: '自I2-9带入',
        attachmentIndex: String(s.attachmentIndex || ''),
      }))
    }
  }
  return out
}

/** 从 I2-2 明细带入项目壳行（待填人员） */
export function seedWorkHourFromDetail(detailRows: any[]): I2WorkHourCheckRow[] {
  const out: I2WorkHourCheckRow[] = []
  for (const r of detailRows ?? []) {
    const projectName = String(r.projectName || r.name || '').trim()
    if (!projectName || projectName === '合计') continue
    const start = String(r.startDate || r.capStartDate || '').slice(0, 10)
    const end = String(r.endDate || '').slice(0, 10)
    const period = start || end ? `${start || '?'}-${end || '?'}` : ''
    out.push(emptyI2WorkHourRow({
      projectName,
      projectCode: String(r.projectCode || ''),
      projectPeriod: period,
      remark: '自I2-2带入',
    }))
  }
  return out
}

export function workHourRowRiskClass(row: I2WorkHourCheckRow): string {
  if (row.conclusion === '偏高' || row.suggestedConclusion === '偏高') return 'risk-high-row'
  if (row.conclusion === '偏低' || row.suggestedConclusion === '偏低') return 'risk-low-row'
  if (row.conclusion === '待核实' || row.suggestedConclusion === '待核实') return 'risk-pending-row'
  return ''
}

export function buildWorkHourConclusionDraft(summary: I2WorkHourSummary): string {
  const parts = [
    `经检查研发人员工时记录共 ${summary.totalCount} 条，研发工时合计 ${summary.totalHours.toFixed(1)} 小时，薪酬计提合计 ${summary.totalSalary.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} 元。`,
  ]
  if (summary.highRatioCount) {
    parts.push(`工时占比偏高 ${summary.highRatioCount} 条，已关注是否虚增研发投入；`)
  }
  if (summary.lowRatioCount) {
    parts.push(`工时占比偏低 ${summary.lowRatioCount} 条，已关注分摊是否充分；`)
  }
  if (summary.missingBasisCount) {
    parts.push(`缺分配依据 ${summary.missingBasisCount} 条，尚需补充；`)
  }
  if (summary.sharePayCount) {
    parts.push(`含股份支付 ${summary.sharePayCount} 条，已复核分摊基础；`)
  }
  if (summary.abnormalCount === 0 && summary.missingBasisCount === 0) {
    parts.push('抽查范围内研发工时分配及薪酬归集在重大方面未见异常。')
  } else {
    parts.push('上述异常/待核实事项已记录于审计说明，结论以最终核实为准。')
  }
  return parts.join('')
}

/**
 * I2-9 ↔ I2-10 硬闸门：工时/薪酬归集人员须为 I2-9 已认定为研发人员。
 * - accepted 集：conclusion === '认定为研发人员'（空/待核实视为 pending，不计入 accepted）
 * - rejected 集：conclusion === '不予认定'
 * - 工时表中有工时或薪酬计提但人员不在 accepted 集 → 闸门失败
 * - 若人员在 rejected 集但仍有工时/薪酬 → 单独提示（不予认定人员）
 */
export function validateWorkHourAgainstStaff(
  workHourRows: I2WorkHourCheckRow[],
  staffRows: Array<{ staffName?: string; conclusion?: string }>,
): I2WorkHourGateResult {
  const accepted = new Set<string>()
  const rejected = new Set<string>()
  for (const s of staffRows ?? []) {
    const name = String(s?.staffName || '').trim()
    if (!name) continue
    const conclusion = String(s?.conclusion || '').trim()
    if (conclusion === '认定为研发人员') accepted.add(name)
    else if (conclusion === '不予认定') rejected.add(name)
    // 空/待核实 → pending：既不在 accepted 也不在 rejected
  }

  const messages: string[] = []
  for (const row of workHourRows ?? []) {
    const name = String(row.staffName || '').trim()
    if (!name) continue
    const hasActivity = _num(row.hours) > 0 || _num(row.salaryAccrual) > 0.01
    if (!hasActivity) continue

    if (rejected.has(name)) {
      messages.push(`「${name}」已在 I2-9 中判定为「不予认定」，但工时表仍有工时/薪酬记录，请核实是否应剔除`)
    } else if (!accepted.has(name)) {
      messages.push(`「${name}」不在 I2-9 已认定研发人员名单中（未认定/待核实），但存在工时/薪酬记录`)
    }
  }
  return { ok: messages.length === 0, messages }
}

/** assertCanConclude 风格闸门：与 validateWorkHourAgainstStaff 语义一致，供「生成草稿」/结论前置校验调用 */
export function assertI2WorkHourCanConclude(
  workHourRows: I2WorkHourCheckRow[],
  staffRows: Array<{ staffName?: string; conclusion?: string }>,
): I2WorkHourGateResult {
  return validateWorkHourAgainstStaff(workHourRows, staffRows)
}

/**
 * 工时表薪酬合计 与 I2-5 人工费本期数（可选 TB 6602）勾稽核对，容差 0.01
 */
export function reconcileWorkHourSalaryVsAnalysis(
  workHourTotalSalary: number,
  analysisLaborCurrent: number,
  tb6602?: number | null,
): I2WorkHourReconcileResult {
  const a = _num(workHourTotalSalary)
  const b = _num(analysisLaborCurrent)
  const diff = a - b
  const ok = Math.abs(diff) <= 0.01
  const diffRate = Math.abs(b) > 1e-9 ? diff / b : null

  let message = ok
    ? `工时表薪酬合计 ${a.toFixed(2)} 与 I2-5 人工费本期数一致`
    : `工时表薪酬合计 ${a.toFixed(2)} 与 I2-5 人工费本期数 ${b.toFixed(2)} 存在差异 ${diff.toFixed(2)}，请核实`

  if (tb6602 != null && Number.isFinite(Number(tb6602))) {
    const c = _num(tb6602)
    const okTb = Math.abs(a - c) <= 0.01
    message += okTb ? `；与 TB 6602 一致` : `；与 TB 6602(${c.toFixed(2)}) 存在差异`
  }

  return { ok, diff, diffRate, message }
}
