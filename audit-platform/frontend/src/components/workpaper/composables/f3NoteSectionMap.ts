/**
 * F3 应付票据披露 ↔ 附注章节冻结映射与 sync payload 构建
 *
 * 权威来源：backend/data/note_template_variant_matrix.json → ying_fu_piao_ju
 *   listed_* → 五、36
 *   soe_*    → 八、36
 *
 * 附注模块（disclosure_notes）中「五、36 应付票据」的表结构为
 * 种类（商业承兑汇票/银行承兑汇票/合计）× 期末余额/上年年末余额，
 * 本模块 push 的 sub_table_data 与该结构一一对应，保证披露信息一致。
 */

export type F3DisclosureVariant = 'listed' | 'soe'

export const F3_NOTE_SECTION = {
  listed: '五、36',
  soe: '八、36',
} as const satisfies Record<F3DisclosureVariant, string>

export const F3_DISCLOSURE_SHEET_NAME = {
  listed: 'F3-note-listed',
  soe: 'F3-note-soe',
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

export interface F3SyncFromWorkpaperPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  current_standard: string
  sub_table_data: Record<string, Record<string, unknown>[]>
}

/**
 * 按附注模板行序（商业承兑汇票 → 银行承兑汇票）排序分类行；
 * 模板为固定两行，缺失的种类补 0 行，保证附注模块行结构始终与模板一致。
 */
export function orderF3ClassRows(rows: readonly F3NoteClassRow[]): F3NoteClassRow[] {
  const order = (label: string): number => {
    if (label.includes('商业承兑')) return 0
    if (label.includes('银行承兑')) return 1
    return 2
  }
  const merged: F3NoteClassRow[] = [...rows]
  for (const label of ['商业承兑汇票', '银行承兑汇票']) {
    if (!merged.some((r) => r.label.includes(label.slice(0, 4)))) {
      merged.push({ label, endAmount: 0, priorAmount: 0 })
    }
  }
  return merged.sort((a, b) => order(a.label) - order(b.label))
}

export function buildF3SyncPayload(
  variant: F3DisclosureVariant,
  wpId: string,
  applicableStandards: readonly string[] | null | undefined,
  classRows: readonly F3NoteClassRow[],
  total: F3NoteClassRow,
  noteText: string,
): F3SyncFromWorkpaperPayload {
  return {
    wp_id: wpId,
    sheet_name: F3_DISCLOSURE_SHEET_NAME[variant],
    section_id: F3_NOTE_SECTION[variant],
    current_standard: resolveF3CurrentStandard(variant, applicableStandards),
    sub_table_data: {
      应付票据: [
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
      _note_texts: [
        { section: `${variant}-note`, text: noteText },
      ],
    },
  }
}
