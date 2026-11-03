import { ref, type ComputedRef, type Ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { reports as P_reports } from '@/services/apiPaths'
import { handleApiError } from '@/utils/errorHandler'
import { fmtAmount } from '@/utils/formatters'
import type { ReportRow } from '@/services/auditPlatformApi'
import { MISSING_AUDIT_YEAR_MESSAGE } from '@/composables/useProjectAuditYear'
import type { useCellSelection } from '@/composables/useCellSelection'
import type { usePenetrate } from '@/composables/usePenetrate'

// ─── Interfaces ─────────────────────────────────────────────────────────────

export interface UseReportContextMenuOptions {
  projectId: ComputedRef<string>
  /** 审计年度；项目没填为 null ⇒ 改单元格 / 查关联底稿提示去填年度，跳转不带 year */
  year: ComputedRef<number | null>
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
  /** 权益矩阵单元格取值（与 ReportEquityTable 一致） */
  eqCellVal?: (row: any, colKey: string, yearKey?: 'current_year' | 'prior_year') => any
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
  /** 权益表 / 减值表格内编辑提交（ReportEquityTable / ReportImpairmentTable 的 cell-edit） */
  onRvCellEdit: (row: any, columnKey: string, value: number | null, yearKey?: 'current_year' | 'prior_year') => void
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
    projectId, year, activeTab, rows, reportMode: _reportMode,
    isConsolidated: _isConsolidated, fetchReport, getRowType,
    goToNote, showFormulaManager, openTrustScore,
    rvCtx, rvPenetrate, onDrilldown, eqCellVal,
  } = options

  const router = useRouter()

  function parseEquityEditTarget(column: any): {
    columnKey: string
    yearKey: 'current_year' | 'prior_year'
    uiColKey: string
  } | null {
    const raw = String(column?.property || '')
    if (raw.startsWith('cy:')) {
      return { columnKey: raw, yearKey: 'current_year', uiColKey: raw.slice(3) }
    }
    if (raw.startsWith('py:')) {
      return { columnKey: raw, yearKey: 'prior_year', uiColKey: raw.slice(3) }
    }
    return null
  }

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
    let value: unknown = row.current_period_amount ?? row[column.property] ?? ''
    if (activeTab.value === 'equity_statement' && eqCellVal) {
      const target = parseEquityEditTarget(column)
      if (target) value = eqCellVal(row, target.uiColKey, target.yearKey)
    }
    rvCtx.selectCell(rowIdx, colIdx, value, event.ctrlKey || event.metaKey, event.shiftKey)
    rvCtx.contextMenu.rowData = row
    rvCtx.contextMenu.itemName = row.row_name || ''
  }

  function onRvCellDblClick(row: any, column: any) {
    // 权益表 / 减值表：格内编辑（ReportMatrixCell，提交走 onRvCellEdit），双击不再弹输入框（spec excel-style-table-editing 5.4）
    if (activeTab.value === 'equity_statement' || activeTab.value === 'impairment_provision') return
    // 主表：双击金额穿透
    const amountCols = ['本期金额', '上期金额']
    if (amountCols.includes(column.label) && row.row_code) {
      rvPenetrate.toReportRow(activeTab.value, row.row_code)
    }
  }

  // ─── 格内编辑提交（权益表 / 减值表 → PUT /reports/cell）─────────────────────
  // 粘贴 / 清空一个区域会连发多格：逐格保存，攒到同一批后只重新取数一次（原先每存一格整表重取一次）
  const cellSaves: Promise<boolean>[] = []
  let cellSaveTimer: ReturnType<typeof setTimeout> | null = null

  function onRvCellEdit(row: any, columnKey: string, value: number | null, yearKey?: 'current_year' | 'prior_year') {
    if (!row?.row_code) return
    if (year.value == null) {
      ElMessage.warning(MISSING_AUDIT_YEAR_MESSAGE)
      return
    }
    const payload: Record<string, unknown> = { row_code: row.row_code, column_key: columnKey, value }
    if (yearKey) payload.year_key = yearKey
    cellSaves.push(
      api.put(`/api/projects/${projectId.value}/reports/cell`, payload, {
        params: { year: year.value, report_type: activeTab.value },
      }).then(() => true, (e: any) => { handleApiError(e, '保存'); return false }),
    )
    if (cellSaveTimer) clearTimeout(cellSaveTimer)
    cellSaveTimer = setTimeout(() => { void flushCellSaves() }, 200)
  }

  async function flushCellSaves() {
    cellSaveTimer = null
    const batch = cellSaves.splice(0)
    const saved = (await Promise.all(batch)).filter(Boolean).length
    if (saved) ElMessage.success(saved > 1 ? `已保存 ${saved} 格` : '已保存')
    await fetchReport() // 失败的格随重新取数恢复成服务器上的值
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
    if (year.value == null) {
      ElMessage.warning(MISSING_AUDIT_YEAR_MESSAGE)
      return
    }
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
      // 年度为空不带 year（原先 String(null) 带成 year=null）
      query: { highlight_row: row.row_code, ...(year.value != null ? { year: String(year.value) } : {}) },
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
      // 年度为空不带 year（原先 String(null) 带成 year=null）
      query: { highlight_row: row.row_code, ...(year.value != null ? { year: String(year.value) } : {}) },
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
    onRvCellEdit,
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
