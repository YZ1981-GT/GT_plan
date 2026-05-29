/**
 * useNCycleEditor — N 税费（所得税）循环专属逻辑 composable
 *
 * 锚定 spec workpaper-editor-refactor Phase 3 Task 3.9
 * 重构 2026-05-28：退化为薄包装，委托 useSimpleCycleEditor generic。
 *
 * N 循环在 WorkpaperEditor.vue 中的独占代码：
 * - N5 所得税测算弹窗（IncomeTaxCalcDialog）触发
 */
import { type Ref } from 'vue'
import type { CycleDialogsAPI } from './useCycleDialogs'
import { useSimpleCycleEditor, type SimpleCycleEditorAPI } from './useSimpleCycleEditor'

const N_DIALOG_KEYS = ['incomeTaxCalc'] as const

export type NCycleEditorAPI = SimpleCycleEditorAPI<typeof N_DIALOG_KEYS[number], 'N'>
export type NCycleDialogs = NCycleEditorAPI['dialogs']
export type NCycleTriggers = NCycleEditorAPI['triggers']
export type NCycleHandlers = NCycleEditorAPI['handlers']

export function useNCycleEditor(
  wpDetail: Ref<{ wp_code?: string | null } | null>,
  cycleDialogs: CycleDialogsAPI,
): NCycleEditorAPI {
  return useSimpleCycleEditor(wpDetail, cycleDialogs, {
    cycleLetter: 'N',
    dialogKeys: N_DIALOG_KEYS,
  })
}
