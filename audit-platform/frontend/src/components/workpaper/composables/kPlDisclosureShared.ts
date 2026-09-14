/**
 * K 系损益类披露（K8~K13）共享列/行/载荷构造
 *
 * 六循环附注结构同构 —— 单表，标签列 + 本期发生额 + 上期发生额 [+ 第 4 列]：
 *
 * | 循环 | listed | soe |
 * |------|--------|-----|
 * | K8 销售费用 / K9 管理费用 / K11 资产减值损失 | 3 列 | 3 列 |
 * | K10 其他收益 | 3 列 | **4 列**（末列「是否为政府补助」文本） |
 * | K12 营业外收入 / K13 营业外支出 | **4 列** | **4 列**（末列「计入当期非经常性损益的金额」金额） |
 *
 * 抽公共构造避免六份 map 漂移。**各循环仍各自 `const` 声明
 * `X_DISCLOSURE_SHEET_NAME`** —— `gen_note_wp_sync_registry.py` 的 `_SHEET_CONST`
 * 正则锚定 `const/let/var` 声明，re-export 取不到；`disclosureSheetNameRegistry.spec.ts`
 * 也按文件名扫 `*NoteSectionMap.ts`。
 *
 * 源模板六个披露 sheet 都是单行表头 → 一律 `flat`（标在标签列即整表生效）。
 *
 * spec: .kiro/specs/k-cycle-disclosure-alignment/ Task 2.1
 */
import { defineColumns, type ColumnDef } from './disclosureColumnDefs'

export type KPlVariant = 'listed' | 'soe'

/** 合计行字面（本批六循环两版模板均为无空格「合计」） */
export const K_PL_TOTAL_LABEL = '合计'

/** 第 4 列声明。`format: 'amount'` → 参与合计求和；`'text'` → 合计置 null。 */
export interface KPlExtraColumn {
  key: string
  label: string
  format: 'amount' | 'text'
}

export interface KPlColumnSpec {
  /** 标签列列头，必须 = 模板 headers[0] */
  labelHeader: string
  currentLabel: string
  priorLabel: string
  extra?: KPlExtraColumn
}

/**
 * 单表列定义（显式 flat，抑制后端 `_infer_groups_from_headers` 前缀推断）。
 *
 * 🔴 **不叫 `buildPlColumns`**：`disclosureColumnsCoverage.spec.ts` 的 sweep 按
 * `^build[A-Z]\w*Columns$` 发现 builder 并用**空入参**调用 —— 参数化 helper 被这样
 * 调用会产出空列头（Property 6 假阳性）。对外只暴露各循环的零参
 * `buildK{n}{Listed,Soe}Columns`，参数化的一律 `xxxColumnsFor` 命名。
 */
export function plColumnsFor(spec: KPlColumnSpec): ColumnDef[] {
  return defineColumns([
    { key: 'label', label: spec.labelHeader, is_label: true, flat: true },
    { key: 'current_amount', label: spec.currentLabel, format: 'amount', align: 'right' },
    { key: 'prior_amount', label: spec.priorLabel, format: 'amount', align: 'right' },
    ...(spec.extra
      ? [{
          key: spec.extra.key,
          label: spec.extra.label,
          format: spec.extra.format,
          ...(spec.extra.format === 'amount' ? { align: 'right' as const } : {}),
        }]
      : []),
  ])
}

export interface KPlRow {
  project: string
  currentAmount: number
  priorAmount: number
  /** 第 4 列值：金额列传 number，文本列传 string */
  extraValue?: number | string | null
  /**
   * 结构行（如国企其他收益的「其中：政府补助」）：原样透传但不参与合计求和。
   * 附注是交付物，缺了看不出明细归属，故不能省。
   */
  isStructural?: boolean
}

function num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

/** 行标签去空白后判定（源模板写「合 计」「小 计」，`startsWith('合计')` 会漏判） */
function normLabel(v: unknown): string {
  return String(v ?? '').replace(/[\s\u3000]/g, '')
}

function isTotalLabel(label: unknown): boolean {
  const n = normLabel(label)
  return n === '合计' || n === '小计'
}

/**
 * 明细行 + 合计行。
 *
 * - 已在入参里的合计/小计行被剔除（合计由本函数统一派生，避免双合计）
 * - `isStructural` 行原样透传但不计入合计
 * - 文本型第 4 列的合计置 `null`（列键仍在，保表头对齐）
 */
export function buildPlTableRows(
  rows: readonly KPlRow[],
  spec: KPlColumnSpec,
  /**
   * 合计行**之后**的结构行（源模板即此行序，如国企其他收益的「其中：政府补助」
   * 排在合计之后）。不参与合计求和。
   */
  afterTotalRows: readonly KPlRow[] = [],
): Array<Record<string, unknown>> {
  const extra = spec.extra

  const toRow = (r: KPlRow): Record<string, unknown> => {
    const row: Record<string, unknown> = {
      label: String(r.project).trim(),
      current_amount: num(r.currentAmount),
      prior_amount: num(r.priorAmount),
    }
    if (extra) {
      row[extra.key] = extra.format === 'amount'
        ? num(r.extraValue)
        : (r.extraValue == null ? '' : String(r.extraValue))
    }
    return row
  }

  const kept = (rows ?? []).filter(
    r => String(r?.project ?? '').trim() && !isTotalLabel(r.project),
  )
  const data = kept.map(toRow)

  const summable = kept
    .map((r, i) => ({ r, row: data[i] }))
    .filter(({ r }) => !r.isStructural)

  const total: Record<string, unknown> = {
    label: K_PL_TOTAL_LABEL,
    current_amount: summable.reduce((s, { row }) => s + num(row.current_amount), 0),
    prior_amount: summable.reduce((s, { row }) => s + num(row.prior_amount), 0),
    is_total: true,
  }
  if (extra) {
    total[extra.key] = extra.format === 'amount'
      ? summable.reduce((s, { row }) => s + num(row[extra.key]), 0)
      : null
  }

  const trailing = (afterTotalRows ?? [])
    .filter(r => String(r?.project ?? '').trim())
    .map(toRow)

  return [...data, total, ...trailing]
}

export interface KPlNoteText {
  section: string
  title: string
  text: string
}

export interface KPlSyncPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  current_standard: string
  sub_table_data: Record<string, unknown>
  columns: Record<string, ColumnDef[]>
}

export interface KPlPayloadArgs {
  wpId: string
  sheetName: string
  sectionId: string
  variant: KPlVariant
  tableName: string
  spec: KPlColumnSpec
  rows: readonly KPlRow[]
  /** 合计行之后的结构行（源模板行序） */
  afterTotalRows?: readonly KPlRow[]
  texts?: readonly KPlNoteText[]
  /** 历史泄漏表名等，改版后须从附注侧删除 */
  removedTableKeys?: readonly string[]
}

export function resolveCurrentStandard(variant: KPlVariant): string {
  return variant === 'listed' ? 'listed_standalone' : 'soe_standalone'
}

export function buildPlPayload(args: KPlPayloadArgs): KPlSyncPayload {
  const sub: Record<string, unknown> = {
    [args.tableName]: buildPlTableRows(args.rows, args.spec, args.afterTotalRows),
  }

  const texts = (args.texts ?? []).filter(t => String(t?.text ?? '').trim())
  if (texts.length) {
    sub._note_texts = texts.map(t => ({
      section: t.section,
      title: t.title,
      text: String(t.text).trim(),
    }))
  }

  const pushed = new Set(Object.keys(sub))
  const removed = (args.removedTableKeys ?? []).filter(n => n && !pushed.has(n))
  if (removed.length) sub._removed_table_keys = removed

  return {
    wp_id: args.wpId,
    sheet_name: args.sheetName,
    section_id: args.sectionId,
    current_standard: resolveCurrentStandard(args.variant),
    sub_table_data: sub,
    columns: { [args.tableName]: plColumnsFor(args.spec) },
  }
}
