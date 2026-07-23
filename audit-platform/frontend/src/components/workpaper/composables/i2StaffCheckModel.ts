/**
 * I2-9 研发人员认定检查表 — 纯模型
 * 对齐致同源表：审计目标 → 人员明细核查 → 编制说明（认定规则）→ 说明/结论
 *
 * 持久化字段位于 I2TabStaffCheck.vue（未抽取独立 composable，逻辑量较小）：
 * load/save/normalize 直接内联；此处集中导出 STORAGE_KEY 供该 Vue 及跨sheet引用（如 I2-10 取数）共用，避免字符串硬编码分裂。
 */

/** checklist_responses item_id：行数据 / 审计说明 / 审计结论（供 I2TabStaffCheck.vue 及跨sheet引用共用） */
export const I2_STAFF_STORAGE_KEY = 'I2-9-rows'
export const I2_STAFF_AUDIT_NOTE_KEY = 'I2-9-audit-note'
export const I2_STAFF_AUDIT_CONCLUSION_KEY = 'I2-9-audit-conclusion'

/** 编制说明（源表底部规则） */
export const I2_STAFF_PREP_NOTES = [
  '研发人员包括直接从事研发活动的人员及与研发活动相关的管理人员和直接服务人员；后勤、接待、餐饮、安保等辅助人员原则上不得认定为研发人员。',
  '兼职从事研发活动且研发工时占比低于 50% 的人员，原则上不应认定为研发人员，除非有充分、适当的证据支持。',
  '从事定制化产品开发或对外提供研发服务的人员，一般不认定为研发人员；除非被审计单位能够控制研发成果并取得未来经济利益。',
  '研发人员原则上应与被审计单位签订劳动合同；劳务派遣人员一般不得认定为研发人员。上市企业披露口径应与招股说明书信息披露规则第 57 条等保持一致。',
] as const

export const I2_STAFF_OBJECTIVES = [
  '确认利润表中记录的研发费用已发生，与被审计单位有关，且已记录于恰当的账户（发生、权利和义务、分类）。',
  '确认与研发费用有关的金额及其他数据已恰当记录，相关披露已得到恰当计量和描述（准确性、计价和分摊、列报）。',
] as const

export const I2_STAFF_GENDER_OPTIONS = ['男', '女', ''] as const
export const I2_STAFF_EDU_OPTIONS = ['博士', '硕士', '本科', '大专', '中专及以下', '其他'] as const
export const I2_STAFF_EMPLOY_OPTIONS = ['劳动合同', '劳务派遣', '兼职/顾问', '实习', '其他'] as const
export const I2_STAFF_CATEGORY_OPTIONS = [
  '直接研发人员',
  '研发管理人员',
  '直接服务人员',
  '后勤辅助',
  '其他',
] as const
export const I2_STAFF_FULLTIME_OPTIONS = ['是', '否', '部分'] as const
export const I2_STAFF_CONCLUSION_OPTIONS = [
  '认定为研发人员',
  '不予认定',
  '待核实',
] as const

/** 明显非研发岗位/部门关键词（用于风险提示） */
export const I2_STAFF_NON_RD_KEYWORDS = [
  '后勤', '接待', '餐饮', '保安', '安保', '门卫', '保洁', '司机',
  '销售', '市场', '行政', '人事', '财务', '出纳', '仓管', '仓储',
] as const

export type I2StaffConclusion = (typeof I2_STAFF_CONCLUSION_OPTIONS)[number] | string

export interface I2StaffCheckRow {
  rowId: string
  /** 姓名 */
  staffName: string
  /** 性别 */
  gender: string
  /** 年龄 */
  age: number | null
  /** 学历 */
  education: string
  /** 毕业院校 */
  graduateSchool: string
  /** 所学专业 */
  major: string
  /** 职称 */
  title: string
  /** 职务 */
  position: string
  /** 部门 */
  department: string
  /** 人员类别 */
  personnelCategory: string
  /** 入职日期 YYYY-MM-DD */
  hireDate: string
  /** 聘用形式 */
  employmentForm: string
  /** 是否全时参与该研发项目 */
  fullTimeRd: string
  /** 研发工时占比 %（0-100） */
  rdHourRatio: number | null
  /** 参与研发项目 */
  projects: string
  /** 附件索引号 */
  attachmentIndex: string
  /** 系统建议结论（公式列，可被人工覆盖） */
  suggestedConclusion: I2StaffConclusion
  /** 认定结论（人工） */
  conclusion: I2StaffConclusion
  /** 备注 */
  remark: string
  /** 兼容旧字段：资质合并展示 */
  qualification?: string
}

export interface I2StaffCheckSummary {
  totalCount: number
  acceptedCount: number
  rejectedCount: number
  pendingCount: number
  /** 建议不予认定但人工仍认定为研发人员 */
  overrideRiskCount: number
  /** 劳务派遣人数 */
  dispatchCount: number
  /** 工时占比&lt;50% 人数 */
  lowRatioCount: number
  /** 非研发关键词命中 */
  nonRdKeywordCount: number
}

export function emptyI2StaffRow(partial?: Partial<I2StaffCheckRow>): I2StaffCheckRow {
  const row: I2StaffCheckRow = {
    rowId: partial?.rowId || `i29-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    staffName: '',
    gender: '',
    age: null,
    education: '',
    graduateSchool: '',
    major: '',
    title: '',
    position: '',
    department: '',
    personnelCategory: '',
    hireDate: '',
    employmentForm: '',
    fullTimeRd: '',
    rdHourRatio: null,
    projects: '',
    attachmentIndex: '',
    suggestedConclusion: '待核实',
    conclusion: '',
    remark: '',
  }
  Object.assign(row, partial)
  row.suggestedConclusion = suggestStaffConclusion(row)
  if (!row.conclusion) row.conclusion = row.suggestedConclusion
  return row
}

/** 文本是否命中非研发关键词 */
export function hitNonRdKeyword(...texts: Array<string | null | undefined>): boolean {
  const blob = texts.filter(Boolean).join(' ')
  if (!blob) return false
  return I2_STAFF_NON_RD_KEYWORDS.some((kw) => blob.includes(kw))
}

/**
 * 按编制说明规则给出建议认定结论（可被人工覆盖）
 * 优先级：劳务派遣 / 后勤类别 / 非研发岗位关键词 / 工时&lt;50% 且非全时 → 不予认定；信息不足 → 待核实；否则建议认定
 */
export function suggestStaffConclusion(row: Pick<
  I2StaffCheckRow,
  | 'employmentForm'
  | 'personnelCategory'
  | 'department'
  | 'position'
  | 'fullTimeRd'
  | 'rdHourRatio'
  | 'staffName'
>): I2StaffConclusion {
  if (!row.staffName?.trim()) return '待核实'

  if (row.employmentForm === '劳务派遣') return '不予认定'
  if (row.personnelCategory === '后勤辅助') return '不予认定'
  if (hitNonRdKeyword(row.department, row.position, row.personnelCategory)) return '不予认定'

  const ratio = row.rdHourRatio
  const isPartTime = row.fullTimeRd === '否' || row.fullTimeRd === '部分'
  if (ratio != null && ratio < 50 && (isPartTime || row.fullTimeRd === '')) {
    return '不予认定'
  }
  if (ratio != null && ratio < 50 && row.fullTimeRd === '是') {
    // 声称全时但占比不足 — 待核实
    return '待核实'
  }

  // 关键身份字段齐全才建议认定
  const hasCore =
    !!(row.position || row.personnelCategory) &&
    !!(row.employmentForm) &&
    (row.fullTimeRd === '是' || (ratio != null && ratio >= 50))

  if (hasCore) return '认定为研发人员'
  return '待核实'
}

export function normalizeI2StaffRow(raw: any): I2StaffCheckRow {
  // 兼容旧版 5 字段结构
  const qualification = String(raw.qualification ?? '')
  let education = String(raw.education ?? '')
  let title = String(raw.title ?? '')
  if (!education && !title && qualification) {
    // 旧「资质」字段拆分尝试：学历/职称
    const parts = qualification.split(/[/／、,，]/).map((s: string) => s.trim()).filter(Boolean)
    education = parts[0] || ''
    title = parts.slice(1).join('/') || ''
  }

  const row = emptyI2StaffRow({
    rowId: String(raw.rowId || ''),
    staffName: String(raw.staffName ?? ''),
    gender: String(raw.gender ?? ''),
    age: raw.age == null || raw.age === '' ? null : Number(raw.age),
    education,
    graduateSchool: String(raw.graduateSchool ?? ''),
    major: String(raw.major ?? ''),
    title,
    position: String(raw.position ?? ''),
    department: String(raw.department ?? ''),
    personnelCategory: String(raw.personnelCategory ?? ''),
    hireDate: String(raw.hireDate ?? ''),
    employmentForm: String(raw.employmentForm ?? ''),
    fullTimeRd: String(raw.fullTimeRd ?? ''),
    rdHourRatio: raw.rdHourRatio == null || raw.rdHourRatio === '' ? null : Number(raw.rdHourRatio),
    projects: String(raw.projects ?? ''),
    attachmentIndex: String(raw.attachmentIndex ?? raw.indexRef ?? ''),
    conclusion: String(raw.conclusion ?? ''),
    remark: String(raw.remark ?? ''),
    qualification,
  })
  // emptyI2StaffRow 会写 suggested；若旧数据已有人工结论则保留
  if (raw.conclusion) row.conclusion = String(raw.conclusion)
  row.suggestedConclusion = suggestStaffConclusion(row)
  return row
}

export function persistI2StaffRow(row: I2StaffCheckRow): Record<string, unknown> {
  return {
    rowId: row.rowId,
    staffName: row.staffName,
    gender: row.gender,
    age: row.age,
    education: row.education,
    graduateSchool: row.graduateSchool,
    major: row.major,
    title: row.title,
    position: row.position,
    department: row.department,
    personnelCategory: row.personnelCategory,
    hireDate: row.hireDate,
    employmentForm: row.employmentForm,
    fullTimeRd: row.fullTimeRd,
    rdHourRatio: row.rdHourRatio,
    projects: row.projects,
    attachmentIndex: row.attachmentIndex,
    conclusion: row.conclusion,
    remark: row.remark,
  }
}

export function summarizeI2StaffRows(rows: I2StaffCheckRow[]): I2StaffCheckSummary {
  let acceptedCount = 0
  let rejectedCount = 0
  let pendingCount = 0
  let overrideRiskCount = 0
  let dispatchCount = 0
  let lowRatioCount = 0
  let nonRdKeywordCount = 0

  for (const r of rows) {
    if (r.conclusion === '认定为研发人员') acceptedCount++
    else if (r.conclusion === '不予认定') rejectedCount++
    else pendingCount++

    if (r.suggestedConclusion === '不予认定' && r.conclusion === '认定为研发人员') {
      overrideRiskCount++
    }
    if (r.employmentForm === '劳务派遣') dispatchCount++
    if (r.rdHourRatio != null && r.rdHourRatio < 50) lowRatioCount++
    if (hitNonRdKeyword(r.department, r.position, r.personnelCategory)) nonRdKeywordCount++
  }

  return {
    totalCount: rows.length,
    acceptedCount,
    rejectedCount,
    pendingCount,
    overrideRiskCount,
    dispatchCount,
    lowRatioCount,
    nonRdKeywordCount,
  }
}

/** 行级风险样式标记 */
export function staffRowRiskClass(row: I2StaffCheckRow): string {
  if (row.conclusion === '不予认定' || row.suggestedConclusion === '不予认定') return 'risk-reject-row'
  if (row.suggestedConclusion === '不予认定' && row.conclusion === '认定为研发人员') return 'risk-override-row'
  if (row.conclusion === '待核实' || !row.conclusion) return 'risk-pending-row'
  return ''
}
