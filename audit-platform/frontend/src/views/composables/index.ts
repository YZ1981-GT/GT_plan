/**
 * View-level composables barrel export
 *
 * Domain-split composables extracted from giant view files:
 * - LedgerPenetration.vue → useLedgerImport / useLedgerBalance / useLedgerNavigation
 * - TrialBalance.vue → useTbSummary / useTbBalanceCheck / useTbCellInteraction
 */

// LedgerPenetration 域拆分
export { useLedgerImport, STANDARD_FIELDS } from './useLedgerImport'
export { useLedgerBalance, resolveDir, balanceTip, getLevel, getParentCode } from './useLedgerBalance'
export type { BalanceRow, BalanceFilter } from './useLedgerBalance'
export { useLedgerNavigation } from './useLedgerNavigation'
export type { PenetrationLevel, BreadcrumbItem } from './useLedgerNavigation'

// TrialBalance 域拆分
export { useTbSummary, TB_SUMMARY_TYPES } from './useTbSummary'
export type { TbSummaryRow } from './useTbSummary'
export { useTbBalanceCheck } from './useTbBalanceCheck'
export type { DisplayRow } from './useTbBalanceCheck'
export { useTbCellInteraction } from './useTbCellInteraction'
export type { CellCoord, DragState } from './useTbCellInteraction'

// Note/Report domain composables (existing)
export { useNoteAi } from './useNoteAi'
export { useNoteCellActions } from './useNoteCellActions'
export { useNoteDetail } from './useNoteDetail'
export { useNoteExport } from './useNoteExport'
export { useNotePersist } from './useNotePersist'
export { useNoteRefresh } from './useNoteRefresh'
export { useNoteSectionManage } from './useNoteSectionManage'
export { useNoteTemplate } from './useNoteTemplate'
export { useNoteTree } from './useNoteTree'
export { useReportCellActions } from './useReportCellActions'
export { useReportColumns } from './useReportColumns'
export { useReportContextMenu } from './useReportContextMenu'
export { useReportCrossCheck } from './useReportCrossCheck'
export { useReportData } from './useReportData'
export { useReportDrilldown } from './useReportDrilldown'
export { useReportExport } from './useReportExport'
export { useReportMapping } from './useReportMapping'
export { useReportTrace } from './useReportTrace'
