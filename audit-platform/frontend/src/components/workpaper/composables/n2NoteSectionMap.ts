/**
 * N2 应交税费披露 ↔ 附注章节映射与 sync payload 构建
 *
 * 权威来源
 * --------
 * - **列结构 / 行型 / 文本** = `backend/wp_templates/N/N2 应交税费.xlsx` 的
 *   `附注披露信息（上市公司）`（A1:K27）与 `附注披露信息（国企）`（A1:K24），逐行实测；
 *   结论固化在 `.kiro/specs/n-cycle-tax-disclosure-alignment/design.md` §Data Models。
 * - **章节号** = `backend/data/note_template_variant_matrix.json` 的 `ying_jiao_shui_fei`
 *   → listed 五、41 / soe 八、41
 * - **表名 / 行集合** = `note_template_{listed,soe}.json`
 *   （由 `backend/scripts/fix/fix_note_n_cycle_tax_structure.py` 幂等维护）
 * - **sheet 名** = `workpaper_sheet_classification`（wp_code=N2）实测全角括号
 *
 * 🔴 **两版列结构本质不同，禁止共用一份列定义**：
 * - 上市 = **双期余额表** 3 列（税项 / 期末余额 / 上年年末余额）
 * - 国企 = **变动表** 5 列（项目 / 期初余额 / 本期应交 / 本期已交 / 期末余额），
 *   末列是源模板行内公式 `=B8+C8-D8`
 *
 * 现状缺陷即源于此：两个披露组件是复制粘贴关系，上市误用了国企的变动口径。
 */
import { defineColumns, type ColumnDef } from './disclosureColumnDefs'
import type { TableNamespaceSpec } from './disclosureSyncedTables'
import { nz, sumNullable, type NullableAmount } from './shared/disclosureConsistency'

export type N2DisclosureVariant = 'listed' | 'soe'

/** 附注章节号（权威矩阵 ying_jiao_shui_fei） */
export const N2_NOTE_SECTION = {
  listed: '五、41',
  soe: '八、41',
} as const satisfies Record<N2DisclosureVariant, string>

/** 底稿披露 sheet 真实 tab 名（供 `_last_sync_sheet` 反向定位；逐字取自 DB） */
export const N2_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息（上市公司）',
  soe: '附注披露信息（国企）',
} as const satisfies Record<N2DisclosureVariant, string>

/** 子表键（逐字取自附注模板 `tables[].name`） */
export const N2_SUB_TABLE_KEYS = {
  listed: { taxes: '应交税费' },
  soe: { taxes: '应交税费' },
} as const satisfies Record<N2DisclosureVariant, Record<string, string>>

/** 表名命名空间（孤儿清理基线播种；表名固定，无动态前缀/续表后缀） */
export const N2_TABLE_NAMESPACE: Record<N2DisclosureVariant, TableNamespaceSpec> = {
  listed: { known: Object.values(N2_SUB_TABLE_KEYS.listed) },
  soe: { known: Object.values(N2_SUB_TABLE_KEYS.soe) },
}

export const N2_TOTAL_LABEL = '合计'

export function resolveN2CurrentStandard(
  variant: N2DisclosureVariant,
  applicableStandards?: readonly string[] | null,
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

// ─── 列定义（逐字对齐附注模板 headers）───────────────────────────────────────

const AMT = 'amount' as const

/** 上市：双期余额表（源模板 R7） */
export function buildN2ListedColumns(): Record<string, ColumnDef[]> {
  return {
    [N2_SUB_TABLE_KEYS.listed.taxes]: defineColumns([
      { key: 'label', label: '税项', is_label: true, flat: true },
      { key: 'end', label: '期末余额', format: AMT },
      { key: 'prior', label: '上年年末余额', format: AMT },
    ]),
  }
}

/** 国企：变动表（源模板 R7；末列为行内公式 `=B8+C8-D8`） */
export function buildN2SoeColumns(): Record<string, ColumnDef[]> {
  return {
    [N2_SUB_TABLE_KEYS.soe.taxes]: defineColumns([
      { key: 'label', label: '项目', is_label: true, flat: true },
      { key: 'opening', label: '期初余额', format: AMT },
      { key: 'payable', label: '本期应交', format: AMT },
      { key: 'paid', label: '本期已交', format: AMT },
      { key: 'end', label: '期末余额', format: AMT },
    ]),
  }
}

/**
 * 变体分发。
 *
 * 🔴 **不能命名为 `buildN2Columns`** —— `disclosureColumnsCoverage` 守卫会 sweep 所有
 * `build*Columns` 导出并**用空入参调用**，带 variant 参数的 builder 会拿到 `undefined`
 * 而产出错变体列头。参数化 builder 统一用 `n2ColumnsFor` 命名。
 */
export function n2ColumnsFor(variant: N2DisclosureVariant): Record<string, ColumnDef[]> {
  return variant === 'listed' ? buildN2ListedColumns() : buildN2SoeColumns()
}

// ─── Snapshot ────────────────────────────────────────────────────────────────

export interface N2ListedTaxRow {
  item: string
  /** 期末余额 */
  end: NullableAmount
  /** 上年年末余额 */
  prior: NullableAmount
}

export interface N2SoeTaxRow {
  item: string
  opening: NullableAmount
  payable: NullableAmount
  paid: NullableAmount
  /** 期末余额（行内公式结果；由编制模型算出后传入，不由用户录入） */
  end: NullableAmount
}

export interface N2DisclosureSnapshot {
  /** 上市：双期行；国企：变动行。由调用方按 variant 传对应类型 */
  taxRows: readonly (N2ListedTaxRow | N2SoeTaxRow)[]
  /** 说明 / 结论文本（按子节，空串不同步） */
  notes?: Record<string, string>
  /** 上次同步成功时推送的子表名（孤儿清理差集基线） */
  previouslySyncedTables?: readonly string[]
}

export interface N2SyncPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  current_standard: string
  year: number
  sub_table_data: Record<string, unknown>
  columns: Record<string, ColumnDef[]>
}

// ─── helpers ─────────────────────────────────────────────────────────────────

/**
 * 行型判定必须先去空白：源模板写的是 `合  计`（中间带空格），
 * `startsWith('合计')` 会漏判 → 合计行被当普通数据行推给附注，丢 `is_total`。
 */
export function normalizeN2RowLabel(label: unknown): string {
  return String(label ?? '').replace(/\s+/g, '')
}

export function isN2TotalLabel(label: unknown): boolean {
  const s = normalizeN2RowLabel(label)
  return s.startsWith('小计') || s.startsWith('合计')
}

const NOTE_TITLES: Record<string, string> = {
  conclusion: '披露说明与结论',
  offset: '当期所得税资产负债抵销列示说明',
}

const NOTE_ORDER = ['offset', 'conclusion']

export function buildN2NoteTexts(
  notes?: Record<string, string>,
): Array<{ section: string; title: string; text: string }> {
  if (!notes) return []
  const keys = [
    ...NOTE_ORDER.filter((k) => k in notes),
    ...Object.keys(notes).filter((k) => !NOTE_ORDER.includes(k)),
  ]
  const out: Array<{ section: string; title: string; text: string }> = []
  for (const k of keys) {
    const text = String(notes[k] ?? '').trim()
    if (!text) continue
    out.push({ section: `n2-disclosure-${k}`, title: NOTE_TITLES[k] || k, text })
  }
  return out
}

/** 国企期末余额行内公式（源模板 `=B8+C8-D8`）；任一项缺失 → null（不塌 0） */
export function computeN2SoeEnd(row: {
  opening: NullableAmount
  payable: NullableAmount
  paid: NullableAmount
}): NullableAmount {
  const o = nz(row.opening)
  const p = nz(row.payable)
  const d = nz(row.paid)
  if (o === null && p === null && d === null) return null
  return Math.round(((o ?? 0) + (p ?? 0) - (d ?? 0)) * 100) / 100
}

// ─── payload 构造（纯函数）───────────────────────────────────────────────────

export function buildN2SyncPayload(
  variant: N2DisclosureVariant,
  snapshot: N2DisclosureSnapshot,
  ctx: { wpId: string; year: number; applicableStandards?: readonly string[] | null },
): N2SyncPayload {
  const key = N2_SUB_TABLE_KEYS[variant].taxes
  const columns = n2ColumnsFor(variant)
  const rows = snapshot.taxRows || []

  const dataRows: Array<Record<string, unknown>> =
    variant === 'listed'
      ? (rows as readonly N2ListedTaxRow[]).map((r) => ({
          label: String(r.item ?? ''),
          end: nz(r.end),
          prior: nz(r.prior),
        }))
      : (rows as readonly N2SoeTaxRow[]).map((r) => ({
          label: String(r.item ?? ''),
          opening: nz(r.opening),
          payable: nz(r.payable),
          paid: nz(r.paid),
          end: nz(r.end),
        }))

  const totalRow: Record<string, unknown> =
    variant === 'listed'
      ? {
          label: N2_TOTAL_LABEL,
          end: sumNullable(dataRows.map((r) => nz(r.end))),
          prior: sumNullable(dataRows.map((r) => nz(r.prior))),
          is_total: true,
        }
      : {
          label: N2_TOTAL_LABEL,
          opening: sumNullable(dataRows.map((r) => nz(r.opening))),
          payable: sumNullable(dataRows.map((r) => nz(r.payable))),
          paid: sumNullable(dataRows.map((r) => nz(r.paid))),
          end: sumNullable(dataRows.map((r) => nz(r.end))),
          is_total: true,
        }

  const subTableData: Record<string, unknown> = { [key]: [...dataRows, totalRow] }

  const texts = buildN2NoteTexts(snapshot.notes)
  if (texts.length > 0) subTableData._note_texts = texts

  return {
    wp_id: ctx.wpId,
    sheet_name: N2_DISCLOSURE_SHEET_NAME[variant],
    section_id: N2_NOTE_SECTION[variant],
    current_standard: resolveN2CurrentStandard(variant, ctx.applicableStandards),
    year: ctx.year,
    sub_table_data: subTableData,
    columns,
  }
}

export default buildN2SyncPayload
