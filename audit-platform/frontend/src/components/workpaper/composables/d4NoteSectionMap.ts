/**
 * D4 营业收入/营业成本披露 ↔ 附注章节冻结映射与 sync payload 构建
 *
 * 权威来源：note_template_listed.json 五、62「营业收入和营业成本」/
 *          note_template_soe.json 八、64「营业收入、营业成本」
 * （表名逐字对照模板；列头对齐 D4TabDisclosureListed/Soe 组件既有 el-table-column，
 *  行数据来自 useD4Disclosure 的 section1~section4 行模型）。
 *
 * 底稿 → 附注单向推送（sync_from_workpaper）：
 *  - sub_table_data 各子表 → 附注 table_data.sub_table_data（读时投影为 _tables 渲染）
 *  - sub_table_data._note_texts → 附注 text_content（文本框内容与披露表保持一致）
 *  - columns → _sub_table_columns（投影器据此产出扁平表头，附注模块渲染）
 *
 * 🔴 覆盖必须完整：note_sub_table_projector 对 `_source=workpaper` 只渲染推送过的子表
 * （不与模板 _tables 合并），故逐张覆盖。
 * 🔴 sub_table_data 各子表键 ↔ columns 键必须相同（后端投影器按名匹配）。
 *
 * 覆盖范围（对照模板 + useD4Disclosure）：
 *  - 上市 五、62：4 张结构化子表（营业收入和营业成本 / 按行业 / 按地区 / 按商品转让时间）
 *    + note-1~note-8 文本 → _note_texts。
 *  - 国企 八、64：4 张结构化子表（同上）+ note-1~note-7 文本 → _note_texts。
 *
 * 与模板字面值的偏差（渲染必需，不新增/不删减数据列，参照 D6 precedent）：
 *  - 主表模板 headers 简化为「项目/本期发生额/上期发生额」3 列，但披露表实为
 *    本期收入/本期成本/上期收入/上期成本（本期发生额、上期发生额各拆收入/成本），
 *    此处以披露表 5 列为准（多级表头拍平为组合列名），保证附注表结构跟披露表一致。
 *  - 按行业/地区/时段表披露表仅录本期收入/本期成本两列（无上期数据），以披露表 2 列为准。
 *  - 模板另含「分摊至尚未履行的履约义务的交易价格…预计时间」与（上市）「试运行销售收入」
 *    两张表，披露表以文本框（note-6/note-8）承载而非结构化行，故不推送结构化子表，
 *    其内容随 note-6/note-8 进入 _note_texts（宁缺勿造，不臆造行数据）。
 */
import type { ColumnDef } from './disclosureColumnDefs'

export type D4DisclosureVariant = 'listed' | 'soe'

export const D4_NOTE_SECTION = {
  listed: '五、62',
  soe: '八、64',
} as const satisfies Record<D4DisclosureVariant, string>

// 底稿披露 sheet 真实 tab 名（🔴 D4 为全角括号，见 workpaper_sheet_classification wp_code=D4-*；
// 与 D7 半角括号不同，错一字符 GtWpRenderer ?sheet= 精确匹配失败会回退底稿目录）。
export const D4_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息（上市公司）',
  soe: '附注披露信息（国企）',
} as const satisfies Record<D4DisclosureVariant, string>

export function resolveD4CurrentStandard(
  variant: D4DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
): string {
  const list = (applicableStandards || []).map((s) => String(s).toLowerCase())
  if (variant === 'listed') {
    if (list.some((s) => s === 'listed_consolidated' || (s.includes('listed') && s.includes('consol')))) {
      return 'listed_consolidated'
    }
    return 'listed_standalone'
  }
  if (list.some((s) => s === 'soe_consolidated' || (s.includes('soe') && s.includes('consol')))) {
    return 'soe_consolidated'
  }
  return 'soe_standalone'
}

// ─── 表名（逐字取自附注模板 五、62 / 八、64）────────────────────────────────
const T = {
  listed: {
    main: '营业收入和营业成本',
    industry: '营业收入、营业成本按行业（或产品类型）划分',
    region: '营业收入、营业成本按地区划分',
    timing: '营业收入、营业成本按商品转让时间划分',
  },
  soe: {
    main: '营业收入、营业成本',
    industry: '按行业（或产品类型）划分',
    region: '营业收入、营业成本按地区划分',
    timing: '营业收入、营业成本按商品转让时间划分',
  },
} as const

const AMT = 'amount' as const

// ─── 列头元数据（列头对齐披露组件既有 el-table-column，收入/成本多级表头拍平为组合列名）──
const MAIN_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '项目', is_label: true },
  { key: 'current_revenue', label: '本期收入', format: AMT },
  { key: 'current_cost', label: '本期成本', format: AMT },
  { key: 'prior_revenue', label: '上期收入', format: AMT },
  { key: 'prior_cost', label: '上期成本', format: AMT },
]
const INDUSTRY_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '主要产品类型（或行业）', is_label: true },
  { key: 'current_revenue', label: '本期收入', format: AMT },
  { key: 'current_cost', label: '本期成本', format: AMT },
]
const REGION_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '主要经营地区', is_label: true },
  { key: 'current_revenue', label: '本期收入', format: AMT },
  { key: 'current_cost', label: '本期成本', format: AMT },
]
const TIMING_COLUMNS_LISTED: ColumnDef[] = [
  { key: 'label', label: '项目', is_label: true },
  { key: 'current_revenue', label: '本期收入', format: AMT },
  { key: 'current_cost', label: '本期成本', format: AMT },
]
const TIMING_COLUMNS_SOE: ColumnDef[] = [
  { key: 'label', label: '合同分类/报告分部', is_label: true },
  { key: 'current_revenue', label: '本期收入', format: AMT },
  { key: 'current_cost', label: '本期成本', format: AMT },
]

// ─── 快照行类型（组件层传入，字段与 useD4Disclosure 行接口对齐）────────────────
/** 主表行（section1Data / section1Total：category + 收入/成本 各本期/上期） */
export interface D4RevenueRowLike {
  label: string
  currentRevenue: number
  currentCost: number
  priorRevenue: number
  priorCost: number
}
/** 按行业/地区/时段行（本期收入 + 本期成本两列） */
export interface D4TwoColRowLike {
  label: string
  currentRevenue: number
  currentCost: number
}

export interface D4DisclosureSnapshot {
  /** section1Data（主营业务/其他业务，不含合计） */
  revenueRows: D4RevenueRowLike[]
  /** section1Total（合计行） */
  revenueTotal: D4RevenueRowLike
  /** section2（按行业/产品类型划分，动态行） */
  industryRows: D4TwoColRowLike[]
  /** section3（按地区划分，动态行） */
  regionRows: D4TwoColRowLike[]
  /** section4（按商品转让时间 / 分解信息，动态行） */
  timingRows: D4TwoColRowLike[]
  /** 各子节说明文本（note-1..note-8），与披露表文本框保持一致后同步到附注 text_content */
  notes: Record<string, string>
}

export interface D4SyncPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  current_standard: string
  sub_table_data: Record<string, unknown>
  columns: Record<string, ColumnDef[]>
}

type NullableAmount = number | null

const num = (v: unknown): number => (typeof v === 'number' && Number.isFinite(v) ? v : 0)
const str = (v: unknown): string => String(v ?? '')
const toN = (v: unknown): NullableAmount => (typeof v === 'number' && Number.isFinite(v) ? v : null)

/** 可空求和：全为 null 时返回 null（不塌成 0）。 */
function sumNullable(vals: readonly NullableAmount[]): NullableAmount {
  let has = false
  let total = 0
  for (const v of vals) {
    if (v === null || v === undefined) continue
    has = true
    total += v
  }
  return has ? Math.round(total * 100) / 100 : null
}

/**
 * 构建 D4 → 附注 sync-from-workpaper 载荷。
 * 上市：五、62；国企：八、64。均推送 4 张结构化子表 + note 文本。
 */
export function buildD4SyncPayload(
  variant: D4DisclosureVariant,
  wpId: string,
  applicableStandards: readonly string[] | null | undefined,
  snapshot: D4DisclosureSnapshot,
): D4SyncPayload {
  const isSoe = variant === 'soe'
  const names = isSoe ? T.soe : T.listed
  const sub: Record<string, unknown> = {}
  const columns: Record<string, ColumnDef[]> = {}
  const put = (name: string, rows: unknown, cols: ColumnDef[]) => {
    sub[name] = rows
    columns[name] = cols
  }

  // ① 营业收入和营业成本主表（明细 + 合计）
  const mainRow = (r: D4RevenueRowLike, isTotal = false) => ({
    label: str(r.label),
    current_revenue: num(r.currentRevenue),
    current_cost: num(r.currentCost),
    prior_revenue: num(r.priorRevenue),
    prior_cost: num(r.priorCost),
    ...(isTotal ? { is_total: true } : {}),
  })
  put(
    names.main,
    [...snapshot.revenueRows.map((r) => mainRow(r)), mainRow(snapshot.revenueTotal, true)],
    MAIN_COLUMNS,
  )

  // ②③④ 两列表（按行业 / 按地区 / 按商品转让时间）—— 合计用 sumNullable（全空返 null 不塌 0）
  const twoColTable = (name: string, rows: D4TwoColRowLike[], cols: ColumnDef[]) => {
    put(
      name,
      [
        ...rows.map((r) => ({
          label: str(r.label),
          current_revenue: num(r.currentRevenue),
          current_cost: num(r.currentCost),
        })),
        {
          label: '合计',
          current_revenue: sumNullable(rows.map((r) => toN(r.currentRevenue))),
          current_cost: sumNullable(rows.map((r) => toN(r.currentCost))),
          is_total: true,
        },
      ],
      cols,
    )
  }
  twoColTable(names.industry, snapshot.industryRows ?? [], INDUSTRY_COLUMNS)
  twoColTable(names.region, snapshot.regionRows ?? [], REGION_COLUMNS)
  twoColTable(names.timing, snapshot.timingRows ?? [], isSoe ? TIMING_COLUMNS_SOE : TIMING_COLUMNS_LISTED)

  // ⑤ 文本框内容
  sub._note_texts = buildD4NoteTexts(variant, snapshot.notes)

  return {
    wp_id: wpId,
    sheet_name: D4_DISCLOSURE_SHEET_NAME[variant],
    section_id: D4_NOTE_SECTION[variant],
    current_standard: resolveD4CurrentStandard(variant, applicableStandards),
    sub_table_data: sub,
    columns,
  }
}

/**
 * 说明文本子节（key = useD4Disclosure 的 note-N；标题与披露表子节一致）。
 * 上市 8 节（含试运行销售收入 note-8）/ 国企 7 节。
 */
export const D4_NOTE_TEXT_SECTIONS: Record<D4DisclosureVariant, Array<{ key: string; title: string }>> = {
  listed: [
    { key: 'note-1', title: '营业收入和营业成本说明' },
    { key: 'note-2', title: '按行业（或产品类型）划分说明' },
    { key: 'note-3', title: '按地区划分说明' },
    { key: 'note-4', title: '收入分解信息说明' },
    { key: 'note-5', title: '履约义务的说明' },
    { key: 'note-6', title: '与剩余履约义务有关的信息' },
    { key: 'note-7', title: '重大合同变更说明' },
    { key: 'note-8', title: '试运行销售收入说明' },
  ],
  soe: [
    { key: 'note-1', title: '营业收入、营业成本说明' },
    { key: 'note-2', title: '按行业（或产品类型）划分说明' },
    { key: 'note-3', title: '按地区划分说明' },
    { key: 'note-4', title: '收入分解信息说明' },
    { key: 'note-5', title: '履约义务相关信息' },
    { key: 'note-6', title: '与剩余履约义务有关的信息' },
    { key: 'note-7', title: '重大合同变更说明' },
  ],
}

/** 各子节说明 → _note_texts（仅非空），保证附注 text_content 与披露表文本框一致。 */
export function buildD4NoteTexts(
  variant: D4DisclosureVariant,
  notes: Record<string, string>,
): Array<{ section: string; title: string; text: string }> {
  const out: Array<{ section: string; title: string; text: string }> = []
  for (const { key, title } of D4_NOTE_TEXT_SECTIONS[variant]) {
    const text = String(notes?.[key] ?? '').trim()
    if (text) out.push({ section: `${variant}-${key}`, title, text })
  }
  return out
}
