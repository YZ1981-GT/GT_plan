/**
 * F3 应付票据披露 ↔ 附注章节冻结映射与 sync payload 构建
 *
 * 权威来源：backend/data/note_template_variant_matrix.json → ying_fu_piao_ju
 *   listed_* → 五、36
 *   soe_*    → 八、36
 *
 * 表结构逐格取自运行时权威源 `backend/wp_templates/F/F3 应付票据.xlsx`：
 *
 * | sheet                  | A6   | B6     | C6         | 行序                        |
 * |------------------------|------|--------|------------|-----------------------------|
 * | 附注披露信息(上市公司) | 种类 | 期末余额 | 上年年末余额 | r7 银行承兑 → r8 商业承兑 → 合计 |
 * | 附注披露信息(国企)     | 类别 | 期末余额 | 期初余额   | 同上                        |
 *
 * 🔴 两变体的**标签列与第 3 列 label 不同**（种类/类别、上年年末余额/期初余额）：
 * 曾只有一份上市口径的 `F3_YFPJ_COLUMNS` 给两变体共用 → 国企项目同步后附注表头
 * 显示上市口径（3 列错 2 列）。字段 key 保持不变（`prior_amount`），只有 label 分变体。
 */

export type F3DisclosureVariant = 'listed' | 'soe'

export const F3_NOTE_SECTION = {
  listed: '五、36',
  soe: '八、36',
} as const satisfies Record<F3DisclosureVariant, string>

export const F3_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息(上市公司)',
  soe: '附注披露信息(国企)',
} as const satisfies Record<F3DisclosureVariant, string>

export function resolveF3CurrentStandard(
  variant: F3DisclosureVariant,
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

export interface F3NoteClassRow {
  label: string
  endAmount: number
  priorAmount: number
}

import type { ColumnDef } from './disclosureColumnDefs'

export interface F3SyncFromWorkpaperPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  current_standard: string
  sub_table_data: Record<string, Record<string, unknown>[]>
  /** 列头元数据（disclosure-table-sync-convergence）：label 取自 F3 披露组件既有 el-table-column */
  columns?: Record<string, ColumnDef[]>
}

/**
 * 子表名 ↔ note_template `tables[].name` 逐字映射。
 * 两变体表名相同（都叫「应付票据」），仍分开声明以便契约测试按变体校验。
 */
export const F3_LISTED_SUBTABLE = { notesPayable: '应付票据' } as const
export const F3_SOE_SUBTABLE = { notesPayable: '应付票据' } as const

/** 上市列头（源 xlsx 上市 A6/B6/C6）。`flat` = 源模板单行表头，抑制后端前缀推断 */
export const F3_LISTED_YFPJ_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '种类', is_label: true, flat: true },
  { key: 'end_amount', label: '期末余额', format: 'amount' },
  { key: 'prior_amount', label: '上年年末余额', format: 'amount' },
]

/** 国企列头（源 xlsx 国企 A6/B6/C6）：标签列「类别」、第 3 列「期初余额」 */
export const F3_SOE_YFPJ_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '类别', is_label: true, flat: true },
  { key: 'end_amount', label: '期末余额', format: 'amount' },
  { key: 'prior_amount', label: '期初余额', format: 'amount' },
]

export const F3_YFPJ_COLUMNS_BY_VARIANT = {
  listed: F3_LISTED_YFPJ_COLUMNS,
  soe: F3_SOE_YFPJ_COLUMNS,
} as const satisfies Record<F3DisclosureVariant, ColumnDef[]>

export const F3_SUBTABLE_BY_VARIANT = {
  listed: F3_LISTED_SUBTABLE,
  soe: F3_SOE_SUBTABLE,
} as const satisfies Record<F3DisclosureVariant, { notesPayable: string }>

/** 源 xlsx 行序（r7 银行承兑汇票 → r8 商业承兑汇票），供应链票据列在其后 */
const F3_CLASS_ROW_ORDER = ['银行承兑汇票', '商业承兑汇票'] as const

/**
 * 按源模板行序（银行承兑汇票 → 商业承兑汇票 → 供应链票据）排序分类行；
 * 银行/商业两种始终列示，缺失的补 0 行，保证附注行结构与模板一致。
 *
 * 🔴 曾按「商业 → 银行」排序（与源 xlsx r7/r8 相反），已按源模板纠正。
 */
export function orderF3ClassRows(rows: readonly F3NoteClassRow[]): F3NoteClassRow[] {
  const order = (label: string): number => {
    if (label.includes('银行承兑')) return 0
    if (label.includes('商业承兑')) return 1
    if (label.includes('供应链')) return 2
    return 3
  }
  const merged: F3NoteClassRow[] = [...rows]
  // 供应链/其他仅在来源已提供时保留（不强制补零行）
  for (const label of F3_CLASS_ROW_ORDER) {
    if (!merged.some((r) => r.label.includes(label.slice(0, 4)))) {
      merged.push({ label, endAmount: 0, priorAmount: 0 })
    }
  }
  return merged.sort((a, b) => order(a.label) - order(b.label))
}

export interface F3NoteTextRow {
  section: string
  title: string
  text: string
}

/**
 * 说明文本 → `_note_texts`（后端 `_format_note_texts` 渲染为 `【title】\n正文`）。
 *
 * 🔴 `title` 必填中文：缺省时后端用 `section` 兜底，附注正文会出现
 * `【listed-note】` 这类英文键（违反 UI 全中文化）。空文本直接丢弃。
 *
 * title 取源：源 xlsx 上市 r10「说明：本期末已到期未支付的应付票据总额为XXX元。」/
 * 国企 r10「注：企业应说明本期已到期未支付的应付票据总金额。」
 */
export function buildF3NoteTexts(
  variant: F3DisclosureVariant,
  noteText: string,
): F3NoteTextRow[] {
  const body = String(noteText ?? '').trim()
  if (!body) return []
  return [{ section: `${variant}-note`, title: '已到期未支付的应付票据说明', text: body }]
}

export function buildF3SyncPayload(
  variant: F3DisclosureVariant,
  wpId: string,
  applicableStandards: readonly string[] | null | undefined,
  classRows: readonly F3NoteClassRow[],
  total: F3NoteClassRow,
  noteText: string,
): F3SyncFromWorkpaperPayload {
  const tableName = F3_SUBTABLE_BY_VARIANT[variant].notesPayable
  return {
    wp_id: wpId,
    sheet_name: F3_DISCLOSURE_SHEET_NAME[variant],
    section_id: F3_NOTE_SECTION[variant],
    current_standard: resolveF3CurrentStandard(variant, applicableStandards),
    sub_table_data: {
      [tableName]: [
        ...orderF3ClassRows(classRows).map((r) => ({
          label: r.label,
          end_amount: r.endAmount,
          prior_amount: r.priorAmount,
        })),
        {
          label: total.label || '合计',
          end_amount: total.endAmount,
          prior_amount: total.priorAmount,
          is_total: true,
        },
      ],
      _note_texts: buildF3NoteTexts(variant, noteText),
    },
    columns: { [tableName]: F3_YFPJ_COLUMNS_BY_VARIANT[variant] },
  }
}
