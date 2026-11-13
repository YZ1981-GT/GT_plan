import { computed, nextTick, type Ref } from 'vue'
import { usePreferredFixedColumns } from '@/composables/usePreferredFixedColumns'
import type { DisplayMeasureKind, RatioScale } from '@/types/displayMeasure'

const DISPLAY_MEASURE_KINDS = new Set<DisplayMeasureKind>([
  'amount', 'quantity', 'count', 'ratio', 'exchange_rate', 'unit_price', 'text',
])
const RATIO_SCALES = new Set<RatioScale>(['fraction', 'percent_points'])

type TableColumn = { key: string; label: string }

/**
 * 单体附注当前投影表的度量/固定列视图（platform-global-display-settings-closure 6A/5）。
 *
 * 元数据只读 `activeTableData` 的服务端 catalog 字段；未匹配或不合法时不猜金额、不开放固定列。
 * 放在独立 composable 以保持 DisclosureEditor 的行数门，同时让列身份/显示规则有单一入口。
 */
export function useNoteTableMeasureDisplay(activeTableData: Ref<any>, tableRef: Ref<any>) {
  const metadataValid = computed(() => {
    const table = activeTableData.value
    const width = Array.isArray(table?.headers) ? table.headers.length : 0
    return table?.measure_status === 'matched'
      && width > 0
      && [table.column_ids, table.column_kinds, table.column_ratio_scales].every((value) => Array.isArray(value) && value.length === width)
      && table.column_ids.every((value: unknown) => typeof value === 'string' && value.length > 0)
  })

  function measureKind(headerIdx: number): DisplayMeasureKind | null {
    if (!metadataValid.value) return null
    const value = activeTableData.value?.column_kinds?.[headerIdx]
    return DISPLAY_MEASURE_KINDS.has(value) ? value : null
  }

  function ratioScale(headerIdx: number): RatioScale | null {
    if (measureKind(headerIdx) !== 'ratio') return null
    const value = activeTableData.value?.column_ratio_scales?.[headerIdx]
    return RATIO_SCALES.has(value) ? value : null
  }

  function columnKey(headerIdx: number): string {
    if (headerIdx === 0) return 'label'
    return String(activeTableData.value?.column_ids?.[headerIdx] || '')
  }

  const fixedPageKey = computed(() => (
    metadataValid.value && activeTableData.value?.table_id
      ? `disclosure-editor:${activeTableData.value.table_id}`
      : ''
  ))
  const fixedColumns = computed<TableColumn[]>(() => !metadataValid.value ? [] : (activeTableData.value?.headers || [])
    .map((label: unknown, index: number) => ({ key: columnKey(index), label: String(label || `第${index + 1}列`) }))
    .filter((column: TableColumn) => !!column.key))
  const mandatoryKeys = computed(() => fixedColumns.value.length ? ['label'] : [])
  const fixed = usePreferredFixedColumns({
    pageKey: fixedPageKey,
    allowedColumns: () => fixedColumns.value.map((column) => column.key),
    mandatoryColumns: mandatoryKeys,
  })

  function fixedFor(headerIdx: number): 'left' | false {
    const key = columnKey(headerIdx)
    return key ? fixed.fixedFor(key) : false
  }

  function onFixedColumnsChange(): void {
    nextTick(() => tableRef.value?.doLayout?.())
  }

  return {
    measureKind,
    ratioScale,
    columnKey,
    fixedPageKey,
    fixedColumns,
    mandatoryKeys,
    fixedFor,
    onFixedColumnsChange,
  }
}
