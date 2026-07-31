/**
 * mEquityChangeNoteSectionMap — M 循环权益类「变动表」披露 ↔ 附注章节共享映射
 *
 * 覆盖结构同构的标准变动表（项目 | 期初余额 | 本期增加 | 本期减少 | 期末余额）：
 *   - M4 资本公积（五、55 / 八、60）
 *   - M5 盈余公积（五、59 / 八、62）
 *   - M7 专项储备（五、58 / 八、61，国企侧多「备注」列）
 *
 * 权威来源：`note_template_variant_matrix.json` + 源 xlsx
 * `backend/wp_templates/M/*.xlsx` 的「附注披露信息（上市公司）/（国有企业）」。
 *
 * 🔴 M1 应付股利（豁免，归 K3）、M2 实收资本/股本（两级表头）、M6 未分配利润（单列变动链）、
 *    M3 库存股、M8 一般风险准备、M9 其他综合收益（多级）、M10 其他权益工具（两级表头）
 *    结构不同，不在本共享映射内。
 */
import { defineColumns, type ColumnDef } from './disclosureColumnDefs'

export type MEquityVariant = 'listed' | 'soe'
export type MEquityCycle = 'M4' | 'M5' | 'M7'

interface MEquityCycleConfig {
  /** {listed, soe} 章节号 */
  section: Record<MEquityVariant, string>
  /** {listed, soe} 附注表名（逐字 = note_template tables[].name） */
  table: Record<MEquityVariant, string>
  /** 国企侧是否含「备注」列（M7 专项储备有） */
  soeRemark?: boolean
}

export const M_EQUITY_CONFIG: Record<MEquityCycle, MEquityCycleConfig> = {
  M4: {
    section: { listed: '五、55', soe: '八、60' },
    table: { listed: '资本公积', soe: '资本公积' },
  },
  M5: {
    section: { listed: '五、59', soe: '八、62' },
    table: { listed: '盈余公积', soe: '盈余公积' },
  },
  M7: {
    section: { listed: '五、58', soe: '八、61' },
    table: { listed: '专项储备', soe: '专项储备' },
    soeRemark: true,
  },
}

/** 各科目底稿内附注 sheet 真实 tab 名（M 循环统一全角括号，实测源 xlsx） */
export const M_EQUITY_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息（上市公司）',
  soe: '附注披露信息（国有企业）',
} as const satisfies Record<MEquityVariant, string>

export const M_EQUITY_TOTAL_LABEL = '合计'

function num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function isTotalLabel(v: unknown): boolean {
  return String(v ?? '').replace(/\s+/g, '') === M_EQUITY_TOTAL_LABEL
}

export function isMEquityApplicable(
  variant: MEquityVariant,
  applicableStandards: readonly string[] | null | undefined,
): boolean {
  const list = (applicableStandards || []).map((s) => String(s).trim().toLowerCase()).filter(Boolean)
  if (list.length === 0) return true
  const hasListed = list.some((s) => s.includes('listed') || s.includes('上市'))
  const hasSoe = list.some((s) => s.includes('soe') || s.includes('state_owned') || s.includes('国'))
  if (!hasListed && !hasSoe) return true
  return variant === 'listed' ? hasListed : hasSoe
}

export function resolveMEquityCurrentStandard(
  variant: MEquityVariant,
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

/** 变动表列定义（单级表头 flat；国企 M7 多「备注」） */
export function mEquityColumnsFor(cycle: MEquityCycle, variant: MEquityVariant): Record<string, ColumnDef[]> {
  const cfg = M_EQUITY_CONFIG[cycle]
  const defs: Array<Partial<ColumnDef> & { key: string; label: string }> = [
    { key: 'label', label: '项目', is_label: true, flat: true },
    { key: 'begin_amount', label: '期初余额', format: 'amount', align: 'right' },
    { key: 'increase', label: '本期增加', format: 'amount', align: 'right' },
    { key: 'decrease', label: '本期减少', format: 'amount', align: 'right' },
    { key: 'end_amount', label: '期末余额', format: 'amount', align: 'right' },
  ]
  if (variant === 'soe' && cfg.soeRemark) {
    defs.push({ key: 'remark', label: '备注', format: 'text' })
  }
  return { [cfg.table[variant]]: defineColumns(defs) }
}

export interface MEquityRow {
  label: string
  begin: number
  increase: number
  decrease: number
  /** 期末 —— 不传则读时派生 = 期初 + 增加 − 减少 */
  end?: number
  remark?: string
}

export interface MEquitySyncPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  current_standard: string
  sub_table_data: Record<string, Record<string, unknown>[]>
  columns?: Record<string, ColumnDef[]>
}

/** 期末派生（权益类贷方：增加=贷方、减少=借方） */
export function mEquityEndAmount(r: MEquityRow): number {
  return r.end != null ? num(r.end) : num(r.begin) + num(r.increase) - num(r.decrease)
}

export function buildMEquityRows(
  rows: readonly MEquityRow[],
  variant: MEquityVariant,
  withRemark: boolean,
): Record<string, unknown>[] {
  const data = rows.filter((r) => String(r.label ?? '').trim() && !isTotalLabel(r.label))
  const out: Record<string, unknown>[] = data.map((r) => {
    const row: Record<string, unknown> = {
      label: String(r.label).trim(),
      begin_amount: num(r.begin),
      increase: num(r.increase),
      decrease: num(r.decrease),
      end_amount: mEquityEndAmount(r),
    }
    if (variant === 'soe' && withRemark) row.remark = r.remark ?? ''
    return row
  })
  const total: Record<string, unknown> = {
    label: M_EQUITY_TOTAL_LABEL,
    begin_amount: data.reduce((s, r) => s + num(r.begin), 0),
    increase: data.reduce((s, r) => s + num(r.increase), 0),
    decrease: data.reduce((s, r) => s + num(r.decrease), 0),
    end_amount: data.reduce((s, r) => s + mEquityEndAmount(r), 0),
    is_total: true,
  }
  if (variant === 'soe' && withRemark) total.remark = ''
  out.push(total)
  return out
}

export interface MEquitySyncSnapshot {
  cycle: MEquityCycle
  variant: MEquityVariant
  rows: readonly MEquityRow[]
  /** 变动说明（源模板「说明：」段），可选 */
  note?: string
}

export function buildMEquitySyncPayload(
  wpId: string,
  snapshot: MEquitySyncSnapshot,
  applicableStandards?: readonly string[] | null,
): MEquitySyncPayload | null {
  const { cycle, variant, rows } = snapshot
  if (!isMEquityApplicable(variant, applicableStandards)) return null
  const cfg = M_EQUITY_CONFIG[cycle]
  const withRemark = !!cfg.soeRemark
  const sub: Record<string, unknown> = {
    [cfg.table[variant]]: buildMEquityRows(rows, variant, withRemark),
  }
  if (snapshot.note?.trim()) {
    sub._note_texts = [{
      section: `${cycle.toLowerCase()}-${variant}-note`,
      title: `${cfg.table[variant]}变动说明`,
      text: snapshot.note.trim(),
    }] as unknown as Record<string, unknown>[]
  }
  return {
    wp_id: wpId,
    sheet_name: M_EQUITY_DISCLOSURE_SHEET_NAME[variant],
    section_id: cfg.section[variant],
    current_standard: resolveMEquityCurrentStandard(variant, applicableStandards),
    sub_table_data: sub as Record<string, Record<string, unknown>[]>,
    columns: mEquityColumnsFor(cycle, variant),
  }
}
