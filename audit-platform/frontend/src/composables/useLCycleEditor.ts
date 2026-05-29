/**
 * useLCycleEditor — L 筹资循环专属逻辑 composable
 *
 * 锚定 spec workpaper-editor-refactor Phase 3 Task 3.7
 * 重构 2026-05-28：退化为薄包装，委托 useSimpleCycleEditor generic。
 *
 * L 循环在 WorkpaperEditor.vue 中的独占代码：
 * - L1/L3 利息测算弹窗（InterestCalcDialog）触发
 * - L5 摊余成本弹窗（BondAmortizationDialog）触发
 */
import { type Ref } from 'vue'
import type { CycleDialogsAPI } from './useCycleDialogs'
import { useSimpleCycleEditor, type SimpleCycleEditorAPI } from './useSimpleCycleEditor'

const L_DIALOG_KEYS = ['interestCalc', 'bondAmortization'] as const

export type LCycleEditorAPI = SimpleCycleEditorAPI<typeof L_DIALOG_KEYS[number], 'L'>
export type LCycleDialogs = LCycleEditorAPI['dialogs']
export type LCycleTriggers = LCycleEditorAPI['triggers']
export type LCycleHandlers = LCycleEditorAPI['handlers']

export function useLCycleEditor(
  wpDetail: Ref<{ wp_code?: string | null } | null>,
  cycleDialogs: CycleDialogsAPI,
): LCycleEditorAPI {
  return useSimpleCycleEditor(wpDetail, cycleDialogs, {
    cycleLetter: 'L',
    dialogKeys: L_DIALOG_KEYS,
  })
}
