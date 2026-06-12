import { type ComputedRef, type Ref } from 'vue'
import type { ReportRow, ReportDrilldownData } from '@/services/auditPlatformApi'
import type { useCellSelection } from '@/composables/useCellSelection'
import type { usePenetrate } from '@/composables/usePenetrate'
import type { useCellComments } from '@/composables/useCellComments'
import { useReportDrilldown, type LineCompositionData } from './useReportDrilldown'
import { useReportTrace, type TraceLocation } from './useReportTrace'
import { useReportContextMenu } from './useReportContextMenu'

// ─── Re-export sub-composable types for consumers ───────────────────────────
export type { LineCompositionAccount, LineCompositionData } from './useReportDrilldown'
export type { TraceLocation } from './useReportTrace'

// ─── Interfaces ─────────────────────────────────────────────────────────────

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
  eqCellVal?: (row: any, colKey: string, yearKey?: 'current_year' | 'prior_year') => any
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

// ─── Aggregator Composable ──────────────────────────────────────────────────

export function useReportCellActions(options: UseReportCellActionsOptions): UseReportCellActionsReturn {
  const {
    projectId, year, activeTab, rows, reportMode,
    isConsolidated, fetchReport, activeTabLabel,
    getRowType, goToNote, consistencyResult,
    showFormulaManager, openTrustScore,
    rvCtx, rvPenetrate, eqCellVal,
  } = options

  // 1. Drilldown + Line Composition + Note References
  const drilldown = useReportDrilldown({
    projectId, year, activeTab, reportMode,
    activeTabLabel, getRowType, rvCtx,
  })

  // 2. Cell trace (lineage) + Audit dialog + Trace select
  const trace = useReportTrace({
    projectId, year, activeTab, activeTabLabel,
    consistencyResult, fetchReport, rvCtx,
  })

  // 3. Context menu handlers (depends on drilldown.onDrilldown)
  const contextMenu = useReportContextMenu({
    projectId, year, activeTab, rows, reportMode,
    isConsolidated, fetchReport, getRowType,
    goToNote, showFormulaManager, openTrustScore,
    rvCtx, rvPenetrate, eqCellVal,
    onDrilldown: drilldown.onDrilldown,
  })

  // ─── Return combined interface ────────────────────────────────────────────
  return {
    // From useReportDrilldown
    ...drilldown,

    // From useReportTrace
    ...trace,

    // From useReportContextMenu
    ...contextMenu,
  }
}
