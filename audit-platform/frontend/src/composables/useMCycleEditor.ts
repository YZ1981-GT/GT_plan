/**
 * useMCycleEditor — M 股东权益（变动表）循环专属逻辑 composable
 *
 * 锚定 spec workpaper-editor-refactor Phase 3 Task 3.8
 *
 * M 循环在 WorkpaperEditor.vue 中的独占代码：
 * - M6 权益变动表弹窗（EquityMovementDialog）触发
 *
 * 本 composable 封装：
 * 1. M 循环弹窗 visible refs（委托 useCycleDialogs 已有的 equityMovement）
 * 2. M 循环特有的 trigger 判定（基于 wpCode）
 * 3. onEquityMovementApplied handler
 *
 * M 循环比 G/H/I 更简单：无分支选择器（branch selector）。
 *
 * 遵循 CycleEditorAPI 接口模式（design.md）：
 * - dialogs: { [key]: Ref<boolean> }
 * - triggers: { [key]: ComputedRef<boolean> }
 * - handlers: { [key]: (...args) => void | Promise<void> }
 */
import { computed, type Ref, type ComputedRef } from 'vue'
import type { CycleDialogsAPI } from './useCycleDialogs'

// ─── 接口定义 ─────────────────────────────────────────────────────────────────

export interface MCycleDialogs {
  /** M6 权益变动表弹窗 visible（委托 useCycleDialogs.equityMovement） */
  equityMovementDialogVisible: Ref<boolean>
}

export interface MCycleTriggers {
  /** 是否为 M 循环底稿 */
  isMCycle: ComputedRef<boolean>
  /** 是否显示权益变动表按钮（M6 开头的底稿） */
  showEquityMovementTrigger: ComputedRef<boolean>
}

export interface MCycleHandlers {
  /** 权益变动表写回通知 */
  onEquityMovementApplied: (sheet: string) => void
}

export interface MCycleEditorAPI {
  dialogs: MCycleDialogs
  triggers: MCycleTriggers
  handlers: MCycleHandlers
}

// ─── Composable 实现 ──────────────────────────────────────────────────────────

/**
 * M 股东权益循环编辑器 composable
 *
 * @param wpDetail - 当前底稿详情（含 wp_code）
 * @param cycleDialogs - 统一弹窗管理（委托 visible/trigger/onApplied）
 */
export function useMCycleEditor(
  wpDetail: Ref<{ wp_code?: string | null } | null>,
  cycleDialogs: CycleDialogsAPI,
): MCycleEditorAPI {
  // ─── Dialogs（委托 useCycleDialogs 已有的 M 循环弹窗） ─────────────────────────
  const dialogs: MCycleDialogs = {
    equityMovementDialogVisible: cycleDialogs.equityMovement.visible,
  }

  // ─── Triggers（委托 useCycleDialogs 已有的 trigger computed） ───────────────────
  const wpCode = computed(() => (wpDetail.value?.wp_code || '').toUpperCase())

  const triggers: MCycleTriggers = {
    isMCycle: computed(() => /^M\d/.test(wpCode.value)),
    showEquityMovementTrigger: cycleDialogs.equityMovement.trigger,
  }

  // ─── Handlers ──────────────────────────────────────────────────────────────

  /** 权益变动表写回通知（委托 useCycleDialogs.equityMovement.onApplied） */
  function onEquityMovementApplied(sheet: string) {
    cycleDialogs.equityMovement.onApplied(sheet)
  }

  const handlers: MCycleHandlers = {
    onEquityMovementApplied,
  }

  return { dialogs, triggers, handlers }
}
