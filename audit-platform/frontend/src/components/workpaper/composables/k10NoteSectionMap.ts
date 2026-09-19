/**
 * K10 其他收益 披露 ↔ 附注章节映射与 sync payload 构建
 *
 * 权威来源（实证 2026-07-30）：
 * - 源 xlsx `backend/wp_templates/K/K10 其他收益.xlsx` 的 `附注披露信息（上市公司）` /
 *   `附注披露信息（国企）`（**全角括号**）：两版都是「项目 / 本期发生额 / 上期发生额」，
 *   数据引 `'明细表K10-2'`。
 * - `note_template_listed.json` §五、68 / `note_template_soe.json` §八、69，
 *   表名两版同为「其他收益」。**国企侧是 4 列** —— 末列「是否为政府补助」，
 *   且行序为「明细行 … / 合计 / 其中：政府补助」（结构行排在合计之后）。
 *   旧常量两版都只声明 3 列 → 国企第 4 列列头丢失。
 *
 * account_code: 6117
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

export type K10DisclosureVariant = KPlVariant

export const K10_NOTE_SECTION = {
  listed: '五、68',
  soe: '八、69',
} as const satisfies Record<K10DisclosureVariant, string>

/** 源 xlsx 真实 tab 名 —— 全角括号（旧值为半角，属漂移） */
export const K10_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息（上市公司）',
  soe: '附注披露信息（国企）',
} as const satisfies Record<K10DisclosureVariant, string>

export const K10_LISTED_SUBTABLE = { main: '其他收益' } as const
export const K10_SOE_SUBTABLE = { main: '其他收益' } as const

/** 国企侧合计行之后的结构行（源模板行序），不参与合计求和 */
export const K10_SOE_STRUCTURAL_ROW = '其中：政府补助'

export const K10_LISTED_ROWS: readonly string[] = [
  '政府补助',
  '增值税进项加计抵减',
  '扣代缴个人所得税手续费返还',
]
export const K10_SOE_ROWS: readonly string[] = [
  '增值税即征即退',
  '代扣代缴个人所得税手续费返还',
]

const SPEC_LISTED: KPlColumnSpec = {
  labelHeader: '项目',
  currentLabel: '本期发生额',
  priorLabel: '上期发生额',
}

const SPEC_SOE: KPlColumnSpec = {
  labelHeader: '项目',
  currentLabel: '本期发生额',
  priorLabel: '上期发生额',
  extra: { key: 'is_gov_grant', label: '是否为政府补助', format: 'text' },
}

export function buildK10ListedColumns(): Record<string, ColumnDef[]> {
  return { [K10_LISTED_SUBTABLE.main]: plColumnsFor(SPEC_LISTED) }
}

export function buildK10SoeColumns(): Record<string, ColumnDef[]> {
  return { [K10_SOE_SUBTABLE.main]: plColumnsFor(SPEC_SOE) }
}

export interface K10DisclosureRow {
  project: string
  currentAmount: number
  priorAmount: number
  /** 国企第 4 列「是否为政府补助」（上市侧忽略） */
  isGovGrant?: string
}

export type K10SyncPayload = KPlSyncPayload

export function buildK10SyncPayload(
  variant: K10DisclosureVariant,
  wpId: string,
  rows: readonly K10DisclosureRow[],
  narrativeText: string,
  /** 国企「其中：政府补助」结构行金额（可省） */
  govGrantRow?: { currentAmount: number; priorAmount: number },
): K10SyncPayload {
  const spec = variant === 'listed' ? SPEC_LISTED : SPEC_SOE
  const tableName = variant === 'listed' ? K10_LISTED_SUBTABLE.main : K10_SOE_SUBTABLE.main
  const mapped: KPlRow[] = rows.map(r => ({
    project: r.project,
    currentAmount: r.currentAmount,
    priorAmount: r.priorAmount,
    ...(variant === 'soe' ? { extraValue: r.isGovGrant ?? '' } : {}),
  }))
  const afterTotalRows: KPlRow[] =
    variant === 'soe'
      ? [{
          project: K10_SOE_STRUCTURAL_ROW,
          currentAmount: govGrantRow?.currentAmount ?? 0,
          priorAmount: govGrantRow?.priorAmount ?? 0,
          extraValue: '是',
          isStructural: true,
        }]
      : []
  const texts: KPlNoteText[] = [
    { section: 'k10-note', title: '其他收益说明', text: narrativeText },
  ]
  return buildPlPayload({
    wpId,
    sheetName: K10_DISCLOSURE_SHEET_NAME[variant],
    sectionId: K10_NOTE_SECTION[variant],
    variant,
    tableName,
    spec,
    rows: mapped,
    afterTotalRows,
    texts,
  })
}
