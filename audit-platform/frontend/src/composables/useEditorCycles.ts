/**
 * useEditorCycles — 6 cycle composable 统一实例化注册器 [V3 Req 12.1.2]
 *
 * 骨架已建 + 示范提取，完整瘦身需独立 Sprint。
 * 将 WorkpaperEditor.vue 中 6 个 cycle composable 的实例化（~150 行）
 * 集中到此文件，主组件仅调用 useEditorCycles 获取统一接口。
 *
 * 注意：Vue setup const 声明顺序铁律 — cycleDialogs 必须在 cycle 实例化之前定义。
 * 因此本 composable 接收 cycleDialogs 作为参数。
 *
 * @example
 * const cycles = useEditorCycles({
 *   wpDetail, projectId, wpId, sheetNavFacade, cycleDialogs, hasForeignCurrency,
 * })
 * // cycles.d / cycles.e / cycles.f / cycles.g / cycles.i / cycles.k / cycles.l / cycles.m / cycles.n
 */
import { type Ref, type ComputedRef } from 'vue'

// 类型定义（完整迁移时从各 cycle composable 导入实际类型）
export interface CycleContext {
  wpDetail: Ref<any>
  projectId: Ref<string>
  wpId: Ref<string>
  sheetNavFacade: any
  cycleDialogs: any
  hasForeignCurrency?: ComputedRef<boolean>
}

export interface CycleHandlers {
  d?: any
  e?: any
  f?: any
  g?: any
  i?: any
  k?: any
  l?: any
  m?: any
  n?: any
}

/**
 * 示范：统一 cycle composable 实例化
 *
 * 完整迁移时，将 WorkpaperEditor.vue 中以下代码块移入：
 * - useDCycleEditor(wpDetail, projectId, sheetNavFacade, onRefreshPrefill)
 * - useECycleEditor(wpDetail, sheetNavFacade, hasForeignCurrency)
 * - useFCycleEditor(wpDetail, projectId, wpId, sheetNavFacade, cycleDialogs)
 * - useGCycleEditor(wpDetail, sheetNavFacade, cycleDialogs)
 * - useICycleEditor(wpDetail, sheetNavFacade, cycleDialogs)
 * - useKCycleEditor(wpDetail, cycleDialogs)
 * - useLCycleEditor(wpDetail, cycleDialogs)
 * - useMCycleEditor(...)
 * - useNCycleEditor(...)
 *
 * 以及各 cycle 的 handlers 解构（onXxxApplied 等 ~50 行）
 */
export function useEditorCycles(_ctx: CycleContext): CycleHandlers {
  // 骨架：完整迁移时在此实例化所有 cycle composable
  // 当前保留在 WorkpaperEditor.vue 中，避免高风险重构
  //
  // 示范提取模式：
  // const dCycle = useDCycleEditor(ctx.wpDetail, ctx.projectId, ctx.sheetNavFacade, onRefreshPrefill)
  // const eCycle = useECycleEditor(ctx.wpDetail, ctx.sheetNavFacade, ctx.hasForeignCurrency)
  // const fCycle = useFCycleEditor(ctx.wpDetail, ctx.projectId, ctx.wpId, ctx.sheetNavFacade, ctx.cycleDialogs)
  // const gCycle = useGCycleEditor(ctx.wpDetail, ctx.sheetNavFacade, ctx.cycleDialogs)
  // const iCycle = useICycleEditor(ctx.wpDetail, ctx.sheetNavFacade, ctx.cycleDialogs)
  // const kCycle = useKCycleEditor(ctx.wpDetail, ctx.cycleDialogs)
  // const lCycle = useLCycleEditor(ctx.wpDetail, ctx.cycleDialogs)
  //
  // return { d: dCycle, e: eCycle, f: fCycle, g: gCycle, i: iCycle, k: kCycle, l: lCycle }

  return {}
}
