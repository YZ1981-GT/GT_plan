/**
 * I1 附注披露（上市公司）数据模型
 *
 * 对齐源模板「附注披露信息（上市公司）」+ note_template_listed「五、26」：
 *  分类列 × 变动行（原值/累计摊销/减值/账面价值）
 *  增减方式对齐 CAS6 / I1-2（购置/内部研发/企业合并；处置/失效终止）
 *
 * 复用 H1 cellValue / MovementRowDef 计算引擎。
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

export type { H1ListedCategory as I1ListedCategory, MovementCellMap, MovementRowDef }

export const I1_LISTED_KEYS = {
  categories: 'I1-listed-categories',
  movement: 'I1-listed-movement',
  noteRdRatio: 'I1-listed-note-rd-ratio',
  noteIndefinite: 'I1-listed-note-indefinite',
  noteMortgage: 'I1-listed-note-mortgage',
  noteImpairment: 'I1-listed-note-impairment',
  noteSale: 'I1-listed-note-sale',
  noteImportant: 'I1-listed-note-important',
  titleCertRows: 'I1-listed-title-cert-rows',
  importantRows: 'I1-listed-important-rows',
  auditNote: 'I1-listed-audit-note',
  auditConclusion: 'I1-listed-audit-conclusion',
} as const

/** 默认分类列（对齐 Excel B–L；可扩「……」） */
export const I1_LISTED_DEFAULT_CATEGORIES: readonly H1ListedCategory[] = [
  { key: 'land', label: '土地使用权' },
  { key: 'housing', label: '房屋使用权' },
  { key: 'patent', label: '专利权' },
  { key: 'knowhow', label: '非专利技术' },
  { key: 'trademark', label: '商标权' },
  { key: 'copyright', label: '著作权' },
  { key: 'franchise', label: '特许权' },
  { key: 'software', label: '软件' },
  { key: 'mining', label: '探矿权/采矿权' },
  { key: 'data', label: '数据资源' },
  { key: 'other', label: '其他' },
] as const

/** 源模板 / note_template 变动行 */
export const I1_LISTED_MOVEMENT_ROWS: MovementRowDef[] = [
  { key: 'cost_section', label: '一、账面原值', indent: 0, kind: 'section' },
  { key: 'cost_begin', label: '1.期初余额', indent: 1, kind: 'detail', editable: true },
  { key: 'cost_inc', label: '2.本期增加金额', indent: 1, kind: 'subtotal', sumOf: ['cost_inc_purchase', 'cost_inc_rd', 'cost_inc_merge', 'cost_inc_other', 'cost_inc_ellipsis'] },
  { key: 'cost_inc_purchase', label: '（1）购置', indent: 2, kind: 'detail', editable: true },
  { key: 'cost_inc_rd', label: '（2）内部研发', indent: 2, kind: 'detail', editable: true },
  { key: 'cost_inc_merge', label: '（3）企业合并增加', indent: 2, kind: 'detail', editable: true },
  { key: 'cost_inc_other', label: '（4）其他增加', indent: 2, kind: 'detail', editable: true },
  { key: 'cost_inc_ellipsis', label: '……', indent: 2, kind: 'ellipsis', editable: true },
  { key: 'cost_dec', label: '3.本期减少金额', indent: 1, kind: 'subtotal', sumOf: ['cost_dec_dispose', 'cost_dec_expire', 'cost_dec_other'] },
  { key: 'cost_dec_dispose', label: '（1）处置', indent: 2, kind: 'detail', editable: true },
  { key: 'cost_dec_expire', label: '（2）失效且终止确认的部分', indent: 2, kind: 'detail', editable: true },
  { key: 'cost_dec_other', label: '（3）其他减少', indent: 2, kind: 'detail', editable: true },
  { key: 'cost_end', label: '4.期末余额', indent: 1, kind: 'calc', endOf: { begin: 'cost_begin', inc: 'cost_inc', dec: 'cost_dec' } },

  { key: 'amort_section', label: '二、累计摊销', indent: 0, kind: 'section' },
  { key: 'amort_begin', label: '1.期初余额', indent: 1, kind: 'detail', editable: true },
  { key: 'amort_inc', label: '2.本期增加金额', indent: 1, kind: 'subtotal', sumOf: ['amort_inc_provision', 'amort_inc_other', 'amort_inc_ellipsis'] },
  { key: 'amort_inc_provision', label: '（1）计提', indent: 2, kind: 'detail', editable: true },
  { key: 'amort_inc_other', label: '（2）其他增加', indent: 2, kind: 'detail', editable: true },
  { key: 'amort_inc_ellipsis', label: '……', indent: 2, kind: 'ellipsis', editable: true },
  { key: 'amort_dec', label: '3.本期减少金额', indent: 1, kind: 'subtotal', sumOf: ['amort_dec_dispose', 'amort_dec_expire', 'amort_dec_other'] },
  { key: 'amort_dec_dispose', label: '（1）处置', indent: 2, kind: 'detail', editable: true },
  { key: 'amort_dec_expire', label: '（2）失效且终止确认的部分', indent: 2, kind: 'detail', editable: true },
  { key: 'amort_dec_other', label: '（3）其他减少', indent: 2, kind: 'detail', editable: true },
  { key: 'amort_end', label: '4.期末余额', indent: 1, kind: 'calc', endOf: { begin: 'amort_begin', inc: 'amort_inc', dec: 'amort_dec' } },

  { key: 'imp_section', label: '三、减值准备', indent: 0, kind: 'section' },
  { key: 'imp_begin', label: '1.期初余额', indent: 1, kind: 'detail', editable: true },
  { key: 'imp_inc', label: '2.本期增加金额', indent: 1, kind: 'subtotal', sumOf: ['imp_inc_provision', 'imp_inc_other', 'imp_inc_ellipsis'] },
  { key: 'imp_inc_provision', label: '（1）计提', indent: 2, kind: 'detail', editable: true },
  { key: 'imp_inc_other', label: '（2）其他增加', indent: 2, kind: 'detail', editable: true },
  { key: 'imp_inc_ellipsis', label: '……', indent: 2, kind: 'ellipsis', editable: true },
  { key: 'imp_dec', label: '3.本期减少金额', indent: 1, kind: 'subtotal', sumOf: ['imp_dec_dispose', 'imp_dec_other', 'imp_dec_ellipsis'] },
  { key: 'imp_dec_dispose', label: '（1）处置', indent: 2, kind: 'detail', editable: true },
  { key: 'imp_dec_other', label: '（2）其他减少', indent: 2, kind: 'detail', editable: true },
  { key: 'imp_dec_ellipsis', label: '……', indent: 2, kind: 'ellipsis', editable: true },
  { key: 'imp_end', label: '4.期末余额', indent: 1, kind: 'calc', endOf: { begin: 'imp_begin', inc: 'imp_inc', dec: 'imp_dec' } },

  { key: 'book_section', label: '四、账面价值', indent: 0, kind: 'section' },
  { key: 'book_end', label: '1.期末账面价值', indent: 1, kind: 'book', bookOf: { cost: 'cost_end', dep: 'amort_end', impair: 'imp_end' } },
  { key: 'book_begin', label: '2.期初账面价值', indent: 1, kind: 'book', bookOf: { cost: 'cost_begin', dep: 'amort_begin', impair: 'imp_begin' } },
]

/** 蓝色指引 → placeholder，不作默认 value */
export const I1_LISTED_GUIDANCE = {
  rdRatio: '①本期通过公司内部研发形成的无形资产占无形资产期末账面价值的比例。',
  indefinite: '②使用寿命不确定的无形资产判断依据。',
  mortgage: '③说明抵押、担保的土地使用权等情况。',
  impairment:
    '④长期资产本期进行减值测试的，应披露可收回金额的具体确定方法及相关参数；即使未计提减值，亦应披露测试情况。',
  sale: '⑤本期以明显高于账面价值的价格出售无形资产的，应说明交易作价基础、估值模型及敏感性分析。',
  important: '⑥对企业财务报表具有重要影响的单项无形资产（内容、账面价值、剩余摊销期限）。',
  titleCert: '（披露期末未办妥权属证书的土地使用权账面价值及原因。）',
} as const

export function i1ListedCellValue(map: MovementCellMap, def: MovementRowDef, catKey: string): number {
  return cellValue(map, def, catKey, I1_LISTED_MOVEMENT_ROWS)
}

export function i1ListedTotalCellValue(
  map: MovementCellMap,
  def: MovementRowDef,
  categories: readonly H1ListedCategory[],
): number {
  if (def.kind === 'section') return 0
  return categories.reduce((s, c) => s + i1ListedCellValue(map, def, c.key), 0)
}

export { rawCell, setCell, num }

/** I1-2 category / name → 上市分类 key */
export function mapToI1ListedCategoryKey(categoryOrName: string): string {
  const s = String(categoryOrName || '')
  if (/土地/.test(s)) return 'land'
  if (/房屋|住房/.test(s)) return 'housing'
  if (/专利/.test(s) && !/非专利/.test(s)) return 'patent'
  if (/非专利|专有技术|know.?how/i.test(s)) return 'knowhow'
  if (/商标/.test(s)) return 'trademark'
  if (/著作|版权/.test(s)) return 'copyright'
  if (/特许|特许经营/.test(s)) return 'franchise'
  if (/软件|系统/.test(s)) return 'software'
  if (/探矿|采矿|矿权/.test(s)) return 'mining'
  if (/数据资源|数据资产/.test(s)) return 'data'
  return 'other'
}

export function mapCostIncreaseMethod(method: string): 'cost_inc_purchase' | 'cost_inc_rd' | 'cost_inc_merge' | 'cost_inc_other' {
  const s = String(method || '')
  if (/购置|外购|购买/.test(s)) return 'cost_inc_purchase'
  if (/内部研发|自行研发|研发/.test(s)) return 'cost_inc_rd'
  if (/企业合并|合并增加|并购/.test(s)) return 'cost_inc_merge'
  return 'cost_inc_other'
}

export function mapCostDecreaseMethod(method: string): 'cost_dec_dispose' | 'cost_dec_expire' | 'cost_dec_other' {
  const s = String(method || '')
  if (/处置|出售|转让|报废/.test(s)) return 'cost_dec_dispose'
  if (/失效|终止确认|到期/.test(s)) return 'cost_dec_expire'
  return 'cost_dec_other'
}

export interface I1TitleCertRow {
  rowId: string
  name: string
  bookValue: number
  reason: string
}

export interface I1ImportantItemRow {
  rowId: string
  name: string
  bookValue: number
  remainingAmortMonths: number
}

export interface I1ListedSyncSnapshot {
  categories: H1ListedCategory[]
  movement: MovementCellMap
  noteRdRatio: string
  noteIndefinite: string
  noteMortgage: string
  noteImpairment: string
  noteSale: string
  noteImportant: string
  titleCertRows: I1TitleCertRow[]
  importantRows: I1ImportantItemRow[]
  /** 数据资源独立子表 */
  dataResource?: import('./i1DisclosureEnhance').I1DataResourceMove
  noteDataResource?: string
  amortAlloc?: import('./i1DisclosureEnhance').I1AmortAllocSummary
}
