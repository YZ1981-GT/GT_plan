import { ref, type ComputedRef, type Ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '@/services/apiProxy'
import { reports as P_reports } from '@/services/apiPaths'
import { handleApiError } from '@/utils/errorHandler'
import { fmtAmount } from '@/utils/formatters'
import type { ReportRow } from '@/services/auditPlatformApi'
import type { useCellSelection } from '@/composables/useCellSelection'
import type { usePenetrate } from '@/composables/usePenetrate'

// ─── Interfaces ─────────────────────────────────────────────────────────────

export interface UseReportContextMenuOptions {
  projectId: ComputedRef<string>
  year: ComputedRef<number>
  activeTab: Ref<string>
  rows: Ref<ReportRow[]>
  reportMode: Ref<string>
  isConsolidated: ComputedRef<boolean>
  fetchReport: () => Promise<void>
  getRowType: (row: ReportRow) => string
  goToNote: (rowCode: string) => void
  showFormulaManager: Ref<boolean>
  openTrustScore: (context: string) => void
  rvCtx: ReturnType<typeof useCellSelection>
  rvPenetrate: ReturnType<typeof usePenetrate>
  // Cross-composable dependency: onDrilldown from useReportDrilldown
  onDrilldown: (row: ReportRow) => Promise<void>
}

export interface UseReportContextMenuReturn {
  consolBreakdownVisible: Ref<boolean>
  consolBreakdownAccountCode: Ref<string>
  onRvCtxViewConsolBreakdown: () => void

  showCellFormulaDetail: Ref<boolean>
  cellDetailWpCode: Ref<string>
  cellDetailSheet: Ref<string>
  cellDetailLabel: Ref<string>
  onRvCtxViewFormulaSource: () => void
  onCellDetailNavigate: (uri: string) => void

  onRvCellClick: (row: any, column: any, _cell: HTMLElement, event: MouseEvent) => void
  onRvCellDblClick: (row: any, column: any) => void
  onRvCellContextMenu: (row: any, column: any, _cell: HTMLElement, event: MouseEvent) => void
  onRvCtxCopy: () => void
  onRvCtxDrillDown: () => void
  onRvCtxFormula: () => void
  onRvCtxTrustScore: () => void
  onRvCtxGoNote: () => void
  onRvCtxOpenWorkpaper: () => Promise<void>
  onRvCtxViewAdjustments: () => void
  onRvCtxSum: () => void
  onRvCtxCompare: () => void
  onRowNameClick: (row: ReportRow) => void
  openWorkpaper: (wpId: string) => void
}

// ─── Composable ─────────────────────────────────────────────────────────────

export function useReportContextMenu(options: UseReportContextMenuOptions): UseReportContextMenuReturn {
  const {
    projectId, year, activeTab, rows, reportMode,
    isConsolidated: _isConsolidated, fetchReport, getRowType,
    goToNote, showFormulaManager, openTrustScore,
    rvCtx, rvPenetrate, onDrilldown,
  } = options

  const router = useRouter()

  // ─── Consol Breakdown ─────────────────────────────────────────────────────
  const consolBreakdownVisible = ref(false)
  const consolBreakdownAccountCode = ref('')

  function onRvCtxViewConsolBreakdown() {
    rvCtx.closeContextMenu()
    const row = rvCtx.contextMenu.rowData
    if (!row?.row_code) {
      ElMessage.info('请在数据行上右键')
      return
    }
    consolBreakdownAccountCode.value = row.row_code
    consolBreakdownVisible.value = true
  }

  // ─── Formula Source ───────────────────────────────────────────────────────
  const showCellFormulaDetail = ref(false)
  const cellDetailWpCode = ref('')
  const cellDetailSheet = ref('')
  const cellDetailLabel = ref('')

  function onRvCtxViewFormulaSource() {
    rvCtx.closeContextMenu()
    const row = rvCtx.contextMenu.rowData
    if (!row?.row_code) {
      ElMessage.info('请在数据行上右键')
      return
    }
    cellDetailWpCode.value = row.row_code
    cellDetailSheet.value = ''
    cellDetailLabel.value = ''
    showCellFormulaDetail.value = true
  }

  function onCellDetailNavigate(uri: string) {
    showCellFormulaDetail.value = false
    const parts = uri.split(':')
    const mod = parts[0]?.toUpperCase()
    if (mod === 'WP' && parts[1]) {
      router.push({ name: 'WorkpaperEditor', params: { id: projectId.value }, query: { wp: parts[1] } })
    } else if (mod === 'NOTE') {
      router.push({ name: 'DisclosureEditor', params: { id: projectId.value } })
    } else if (mod === 'TB') {
      router.push({ path: `/projects/${projectId.value}/trial-balance` })
    }
  }

  // ─── Cell Event Handlers ──────────────────────────────────────────────────
  function onRvCellClick(row: any, column: any, _cell: HTMLElement, event: MouseEvent) {
    rvCtx.closeContextMenu()
    const rowIdx = rows.value.indexOf(row)
    const mainColLabels = ['序号', '项目', '本期金额', '上期金额']
    let colIdx = mainColLabels.indexOf(column.label)
    if (colIdx < 0 && column.index !== undefined) {
      colIdx = column.index
    }
    if (rowIdx < 0 || colIdx < 0) return
    const value = row.current_period_amount ?? row[column.property] ?? ''
    rvCtx.selectCell(rowIdx, colIdx, value, event.ctrlKey || event.metaKey, event.shiftKey)
    rvCtx.contextMenu.rowData = row
    rvCtx.contextMenu.itemName = row.row_name || ''
  }

  function onRvCellDblClick(row: any, column: any) {
    // 权益表/减值表：双击编辑单元格
    if (activeTab.value === 'equity_statement' || activeTab.value === 'impairment_provision') {
      if (column.label === '项目') return
      const colKey = column.property || column.label
      ElMessageBox.prompt(`编辑「${row.row_name}」的「${column.label}」`, '编辑单元格', {
        inputValue: String(row.current_period_amount || 0),
        inputPattern: /^-?\d*\.?\d*$/,
        inputErrorMessage: '请输入数字',
        confirmButtonText: '保存',
        cancelButtonText: '取消',
      }).then(({ value }) => {
        const numVal = value ? parseFloat(value) : null
        api.put(`/api/projects/${projectId.value}/reports/cell`, {
          row_code: row.row_code || '',
          column_key: colKey,
          value: numVal,
        }, { params: { year: year.value, report_type: activeTab.value } })
          .then(() => { ElMessage.success('已保存'); fetchReport() })
          .catch((e: any) => handleApiError(e, '保存'))
      }).catch(() => { /* 取消 */ })
      return
    }
    // 主表：双击金额穿透
    const amountCols = ['本期金额', '上期金额']
    if (amountCols.includes(column.label) && row.row_code) {
      rvPenetrate.toReportRow(activeTab.value, row.row_code)
    }
  }

  function onRvCellContextMenu(row: any, column: any, _cell: HTMLElement, event: MouseEvent) {
    const rowIdx = rows.value.indexOf(row)
    const mainColLabels = ['序号', '项目', '本期金额', '上期金额']
    let colIdx = mainColLabels.indexOf(column.label)
    if (colIdx < 0 && column.index !== undefined) colIdx = column.index
    if (rowIdx >= 0 && colIdx >= 0 && !rvCtx.isCellSelected(rowIdx, colIdx)) {
      const value = row.current_period_amount ?? row[column.property] ?? ''
      rvCtx.selectCell(rowIdx, colIdx, value, false)
    }
    rvCtx.contextMenu.rowData = row
    rvCtx.contextMenu.itemName = row.row_name || ''
    rvCtx.openContextMenu(event, rvCtx.contextMenu.itemName, row)
  }

  // ─── Right-click Action Handlers ──────────────────────────────────────────
  function onRvCtxCopy() {
    rvCtx.closeContextMenu()
    rvCtx.copySelectedValues()
    ElMessage.success('已复制')
  }

  function onRvCtxDrillDown() {
    rvCtx.closeContextMenu()
    if (rvCtx.contextMenu.rowData) onDrilldown(rvCtx.contextMenu.rowData)
  }

  function onRvCtxFormula() {
    rvCtx.closeContextMenu()
    showFormulaManager.value = true
  }

  function onRvCtxTrustScore() {
    rvCtx.closeContextMenu()
    const row = rvCtx.contextMenu.rowData
    const context = `report:${activeTab.value}|${row?.row_code || ''}`
    openTrustScore(context)
  }

  function onRvCtxGoNote() {
    rvCtx.closeContextMenu()
    if (rvCtx.contextMenu.rowData?.row_code) goToNote(rvCtx.contextMenu.rowData.row_code)
  }

  async function onRvCtxOpenWorkpaper() {
    rvCtx.closeContextMenu()
    const row = rvCtx.contextMenu.rowData
    if (!row?.row_code) return
    try {
      const data = await api.get(P_reports.relatedWorkpapers(projectId.value, year.value, activeTab.value, row.row_code))
      const wps = (data as any)?.workpapers || []
      if (wps.length === 1) {
        rvPenetrate.toWorkpaperEditor(wps[0].id)
      } else if (wps.length > 1) {
        ElMessage.info(`该行关联 ${wps.length} 个底稿：${wps.map((w: any) => w.wp_code).join(', ')}`)
      } else {
        ElMessage.info('该行暂无关联底稿')
      }
    } catch { ElMessage.warning('查询关联底稿失败') }
  }

  function onRvCtxViewAdjustments() {
    rvCtx.closeContextMenu()
    const row = rvCtx.contextMenu.rowData
    if (!row?.row_code) {
      ElMessage.info('请在数据行上右键')
      return
    }
    router.push({
      path: `/projects/${projectId.value}/trial-balance`,
      query: { highlight_row: row.row_code, year: String(year.value) },
    })
  }

  function onRvCtxSum() {
    rvCtx.closeContextMenu()
    const sum = rvCtx.sumSelectedValues()
    ElMessage.info(`选中 ${rvCtx.selectedCells.value.length} 格，合计：${fmtAmount(sum)}`)
  }

  function onRvCtxCompare() {
    rvCtx.closeContextMenu()
    if (rvCtx.selectedCells.value.length < 2) return
    const vals = rvCtx.selectedCells.value.map(c => Number(c.value) || 0)
    const diff = vals[0] - vals[1]
    ElMessage.info(`差异：${fmtAmount(diff)}`)
  }

  /** 行名点击穿透到试算表对应科目 */
  function onRowNameClick(row: ReportRow) {
    if (!row.row_code || row.is_total_row || getRowType(row) === 'header') return
    router.push({
      path: `/projects/${projectId.value}/trial-balance`,
      query: { highlight_row: row.row_code, year: String(year.value) },
    })
  }

  function openWorkpaper(wpId: string) {
    router.push({ name: 'WorkpaperEditor', params: { projectId: projectId.value, wpId } })
  }

  return {
    consolBreakdownVisible,
    consolBreakdownAccountCode,
    onRvCtxViewConsolBreakdown,

    showCellFormulaDetail,
    cellDetailWpCode,
    cellDetailSheet,
    cellDetailLabel,
    onRvCtxViewFormulaSource,
    onCellDetailNavigate,

    onRvCellClick,
    onRvCellDblClick,
    onRvCellContextMenu,
    onRvCtxCopy,
    onRvCtxDrillDown,
    onRvCtxFormula,
    onRvCtxTrustScore,
    onRvCtxGoNote,
    onRvCtxOpenWorkpaper,
    onRvCtxViewAdjustments,
    onRvCtxSum,
    onRvCtxCompare,
    onRowNameClick,
    openWorkpaper,
  }
}
