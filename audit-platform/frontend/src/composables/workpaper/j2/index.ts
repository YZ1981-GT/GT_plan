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
// ⚠️ useJ2DualMode 已移除（spec j2-j3-non-entry-hosts-and-orphan-cleanup，OD-3）：
//    它是**二阶孤儿** —— 生产边只有本 barrel（#L18）+ 一条测试边，而本 barrel 自身
//    入边现算为 **0**（J2 宿主与 6 个子 Tab 全走逐模块深链，不走 barrel）⇒ 从任何真实
//    宿主都到不了。朴素判据「入度 > 0 ⇒ 不是孤儿」在它身上（入度 2）会**放它过去**。
//    J2 不是 manifest entry（entry 集合现算恰 1 条 xlsx/j1/gt-j1-employee-compensation），
//    宿主外层 template 里 OO 组件与模式切换器命中各 0 ⇒ 无双模式可切。
//    （🔴 此处刻意不写那两个组件的**字面名** —— `test_task52` 的 AC14 守卫按字面量 grep
//     全域统计模式切换器站点，注释里写出名字会被数成第 4 个站点而假红。）

// Pure function engines (for PBT)
export * from './useJ2FormulaEngine'
export * from './useJ2ActuarialEngine'
