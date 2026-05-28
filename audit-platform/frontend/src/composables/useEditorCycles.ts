/**
 * useEditorCycles — cycle composable 统一实例化注册器 [V3 Req 12.1.2]
 *
 * 把 WorkpaperEditor.vue 中 7 个 cycle composable（cycleDialogs + F/I/G/K/L/M/N
 * 共 8 个）的实例化集中到本 composable，主组件仅调用 `useEditorCycles(ctx)`
 * 即可解构出全部 cycle 实例。
 *
 * 设计要点：
 *  1. 所有 cycle composable 都依赖 cycleDialogs；本 composable 内部按依赖顺序
 *     先实例化 cycleDialogs，再实例化各循环编辑器，调用方无需关心拓扑顺序。
 *  2. 接收 reactive context（wpDetail / projectId / wpId / sheetNavActiveId /
 *     sheetNavFacade / cycleType），与原 WorkpaperEditor.vue 调用签名 1:1 对齐，
 *     保证行为与重构前等价。
 *  3. 不在此处提取 dialog 别名 / handlers 解构 — 那是 12.1.5 的职责，本任务
 *     仅迁移实例化。
 *
 * @example
 * const { cycleDialogs, fCycle, iCycle, gCycle, kCycle, lCycle, mCycle, nCycle }
 *   = useEditorCycles({
 *     wpDetail, projectId, wpId, sheetNavActiveId, sheetNavFacade, cycleType,
 *   })
 * const iBranchSelector = iCycle.branchSelector
 */
import type { ComputedRef, Ref } from 'vue'

import { useCycleDialogs, type CycleDialogsAPI } from './useCycleDialogs'
import { useFCycleEditor, type FCycleEditorAPI } from './useFCycleEditor'
import { useICycleEditor, type ICycleEditorAPI } from './useICycleEditor'
import { useGCycleEditor, type GCycleEditorAPI } from './useGCycleEditor'
import { useKCycleEditor, type KCycleEditorAPI } from './useKCycleEditor'
import { useLCycleEditor, type LCycleEditorAPI } from './useLCycleEditor'
import { useMCycleEditor, type MCycleEditorAPI } from './useMCycleEditor'
import { useNCycleEditor, type NCycleEditorAPI } from './useNCycleEditor'
import type { CycleTypeFlags } from './useCycleType'
import type { SheetNavFacadeAPI } from './useSheetNavFacade'

// ─── 接口 ─────────────────────────────────────────────────────────────────────

export interface EditorCyclesContext {
  /** 当前底稿详情（含 wp_code / parsed_data） */
  wpDetail: Ref<{ wp_code?: string | null; parsed_data?: any } | null>
  /** 当前项目 ID（路由派生） */
  projectId: ComputedRef<string> | Ref<string>
  /** 当前底稿 ID（路由派生） */
  wpId: ComputedRef<string> | Ref<string>
  /** Sheet 导航 facade 暴露的 activeSheetId（cycleDialogs trigger 依赖） */
  sheetNavActiveId: ComputedRef<string>
  /** Sheet 导航 facade（F/I/G 等需要 hCycleNav/iCycleNav/gCycleNav） */
  sheetNavFacade: SheetNavFacadeAPI
  /** 循环类型 flags（cycleDialogs 的 trigger 依赖） */
  cycleType: CycleTypeFlags
}

export interface EditorCyclesAPI {
  cycleDialogs: CycleDialogsAPI
  fCycle: FCycleEditorAPI
  iCycle: ICycleEditorAPI
  gCycle: GCycleEditorAPI
  kCycle: KCycleEditorAPI
  lCycle: LCycleEditorAPI
  mCycle: MCycleEditorAPI
  nCycle: NCycleEditorAPI
}

// ─── 实现 ─────────────────────────────────────────────────────────────────────

/**
 * 统一实例化 7 个 cycle composable 并返回稳定接口。
 *
 * 注意：函数体内部的实例化顺序遵循 "Vue setup const 声明顺序铁律"——
 * cycleDialogs 必须先于其他 cycle composable，因为后者将 cycleDialogs
 * 作为入参。调用方因此无需在外部维护这个顺序。
 */
export function useEditorCycles(ctx: EditorCyclesContext): EditorCyclesAPI {
  // 1) 弹窗状态汇总（其余 cycle 都依赖此对象）
  const cycleDialogs = useCycleDialogs(
    ctx.wpDetail,
    ctx.wpId,
    ctx.sheetNavActiveId,
    ctx.cycleType,
  )

  // 2) 各审计循环编辑器（与 WorkpaperEditor.vue 重构前签名一致）
  const fCycle = useFCycleEditor(
    ctx.wpDetail,
    ctx.projectId,
    ctx.wpId,
    ctx.sheetNavFacade,
    cycleDialogs,
  )
  const iCycle = useICycleEditor(ctx.wpDetail, ctx.sheetNavFacade, cycleDialogs)
  const gCycle = useGCycleEditor(ctx.wpDetail, ctx.sheetNavFacade, cycleDialogs)
  const kCycle = useKCycleEditor(ctx.wpDetail, cycleDialogs)
  const lCycle = useLCycleEditor(ctx.wpDetail, cycleDialogs)
  const mCycle = useMCycleEditor(ctx.wpDetail, cycleDialogs)
  const nCycle = useNCycleEditor(ctx.wpDetail, cycleDialogs)

  return {
    cycleDialogs,
    fCycle,
    iCycle,
    gCycle,
    kCycle,
    lCycle,
    mCycle,
    nCycle,
  }
}
