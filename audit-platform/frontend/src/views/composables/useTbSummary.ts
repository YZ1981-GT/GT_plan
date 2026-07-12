/**
 * useTbSummary - 试算平衡表（报表行次级别）域逻辑
 *
 * 从 TrialBalance.vue 拆分而来，包含：
 * - 试算平衡表数据加载（loadTbSummary）
 * - 期初/期末切换
 * - 报表类型切换（BS/IS/CF）
 * - 编辑模式（断开公式 / 恢复公式）
 * - 保存 / 导出 / 导入
 * - 右键菜单（公式/溯源/复制/汇总明细）
 * - 审定数自动重算
 *
 * @domain tb-summary
 */
import { ref, computed, type Ref, type ComputedRef } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { handleApiError } from '@/utils/errorHandler'
import { useLazyEdit } from '@/composables/useLazyEdit'

// ─── 类型 ───
export interface TbSummaryRow {
  row_code: string
  row_name: string
  unadjusted: number | null
  aje_dr: number | null
  aje_cr: number | null
  rcl_dr: number | null
  rcl_cr: number | null
  audited: number | null
  indent?: number
  formula_detached?: boolean
  _isHeader?: boolean
  _isTotal?: boolean
  [key: string]: any
}

export const TB_SUMMARY_TYPES = [
  { key: 'balance_sheet', label: '资产负债表' },
  { key: 'income_statement', label: '利润表' },
  { key: 'cash_flow', label: '现金流量表' },
] as const

export function useTbSummary(
  projectId: Ref<string> | ComputedRef<string>,
  year: Ref<number> | ComputedRef<number>,
) {
  // ─── 状态 ───
  const tbSummaryRows = ref<TbSummaryRow[]>([])
  const tbSummaryLoading = ref(false)
  const tbSumPeriod = ref<'ending' | 'opening'>('ending')
  const tbSummaryType = ref<string>('balance_sheet')
  const tbSumEditMode = ref(false)
  const tbSumOpeningSource = ref<'prior_year' | 'manual'>('prior_year')
  const tbSummaryTableRef = ref<any>(null)
  const tbSummaryMaxHeight = ref(600)

  // 右键菜单
  const tbSumCtxVisible = ref(false)
  const tbSumCtxX = ref(0)
  const tbSumCtxY = ref(0)
  const tbSumCtxRow = ref<TbSummaryRow | null>(null)
  const tbSumSelectedRows = ref<Set<number>>(new Set())

  // 编辑（lazyEdit）
  const tbSumLazyEdit = useLazyEdit()

  // 未审数列是否可编辑（仅 opening 期初或 formula_detached 时）
  const tbSumUnadjEditable = computed(() => tbSumEditMode.value && tbSumPeriod.value === 'opening')

  const tbSummaryTypes = TB_SUMMARY_TYPES

  // ─── 加载 ───
  async function loadTbSummary() {
    tbSummaryLoading.value = true
    try {
      const params: Record<string, any> = {
        year: year.value,
        report_type: tbSummaryType.value,
        period: tbSumPeriod.value,
      }
      const data = await api.get(
        `/api/projects/${projectId.value}/trial-balance/summary`,
        { params },
      )
      tbSummaryRows.value = data?.rows ?? data ?? []
      if (data?.opening_source) {
        tbSumOpeningSource.value = data.opening_source
      }
    } catch (e: any) {
      handleApiError(e, '加载试算平衡表')
    } finally {
      tbSummaryLoading.value = false
    }
  }

  // ─── 审定数重算 ───
  function recalcTbSummaryAudited() {
    for (const row of tbSummaryRows.value) {
      if (row._isHeader || row._isTotal) continue
      const unadj = Number(row.unadjusted) || 0
      const ajeDr = Number(row.aje_dr) || 0
      const ajeCr = Number(row.aje_cr) || 0
      const rclDr = Number(row.rcl_dr) || 0
      const rclCr = Number(row.rcl_cr) || 0
      row.audited = unadj + ajeDr - ajeCr + rclDr - rclCr
    }
  }

  // ─── 保存 ───
  async function saveTbSummary() {
    try {
      await api.put(
        `/api/projects/${projectId.value}/trial-balance/summary`,
        {
          year: year.value,
          report_type: tbSummaryType.value,
          period: tbSumPeriod.value,
          rows: tbSummaryRows.value,
        },
      )
      ElMessage.success('保存成功')
    } catch (e: any) {
      handleApiError(e, '保存')
    }
  }

  // ─── 导出 ───
  async function exportTbSummary() {
    try {
      const resp = await api.get(
        `/api/projects/${projectId.value}/trial-balance/summary/export`,
        {
          params: { year: year.value, report_type: tbSummaryType.value, period: tbSumPeriod.value },
          responseType: 'blob',
        },
      )
      const blob = new Blob([resp], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `试算平衡表_${tbSummaryType.value}_${tbSumPeriod.value}_${year.value}.xlsx`
      a.click()
      URL.revokeObjectURL(url)
    } catch (e: any) {
      handleApiError(e, '导出')
    }
  }

  async function exportTbSumTemplate() {
    try {
      const resp = await api.get(
        `/api/projects/${projectId.value}/trial-balance/summary/export-template`,
        {
          params: { year: year.value, report_type: tbSummaryType.value },
          responseType: 'blob',
        },
      )
      const blob = new Blob([resp], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `试算平衡表模板_${tbSummaryType.value}_${year.value}.xlsx`
      a.click()
      URL.revokeObjectURL(url)
    } catch (e: any) {
      handleApiError(e, '导出模板')
    }
  }

  // ─── 断开/恢复公式 ───
  function detachFormula(row: TbSummaryRow) {
    row.formula_detached = true
  }

  function restoreFormula(row: TbSummaryRow) {
    row.formula_detached = false
    recalcTbSummaryAudited()
  }

  // ─── 右键菜单 ───
  function showCtxMenu(event: MouseEvent, row: TbSummaryRow) {
    tbSumCtxVisible.value = true
    tbSumCtxX.value = event.clientX
    tbSumCtxY.value = event.clientY
    tbSumCtxRow.value = row
  }

  function closeCtxMenu() {
    tbSumCtxVisible.value = false
  }

  // ─── 行样式 ───
  function tbSumRowClassName({ row, rowIndex }: { row: any; rowIndex: number }) {
    const classes: string[] = []
    if (row._isHeader) classes.push('gt-tb-sum-header-row')
    if (row._isTotal) classes.push('gt-tb-sum-total-row')
    if (tbSumSelectedRows.value.has(rowIndex)) classes.push('gt-tb-sum-selected')
    return classes.join(' ')
  }

  function tbSumCellClassName({ rowIndex, columnIndex }: { rowIndex: number; columnIndex: number }) {
    if (tbSumLazyEdit.isEditing(rowIndex, columnIndex)) return 'gt-tb-editing-cell'
    return ''
  }

  return {
    // 状态
    tbSummaryRows,
    tbSummaryLoading,
    tbSumPeriod,
    tbSummaryType,
    tbSumEditMode,
    tbSumOpeningSource,
    tbSummaryTableRef,
    tbSummaryMaxHeight,
    tbSumCtxVisible,
    tbSumCtxX,
    tbSumCtxY,
    tbSumCtxRow,
    tbSumSelectedRows,
    tbSumLazyEdit,
    tbSumUnadjEditable,
    tbSummaryTypes,
    // 方法
    loadTbSummary,
    recalcTbSummaryAudited,
    saveTbSummary,
    exportTbSummary,
    exportTbSumTemplate,
    detachFormula,
    restoreFormula,
    showCtxMenu,
    closeCtxMenu,
    tbSumRowClassName,
    tbSumCellClassName,
  }
}
