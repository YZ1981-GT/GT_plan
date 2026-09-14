/**
 * useAuditSheetColumns — 审定表动态列分组 + 期初区折叠（spec workpaper-frontend-large-component-split, Req 3）
 *
 * 从 GtAuditSheet.vue 抽出：
 * - isDynamicColumns / dynamicColumnDefs computed
 * - openingGroupCollapsed ref（期初区折叠状态）
 * - columnGroups computed（按列位置分期初/本期变动/期末区）
 *
 * 铁律：行为零变更、保响应式（ref/computed）；依赖单向（主组件 → composable → htmlData getter）；
 *       composable 之间不互相 import。
 */
import { ref, computed } from 'vue'
import type { AuditSheetHtmlData } from '@/components/workpaper/auditSheetTypes'

export function useAuditSheetColumns(options: {
  /** htmlData 取值（getter，保持响应式） */
  htmlData: () => AuditSheetHtmlData | undefined
}) {
  const { htmlData } = options

  // ─── 动态列模式（多列明细表）───
  const isDynamicColumns = computed<boolean>(() => {
    const defs = htmlData()?.column_defs
    return Array.isArray(defs) && defs.length > 0
  })
  const dynamicColumnDefs = computed(() => isDynamicColumns.value ? (htmlData()?.column_defs ?? []) : [])

  /** 期初区折叠状态（默认收起，减少水平滚动） */
  const openingGroupCollapsed = ref(true)

  /**
   * 列分组：按列位置自动分为期初区/本期变动区/期末区。
   * 规则：找到"期初审定数"列 → 其及之前的列全为期初区；
   *       找到"期末未审数"/"期末余额" → 其及之后的列全为期末区；
   *       中间的列为本期变动区。
   * 如果找不到分界点 → 全部放 current 不折叠。
   */
  const columnGroups = computed(() => {
    const cols = dynamicColumnDefs.value
    if (cols.length <= 8) {
      // 列数不多不需要折叠
      return { opening: [] as typeof cols, current: cols, closing: [] as typeof cols }
    }
    // 找期初审定数列（期初区的最后一列）
    const openingEndIdx = cols.findIndex(c => c.label.includes('期初审定'))
    // 找期末未审数/期末余额列（期末区的第一列）
    const closingStartIdx = cols.findIndex(c => c.label.includes('期末未审') || c.label.includes('期末余额'))

    if (openingEndIdx < 0 || closingStartIdx < 0 || closingStartIdx <= openingEndIdx) {
      // 找不到有效分界点 → 不折叠
      return { opening: [] as typeof cols, current: cols, closing: [] as typeof cols }
    }

    const opening = cols.slice(0, openingEndIdx + 1)
    const current = cols.slice(openingEndIdx + 1, closingStartIdx)
    const closing = cols.slice(closingStartIdx)
    return { opening, current, closing }
  })

  return {
    isDynamicColumns,
    dynamicColumnDefs,
    openingGroupCollapsed,
    columnGroups,
  }
}
