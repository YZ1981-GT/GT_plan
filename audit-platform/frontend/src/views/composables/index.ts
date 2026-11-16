/**
 * View-level composables barrel export
 *
 * Domain-split composables extracted from giant view files:
 * - LedgerPenetration.vue → useLedgerImport / useLedgerBalance / useLedgerNavigation
 * - TrialBalance.vue → useTbBalanceCheck / useTbCellInteraction
 *   （`useTbSummary` 已于 2026-11-16 删除：从未被调用，且指向不存在的后端端点）
 */

// LedgerPenetration 域拆分
export { useLedgerImport, STANDARD_FIELDS } from './useLedgerImport'
export { useLedgerBalance, resolveDir, balanceTip, getLevel, getParentCode } from './useLedgerBalance'
export type { BalanceRow, BalanceFilter } from './useLedgerBalance'
export { useLedgerNavigation } from './useLedgerNavigation'
export type { PenetrationLevel, BreadcrumbItem } from './useLedgerNavigation'

// TrialBalance 域拆分
//
// 🔴 `useTbSummary` 已删除（2026-11-16）：整个文件**从未被调用**
// （`TrialBalance.vue` 有自己的 `loadTbSummary` / `exportTbSummary` /
// `exportTbSumTemplate` 实现，且导出走纯前端 `exportMultiSheetData` 不经后端），
// 而它的两个导出方法指向后端**从未实现**的试算表汇总导出端点 ⇒
// 留着就是「随时可能被接上的 404 陷阱」。
// 守卫 `tbSummaryDeadExportPathGuard.spec.ts` 防这类路径再出现。
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
