/**
 * useKCycleEditor — K 管理费用循环专属逻辑 composable
 *
 * 锚定 spec workpaper-editor-refactor Phase 3 Task 3.6
 * 重构 2026-05-28：从 ~95 行特化实现退化为 ~25 行薄包装，
 *                 委托给 `useSimpleCycleEditor` generic（去重 K/L/M/N 4 个 100% 同构 CycleEditor）。
 *
 * K 循环在 WorkpaperEditor.vue 中的独占代码：
 * - K8/K9 费用分析弹窗（ExpenseAnalysisDialog）触发
 * - K11 跨循环减值汇总弹窗（ImpairmentSummaryDialog）触发
 *
 * K 循环比 G/H/I 更简单：无分支选择器（branch selector）。
 * 因此可使用 useSimpleCycleEditor generic（仅依赖 dialogKeys + cycleLetter）。
 */
import { type Ref } from 'vue'
import type { CycleDialogsAPI } from './useCycleDialogs'
import { useSimpleCycleEditor, type SimpleCycleEditorAPI } from './useSimpleCycleEditor'

// ─── 接口定义（保留向后兼容的具名导出，便于其他地方 import 类型） ──────────────

const K_DIALOG_KEYS = ['expenseAnalysis', 'impairmentSummary'] as const

export type KCycleEditorAPI = SimpleCycleEditorAPI<typeof K_DIALOG_KEYS[number], 'K'>
export type KCycleDialogs = KCycleEditorAPI['dialogs']
export type KCycleTriggers = KCycleEditorAPI['triggers']
export type KCycleHandlers = KCycleEditorAPI['handlers']

// ─── Composable ─────────────────────────────────────────────────────────────

/**
 * K 管理费用循环编辑器 composable
 *
 * @param wpDetail - 当前底稿详情（含 wp_code）
 * @param cycleDialogs - 统一弹窗管理（委托 visible/trigger/onApplied）
 */
export function useKCycleEditor(
  wpDetail: Ref<{ wp_code?: string | null } | null>,
  cycleDialogs: CycleDialogsAPI,
): KCycleEditorAPI {
  return useSimpleCycleEditor(wpDetail, cycleDialogs, {
    cycleLetter: 'K',
    dialogKeys: K_DIALOG_KEYS,
  })
}
