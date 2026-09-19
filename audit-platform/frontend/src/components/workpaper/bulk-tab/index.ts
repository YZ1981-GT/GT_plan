/**
 * bulk-tab — 项目级底稿批量 Tab 导入导出
 *
 * 与 WpBatchExportDialog（整份文件批量导出）并列。
 */
export { default as WpBulkDialog } from './WpBulkDialog.vue'
export { default as WpBulkImportReport } from './WpBulkImportReport.vue'
export { default as WpBulkProgressBar } from './WpBulkProgressBar.vue'
export { useBulkTabImportExport } from '@/composables/useBulkTabImportExport'
export type {
  ImportReport,
  SheetReportItem,
  SheetImportStatus,
  ConflictStrategy,
} from '@/composables/useBulkTabImportExport'
