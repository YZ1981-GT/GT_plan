/**
 * j1NoteSectionMap — J1 应付职工薪酬 披露表↔附注模块 联动映射
 *
 * 权威来源（2026-07-26 Wave 0 核实）：
 *   - note_template_variant_matrix.json: ying_fu_zhi_gong_xin_chou → listed 五、40 / soe 八、40
 *   - workpaper_sheet_classification(wp_code=J1): 附注披露信息（上市公司）/ 附注披露信息（国有企业）
 *   - note_template_listed.json 五、40: 3 tables (应付职工薪酬/短期薪酬/设定提存计划)
 *   - note_template_soe.json 八、40: 3 tables (应付职工薪酬列示/短期薪酬列示/短期薪酬列示[重名])
 *
 * 允许偏离模板（Decision 3）：
 *   soe 第三张表模板 name 重复为「短期薪酬列示」（与第二张同名，模板笔误），
 *   Sub_Table_Key 改取 text_sections 章节标题「设定提存计划列示」，避免同名键覆盖丢表。
 *
 * 列头（Decision 2）：
 *   组件列头「上年年末数」不外溢到附注，columns label 一律用模板「期初余额」。
 *
 * Spec: .kiro/specs/j1-disclosure-note-linkage/
 */
import type { J1DisclosureRow } from '@/composables/workpaper/j1/useJ1DisclosureSections'

// ─── 常量（Wave 0 冻结） ──────────────────────────────────────────────────────

export type J1DisclosureVariant = 'listed' | 'soe'

/** 权威矩阵 ying_fu_zhi_gong_xin_chou */
export const J1_NOTE_SECTION = { listed: '五、40', soe: '八、40' } as const

/** workpaper_sheet_classification 实测值 */
export const J1_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息（上市公司）',
  soe: '附注披露信息（国有企业）',
} as const

/** 子表键（逐字取自模板 tables[].name；soe 第三张按 Decision 3 消歧） */
export const J1_SUB_TABLE_KEYS = {
  listed: { summary: '应付职工薪酬', shortTerm: '短期薪酬', postEmployment: '设定提存计划' },
  soe: { summary: '应付职工薪酬列示', shortTerm: '短期薪酬列示', postEmployment: '设定提存计划列示' },
} as const

/** 五列（两变体 headers 相同） */
export const J1_NOTE_HEADERS = ['项目', '期初余额', '本期增加', '本期减少', '期末余额'] as const

// ─── 列定义（供 columns 传参 + 投影器消费） ──────────────────────────────────

export interface ColumnDef {
  key: string
  label: string
  is_label?: boolean
}

export function j1MovementColumns(): ColumnDef[] {
  return [
    { key: '项目', label: '项目', is_label: true },
    { key: '期初余额', label: '期初余额' },
    { key: '本期增加', label: '本期增加' },
    { key: '本期减少', label: '本期减少' },
    { key: '期末余额', label: '期末余额' },
  ]
}

// ─── current_standard 解析 ───────────────────────────────────────────────────

const STANDARD_MAP: Record<string, string> = {
  listed: 'listed_standalone',
  soe: 'soe_standalone',
}

export function resolveJ1CurrentStandard(
  variant: J1DisclosureVariant,
  _applicableStandards?: readonly string[] | null,
): string {
  return STANDARD_MAP[variant] || 'soe_standalone'
}

// ─── 行映射 ──────────────────────────────────────────────────────────────────

export interface J1SyncRow {
  label: string
  values: (number | null)[]
  is_total?: boolean
}

/** 数值→null（空/NaN/Infinity→null，0 保留为 0） */
function nullableAmount(v: unknown): number | null {
  if (v === null || v === undefined) return null
  const n = Number(v)
  return Number.isFinite(n) ? n : null
}

function mapDisclosureRows(rows: J1DisclosureRow[]): J1SyncRow[] {
  return rows.map((r) => ({
    label: r.label || '',
    values: [
      nullableAmount(r.beginBalance),
      nullableAmount(r.increase),
      nullableAmount(r.decrease),
      nullableAmount(r.endBalance),
    ],
    is_total: r.isSubtotal || undefined,
  }))
}

// ─── 说明文本 ────────────────────────────────────────────────────────────────

export interface NoteText {
  section: string
  title: string
  text: string
}

const LISTED_NOTE_KEYS: Array<{ key: string; title: string }> = [
  { key: 'shortTerm', title: '短期薪酬说明' },
  { key: 'postEmployment', title: '设定提存计划说明' },
  { key: 'severance', title: '辞退福利说明' },
]

const SOE_NOTE_KEYS: Array<{ key: string; title: string }> = [
  { key: 'soe', title: '应付职工薪酬说明' },
]

export function buildJ1NoteTexts(
  variant: J1DisclosureVariant,
  notes: Record<string, string>,
): NoteText[] {
  const defs = variant === 'listed' ? LISTED_NOTE_KEYS : SOE_NOTE_KEYS
  return defs
    .filter((d) => (notes[d.key] ?? '').trim())
    .map((d) => ({ section: d.key, title: d.title, text: notes[d.key].trim() }))
}

// ─── 载荷构建器 ──────────────────────────────────────────────────────────────

export interface J1DisclosureSnapshot {
  summary: J1DisclosureRow[]
  shortTerm: J1DisclosureRow[]
  postEmployment: J1DisclosureRow[]
  notes: Record<string, string>
}

export function buildJ1SyncPayload(args: {
  variant: J1DisclosureVariant
  wpId: string
  year: number | string
  snapshot: J1DisclosureSnapshot
  applicableStandards?: readonly string[] | null
}): { section: string; body: Record<string, unknown> } {
  const { variant, wpId, year, snapshot, applicableStandards } = args
  const keys = J1_SUB_TABLE_KEYS[variant]
  const cols = j1MovementColumns()

  const sub_table_data: Record<string, unknown> = {
    [keys.summary]: mapDisclosureRows(snapshot.summary),
    [keys.shortTerm]: mapDisclosureRows(snapshot.shortTerm),
    [keys.postEmployment]: mapDisclosureRows(snapshot.postEmployment),
    _note_texts: buildJ1NoteTexts(variant, snapshot.notes),
  }

  const columns: Record<string, ColumnDef[]> = {
    [keys.summary]: cols,
    [keys.shortTerm]: cols,
    [keys.postEmployment]: cols,
  }

  return {
    section: J1_NOTE_SECTION[variant],
    body: {
      wp_id: wpId,
      year: Number(year) || undefined,
      sheet_name: J1_DISCLOSURE_SHEET_NAME[variant],
      section_id: J1_NOTE_SECTION[variant],
      current_standard: resolveJ1CurrentStandard(variant, applicableStandards),
      sub_table_data,
      columns,
    },
  }
}
