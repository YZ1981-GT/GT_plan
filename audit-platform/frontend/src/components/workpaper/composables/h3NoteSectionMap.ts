/**
 * H3 投资性房地产披露 ↔ 附注章节映射与 sync payload 构建
 *
 * 权威来源：
 * - 章节号 `backend/data/note_template_variant_matrix.json` · `tou_zi_xing_fang_di_chan`
 *   → 上市 `五、21` / 国企 **`八、21`**（🔴 曾误写 `八、22`，而 `八、22` 是**固定资产**章节
 *   → H3 国企披露一直推进固定资产章节。DB + variant_matrix 双证，断言里禁写 `八、22`）
 * - 表结构 `backend/wp_templates/H/H3 投资性房地产.xlsx` 两张披露 sheet（逐 sheet 精读）
 * - 附注模板 `note_template_{listed,soe}.json` §五、21 / §八、21
 *   （由 `backend/scripts/fix/fix_note_h3_investment_property_structure.py` 对齐）
 *
 * 结构要点：
 * - **上市是列转置结构**：列 = 资产类别（房屋、建筑物 / 土地使用权 / 在建工程 / 合计），
 *   行 = 变动层次明细（成本表四层 32 行 / 公允表 9 行）。单行表头 → `flat`。
 * - **国企是两级表头**：以成本计量 7 列（`本期增加{购置或计提, 自用房地产或存货转入}` /
 *   `本期减少{处 置, 转为自用房地产}`，期初/期末 rowspan=2 **不带 group**）；
 *   以公允价值计量 8 列（本期增加含 `公允价值变动损益`）。行 = 5 层 / 3 层，
 *   每层 1 合计行 + 2 类别行。
 *
 * 契约（后端权威，勿改形状）：
 * 1. `sub_table_data` 行必须是 **keyed dict**（键 = `columns[].key`）——
 *    `note_sub_table_projector.project_sub_tables` 按 `row.get(colDef.key)` 投影；
 *    位置化 `{label, values:[]}` 是非规范历史形态（本文件已弃用）。
 * 2. 叙述正文放 `sub_table_data._note_texts`（服务端 pop 后写 `text_content`），
 *    每条必须带中文 `title`（缺 title 会渲染成英文 section 键）。
 * 3. 子表键 = 模板 `tables[].name` 逐字，否则产孤儿子表（附注 TAB 永空）。
 */
import type { ColumnDef } from './disclosureColumnDefs'

export type H3DisclosureVariant = 'listed' | 'soe'
export type H3MeasurementModel = 'cost' | 'fair_value'

export const H3_NOTE_SECTION = {
  listed: '五、21',
  soe: '八、21',
} as const satisfies Record<H3DisclosureVariant, string>

export const H3_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息（上市公司）',
  soe: '附注披露信息（国有企业）',
} as const satisfies Record<H3DisclosureVariant, string>

/** 与 note_template_listed §五、21 tables[].name 逐字一致 */
export const H3_LISTED_SUBTABLE = {
  cost: '按成本计量的投资性房地产',
  fair: '按公允价值计量的投资性房地产',
  title: '未办妥产权证书的情况',
} as const

/** 与 note_template_soe §八、21 tables[].name 逐字一致 */
export const H3_SOE_SUBTABLE = {
  cost: '以成本计量',
  fair: '以公允价值计量',
  title: '未办妥产权证书的投资性房地产',
} as const

/**
 * 历史孤儿表名（旧载荷自造名 + 国企第 3 表曾与第 2 表重名）。
 * 同步时经 `_removed_table_keys` 清理，避免附注永久残留空表。
 */
export const H3_LEGACY_OBSOLETE_TABLES: readonly string[] = [
  '以成本模式计量的投资性房地产（账面原值）',
  '以成本模式计量的投资性房地产（累计折旧和累计摊销）',
  '以成本模式计量的投资性房地产（减值准备）',
  '以公允价值模式计量的投资性房地产',
  '投资性房地产（账面原值）',
  '投资性房地产（累计折旧和累计摊销）',
  '投资性房地产（减值准备）',
  '投资性房地产（公允价值模式）',
]

/** 上市资产类别列（源 xlsx 行 8 / 行 53） */
export const H3_LISTED_CATEGORIES = ['房屋、建筑物', '土地使用权', '在建工程'] as const
export const H3_TOTAL_LABEL = '合计'

/** 国企类别行（源 xlsx 每层下辖两类） */
export const H3_SOE_CATEGORIES = ['房屋、建筑物', '土地使用权'] as const

// ─── 列定义 ──────────────────────────────────────────────────────────────────

/** 上市列转置：标签列 + 资产类别 + 合计（单行表头 → flat 标在标签列即对整表生效） */
function listedTransposedColumns(): ColumnDef[] {
  return [
    { key: 'label', label: '项目', is_label: true, flat: true },
    ...H3_LISTED_CATEGORIES.map((c) => ({ key: c, label: c, format: 'amount' as const })),
    { key: H3_TOTAL_LABEL, label: H3_TOTAL_LABEL, format: 'amount' as const },
  ]
}

const H3_LISTED_TITLE_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '项目', is_label: true, flat: true },
  { key: 'book_value', label: '账面价值', format: 'amount' },
  { key: 'reason', label: '未办妥产权证书原因' },
]

/** 国企以成本计量：7 列两级（期初/期末 rowspan=2 不带 group） */
const H3_SOE_COST_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '项目', is_label: true },
  { key: 'begin', label: '期初余额', format: 'amount' },
  { key: 'buy_or_provision', label: '购置或计提', group: '本期增加', format: 'amount' },
  { key: 'transfer_in', label: '自用房地产或存货转入', group: '本期增加', format: 'amount' },
  { key: 'disposal', label: '处 置', group: '本期减少', format: 'amount' },
  { key: 'transfer_out', label: '转为自用房地产', group: '本期减少', format: 'amount' },
  { key: 'end', label: '期末余额', format: 'amount' },
]

/** 国企以公允价值计量：8 列两级（本期增加含公允价值变动损益） */
const H3_SOE_FAIR_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '项目', is_label: true },
  { key: 'begin_fair', label: '期初公允价值', format: 'amount' },
  { key: 'buy', label: '购置', group: '本期增加', format: 'amount' },
  { key: 'transfer_in', label: '自用房地产或存货转入', group: '本期增加', format: 'amount' },
  { key: 'fair_change_pl', label: '公允价值变动损益', group: '本期增加', format: 'amount' },
  { key: 'disposal', label: '处 置', group: '本期减少', format: 'amount' },
  { key: 'transfer_out', label: '转为自用房地产', group: '本期减少', format: 'amount' },
  { key: 'end_fair', label: '期末公允价值', format: 'amount' },
]

const H3_SOE_TITLE_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '项目', is_label: true, flat: true },
  { key: 'book_value', label: '账面价值', format: 'amount' },
  { key: 'reason', label: '原因' },
]

/** 上市 3 张子表列头（键 = 模板 tables[].name） */
export function buildH3ListedColumns(): Record<string, ColumnDef[]> {
  return {
    [H3_LISTED_SUBTABLE.cost]: listedTransposedColumns(),
    [H3_LISTED_SUBTABLE.fair]: listedTransposedColumns(),
    [H3_LISTED_SUBTABLE.title]: H3_LISTED_TITLE_COLUMNS,
  }
}

/** 国企 3 张子表列头（键 = 模板 tables[].name） */
export function buildH3SoeColumns(): Record<string, ColumnDef[]> {
  return {
    [H3_SOE_SUBTABLE.cost]: H3_SOE_COST_COLUMNS,
    [H3_SOE_SUBTABLE.fair]: H3_SOE_FAIR_COLUMNS,
    [H3_SOE_SUBTABLE.title]: H3_SOE_TITLE_COLUMNS,
  }
}

// ─── 组件行模型 ──────────────────────────────────────────────────────────────

/**
 * 披露 Tab 的一行（`useH3Disclosure.getSectionRows(key)` 产出）。
 *
 * `buyOrProvision` / `transferIn` / `disposal` / `transferOut` 是源模板国企两级子列，
 * 底稿尚未提供独立录入位置时为 `undefined` → 载荷退化为把聚合 `increase` 归入
 * **主渠道** `购置或计提`、`decrease` 归入 `处 置`（源模板该列即主增减渠道），
 * 并保持期末派生自洽；待底稿补齐子列录入后自动改用细分值（见 spec Task 10）。
 */
export interface H3DisclosureRow {
  rowId?: string
  category?: string
  beginBalance?: number
  increase?: number
  decrease?: number
  fairChange?: number
  buyOrProvision?: number
  transferIn?: number
  disposal?: number
  transferOut?: number
  bookValue?: number
  reason?: string
  /** 未办妥产权证书原因 —— 底稿「未办妥产权证书」区块历史用 `usage` 承载原因列 */
  usage?: string
  [k: string]: unknown
}

function num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

/** 该行是否有任何实质内容（全空行不推送，避免造空披露行） */
function isMeaningfulRow(r: H3DisclosureRow): boolean {
  if (String(r.category || '').trim()) return true
  if (String(r.reason || r.usage || '').trim()) return true
  return ['beginBalance', 'increase', 'decrease', 'fairChange', 'bookValue']
    .some((k) => num(r[k]) !== 0)
}

interface Movement {
  begin: number
  increase: number
  decrease: number
  fairChange: number
  buyOrProvision: number
  transferIn: number
  disposal: number
  transferOut: number
}

const ZERO: Movement = {
  begin: 0, increase: 0, decrease: 0, fairChange: 0,
  buyOrProvision: 0, transferIn: 0, disposal: 0, transferOut: 0,
}

function toMovement(r: H3DisclosureRow): Movement {
  const increase = num(r.increase)
  const decrease = num(r.decrease)
  return {
    begin: num(r.beginBalance),
    increase,
    decrease,
    fairChange: num(r.fairChange),
    // 未提供细分子列时，聚合额归入源模板的主增减渠道（购置或计提 / 处 置）
    buyOrProvision: r.buyOrProvision === undefined ? increase : num(r.buyOrProvision),
    transferIn: num(r.transferIn),
    disposal: r.disposal === undefined ? decrease : num(r.disposal),
    transferOut: num(r.transferOut),
  }
}

function addMovement(a: Movement, b: Movement): Movement {
  return {
    begin: a.begin + b.begin,
    increase: a.increase + b.increase,
    decrease: a.decrease + b.decrease,
    fairChange: a.fairChange + b.fairChange,
    buyOrProvision: a.buyOrProvision + b.buyOrProvision,
    transferIn: a.transferIn + b.transferIn,
    disposal: a.disposal + b.disposal,
    transferOut: a.transferOut + b.transferOut,
  }
}

const movEnd = (m: Movement): number => m.begin + m.increase - m.decrease
const movEndFair = (m: Movement): number => m.begin + m.increase - m.decrease + m.fairChange

/** 按类别名归集组件行；`合计` 为全部行之和（不依赖用户是否录了「合计」行） */
function indexByCategory(rows: readonly H3DisclosureRow[] | undefined): {
  byCat: Map<string, Movement>
  total: Movement
} {
  const byCat = new Map<string, Movement>()
  let total = { ...ZERO }
  for (const r of rows || []) {
    if (!isMeaningfulRow(r)) continue
    const cat = String(r.category || '').trim()
    // 用户自录的「合计」行不重复计入（合计由明细派生）
    if (cat === H3_TOTAL_LABEL || cat === '合 计') continue
    const m = toMovement(r)
    byCat.set(cat, addMovement(byCat.get(cat) || { ...ZERO }, m))
    total = addMovement(total, m)
  }
  return { byCat, total }
}

// ─── 上市：列转置行构造 ───────────────────────────────────────────────────────

type CellPicker = (m: Movement) => number | null

/** 一行 = 标签 + 各类别列取值（含合计列）；全 null 的行只出标签（保结构不造数） */
function transposedRow(
  label: string,
  idx: { byCat: Map<string, Movement>; total: Movement } | null,
  pick: CellPicker | null,
  extra: Record<string, unknown> = {},
): Record<string, unknown> {
  const row: Record<string, unknown> = { label, ...extra }
  for (const cat of H3_LISTED_CATEGORIES) {
    row[cat] = idx && pick ? pick(idx.byCat.get(cat) || { ...ZERO }) : null
  }
  row[H3_TOTAL_LABEL] = idx && pick ? pick(idx.total) : null
  return row
}

/** 上市成本表 32 行（与模板 rows 逐字对齐；无录入位置的明细项留 null，不造数） */
function buildListedCostRows(
  original: readonly H3DisclosureRow[] | undefined,
  dep: readonly H3DisclosureRow[] | undefined,
  impair: readonly H3DisclosureRow[] | undefined,
): Record<string, unknown>[] {
  const o = indexByCategory(original)
  const d = indexByCategory(dep)
  const p = indexByCategory(impair)
  const layer = (
    idx: typeof o,
    header: string,
    detailLabels: readonly string[],
    decreaseLabel: string,
  ): Record<string, unknown>[] => [
    transposedRow(header, null, null),
    transposedRow('1.期初余额', idx, (m) => m.begin),
    transposedRow('2.本期增加金额', idx, (m) => m.increase),
    ...detailLabels.map((l) => transposedRow(l, null, null)),
    transposedRow(decreaseLabel, idx, (m) => m.decrease),
    transposedRow('（1）处置', null, null),
    transposedRow('（2）其他转出', null, null),
    transposedRow('4.期末余额', idx, movEnd),
  ]
  return [
    ...layer(o, '一、账面原值', ['（1）外购', '（2）存货\\固定资产\\在建工程转入', '（3）企业合并增加'], '3.本期减少金额'),
    ...layer(d, '二、累计折旧和累计摊销', ['（1）计提或摊销', '（2）企业合并增加', '（3）其他增加'], '3.本期减少金额'),
    // 源模板此层为顿号书写「3、本期减少金额」（其余层为「3.」），保持源模板字面
    ...layer(p, '三、减值准备', ['（1）计提', '（2）其他增加'], '3、本期减少金额'),
    transposedRow('四、账面价值', null, null),
    transposedRow('1.期末账面价值', null, null, carryingCells(o, d, p, 'end')),
    transposedRow('2.期初账面价值', null, null, carryingCells(o, d, p, 'begin')),
  ]
}

/** 账面价值 = 账面原值 − 累计折旧和累计摊销 − 减值准备（逐类别 + 合计） */
function carryingCells(
  o: { byCat: Map<string, Movement>; total: Movement },
  d: { byCat: Map<string, Movement>; total: Movement },
  p: { byCat: Map<string, Movement>; total: Movement },
  at: 'begin' | 'end',
): Record<string, unknown> {
  const val = (m: Movement) => (at === 'end' ? movEnd(m) : m.begin)
  const cells: Record<string, unknown> = {}
  for (const cat of H3_LISTED_CATEGORIES) {
    const g = (x: typeof o) => val(x.byCat.get(cat) || { ...ZERO })
    cells[cat] = g(o) - g(d) - g(p)
  }
  cells[H3_TOTAL_LABEL] = val(o.total) - val(d.total) - val(p.total)
  return cells
}

/** 上市公允价值表 9 行 */
function buildListedFairRows(fair: readonly H3DisclosureRow[] | undefined): Record<string, unknown>[] {
  const f = indexByCategory(fair)
  return [
    transposedRow('一、期初余额', f, (m) => m.begin),
    transposedRow('二、本期变动', f, (m) => m.increase - m.decrease + m.fairChange),
    transposedRow('加：外购', null, null),
    transposedRow('存货\\固定资产\\在建工程转入', null, null),
    transposedRow('企业合并增加', null, null),
    transposedRow('减：处置', null, null),
    transposedRow('其他转出', null, null),
    transposedRow('公允价值变动', f, (m) => m.fairChange),
    transposedRow('三、期末余额', f, movEndFair),
  ]
}

/** 未办妥产权证书表（两版共用行构造，列 key 相同） */
function buildTitleRows(rows: readonly H3DisclosureRow[] | undefined, withTotal: boolean): Record<string, unknown>[] {
  const out: Record<string, unknown>[] = []
  let total = 0
  for (const r of rows || []) {
    if (!isMeaningfulRow(r)) continue
    const cat = String(r.category || '').trim()
    if (cat === H3_TOTAL_LABEL || cat === '合 计') continue
    const bv = num(r.bookValue ?? r.beginBalance)
    // 原因列：底稿该区块用 `usage` 承载（`reason` 为通用回退），两者都认
    out.push({ label: cat, book_value: bv, reason: String(r.reason || r.usage || '') })
    total += bv
  }
  if (out.length && withTotal) {
    out.push({ label: H3_TOTAL_LABEL, book_value: total, reason: '', is_total: true })
  }
  return out
}

// ─── 国企：分层行构造 ────────────────────────────────────────────────────────

function soeLayerRows(
  layerLabel: string,
  idx: { byCat: Map<string, Movement>; total: Movement },
  opts: { whichPrefix: boolean; fair: boolean },
): Record<string, unknown>[] {
  const cell = (m: Movement): Record<string, unknown> => opts.fair
    ? {
      begin_fair: m.begin,
      buy: m.buyOrProvision,
      transfer_in: m.transferIn,
      fair_change_pl: m.fairChange,
      disposal: m.disposal,
      transfer_out: m.transferOut,
      end_fair: movEndFair(m),
    }
    : {
      begin: m.begin,
      buy_or_provision: m.buyOrProvision,
      transfer_in: m.transferIn,
      disposal: m.disposal,
      transfer_out: m.transferOut,
      end: movEnd(m),
    }
  const rows: Record<string, unknown>[] = [
    { label: layerLabel, is_total: true, ...cell(idx.total) },
  ]
  H3_SOE_CATEGORIES.forEach((cat, i) => {
    const label = opts.whichPrefix && i === 0
      ? `其中：1、${cat}`
      : `${i + 1}、${cat}`
    rows.push({ label, ...cell(idx.byCat.get(cat) || { ...ZERO }) })
  })
  return rows
}

/** 差集（净值/账面价值层由派生得出） */
function diffIndex(
  a: { byCat: Map<string, Movement>; total: Movement },
  b: { byCat: Map<string, Movement>; total: Movement },
): { byCat: Map<string, Movement>; total: Movement } {
  const sub = (x: Movement, y: Movement): Movement => ({
    begin: x.begin - y.begin,
    increase: x.increase - y.increase,
    decrease: x.decrease - y.decrease,
    fairChange: x.fairChange - y.fairChange,
    buyOrProvision: x.buyOrProvision - y.buyOrProvision,
    transferIn: x.transferIn - y.transferIn,
    disposal: x.disposal - y.disposal,
    transferOut: x.transferOut - y.transferOut,
  })
  const byCat = new Map<string, Movement>()
  for (const cat of H3_SOE_CATEGORIES) {
    byCat.set(cat, sub(a.byCat.get(cat) || { ...ZERO }, b.byCat.get(cat) || { ...ZERO }))
  }
  return { byCat, total: sub(a.total, b.total) }
}

// ─── buildH3SyncPayload ─────────────────────────────────────────────────────

export interface H3SyncPayloadOptions {
  variant: H3DisclosureVariant
  measurementModel: H3MeasurementModel
  /** 成本模式 — 账面原值变动行 */
  costOriginalRows?: readonly H3DisclosureRow[]
  /** 成本模式 — 累计折旧和累计摊销行 */
  costDepRows?: readonly H3DisclosureRow[]
  /** 成本模式 — 减值准备行 */
  costImpairRows?: readonly H3DisclosureRow[]
  /** 公允价值模式 — 公允价值变动行 */
  fairChangeRows?: readonly H3DisclosureRow[]
  /** 未办妥产权证书行（两种计量模式下均披露） */
  titleRows?: readonly H3DisclosureRow[]
  /** 各 section 说明文本（key→text） */
  sectionTexts?: Record<string, string>
  projectId: string
  wpId: string
}

export interface H3SyncFromWorkpaperPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  current_standard: string
  sub_table_data: Record<string, unknown>
  columns: Record<string, ColumnDef[]>
}

/** 说明文本 section → 中文标题（缺 title 会让附注正文渲染成英文键） */
const NOTE_TEXT_TITLES: Record<string, string> = {
  'cost-original': '按成本计量的投资性房地产说明',
  'cost-dep': '累计折旧和累计摊销说明',
  'cost-impair': '减值准备说明',
  'fair-change': '按公允价值计量的投资性房地产说明',
  'soe-cost': '以成本计量说明',
  'soe-cost-dep': '累计折旧和累计摊销说明',
  'soe-impair': '减值准备说明',
  'soe-fair-value': '以公允价值计量说明',
  'soe-fair-change': '公允价值变动说明',
  'soe-unlicensed': '未办妥产权证书的投资性房地产说明',
  'title-cert': '未办妥产权证书的情况说明',
  conversion: '房地产转换情况及改变计量模式的情况',
}

function buildNoteTexts(
  sectionTexts: Record<string, string>,
): Array<{ section: string; title: string; text: string }> {
  return Object.entries(sectionTexts)
    .filter(([, v]) => String(v || '').trim())
    .map(([key, text]) => ({
      section: key,
      title: NOTE_TEXT_TITLES[key] || key,
      text: String(text),
    }))
}

/**
 * 构建 H3 投资性房地产底稿 → 附注 sync payload。
 *
 * - 按计量模式二选一推表（成本 ↔ 公允价值），未选中模式的表名进 `_removed_table_keys`；
 * - 「未办妥产权证书」两模式均推；无行时不推空表且列入 `_removed_table_keys`
 *   （底稿有录入区块的条件表语义）；
 * - 历史孤儿表名一并清理。
 */
export function buildH3SyncPayload(opts: H3SyncPayloadOptions): H3SyncFromWorkpaperPayload {
  const { variant, measurementModel, sectionTexts = {} } = opts
  const names = variant === 'listed' ? H3_LISTED_SUBTABLE : H3_SOE_SUBTABLE
  const allColumns = variant === 'listed' ? buildH3ListedColumns() : buildH3SoeColumns()

  const sub_table_data: Record<string, unknown> = {}
  const columns: Record<string, ColumnDef[]> = {}
  const removed: string[] = [...H3_LEGACY_OBSOLETE_TABLES]

  const isCost = measurementModel === 'cost'

  if (isCost) {
    const rows = variant === 'listed'
      ? buildListedCostRows(opts.costOriginalRows, opts.costDepRows, opts.costImpairRows)
      : buildSoeCostRows(opts.costOriginalRows, opts.costDepRows, opts.costImpairRows)
    sub_table_data[names.cost] = rows
    columns[names.cost] = allColumns[names.cost]
    removed.push(names.fair)
  } else {
    const rows = variant === 'listed'
      ? buildListedFairRows(opts.fairChangeRows)
      : buildSoeFairRows(opts.fairChangeRows)
    sub_table_data[names.fair] = rows
    columns[names.fair] = allColumns[names.fair]
    removed.push(names.cost)
  }

  // 未办妥产权证书：条件表（有行才推；无行清理避免残留过时明细）
  const titleRows = buildTitleRows(opts.titleRows, variant === 'soe')
  if (titleRows.length) {
    sub_table_data[names.title] = titleRows
    columns[names.title] = allColumns[names.title]
  } else {
    removed.push(names.title)
  }

  const noteTexts = buildNoteTexts(sectionTexts)
  if (noteTexts.length) sub_table_data._note_texts = noteTexts
  sub_table_data._removed_table_keys = Array.from(new Set(removed))

  return {
    wp_id: opts.wpId,
    sheet_name: H3_DISCLOSURE_SHEET_NAME[variant],
    section_id: H3_NOTE_SECTION[variant],
    current_standard: variant === 'listed' ? 'listed_standalone' : 'soe_standalone',
    sub_table_data,
    columns,
  }
}

/** 国企成本表 15 行（5 层 × [合计 + 2 类别]；净值/账面价值层派生） */
function buildSoeCostRows(
  original: readonly H3DisclosureRow[] | undefined,
  dep: readonly H3DisclosureRow[] | undefined,
  impair: readonly H3DisclosureRow[] | undefined,
): Record<string, unknown>[] {
  const o = indexByCategory(original)
  const d = indexByCategory(dep)
  const p = indexByCategory(impair)
  const net = diffIndex(o, d)
  const carrying = diffIndex(net, p)
  const opt = { whichPrefix: false, fair: false }
  return [
    ...soeLayerRows('一、账面原值合计', o, opt),
    ...soeLayerRows('二、累计折旧和累计摊销合计', d, opt),
    ...soeLayerRows('三、投资性房地产账面净值合计', net, opt),
    ...soeLayerRows('四、投资性房地产减值准备累计金额合计', p, opt),
    ...soeLayerRows('五、投资性房地产账面价值合计', carrying, opt),
  ]
}

/** 国企公允价值表 9 行（3 层 × [合计 + 2 类别]；账面价值层 = 成本 + 公允价值变动） */
function buildSoeFairRows(
  fair: readonly H3DisclosureRow[] | undefined,
): Record<string, unknown>[] {
  const f = indexByCategory(fair)
  // 成本层 = 期初 + 增减（不含公允价值变动）；变动层 = 公允价值变动
  const costLayer: typeof f = {
    byCat: new Map([...f.byCat].map(([k, m]) => [k, { ...m, fairChange: 0 }])),
    total: { ...f.total, fairChange: 0 },
  }
  const changeLayer: typeof f = {
    byCat: new Map([...f.byCat].map(([k, m]) => [k, { ...ZERO, begin: 0, fairChange: m.fairChange }])),
    total: { ...ZERO, fairChange: f.total.fairChange },
  }
  const opt = { whichPrefix: true, fair: true }
  return [
    ...soeLayerRows('一、成本合计', costLayer, opt),
    ...soeLayerRows('二、公允价值变动合计', changeLayer, opt),
    ...soeLayerRows('三、投资性房地产账面价值合计', f, opt),
  ]
}
