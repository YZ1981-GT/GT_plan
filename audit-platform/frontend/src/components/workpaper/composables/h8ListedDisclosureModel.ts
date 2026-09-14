/**
 * H8 附注披露（上市公司）数据模型
 *
 * 对齐源模板「附注披露信息（上市公司）」48行7列 + note_template_listed「五、25」：
 *  一、账面原值（租入 / 租赁负债调整 / 转租赁为融资租赁 / 转让或持有待售 / 其他）
 *  二、累计折旧
 *  三、减值准备
 *  四、账面价值（期末/期初）
 *  提示：短期/低价值费用见附注；减值测试披露
 *
 * 复用 H1 的 cellValue / MovementRowDef 计算引擎。
 */
import {
  cellValue,
  num,
  rawCell,
  setCell,
  type H1ListedCategory,
  type MovementCellMap,
  type MovementRowDef,
} from './h1ListedDisclosureModel'

export type { H1ListedCategory as H8ListedCategory, MovementCellMap, MovementRowDef }

export const H8_LISTED_KEYS = {
  categories: 'H8-listed-categories',
  movement: 'H8-listed-movement',
  noteShortLow: 'H8-listed-note-short-low',
  noteImpairment: 'H8-listed-note-impairment',
  auditNote: 'H8-listed-audit-note',
  auditConclusion: 'H8-listed-audit-conclusion',
} as const

/** 默认分类列（对齐源模板 B–D + 可扩「……」） */
export const H8_LISTED_DEFAULT_CATEGORIES: readonly H1ListedCategory[] = [
  { key: 'buildings', label: '房屋及建筑物' },
  { key: 'machinery', label: '机器设备' },
  { key: 'transport', label: '运输设备' },
  { key: 'other', label: '其他' },
] as const

/** 源模板 R7–R45 行结构（使用权资产专用增减明细） */
export const H8_LISTED_MOVEMENT_ROWS: MovementRowDef[] = [
  { key: 'cost_section', label: '一、账面原值：', indent: 0, kind: 'section' },
  { key: 'cost_begin', label: '1.期初余额', indent: 1, kind: 'detail', editable: true },
  { key: 'cost_inc', label: '2.本期增加金额', indent: 1, kind: 'subtotal', sumOf: ['cost_inc_lease', 'cost_inc_liab_adj', 'cost_inc_ellipsis'] },
  { key: 'cost_inc_lease', label: '（1）租入', indent: 2, kind: 'detail', editable: true },
  { key: 'cost_inc_liab_adj', label: '（2）租赁负债调整', indent: 2, kind: 'detail', editable: true },
  { key: 'cost_inc_ellipsis', label: '……', indent: 2, kind: 'ellipsis', editable: true },
  { key: 'cost_dec', label: '3.本期减少金额', indent: 1, kind: 'subtotal', sumOf: ['cost_dec_sublease', 'cost_dec_transfer', 'cost_dec_other', 'cost_dec_ellipsis'] },
  { key: 'cost_dec_sublease', label: '（1）转租赁为融资租赁', indent: 2, kind: 'detail', editable: true },
  { key: 'cost_dec_transfer', label: '（2）转让或持有待售', indent: 2, kind: 'detail', editable: true },
  { key: 'cost_dec_other', label: '（3）其他减少', indent: 2, kind: 'detail', editable: true },
  { key: 'cost_dec_ellipsis', label: '……', indent: 2, kind: 'ellipsis', editable: true },
  { key: 'cost_end', label: '4.期末余额', indent: 1, kind: 'calc', endOf: { begin: 'cost_begin', inc: 'cost_inc', dec: 'cost_dec' } },

  { key: 'dep_section', label: '二、累计折旧', indent: 0, kind: 'section' },
  { key: 'dep_begin', label: '1.期初余额', indent: 1, kind: 'detail', editable: true },
  { key: 'dep_inc', label: '2.本期增加金额', indent: 1, kind: 'subtotal', sumOf: ['dep_inc_provision', 'dep_inc_other', 'dep_inc_ellipsis'] },
  { key: 'dep_inc_provision', label: '（1）计提', indent: 2, kind: 'detail', editable: true },
  { key: 'dep_inc_other', label: '（2）其他增加', indent: 2, kind: 'detail', editable: true },
  { key: 'dep_inc_ellipsis', label: '……', indent: 2, kind: 'ellipsis', editable: true },
  { key: 'dep_dec', label: '3.本期减少金额', indent: 1, kind: 'subtotal', sumOf: ['dep_dec_sublease', 'dep_dec_transfer', 'dep_dec_other', 'dep_dec_ellipsis'] },
  { key: 'dep_dec_sublease', label: '（1）转租赁为融资租赁', indent: 2, kind: 'detail', editable: true },
  { key: 'dep_dec_transfer', label: '（2）转让或持有待售', indent: 2, kind: 'detail', editable: true },
  { key: 'dep_dec_other', label: '（3）其他减少', indent: 2, kind: 'detail', editable: true },
  { key: 'dep_dec_ellipsis', label: '……', indent: 2, kind: 'ellipsis', editable: true },
  { key: 'dep_end', label: '4.期末余额', indent: 1, kind: 'calc', endOf: { begin: 'dep_begin', inc: 'dep_inc', dec: 'dep_dec' } },

  { key: 'imp_section', label: '三、减值准备', indent: 0, kind: 'section' },
  { key: 'imp_begin', label: '1.期初余额', indent: 1, kind: 'detail', editable: true },
  { key: 'imp_inc', label: '2.本期增加金额', indent: 1, kind: 'subtotal', sumOf: ['imp_inc_provision', 'imp_inc_other', 'imp_inc_ellipsis'] },
  { key: 'imp_inc_provision', label: '（1）计提', indent: 2, kind: 'detail', editable: true },
  { key: 'imp_inc_other', label: '（2）其他增加', indent: 2, kind: 'detail', editable: true },
  { key: 'imp_inc_ellipsis', label: '……', indent: 2, kind: 'ellipsis', editable: true },
  { key: 'imp_dec', label: '3.本期减少金额', indent: 1, kind: 'subtotal', sumOf: ['imp_dec_sublease', 'imp_dec_transfer', 'imp_dec_other', 'imp_dec_ellipsis'] },
  { key: 'imp_dec_sublease', label: '（1）转租赁为融资租赁', indent: 2, kind: 'detail', editable: true },
  { key: 'imp_dec_transfer', label: '（2）转让或持有待售', indent: 2, kind: 'detail', editable: true },
  { key: 'imp_dec_other', label: '（3）其他减少', indent: 2, kind: 'detail', editable: true },
  { key: 'imp_dec_ellipsis', label: '……', indent: 2, kind: 'ellipsis', editable: true },
  { key: 'imp_end', label: '4.期末余额', indent: 1, kind: 'calc', endOf: { begin: 'imp_begin', inc: 'imp_inc', dec: 'imp_dec' } },

  { key: 'book_section', label: '四、账面价值', indent: 0, kind: 'section' },
  { key: 'book_end', label: '1.期末账面价值', indent: 1, kind: 'book', bookOf: { cost: 'cost_end', dep: 'dep_end', impair: 'imp_end' } },
  { key: 'book_begin', label: '2.期初账面价值', indent: 1, kind: 'book', bookOf: { cost: 'cost_begin', dep: 'dep_begin', impair: 'imp_begin' } },
]

/** 源模板蓝/黄字提示 → placeholder，不作默认 value */
export const H8_LISTED_GUIDANCE = {
  shortLow: '本公司确认与短期租赁和低价值资产租赁相关的租赁费用见附注五、82。',
  impairment:
    '【长期资产本期进行减值测试的，应披露可收回金额的具体确定方法。可收回金额按公允价值减去处置费用后的净额确定的，应披露公允价值和处置费用的确定方式、关键参数及其确定依据。可收回金额按预计未来现金流量的现值确定的，应披露预测期的年限、预测期及稳定期的关键参数及其确定依据。前述信息与以前年度减值测试采用的信息或外部信息明显不一致的，应披露差异原因。】',
  impairmentNote: '注意：1、本年执行减值测试的，即使未计提减值，也要参照上述要求披露。2、估计可收回金额时通常不应使用重置成本法。',
} as const

export function h8ListedCellValue(map: MovementCellMap, def: MovementRowDef, catKey: string): number {
  return cellValue(map, def, catKey, H8_LISTED_MOVEMENT_ROWS)
}

export function h8ListedTotalCellValue(
  map: MovementCellMap,
  def: MovementRowDef,
  categories: readonly H1ListedCategory[],
): number {
  if (def.kind === 'section') return 0
  return categories.reduce((s, c) => s + h8ListedCellValue(map, def, c.key), 0)
}

export { rawCell, setCell, num }

/** 将 H8-2/H8-1 名称映射到上市分类 key */
export function mapToListedCategoryKey(name: string): string {
  const s = String(name || '')
  if (/房屋|建筑|办公楼|厂房/.test(s)) return 'buildings'
  if (/机器|设备|生产/.test(s) && !/运输|车辆/.test(s)) return 'machinery'
  if (/运输|车辆|汽车|货车/.test(s)) return 'transport'
  return 'other'
}

export interface H8ListedSyncSnapshot {
  categories: H1ListedCategory[]
  movement: MovementCellMap
  noteShortLow: string
  noteImpairment: string
}
