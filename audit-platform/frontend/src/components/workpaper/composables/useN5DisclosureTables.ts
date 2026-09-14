/**
 * useN5DisclosureTables — N5 所得税费用披露表（上市 / 国企）编制模型
 *
 * 源模板权威 = `backend/wp_templates/N/N5 所得税费用.xlsx`
 * （`附注披露信息（上市公司）` A1:L29 / `附注披露信息（国企` A1:IU32）：
 *
 * | 变体 | 表（1）所得税费用明细 | 表（2）调整过程 |
 * |---|---|---|
 * | 上市 | 2 行 + `合  计`（=SUM(C9:C10)） | 12 行 + **`所得税费用` 勾稽行**（注 1） |
 * | 国企 | 3 行 + `合  计`（=SUM(C8:C10)） | 9 行 + `合  计` |
 *
 * 🔴 **表（2）末行求和口径排除首行 `利润总额`**：源模板注 1 写「所得税费用等于
 * **第二行至倒数第二行**之和」——首行是利润总额（起算点），把它算进去会恒不平。
 * 🔴 表（2）末行是**公式行**（只读），不由用户录入。
 */
import { computed, ref, type Ref } from 'vue'
import {
  N5_LISTED_TAIL_LABEL,
  N5_TOTAL_LABEL,
  buildN5SyncPayload,
  n5ColumnsFor,
  type N5DisclosureSnapshot,
  type N5DisclosureVariant,
  type N5Row,
} from './n5NoteSectionMap'
import { runN5Checks, type WpCheckResult } from './nCycleTaxConsistency'
import { nz, sumNullable, type NullableAmount } from './shared/disclosureConsistency'
import type { WpSegColumn, WpSegment } from './shared/disclosureSegmentTypes'

// ─── 行骨架（逐字取自附注模板 rows，与源模板动态引用行对应）─────────────────

export const N5_LISTED_DETAIL_ITEMS = [
  '按税法及相关规定计算的当期所得税',
  '递延所得税费用',
] as const

export const N5_LISTED_RECONCILE_ITEMS = [
  '利润总额',
  '按法定（或适用）税率计算的所得税费用（利润总额*XX%）',
  '某些子公司适用不同税率的影响',
  '对以前期间当期所得税的调整',
  '权益法核算的合营企业和联营企业损益',
  '无须纳税的收入（以“-”填列）',
  '不可抵扣的成本、费用和损失',
  '税率变动对期初递延所得税余额的影响',
  '利用以前年度未确认可抵扣亏损和可抵扣暂时性差异的纳税影响（以“-”填列）',
  '未确认可抵扣亏损和可抵扣暂时性差异的纳税影响',
  '研究开发费加成扣除的纳税影响（以“-”填列）',
  '其他',
] as const

export const N5_SOE_DETAIL_ITEMS = ['当期所得税费用', '递延所得税调整', '其他'] as const

export const N5_SOE_RECONCILE_ITEMS = [
  '利润总额',
  '按适定/适用税率计算的所得税费用',
  '子公司适用不同税率的影响',
  '调整以前期间所得税的影响',
  '非应税收入的影响',
  '不可抵扣的成本、费用和损失的影响',
  '使用前期未确认递延所得税资产的可抵扣亏损的影响',
  '本期未确认递延所得税资产的可抵扣暂时性差异或可抵扣亏损的影响',
  '其他',
] as const

/** 表（2）首行 = 起算点，不参与末行求和（源模板注 1） */
export const N5_RECONCILE_START_LABEL = '利润总额'

export interface N5RowModel {
  item: string
  current: NullableAmount
  prior: NullableAmount
  _editableLabel?: boolean
}

export function n5DisclosureItemIds(variant: N5DisclosureVariant) {
  const p = `N5-disclosure-${variant}`
  return {
    detail: `${p}-detail`,
    reconcile: `${p}-reconcile`,
    detailNote: `${p}-detail-note`,
    reconcileNote: `${p}-reconcile-note`,
    conclusion: `${p}-conclusion`,
    syncedTables: `${p}-synced-tables`,
  } as const
}

const AMT = 'amount' as const

export function n5SegColumns(): WpSegColumn[] {
  return [
    { key: 'current', label: '本期发生额', format: AMT, minWidth: 170 },
    { key: 'prior', label: '上期发生额', format: AMT, minWidth: 170 },
  ]
}

/** 标签列表头（源模板 `项  目`） */
export const N5_LABEL_HEADER = '项  目'

function parseJsonArray<T>(raw: unknown): T[] | null {
  if (typeof raw !== 'string' || !raw) return null
  try {
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? (parsed as T[]) : null
  } catch {
    return null
  }
}

function defaults(items: readonly string[]): N5RowModel[] {
  return items.map((item) => ({ item, current: null, prior: null }))
}

export interface UseN5DisclosureTablesOptions {
  variant: N5DisclosureVariant
  allResponses: Ref<Map<string, { conclusion?: string | null; remark?: string | null }>>
}

export function useN5DisclosureTables(opts: UseN5DisclosureTablesOptions) {
  const { variant, allResponses } = opts
  const ID = n5DisclosureItemIds(variant)

  const detailRows = ref<N5RowModel[]>([])
  const reconcileRows = ref<N5RowModel[]>([])
  const detailNote = ref('')
  const reconcileNote = ref('')
  const conclusionNote = ref('')
  const syncedTables = ref<string[]>([])

  const DETAIL_ITEMS = variant === 'listed' ? N5_LISTED_DETAIL_ITEMS : N5_SOE_DETAIL_ITEMS
  const RECONCILE_ITEMS =
    variant === 'listed' ? N5_LISTED_RECONCILE_ITEMS : N5_SOE_RECONCILE_ITEMS

  function restore(): void {
    detailRows.value =
      parseJsonArray<N5RowModel>(allResponses.value.get(ID.detail)?.conclusion) ?? defaults(DETAIL_ITEMS)
    if (!detailRows.value.length) detailRows.value = defaults(DETAIL_ITEMS)
    reconcileRows.value =
      parseJsonArray<N5RowModel>(allResponses.value.get(ID.reconcile)?.conclusion)
      ?? defaults(RECONCILE_ITEMS)
    if (!reconcileRows.value.length) reconcileRows.value = defaults(RECONCILE_ITEMS)
    detailNote.value = allResponses.value.get(ID.detailNote)?.remark || ''
    reconcileNote.value = allResponses.value.get(ID.reconcileNote)?.remark || ''
    conclusionNote.value = allResponses.value.get(ID.conclusion)?.remark || ''
    syncedTables.value =
      parseJsonArray<string>(allResponses.value.get(ID.syncedTables)?.conclusion) ?? []
  }

  // ── 表（1）合计（源模板 =SUM(C9:C10) / =SUM(C8:C10)）──────────────────────

  const detailTotals = computed(() => ({
    current: sumNullable(detailRows.value.map((r) => nz(r.current))),
    prior: sumNullable(detailRows.value.map((r) => nz(r.prior))),
  }))

  /**
   * 表（2）参与末行求和的行 = 排除首行 `利润总额`（源模板注 1「第二行至倒数第二行」）。
   * 用标签判定而非固定下标 —— 审计师可能删掉不适用行。
   */
  const reconcileSumRows = computed<N5RowModel[]>(() =>
    reconcileRows.value.filter(
      (r) => String(r.item ?? '').replace(/\s+/g, '') !== N5_RECONCILE_START_LABEL,
    ),
  )

  /** 表（2）末行（公式行）：上市 = 所得税费用 / 国企 = 合计 */
  const reconcileTail = computed(() => ({
    current: sumNullable(reconcileSumRows.value.map((r) => nz(r.current))),
    prior: sumNullable(reconcileSumRows.value.map((r) => nz(r.prior))),
  }))

  const tailLabel = computed(() =>
    variant === 'listed' ? N5_LISTED_TAIL_LABEL : N5_TOTAL_LABEL,
  )

  // ── 渲染段 ────────────────────────────────────────────────────────────────

  const asSegRows = (rows: readonly object[]): WpSegment['rows'] =>
    rows as unknown as WpSegment['rows']

  const detailSegments = computed<WpSegment[]>(() => [
    {
      key: 'detail',
      label: '',
      rows: asSegRows(detailRows.value),
      subtotal: { current: detailTotals.value.current, prior: detailTotals.value.prior },
      subtotalLabel: N5_TOTAL_LABEL,
    },
  ])

  const reconcileSegments = computed<WpSegment[]>(() => [
    {
      key: 'reconcile',
      label: '',
      rows: asSegRows(reconcileRows.value),
      subtotal: { current: reconcileTail.value.current, prior: reconcileTail.value.prior },
      subtotalLabel: tailLabel.value,
    },
  ])

  const columns = computed(() => n5SegColumns())

  // ── 勾稽 ──────────────────────────────────────────────────────────────────

  const checks = computed<WpCheckResult[]>(() =>
    runN5Checks(variant, {
      detailRows: detailRows.value.map((r) => ({
        item: r.item,
        current: nz(r.current),
        prior: nz(r.prior),
      })),
      detailTotals: detailTotals.value,
      reconcileRows: reconcileSumRows.value.map((r) => ({
        item: r.item,
        current: nz(r.current),
        prior: nz(r.prior),
      })),
      reconcileTail: reconcileTail.value,
    }),
  )

  // ── 行增删改 ──────────────────────────────────────────────────────────────

  function rowsRef(table: 'detail' | 'reconcile') {
    return table === 'detail' ? detailRows : reconcileRows
  }

  function addRow(table: 'detail' | 'reconcile'): void {
    const target = rowsRef(table)
    target.value = [
      ...target.value,
      { item: '', current: null, prior: null, _editableLabel: true },
    ]
  }

  function removeRow(table: 'detail' | 'reconcile', index: number): void {
    const target = rowsRef(table)
    target.value = target.value.filter((_, i) => i !== index)
  }

  function setCell(
    table: 'detail' | 'reconcile',
    index: number,
    key: string,
    value: number | string,
  ): void {
    const row = rowsRef(table).value[index] as unknown as Record<string, unknown>
    if (!row) return
    row[key] = value
  }

  function setLabel(table: 'detail' | 'reconcile', index: number, value: string): void {
    const row = rowsRef(table).value[index]
    if (!row) return
    row.item = value
  }

  function serializeRows(table: 'detail' | 'reconcile'): string {
    return JSON.stringify(rowsRef(table).value)
  }

  // ── 同步载荷 ──────────────────────────────────────────────────────────────

  function buildSnapshot(): N5DisclosureSnapshot {
    const strip = (r: N5RowModel): N5Row => {
      const { _editableLabel, ...rest } = r
      return rest
    }
    return {
      detailRows: detailRows.value.map(strip),
      // 载荷只列示明细行，末行由 `reconcileTail` 给出（公式行不双真源）
      reconcileRows: reconcileRows.value.map(strip),
      reconcileTail: reconcileTail.value,
      notes: {
        ...(detailNote.value.trim() ? { detail: detailNote.value } : {}),
        ...(reconcileNote.value.trim() ? { reconcile: reconcileNote.value } : {}),
        ...(conclusionNote.value.trim() ? { conclusion: conclusionNote.value } : {}),
      },
      previouslySyncedTables: syncedTables.value,
    }
  }

  function buildPayload(ctx: { wpId: string; year: number }) {
    return buildN5SyncPayload(variant, buildSnapshot(), ctx)
  }

  return {
    detailRows,
    reconcileRows,
    detailNote,
    reconcileNote,
    conclusionNote,
    syncedTables,
    detailTotals,
    reconcileSumRows,
    reconcileTail,
    tailLabel,
    detailSegments,
    reconcileSegments,
    columns,
    labelHeader: computed(() => N5_LABEL_HEADER),
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
    noteColumns: computed(() => n5ColumnsFor(variant)),
  }
}
