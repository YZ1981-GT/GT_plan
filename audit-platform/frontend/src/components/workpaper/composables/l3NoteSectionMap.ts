/**
 * l3NoteSectionMap — L3 长期借款 披露表↔附注模块 联动映射
 *
 * 权威来源 note_template_variant_matrix.json · chang_qi_jie_kuan：
 *   listed_standalone = 五、45
 *   soe_standalone    = 八、49
 *
 * 附注模板结构：
 *   表1: 长期借款分类（项目/期末余额/利率区间/上年年末余额/利率区间）
 *     固定行: 质押/抵押/保证/信用借款 + 小计 − 减一年内到期 = 合计
 *   表2: 一年内到期的长期借款
 *   说明: 财产抵押质押情况 + 审计结论
 */
import type { ColumnDef } from './disclosureColumnDefs'

export const L3_NOTE_SECTION = {
  listed: '五、45',
  soe: '八、49',
} as const

export const L3_DISCLOSURE_SHEET_LISTED = '附注披露信息核对（上市公司）'
export const L3_DISCLOSURE_SHEET_SOE = '附注披露信息核对（国企）'

function buildClassificationColumns(variant: 'listed' | 'soe'): ColumnDef[] {
  return [
    { key: 'label', label: '项目', is_label: true },
    { key: 'endAmount', label: '期末余额' },
    { key: 'endRate', label: '利率区间' },
    { key: 'priorAmount', label: variant === 'listed' ? '上年年末余额' : '期初余额' },
    { key: 'priorRate', label: '利率区间' },
  ]
}

function buildCurrentPortionColumns(variant: 'listed' | 'soe'): ColumnDef[] {
  return [
    { key: 'label', label: '项目', is_label: true },
    { key: 'endAmount', label: '期末余额' },
    { key: 'priorAmount', label: variant === 'listed' ? '上年年末余额' : '期初余额' },
  ]
}

export interface L3SyncPayloadOptions {
  variant: 'listed' | 'soe'
  classificationRows: Array<{ label: string; endAmount: number; priorAmount: number; isTotal?: boolean; isSubtotal?: boolean; isDeduction?: boolean; rowKey?: string }>
  currentPortionRows: Array<{ label: string; endAmount: number; priorAmount: number; isTotal?: boolean }>
  rateRange: (rowKey: string, period: 'end' | 'prior') => string
  propertyNote: string
  conclusion: string
}

export function buildL3SyncPayload(opts: L3SyncPayloadOptions) {
  const { variant, classificationRows, currentPortionRows, rateRange, propertyNote, conclusion } = opts

  const classRows = classificationRows.map(r => ({
    label: r.label,
    values: [r.endAmount, rateRange(r.rowKey || '', 'end'), r.priorAmount, rateRange(r.rowKey || '', 'prior')],
    ...(r.isTotal ? { is_total: true } : {}),
  }))

  const cpRows = currentPortionRows.map(r => ({
    label: r.label,
    values: [r.endAmount, r.priorAmount],
    ...(r.isTotal ? { is_total: true } : {}),
  }))

  const sub_table_data: Record<string, any> = {
    '长期借款': classRows,
    '一年内到期的长期借款': cpRows,
  }

  const columns: Record<string, ColumnDef[]> = {
    '长期借款': buildClassificationColumns(variant),
    '一年内到期的长期借款': buildCurrentPortionColumns(variant),
  }

  const _note_texts: Array<{ section: string; title: string; text: string }> = []
  if (propertyNote) _note_texts.push({ section: 'property', title: '抵押质押说明', text: propertyNote })
  if (conclusion) _note_texts.push({ section: 'conclusion', title: '审计结论', text: conclusion })
  if (_note_texts.length > 0) sub_table_data._note_texts = _note_texts

  return { sub_table_data, columns }
}
