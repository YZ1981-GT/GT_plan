/**
 * K8 销售费用 披露 ↔ 附注章节映射与 sync payload 构建
 *
 * 权威来源（实证 2026-07-30）：
 * - 源 xlsx `backend/wp_templates/K/K8 销售费用.xlsx` 的 `附注披露信息（上市公司）` /
 *   `附注披露信息（国企）`（**全角括号**）：两版都是「项目 / 本期发生额 / 上期发生额」
 *   三列，数据引 `'审定表K8-1'`；另各有一块「销售费用(合并报表)」——合并口径归合并附注
 *   模板，本表为个别报表口径，不推第二张表（该附注章节只有 1 张表，推两张会造孤儿表）。
 * - `note_template_listed.json` §五、64 表名「销售费用（按费用性质列示）」
 *   / `note_template_soe.json` §八、65 表名「销售费用」（**两版表名不同**，
 *   旧常量两版都写「销售费用」→ 上市侧孤儿子表）。
 *
 * account_code: 6601
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

export type K8DisclosureVariant = KPlVariant

export const K8_NOTE_SECTION = {
  listed: '五、64',
  soe: '八、65',
} as const satisfies Record<K8DisclosureVariant, string>

/** 源 xlsx 真实 tab 名 —— 全角括号，勿"修正"为半角（旧值为半角，属漂移） */
export const K8_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息（上市公司）',
  soe: '附注披露信息（国企）',
} as const satisfies Record<K8DisclosureVariant, string>

export const K8_LISTED_SUBTABLE = { main: '销售费用（按费用性质列示）' } as const
export const K8_SOE_SUBTABLE = { main: '销售费用' } as const

/** 旧常量两版都写「销售费用」→ 上市侧曾产生孤儿子表，须清理 */
export const K8_LEGACY_OBSOLETE_TABLES: readonly string[] = ['销售费用']

/**
 * 模板固定行：两版都只有合计骨架（明细按费用性质随项目实际列示，源模板从
 * 审定表 K8-1 逐行引入）。
 */
export const K8_LISTED_ROWS: readonly string[] = []
export const K8_SOE_ROWS: readonly string[] = []

const SPEC: KPlColumnSpec = {
  labelHeader: '项目',
  currentLabel: '本期发生额',
  priorLabel: '上期发生额',
}

export function buildK8ListedColumns(): Record<string, ColumnDef[]> {
  return { [K8_LISTED_SUBTABLE.main]: plColumnsFor(SPEC) }
}

export function buildK8SoeColumns(): Record<string, ColumnDef[]> {
  return { [K8_SOE_SUBTABLE.main]: plColumnsFor(SPEC) }
}

export interface K8DisclosureRow {
  project: string
  currentAmount: number
  priorAmount: number
}

export type K8SyncPayload = KPlSyncPayload

export function buildK8SyncPayload(
  variant: K8DisclosureVariant,
  wpId: string,
  rows: readonly K8DisclosureRow[],
  narrativeText: string,
): K8SyncPayload {
  const tableName = variant === 'listed' ? K8_LISTED_SUBTABLE.main : K8_SOE_SUBTABLE.main
  const texts: KPlNoteText[] = [
    { section: 'k8-note', title: '销售费用说明', text: narrativeText },
  ]
  return buildPlPayload({
    wpId,
    sheetName: K8_DISCLOSURE_SHEET_NAME[variant],
    sectionId: K8_NOTE_SECTION[variant],
    variant,
    tableName,
    spec: SPEC,
    rows: rows as readonly KPlRow[],
    texts,
    removedTableKeys: variant === 'listed' ? K8_LEGACY_OBSOLETE_TABLES : [],
  })
}
