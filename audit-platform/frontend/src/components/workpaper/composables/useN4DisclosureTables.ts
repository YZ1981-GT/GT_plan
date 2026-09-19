/**
 * useN4DisclosureTables — N4 税金及附加披露表（上市）编制模型
 *
 * 源模板权威 = `backend/wp_templates/N/N4 税金及附加.xlsx` 的
 * `附注披露信息（上市公司）`（A1:L18）：1 张 3 列表（项目 / 本期发生额 / 上期发生额）
 * + `合  计` 公式行 + R18 说明「各项税金及附加的计缴标准详见附注四、税项。」
 *
 * 🔴 **国企版不披露**（源模板 `附注披露信息：无`），故本 composable 只服务上市版。
 * 🔴 源模板没有的列（变动额 / 变动率 / 变动原因）不再提供 —— 那是审计过程，
 * 属 N4-1 审定表与 N4-2 明细表。
 */
import { computed, ref, type Ref } from 'vue'
import {
  N4_TOTAL_LABEL,
  buildN4ListedColumns,
  buildN4SyncPayload,
  type N4DisclosureSnapshot,
  type N4TaxRow,
} from './n4NoteSectionMap'
import { runN4ListedChecks, type WpCheckResult } from './nCycleTaxConsistency'
import { nz, sumNullable, type NullableAmount } from './shared/disclosureConsistency'
import type { WpSegColumn, WpSegment } from './shared/disclosureSegmentTypes'

/** 默认税费项目（附注模板 五、63 rows；源模板 R8~R16 引用 N4-1 审定表） */
export const N4_TAX_ITEMS = [
  '消费税',
  '城市维护建设税',
  '教育费附加',
  '资源税',
  '房产税',
  '土地使用税',
  '车船使用税',
  '印花税',
] as const

export interface N4RowModel {
  item: string
  current: NullableAmount
  prior: NullableAmount
  _editableLabel?: boolean
}

export function n4DisclosureItemIds() {
  const p = 'N4-disclosure-listed'
  return {
    taxes: `${p}-taxes`,
    standardNote: `${p}-standard-note`,
    conclusion: `${p}-conclusion`,
    syncedTables: `${p}-synced-tables`,
  } as const
}

const AMT = 'amount' as const

export function n4SegColumns(): WpSegColumn[] {
  return [
    { key: 'current', label: '本期发生额', format: AMT, minWidth: 170 },
    { key: 'prior', label: '上期发生额', format: AMT, minWidth: 170 },
  ]
}

/** 标签列表头（源模板 A7 `项  目`） */
export const N4_LABEL_HEADER = '项  目'

function parseJsonArray<T>(raw: unknown): T[] | null {
  if (typeof raw !== 'string' || !raw) return null
  try {
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? (parsed as T[]) : null
  } catch {
    return null
  }
}

export interface UseN4DisclosureTablesOptions {
  allResponses: Ref<Map<string, { conclusion?: string | null; remark?: string | null }>>
}

export function useN4DisclosureTables(opts: UseN4DisclosureTablesOptions) {
  const { allResponses } = opts
  const ID = n4DisclosureItemIds()

  const rows = ref<N4RowModel[]>([])
  const standardNote = ref('')
  const conclusionNote = ref('')
  const syncedTables = ref<string[]>([])

  function restore(): void {
    const saved = parseJsonArray<N4RowModel>(allResponses.value.get(ID.taxes)?.conclusion)
    rows.value = saved?.length
      ? saved
      : N4_TAX_ITEMS.map((item) => ({ item, current: null, prior: null }))
    standardNote.value = allResponses.value.get(ID.standardNote)?.remark || ''
    conclusionNote.value = allResponses.value.get(ID.conclusion)?.remark || ''
    syncedTables.value =
      parseJsonArray<string>(allResponses.value.get(ID.syncedTables)?.conclusion) ?? []
  }

  /** 合计（源模板 =SUM(B8:B16) / =SUM(C8:C16)） */
  const totals = computed(() => ({
    current: sumNullable(rows.value.map((r) => nz(r.current))),
    prior: sumNullable(rows.value.map((r) => nz(r.prior))),
  }))

  const segments = computed<WpSegment[]>(() => [
    {
      key: 'main',
      label: '',
      rows: rows.value as unknown as WpSegment['rows'],
      subtotal: { current: totals.value.current, prior: totals.value.prior },
      subtotalLabel: N4_TOTAL_LABEL,
    },
  ])

  const columns = computed(() => n4SegColumns())

  const checks = computed<WpCheckResult[]>(() =>
    runN4ListedChecks(
      rows.value.map((r) => ({ item: r.item, current: nz(r.current), prior: nz(r.prior) })),
      totals.value,
    ),
  )

  function addRow(): void {
    rows.value = [...rows.value, { item: '', current: null, prior: null, _editableLabel: true }]
  }

  function removeRow(index: number): void {
    rows.value = rows.value.filter((_, i) => i !== index)
  }

  function setCell(index: number, key: string, value: number | string): void {
    const row = rows.value[index] as unknown as Record<string, unknown>
    if (!row) return
    row[key] = value
  }

  function setLabel(index: number, value: string): void {
    const row = rows.value[index]
    if (!row) return
    row.item = value
  }

  function serializeRows(): string {
    return JSON.stringify(rows.value)
  }

  function buildSnapshot(): N4DisclosureSnapshot {
    return {
      taxRows: rows.value.map(({ _editableLabel, ...rest }) => rest) as N4TaxRow[],
      notes: {
        ...(standardNote.value.trim() ? { standard: standardNote.value } : {}),
        ...(conclusionNote.value.trim() ? { conclusion: conclusionNote.value } : {}),
      },
      previouslySyncedTables: syncedTables.value,
    }
  }

  function buildPayload(ctx: { wpId: string; year: number }) {
    return buildN4SyncPayload('listed', buildSnapshot(), ctx)
  }

  return {
    rows,
    standardNote,
    conclusionNote,
    syncedTables,
    totals,
    segments,
    columns,
    labelHeader: computed(() => N4_LABEL_HEADER),
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
    noteColumns: computed(() => buildN4ListedColumns()),
  }
}
