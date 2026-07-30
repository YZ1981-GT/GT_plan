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
import {
  buildDisclosureSubtotal,
  type J1DisclosureRow,
} from '@/composables/workpaper/j1/j1DisclosureRowModel'
import { defineColumns, type ColumnDef } from './disclosureColumnDefs'

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
//
// 🔴 `flat: true` 必需：本表 5 列是**单行表头**（附注模板 J1 三张表 headers 均为一行），
//    但「本期增加」「本期减少」共享前缀「本期」→ 后端 `_infer_groups_from_headers`
//    会反猜出一个源模板**不存在**的「本期」父表头（与 F2 房企 3 表同款缺陷，
//    spec disclosure-columns-coverage-rollout R3.1/R3.4）。标在标签列即对整表生效。
//
// 列定义收敛到共享 `disclosureColumnDefs.ColumnDef`（原本地 interface 无 `flat`/`format`
// 字段，无法表达单级声明与金额格式；经查无任何消费方 import 该本地类型）。

export function j1MovementColumns(): ColumnDef[] {
  return defineColumns([
    { key: '项目', label: '项目', is_label: true, flat: true },
    { key: '期初余额', label: '期初余额', format: 'amount' },
    { key: '本期增加', label: '本期增加', format: 'amount' },
    { key: '本期减少', label: '本期减少', format: 'amount' },
    { key: '期末余额', label: '期末余额', format: 'amount' },
  ])
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

/**
 * 附注模板三张表的合计行字面 = `合计`（**无空格**）。
 *
 * 🔴 底稿 UI 用的是源模板字面「合 计」/「合  计」（中间带空格），
 * 直接外溢会让附注合计行与模板 `rows[].label` 漂移 —— 与 D3 的
 * `DISCLOSURE_TOTAL_LABEL`（`合 计`）不可全局硬套同款问题，按**本章节实证**取字面。
 */
export const J1_NOTE_TOTAL_LABEL = '合计'

/**
 * 补合计行。
 *
 * 🔴 P0 回归（2026-07-30 复盘）：组件传入的 `summaryData` / `shortTermData` /
 * `postEmploymentData` **都不含合计行**（合计在 composable 里是 computed），
 * 历史实现直接 `mapDisclosureRows(snapshot.summary)` → 同步后附注三张表**全缺合计行**。
 * 交付物缺合计行等于表没编完，故由载荷层统一补，组件不会漏。
 *
 * 合计口径复用 `buildDisclosureSubtotal`（只累加非缩进行），与 UI 显示的合计同源。
 */
function withTotalRow(rows: J1DisclosureRow[], id: string): J1DisclosureRow[] {
  // 防御：若上游已带合计行（历史脏数据 / 未来改动），先剔除再重算，避免双合计行
  const data = rows.filter((r) => !r.isSubtotal)
  const category = data.find((r) => r.category)?.category ?? ''
  return [...data, buildDisclosureSubtotal(id, J1_NOTE_TOTAL_LABEL, category, data)]
}

function mapDisclosureRows(rows: J1DisclosureRow[], totalId: string): J1SyncRow[] {
  return withTotalRow(rows, totalId).map((r) => ({
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
    [keys.summary]: mapDisclosureRows(snapshot.summary, 'summary-total'),
    [keys.shortTerm]: mapDisclosureRows(snapshot.shortTerm, 'short-term-total'),
    [keys.postEmployment]: mapDisclosureRows(snapshot.postEmployment, 'post-employment-total'),
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
