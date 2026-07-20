/**
 * G8 附注披露行/列定义 — 对齐底稿模板
 * backend/wp_templates/G/G8 其他权益工具投资.xlsx
 *
 * 上市公司（18×7）：余额表 R8–R12（3 明细+合计）+ 指定原因 R13–R14 + OCI 变动表 R15–R18（3 明细）
 * 国企（20×7）：（1）余额 R7–R12 + 指定原因 R13 +（2）期末明细 R14–R20（4 明细+合计）
 */

export type G8DisclosureSection = 'balance' | 'designation' | 'oci' | 'detail'

/** @deprecated 扁平行已改为分表结构；保留类型供旧引用兼容 */
export interface G8DisclosureRowDef {
  rowKey: string
  label: string
  section: G8DisclosureSection
  isNarrative?: boolean
}

/** G8-1 审定表明细行标签（供跨表带入参考，非附注固定行） */
export const G8_ADJUDICATION_SCHEMA_LABELS = [
  '权益工具投资（FVOCI）',
  '其他',
  ...Array.from({ length: 8 }, (_, i) => `被投资单位${i + 1}`),
] as const

/** 模板槽位数 */
export const G8_LISTED_BALANCE_SLOTS = 3
export const G8_LISTED_OCI_SLOTS = 3
export const G8_SOE_BALANCE_SLOTS = 3
export const G8_SOE_DETAIL_SLOTS = 4

export const G8_LISTED_INTRO =
  '（15号文第十九条（九）分项列示其他权益工具投资期初余额、期末余额、本期计入其他综合收益的利得和损失、本期末累计计入其他综合收益的利得和损失、本期确认的股利收入以及指定为以公允价值计量且其变动计入其他综合收益的原因。本期存在终止确认的，应分项披露终止确认的原因，以及因终止确认转入留存收益的累计利得和损失。）'

export const G8_LISTED_DESIGNATION_HINT =
  '【披露企业将上述各项目指定为以公允价值计量且其变动计入其他综合收益的原因。例如：'

export const G8_LISTED_DESIGNATION_PLACEHOLDER =
  '由于[项目名称1]是本公司出于战略目的而计划长期持有的投资，因此本公司将其指定为以公允价值计量且其变动计入其他综合收益的金融资产。'

export const G8_SOE_SECTION1_TITLE = '（1）其他权益工具投资情况'
export const G8_SOE_SECTION2_TITLE = '（2）期末其他权益工具投资情况'

export const G8_SOE_DESIGNATION_HINT =
  '[披露企业将上述各项目指定为以公允价值计量且其变动计入其他综合收益的原因。例如：'

export const G8_SOE_DESIGNATION_PLACEHOLDER =
  '由于[项目名称1]是本公司出于战略目的而计划长期持有的投资，因此本公司将其指定为以公允价值计量且其变动计入其他综合收益的金融资产。]'

export interface G8DiscBalanceRow {
  rowKey: string
  label: string
  closing: number
  prior: number
  isTotal?: boolean
}

export interface G8DiscListedOciRow {
  rowKey: string
  label: string
  ociPeriod: number
  ociCumulative: number
  dividend: number
  transferToRE: number
  derecogReason: string
}

export interface G8DiscSoeDetailRow {
  rowKey: string
  label: string
  dividend: number
  ociPeriod: number
  ociCumulative: number
  transferAmt: number
  transferReason: string
  isTotal?: boolean
}

/** 持久化 v2（对齐模板分表） */
export interface G8DisclosureStoreV2 {
  v: 2
  balanceRows: Array<{ label: string; closing: number; prior: number }>
  designationText: string
  ociRows?: Array<{
    label: string
    ociPeriod: number
    ociCumulative: number
    dividend: number
    transferToRE: number
    derecogReason: string
  }>
  detailRows?: Array<{
    label: string
    dividend: number
    ociPeriod: number
    ociCumulative: number
    transferAmt: number
    transferReason: string
  }>
}

function emptyBalance(n: number) {
  return Array.from({ length: n }, () => ({ label: '', closing: 0, prior: 0 }))
}

function emptyListedOci(n: number) {
  return Array.from({ length: n }, () => ({
    label: '',
    ociPeriod: 0,
    ociCumulative: 0,
    dividend: 0,
    transferToRE: 0,
    derecogReason: '',
  }))
}

function emptySoeDetail(n: number) {
  return Array.from({ length: n }, () => ({
    label: '',
    dividend: 0,
    ociPeriod: 0,
    ociCumulative: 0,
    transferAmt: 0,
    transferReason: '',
  }))
}

export function createEmptyListedStore(): G8DisclosureStoreV2 {
  return {
    v: 2,
    balanceRows: emptyBalance(G8_LISTED_BALANCE_SLOTS),
    designationText: '',
    ociRows: emptyListedOci(G8_LISTED_OCI_SLOTS),
  }
}

export function createEmptySoeStore(): G8DisclosureStoreV2 {
  return {
    v: 2,
    balanceRows: emptyBalance(G8_SOE_BALANCE_SLOTS),
    designationText: '',
    detailRows: emptySoeDetail(G8_SOE_DETAIL_SLOTS),
  }
}

/** 旧扁平键 → v2（兼容已保存底稿） */
export function migrateLegacyDisclosureStore(
  raw: unknown,
  variant: 'listed' | 'soe',
): G8DisclosureStoreV2 {
  const base = variant === 'listed' ? createEmptyListedStore() : createEmptySoeStore()
  if (!raw || typeof raw !== 'object') return base
  const obj = raw as Record<string, any>

  if (obj.v === 2 && Array.isArray(obj.balanceRows)) {
    const balSlots = variant === 'listed' ? G8_LISTED_BALANCE_SLOTS : G8_SOE_BALANCE_SLOTS
    base.balanceRows = emptyBalance(balSlots).map((d, i) => ({
      label: String(obj.balanceRows[i]?.label ?? ''),
      closing: Number(obj.balanceRows[i]?.closing ?? 0) || 0,
      prior: Number(obj.balanceRows[i]?.prior ?? 0) || 0,
    }))
    base.designationText = String(obj.designationText ?? '')
    if (variant === 'listed') {
      base.ociRows = emptyListedOci(G8_LISTED_OCI_SLOTS).map((d, i) => ({
        label: String(obj.ociRows?.[i]?.label ?? ''),
        ociPeriod: Number(obj.ociRows?.[i]?.ociPeriod ?? 0) || 0,
        ociCumulative: Number(obj.ociRows?.[i]?.ociCumulative ?? 0) || 0,
        dividend: Number(obj.ociRows?.[i]?.dividend ?? 0) || 0,
        transferToRE: Number(obj.ociRows?.[i]?.transferToRE ?? 0) || 0,
        derecogReason: String(obj.ociRows?.[i]?.derecogReason ?? ''),
      }))
    } else {
      base.detailRows = emptySoeDetail(G8_SOE_DETAIL_SLOTS).map((d, i) => ({
        label: String(obj.detailRows?.[i]?.label ?? ''),
        dividend: Number(obj.detailRows?.[i]?.dividend ?? 0) || 0,
        ociPeriod: Number(obj.detailRows?.[i]?.ociPeriod ?? 0) || 0,
        ociCumulative: Number(obj.detailRows?.[i]?.ociCumulative ?? 0) || 0,
        transferAmt: Number(obj.detailRows?.[i]?.transferAmt ?? 0) || 0,
        transferReason: String(obj.detailRows?.[i]?.transferReason ?? ''),
      }))
    }
    return base
  }

  // legacy flat: listed_bal_N / soe_bal_N / listed_oci_N / soe_detail_N / *_designation
  const balSlots = variant === 'listed' ? G8_LISTED_BALANCE_SLOTS : G8_SOE_BALANCE_SLOTS
  const prefix = variant === 'listed' ? 'listed' : 'soe'
  base.balanceRows = emptyBalance(balSlots).map((d, i) => {
    const leg = obj[`${prefix}_bal_${i + 1}`]
    return {
      label: String(leg?.label ?? ''),
      closing: Number(leg?.currentAmount ?? leg?.closing ?? 0) || 0,
      prior: Number(leg?.priorAmount ?? leg?.prior ?? 0) || 0,
    }
  })
  const desig = obj[`${prefix}_designation`]
  base.designationText = String(desig?.noteText ?? desig?.designationText ?? '')

  if (variant === 'listed') {
    base.ociRows = emptyListedOci(G8_LISTED_OCI_SLOTS).map((d, i) => {
      const leg = obj[`listed_oci_${i + 1}`]
      return {
        label: String(leg?.label ?? ''),
        ociPeriod: Number(leg?.currentAmount ?? leg?.ociPeriod ?? 0) || 0,
        ociCumulative: Number(leg?.priorAmount ?? leg?.ociCumulative ?? 0) || 0,
        dividend: Number(leg?.dividend ?? 0) || 0,
        transferToRE: Number(leg?.transferToRE ?? 0) || 0,
        derecogReason: String(leg?.noteText ?? leg?.derecogReason ?? ''),
      }
    })
  } else {
    base.detailRows = emptySoeDetail(G8_SOE_DETAIL_SLOTS).map((d, i) => {
      const leg = obj[`soe_detail_${i + 1}`]
      return {
        label: String(leg?.label ?? `项目名称${i + 1}`),
        dividend: Number(leg?.currentAmount ?? leg?.dividend ?? 0) || 0,
        ociPeriod: Number(leg?.priorAmount ?? leg?.ociPeriod ?? 0) || 0,
        ociCumulative: Number(leg?.ociCumulative ?? 0) || 0,
        transferAmt: Number(leg?.transferAmt ?? 0) || 0,
        transferReason: String(leg?.noteText ?? leg?.transferReason ?? ''),
      }
    })
  }
  return base
}

export function disclosureStoreHasContent(store: G8DisclosureStoreV2): boolean {
  if ((store.designationText || '').trim()) return true
  if (store.balanceRows.some((r) => Math.abs(r.closing) > 0.01 || Math.abs(r.prior) > 0.01 || !!(r.label || '').trim())) {
    return true
  }
  if (store.ociRows?.some((r) =>
    Math.abs(r.ociPeriod) > 0.01 || Math.abs(r.ociCumulative) > 0.01 || Math.abs(r.dividend) > 0.01
    || Math.abs(r.transferToRE) > 0.01 || !!(r.label || '').trim() || !!(r.derecogReason || '').trim(),
  )) return true
  if (store.detailRows?.some((r) =>
    Math.abs(r.dividend) > 0.01 || Math.abs(r.ociPeriod) > 0.01 || Math.abs(r.ociCumulative) > 0.01
    || Math.abs(r.transferAmt) > 0.01 || !!(r.label || '').trim() || !!(r.transferReason || '').trim(),
  )) return true
  return false
}

const DIFF_TOL = 0.01

/** 解析附注 remark：是否有实质内容（金额/指定原因/项目名） */
export function g8DisclosureRemarkHasContent(
  raw: string | null | undefined,
  variant: 'listed' | 'soe' = 'listed',
): boolean {
  if (!raw || !String(raw).trim() || raw === '{}') return false
  try {
    return disclosureStoreHasContent(migrateLegacyDisclosureStore(JSON.parse(raw), variant))
  } catch {
    return false
  }
}

/** 余额合计期末（兼容 v2 / 旧扁平） */
export function g8DisclosureBalanceClosingTotal(
  raw: string | null | undefined,
  variant: 'listed' | 'soe' = 'listed',
): number {
  if (!raw) return 0
  try {
    const store = migrateLegacyDisclosureStore(JSON.parse(raw), variant)
    return store.balanceRows.reduce((s, r) => s + (Number(r.closing) || 0), 0)
  } catch {
    return 0
  }
}

export function g8DisclosureDesignationText(
  raw: string | null | undefined,
  variant: 'listed' | 'soe' = 'listed',
): string {
  if (!raw) return ''
  try {
    return migrateLegacyDisclosureStore(JSON.parse(raw), variant).designationText.trim()
  } catch {
    return ''
  }
}

/** 附注完成：结论 + 指定原因非空 + 已发布审定且余额合计勾稽一致 */
export function isG8DisclosureSheetComplete(
  m: Map<string, any>,
  variant: 'listed' | 'soe',
): boolean {
  const storeKey = variant === 'listed' ? 'G8-disclosure-listed' : 'G8-disclosure-soe'
  const conclusionKey = `G8-disclosure-${variant}-audit-conclusion`
  if (!(m.get(conclusionKey)?.remark || '').trim()) return false

  const raw = m.get(storeKey)?.remark as string | undefined
  if (!raw) return false
  if (!g8DisclosureDesignationText(raw, variant)) return false

  const adjRaw = m.get('G8-1-adjudicated-amount')?.conclusion
  if (adjRaw == null || adjRaw === '') return false
  const adj = Number(adjRaw)
  if (!Number.isFinite(adj)) return false

  const closing = g8DisclosureBalanceClosingTotal(raw, variant)
  return Math.abs(closing - adj) <= DIFF_TOL
}

/** @deprecated 扁平 schema；保留空数组避免破坏旧 import 长度断言 */
export const G8_DISCLOSURE_LISTED_SCHEMA: G8DisclosureRowDef[] = []
export const G8_DISCLOSURE_SOE_SCHEMA: G8DisclosureRowDef[] = []
