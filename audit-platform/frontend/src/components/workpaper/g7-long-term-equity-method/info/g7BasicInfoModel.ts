export const G7_BASIC_INFO_GROUPS = [
  { value: 'subsidiary', label: '（一）子公司', accountingMethod: '成本法' },
  { value: 'joint_venture', label: '（二）合营企业（共同控制）', accountingMethod: '权益法' },
  { value: 'associate', label: '（三）联营企业（重大影响）', accountingMethod: '权益法' },
  { value: 'joint_operation', label: '（四）共同经营（共同控制）', accountingMethod: '各项单独确认' },
] as const

export type G7BasicInfoGroup = typeof G7_BASIC_INFO_GROUPS[number]['value']

export const G7_ENTERPRISE_TYPE_OPTIONS = [
  { value: '1', label: '1－境内非金融子企业' },
  { value: '2', label: '2－境内金融子企业' },
  { value: '3', label: '3－境外子企业' },
  { value: '4', label: '4－事业单位' },
  { value: '5', label: '5－基建单位' },
] as const

export const G7_YES_NO_OPTIONS = ['是', '否'] as const

export interface G7BasicInfoRow {
  id: string
  seq: number
  groupType: G7BasicInfoGroup
  investeeName: string
  level: string
  enterpriseType: string
  newlyConsolidated: '' | '是' | '否'
  principalPlace: string
  registeredPlace: string
  businessNature: string
  registeredCapital: number | null
  investmentAmount: number | null
  endingNetAssets: number | null
  currentNetProfit: number | null
  directHoldingRatio: number | null
  indirectHoldingRatio: number | null
  votingRatio: number | null
  holdingVotingDifferenceReason: string
  lessThanHalfControlReason: string
  majorityNoControlReason: string
  acquisitionMethod: string
  accountingMethod: string
}

const GROUP_ALIASES: Record<string, G7BasicInfoGroup> = {
  子公司: 'subsidiary',
  合营: 'joint_venture',
  合营企业: 'joint_venture',
  联营: 'associate',
  联营企业: 'associate',
  共同经营: 'joint_operation',
}

function numberOrNull(value: unknown): number | null {
  if (value === '' || value == null) return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

function stringValue(value: unknown): string {
  return value == null ? '' : String(value).trim()
}

/** 旧版 G7-4 / G7-2 使用 0～1 小数；现行 G7-4 统一为百分数 0～100。 */
export function looksLikeFractionRatio(value: number | null | undefined): boolean {
  return value != null && value > 0 && value <= 1
}

/** 仅在 force=true（确认来源为小数比例）时换算为百分数。 */
export function toPercentRatio(
  value: number | null,
  options: { force?: boolean } = {},
): number | null {
  if (value == null) return null
  if (options.force) {
    return Math.round(value * 10000) / 100
  }
  return value
}

function isLegacyBasicInfoPayload(raw: Record<string, unknown>): boolean {
  if (raw.ratioScale === 'fraction') return true
  if (raw.ratioScale === 'percent') return false
  if (raw.groupType) return false
  return raw.controlType != null || raw.investmentRatio != null
}

export function accountingMethodFor(groupType: G7BasicInfoGroup): string {
  return G7_BASIC_INFO_GROUPS.find(group => group.value === groupType)?.accountingMethod ?? ''
}

export function createG7BasicInfoRow(
  groupType: G7BasicInfoGroup,
  seq: number,
  investeeName = '',
): G7BasicInfoRow {
  return {
    id: crypto.randomUUID(),
    seq,
    groupType,
    investeeName,
    level: '',
    enterpriseType: '',
    newlyConsolidated: '',
    principalPlace: '',
    registeredPlace: '',
    businessNature: '',
    registeredCapital: null,
    investmentAmount: null,
    endingNetAssets: null,
    currentNetProfit: null,
    directHoldingRatio: null,
    indirectHoldingRatio: null,
    votingRatio: null,
    holdingVotingDifferenceReason: '',
    lessThanHalfControlReason: '',
    majorityNoControlReason: '',
    acquisitionMethod: '',
    accountingMethod: accountingMethodFor(groupType),
  }
}

export function normalizeG7BasicInfoRow(
  raw: Record<string, unknown>,
  index: number,
): G7BasicInfoRow {
  const groupType =
    (G7_BASIC_INFO_GROUPS.some(group => group.value === raw.groupType)
      ? raw.groupType
      : GROUP_ALIASES[stringValue(raw.groupType ?? raw.controlType)]) as G7BasicInfoGroup
    || 'associate'
  const row = createG7BasicInfoRow(
    groupType,
    index + 1,
    stringValue(raw.investeeName ?? raw.investee_name ?? raw.companyName),
  )
  const legacy = isLegacyBasicInfoPayload(raw)
  const directRaw = numberOrNull(raw.directHoldingRatio ?? raw.investmentRatio)
  const indirectRaw = numberOrNull(raw.indirectHoldingRatio)
  const votingRaw = numberOrNull(raw.votingRatio)

  return {
    ...row,
    id: stringValue(raw.id) || row.id,
    level: stringValue(raw.level),
    enterpriseType: stringValue(raw.enterpriseType),
    newlyConsolidated: G7_YES_NO_OPTIONS.includes(raw.newlyConsolidated as '是' | '否')
      ? raw.newlyConsolidated as '是' | '否'
      : '',
    principalPlace: stringValue(raw.principalPlace),
    registeredPlace: stringValue(raw.registeredPlace ?? raw.registeredAddress),
    businessNature: stringValue(raw.businessNature ?? raw.mainBusiness ?? raw.industry),
    registeredCapital: numberOrNull(raw.registeredCapital),
    investmentAmount: numberOrNull(raw.investmentAmount),
    endingNetAssets: numberOrNull(raw.endingNetAssets),
    currentNetProfit: numberOrNull(raw.currentNetProfit),
    directHoldingRatio: toPercentRatio(directRaw, { force: legacy && looksLikeFractionRatio(directRaw) }),
    indirectHoldingRatio: toPercentRatio(indirectRaw, { force: legacy && looksLikeFractionRatio(indirectRaw) }),
    votingRatio: toPercentRatio(votingRaw, { force: legacy && looksLikeFractionRatio(votingRaw) }),
    holdingVotingDifferenceReason: stringValue(raw.holdingVotingDifferenceReason),
    lessThanHalfControlReason: stringValue(raw.lessThanHalfControlReason),
    majorityNoControlReason: stringValue(raw.majorityNoControlReason),
    acquisitionMethod: stringValue(raw.acquisitionMethod),
    accountingMethod: accountingMethodFor(groupType),
  }
}

export function resequenceG7BasicInfoRows(rows: G7BasicInfoRow[]): void {
  for (const group of G7_BASIC_INFO_GROUPS) {
    rows
      .filter(row => row.groupType === group.value)
      .forEach((row, index) => { row.seq = index + 1 })
  }
}

export function holdingRatioTotal(row: G7BasicInfoRow): number | null {
  if (row.directHoldingRatio == null && row.indirectHoldingRatio == null) return null
  return (row.directHoldingRatio ?? 0) + (row.indirectHoldingRatio ?? 0)
}

export function needsHoldingVotingReason(row: G7BasicInfoRow): boolean {
  if (row.groupType === 'joint_operation' || row.votingRatio == null) return false
  const holding = holdingRatioTotal(row)
  return holding != null && Math.abs(holding - row.votingRatio) > 0.0001
}

export function needsLessThanHalfControlReason(row: G7BasicInfoRow): boolean {
  return row.groupType === 'subsidiary' && row.votingRatio != null && row.votingRatio < 50
}

export function needsMajorityNoControlReason(row: G7BasicInfoRow): boolean {
  return row.groupType !== 'subsidiary'
    && row.groupType !== 'joint_operation'
    && row.votingRatio != null
    && row.votingRatio >= 50
}

export interface G7BasicInfoIssue {
  severity: 'error' | 'warning'
  rowId?: string
  investeeName?: string
  message: string
}

export function validateG7BasicInfoRows(rows: G7BasicInfoRow[]): G7BasicInfoIssue[] {
  const issues: G7BasicInfoIssue[] = []
  const names = new Map<string, string>()

  for (const row of rows) {
    const name = row.investeeName.trim()
    if (!name) {
      issues.push({
        severity: 'error',
        rowId: row.id,
        message: `${labelOf(row.groupType)}第${row.seq}行公司名称不能为空`,
      })
      continue
    }
    const prior = names.get(name)
    if (prior) {
      issues.push({
        severity: 'error',
        rowId: row.id,
        investeeName: name,
        message: `公司名称「${name}」重复`,
      })
    } else {
      names.set(name, row.id)
    }

    const holding = holdingRatioTotal(row)
    if (holding != null && (holding < 0 || holding > 100)) {
      issues.push({
        severity: 'error',
        rowId: row.id,
        investeeName: name,
        message: `「${name}」持股合计应为 0%～100%，当前为 ${holding}%`,
      })
    }
    if (row.votingRatio != null && (row.votingRatio < 0 || row.votingRatio > 100)) {
      issues.push({
        severity: 'error',
        rowId: row.id,
        investeeName: name,
        message: `「${name}」表决权比例应为 0%～100%`,
      })
    }
    if (row.groupType === 'subsidiary' && row.enterpriseType && !['1', '2', '3', '4', '5'].includes(row.enterpriseType)) {
      issues.push({
        severity: 'error',
        rowId: row.id,
        investeeName: name,
        message: `「${name}」企业类型须为 1～5`,
      })
    }
    if (needsHoldingVotingReason(row) && !row.holdingVotingDifferenceReason.trim()) {
      issues.push({
        severity: 'warning',
        rowId: row.id,
        investeeName: name,
        message: `「${name}」持股与表决权不一致，请填写原因`,
      })
    }
    if (needsLessThanHalfControlReason(row) && !row.lessThanHalfControlReason.trim()) {
      issues.push({
        severity: 'warning',
        rowId: row.id,
        investeeName: name,
        message: `「${name}」表决权不足半数，请填写形成控制的原因`,
      })
    }
    if (needsMajorityNoControlReason(row) && !row.majorityNoControlReason.trim()) {
      issues.push({
        severity: 'warning',
        rowId: row.id,
        investeeName: name,
        message: `「${name}」表决权达到半数以上但未列为子公司，请填写未形成控制的原因`,
      })
    }
    if (row.groupType === 'subsidiary' && !row.acquisitionMethod.trim()) {
      issues.push({
        severity: 'warning',
        rowId: row.id,
        investeeName: name,
        message: `「${name}」建议填写取得方式`,
      })
    }
  }

  return issues
}

function labelOf(groupType: G7BasicInfoGroup): string {
  return G7_BASIC_INFO_GROUPS.find(group => group.value === groupType)?.label ?? groupType
}

export interface G7BasicInfoSyncSource {
  groupType: Exclude<G7BasicInfoGroup, 'joint_operation'>
  investeeName: string
  directHoldingRatio: number | null
  votingRatio: number | null
  investmentAmount: number | null
  acquisitionMethod: string
}

/** 从 G7-2 明细状态提取可同步到 G7-4 的被投资单位（不含共同经营）。 */
export function sourcesFromG7DetailPayload(payload: unknown): G7BasicInfoSyncSource[] {
  const rows: Record<string, unknown>[] = Array.isArray(payload)
    ? payload as Record<string, unknown>[]
    : Array.isArray((payload as any)?.rows)
      ? (payload as any).rows
      : Array.isArray((payload as any)?.costRows)
        ? [
            ...((payload as any).costRows || []),
            ...((payload as any).equityRows || []),
          ]
        : []

  const sources: G7BasicInfoSyncSource[] = []
  for (const raw of rows) {
    const name = stringValue(raw.investeeName ?? raw.investee_name)
    if (!name) continue
    const section = stringValue(raw.section)
    let groupType: G7BasicInfoSyncSource['groupType'] | null = null
    if (section === 'cost' || (!section && stringValue(raw.controlType) === '子公司')) {
      groupType = 'subsidiary'
    } else if (section === 'equity' || raw.relationship) {
      groupType = raw.relationship === 'associate' ? 'associate' : 'joint_venture'
    } else if (section === 'impairment') {
      continue
    } else if (GROUP_ALIASES[stringValue(raw.controlType)] === 'subsidiary') {
      groupType = 'subsidiary'
    } else {
      continue
    }

    const ratioRaw = numberOrNull(
      raw.auditedClosingRatio ?? raw.closingRatio ?? raw.investmentRatio,
    )
    const votingRaw = numberOrNull(raw.votingRatio)
    // G7-2 比例按 0～1 小数存储，同步到 G7-4 时换算为百分数
    sources.push({
      groupType,
      investeeName: name,
      directHoldingRatio: toPercentRatio(ratioRaw, { force: true }),
      votingRatio: toPercentRatio(votingRaw ?? ratioRaw, { force: true }),
      investmentAmount: numberOrNull(
        raw.auditedClosingAmount ?? raw.closingAmount ?? raw.initialInvestmentCost,
      ),
      acquisitionMethod: stringValue(raw.investmentMethod),
    })
  }
  return sources
}

export interface G7BasicInfoSyncResult {
  rows: G7BasicInfoRow[]
  added: number
  filled: number
}

/**
 * 按公司名称把 G7-2 名单并入 G7-4：
 * - 缺失单位新增；
 * - 已有单位只回填空的比例/投资额/取得方式，不覆盖手工录入；
 * - 不删除 G7-4 中已有、但 G7-2 没有的单位（如共同经营）。
 */
export function syncG7BasicInfoFromSources(
  existing: G7BasicInfoRow[],
  sources: G7BasicInfoSyncSource[],
): G7BasicInfoSyncResult {
  const rows = existing.map(row => ({ ...row }))
  let added = 0
  let filled = 0

  for (const source of sources) {
    const hit = rows.find(row => row.investeeName.trim() === source.investeeName)
    if (!hit) {
      const created = createG7BasicInfoRow(source.groupType, 0, source.investeeName)
      created.directHoldingRatio = source.directHoldingRatio
      created.votingRatio = source.votingRatio
      created.investmentAmount = source.investmentAmount
      created.acquisitionMethod = source.acquisitionMethod
      rows.push(created)
      added += 1
      continue
    }
    if (hit.groupType !== source.groupType && hit.groupType !== 'joint_operation') {
      // 分类以 G7-4 手工判断为准，仅提示性不改写
    }
    if (hit.directHoldingRatio == null && source.directHoldingRatio != null) {
      hit.directHoldingRatio = source.directHoldingRatio
      filled += 1
    }
    if (hit.votingRatio == null && source.votingRatio != null) {
      hit.votingRatio = source.votingRatio
      filled += 1
    }
    if (hit.investmentAmount == null && source.investmentAmount != null) {
      hit.investmentAmount = source.investmentAmount
      filled += 1
    }
    if (!hit.acquisitionMethod.trim() && source.acquisitionMethod) {
      hit.acquisitionMethod = source.acquisitionMethod
      filled += 1
    }
  }

  resequenceG7BasicInfoRows(rows)
  return { rows, added, filled }
}

/** 持久化时附带 ratioScale，避免再次被当成小数迁移。 */
export function serializeG7BasicInfoRows(rows: G7BasicInfoRow[]): Array<G7BasicInfoRow & { ratioScale: 'percent' }> {
  return rows.map(row => ({ ...row, ratioScale: 'percent' as const }))
}
