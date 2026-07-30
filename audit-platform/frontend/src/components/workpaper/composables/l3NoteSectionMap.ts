/**
 * l3NoteSectionMap — L3 长期借款 披露表↔附注模块 联动映射
 *
 * 权威来源 note_template_variant_matrix.json · chang_qi_jie_kuan：
 *   listed_standalone = 五、45
 *   soe_standalone    = 八、49
 *
 * 附注模板结构：
 *   表1: 长期借款分类
 *     上市 五、45: 项目/期末余额/利率区间/上年年末余额/利率区间
 *     国企 八、49: 借款类别/期末余额/期初余额/期末利率期间（%）
 *     固定行: 质押/抵押/保证/信用借款 + 小计 − 减一年内到期 = 合计
 *   表2: 一年内到期的长期借款（项目/期末余额/上年年末余额|期初余额）
 *   说明: 财产抵押质押情况 + 审计结论
 */
import type { ColumnDef } from './disclosureColumnDefs'

export const L3_NOTE_SECTION = {
  listed: '五、45',
  soe: '八、49',
} as const

export const L3_DISCLOSURE_SHEET_LISTED = '附注披露信息核对（上市公司）'
export const L3_DISCLOSURE_SHEET_SOE = '附注披露信息核对（国企）'

// ─── 列定义 ──────────────────────────────────────────────────────────────────
//
// 口径实证见 spec `disclosure-columns-coverage-rollout` design §批 1 列头清查 §4/§5：
//   · 4 张表在源模板中**全是单行表头** → 标签列一律 `flat: true`，0 处 `group`。
//   · 上市长期借款表两列同名 `利率区间`（附注模版 L4632 即如此）—— 不去重、不加期别
//     前缀（加前缀即杜撰），靠 key 区分 `endRate` / `priorRate`。
//   · 国企长期借款表取**附注模版 L3679 的 4 列**（借款类别/期末余额/期初余额/
//     期末利率期间（%）），与 `note_template_soe.json` 八、49 + consol 五-50-1 一致。
//     源 xlsx A8:E8 多一列期初「利率区间」，在附注侧无落点 →
//     按「附注是交付物，底稿可多留审计列但同步时投影成附注形状」丢弃 `priorRate`。
//   · 国企一年内到期表标签列取附注模版 L3628 的 `项目`（源 A21 与底稿 UI 为
//     `借款类别`，冲突时以附注为准，否则标签列头 ≠ 附注 headers[0] 会出孤儿列）。

function buildClassificationColumns(variant: 'listed' | 'soe'): ColumnDef[] {
  if (variant === 'soe') {
    return [
      { key: 'label', label: '借款类别', is_label: true, flat: true },
      { key: 'endAmount', label: '期末余额', format: 'amount' },
      { key: 'priorAmount', label: '期初余额', format: 'amount' },
      { key: 'endRate', label: '期末利率期间（%）', format: 'text' },
    ]
  }
  return [
    { key: 'label', label: '项目', is_label: true, flat: true },
    { key: 'endAmount', label: '期末余额', format: 'amount' },
    { key: 'endRate', label: '利率区间', format: 'text' },
    { key: 'priorAmount', label: '上年年末余额', format: 'amount' },
    { key: 'priorRate', label: '利率区间', format: 'text' },
  ]
}

function buildCurrentPortionColumns(variant: 'listed' | 'soe'): ColumnDef[] {
  return [
    { key: 'label', label: '项目', is_label: true, flat: true },
    { key: 'endAmount', label: '期末余额', format: 'amount' },
    { key: 'priorAmount', label: variant === 'listed' ? '上年年末余额' : '期初余额', format: 'amount' },
  ]
}

function buildL3Columns(variant: 'listed' | 'soe'): Record<string, ColumnDef[]> {
  return {
    '长期借款': buildClassificationColumns(variant),
    '一年内到期的长期借款': buildCurrentPortionColumns(variant),
  }
}

/** L3 上市（五、45）子表列头，键 = `sub_table_data` 数据键 */
export function buildL3ListedColumns(): Record<string, ColumnDef[]> {
  return buildL3Columns('listed')
}

/** L3 国企（八、49）子表列头，键 = `sub_table_data` 数据键 */
export function buildL3SoeColumns(): Record<string, ColumnDef[]> {
  return buildL3Columns('soe')
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

  // values 必须与 buildClassificationColumns(variant) 的非标签列**同序**：
  //   上市 4 列 = 期末余额 / 利率区间(end) / 上年年末余额 / 利率区间(prior)
  //   国企 3 列 = 期末余额 / 期初余额 / 期末利率期间（%）（附注侧无期初利率落点）
  const classRows = classificationRows.map(r => ({
    label: r.label,
    values: variant === 'soe'
      ? [r.endAmount, r.priorAmount, rateRange(r.rowKey || '', 'end')]
      : [r.endAmount, rateRange(r.rowKey || '', 'end'), r.priorAmount, rateRange(r.rowKey || '', 'prior')],
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

  const columns = variant === 'listed' ? buildL3ListedColumns() : buildL3SoeColumns()

  const _note_texts: Array<{ section: string; title: string; text: string }> = []
  if (propertyNote) _note_texts.push({ section: 'property', title: '抵押质押说明', text: propertyNote })
  if (conclusion) _note_texts.push({ section: 'conclusion', title: '审计结论', text: conclusion })
  if (_note_texts.length > 0) sub_table_data._note_texts = _note_texts

  return { sub_table_data, columns }
}
