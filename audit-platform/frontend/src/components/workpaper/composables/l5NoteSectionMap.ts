/**
 * l5NoteSectionMap — L5 长期应付款 披露表↔附注模块 联动映射
 *
 * 权威来源 note_template_variant_matrix.json · chang_qi_ying_fu_kuan：
 *   listed_standalone = 五、48
 *   soe_standalone    = 八、53
 */
import type { ColumnDef } from './disclosureColumnDefs'

export const L5_NOTE_SECTION = {
  listed: '五、48',
  soe: '八、53',
} as const

export const L5_DISCLOSURE_SHEET_LISTED = '附注披露信息核对（上市公司）'
export const L5_DISCLOSURE_SHEET_SOE = '附注披露信息核对（国企）'

export interface L5SyncPayloadOptions {
  variant: 'listed' | 'soe'
  categoryRows: Array<{ category: string; endBalance: number; beginBalance: number }>
  maturityRows?: Array<{ period: string; amount: number }>
  conclusion: string
}

export function buildL5SyncPayload(opts: L5SyncPayloadOptions) {
  const { variant, categoryRows, maturityRows, conclusion } = opts
  const sub_table_data: Record<string, any> = {}
  const columns: Record<string, ColumnDef[]> = {}

  // 分类表
  sub_table_data['长期应付款'] = categoryRows.map(r => ({
    label: r.category,
    values: [r.endBalance, r.beginBalance],
    ...(r.category === '合计' ? { is_total: true } : {}),
  }))
  columns['长期应付款'] = [
    { key: 'label', label: '项目', is_label: true },
    { key: 'endBalance', label: '期末余额' },
    { key: 'beginBalance', label: variant === 'listed' ? '上年年末余额' : '期初余额' },
  ]

  // 到期分析（上市版）
  if (variant === 'listed' && maturityRows && maturityRows.length > 0) {
    sub_table_data['未折现的到期分析'] = maturityRows.map(r => ({
      label: r.period, values: [r.amount],
    }))
    columns['未折现的到期分析'] = [
      { key: 'label', label: '到期期间', is_label: true },
      { key: 'amount', label: '金额' },
    ]
  }

  // 说明文本
  if (conclusion) {
    sub_table_data._note_texts = [{ section: 'conclusion', title: '审计结论', text: conclusion }]
  }

  return { sub_table_data, columns }
}
