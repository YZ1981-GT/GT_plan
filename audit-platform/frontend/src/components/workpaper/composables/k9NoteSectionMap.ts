/**
 * K9 管理费用 披露 ↔ 附注章节映射与 sync payload 构建
 *
 * 权威来源（实证 2026-07-30）：
 * - 源 xlsx `backend/wp_templates/K/K9 管理费用.xlsx` 的 `附注披露信息（上市公司）` /
 *   `附注披露信息（国企）`（**全角括号**）：两版都是「项目 / 本期发生额 / 上期发生额」
 *   三列，数据引 `'审定表K9-1'`；另各有一块「管理费用（合并报表）」——合并口径归合并
 *   附注模板，本表为个别报表口径。
 * - `note_template_listed.json` §五、65 表名「管理费用（按费用性质列示）」
 *   / `note_template_soe.json` §八、66 表名「管理费用」（**两版表名不同**，
 *   旧常量两版都写「管理费用」→ 上市侧孤儿子表）。
 *
 * account_code: 6602
 *
 * spec: .kiro/specs/k-cycle-disclosure-alignment/ Task 2
 */
import type { ColumnDef } from './disclosureColumnDefs'
import {
  plColumnsFor,
  buildPlPayload,
  type KPlColumnSpec,
  type KPlNoteText,
  type KPlRow,
  type KPlSyncPayload,
  type KPlVariant,
} from './kPlDisclosureShared'

export type K9DisclosureVariant = KPlVariant

export const K9_NOTE_SECTION = {
  listed: '五、65',
  soe: '八、66',
} as const satisfies Record<K9DisclosureVariant, string>

/** 源 xlsx 真实 tab 名 —— 全角括号（旧值为半角，属漂移） */
export const K9_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息（上市公司）',
  soe: '附注披露信息（国企）',
} as const satisfies Record<K9DisclosureVariant, string>

export const K9_LISTED_SUBTABLE = { main: '管理费用（按费用性质列示）' } as const
export const K9_SOE_SUBTABLE = { main: '管理费用' } as const

/** 旧常量两版都写「管理费用」→ 上市侧曾产生孤儿子表，须清理 */
export const K9_LEGACY_OBSOLETE_TABLES: readonly string[] = ['管理费用']

/** 模板固定行（两版一致；其余明细按费用性质随项目实际列示） */
export const K9_LISTED_ROWS: readonly string[] = ['残疾人就业保障金']
export const K9_SOE_ROWS: readonly string[] = ['残疾人就业保障金']

const SPEC: KPlColumnSpec = {
  labelHeader: '项目',
  currentLabel: '本期发生额',
  priorLabel: '上期发生额',
}

export function buildK9ListedColumns(): Record<string, ColumnDef[]> {
  return { [K9_LISTED_SUBTABLE.main]: plColumnsFor(SPEC) }
}

export function buildK9SoeColumns(): Record<string, ColumnDef[]> {
  return { [K9_SOE_SUBTABLE.main]: plColumnsFor(SPEC) }
}

export interface K9DisclosureRow {
  project: string
  currentAmount: number
  priorAmount: number
}

export type K9SyncPayload = KPlSyncPayload

export function buildK9SyncPayload(
  variant: K9DisclosureVariant,
  wpId: string,
  rows: readonly K9DisclosureRow[],
  narrativeText: string,
): K9SyncPayload {
  const tableName = variant === 'listed' ? K9_LISTED_SUBTABLE.main : K9_SOE_SUBTABLE.main
  const texts: KPlNoteText[] = [
    { section: 'k9-note', title: '管理费用说明', text: narrativeText },
  ]
  return buildPlPayload({
    wpId,
    sheetName: K9_DISCLOSURE_SHEET_NAME[variant],
    sectionId: K9_NOTE_SECTION[variant],
    variant,
    tableName,
    spec: SPEC,
    rows: rows as readonly KPlRow[],
    texts,
    removedTableKeys: variant === 'listed' ? K9_LEGACY_OBSOLETE_TABLES : [],
  })
}
