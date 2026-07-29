/**
 * l7NoteSectionMap — L7 其他非流动负债 披露表↔附注模块 联动映射
 *
 * 权威来源 note_template_variant_matrix.json · qi_ta_fei_liu_dong_fu_zhai：
 *   listed_standalone = 五、52
 *   soe_standalone    = 八、57
 */
import type { ColumnDef } from './disclosureColumnDefs'

export const L7_NOTE_SECTION = {
  listed: '五、52',
  soe: '八、57',
} as const

export const L7_DISCLOSURE_SHEET_LISTED = '附注披露信息核对（上市公司）'
export const L7_DISCLOSURE_SHEET_SOE = '附注披露信息核对（国企）'

export interface L7SyncPayloadOptions {
  variant: 'listed' | 'soe'
  disclosureRows: Array<{ item: string; endAmount?: number; priorYearEnd?: number; beginBalance?: number; endBalance?: number }>
  conclusion: string
}

export function buildL7SyncPayload(opts: L7SyncPayloadOptions) {
  const { variant, disclosureRows, conclusion } = opts
  const sub_table_data: Record<string, any> = {}
  const columns: Record<string, ColumnDef[]> = {}

  // 主表
  sub_table_data['其他非流动负债'] = disclosureRows.map(r => ({
    label: r.item,
    values: variant === 'listed'
      ? [r.endAmount ?? r.endBalance ?? 0, r.priorYearEnd ?? r.beginBalance ?? 0]
      : [r.endBalance ?? r.endAmount ?? 0, r.beginBalance ?? r.priorYearEnd ?? 0],
    ...(r.item === '合计' ? { is_total: true } : {}),
  }))
  columns['其他非流动负债'] = [
    { key: 'label', label: '项目', is_label: true },
    { key: 'endAmount', label: variant === 'listed' ? '期末数' : '期末余额' },
    { key: 'priorAmount', label: variant === 'listed' ? '上年年末数' : '年初余额' },
  ]

  if (conclusion) {
    sub_table_data._note_texts = [{ section: 'conclusion', title: '审计结论', text: conclusion }]
  }

  return { sub_table_data, columns }
}
