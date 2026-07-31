/**
 * j1NoteSectionMap — J1 应付职工薪酬 披露表↔附注模块 联动映射
 *
 * 权威来源（2026-07-26 Wave 0 核实）：
 *   - note_template_variant_matrix.json: ying_fu_zhi_gong_xin_chou → listed 五、40 / soe 八、40
 *   - workpaper_sheet_classification(wp_code=J1): 附注披露信息（上市公司）/ 附注披露信息（国有企业）
 *   - note_template_listed.json 五、40: 3 tables (应付职工薪酬/短期薪酬/设定提存计划)
 *   - note_template_soe.json 八、40: 3 tables (应付职工薪酬列示/短期薪酬列示/短期薪酬列示[重名])
 *
 * ✅ 原 Decision 3 已撤销（2026-07-30，`j1-disclosure-template-alignment` Task 1.2）：
 *   soe 第 3 张表模板 name 原重复为「短期薪酬列示」（与第 2 张同名），当时的处置是
 *   "允许偏离模板，Sub_Table_Key 取 text_sections 章节标题「设定提存计划列示」"——
 *   这是绕行而非修复：前端推的键在模板里**根本不存在** → 孤儿子表（未同步项目的 seed
 *   `_tables` 里是两张同名表，附注 TAB 页签重复且按 name 建键互相覆盖；契约 P1 必失败）。
 *   现已改模板（`fix_note_j1_employee_comp_structure.py`，`consol_note_sections_soe`
 *   五-41-3 的 title 即「设定提存计划列示」，是致同原本措辞）→ 前端键不变即自动对齐。
 *
 * 列头（Decision 2，仍有效）：
 *   组件列头「上年年末数 / 期末数」（上市源模板口径）不外溢到附注，
 *   columns label 一律用附注交付口径「期初余额 / 期末余额」。
 *
 * Spec: .kiro/specs/j1-disclosure-template-alignment/（前身 j1-disclosure-note-linkage）
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

export interface J1NoteFieldDef {
  /** 持久化键（`J1-disc-{variant}-notes` 里的字段名） */
  key: string
  /** 推给附注 `_note_texts` 的小节标题，也用作底稿文本域标签 */
  title: string
  /** 底稿文本域 placeholder（源模板说明段原文，不得改写） */
  placeholder: string
}

/** 上市侧 3 段说明（源 xlsx R37 / R38 / R50 / R53；前两条合为「短期薪酬说明」一域） */
export const J1_LISTED_NOTE_FIELDS: readonly J1NoteFieldDef[] = [
  {
    key: 'shortTerm',
    title: '短期薪酬说明',
    placeholder:
      '1、（企业本期为职工提供的各项非货币性福利形式、其计算依据。）\n' +
      '2、（企业依据短期利润分享计划提供的职工薪酬计算依据。）',
  },
  {
    key: 'postEmployment',
    title: '设定提存计划说明',
    placeholder: '（设定提存计划的性质、计算缴费金额的公式或依据）',
  },
  { key: 'severance', title: '辞退福利说明', placeholder: '辞退福利的性质、内容及计算依据。' },
]

/**
 * 国企侧 3 段说明（源 xlsx R42 / R43 / R44 **逐字**）。
 *
 * 🔴 历史实现只有 1 段 `soe`（单一 textarea），且第 3 条 placeholder 被截断改写，
 * 丢了「及其变动、对未来现金流的影响、重大精算假设及有关敏感性分析等」。
 * 交叉引用按实证指向 `八、54`（源 xlsx 写的 八、47 在平台现行编号里是
 * 「（3）一年内到期的长期应付款」，`八、54` 才是「长期应付职工薪酬」）。
 */
export const J1_SOE_NOTE_FIELDS: readonly J1NoteFieldDef[] = [
  {
    key: 'soeNonMonetary',
    title: '非货币性福利说明',
    placeholder: '1.企业本期为职工提供的各项非货币性福利的形式、金额及其计算依据。',
  },
  {
    key: 'soeDefinedContribution',
    title: '设定提存计划说明',
    placeholder: '2.企业应说明设立或参与的设定提存计划的性质、计算缴费金额的公式或依据。',
  },
  {
    key: 'soeDefinedBenefit',
    title: '设定受益计划说明',
    placeholder:
      '3.存在设定受益计划的企业，应说明设定受益计划的特征及与之相关的风险、' +
      '在财务报表中确认的金额及其变动、对未来现金流的影响、重大精算假设及有关敏感性分析等。' +
      '设定受益计划情况详见附注八、54「长期应付职工薪酬」。',
  },
]

export function j1NoteFields(variant: J1DisclosureVariant): readonly J1NoteFieldDef[] {
  return variant === 'listed' ? J1_LISTED_NOTE_FIELDS : J1_SOE_NOTE_FIELDS
}

/** 持久化键列表（传给 `useJ1DisclosureSections({ noteKeys })`） */
export function j1NoteKeys(variant: J1DisclosureVariant): string[] {
  return j1NoteFields(variant).map((d) => d.key)
}

export function buildJ1NoteTexts(
  variant: J1DisclosureVariant,
  notes: Record<string, string>,
): NoteText[] {
  return j1NoteFields(variant)
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
