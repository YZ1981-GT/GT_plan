/**
 * G8-6 凭证检查 ↔ G8-2/G8-4/G8-5 跨表联动（纯函数）
 */
import { matchG8InvesteeKey, G8_DETAIL_KEY, G8_FV_KEY, G8_DESIGNATION_KEY } from './g8CrossHelpers'
import { parseNum } from './useG8FormulaEngine'
import type { ChecklistResponse } from './useF1FormData'

/** 异常定性：金额类 vs 程序/分类类（影响是否进入错报推断） */
export type G8AbnormalType = 'none' | 'qualitative' | 'quantitative' | 'mixed'

export type G8VoucherSourceFilter = 'all' | '抽凭' | '截止' | '手工'

export interface G8DetailOption {
  rowId: string
  investeeName: string
  label: string
}

export interface G8VoucherLinkHint {
  code: 'fv-diff' | 'fv-level3' | 'desig-trading' | 'desig-incomplete' | 'desig-oci' | 'no-detail'
  level: 'info' | 'warning' | 'danger'
  text: string
  /** 建议将核对4标为不通过 */
  suggestCheck4Fail?: boolean
  /** 建议将核对5标为不通过 */
  suggestCheck5Fail?: boolean
}

export interface G8VoucherCrossSnapshot {
  details: G8DetailOption[]
  fvByInvestee: Map<string, { name: string; diff: number; level: string }>
  desigByInvestee: Map<string, {
    name: string
    hasTrading: boolean
    ociOk: boolean
    complete: boolean
  }>
}

/** 联动所需的行最小字段（避免与 useG8VoucherCheck 循环依赖） */
export interface G8VoucherLinkRow {
  source?: string
  investeeName?: string
  detailRowId?: string
  isAbnormal: boolean
  forceAbnormal: boolean
  abnormalDesc: string
  check1OriginalComplete: boolean | null
  check2Authorization: boolean | null
  check3Accounting: boolean | null
  check4FairValueCorrect: boolean | null
  check5OCICorrect: boolean | null
}

function parseJsonArray(raw: string | null | undefined): Record<string, unknown>[] {
  if (!raw) return []
  try {
    const arr = JSON.parse(raw)
    return Array.isArray(arr) ? arr : []
  } catch {
    return []
  }
}

/** 从 allResponses 提取跨表快照（供联动提示） */
export function buildG8VoucherCrossSnapshot(
  responses: Map<string, ChecklistResponse>,
): G8VoucherCrossSnapshot {
  const detailsRaw = parseJsonArray(responses.get(G8_DETAIL_KEY)?.remark)
  const details: G8DetailOption[] = detailsRaw
    .map((r, i) => {
      const name = String(r.investeeName ?? '').trim()
      const rowId = String(r.rowId ?? r.id ?? `d-${i}`)
      return {
        rowId,
        investeeName: name,
        label: name ? `${name}` : `（未命名#${i + 1}）`,
      }
    })
    .filter((d) => d.investeeName)

  const fvByInvestee = new Map<string, { name: string; diff: number; level: string }>()
  for (const r of parseJsonArray(responses.get(G8_FV_KEY)?.remark)) {
    const name = String(r.investeeName ?? '').trim()
    if (!name) continue
    const unadj = parseNum(r.closingUnadjustedFV)
    const audited = parseNum(r.closingAuditedFV)
    const diff = r.fairValueDiff != null ? parseNum(r.fairValueDiff) : audited - unadj
    fvByInvestee.set(matchG8InvesteeKey(name), {
      name,
      diff,
      level: String(r.fairValueLevel ?? ''),
    })
  }

  const desigByInvestee = new Map<string, {
    name: string
    hasTrading: boolean
    ociOk: boolean
    complete: boolean
  }>()
  for (const r of parseJsonArray(responses.get(G8_DESIGNATION_KEY)?.remark)) {
    const name = String(r.investeeName ?? '').trim()
    if (!name) continue
    const tradingNearTermSale = String(r.tradingNearTermSale ?? '')
    const tradingPortfolioShortTerm = String(r.tradingPortfolioShortTerm ?? '')
    const tradingDerivative = String(r.tradingDerivative ?? '')
    const hasTrading =
      tradingNearTermSale === 'yes'
      || tradingPortfolioShortTerm === 'yes'
      || tradingDerivative === 'yes'
    const equityInstrument = String(r.equityInstrument ?? '')
    const designatedFvtoci = String(r.designatedFvtoci ?? '')
    const fvReliable = String(r.fvReliable ?? '')
    const fields = [
      tradingNearTermSale,
      tradingPortfolioShortTerm,
      tradingDerivative,
      equityInstrument,
      designatedFvtoci,
      fvReliable,
    ]
    const complete = fields.every((f) => f !== '')
    const ociOk =
      equityInstrument === 'yes'
      && designatedFvtoci === 'yes'
      && fvReliable === 'yes'
      && !hasTrading
    desigByInvestee.set(matchG8InvesteeKey(name), { name, hasTrading, ociOk, complete })
  }

  return { details, fvByInvestee, desigByInvestee }
}

/**
 * 异常类型：
 * - quantitative：公允价值计量不通过（金额向）
 * - qualitative：完整/授权/账务/OCI 不通过或强制异常
 * - mixed：两者皆有
 */
export function deriveG8AbnormalType(row: G8VoucherLinkRow): G8AbnormalType {
  if (!row.isAbnormal) return 'none'
  const quantitative = row.check4FairValueCorrect === false
  const qualitative =
    row.forceAbnormal
    || row.check1OriginalComplete === false
    || row.check2Authorization === false
    || row.check3Accounting === false
    || row.check5OCICorrect === false
  if (quantitative && qualitative) return 'mixed'
  if (quantitative) return 'quantitative'
  if (qualitative) return 'qualitative'
  return 'qualitative'
}

export function formatG8AbnormalType(t: G8AbnormalType): string {
  switch (t) {
    case 'quantitative': return '金额'
    case 'qualitative': return '定性'
    case 'mixed': return '混合'
    default: return '—'
  }
}

/** 按被投资单位生成 G8-4/G8-5 联动提示 */
export function buildG8VoucherLinkHints(
  investeeName: string,
  snap: G8VoucherCrossSnapshot,
): G8VoucherLinkHint[] {
  const name = (investeeName || '').trim()
  const hints: G8VoucherLinkHint[] = []
  if (!name) {
    if (snap.details.length > 0) {
      hints.push({
        code: 'no-detail',
        level: 'info',
        text: '未挂接明细：建议选择 G8-2 被投资单位',
      })
    }
    return hints
  }

  const key = matchG8InvesteeKey(name)
  const fv = snap.fvByInvestee.get(key)
  if (fv) {
    if (Math.abs(fv.diff) > 0.01) {
      hints.push({
        code: 'fv-diff',
        level: Math.abs(fv.diff) > 1000 ? 'danger' : 'warning',
        text: `G8-4 公允差异 ${fv.diff.toLocaleString('zh-CN', { maximumFractionDigits: 2 })}，建议复核核对4`,
        suggestCheck4Fail: true,
      })
    }
    if (/level\s*3|第三/i.test(fv.level)) {
      hints.push({
        code: 'fv-level3',
        level: 'info',
        text: 'G8-4 为 Level3，请核验估值技术与不可观察输入值',
      })
    }
  }

  const desig = snap.desigByInvestee.get(key)
  if (desig) {
    if (desig.hasTrading) {
      hints.push({
        code: 'desig-trading',
        level: 'danger',
        text: 'G8-5 存在交易性特征，不宜指定 FVOCI，建议复核核对5',
        suggestCheck5Fail: true,
      })
    } else if (!desig.ociOk && desig.complete) {
      hints.push({
        code: 'desig-oci',
        level: 'warning',
        text: 'G8-5 指定条件未齐备，建议复核 OCI 计入（核对5）',
        suggestCheck5Fail: true,
      })
    } else if (!desig.complete) {
      hints.push({
        code: 'desig-incomplete',
        level: 'info',
        text: 'G8-5 适当性检查尚未填完',
      })
    }
  }

  return hints
}

export function filterG8VoucherRowsBySource<T extends { source?: string }>(
  rows: T[],
  filter: G8VoucherSourceFilter,
): T[] {
  if (filter === 'all') return rows
  if (filter === '手工') {
    return rows.filter((r) => !r.source || r.source === '手工')
  }
  return rows.filter((r) => r.source === filter)
}

export function countG8VoucherBySource(rows: Array<{ source?: string }>): Record<G8VoucherSourceFilter, number> {
  return {
    all: rows.length,
    抽凭: rows.filter((r) => r.source === '抽凭').length,
    截止: rows.filter((r) => r.source === '截止').length,
    手工: rows.filter((r) => !r.source || r.source === '手工').length,
  }
}

/** 应用联动建议：仅改「未测」项，不覆盖已明确「通过」 */
export function applyG8LinkHintSuggestions(
  row: G8VoucherLinkRow,
  hints: G8VoucherLinkHint[],
): Partial<G8VoucherLinkRow> {
  const patch: Partial<G8VoucherLinkRow> = {}
  const want4 = hints.some((h) => h.suggestCheck4Fail)
  const want5 = hints.some((h) => h.suggestCheck5Fail)
  if (want4 && row.check4FairValueCorrect == null) {
    patch.check4FairValueCorrect = false
  }
  if (want5 && row.check5OCICorrect == null) {
    patch.check5OCICorrect = false
  }
  if (Object.keys(patch).length && !row.abnormalDesc) {
    patch.abnormalDesc = hints
      .filter((h) => h.suggestCheck4Fail || h.suggestCheck5Fail)
      .map((h) => h.text)
      .join('；')
  }
  return patch
}

/** 金额类异常行 → 创建错报请求体 */
export function mapG8VoucherToMisstatementBody(
  row: G8VoucherLinkRow & {
    voucherNo?: string
    businessContent?: string
    debitAmount?: number
    creditAmount?: number
    rowId?: string
    abnormalType?: string
  },
  year: number,
  accountCode = '1503',
): Record<string, unknown> {
  const amount = Math.max(Math.abs(row.debitAmount || 0), Math.abs(row.creditAmount || 0))
  const descParts = [
    row.voucherNo ? `凭证 ${row.voucherNo}` : '',
    row.investeeName || '',
    row.abnormalDesc || row.businessContent || 'G8-6 凭证检查金额类异常',
  ].filter(Boolean)
  return {
    year,
    misstatement_type: 'factual',
    misstatement_description: descParts.join('｜'),
    affected_account_code: accountCode,
    affected_account_name: '其他权益工具投资',
    misstatement_amount: String(amount),
    auditor_evaluation: `来源 G8-6；类型=${row.abnormalType || 'quantitative'}；rowId=${row.rowId || ''}`,
  }
}

/** 事件总线 a13:push-misstatement 的条目 */
export function mapG8VoucherToA13PushItem(
  row: G8VoucherLinkRow & {
    voucherNo?: string
    businessContent?: string
    debitAmount?: number
    creditAmount?: number
  },
): Record<string, unknown> {
  return {
    wpCode: 'G8-6',
    entryType: 'AJE',
    description: row.abnormalDesc || row.businessContent || 'G8-6 金额类异常',
    reportItem: '其他权益工具投资',
    accountName: row.investeeName || '其他权益工具投资',
    debitAmount: row.debitAmount || 0,
    creditAmount: row.creditAmount || 0,
    indexRef: `G8-6/${row.voucherNo || ''}`,
  }
}

export function selectG8QuantitativeAbnormals<T extends { isAbnormal: boolean; abnormalType?: string }>(
  rows: T[],
): T[] {
  return rows.filter(
    (r) => r.isAbnormal && (r.abnormalType === 'quantitative' || r.abnormalType === 'mixed'),
  )
}
