import { ref, computed, type ComputedRef, type Ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '@/services/apiProxy'
import { reports as P_reports } from '@/services/apiPaths'
import { handleApiError } from '@/utils/errorHandler'
import { fmtAmount } from '@/utils/formatters'
import { eventBus } from '@/utils/eventBus'
import {
  getReportDrilldown,
  type ReportRow, type ReportDrilldownData,
} from '@/services/auditPlatformApi'
import { useNavigationStack } from '@/composables/useNavigationStack'
import type { useCellSelection } from '@/composables/useCellSelection'
import type { usePenetrate } from '@/composables/usePenetrate'
import type { useCellComments } from '@/composables/useCellComments'

// ─── Interfaces ─────────────────────────────────────────────────────────────

export interface LineCompositionAccount {
  code: string
  name: string
  closing_balance: number
  pct: number
}

export interface LineCompositionData {
  line_code: string
  item_name: string
  total_amount: number
  accounts: LineCompositionAccount[]
}

export interface TraceLocation {
  label: string
  tab: string
  rowCode: string
}

export interface UseReportCellActionsOptions {
  projectId: ComputedRef<string>
  year: ComputedRef<number>
  activeTab: Ref<string>
  rows: Ref<ReportRow[]>
  reportMode: Ref<string>
  isConsolidated: ComputedRef<boolean>
  fetchReport: () => Promise<void>
  activeTabLabel: ComputedRef<string>
  getRowType: (row: ReportRow) => string
  goToNote: (rowCode: string) => void
  consistencyResult: Ref<any>
  showFormulaManager: Ref<boolean>
  openTrustScore: (context: string) => void
  // 🔴 Existing instances passed from main file — MUST NOT re-create
  rvCtx: ReturnType<typeof useCellSelection>
  rvPenetrate: ReturnType<typeof usePenetrate>
  rvComments: ReturnType<typeof useCellComments>
}

export interface UseReportCellActionsReturn {
  // Drilldown
  drilldownVisible: Ref<boolean>
  drilldownLoading: Ref<boolean>
  drilldownData: Ref<ReportDrilldownData | null>
  onDrilldown: (row: ReportRow) => Promise<void>

  // Line composition
  lineCompVisible: Ref<boolean>
  lineCompLoading: Ref<boolean>
  lineCompData: Ref<LineCompositionData | null>
  onLineComposition: (row: ReportRow) => Promise<void>
  onLineCompJumpToTB: (accountCode: string) => void

  // Note references
  noteRefsVisible: Ref<boolean>
  noteRefsLoading: Ref<boolean>
  noteRefsList: Ref<any[]>
  noteRefsRowCode: Ref<string>
  noteRefsRowName: Ref<string>
  onRvCtxShowNoteRefs: () => Promise<void>
  onJumpToNoteSection: (ref: { note_section: string; table_index: number }) => void

  // Cell trace (lineage)
  rvTraceDialogVisible: Ref<boolean>
  rvTraceLoading: Ref<boolean>
  rvTraceResult: Ref<{ upstream: any[]; downstream: any[] } | null>
  onRvCtxCellTrace: () => Promise<void>
  onRvTraceLocate: (node: any) => void

  // Audit dialog
  showAuditDialog: Ref<boolean>
  auditTab: Ref<string>
  filteredAuditChecks: ComputedRef<any[]>
  onExportAuditExcel: () => void
  onAuditDrilldown: (check: any) => void

  // Trace select
  showTraceSelectDialog: Ref<boolean>
  traceSelectOptions: Ref<TraceLocation[]>
  traceSelectCheck: Ref<any>
  isTracing: Ref<boolean>
  onTraceJump: (loc: TraceLocation) => void
  onTraceReturn: () => void

  // Consol breakdown
  consolBreakdownVisible: Ref<boolean>
  consolBreakdownAccountCode: Ref<string>
  onRvCtxViewConsolBreakdown: () => void

  // Formula source
  showCellFormulaDetail: Ref<boolean>
  cellDetailWpCode: Ref<string>
  cellDetailSheet: Ref<string>
  cellDetailLabel: Ref<string>
  onRvCtxViewFormulaSource: () => void
  onCellDetailNavigate: (uri: string) => void

  // Cell event handlers
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

  // Helpers exposed for template
  parseTraceLocations: (check: any) => TraceLocation[]
  openWorkpaper: (wpId: string) => void
}

// ─── Composable ─────────────────────────────────────────────────────────────

export function useReportCellActions(options: UseReportCellActionsOptions): UseReportCellActionsReturn {
  const {
    projectId, year, activeTab, rows, reportMode,
    isConsolidated, fetchReport, activeTabLabel,
    getRowType, goToNote, consistencyResult,
    showFormulaManager, openTrustScore,
    rvCtx, rvPenetrate, rvComments,
  } = options

  const router = useRouter()
  const { push: navPush } = useNavigationStack()

  // ─── Drilldown ──────────────────────────────────────────────────────────────
  const drilldownVisible = ref(false)
  const drilldownLoading = ref(false)
  const drilldownData = ref<ReportDrilldownData | null>(null)

  async function onDrilldown(row: ReportRow) {
    if (!row.row_code || row.is_total_row) return
    drilldownVisible.value = true
    drilldownLoading.value = true
    drilldownData.value = null
    try {
      const result = await getReportDrilldown(projectId.value, year.value, activeTab.value, row.row_code)
      drilldownData.value = {
        ...result,
        accounts: result.accounts.map((item: any) => ({
          ...item,
          amount: reportMode.value === 'unadjusted'
            ? (item.unadjusted_amount ?? item.amount ?? '0')
            : (item.audited_amount ?? item.amount ?? '0'),
        })),
      }
    } catch (e) {
      handleApiError(e, '穿透查询')
    } finally {
      drilldownLoading.value = false
    }
  }

  // ─── Line Composition ───────────────────────────────────────────────────────
  const lineCompVisible = ref(false)
  const lineCompLoading = ref(false)
  const lineCompData = ref<LineCompositionData | null>(null)

  async function onLineComposition(row: ReportRow) {
    if (!row.row_code || row.is_total_row || getRowType(row) === 'header') return
    lineCompVisible.value = true
    lineCompLoading.value = true
    lineCompData.value = null
    try {
      const resp: any = await api.get(P_reports.lineComposition(projectId.value, row.row_code))
      lineCompData.value = resp as LineCompositionData
    } catch (e) {
      handleApiError(e, '构成科目查询')
      lineCompVisible.value = false
    } finally {
      lineCompLoading.value = false
    }
  }

  function onLineCompJumpToTB(accountCode: string) {
    lineCompVisible.value = false
    navPush({
      source_view: router.currentRoute.value.fullPath,
      label: `报表 ${activeTabLabel.value}`,
      direction: 'down',
    })
    router.push({
      name: 'TrialBalance',
      params: { projectId: projectId.value },
      query: { account_code: accountCode },
    })
  }

  // ─── Note References ────────────────────────────────────────────────────────
  const noteRefsVisible = ref(false)
  const noteRefsLoading = ref(false)
  const noteRefsRowCode = ref('')
  const noteRefsRowName = ref('')
  const noteRefsList = ref<Array<{ note_section: string; section_title: string; table_index: number }>>([])

  async function onRvCtxShowNoteRefs() {
    rvCtx.closeContextMenu()
    const row = rvCtx.contextMenu.rowData
    if (!row?.row_code) {
      ElMessage.info('该行无 row_code，无法反查附注引用')
      return
    }
    noteRefsRowCode.value = row.row_code
    noteRefsRowName.value = row.row_name || ''
    noteRefsList.value = []
    noteRefsVisible.value = true
    noteRefsLoading.value = true
    try {
      const resp: any = await api.get(P_reports.noteReferences(projectId.value, year.value, row.row_code))
      noteRefsList.value = (resp?.notes || []) as any[]
    } catch (e) {
      handleApiError(e, '反查附注引用')
    } finally {
      noteRefsLoading.value = false
    }
  }

  function onJumpToNoteSection(ref: { note_section: string; table_index: number }) {
    noteRefsVisible.value = false
    router.push({
      path: `/projects/${projectId.value}/disclosure-notes`,
      query: {
        section: ref.note_section,
        table_index: String(ref.table_index ?? 0),
        year: String(year.value),
      },
    })
  }

  // ─── Cell Trace (Lineage) ─────────────────────────────────────────────────
  const rvTraceDialogVisible = ref(false)
  const rvTraceLoading = ref(false)
  const rvTraceResult = ref<{ upstream: any[]; downstream: any[] } | null>(null)

  async function onRvCtxCellTrace() {
    rvCtx.closeContextMenu()
    const row = rvCtx.contextMenu.rowData
    if (!row?.row_code) {
      ElMessage.info('请在数据行上右键')
      return
    }
    rvTraceDialogVisible.value = true
    rvTraceLoading.value = true
    rvTraceResult.value = null
    try {
      const data: any = await api.get(
        `/api/projects/${projectId.value}/lineage`,
        { params: { object_type: 'report_row', object_id: row.row_code, direction: 'both' } },
      )
      const upstream = data?.upstream || []
      const downstream = data?.downstream || []
      rvTraceResult.value = { upstream, downstream }
      if (!upstream.length && !downstream.length) {
        rvTraceDialogVisible.value = false
        ElMessage.info('该数字暂无溯源信息')
      }
    } catch (e: any) {
      rvTraceDialogVisible.value = false
      handleApiError(e, '数字溯源')
    } finally {
      rvTraceLoading.value = false
    }
  }

  function onRvTraceLocate(node: any) {
    rvTraceDialogVisible.value = false
    if (node.wp_code) {
      eventBus.emit('workpaper:locate-cell', {
        wpId: node.wp_code,
        sheetName: node.sheet_name || undefined,
        cellRef: node.cell_ref || '',
      })
    }
  }

  // ─── Audit Dialog ─────────────────────────────────────────────────────────
  const showAuditDialog = ref(false)
  const auditTab = ref('all')

  const filteredAuditChecks = computed(() => {
    const checks = consistencyResult.value?.checks || []
    if (auditTab.value === 'all') return checks
    return checks.filter((c: any) => c.category === auditTab.value)
  })

  function onExportAuditExcel() {
    const checks = filteredAuditChecks.value
    if (!checks.length) {
      ElMessage.warning('无审核数据可导出')
      return
    }
    const BOM = '\uFEFF'
    const header = '结果,审核项目,期望值,实际值,差额,类型,公式/来源\n'
    const csvRows = checks.map((c: any) =>
      [
        c.passed ? '通过' : '未通过',
        `"${(c.name || '').replace(/"/g, '""')}"`,
        c.expected || '',
        c.actual || '',
        c.diff || '',
        c.category_label || '',
        `"${(c.formula || c.source || '').replace(/"/g, '""')}"`,
      ].join(',')
    ).join('\n')
    const blob = new Blob([BOM + header + csvRows], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `审核报告_${activeTabLabel.value}_${year.value}.csv`
    a.click()
    URL.revokeObjectURL(url)
    ElMessage.success('审核报告已导出')
  }

  function onAuditDrilldown(check: any) {
    const locs = parseTraceLocations(check)
    if (locs.length === 1) {
      onTraceJump(locs[0])
    } else if (locs.length > 1) {
      showTraceSelectDialog.value = true
      traceSelectOptions.value = locs
      traceSelectCheck.value = check
    } else {
      ElMessage.info('该审核项无可溯源的定位信息')
    }
  }

  // ─── Trace Select ─────────────────────────────────────────────────────────
  const showTraceSelectDialog = ref(false)
  const traceSelectOptions = ref<TraceLocation[]>([])
  const traceSelectCheck = ref<any>(null)
  const isTracing = ref(false)
  const traceFromTab = ref('')

  function onTraceJump(loc: TraceLocation) {
    traceFromTab.value = activeTab.value
    activeTab.value = loc.tab
    showTraceSelectDialog.value = false
    showAuditDialog.value = false
    isTracing.value = true
    fetchReport()
  }

  function onTraceReturn() {
    isTracing.value = false
    showAuditDialog.value = true
    if (traceFromTab.value) {
      activeTab.value = traceFromTab.value
      fetchReport()
    }
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

  // ─── Helpers ──────────────────────────────────────────────────────────────

  function parseTraceLocations(check: any): TraceLocation[] {
    const locs: TraceLocation[] = []
    const formula = check.formula || ''
    const source = check.source || ''
    const name = check.name || ''

    const codeMatch = source.match(/^([A-Z]+-\d+)/)
    if (codeMatch) {
      const code = codeMatch[1]
      const tab = codeToTab(code)
      locs.push({ label: `${code} (${tabLabel(tab)})`, tab, rowCode: code })
    }

    const refs = formula.matchAll(/([A-Z]+-\d+)/g)
    for (const m of refs) {
      const code = m[1]
      if (!locs.find(l => l.rowCode === code)) {
        const tab = codeToTab(code)
        locs.push({ label: `${code} (${tabLabel(tab)})`, tab, rowCode: code })
      }
    }

    if (!locs.length) {
      if (name.includes('资产负债表')) locs.push({ label: '资产负债表', tab: 'balance_sheet', rowCode: '' })
      else if (name.includes('利润')) locs.push({ label: '利润表', tab: 'income_statement', rowCode: '' })
      else if (name.includes('现金')) locs.push({ label: '现金流量表', tab: 'cash_flow_statement', rowCode: '' })
    }

    return locs
  }

  function codeToTab(code: string): string {
    if (code.startsWith('BS-')) return 'balance_sheet'
    if (code.startsWith('IS-')) return 'income_statement'
    if (code.startsWith('CFS-')) return 'cash_flow_statement'
    if (code.startsWith('EQ-')) return 'equity_statement'
    if (code.startsWith('CFSS-')) return 'cash_flow_supplement'
    if (code.startsWith('IMP-')) return 'impairment_provision'
    return 'balance_sheet'
  }

  function tabLabel(tab: string): string {
    const m: Record<string, string> = {
      balance_sheet: '资产负债表', income_statement: '利润表',
      cash_flow_statement: '现金流量表', equity_statement: '权益变动表',
      cash_flow_supplement: '现金流附表', impairment_provision: '资产减值准备表',
    }
    return m[tab] || tab
  }

  // ─── Return ───────────────────────────────────────────────────────────────
  return {
    drilldownVisible,
    drilldownLoading,
    drilldownData,
    onDrilldown,

    lineCompVisible,
    lineCompLoading,
    lineCompData,
    onLineComposition,
    onLineCompJumpToTB,

    noteRefsVisible,
    noteRefsLoading,
    noteRefsList,
    noteRefsRowCode,
    noteRefsRowName,
    onRvCtxShowNoteRefs,
    onJumpToNoteSection,

    rvTraceDialogVisible,
    rvTraceLoading,
    rvTraceResult,
    onRvCtxCellTrace,
    onRvTraceLocate,

    showAuditDialog,
    auditTab,
    filteredAuditChecks,
    onExportAuditExcel,
    onAuditDrilldown,

    showTraceSelectDialog,
    traceSelectOptions,
    traceSelectCheck,
    isTracing,
    onTraceJump,
    onTraceReturn,

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

    parseTraceLocations,
    openWorkpaper,
  }
}
