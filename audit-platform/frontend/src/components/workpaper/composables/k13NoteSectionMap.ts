/**
 * K13 营业外支出披露 ↔ 附注章节映射与 sync payload 构建
 * 权威来源：note_template_variant_matrix.json ying_ye_wai_zhi_chu
 * listed: null (关键词 '营业外支出') / soe: 八、77
 * account_code: 6711
 * 附注表结构：单表「营业外支出」(项目/本期发生额/上期发生额)
 */
import type { ColumnDef } from './disclosureColumnDefs'

export type K13DisclosureVariant = 'listed' | 'soe'

export const K13_NOTE_SECTION = {
  listed: '营业外支出',
  soe: '八、77',
} as const satisfies Record<K13DisclosureVariant, string>

export const K13_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息(上市公司)',
  soe: '附注披露信息(国企)',
} as const satisfies Record<K13DisclosureVariant, string>

const TABLE_NAME = '营业外支出'

const COLUMNS_LISTED: ColumnDef[] = [
  { key: 'label', label: '项目', is_label: true },
  { key: 'current_amount', label: '本期发生额', format: 'amount' },
  { key: 'prior_amount', label: '上期发生额', format: 'amount' },
]
const COLUMNS_SOE: ColumnDef[] = [
  { key: 'label', label: '项目', is_label: true },
  { key: 'current_amount', label: '本期发生额', format: 'amount' },
  { key: 'prior_amount', label: '上期发生额', format: 'amount' },
]

export interface K13DisclosureRow {
  project: string
  currentAmount: number
  priorAmount: number
}

export interface K13SyncPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  current_standard: string
  sub_table_data: Record<string, unknown>
  columns: Record<string, ColumnDef[]>
}

function resolveCurrentStandard(variant: K13DisclosureVariant): string {
  return variant === 'listed' ? 'listed_standalone' : 'soe_standalone'
}

export function buildK13SyncPayload(
  variant: K13DisclosureVariant,
  wpId: string,
  rows: K13DisclosureRow[],
  narrativeText: string,
): K13SyncPayload {
  const cols = variant === 'listed' ? COLUMNS_LISTED : COLUMNS_SOE
  const tableRows = [
    ...rows.map(r => ({
      label: r.project || '',
      current_amount: r.currentAmount || 0,
      prior_amount: r.priorAmount || 0,
    })),
    {
      label: '合计',
      current_amount: rows.reduce((s, r) => s + (r.currentAmount || 0), 0),
      prior_amount: rows.reduce((s, r) => s + (r.priorAmount || 0), 0),
      is_total: true,
    },
  ]

  const sub: Record<string, unknown> = {}
  const columns: Record<string, ColumnDef[]> = {}
  sub[TABLE_NAME] = tableRows
  columns[TABLE_NAME] = cols

  if (narrativeText.trim()) {
    sub._note_texts = [{ section: 'note-non-operating-expense', title: '营业外支出说明', text: narrativeText.trim() }]
  }

  return {
    wp_id: wpId,
    sheet_name: K13_DISCLOSURE_SHEET_NAME[variant],
    section_id: K13_NOTE_SECTION[variant],
    current_standard: resolveCurrentStandard(variant),
    sub_table_data: sub,
    columns,
  }
}
