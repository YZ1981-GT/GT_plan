/**
 * N5 所得税费用披露 ↔ 附注章节映射与 sync payload 构建
 *
 * 权威来源
 * --------
 * - **列结构 / 行型 / 文本** = `backend/wp_templates/N/N5 所得税费用.xlsx` 的
 *   `附注披露信息（上市公司）`（A1:L29）与 `附注披露信息（国企`（A1:IU32），逐行实测；
 *   结论固化在 `.kiro/specs/n-cycle-tax-disclosure-alignment/design.md` §Data Models。
 * - **章节号** = `note_template_{listed,soe}.json` 现存章节
 *   → listed `三、所得税费用` / soe `八、78`
 * - **表名 / 行集合** = 同上两份模板
 *   （由 `backend/scripts/fix/fix_note_n_cycle_tax_structure.py` 幂等维护）
 * - **sheet 名** = `workpaper_sheet_classification`（wp_code=N5）实测
 *
 * 🔴 **国企披露 sheet 的 tab 名缺右括号**：`附注披露信息（国企`（A2 单元格才是完整的
 * `附注披露信息（国企）`）。`workpaper_sheet_classification` 记的是 tab 名，
 * 同步 `sheet_name` 必须与之**逐字一致**，不要"修正"—— 否则附注「打开同步底稿」
 * 的 `?sheet=` 精确匹配落空，落到底稿首个 sheet。
 *
 * 🔴 **两版表名原本各自重名**（md 重建把表头首格 / 章节名当表名泄漏），
 * 而表名是 `sub_table_data` 的键 → 同名会互相覆盖**丢整张表**：
 * - listed 两表都叫 `项  目` → `所得税费用明细` / `所得税费用与利润总额的关系`
 * - soe 两表都叫 `所得税费用` → `所得税费用` / `会计利润与所得税费用调整过程`
 * 去重后既有已同步项目会残留旧键 → 见 `N5_LEGACY_OBSOLETE_TABLES`。
 *
 * 🔴 **章节 `三、所得税费用` 位置本身不对**（md 重建把 8 个利润表项目注释章节挂到
 * `chapter-03 重要会计政策`，应在 `chapter-05 项目注释`）。修它会改动章节号并影响
 * 既有项目的 `note_section` 定位键 → 属跨 spec 依赖，本模块用模板**现存**章节号保证链路通。
 */
import { defineColumns, type ColumnDef } from './disclosureColumnDefs'
import {
  attachRemovedTableKeys,
  dataTableNames,
  type TableNamespaceSpec,
} from './disclosureSyncedTables'
import { nz, sumNullable, type NullableAmount } from './shared/disclosureConsistency'

export type N5DisclosureVariant = 'listed' | 'soe'

/** 附注章节号（模板现存值；listed 侧的章节归属错误属跨 spec 依赖，不在此修） */
export const N5_NOTE_SECTION = {
  listed: '三、所得税费用',
  soe: '八、78',
} as const satisfies Record<N5DisclosureVariant, string>

/**
 * 底稿披露 sheet 真实 tab 名（逐字取自 `workpaper_sheet_classification`）。
 * 🔴 `soe` **缺右括号**，源模板 tab 名如此，禁"修正"。
 */
export const N5_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息（上市公司）',
  soe: '附注披露信息（国企',
} as const satisfies Record<N5DisclosureVariant, string>

/** 子表键（逐字取自附注模板 `tables[].name`，已去重） */
export const N5_SUB_TABLE_KEYS = {
  listed: {
    detail: '所得税费用明细',
    reconcile: '所得税费用与利润总额的关系',
  },
  soe: {
    detail: '所得税费用',
    reconcile: '会计利润与所得税费用调整过程',
  },
} as const satisfies Record<N5DisclosureVariant, Record<string, string>>

/**
 * 表名去重前的旧键（既有已同步项目残留）。
 * - listed：两表都叫 `项  目`（md 重建把表头首格当表名）
 * - soe：第 2 表原与第 1 表同名 `所得税费用`，同名塌成一张 → **无额外孤儿键**
 */
export const N5_LEGACY_OBSOLETE_TABLES = {
  listed: ['项  目'],
  soe: [],
} as const satisfies Record<N5DisclosureVariant, readonly string[]>

/** 表名命名空间（孤儿清理基线播种；表名固定，无动态前缀/续表后缀） */
export const N5_TABLE_NAMESPACE: Record<N5DisclosureVariant, TableNamespaceSpec> = {
  listed: {
    known: [
      ...Object.values(N5_SUB_TABLE_KEYS.listed),
      ...N5_LEGACY_OBSOLETE_TABLES.listed,
    ],
  },
  soe: {
    known: [...Object.values(N5_SUB_TABLE_KEYS.soe), ...N5_LEGACY_OBSOLETE_TABLES.soe],
  },
}

export const N5_TOTAL_LABEL = '合计'

/** 上市表（2）末行不是合计行，而是勾稽落点（源模板注 1） */
export const N5_LISTED_TAIL_LABEL = '所得税费用'

export function resolveN5CurrentStandard(
  variant: N5DisclosureVariant,
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

// ─── 列定义（两版结构相同：3 列双期发生额）───────────────────────────────────

const AMT = 'amount' as const

function threeColumnDefs(): ColumnDef[] {
  return defineColumns([
    { key: 'label', label: '项目', is_label: true, flat: true },
    { key: 'current', label: '本期发生额', format: AMT },
    { key: 'prior', label: '上期发生额', format: AMT },
  ])
}

export function buildN5ListedColumns(): Record<string, ColumnDef[]> {
  return {
    [N5_SUB_TABLE_KEYS.listed.detail]: threeColumnDefs(),
    [N5_SUB_TABLE_KEYS.listed.reconcile]: threeColumnDefs(),
  }
}

export function buildN5SoeColumns(): Record<string, ColumnDef[]> {
  return {
    [N5_SUB_TABLE_KEYS.soe.detail]: threeColumnDefs(),
    [N5_SUB_TABLE_KEYS.soe.reconcile]: threeColumnDefs(),
  }
}

/**
 * 变体分发。
 * 🔴 不能命名为 `buildN5Columns`（覆盖率守卫会用空入参 sweep `build*Columns`）。
 */
export function n5ColumnsFor(variant: N5DisclosureVariant): Record<string, ColumnDef[]> {
  return variant === 'listed' ? buildN5ListedColumns() : buildN5SoeColumns()
}

// ─── Snapshot ────────────────────────────────────────────────────────────────

export interface N5Row {
  item: string
  /** 本期发生额 */
  current: NullableAmount
  /** 上期发生额 */
  prior: NullableAmount
}

export interface N5DisclosureSnapshot {
  /** 表（1）所得税费用明细（不含合计行，合计由载荷层求和） */
  detailRows: readonly N5Row[]
  /**
   * 表（2）调整过程行（不含末行）。
   * 首行是 `利润总额`（起算点，不参与末行求和）—— 求和口径由编制模型决定，
   * 载荷层只负责按传入行原样列示 + 用 `reconcileTail` 作末行。
   */
  reconcileRows: readonly N5Row[]
  /** 表（2）末行金额（上市 = 所得税费用行 / 国企 = 合计行） */
  reconcileTail: { current: NullableAmount; prior: NullableAmount }
  notes?: Record<string, string>
  previouslySyncedTables?: readonly string[]
}

export interface N5SyncPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  current_standard: string
  year: number
  sub_table_data: Record<string, unknown>
  columns: Record<string, ColumnDef[]>
}

// ─── helpers ─────────────────────────────────────────────────────────────────

/** 行型判定先去空白（源模板写 `合  计`） */
export function normalizeN5RowLabel(label: unknown): string {
  return String(label ?? '').replace(/\s+/g, '')
}

export function isN5TotalLabel(label: unknown): boolean {
  const s = normalizeN5RowLabel(label)
  return s.startsWith('小计') || s.startsWith('合计')
}

const NOTE_TITLES: Record<string, string> = {
  detail: '所得税费用明细说明',
  reconcile: '所得税费用与利润总额关系说明',
  conclusion: '披露说明与结论',
}

const NOTE_ORDER = ['detail', 'reconcile', 'conclusion']

export function buildN5NoteTexts(
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
    out.push({ section: `n5-disclosure-${k}`, title: NOTE_TITLES[k] || k, text })
  }
  return out
}

function mapRows(rows: readonly N5Row[]): Array<Record<string, unknown>> {
  return rows.map((r) => ({
    label: String(r.item ?? ''),
    current: nz(r.current),
    prior: nz(r.prior),
  }))
}

// ─── payload 构造（纯函数）───────────────────────────────────────────────────

export function buildN5SyncPayload(
  variant: N5DisclosureVariant,
  snapshot: N5DisclosureSnapshot,
  ctx: { wpId: string; year: number; applicableStandards?: readonly string[] | null },
): N5SyncPayload {
  const keys = N5_SUB_TABLE_KEYS[variant]
  const detailRows = mapRows(snapshot.detailRows || [])
  const reconcileRows = mapRows(snapshot.reconcileRows || [])

  const detailTotal: Record<string, unknown> = {
    label: N5_TOTAL_LABEL,
    current: sumNullable(detailRows.map((r) => nz(r.current))),
    prior: sumNullable(detailRows.map((r) => nz(r.prior))),
    is_total: true,
  }

  // 上市表（2）末行是「所得税费用」勾稽落点（源模板注 1），不是合计行；
  // 国企表（2）末行是 `合  计` → 打 is_total
  const tail: Record<string, unknown> =
    variant === 'listed'
      ? {
          label: N5_LISTED_TAIL_LABEL,
          current: nz(snapshot.reconcileTail?.current ?? null),
          prior: nz(snapshot.reconcileTail?.prior ?? null),
        }
      : {
          label: N5_TOTAL_LABEL,
          current: nz(snapshot.reconcileTail?.current ?? null),
          prior: nz(snapshot.reconcileTail?.prior ?? null),
          is_total: true,
        }

  const subTableData: Record<string, unknown> = {
    [keys.detail]: [...detailRows, detailTotal],
    [keys.reconcile]: [...reconcileRows, tail],
  }

  const texts = buildN5NoteTexts(snapshot.notes)
  if (texts.length > 0) subTableData._note_texts = texts

  // 表名去重后的旧键清理（本次推送的键绝不进）
  attachRemovedTableKeys(subTableData, {
    previouslySynced: snapshot.previouslySyncedTables,
    legacyObsolete: N5_LEGACY_OBSOLETE_TABLES[variant],
    pushed: dataTableNames(subTableData),
  })

  return {
    wp_id: ctx.wpId,
    sheet_name: N5_DISCLOSURE_SHEET_NAME[variant],
    section_id: N5_NOTE_SECTION[variant],
    current_standard: resolveN5CurrentStandard(variant, ctx.applicableStandards),
    year: ctx.year,
    sub_table_data: subTableData,
    columns: n5ColumnsFor(variant),
  }
}

export default buildN5SyncPayload
