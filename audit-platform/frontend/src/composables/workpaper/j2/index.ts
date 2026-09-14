/**
 * J2 设定受益计划 composable 导出
 *
 * ⚠️ useJ2FormData / useJ2Integration 已移除（spec tb-writeback-explicit-publish-gate Task 17 批C）：
 *    二者是无渲染宿主 import 的孤儿链 TB 回写死代码（useJ2FormData.writebackTB 2221 +
 *    useJ2Integration.onAdjudicationComplete），走变体端点 POST .../trial-balance/writeback，
 *    实证仅本 barrel 引用、barrel 自身零消费方（J2 目录 10 个 .vue 无一 import）。
 *    J2 真实宿主 J2TabAdjudication.vue 无 TB 回写。TB 回写走显式发布门 publish-to-tb。
 *    j2 目录其余 composable（ImportExport/Actuarial/Formula 等）属 I/E 孤儿链，归
 *    workpaper-import-export-lifecycle-closure spec（ieOrphanBaseline 追踪），不在本 spec 半径。
 */
export { useJ2CrossSheet } from './useJ2CrossSheet'
export { useJ2Adjudication } from './useJ2Adjudication'
export { useJ2Detail } from './useJ2Detail'
export { useJ2AccrualCheck } from './useJ2AccrualCheck'
export { useJ2Disclosure } from './useJ2Disclosure'
export { useJ2ImportExport } from './useJ2ImportExport'
export { useJ2DualMode } from './useJ2DualMode'

// Pure function engines (for PBT)
export * from './useJ2FormulaEngine'
export * from './useJ2ActuarialEngine'
