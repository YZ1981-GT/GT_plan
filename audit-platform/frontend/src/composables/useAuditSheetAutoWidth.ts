/**
 * useAuditSheetAutoWidth — 审定表数值列自适应列宽（从 GtAuditSheet.vue 抽出，行为不变）
 *
 * 把各数值列的**显示值**（经组件的 display* 取值函数）投影成平铺行，交给 useAutoColumnWidth
 * 按格式化后的文本宽度算列宽。分组行（isSection）不参与。
 */
import { computed, type Ref } from 'vue'
import { useAutoColumnWidth } from '@/composables/useAutoColumnWidth'

type CellFn = (row: any) => unknown

export function useAuditSheetAutoWidth(options: {
  tableData: Ref<any[]>
  values: {
    opening_unadjusted: CellFn
    opening_audited: CellFn
    current_unadjusted: CellFn
    adj_amount: CellFn
    reclass_amount: CellFn
    audited: CellFn
    change_amount: CellFn
  }
  formatter: (v: any) => string
}) {
  const fields = Object.keys(options.values) as Array<keyof typeof options.values>
  const rows = computed(() =>
    options.tableData.value
      .filter((r: any) => !r.isSection)
      .map((r: any) => Object.fromEntries(fields.map((f) => [f, options.values[f](r)]))),
  )
  return useAutoColumnWidth({
    rows,
    columns: [
      { field: 'opening_unadjusted', header: '期初未审' },
      { field: 'opening_audited',    header: '期初审定' },
      { field: 'current_unadjusted', header: '本期未审' },
      { field: 'adj_amount',         header: '账项调整' },
      { field: 'reclass_amount',     header: '重分类' },
      { field: 'audited',            header: '审定数' },
      { field: 'change_amount',      header: '变动额' },
    ],
    formatter: options.formatter,
  })
}
