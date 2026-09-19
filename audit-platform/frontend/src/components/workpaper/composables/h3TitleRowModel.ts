/**
 * H3-12 产权核对行模型与纯函数（供 composable / 跨表联动共用）
 */

export type CertStatus = '' | '已办证' | '办证中' | '无需办证'
export type SourceTag = 'H3-2' | 'H3-9' | 'L1' | '手工'

export interface TitleRow {
  rowId: string
  seq: number
  bookOwner: string
  assetCode: string
  assetName: string
  location: string
  bookArea: number
  bookValue: number
  certName: string
  titleCertNo: string
  certArea: number
  areaDiff: number
  certOwner: string
  isAuditEntity: string
  matchConsistent: string
  inconsistentReason: string
  certPurpose: string
  actualPurpose: string
  purposeConsistent: boolean
  isRestricted: string
  mortgageArea: number
  mortgageValue: number
  mortgageNature: string
  seizure: string
  restriction: string
  refIndex: string
  remark: string
  /** 办证状态 */
  certStatus: CertStatus
  /** 预计办证日 YYYY-MM-DD */
  expectedCertDate: string
  /** 办证进度说明 */
  certProgressNote: string
  /** 是否存在权属纠纷 */
  hasDispute: string
  /** 数据来源标记 */
  sourceTags: string
  /** 证载面积待原件核实 */
  certAreaPending: boolean
  /** 是否纳入抽样核对 */
  sampled: boolean
  /** OCR 原始识别轨迹（可选） */
  ocrResult: string
}

/** 绝对面积容差（㎡） */
export const AREA_ABS_TOLERANCE = 1
/** 相对面积容差（0.5%） */
export const AREA_PCT_TOLERANCE = 0.005
const AREA_EPS = 0.01

export function calcAreaDiff(certArea: number, bookArea: number): number {
  return (Number(certArea) || 0) - (Number(bookArea) || 0)
}

/** 面积差异是否超出可接受容差（绝对≥1㎡ 且 相对≥0.5%） */
export function isAreaAnomaly(certArea: number, bookArea: number): boolean {
  const diff = Math.abs(calcAreaDiff(certArea, bookArea))
  if (diff <= AREA_EPS) return false
  if (diff <= AREA_ABS_TOLERANCE) return false
  const base = Math.max(Math.abs(Number(bookArea) || 0), Math.abs(Number(certArea) || 0), 1)
  return diff / base >= AREA_PCT_TOLERANCE
}

/** 有差异但在容差内（可接受差异） */
export function isAreaAcceptableDiff(certArea: number, bookArea: number): boolean {
  const diff = Math.abs(calcAreaDiff(certArea, bookArea))
  return diff > AREA_EPS && !isAreaAnomaly(certArea, bookArea)
}

export function suggestMatchConsistent(row: Pick<
  TitleRow,
  'isAuditEntity' | 'areaDiff' | 'certPurpose' | 'actualPurpose' | 'inconsistentReason' | 'certArea' | 'bookArea'
>): string {
  if (row.isAuditEntity === '否') return '否'
  if (isAreaAnomaly(row.certArea ?? 0, row.bookArea ?? 0)) return '否'
  if (row.certPurpose && row.actualPurpose && row.certPurpose !== row.actualPurpose) return '否'
  if ((row.inconsistentReason || '').trim()) return '否'
  return '是'
}

export function normalizeTitleRow(raw: any, idx?: number): TitleRow {
  const certArea = Number(raw.certArea) || 0
  const bookArea = Number(raw.bookArea) || 0
  const areaDiff = calcAreaDiff(certArea, bookArea)
  const certPurpose = raw.certPurpose ?? ''
  const actualPurpose = raw.actualPurpose ?? ''
  const isAuditEntity = typeof raw.isAuditEntity === 'string'
    ? raw.isAuditEntity
    : (raw.isAuditEntity === false ? '否' : (raw.isAuditEntity === true ? '是' : ''))
  const certStatus = (['已办证', '办证中', '无需办证'].includes(raw.certStatus) ? raw.certStatus : '') as TitleRow['certStatus']
  const row: TitleRow = {
    rowId: raw.rowId ?? `tt-${Math.random().toString(36).slice(2, 8)}`,
    seq: raw.seq ?? (idx != null ? idx + 1 : 1),
    bookOwner: raw.bookOwner ?? raw.certOwner ?? '',
    assetCode: raw.assetCode ?? '',
    assetName: raw.assetName ?? '',
    location: raw.location ?? '',
    bookArea,
    bookValue: Number(raw.bookValue) || 0,
    certName: raw.certName ?? '',
    titleCertNo: raw.titleCertNo ?? raw.titleNo ?? '',
    certArea,
    areaDiff,
    certOwner: raw.certOwner ?? raw.bookOwner ?? '',
    isAuditEntity,
    matchConsistent: raw.matchConsistent ?? '',
    inconsistentReason: raw.inconsistentReason ?? '',
    certPurpose,
    actualPurpose,
    purposeConsistent: raw.purposeConsistent ?? (certPurpose === actualPurpose),
    isRestricted: raw.isRestricted ?? (raw.mortgage ? '是' : ''),
    mortgageArea: Number(raw.mortgageArea) || 0,
    mortgageValue: Number(raw.mortgageValue) || 0,
    mortgageNature: raw.mortgageNature ?? raw.mortgage ?? '',
    seizure: raw.seizure ?? '',
    restriction: raw.restriction ?? '',
    refIndex: raw.refIndex ?? '',
    remark: raw.remark ?? '',
    certStatus: certStatus || (raw.titleCertNo || raw.titleNo ? '已办证' : ''),
    expectedCertDate: raw.expectedCertDate ?? '',
    certProgressNote: raw.certProgressNote ?? '',
    hasDispute: raw.hasDispute ?? '',
    sourceTags: raw.sourceTags ?? '',
    certAreaPending: !!raw.certAreaPending,
    sampled: !!raw.sampled,
    ocrResult: raw.ocrResult ?? '',
  }
  if (!row.matchConsistent) row.matchConsistent = suggestMatchConsistent(row)
  row.purposeConsistent = !certPurpose || !actualPurpose || certPurpose === actualPurpose
  return row
}

export function recomputeTitleRow(row: TitleRow): void {
  row.certArea = Number(row.certArea) || 0
  row.bookArea = Number(row.bookArea) || 0
  row.areaDiff = calcAreaDiff(row.certArea, row.bookArea)
  row.purposeConsistent = !row.certPurpose || !row.actualPurpose || row.certPurpose === row.actualPurpose
}

export function addSourceTag(row: TitleRow, tag: SourceTag): void {
  const tags = new Set((row.sourceTags || '').split(/[,，]/).map((s) => s.trim()).filter(Boolean))
  tags.add(tag)
  row.sourceTags = [...tags].join(',')
}

export function normName(s: string): string {
  return (s || '').trim().toLowerCase().replace(/\s+/g, '')
}

/** 名称模糊分：1=精确，0.8=包含，0=不匹配 */
export function nameSimilarity(a: string, b: string): number {
  const x = normName(a)
  const y = normName(b)
  if (!x || !y) return 0
  if (x === y) return 1
  if (x.includes(y) || y.includes(x)) return 0.8
  return 0
}

export const PROCEDURE_TEMPLATE = `1. 取得投资性房地产产权证书原件，与复印件（加盖被审计单位公章）核对一致，并留存复印件作为底稿附件。
2. 将证载权利人、坐落、面积、用途与账面明细及盘点记录逐项比对。
3. 结合银行借款（L1）及抵质押检查，了解是否存在重大抵押、担保、查封等权利限制，并交叉索引。
4. 对正在办理权属证明的大额资产，了解办理进度、预计办证日，确认是否存在权属纠纷或实质性障碍。
5. 评估权属瑕疵及权利限制对报表认定及附注披露的影响。`

/** 从底稿 htmlData 解析被审计单位名称（project_context.client_name） */
export function resolveProjectClientName(htmlData?: unknown): string {
  if (!htmlData || typeof htmlData !== 'object') return ''
  const d = htmlData as Record<string, unknown>
  const ctx = (d.project_context ?? d.projectContext) as Record<string, unknown> | undefined
  if (!ctx || typeof ctx !== 'object') return ''
  return String(ctx.client_name ?? ctx.entity_name ?? '').trim()
}

export function buildRestrictionDisclosureText(rows: TitleRow[]): string {
  const restricted = rows.filter((r) => r.isRestricted === '是' || (r.mortgageValue > 0))
  if (!restricted.length) {
    return '经检查，本期投资性房地产未见重大抵押、查封或其他权利限制情形。（来源:H3-12）'
  }
  const lines = restricted.map((r, i) => {
    const parts = [
      `${i + 1}. ${r.assetName || '未命名资产'}`,
      r.titleCertNo ? `权证:${r.titleCertNo}` : '',
      r.mortgageNature ? `性质:${r.mortgageNature}` : '抵押/受限',
      r.mortgageArea ? `抵押面积:${r.mortgageArea}㎡` : '',
      r.mortgageValue ? `抵押价值:${r.mortgageValue.toLocaleString('zh-CN')}` : '',
      r.seizure ? `查封:${r.seizure}` : '',
      r.refIndex ? `索引:${r.refIndex}` : '',
    ].filter(Boolean)
    return parts.join('；')
  })
  return `投资性房地产权利限制情况如下（来源:H3-12）：\n${lines.join('\n')}`
}
