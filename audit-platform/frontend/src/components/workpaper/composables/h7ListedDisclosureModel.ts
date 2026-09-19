/**
 * H7 生产性生物资产 附注披露（上市公司）数据模型
 *
 * 源模板 `H7 生产性生物资产.xlsx` / `附注披露信息（上市公司）`，openpyxl 合并区实证
 * 两级表头（表1 `A9:A10` / `B9:C9` / `D9:E9` / `F9:G9` / `H9:I9` / `J9:J10`；
 * 表2 R51:R52 同构）：
 *
 *   列 = 项目（rowspan 2）+ 4 个产业（每个下辖 `类别` + `……` 两个子列）+ 合计（rowspan 2）
 *   表1「（1）以成本计量」R11–R44 = 34 行四层
 *   表2「（2）以公允价值计量」R53–R64 = 11 行
 *
 * 🔴 `……` 两种语义相反：
 * - 作**列头**（R10/R52 的 `……`）永远收不到数据 → 丢弃，改为「可增删的类别列」
 * - 作**行**（表1 R20/R30/R40、表2 R58/R63）是真实可扩明细行且参与所属小计 → 保留
 *
 * 🔴 列 `key` 用稳定的 `{industryKey}_{seq}`，**不能用 `key: label`**（H1/H8 那样）——
 * 四个产业的默认叶子名都是源模板字面 `类别`，用 label 作 key 会撞键。
 *
 * spec: h7-biological-assets-disclosure-rebuild (Task 2)
 */
import {
  emptyMovement,
  num,
  rawCell,
  setCell,
  type MovementCellMap,
} from './h1ListedDisclosureModel'

export type { MovementCellMap }
export { emptyMovement, num, rawCell, setCell }

/** 源模板 R9 的 4 个产业（父表头） */
export const H7_INDUSTRIES = [
  { key: 'crop', label: '种植业' },
  { key: 'livestock', label: '畜牧养殖业' },
  { key: 'forestry', label: '林业' },
  { key: 'aquatic', label: '水产业' },
] as const

export type H7IndustryKey = (typeof H7_INDUSTRIES)[number]['key']

export const H7_INDUSTRY_LABELS: readonly string[] = H7_INDUSTRIES.map((i) => i.label)

/** 源模板 R10 首个子列表头字面（占位，审计师应改成实际类别名如「苹果树」「奶牛」） */
export const H7_DEFAULT_CATEGORY_LABEL = '类别'

/** 合计列 key（源模板 J 列，rowspan=2 无 group） */
export const H7_TOTAL_COL_KEY = 'total'

export interface H7ListedCategory {
  /** 稳定标识 `{industryKey}_{seq}`；删中间项不重排，不与已删 key 冲突 */
  key: string
  /** 叶子列名（审计师可改） */
  label: string
  /** 所属产业 key */
  industry: H7IndustryKey
}

/** 默认：每产业 1 个类别列，叶子名取源模板字面 `类别` */
export function createDefaultH7Categories(): H7ListedCategory[] {
  return H7_INDUSTRIES.map((ind) => ({
    key: `${ind.key}_1`,
    label: H7_DEFAULT_CATEGORY_LABEL,
    industry: ind.key,
  }))
}

/**
 * 为某产业分配下一个不冲突的类别 key。
 *
 * 取该产业现有 key 的最大 seq + 1（**不复用**已删除的 seq），保证新增列不与
 * 历史数据错位。
 */
export function nextH7CategoryKey(
  categories: readonly H7ListedCategory[],
  industry: H7IndustryKey,
): string {
  const prefix = `${industry}_`
  let max = 0
  for (const c of categories) {
    if (!c.key.startsWith(prefix)) continue
    const seq = Number(c.key.slice(prefix.length))
    if (Number.isFinite(seq) && seq > max) max = seq
  }
  return `${prefix}${max + 1}`
}

/** 按源模板列序（产业顺序 → 产业内原序）排列；入参缺失时返回空数组不抛错 */
export function orderH7Categories(
  categories: readonly H7ListedCategory[] | null | undefined,
): H7ListedCategory[] {
  const list = Array.isArray(categories) ? categories : []
  const out: H7ListedCategory[] = []
  for (const ind of H7_INDUSTRIES) {
    for (const c of list) if (c.industry === ind.key) out.push(c)
  }
  return out
}

export function h7IndustryLabel(key: string): string {
  return H7_INDUSTRIES.find((i) => i.key === key)?.label || String(key)
}

// ─────────────────────────── 行模型 ───────────────────────────

export type H7RowKind =
  | 'section'
  | 'detail'
  | 'ellipsis'
  | 'subtotal'
  | 'calc'
  | 'book'
  | 'delta'
  | 'calc2'

export interface H7MovementRowDef {
  key: string
  label: string
  indent: number
  kind: H7RowKind
  editable?: boolean
  /** subtotal：分项之和 */
  sumOf?: string[]
  /** calc：期末 = 期初 + 增 − 减 */
  endOf?: { begin: string; inc: string; dec: string }
  /** book：账面价值 = 原值 − 累计折旧 − 减值准备 */
  bookOf?: { cost: string; dep: string; impair: string }
  /** delta：带符号合成（本期变动 = 加项之和 − 减项之和） */
  delta?: { plus: string[]; minus: string[] }
  /** calc2：两项相加（期末余额 = 期初余额 + 本期变动） */
  addOf?: [string, string]
}

/** 表1「（1）以成本计量」源模板 R11–R44 共 34 行四层 */
export const H7_COST_MOVEMENT_ROWS: H7MovementRowDef[] = [
  { key: 'cost_section', label: '一、账面原值', indent: 0, kind: 'section' },
  { key: 'cost_begin', label: '1.期初余额', indent: 1, kind: 'detail', editable: true },
  {
    key: 'cost_inc', label: '2.本期增加金额', indent: 1, kind: 'subtotal',
    sumOf: ['cost_inc_purchase', 'cost_inc_self', 'cost_inc_other'],
  },
  { key: 'cost_inc_purchase', label: '（1）外购', indent: 2, kind: 'detail', editable: true },
  { key: 'cost_inc_self', label: '（2）自行培育', indent: 2, kind: 'detail', editable: true },
  { key: 'cost_inc_other', label: '（3）其他增加', indent: 2, kind: 'detail', editable: true },
  {
    key: 'cost_dec', label: '3.本期减少金额', indent: 1, kind: 'subtotal',
    sumOf: ['cost_dec_dispose', 'cost_dec_other', 'cost_dec_ellipsis'],
  },
  { key: 'cost_dec_dispose', label: '（1）处置', indent: 2, kind: 'detail', editable: true },
  { key: 'cost_dec_other', label: '（2）其他', indent: 2, kind: 'detail', editable: true },
  { key: 'cost_dec_ellipsis', label: '……', indent: 2, kind: 'ellipsis', editable: true },
  {
    key: 'cost_end', label: '4.期末余额', indent: 1, kind: 'calc',
    endOf: { begin: 'cost_begin', inc: 'cost_inc', dec: 'cost_dec' },
  },

  { key: 'dep_section', label: '二、累计折旧', indent: 0, kind: 'section' },
  { key: 'dep_begin', label: '1.期初余额', indent: 1, kind: 'detail', editable: true },
  {
    key: 'dep_inc', label: '2.本期增加金额', indent: 1, kind: 'subtotal',
    sumOf: ['dep_inc_provision', 'dep_inc_other'],
  },
  { key: 'dep_inc_provision', label: '（1）计提', indent: 2, kind: 'detail', editable: true },
  { key: 'dep_inc_other', label: '（2）其他增加', indent: 2, kind: 'detail', editable: true },
  {
    key: 'dep_dec', label: '3.本期减少金额', indent: 1, kind: 'subtotal',
    sumOf: ['dep_dec_dispose', 'dep_dec_other', 'dep_dec_ellipsis'],
  },
  { key: 'dep_dec_dispose', label: '（1）处置', indent: 2, kind: 'detail', editable: true },
  { key: 'dep_dec_other', label: '（2）其他', indent: 2, kind: 'detail', editable: true },
  { key: 'dep_dec_ellipsis', label: '……', indent: 2, kind: 'ellipsis', editable: true },
  {
    key: 'dep_end', label: '4.期末余额', indent: 1, kind: 'calc',
    endOf: { begin: 'dep_begin', inc: 'dep_inc', dec: 'dep_dec' },
  },

  { key: 'imp_section', label: '三、减值准备', indent: 0, kind: 'section' },
  { key: 'imp_begin', label: '1.期初余额', indent: 1, kind: 'detail', editable: true },
  {
    key: 'imp_inc', label: '2.本期增加金额', indent: 1, kind: 'subtotal',
    sumOf: ['imp_inc_provision', 'imp_inc_other'],
  },
  { key: 'imp_inc_provision', label: '（1）计提', indent: 2, kind: 'detail', editable: true },
  { key: 'imp_inc_other', label: '（2）其他增加', indent: 2, kind: 'detail', editable: true },
  {
    key: 'imp_dec', label: '3.本期减少金额', indent: 1, kind: 'subtotal',
    sumOf: ['imp_dec_dispose', 'imp_dec_other', 'imp_dec_ellipsis'],
  },
  { key: 'imp_dec_dispose', label: '（1）处置', indent: 2, kind: 'detail', editable: true },
  { key: 'imp_dec_other', label: '（2）其他', indent: 2, kind: 'detail', editable: true },
  { key: 'imp_dec_ellipsis', label: '……', indent: 2, kind: 'ellipsis', editable: true },
  {
    key: 'imp_end', label: '4.期末余额', indent: 1, kind: 'calc',
    endOf: { begin: 'imp_begin', inc: 'imp_inc', dec: 'imp_dec' },
  },

  { key: 'book_section', label: '四、账面价值', indent: 0, kind: 'section' },
  {
    key: 'book_end', label: '1.期末账面价值', indent: 1, kind: 'book',
    bookOf: { cost: 'cost_end', dep: 'dep_end', impair: 'imp_end' },
  },
  {
    key: 'book_begin', label: '2.期初账面价值', indent: 1, kind: 'book',
    bookOf: { cost: 'cost_begin', dep: 'dep_begin', impair: 'imp_begin' },
  },
]

/** 表2「（2）以公允价值计量」源模板 R53–R64 共 11 行（R61 为空行，源模板留白） */
export const H7_FAIR_MOVEMENT_ROWS: H7MovementRowDef[] = [
  { key: 'fair_begin', label: '一、期初余额', indent: 0, kind: 'detail', editable: true },
  {
    key: 'fair_change', label: '二、本期变动', indent: 0, kind: 'delta',
    delta: {
      plus: ['fair_add_purchase', 'fair_add_self', 'fair_add_merge', 'fair_add_ellipsis',
        'fair_fv_change', 'fair_fv_ellipsis'],
      minus: ['fair_less_dispose', 'fair_less_other'],
    },
  },
  { key: 'fair_add_purchase', label: '加：外购', indent: 1, kind: 'detail', editable: true },
  { key: 'fair_add_self', label: '自行培育', indent: 2, kind: 'detail', editable: true },
  { key: 'fair_add_merge', label: '企业合并增加', indent: 2, kind: 'detail', editable: true },
  { key: 'fair_add_ellipsis', label: '……', indent: 2, kind: 'ellipsis', editable: true },
  { key: 'fair_less_dispose', label: '减：处置', indent: 1, kind: 'detail', editable: true },
  { key: 'fair_less_other', label: '其他转出', indent: 2, kind: 'detail', editable: true },
  { key: 'fair_fv_change', label: '公允价值变动', indent: 1, kind: 'detail', editable: true },
  { key: 'fair_fv_ellipsis', label: '……', indent: 2, kind: 'ellipsis', editable: true },
  {
    key: 'fair_end', label: '三、期末余额', indent: 0, kind: 'calc2',
    addOf: ['fair_begin', 'fair_change'],
  },
]

// ─────────────────────────── 取值引擎 ───────────────────────────

/**
 * 单格取值。派生行**读时推导**（不持久化），与 H1/H8 同范式。
 *
 * 未知 kind / 缺失格一律返回 0，不抛错。
 */
export function h7CellValue(
  map: MovementCellMap,
  def: H7MovementRowDef,
  colKey: string,
  rows: readonly H7MovementRowDef[],
): number {
  const byKey = (k: string) => rows.find((r) => r.key === k)
  const val = (k: string): number => {
    const d = byKey(k)
    return d ? h7CellValue(map, d, colKey, rows) : 0
  }

  switch (def.kind) {
    case 'section':
      return 0
    case 'detail':
    case 'ellipsis':
      return rawCell(map, def.key, colKey)
    case 'subtotal':
      return (def.sumOf || []).reduce((s, k) => s + val(k), 0)
    case 'calc': {
      const e = def.endOf
      if (!e) return 0
      return val(e.begin) + val(e.inc) - val(e.dec)
    }
    case 'book': {
      const b = def.bookOf
      if (!b) return 0
      return val(b.cost) - val(b.dep) - val(b.impair)
    }
    case 'delta': {
      const d = def.delta
      if (!d) return 0
      const plus = d.plus.reduce((s, k) => s + val(k), 0)
      const minus = d.minus.reduce((s, k) => s + val(k), 0)
      return plus - minus
    }
    case 'calc2': {
      const a = def.addOf
      if (!a) return 0
      return val(a[0]) + val(a[1])
    }
    default:
      return 0
  }
}

/** 合计列 = 各类别列之和（section 行恒 0） */
export function h7TotalCellValue(
  map: MovementCellMap,
  def: H7MovementRowDef,
  categories: readonly H7ListedCategory[],
  rows: readonly H7MovementRowDef[],
): number {
  if (def.kind === 'section') return 0
  return categories.reduce((s, c) => s + h7CellValue(map, def, c.key, rows), 0)
}

/** 该行是否可录入（派生行只读） */
export function isH7EditableRow(def: H7MovementRowDef): boolean {
  return def.editable === true && (def.kind === 'detail' || def.kind === 'ellipsis')
}

/** 派生行的公式说明（UI tooltip / 溯源） */
export function h7RowFormula(def: H7MovementRowDef): string {
  switch (def.kind) {
    case 'subtotal':
      return `= ${(def.sumOf || []).length} 个分项之和`
    case 'calc':
      return '期末余额 = 期初余额 + 本期增加金额 − 本期减少金额'
    case 'book':
      return '账面价值 = 账面原值 − 累计折旧 − 减值准备'
    case 'delta':
      return '本期变动 = 加项之和 − 减项之和（含公允价值变动）'
    case 'calc2':
      return '期末余额 = 期初余额 + 本期变动'
    default:
      return ''
  }
}

export interface H7ListedSyncSnapshot {
  categories: H7ListedCategory[]
  cost: MovementCellMap
  fair: MovementCellMap
  notePolicy: string
  noteImpairment: string
  noteSupplement: string
}

/** 持久化键（checklist_responses item_id） */
export const H7_LISTED_KEYS = {
  categories: 'H7-disc-listed-categories',
  cost: 'H7-disc-listed-cost',
  fair: 'H7-disc-listed-fair',
  notePolicy: 'H7-disc-listed-policy',
  noteImpairment: 'H7-disc-listed-impairment',
  noteSupplement: 'H7-disc-listed-text',
} as const

/** 源模板红字（作方法论上下文 / placeholder，勿写入 v-model） */
export const H7_LISTED_GUIDANCE = {
  impairment:
    '【长期资产本期进行减值测试的，应披露可收回金额的具体确定方法。可收回金额按公允价值减去处置费用后的净额确定的，'
    + '应披露公允价值和处置费用的确定方式、关键参数及其确定依据。可收回金额按预计未来现金流量的现值确定的，'
    + '应披露预测期的年限、预测期及稳定期的关键参数及其确定依据。前述信息与以前年度减值测试采用的信息或外部信息'
    + '明显不一致的，或公司以前年度减值测试采用信息与当年实际情况明显不一致的，应披露差异原因。（15号文第十九条（十九））】',
  impairmentNote: '注意：本年执行减值测试的，即使未计提减值，也要参照上述要求披露。',
  supplement:
    '（提示：如有天然起源的生物资产，还应披露该资产的类别、取得方式和数量等。各类生产性生物资产的预计使用寿命、'
    + '预计净残值、折旧方法、累计折旧和减值准备累计金额。与生物资产相关的风险情况与管理措施。）',
  publicWelfare:
    '（有公益性生物资产的企业，应增设“公益性生物资产”项目，列在“生产性生物资产”项目之后）',
} as const
