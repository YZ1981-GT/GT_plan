/**
 * useNCycleEditor — N 税费（所得税）循环专属逻辑 composable
 *
 * 锚定 spec workpaper-editor-refactor Phase 3 Task 3.9
 *
 * N 循环在 WorkpaperEditor.vue 中的独占代码：
 * - N5 所得税测算弹窗（IncomeTaxCalcDialog）触发
 *
 * 本 composable 封装：
 * 1. N 循环弹窗 visible refs（委托 useCycleDialogs 已有的 incomeTaxCalc）
 * 2. N 循环特有的 trigger 判定（基于 wpCode）
 * 3. onIncomeTaxCalcApplied handler
 *
 * N 循环比 G/H/I 更简单：无分支选择器（branch selector）。
 *
 * 遵循 CycleEditorAPI 接口模式（design.md）：
 * - dialogs: { [key]: Ref<boolean> }
 * - triggers: { [key]: ComputedRef<boolean> }
 * - handlers: { [key]: (...args) => void | Promise<void> }
 */
import { computed, type Ref, type ComputedRef } from 'vue'
import type { CycleDialogsAPI } from './useCycleDialogs'

// ─── 接口定义 ─────────────────────────────────────────────────────────────────

export interface NCycleDialogs {
  /** N5 所得税测算弹窗 visible（委托 useCycleDialogs.incomeTaxCalc） */
  incomeTaxCalcDialogVisible: Ref<boolean>
}

export interface NCycleTriggers {
  /** 是否为 N 循环底稿 */
  isNCycle: ComputedRef<boolean>
  /** 是否显示所得税测算按钮（N5 开头的底稿） */
  showIncomeTaxCalcTrigger: ComputedRef<boolean>
}

export interface NCycleHandlers {
  /** 所得税测算写回通知 */
  onIncomeTaxCalcApplied: (sheet: string) => void
}

export interface NCycleEditorAPI {
  dialogs: NCycleDialogs
  triggers: NCycleTriggers
  handlers: NCycleHandlers
}

// ─── Composable 实现 ──────────────────────────────────────────────────────────

/**
 * N 税费（所得税）循环编辑器 composable
 *
 * @param wpDetail - 当前底稿详情（含 wp_code）
 * @param cycleDialogs - 统一弹窗管理（委托 visible/trigger/onApplied）
 */
export function useNCycleEditor(
  wpDetail: Ref<{ wp_code?: string | null } | null>,
  cycleDialogs: CycleDialogsAPI,
): NCycleEditorAPI {
  // ─── Dialogs（委托 useCycleDialogs 已有的 N 循环弹窗） ─────────────────────────
  const dialogs: NCycleDialogs = {
    incomeTaxCalcDialogVisible: cycleDialogs.incomeTaxCalc.visible,
  }

  // ─── Triggers（委托 useCycleDialogs 已有的 trigger computed） ───────────────────
  const wpCode = computed(() => (wpDetail.value?.wp_code || '').toUpperCase())

  const triggers: NCycleTriggers = {
    isNCycle: computed(() => /^N\d/.test(wpCode.value)),
    showIncomeTaxCalcTrigger: cycleDialogs.incomeTaxCalc.trigger,
  }

  // ─── Handlers ──────────────────────────────────────────────────────────────

  /** 所得税测算写回通知（委托 useCycleDialogs.incomeTaxCalc.onApplied） */
  function onIncomeTaxCalcApplied(sheet: string) {
    cycleDialogs.incomeTaxCalc.onApplied(sheet)
  }

  const handlers: NCycleHandlers = {
    onIncomeTaxCalcApplied,
  }

  return { dialogs, triggers, handlers }
}
