/**
 * Composable Factories — 参数化工厂 barrel export
 *
 * Feature: workpaper-maintainability-convergence
 * Requirements: 6.1, 6.2, 6.5, 6.6
 *
 * 五大工厂用于收敛 ~200 个底稿 tab 的同构 composable：
 * - createChecklistFormData: 统一 checklist 持久化（复用 useChecklistPersistence）
 * - createCycleFormData: 表单数据加载/保存/校验（legacy，新代码优先 createChecklistFormData）
 * - createDualMode: HTML ↔ OnlyOffice 双模式
 * - createImportExport: 导入导出（模板/数据/上传）
 * - createDetailTable: 明细表行管理 + 合计
 */

export { createChecklistFormData } from './createChecklistFormData'
export type { ChecklistFormDataConfig, ChecklistFormDataReturn } from './createChecklistFormData'

export { createCycleFormData } from './createCycleFormData'
export type { CycleFormDataConfig, CycleFormDataReturn, FormDataItem } from './createCycleFormData'

export { createDualMode } from './createDualMode'
export type { DualModeConfig, DualModeReturn, DualModeType } from './createDualMode'

export { createImportExport } from './createImportExport'
export type { ImportExportConfig, ImportExportReturn, ImportResult } from './createImportExport'

export { createDetailTable } from './createDetailTable'
export type { DetailTableConfig, DetailTableReturn, ColumnDef } from './createDetailTable'
