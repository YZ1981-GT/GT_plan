/**
 * I2-4 会计政策检查 — 纯模型
 * 对齐致同 Excel：访谈 → 研发流程核验 → CAS6 政策段落 → 同业对比 → 合理性分析 → 结论
 */

export type YnNa = '' | '是' | '否' | '不适用' | '未检查'
export type CasConclusion = '' | '是' | '否' | '不适用'

export interface I2PolicyCasItem {
  key: string
  label: string
  casRef: string
  actualPolicy: string
  evaluation: string
  conclusion: CasConclusion
  explanationIfNo: string
}

export interface I2PolicyProcessItem {
  key: string
  label: string
  /** 检查结果 */
  status: YnNa
  /** 获取/查阅情况说明 */
  evidence: string
  /** 索引号 */
  indexRef: string
}

export interface I2PolicyInterview {
  interviewee: string
  interviewDate: string
  businessTypes: string
  rdProcessSummary: string
  rdModel: string
  consistencyWithPrior: YnNa
  notes: string
}

export interface I2PolicyPeerRow {
  rowId: string
  companyName: string
  source: string
  capitalizationPolicy: string
  costAggregation: string
  staffAllocation: string
  remark: string
}

export interface I2PolicyReasonableness {
  /** 检查的研发项目（可填项目名称/索引） */
  inspectedProjects: string
  /** 政策主题（如资本化时点） */
  policyTopic: string
  /** 是否合理 */
  isReasonable: YnNa
  /** 理由 */
  reasons: string
}

export const I2_POLICY_PROCESS_DEFS: Omit<I2PolicyProcessItem, 'status' | 'evidence' | 'indexRef'>[] = [
  { key: 'initiation', label: '立项报告' },
  { key: 'feasibility', label: '可行性研究' },
  { key: 'tech-roadmap', label: '技术路线图及创新点' },
  { key: 'experiment-log', label: '实验记录' },
  { key: 'completion-report', label: '结题报告' },
  { key: 'site-equipment', label: '研发场地、设备使用情况检查' },
]

export const I2_POLICY_CAS_DEFS: Omit<I2PolicyCasItem, 'actualPolicy' | 'evaluation' | 'conclusion' | 'explanationIfNo'>[] = [
  {
    key: 'research-development-split',
    label: '研究阶段与开发阶段界定',
    casRef: 'CAS6§7-8：研究阶段的支出全部费用化计入当期损益；企业须根据研发立项、可行性研究报告、董事会纪要等文件合理界定研究阶段与开发阶段的时点。',
  },
  {
    key: 'capitalization-policy',
    label: '开发支出资本化会计政策',
    casRef: 'CAS6§9：开发阶段支出同时满足「五个条件」方可资本化确认为无形资产；须检查资本化归集范围、资本化时点及开发完成时点界定是否合理、是否符合研发业务特点与行业惯例。',
  },
  {
    key: 'cost-aggregation-scope',
    label: '研发费用归集范围',
    casRef: '研发支出应单独核算，包括直接研发人员工资、材料费、相关设备折旧费、委外研发费等；同时从事多项研究开发活动的，应按合理标准分摊，无法合理分配的计入当期损益。',
  },
  {
    key: 'part-time-staff-allocation',
    label: '非全时研发人员工时分摊政策',
    casRef: '非全时研发人员应清晰统计从事不同职能的工时情况，按企业会计准则将属于研发活动的薪酬准确合理分摊计入研发支出；工时占比低于50%的原则上不应认定为研发人员。',
  },
  {
    key: 'expense-capitalize-detail',
    label: '费用化/资本化明细核算',
    casRef: '开发支出可按研究开发项目分别「费用化支出」「资本化支出」明细核算；研发费用应从开发支出贷方转出，不能直接列支在损益中。',
  },
  {
    key: 'ht-super-deduction',
    label: '高新认定及加计扣除口径',
    casRef: '关注高新技术企业认定研发费用口径与会计归集差异；委外研发加计扣除通常按实际发生额的80%计入；税会差异应恰当处理并充分披露（财税相关文件 / 财会〔2019〕6号）。',
  },
  {
    key: 'policy-consistency',
    label: '会计政策一贯性及同业比较',
    casRef: '将本期会计政策/估计与前期及同行业公司对比，关注是否利用政策变更操纵利润；与同行业相比是否存在显著差异。',
  },
]

export const I2_POLICY_DEFAULT_CONCLUSION =
  '被审计单位研发费用/开发支出会计政策和会计估计与企业会计准则的规定一致，反映了被审计单位经营业务实际情况，与同行业公司相比不存在显著差异，且得到一贯性执行。'

export function emptyInterview(partial?: Partial<I2PolicyInterview>): I2PolicyInterview {
  return {
    interviewee: '',
    interviewDate: '',
    businessTypes: '',
    rdProcessSummary: '',
    rdModel: '',
    consistencyWithPrior: '',
    notes: '',
    ...partial,
  }
}

export function emptyProcessItems(): I2PolicyProcessItem[] {
  return I2_POLICY_PROCESS_DEFS.map((d) => ({
    ...d,
    status: '',
    evidence: '',
    indexRef: '',
  }))
}

export function emptyCasItems(): I2PolicyCasItem[] {
  return I2_POLICY_CAS_DEFS.map((d) => ({
    ...d,
    actualPolicy: '',
    evaluation: '',
    conclusion: '',
    explanationIfNo: '',
  }))
}

export function emptyPeerRow(partial?: Partial<I2PolicyPeerRow>): I2PolicyPeerRow {
  return {
    rowId: partial?.rowId || `peer-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    companyName: '',
    source: '',
    capitalizationPolicy: '',
    costAggregation: '',
    staffAllocation: '',
    remark: '',
    ...partial,
  }
}

export function emptyReasonableness(partial?: Partial<I2PolicyReasonableness>): I2PolicyReasonableness {
  return {
    inspectedProjects: '',
    policyTopic: '研发费用/开发支出会计政策',
    isReasonable: '',
    reasons: '',
    ...partial,
  }
}

function _str(v: unknown): string {
  return v == null ? '' : String(v)
}

export function normalizeInterview(raw: any): I2PolicyInterview {
  if (!raw || typeof raw !== 'object') return emptyInterview()
  return emptyInterview({
    interviewee: _str(raw.interviewee),
    interviewDate: _str(raw.interviewDate),
    businessTypes: _str(raw.businessTypes),
    rdProcessSummary: _str(raw.rdProcessSummary),
    rdModel: _str(raw.rdModel),
    consistencyWithPrior: (_str(raw.consistencyWithPrior) as YnNa) || '',
    notes: _str(raw.notes),
  })
}

export function normalizeProcessItems(raw: unknown): I2PolicyProcessItem[] {
  const base = emptyProcessItems()
  if (!Array.isArray(raw)) return base
  for (const saved of raw) {
    const target = base.find((i) => i.key === saved?.key)
    if (!target) continue
    target.status = (_str(saved.status) as YnNa) || ''
    target.evidence = _str(saved.evidence)
    target.indexRef = _str(saved.indexRef)
  }
  return base
}

export function normalizeCasItems(raw: unknown): I2PolicyCasItem[] {
  const base = emptyCasItems()
  if (!Array.isArray(raw)) return base
  for (const saved of raw) {
    const target = base.find((i) => i.key === saved?.key)
    if (!target) continue
    target.actualPolicy = _str(saved.actualPolicy)
    target.evaluation = _str(saved.evaluation)
    target.conclusion = (_str(saved.conclusion) as CasConclusion) || ''
    target.explanationIfNo = _str(saved.explanationIfNo)
  }
  return base
}

export function normalizePeerRows(raw: unknown): I2PolicyPeerRow[] {
  if (!Array.isArray(raw) || raw.length === 0) return [emptyPeerRow(), emptyPeerRow()]
  return raw.map((r: any) => emptyPeerRow({
    rowId: _str(r?.rowId) || undefined,
    companyName: _str(r?.companyName),
    source: _str(r?.source),
    capitalizationPolicy: _str(r?.capitalizationPolicy),
    costAggregation: _str(r?.costAggregation),
    staffAllocation: _str(r?.staffAllocation),
    remark: _str(r?.remark),
  }))
}

export function normalizeReasonableness(raw: any): I2PolicyReasonableness {
  if (!raw || typeof raw !== 'object') return emptyReasonableness()
  return emptyReasonableness({
    inspectedProjects: _str(raw.inspectedProjects),
    policyTopic: _str(raw.policyTopic) || '研发费用/开发支出会计政策',
    isReasonable: (_str(raw.isReasonable) as YnNa) || '',
    reasons: _str(raw.reasons),
  })
}

export interface I2PolicyCompletenessItem {
  id: string
  label: string
  ok: boolean
  hint: string
}

export function evaluateI2PolicyCompleteness(input: {
  interview: I2PolicyInterview
  processItems: I2PolicyProcessItem[]
  casItems: I2PolicyCasItem[]
  peerRows: I2PolicyPeerRow[]
  reasonableness: I2PolicyReasonableness
  auditConclusion: string
}): { items: I2PolicyCompletenessItem[]; progress: number; ok: boolean } {
  const processDone = input.processItems.filter((i) => !!i.status && i.status !== '未检查').length
  const casDone = input.casItems.filter((i) => !!i.conclusion).length
  const casNoMissingExplain = input.casItems.every((i) => i.conclusion !== '否' || !!i.explanationIfNo.trim())
  const peerFilled = input.peerRows.some((r) => r.companyName.trim() && (r.capitalizationPolicy.trim() || r.costAggregation.trim()))

  const items: I2PolicyCompletenessItem[] = [
    {
      id: 'interview',
      label: '管理层访谈',
      ok: !!(input.interview.interviewee.trim() && input.interview.rdProcessSummary.trim()),
      hint: '填写访谈对象及研发流程/模式摘要',
    },
    {
      id: 'process',
      label: '研发流程资料核验',
      ok: processDone >= Math.min(4, input.processItems.length),
      hint: `已核验 ${processDone}/${input.processItems.length} 项（建议至少 4 项）`,
    },
    {
      id: 'cas',
      label: 'CAS6 政策段落评价',
      ok: casDone === input.casItems.length && casNoMissingExplain,
      hint: casNoMissingExplain
        ? `已结论 ${casDone}/${input.casItems.length}`
        : '「不符合」项须填写原因说明',
    },
    {
      id: 'peer',
      label: '同行业政策对比',
      ok: peerFilled,
      hint: '至少填写 1 家同业公司的关键政策要点',
    },
    {
      id: 'reason',
      label: '合理性分析',
      ok: !!(input.reasonableness.isReasonable && input.reasonableness.reasons.trim()),
      hint: '填写是否合理及理由',
    },
    {
      id: 'conclusion',
      label: '审计结论',
      ok: !!input.auditConclusion.trim(),
      hint: '填写或采用模板结论',
    },
  ]

  const okCount = items.filter((i) => i.ok).length
  const progress = Math.round((okCount / items.length) * 100)
  return { items, progress, ok: okCount === items.length }
}

/** 生成合理性分析叙述稿 */
export function buildReasonablenessNarrative(r: I2PolicyReasonableness): string {
  const projects = r.inspectedProjects.trim() || '________'
  const topic = r.policyTopic.trim() || '研发费用/开发支出会计政策'
  const verdict = r.isReasonable === '是'
    ? '是合理的'
    : r.isReasonable === '否'
      ? '存在不合理之处'
      : r.isReasonable === '不适用'
        ? '不适用（请说明）'
        : '________'
  const reasons = r.reasons.trim() || '①……；②……'
  return `通过研发项目检查（${projects}），被审计单位「${topic}」${verdict}，理由如下：${reasons}`
}
