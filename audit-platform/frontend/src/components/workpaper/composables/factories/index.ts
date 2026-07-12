/**
 * Composable Factories — 参数化工厂 barrel export
 *
 * Feature: platform-global-hardening
 * Requirements: 6.5, 6.6
 *
 * 四大工厂用于收敛 ~200 个底稿 tab 的同构 composable：
 * - createCycleFormData: 表单数据加载/保存/校验
 * - createDualMode: HTML ↔ OnlyOffice 双模式
 * - createImportExport: 导入导出（模板/数据/上传）
 * - createDetailTable: 明细表行管理 + 合计
 */

export { createCycleFormData } from './createCycleFormData'
export type { CycleFormDataConfig, CycleFormDataReturn, FormDataItem } from './createCycleFormData'

export { createDualMode } from './createDualMode'
export type { DualModeConfig, DualModeReturn, DualModeType } from './createDualMode'

export { createImportExport } from './createImportExport'
export type { ImportExportConfig, ImportExportReturn, ImportResult } from './createImportExport'

export { createDetailTable } from './createDetailTable'
export type { DetailTableConfig, DetailTableReturn, ColumnDef } from './createDetailTable'
