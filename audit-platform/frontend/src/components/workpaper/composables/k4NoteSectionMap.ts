/**
 * K4 其他流动负债 披露 ↔ 附注章节映射与 sync payload 构建
 * 权威来源：note_template_variant_matrix.json qi_ta_liu_dong_fu_zhai
 * listed: 五、44 / soe: 八、48
 * account_code: 2245
 * 附注表结构：单表「其他流动负债」(项目/期末余额/上年年末余额|期初余额)
 */
import type { ColumnDef } from './disclosureColumnDefs'

export type K4DisclosureVariant = 'listed' | 'soe'

export const K4_NOTE_SECTION = {
  listed: '五、44',
  soe: '八、48',
} as const satisfies Record<K4DisclosureVariant, string>

export const K4_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息(上市公司)',
  soe: '附注披露信息(国企)',
} as const satisfies Record<K4DisclosureVariant, string>

const TABLE_NAME = '其他流动负债'

const COLUMNS_LISTED: ColumnDef[] = [
  { key: 'label', label: '项目', is_label: true },
  { key: 'end_amount', label: '期末余额', format: 'amount' },
  { key: 'prior_amount', label: '上年年末余额', format: 'amount' },
]
const COLUMNS_SOE: ColumnDef[] = [
  { key: 'label', label: '项目', is_label: true },
  { key: 'end_amount', label: '期末余额', format: 'amount' },
  { key: 'prior_amount', label: '期初余额', format: 'amount' },
]

export interface K4DisclosureRow {
  project: string
  endAmount: number
  priorAmount: number
}

export interface K4SyncPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  current_standard: string
  sub_table_data: Record<string, unknown>
  columns: Record<string, ColumnDef[]>
}

function resolveCurrentStandard(variant: K4DisclosureVariant): string {
  return variant === 'listed' ? 'listed_standalone' : 'soe_standalone'
}

export function buildK4SyncPayload(
  variant: K4DisclosureVariant,
  wpId: string,
  rows: K4DisclosureRow[],
  narrativeText: string,
): K4SyncPayload {
  const cols = variant === 'listed' ? COLUMNS_LISTED : COLUMNS_SOE
  const tableRows = [
    ...rows.map(r => ({
      label: r.project || '',
      end_amount: r.endAmount || 0,
      prior_amount: r.priorAmount || 0,
    })),
    {
      label: '合计',
      end_amount: rows.reduce((s, r) => s + (r.endAmount || 0), 0),
      prior_amount: rows.reduce((s, r) => s + (r.priorAmount || 0), 0),
      is_total: true,
    },
  ]

  const sub: Record<string, unknown> = {}
  const columns: Record<string, ColumnDef[]> = {}
  sub[TABLE_NAME] = tableRows
  columns[TABLE_NAME] = cols

  if (narrativeText.trim()) {
    sub._note_texts = [{ section: 'note-other-current-liability', title: '其他流动负债说明', text: narrativeText.trim() }]
  }

  return {
    wp_id: wpId,
    sheet_name: K4_DISCLOSURE_SHEET_NAME[variant],
    section_id: K4_NOTE_SECTION[variant],
    current_standard: resolveCurrentStandard(variant),
    sub_table_data: sub,
    columns,
  }
}
