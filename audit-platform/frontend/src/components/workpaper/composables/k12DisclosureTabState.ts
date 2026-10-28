/**
 * K12 营业外收入披露 Tab 的表格行 + 附注说明（底稿披露 Tab 与附注页离屏同步共用，spec note-pull-followup-closure R1 / ADR-1）。
 *
 * 由 `K12TabDisclosureListed` / `K12TabDisclosureSoe` 原样抽出（两版分类相同、只差条目键）：挂载时按分类逐行读回
 * `K12-disc-{variant}-row-{i}` 与附注说明，再从 K12-1 审定表按名称取数；「同步到附注」把行映射成 builder 行（含第 4 列）。
 * Tab 与离屏 provider 调同一份计算 ⇒ 两条路径发出逐字节相同的载荷。取数后的逐行保存、提示、事件、国企「与企业日常活动
 * 无关的政府补助明细」子表（附注没有对应表，不推）留在 Tab。
 */
import type { K12DisclosureRow, K12DisclosureVariant } from './k12NoteSectionMap'

/**
 * 营业外收入标准来源分类（P1 对齐源模板 K12-1 canonical 行，与审定表按 name 匹配）。两版相同：
 * P0-6 已删国企版臆造的「国有资产处置收益」（源模板国企版分类与上市版相同，违「禁止自造披露内容」铁律）。
 */
export const K12_DISCLOSURE_CATEGORIES: readonly string[] = [
  '与日常活动无关的政府补助',
  '捐赠利得',
  '盘盈利得（不包括存货盘盈及固定资产盘盈）',
  '碳排放配额出售利得',
  '其他',
]

export interface K12DisclosureTabRow {
  category: string
  currentAmount: number
  priorAmount: number
  /** 计入当期非经常性损益的金额（源模板必填列） */
  nonRecurringAmount: number
  remark: string
}

/**
 * 逐行读回的条目。Tab 逐行保存写同形字面量 `K12-disc-{listed|soe}-row-${idx}`（原样留在 Tab）；两版各写一个字面量模板，
 * 不合成 `${variant}` —— K 循环键守卫（KF-P16 宽口径）按字面量模板计数。
 */
const K12_ROW_ITEM_ID: Record<K12DisclosureVariant, (i: number) => string> = {
  listed: (i) => `K12-disc-listed-row-${i}`,
  soe: (i) => `K12-disc-soe-row-${i}`,
}

export const K12_DISCLOSURE_NARRATIVE_ITEM = {
  listed: 'K12-disclosure-listed-narrative',
  soe: 'K12-disclosure-soe-narrative',
} as const satisfies Record<K12DisclosureVariant, string>

type Responses = ReadonlyMap<string, any>

export function k12DefaultDisclosureRows(): K12DisclosureTabRow[] {
  return K12_DISCLOSURE_CATEGORIES.map((c) => ({
    category: c, currentAmount: 0, priorAmount: 0, nonRecurringAmount: 0, remark: '',
  }))
}

/** 挂载时读回：按分类逐行读回（解析不了 / 空的行保持默认 0）；附注说明没有该条目时为 null（Tab 保持原值） */
export function loadK12DisclosureState(
  responses: Responses,
  variant: K12DisclosureVariant,
): { rows: K12DisclosureTabRow[]; narrative: string | null } {
  const rows = k12DefaultDisclosureRows()
  for (let i = 0; i < K12_DISCLOSURE_CATEGORIES.length; i++) {
    const saved = responses.get(K12_ROW_ITEM_ID[variant](i))
    if (saved) {
      try {
        const parsed = typeof saved.remark === 'string' ? JSON.parse(saved.remark) : saved.remark
        if (parsed) {
          rows[i] = {
            category: K12_DISCLOSURE_CATEGORIES[i],
            currentAmount: Number(parsed.currentAmount || 0),
            priorAmount: Number(parsed.priorAmount || 0),
            nonRecurringAmount: Number(parsed.nonRecurringAmount || 0),
            remark: parsed.remark || '',
          }
        }
      } catch { /* ignore parse errors */ }
    }
  }
  const narrativeSaved = responses.get(K12_DISCLOSURE_NARRATIVE_ITEM[variant])
  return { rows, narrative: narrativeSaved ? (narrativeSaved.remark || narrativeSaved.conclusion || '') : null }
}

/** `missing` = 没有 K12-1 审定表条目（Tab 非静默时提示）；`invalid` = 有但解析不出数组（静默返回） */
export type K12AutoFillResult = 'missing' | 'invalid' | { matched: number; totalAudited: number }

/**
 * 从 K12-1 审定表取数（P0 修复：原读 `K12-1-row-${i}-audited` 死键，useK12Adjudication 从不写 → 恒 no-op；
 * 改读 `K12-1-rows` 按 name 匹配）。命中的行改本期 / 上期发生额后调 `onFilled(row)`（Tab 传逐行保存 + 排程自动同步；
 * 离屏不传 ⇒ 只改内存）。
 */
export function applyK12AutoFill(
  rows: K12DisclosureTabRow[],
  responses: Responses,
  onFilled?: (row: K12DisclosureTabRow) => void,
): K12AutoFillResult {
  const saved = responses.get('K12-1-rows')
  if (!saved) return 'missing'
  let k12Rows: any[] = []
  try {
    const raw = saved.remark ?? saved.conclusion ?? saved
    k12Rows = typeof raw === 'string' ? JSON.parse(raw) : raw
  } catch { return 'invalid' }
  if (!Array.isArray(k12Rows)) return 'invalid'

  const byName = new Map<string, { audited: number; prior: number }>()
  for (const r of k12Rows) {
    const audited = Number(
      r.audited ?? (Number(r.unadjusted || 0) + Number(r.aje || 0) + Number(r.rje || 0)),
    )
    const prior = Number(
      r.priorAudited ?? (Number(r.priorUnadj || 0) + Number(r.priorAje || 0) + Number(r.priorRje || 0)),
    )
    byName.set(String(r.name || '').trim(), { audited, prior })
  }

  let matched = 0
  for (const row of rows) {
    const hit = byName.get(row.category.trim())
    if (hit) {
      row.currentAmount = hit.audited
      row.priorAmount = hit.prior
      onFilled?.(row)
      matched++
    }
  }
  return { matched, totalAudited: k12Rows.reduce((s, r) => s + Number(r.audited ?? 0), 0) }
}

/** 「同步到附注」的 builder 行（第 4 列「计入当期非经常性损益的金额」是源模板必填列，旧载荷从未推送） */
export function k12DisclosureSyncRows(rows: readonly K12DisclosureTabRow[]): K12DisclosureRow[] {
  return rows.map((r) => ({
    project: r.category,
    currentAmount: r.currentAmount,
    priorAmount: r.priorAmount,
    nonRecurringAmount: r.nonRecurringAmount,
  }))
}
