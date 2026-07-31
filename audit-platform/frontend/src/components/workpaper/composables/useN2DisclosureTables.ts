/**
 * useN2DisclosureTables — N2 应交税费披露表（上市 / 国企）编制模型
 *
 * 把源模板结构收敛到一处：行骨架、列定义、合计公式、国企期末余额行内公式、
 * 持久化键、勾稽入参、同步载荷组装。两个 Tab 只负责渲染。
 *
 * 源模板权威 = `backend/wp_templates/N/N2 应交税费.xlsx`
 * （`附注披露信息（上市公司）` A1:K27 / `附注披露信息（国企）` A1:K24）。
 *
 * 🔴 两版口径本质不同（上市双期余额 / 国企变动），行骨架与列都分别构造；
 * 现状缺陷即两个组件复制粘贴导致上市误用国企口径。
 * 🔴 源模板里没有的小节（税种变动说明 / 欠缴税款说明 / 应缴国有资本收益说明）不再提供 ——
 * 变动分析属审计过程，留在 N2-1 审定表与 N2-2 明细表。
 */
import { computed, ref, type Ref } from 'vue'
import {
  N2_TOTAL_LABEL,
  buildN2SyncPayload,
  computeN2SoeEnd,
  n2ColumnsFor,
  type N2DisclosureSnapshot,
  type N2DisclosureVariant,
  type N2ListedTaxRow,
  type N2SoeTaxRow,
} from './n2NoteSectionMap'
import {
  runN2ListedChecks,
  runN2SoeChecks,
  type WpCheckResult,
} from './nCycleTaxConsistency'
import { nz, sumNullable, type NullableAmount } from './shared/disclosureConsistency'
import type { WpSegColumn, WpSegment } from './shared/disclosureSegmentTypes'

// ─── 行骨架（逐字取自附注模板，与源模板动态引用行对应）─────────────────────

/** 上市默认税种（附注模板 五、41 rows） */
export const N2_LISTED_TAX_ITEMS = [
  '增值税',
  '消费税',
  '企业所得税',
  '个人所得税',
  '城市维护建设税',
] as const

/** 国企默认税种（附注模板 八、41 rows，比上市细） */
export const N2_SOE_TAX_ITEMS = [
  '增值税',
  '消费税',
  '资源税',
  '企业所得税',
  '城市维护建设税',
  '房产税',
  '土地使用税',
  '个人所得税',
  '教育费附加（含地方教育费附加）',
  '其他税费',
] as const

// ─── 行模型 ──────────────────────────────────────────────────────────────────

export interface N2ListedRowModel extends N2ListedTaxRow {
  _editableLabel?: boolean
}

/** 国企行：`end` 不落库（行内公式），持久化时剔除 */
export interface N2SoeRowModel {
  item: string
  opening: NullableAmount
  payable: NullableAmount
  paid: NullableAmount
  _editableLabel?: boolean
}

// ─── 持久化键 ────────────────────────────────────────────────────────────────

export function n2DisclosureItemIds(variant: N2DisclosureVariant) {
  const p = `N2-disclosure-${variant}`
  return {
    taxes: `${p}-taxes`,
    offsetNote: `${p}-offset-note`,
    conclusion: `${p}-conclusion`,
    syncedTables: `${p}-synced-tables`,
  } as const
}

// ─── 列定义（供 WpDisclosureSegmentTable）────────────────────────────────────

const AMT = 'amount' as const

export function n2ListedSegColumns(): WpSegColumn[] {
  return [
    { key: 'end', label: '期末余额', format: AMT, minWidth: 170 },
    { key: 'prior', label: '上年年末余额', format: AMT, minWidth: 170 },
  ]
}

export function n2SoeSegColumns(): WpSegColumn[] {
  return [
    { key: 'opening', label: '期初余额', format: AMT, minWidth: 160 },
    { key: 'payable', label: '本期应交', format: AMT, minWidth: 160 },
    { key: 'paid', label: '本期已交', format: AMT, minWidth: 160 },
    // 源模板 E 列是行内公式 =B8+C8-D8 → 只读公式列
    { key: 'end', label: '期末余额', format: AMT, minWidth: 170, readonly: true },
  ]
}

export function n2SegColumns(variant: N2DisclosureVariant): WpSegColumn[] {
  return variant === 'listed' ? n2ListedSegColumns() : n2SoeSegColumns()
}

/** 标签列表头（源模板：上市 `税  项` / 国企 `项  目`） */
export const N2_LABEL_HEADER = {
  listed: '税  项',
  soe: '项  目',
} as const satisfies Record<N2DisclosureVariant, string>

// ─── 工具 ────────────────────────────────────────────────────────────────────

function parseJsonArray<T>(raw: unknown): T[] | null {
  if (typeof raw !== 'string' || !raw) return null
  try {
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? (parsed as T[]) : null
  } catch {
    return null
  }
}

// ─── 主 composable ───────────────────────────────────────────────────────────

export interface UseN2DisclosureTablesOptions {
  variant: N2DisclosureVariant
  allResponses: Ref<Map<string, { conclusion?: string | null; remark?: string | null }>>
}

export function useN2DisclosureTables(opts: UseN2DisclosureTablesOptions) {
  const { variant, allResponses } = opts
  const ID = n2DisclosureItemIds(variant)

  const listedRows = ref<N2ListedRowModel[]>([])
  const soeRows = ref<N2SoeRowModel[]>([])
  const offsetNote = ref('')
  const conclusionNote = ref('')
  const syncedTables = ref<string[]>([])

  function restore(): void {
    const saved = allResponses.value.get(ID.taxes)?.conclusion
    if (variant === 'listed') {
      const rows = parseJsonArray<N2ListedRowModel>(saved)
      listedRows.value = rows?.length
        ? rows
        : N2_LISTED_TAX_ITEMS.map((item) => ({ item, end: null, prior: null }))
    } else {
      const rows = parseJsonArray<N2SoeRowModel>(saved)
      soeRows.value = rows?.length
        ? rows
        : N2_SOE_TAX_ITEMS.map((item) => ({ item, opening: null, payable: null, paid: null }))
    }
    offsetNote.value = allResponses.value.get(ID.offsetNote)?.remark || ''
    conclusionNote.value = allResponses.value.get(ID.conclusion)?.remark || ''
    syncedTables.value = parseJsonArray<string>(allResponses.value.get(ID.syncedTables)?.conclusion) ?? []
  }

  /** 国企：带行内公式结果的展示行（`end` 由 `computeN2SoeEnd` 算出） */
  const soeRowsWithEnd = computed<N2SoeTaxRow[]>(() =>
    soeRows.value.map((r) => ({
      item: r.item,
      opening: nz(r.opening),
      payable: nz(r.payable),
      paid: nz(r.paid),
      end: computeN2SoeEnd(r),
    })),
  )

  // ── 合计（源模板 =SUM(B8:B22) 等）──────────────────────────────────────────

  const listedTotals = computed(() => ({
    end: sumNullable(listedRows.value.map((r) => nz(r.end))),
    prior: sumNullable(listedRows.value.map((r) => nz(r.prior))),
  }))

  const soeTotals = computed(() => ({
    opening: sumNullable(soeRowsWithEnd.value.map((r) => nz(r.opening))),
    payable: sumNullable(soeRowsWithEnd.value.map((r) => nz(r.payable))),
    paid: sumNullable(soeRowsWithEnd.value.map((r) => nz(r.paid))),
    end: sumNullable(soeRowsWithEnd.value.map((r) => nz(r.end))),
  }))

  // ── 渲染段（单段平表：label 为空串 → 不渲染分组标题行）────────────────────

  const asSegRows = (rows: readonly object[]): WpSegment['rows'] =>
    rows as unknown as WpSegment['rows']

  const segments = computed<WpSegment[]>(() => [
    {
      key: 'main',
      label: '',
      rows: asSegRows(variant === 'listed' ? listedRows.value : soeRowsWithEnd.value),
      subtotal:
        variant === 'listed'
          ? { end: listedTotals.value.end, prior: listedTotals.value.prior }
          : {
              opening: soeTotals.value.opening,
              payable: soeTotals.value.payable,
              paid: soeTotals.value.paid,
              end: soeTotals.value.end,
            },
      subtotalLabel: N2_TOTAL_LABEL,
    },
  ])

  const columns = computed(() => n2SegColumns(variant))
  const labelHeader = computed(() => N2_LABEL_HEADER[variant])

  // ── 勾稽 ──────────────────────────────────────────────────────────────────

  const checks = computed<WpCheckResult[]>(() =>
    variant === 'listed'
      ? runN2ListedChecks(listedRows.value, listedTotals.value)
      : runN2SoeChecks(soeRowsWithEnd.value, soeTotals.value),
  )

  // ── 行增删 ────────────────────────────────────────────────────────────────

  function addRow(): void {
    if (variant === 'listed') {
      listedRows.value = [
        ...listedRows.value,
        { item: '', end: null, prior: null, _editableLabel: true },
      ]
    } else {
      soeRows.value = [
        ...soeRows.value,
        { item: '', opening: null, payable: null, paid: null, _editableLabel: true },
      ]
    }
  }

  function removeRow(index: number): void {
    if (variant === 'listed') {
      listedRows.value = listedRows.value.filter((_, i) => i !== index)
    } else {
      soeRows.value = soeRows.value.filter((_, i) => i !== index)
    }
  }

  function setCell(index: number, key: string, value: number | string): void {
    const target = variant === 'listed' ? listedRows : soeRows
    const row = (target.value as Array<Record<string, unknown>>)[index]
    if (!row) return
    row[key] = value
  }

  function setLabel(index: number, value: string): void {
    const target = variant === 'listed' ? listedRows : soeRows
    const row = (target.value as Array<{ item: string }>)[index]
    if (!row) return
    row.item = value
  }

  /** 持久化载荷（国企不存 `end` —— 它是行内公式派生值，存了会变双真源） */
  function serializeRows(): string {
    return JSON.stringify(variant === 'listed' ? listedRows.value : soeRows.value)
  }

  // ── 同步载荷 ──────────────────────────────────────────────────────────────

  function buildSnapshot(): N2DisclosureSnapshot {
    const strip = <T extends { _editableLabel?: boolean }>(r: T) => {
      const { _editableLabel, ...rest } = r
      return rest
    }
    return {
      taxRows:
        variant === 'listed'
          ? listedRows.value.map(strip) as N2ListedTaxRow[]
          : soeRowsWithEnd.value,
      notes: {
        ...(offsetNote.value.trim() ? { offset: offsetNote.value } : {}),
        ...(conclusionNote.value.trim() ? { conclusion: conclusionNote.value } : {}),
      },
      previouslySyncedTables: syncedTables.value,
    }
  }

  function buildPayload(ctx: { wpId: string; year: number }) {
    return buildN2SyncPayload(variant, buildSnapshot(), ctx)
  }

  return {
    listedRows,
    soeRows,
    soeRowsWithEnd,
    offsetNote,
    conclusionNote,
    syncedTables,
    listedTotals,
    soeTotals,
    segments,
    columns,
    labelHeader,
    checks,
    addRow,
    removeRow,
    setCell,
    setLabel,
    serializeRows,
    restore,
    buildSnapshot,
    buildPayload,
    itemIds: ID,
    noteColumns: computed(() => n2ColumnsFor(variant)),
  }
}
