/**
 * H2-14 监盘小结 — 数据结构与默认值
 * 对齐致同模板「在建工程监盘小结」：了解→盘前→人员/时间→逐项踏勘→总体核对→异常→收尾→结论
 * 参照 H1-11（固定资产监盘小结）处理范式，保留 CIP 专用字段（形象进度/停工/转固时点）
 */

export interface H2SummaryPersonnelRow {
  rowId: string
  seq: number
  department: string
  headcount: number
  names: string
  responsibleArea: string
}

export interface H2SummaryAuditorRow {
  rowId: string
  seq: number
  names: string
  responsibleArea: string
}

/** 逐个工程项目形象进度等情况描述 */
export interface H2ProjectObservationRow {
  rowId: string
  seq: number
  projectName: string
  diagramIndex: string
  location: string
  progressDescription: string
  photoIndex: string
  /** 来自 H2-13 的施工状态（展示用，可手改） */
  constructionStatus: string
  visibleProgress: number | null
}

export interface H2ObservationCheckItem {
  id: string
  label: string
  answer: string
  indexRef: string
}

export interface H2AbnormalItem {
  rowId: string
  name: string
  abnormalType: string
  description: string
  suggestion: string
}

export interface H2StocktakeSummaryForm {
  /** 一、资产负债表日说明 */
  bsDateNote: string
  /** 二、盘前：工程管理部门 */
  engDept: string
  /** 二、盘前：管理人员 */
  engStaff: string
  /** 管理制度设计是否合理 */
  policyDesignOk: string
  /** 是否有效执行 */
  policyExecutedOk: string
  /** 管理制度索引 */
  policyIndex: string
  /** 三、参与人员 */
  clientPersonnel: H2SummaryPersonnelRow[]
  auditorPersonnel: H2SummaryAuditorRow[]
  /** 实际现场察看日/时段 */
  actualDate: string
  startTime: string
  endTime: string
  /** 四(一)、逐项工程观察 */
  projectObservations: H2ProjectObservationRow[]
  /** 四(二)、察看总体情况描述（6 项核对） */
  observationChecks: H2ObservationCheckItem[]
  /** 总体情况补充叙述（兼容旧版 overallSituation） */
  overallSituation: string
  /** 五、异常 */
  abnormalProjects: H2AbnormalItem[]
  abnormalNote: string
  /** 六、结束工作 */
  postWorkNote: string
  evalFamiliarity: string
  evalAttitude: string
  evalCooperation: string
  diffExplanationObtained: '' | 'Y' | 'N'
  diffExplanationIndex: string
  clientSigned: '' | 'Y' | 'N'
  clientSignIndex: string
  /** 结论与签署 */
  conclusion: string
  preparedBy: string
  preparedDate: string
  reviewedBy: string
  reviewedDate: string
  /** 人工覆盖过的自动字段（不再被 H2-13 实时回填） */
  manualOverrides: string[]
  lastAutoSyncAt: string
}

/** 四(二) 总体核对项 — 对齐致同模板 */
export const OBSERVATION_CHECK_DEFS: { id: string; label: string }[] = [
  {
    id: 'qtyMatch',
    label: '实际观察到的在建工程是否与会计账簿记载数量一致',
  },
  {
    id: 'offBook',
    label: '是否存在会计账簿未记载的工程',
  },
  {
    id: 'diagramMatch',
    label: '获取的工程简图与现场是否一致',
  },
  {
    id: 'progressMatch',
    label: '现场察看的工程完工进度是否与账面记载一致，并与监理报告核对一致',
  },
  {
    id: 'readyNotTransferred',
    label: '有无已达到预计可使用状态但尚未办理竣工决算手续仍列于在建工程的情况',
  },
  {
    id: 'longStoppage',
    label: '有无长期停工的工程',
  },
]

function _id(): string {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

export function createEmptyH2SummaryForm(): H2StocktakeSummaryForm {
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
    observationChecks: OBSERVATION_CHECK_DEFS.map((d) => ({
      ...d,
      answer: '',
      indexRef: '',
    })),
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
    manualOverrides: [],
    lastAutoSyncAt: '',
  }
}

/** 合并已存 JSON，兼容旧版仅 overallSituation/abnormalProjects/conclusion */
export function normalizeH2SummaryForm(raw: any): H2StocktakeSummaryForm {
  const base = createEmptyH2SummaryForm()
  if (!raw || typeof raw !== 'object') return base

  const out: H2StocktakeSummaryForm = { ...base, ...raw }

  out.observationChecks = OBSERVATION_CHECK_DEFS.map((d) => {
    const found = (Array.isArray(raw.observationChecks) ? raw.observationChecks : []).find(
      (x: any) => x?.id === d.id,
    )
    return {
      ...d,
      answer: found?.answer ?? '',
      indexRef: found?.indexRef ?? '',
    }
  })

  out.clientPersonnel = Array.isArray(raw.clientPersonnel)
    ? raw.clientPersonnel.map((r: any, i: number) => ({
        rowId: r.rowId ?? `cp-${_id()}`,
        seq: r.seq ?? i + 1,
        department: r.department ?? '',
        headcount: Number(r.headcount) || 0,
        names: r.names ?? '',
        responsibleArea: r.responsibleArea ?? '',
      }))
    : []

  out.auditorPersonnel = Array.isArray(raw.auditorPersonnel)
    ? raw.auditorPersonnel.map((r: any, i: number) => ({
        rowId: r.rowId ?? `ap-${_id()}`,
        seq: r.seq ?? i + 1,
        names: r.names ?? '',
        responsibleArea: r.responsibleArea ?? '',
      }))
    : []

  out.projectObservations = Array.isArray(raw.projectObservations)
    ? raw.projectObservations.map((r: any, i: number) => ({
        rowId: r.rowId ?? `po-${_id()}`,
        seq: r.seq ?? i + 1,
        projectName: r.projectName ?? '',
        diagramIndex: r.diagramIndex ?? '',
        location: r.location ?? '',
        progressDescription: r.progressDescription ?? '',
        photoIndex: r.photoIndex ?? '',
        constructionStatus: r.constructionStatus ?? '',
        visibleProgress: r.visibleProgress != null ? Number(r.visibleProgress) : null,
      }))
    : []

  out.abnormalProjects = Array.isArray(raw.abnormalProjects)
    ? raw.abnormalProjects.map((a: any) => ({
        rowId: a.rowId ?? `ab-${_id()}`,
        name: a.name ?? '',
        abnormalType: a.abnormalType ?? '',
        description: a.description ?? '',
        suggestion: a.suggestion ?? '',
      }))
    : []

  if (!Array.isArray(out.manualOverrides)) out.manualOverrides = []
  if (!out.lastAutoSyncAt) out.lastAutoSyncAt = ''

  // 旧版字段兜底
  if (!out.overallSituation && typeof raw.overallSituation === 'string') {
    out.overallSituation = raw.overallSituation
  }
  if (!out.conclusion && typeof raw.conclusion === 'string') {
    out.conclusion = raw.conclusion
  }

  return out
}

export function newClientPersonnelRow(
  partial?: Partial<H2SummaryPersonnelRow>,
): H2SummaryPersonnelRow {
  return {
    rowId: `cp-${_id()}`,
    seq: 1,
    department: '',
    headcount: 1,
    names: '',
    responsibleArea: '',
    ...partial,
  }
}

export function newAuditorRow(partial?: Partial<H2SummaryAuditorRow>): H2SummaryAuditorRow {
  return {
    rowId: `ap-${_id()}`,
    seq: 1,
    names: '',
    responsibleArea: '',
    ...partial,
  }
}

export function newProjectObservationRow(
  partial?: Partial<H2ProjectObservationRow>,
): H2ProjectObservationRow {
  return {
    rowId: `po-${_id()}`,
    seq: 1,
    projectName: '',
    diagramIndex: '',
    location: '',
    progressDescription: '',
    photoIndex: '',
    constructionStatus: '',
    visibleProgress: null,
    ...partial,
  }
}

export function newAbnormalItem(partial?: Partial<H2AbnormalItem>): H2AbnormalItem {
  return {
    rowId: `ab-${_id()}`,
    name: '',
    abnormalType: '',
    description: '',
    suggestion: '',
    ...partial,
  }
}

/** 结束时间须晚于开始时间（HH:mm） */
export function isTimeRangeValid(start: string, end: string): boolean {
  if (!start || !end) return true
  const toMin = (t: string) => {
    const m = t.match(/^(\d{1,2}):(\d{2})$/)
    if (!m) return null
    return Number(m[1]) * 60 + Number(m[2])
  }
  const a = toMin(start)
  const b = toMin(end)
  if (a == null || b == null) return true
  return b > a
}

/** 从 H2-13 检查行草稿逐项观察表（按工程名去重合并；兼容旧/新字段） */
export function draftObservationsFromCheckRows(
  rows: {
    name: string
    siteLocation?: string
    location?: string
    visibleProgress?: number | null
    constructionStatus?: string
    progressDifference?: string
    progressDesc?: string
    stopDuration?: string
    stopReason?: string
    readyForUse?: string
    result?: string
    photos?: string
    photoUrl?: string
    auditConclusion?: string
    remark?: string
  }[],
): H2ProjectObservationRow[] {
  return rows.map((r, i) => {
    const progressDiff = r.progressDesc || r.progressDifference || ''
    const parts = [
      r.constructionStatus ? `施工状态：${r.constructionStatus}` : '',
      r.visibleProgress != null ? `形象进度约 ${r.visibleProgress}%` : '',
      progressDiff ? `进度状况：${progressDiff}` : '',
      r.readyForUse ? `达可使用状态：${r.readyForUse}` : '',
      r.stopDuration ? `已停工：${r.stopDuration}` : '',
      r.stopReason ? `停工原因：${r.stopReason}` : '',
      (r.result || r.auditConclusion) ? `检查结论：${r.result || r.auditConclusion}` : '',
      r.remark || '',
    ].filter(Boolean)
    return newProjectObservationRow({
      seq: i + 1,
      projectName: r.name || '',
      location: r.location || r.siteLocation || '',
      progressDescription: parts.join('；'),
      photoIndex: r.photoUrl || r.photos || '',
      constructionStatus: r.constructionStatus || '',
      visibleProgress: r.visibleProgress ?? null,
    })
  })
}

/** 从 H2-13 停工/进度异常/不存在等自动生成异常草稿（兼容旧/新字段） */
export function draftAbnormalsFromCheckRows(
  rows: {
    name: string
    constructionStatus?: string
    progressDifference?: string
    progressDesc?: string
    stopDuration?: string
    stopReason?: string
    readyForUse?: string
    result?: string
    auditConclusion?: string
    remark?: string
  }[],
): H2AbnormalItem[] {
  const out: H2AbnormalItem[] = []
  for (const r of rows) {
    const stopped =
      r.constructionStatus === '停工'
      || !!String(r.stopDuration ?? '').trim()
      || !!String(r.stopReason ?? '').trim()
    if (stopped) {
      out.push(
        newAbnormalItem({
          name: r.name,
          abnormalType: '停工',
          description: [
            r.stopDuration,
            r.stopReason,
            r.progressDesc || r.progressDifference,
            r.remark,
            r.result || r.auditConclusion,
          ].filter(Boolean).join('；'),
          suggestion: '关注减值（→H2-15）',
        }),
      )
      continue
    }
    if (r.readyForUse === '是') {
      out.push(
        newAbnormalItem({
          name: r.name,
          abnormalType: '达可使用未转固',
          description: '现场判断已达预定可使用状态',
          suggestion: '核对转固时点（→H2-5）',
        }),
      )
    }
    const diff = (r.progressDesc || r.progressDifference || '').trim()
    if (diff && !/一致|无差异|相符/.test(diff)) {
      out.push(
        newAbnormalItem({
          name: r.name,
          abnormalType: '进度异常',
          description: diff,
          suggestion: '追加说明',
        }),
      )
    }
    const conclusion = r.result || r.auditConclusion || ''
    if (/不存在|未见|无法核实|盘亏/.test(conclusion)) {
      out.push(
        newAbnormalItem({
          name: r.name,
          abnormalType: /盘亏/.test(conclusion) ? '盘亏' : '不存在',
          description: conclusion,
          suggestion: '建议调整',
        }),
      )
    }
  }
  return out
}

/** 完工程度闸门 */
export function calcH2SummaryCompleteness(form: H2StocktakeSummaryForm): {
  id: string
  label: string
  ok: boolean
  hint: string
}[] {
  return [
    {
      id: 'bs',
      label: '资产负债表日说明',
      ok: !!form.bsDateNote.trim(),
      hint: '说明监盘日与资产负债表日关系',
    },
    {
      id: 'pre',
      label: '盘前了解（部门/制度）',
      ok: !!(form.engDept.trim() || form.engStaff.trim() || form.policyDesignOk.trim()),
      hint: '填写工程管理部门或管理制度评价',
    },
    {
      id: 'people',
      label: '参与察看人员',
      ok: form.clientPersonnel.length > 0 || form.auditorPersonnel.length > 0,
      hint: '至少登记一方参与人员',
    },
    {
      id: 'time',
      label: '实际察看时间',
      ok: !!form.actualDate,
      hint: '填写实际现场察看日',
    },
    {
      id: 'obs',
      label: '逐项工程观察',
      ok: form.projectObservations.length > 0,
      hint: '可从 H2-13 回填',
    },
    {
      id: 'checks',
      label: '总体核对（至少填 1 项）',
      ok: form.observationChecks.some((c) => !!c.answer.trim()),
      hint: '完成四(二)存在性/进度/停工等核对',
    },
    {
      id: 'conclusion',
      label: '监盘结论',
      ok: !!form.conclusion.trim(),
      hint: '明确是否达到审计目标',
    },
  ]
}

/** 规则起草结论草稿 */
export function draftH2Conclusion(form: H2StocktakeSummaryForm, stats: {
  total: number
  inProgress: number
  stopped: number
  completed: number
}): string {
  const n = form.projectObservations.length || stats.total
  const abn = form.abnormalProjects.length
  const stop = form.abnormalProjects.filter((a) => a.abnormalType === '停工').length || stats.stopped
  const ready = form.observationChecks.find((c) => c.id === 'readyNotTransferred')?.answer || ''
  const lines = [
    `本次现场察看覆盖在建工程项目 ${n} 个（施工中 ${stats.inProgress}、停工 ${stats.stopped}、完工 ${stats.completed}）。`,
    abn > 0
      ? `发现异常事项 ${abn} 项${stop > 0 ? `（其中停工 ${stop} 项，建议联动 H2-15 关注减值）` : ''}，详见异常清单。`
      : '现场察看未发现重大异常。',
    ready.trim()
      ? `关于已达预计可使用状态仍挂在建：${ready.trim()}。`
      : '',
    '经实施上述程序，我们认为在建工程监盘程序已按计划执行，相关存在性、形象进度及停工/转固风险已得到适当关注（具体结论请结合抽样覆盖与证据充分性进一步判断）。',
  ]
  return lines.filter(Boolean).join('\n')
}
