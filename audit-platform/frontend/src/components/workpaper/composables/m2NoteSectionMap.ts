/**
 * m2NoteSectionMap — M2 实收资本（股本）披露→附注映射
 *
 * 章节：五、53 股本（仅上市）/ 八、58 实收资本（仅国企）
 * 源 xlsx：`backend/wp_templates/M/M2 实收资本（股本）.xlsx`
 *   上市 = 两级 8 列表头（项目 | 期初余额 | 本期增减(发行新股/送股/公积金转股/其他/小计) | 期末余额）
 *   国企 = 两级 7 列表头（投资者名称 | 年初余额(投资金额/所占比例) | 本期增加 | 本期减少 | 期末余额(投资金额/所占比例)）
 *
 * 🔴 两版结构完全不对称：
 *   - 上市单位「万股」，按股份性质分行（限售/非限售/合计）
 *   - 国企单位「元」，按投资者分行（动态插行）
 *
 * 表名权威 = `note_template_{listed,soe}.json` 对应章节 tables[0].name
 *   listed: '股本（单位：万股）'
 *   soe: '实收资本'
 */

import { defineColumns, type ColumnDef } from './disclosureColumnDefs'

export type M2Variant = 'listed' | 'soe'

// ─── 章节号 ─────────────────────────────────────────────────────────────────

export const M2_NOTE_SECTION = {
  listed: '五、53',
  soe: '八、58',
} as const

export const M2_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息（上市公司）',
  soe: '附注披露信息（国有企业）',
} as const

export const M2_SUBTABLE = {
  listed: '股本（单位：万股）',
  soe: '实收资本',
} as const

// ─── 列定义 ─────────────────────────────────────────────────────────────────

/**
 * 上市版（五、53）两级 8 列：
 * 项目(rowspan2) | 期初余额(rowspan2) | 本期增减(+、-): 发行新股/送股/公积金转股/其他/小计 | 期末余额(rowspan2)
 */
export function buildM2ListedColumns(): Record<string, ColumnDef[]> {
  return {
    [M2_SUBTABLE.listed]: defineColumns([
      { key: 'label', label: '项目', is_label: true },
      { key: 'begin_amount', label: '期初余额', format: 'amount', align: 'right' },
      { key: 'issue_new', label: '发行新股', format: 'amount', align: 'right', group: '本期增减（+、-）' },
      { key: 'bonus_shares', label: '送股', format: 'amount', align: 'right', group: '本期增减（+、-）' },
      { key: 'reserve_to_shares', label: '公积金转股', format: 'amount', align: 'right', group: '本期增减（+、-）' },
      { key: 'other_change', label: '其他', format: 'amount', align: 'right', group: '本期增减（+、-）' },
      { key: 'subtotal_change', label: '小计', format: 'amount', align: 'right', group: '本期增减（+、-）' },
      { key: 'end_amount', label: '期末余额', format: 'amount', align: 'right' },
    ]),
  }
}

/**
 * 国企版（八、58）两级 7 列：
 * 投资者名称(rowspan2) | 年初余额: 投资金额/所占比例(%) | 本期增加(rowspan2) | 本期减少(rowspan2) | 期末余额: 投资金额/所占比例(%)
 */
export function buildM2SoeColumns(): Record<string, ColumnDef[]> {
  return {
    [M2_SUBTABLE.soe]: defineColumns([
      { key: 'label', label: '投资者名称', is_label: true },
      { key: 'begin_amount', label: '投资金额', format: 'amount', align: 'right', group: '年初余额' },
      { key: 'begin_ratio', label: '所占比例（%）', format: 'text', align: 'center', group: '年初余额' },
      { key: 'increase', label: '本期增加', format: 'amount', align: 'right' },
      { key: 'decrease', label: '本期减少', format: 'amount', align: 'right' },
      { key: 'end_amount', label: '投资金额', format: 'amount', align: 'right', group: '期末余额' },
      { key: 'end_ratio', label: '所占比例（%）', format: 'text', align: 'center', group: '期末余额' },
    ]),
  }
}

// ─── 行模型 ─────────────────────────────────────────────────────────────────

/** 上市版行（万股维度） */
export interface M2ListedRow {
  label: string
  beginShares: number
  issueNew: number
  bonusShares: number
  reserveToShares: number
  otherChange: number
}

/** 国企版行（元维度，含比例） */
export interface M2SoeRow {
  label: string
  beginAmount: number
  beginRatio: string
  increase: number
  decrease: number
}

function num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

/** 上市：小计 = 发行新股+送股+公积金转股+其他；期末 = 期初+小计 */
export function m2ListedSubtotal(r: M2ListedRow): number {
  return num(r.issueNew) + num(r.bonusShares) + num(r.reserveToShares) + num(r.otherChange)
}
export function m2ListedEnd(r: M2ListedRow): number {
  return num(r.beginShares) + m2ListedSubtotal(r)
}

/** 国企：期末 = 年初+增加−减少 */
export function m2SoeEnd(r: M2SoeRow): number {
  return num(r.beginAmount) + num(r.increase) - num(r.decrease)
}

// ─── 载荷构建 ───────────────────────────────────────────────────────────────

export interface M2SyncPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  current_standard: string
  sub_table_data: Record<string, Record<string, unknown>[]>
  columns: Record<string, ColumnDef[]>
}

/** 上市版载荷 */
export function buildM2ListedSyncPayload(
  wpId: string,
  rows: readonly M2ListedRow[],
  noteTexts?: { restricted?: string; changeReason?: string; eps?: string },
): M2SyncPayload | null {
  if (!wpId) return null

  const dataRows: Record<string, unknown>[] = rows
    .filter((r) => (r.label ?? '').trim())
    .map((r) => ({
      label: r.label.trim(),
      begin_amount: num(r.beginShares),
      issue_new: num(r.issueNew),
      bonus_shares: num(r.bonusShares),
      reserve_to_shares: num(r.reserveToShares),
      other_change: num(r.otherChange),
      subtotal_change: m2ListedSubtotal(r),
      end_amount: m2ListedEnd(r),
    }))

  // 合计行
  const total: Record<string, unknown> = {
    label: '股份总数',
    begin_amount: dataRows.reduce((s, r) => s + num(r.begin_amount), 0),
    issue_new: dataRows.reduce((s, r) => s + num(r.issue_new), 0),
    bonus_shares: dataRows.reduce((s, r) => s + num(r.bonus_shares), 0),
    reserve_to_shares: dataRows.reduce((s, r) => s + num(r.reserve_to_shares), 0),
    other_change: dataRows.reduce((s, r) => s + num(r.other_change), 0),
    subtotal_change: dataRows.reduce((s, r) => s + num(r.subtotal_change), 0),
    end_amount: dataRows.reduce((s, r) => s + num(r.end_amount), 0),
    is_total: true,
  }
  dataRows.push(total)

  const sub: Record<string, unknown> = {
    [M2_SUBTABLE.listed]: dataRows,
  }

  // _note_texts
  const texts: Array<{ section: string; title: string; text: string }> = []
  if (noteTexts?.restricted?.trim()) {
    texts.push({ section: 'm2-listed-restricted', title: '限售股份说明', text: noteTexts.restricted.trim() })
  }
  if (noteTexts?.changeReason?.trim()) {
    texts.push({ section: 'm2-listed-change-reason', title: '股本变动原因说明', text: noteTexts.changeReason.trim() })
  }
  if (noteTexts?.eps?.trim()) {
    texts.push({ section: 'm2-listed-eps', title: '与每股收益计算相关说明', text: noteTexts.eps.trim() })
  }
  if (texts.length > 0) {
    ;(sub as any)._note_texts = texts
  }

  return {
    wp_id: wpId,
    sheet_name: M2_DISCLOSURE_SHEET_NAME.listed,
    section_id: M2_NOTE_SECTION.listed,
    current_standard: 'listed_standalone',
    sub_table_data: sub as Record<string, Record<string, unknown>[]>,
    columns: buildM2ListedColumns(),
  }
}

/** 国企版载荷 */
export function buildM2SoeSyncPayload(
  wpId: string,
  rows: readonly M2SoeRow[],
  noteTexts?: { stateCapital?: string; method?: string; registration?: string },
): M2SyncPayload | null {
  if (!wpId) return null

  const dataRows: Record<string, unknown>[] = rows
    .filter((r) => (r.label ?? '').trim())
    .map((r) => ({
      label: r.label.trim(),
      begin_amount: num(r.beginAmount),
      begin_ratio: r.beginRatio || '',
      increase: num(r.increase),
      decrease: num(r.decrease),
      end_amount: m2SoeEnd(r),
      end_ratio: '', // 期末比例由投影器推导或手工填
    }))

  // 合计行
  const totalBegin = dataRows.reduce((s, r) => s + num(r.begin_amount), 0)
  const totalIncrease = dataRows.reduce((s, r) => s + num(r.increase), 0)
  const totalDecrease = dataRows.reduce((s, r) => s + num(r.decrease), 0)
  const total: Record<string, unknown> = {
    label: '合计',
    begin_amount: totalBegin,
    begin_ratio: '100.00',
    increase: totalIncrease,
    decrease: totalDecrease,
    end_amount: totalBegin + totalIncrease - totalDecrease,
    end_ratio: '100.00',
    is_total: true,
  }
  dataRows.push(total)

  // 按合计金额重算各行期末比例
  const totalEnd = num(total.end_amount)
  if (totalEnd > 0) {
    for (const r of dataRows) {
      if (!r.is_total) {
        r.end_ratio = ((num(r.end_amount) / totalEnd) * 100).toFixed(2)
      }
    }
  }

  const sub: Record<string, unknown> = {
    [M2_SUBTABLE.soe]: dataRows,
  }

  // _note_texts
  const texts: Array<{ section: string; title: string; text: string }> = []
  if (noteTexts?.stateCapital?.trim()) {
    texts.push({ section: 'm2-soe-state-capital', title: '国有资本出资情况说明', text: noteTexts.stateCapital.trim() })
  }
  if (noteTexts?.method?.trim()) {
    texts.push({ section: 'm2-soe-method', title: '出资方式说明', text: noteTexts.method.trim() })
  }
  if (noteTexts?.registration?.trim()) {
    texts.push({ section: 'm2-soe-registration', title: '验资及工商登记情况', text: noteTexts.registration.trim() })
  }
  if (texts.length > 0) {
    ;(sub as any)._note_texts = texts
  }

  return {
    wp_id: wpId,
    sheet_name: M2_DISCLOSURE_SHEET_NAME.soe,
    section_id: M2_NOTE_SECTION.soe,
    current_standard: 'soe_standalone',
    sub_table_data: sub as Record<string, Record<string, unknown>[]>,
    columns: buildM2SoeColumns(),
  }
}
