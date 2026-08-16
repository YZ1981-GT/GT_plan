/**
 * l7NoteSectionMap — L7 其他非流动负债 披露表 ↔ 附注章节冻结映射
 *
 * 权威来源：
 * - `note_template_variant_matrix.json` · `qi_ta_fei_liu_dong_fu_zhai`
 *   → listed_standalone = 五、52 / soe_standalone = 八、57
 * - 源 xlsx `backend/wp_templates/L/L7 其他非流动负债.xlsx` 的
 *   `附注披露信息（上市公司）` / `附注披露信息(国企)`（**国企侧半角括号，源模板即如此**）
 * - 表名逐字 = `note_template_{listed,soe}.json` 的 `tables[].name` = 「其他非流动负债」
 *   （上市侧原为表头首格泄漏名 `项  目`，已由 `fix_note_l_cycle_structure.py` 正名）
 *
 * 🔴 国企侧列序 = 「期末余额 / 期初余额」（附注交付物口径），与**底稿录入界面**的
 * 「年初余额 / 期末余额」相反 —— 源 xlsx 国企 r6 是期初在前，但附注模板与上市侧
 * 都是期末在前。载荷层负责这一次投影，勿把底稿列序传导到附注。
 */
import { defineColumns, type ColumnDef } from './disclosureColumnDefs'

export type L7DisclosureVariant = 'listed' | 'soe'

export const L7_NOTE_SECTION = {
  listed: '五、52',
  soe: '八、57',
} as const satisfies Record<L7DisclosureVariant, string>

/** 源 xlsx 中文 tab 名（国企侧半角括号是源模板字面，勿"修正"为全角） */
export const L7_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息（上市公司）',
  soe: '附注披露信息(国企)',
} as const satisfies Record<L7DisclosureVariant, string>

/** 向后兼容的单值导出（`noteDisclosureJump` 等旧消费方） */
export const L7_DISCLOSURE_SHEET_LISTED = L7_DISCLOSURE_SHEET_NAME.listed
export const L7_DISCLOSURE_SHEET_SOE = L7_DISCLOSURE_SHEET_NAME.soe

/** 与 note_template `tables[].name` 逐字一致 */
export const L7_SUBTABLE = {
  main: '其他非流动负债',
} as const

/** 合计行字面 —— 取本章节模板实证值（两版都是无空格「合计」） */
export const L7_TOTAL_LABEL = '合计'

export function isL7DisclosureApplicable(
  variant: L7DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
): boolean {
  const list = (applicableStandards || []).map((s) => String(s).trim().toLowerCase()).filter(Boolean)
  if (list.length === 0) return true
  const hasListed = list.some((s) => s.includes('listed') || s.includes('上市'))
  const hasSoe = list.some((s) => s.includes('soe') || s.includes('state_owned') || s.includes('国'))
  if (!hasListed && !hasSoe) return true
  return variant === 'listed' ? hasListed : hasSoe
}

export function resolveL7CurrentStandard(
  variant: L7DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
): string {
  const list = (applicableStandards || []).map((s) => String(s).toLowerCase())
  if (variant === 'listed') {
    return list.some((s) => s === 'listed_consolidated' || (s.includes('listed') && s.includes('consol')))
      ? 'listed_consolidated'
      : 'listed_standalone'
  }
  return list.some((s) => s === 'soe_consolidated' || (s.includes('soe') && s.includes('consol')))
    ? 'soe_consolidated'
    : 'soe_standalone'
}

/**
 * 主表列定义（单级表头 → 显式 `flat`）。
 *
 * 列名按变体分取源模板字面：上市「期末数 / 上年年末数」、国企「期末余额 / 期初余额」。
 */
export function l7ColumnsFor(variant: L7DisclosureVariant): Record<string, ColumnDef[]> {
  const isListed = variant === 'listed'
  return {
    [L7_SUBTABLE.main]: defineColumns([
      { key: 'label', label: '项目', is_label: true, flat: true },
      // 🔴 soe 列序 = 源模板口径（年初余额/期末余额），与 listed（期末数/上年年末数）相反
      //    是源模板事实（spec l-cycle-…completion 裁决 C）。
      //    key 保持不变（prior_amount=期初/年初，end_amount=期末），只改 label 与数组顺序。
      ...(isListed
        ? [
            { key: 'end_amount', label: '期末数', format: 'amount' as const, align: 'right' as const },
            { key: 'prior_amount', label: '上年年末数', format: 'amount' as const, align: 'right' as const },
          ]
        : [
            { key: 'prior_amount', label: '年初余额', format: 'amount' as const, align: 'right' as const },
            { key: 'end_amount', label: '期末余额', format: 'amount' as const, align: 'right' as const },
          ]),
    ]),
  }
}

export const buildL7ListedColumns = () => l7ColumnsFor('listed')
export const buildL7SoeColumns = () => l7ColumnsFor('soe')

/** 载荷入参行（组件侧把各自字段名归一到这里） */
export interface L7DisclosureRow {
  label: string
  endAmount: number
  priorAmount: number
}

export interface L7SyncPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  current_standard: string
  sub_table_data: Record<string, Record<string, unknown>[]>
  columns?: Record<string, ColumnDef[]>
}

function num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function isTotalLabel(label: string): boolean {
  // 源模板合计行字面带空格（「合  计」），先去空白再比
  return label.replace(/\s+/g, '') === '合计'
}

/**
 * 主表行：业务键行（`{label, end_amount, prior_amount}`）。
 *
 * 🔴 不用位置化 `values` 数组 —— `sub_table_data` 唯一规范形态是业务键行，
 * 且 `columns` 的 key 必须能在行对象里找到落点，否则附注渲染取不到值。
 */
export function buildL7MainRows(rows: readonly L7DisclosureRow[]): Record<string, unknown>[] {
  const dataRows = rows.filter((r) => !isTotalLabel(String(r.label ?? '')))
  const out: Record<string, unknown>[] = dataRows.map((r) => ({
    label: String(r.label ?? '').trim(),
    end_amount: num(r.endAmount),
    prior_amount: num(r.priorAmount),
  }))
  out.push({
    label: L7_TOTAL_LABEL,
    end_amount: dataRows.reduce((s, r) => s + num(r.endAmount), 0),
    prior_amount: dataRows.reduce((s, r) => s + num(r.priorAmount), 0),
    is_total: true,
  })
  return out
}

export interface L7SyncSnapshot {
  variant: L7DisclosureVariant
  rows: readonly L7DisclosureRow[]
}

/**
 * 构建同步载荷。
 *
 * 🔴 **审计结论不进附注**：源 xlsx 五、52 / 八、57 都没有说明段（模板 `text_sections`
 * 亦为空），底稿的「核对结论」是过程记录，推进去会在附注正文凭空多一段。
 */
export function buildL7SyncPayload(
  wpId: string,
  snapshot: L7SyncSnapshot,
  applicableStandards?: readonly string[] | null,
): L7SyncPayload | null {
  const { variant, rows } = snapshot
  if (!isL7DisclosureApplicable(variant, applicableStandards)) return null
  return {
    wp_id: wpId,
    sheet_name: L7_DISCLOSURE_SHEET_NAME[variant],
    section_id: L7_NOTE_SECTION[variant],
    current_standard: resolveL7CurrentStandard(variant, applicableStandards),
    sub_table_data: { [L7_SUBTABLE.main]: buildL7MainRows(rows) },
    columns: l7ColumnsFor(variant),
  }
}
