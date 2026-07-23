/**
 * useK1RelatedParty — K1-11 其他应收款关联方及交易检查表
 *
 * Excel 13 列：关联方|关系|期初|借方|贷方|期末(自动)|坏账|账面价值(自动)|
 * 发生时间及账龄|款项性质|期后收款|索引|备注
 * 期末 = 期初 + 借方 − 贷方（资产类）
 */
import {
  calcAssetEndBalance,
  calcNetValue,
  calcSubtotal,
  calcTriangleReconciliation,
} from './useK1FormulaEngine'
import type { AuditRow } from './useK1AuditRows'
import type { K1DetailRow } from './useK1Detail'
import {
  computeMissingRelatedParties,
  relatedPartyNameMatches,
} from './useF1RelatedParty'

export const K1_RELATED_PARTY_RELATIONSHIP_OPTIONS = [
  '实际控制人',
  '控股股东',
  '控股股东、实际控制人的附属企业',
  '持有5%以上股份的法人或其他组织',
  '联营企业',
  '合营企业',
  '董高监等关键管理人员',
  '其他关联方',
] as const

/** K1-2 明细表「关联关系」下拉：否 + 8 类（兼容历史值「是」） */
export const K1_DETAIL_RELATED_PARTY_OPTIONS = [
  '否',
  ...K1_RELATED_PARTY_RELATIONSHIP_OPTIONS,
  '是', // 历史数据兼容
] as const

export type K1RelatedPartyRow = AuditRow & {
  name: string
  relation: string
  beginBalance: number
  debit: number
  credit: number
  endBalance: number
  provision: number
  aging: string
  nature: string
  postCollection: number
  indexNo: string
  remark: string
  /** 是否公允 */
  isFair: string
  /** 是否披露 */
  isDisclosed: string
  /** 资金占用 */
  capitalOccupation: string
}

export function isK1RelatedPartyMarked(relatedParty: string | null | undefined): boolean {
  const rp = String(relatedParty ?? '').trim()
  return !!rp && rp !== '否'
}

/** B19 清单名称匹配 → 建议关联关系（默认其他关联方） */
export function matchK1RelatedPartyFromRegistry(
  counterparty: string,
  registry: string[],
): string {
  if (!counterparty?.trim() || !registry.length) return '否'
  const matched = registry.some(p => relatedPartyNameMatches(counterparty, p))
  return matched ? '其他关联方' : '否'
}

export function normalizeK1RelatedPartyRow(raw: Partial<K1RelatedPartyRow>): K1RelatedPartyRow {
  return recalcK1RelatedPartyRow({
    id: raw.id ?? `k1rp-${Date.now()}`,
    name: raw.name ?? '',
    relation: raw.relation ?? '',
    beginBalance: parseNum(raw.beginBalance),
    debit: parseNum(raw.debit),
    credit: parseNum(raw.credit),
    endBalance: parseNum(raw.endBalance),
    provision: parseNum(raw.provision),
    aging: raw.aging ?? '',
    nature: raw.nature ?? '',
    postCollection: parseNum(raw.postCollection),
    indexNo: raw.indexNo ?? '',
    remark: raw.remark ?? '',
    isFair: raw.isFair ?? '待评估',
    isDisclosed: raw.isDisclosed ?? '待评估',
    capitalOccupation: raw.capitalOccupation ?? '待评估',
  })
}

export function computeK1MissingRelatedParties(
  registry: string[],
  rows: Array<{ name: string }>,
): string[] {
  return computeMissingRelatedParties(registry, rows.map(r => ({ partyName: r.name })))
}

export function addMissingK1RelatedPartyRows(
  existing: K1RelatedPartyRow[],
  missingNames: string[],
): K1RelatedPartyRow[] {
  const names = new Set(existing.map(r => String(r.name || '').trim()))
  const added: K1RelatedPartyRow[] = []
  for (const name of missingNames) {
    const key = String(name || '').trim()
    if (!key || names.has(key)) continue
    names.add(key)
    added.push(normalizeK1RelatedPartyRow({ id: `k1rp-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`, name: key }))
  }
  return [...existing.map(r => normalizeK1RelatedPartyRow(r)), ...added]
}

function parseNum(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

/** 从 K1-2 账龄段拼「发生时间及账龄」描述 */
export function buildAgingDescription(row: Partial<K1DetailRow>): string {
  const audited = row.agingAudited
  if (!audited || typeof audited !== 'object') return ''
  const parts: string[] = []
  const labels: Record<string, string> = {
    within1: '1年以内',
    y1to2: '1-2年',
    y2to3: '2-3年',
    y3to4: '3-4年',
    y4to5: '4-5年',
    over5: '5年以上',
  }
  for (const [key, label] of Object.entries(labels)) {
    const amt = parseNum(audited[key])
    if (amt > 0) parts.push(`${label}:${amt}`)
  }
  return parts.join('；')
}

/** 根据期初/期末反推借贷发生额，使三角勾稽平衡 */
export function inferMovementFromBalances(begin: number, end: number): { debit: number; credit: number } {
  const diff = end - begin
  if (diff > 0) return { debit: diff, credit: 0 }
  if (diff < 0) return { debit: 0, credit: -diff }
  return { debit: 0, credit: 0 }
}

export function recalcK1RelatedPartyRow(row: K1RelatedPartyRow): K1RelatedPartyRow {
  const beginBalance = parseNum(row.beginBalance)
  const debit = parseNum(row.debit)
  const credit = parseNum(row.credit)
  const provision = parseNum(row.provision)
  const endBalance = calcAssetEndBalance(beginBalance, debit, credit)
  return {
    ...row,
    beginBalance,
    debit,
    credit,
    provision,
    endBalance,
    postCollection: parseNum(row.postCollection),
  }
}

export function bookValueOf(row: K1RelatedPartyRow): number {
  return calcNetValue(parseNum(row.endBalance), parseNum(row.provision))
}

export function rowBalanceGap(row: K1RelatedPartyRow): number {
  return calcTriangleReconciliation(
    parseNum(row.beginBalance),
    parseNum(row.debit),
    parseNum(row.credit),
    parseNum(row.endBalance),
  )
}

export function computeK1RelatedPartySubtotal(rows: K1RelatedPartyRow[]) {
  const recalc = rows.map(recalcK1RelatedPartyRow)
  return {
    beginBalance: calcSubtotal(recalc.map(r => r.beginBalance)),
    debit: calcSubtotal(recalc.map(r => r.debit)),
    credit: calcSubtotal(recalc.map(r => r.credit)),
    endBalance: calcSubtotal(recalc.map(r => r.endBalance)),
    provision: calcSubtotal(recalc.map(r => r.provision)),
    bookValue: calcSubtotal(recalc.map(bookValueOf)),
    postCollection: calcSubtotal(recalc.map(r => r.postCollection)),
  }
}

/** K1-2 中关联方行（关联关系 ≠ 否） */
export function extractRelatedPartyDetailRows(allResponses: Map<string, any>): K1DetailRow[] {
  try {
    const raw = allResponses.get('K1-2-detail-rows')?.remark
    if (!raw) return []
    const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw
    if (!Array.isArray(parsed)) return []
    return parsed.filter((r: any) =>
      isK1RelatedPartyMarked(r?.relatedParty) && String(r?.counterparty ?? '').trim(),
    )
  } catch {
    return []
  }
}

/** 从 K1-2 导入/合并关联方行（同名更新，保留已填说明） */
export function mergeRelatedPartyFromK1Detail(
  existing: K1RelatedPartyRow[],
  detailRows: Array<Partial<K1DetailRow>>,
): K1RelatedPartyRow[] {
  const map = new Map<string, K1RelatedPartyRow>()
  for (const row of existing) {
    const key = String(row.name || '').trim()
    if (key) map.set(key, recalcK1RelatedPartyRow(row as K1RelatedPartyRow))
  }

  for (const src of detailRows) {
    const name = String(src.counterparty || '').trim()
    if (!name) continue
    const begin = parseNum(src.beginBalance)
    const end = parseNum(src.endBalance)
    const movement = inferMovementFromBalances(begin, end)
    const prev = map.get(name)

    const rpType = String(src.relatedParty || '')
    const importedRelation = rpType === '是' ? '' : rpType

    const merged: K1RelatedPartyRow = normalizeK1RelatedPartyRow({
      ...prev,
      id: prev?.id ?? `k1rp-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      name,
      relation: prev?.relation || importedRelation,
      beginBalance: begin,
      debit: movement.debit,
      credit: movement.credit,
      endBalance: end,
      provision: parseNum(src.badDebtProvision ?? prev?.provision),
      aging: buildAgingDescription(src) || prev?.aging || '',
      nature: String(src.nature || prev?.nature || ''),
      postCollection: prev?.postCollection ?? 0,
      indexNo: prev?.indexNo ?? '',
      remark: prev?.remark ?? String(src.remark || ''),
    })
    map.set(name, merged)
  }

  return Array.from(map.values())
}

/** K1-2 关联方期末合计（用于勾稽提示） */
export function k1DetailRelatedPartyEndTotal(allResponses: Map<string, any>): number {
  return extractRelatedPartyDetailRows(allResponses).reduce(
    (s, r) => s + parseNum(r.endBalance),
    0,
  )
}

/** K1-2 批量将 B19 清单匹配到的往来对象标记为关联方 */
export function batchMatchK1DetailRelatedParty(
  rows: Array<{ counterparty: string; relatedParty: string }>,
  registry: string[],
): number {
  if (!registry.length) return 0
  let count = 0
  for (const row of rows) {
    if (isK1RelatedPartyMarked(row.relatedParty)) continue
    const suggested = matchK1RelatedPartyFromRegistry(row.counterparty, registry)
    if (suggested !== '否') {
      row.relatedParty = suggested
      count++
    }
  }
  return count
}
