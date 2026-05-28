/**
 * useMCycleEditor — M 股东权益（变动表）循环专属逻辑 composable
 *
 * 锚定 spec workpaper-editor-refactor Phase 3 Task 3.8
 * 重构 2026-05-28：退化为薄包装，委托 useSimpleCycleEditor generic。
 *
 * M 循环在 WorkpaperEditor.vue 中的独占代码：
 * - M6 权益变动表弹窗（EquityMovementDialog）触发
 */
import { type Ref } from 'vue'
import type { CycleDialogsAPI } from './useCycleDialogs'
import { useSimpleCycleEditor, type SimpleCycleEditorAPI } from './useSimpleCycleEditor'

const M_DIALOG_KEYS = ['equityMovement'] as const

export type MCycleEditorAPI = SimpleCycleEditorAPI<typeof M_DIALOG_KEYS[number], 'M'>
export type MCycleDialogs = MCycleEditorAPI['dialogs']
export type MCycleTriggers = MCycleEditorAPI['triggers']
export type MCycleHandlers = MCycleEditorAPI['handlers']

export function useMCycleEditor(
  wpDetail: Ref<{ wp_code?: string | null } | null>,
  cycleDialogs: CycleDialogsAPI,
): MCycleEditorAPI {
  return useSimpleCycleEditor(wpDetail, cycleDialogs, {
    cycleLetter: 'M',
    dialogKeys: M_DIALOG_KEYS,
  })
}
