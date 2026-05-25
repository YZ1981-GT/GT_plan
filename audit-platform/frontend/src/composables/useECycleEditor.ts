/**
 * useECycleEditor — E 货币资金循环专属逻辑 composable
 *
 * 锚定 spec workpaper-editor-refactor Phase 3 Task 3.1
 *
 * E 循环在 WorkpaperEditor.vue 中的独占代码极少，原因：
 * - E 循环的 sheet 导航使用通用 useUniverSheetNav（已通过 useSheetNavFacade 外置）
 * - E 循环的类型识别已通过 useCycleType 外置（isECycle 未显式暴露，走 fallback）
 * - E 循环无专属弹窗（useCycleDialogs 中无 E 循环条目）
 * - E1 的外币显隐规则已通过 useSheetNavFacade.applyForeignCurrencyVisibility 外置
 *
 * 本 composable 封装：
 * 1. E1 外币/数字货币 sheet 显隐触发（initUniver 后自动应用）
 * 2. E 循环特有的 trigger 判定（基于 wpCode）
 * 3. 未来 E 循环弹窗的 placeholder dialog refs（银行函证/外币折算等）
 *
 * 遵循 CycleEditorAPI 接口模式（design.md）：
 * - dialogs: { [key]: Ref<boolean> }
 * - triggers: { [key]: ComputedRef<boolean> }
 * - handlers: { [key]: (...args) => void | Promise<void> }
 */
import { ref, computed, type Ref, type ComputedRef } from 'vue'
import type { SheetNavFacadeAPI } from './useSheetNavFacade'

// ─── 接口定义 ─────────────────────────────────────────────────────────────────

export interface ECycleDialogs {
  /** 银行函证弹窗（E1 货币资金专属，待实现） */
  bankConfirmationDialog: Ref<boolean>
  /** 外币折算弹窗（E1 外币账户折算检查，待实现） */
  foreignCurrencyDialog: Ref<boolean>
}

export interface ECycleTriggers {
  /** 是否为 E 循环底稿 */
  isECycle: ComputedRef<boolean>
  /** 是否显示银行函证按钮（E1 开头的底稿） */
  showBankConfirmation: ComputedRef<boolean>
  /** 是否显示外币折算按钮（E1 且项目有外币） */
  showForeignCurrency: ComputedRef<boolean>
}

export interface ECycleHandlers {
  /** E1 初始化后应用外币 sheet 显隐规则 */
  applyForeignCurrencyVisibility: () => void
}

export interface ECycleEditorAPI {
  dialogs: ECycleDialogs
  triggers: ECycleTriggers
  handlers: ECycleHandlers
}

// ─── Composable 实现 ──────────────────────────────────────────────────────────

/**
 * E 货币资金循环编辑器 composable
 *
 * @param wpDetail - 当前底稿详情（含 wp_code）
 * @param sheetNav - Sheet 导航 facade（用于 applyForeignCurrencyVisibility）
 * @param hasForeignCurrency - 项目是否有外币业务
 */
export function useECycleEditor(
  wpDetail: Ref<{ wp_code?: string | null } | null>,
  sheetNav: SheetNavFacadeAPI,
  hasForeignCurrency: ComputedRef<boolean>,
): ECycleEditorAPI {
  // ─── Dialogs（placeholder，待未来实现弹窗组件时激活） ─────────────────────────
  const dialogs: ECycleDialogs = {
    bankConfirmationDialog: ref(false),
    foreignCurrencyDialog: ref(false),
  }

  // ─── Triggers ──────────────────────────────────────────────────────────────
  const wpCode = computed(() => (wpDetail.value?.wp_code || '').toUpperCase())

  const triggers: ECycleTriggers = {
    isECycle: computed(() => /^E\d/.test(wpCode.value)),
    showBankConfirmation: computed(() => /^E1/.test(wpCode.value)),
    showForeignCurrency: computed(() => /^E1/.test(wpCode.value) && hasForeignCurrency.value),
  }

  // ─── Handlers ──────────────────────────────────────────────────────────────

  /**
   * E1 Sprint 2 Task 2.37: 应用 has_foreign_currency 显隐规则到 E1-1
   * 在 initUniver 完成后调用，根据项目是否有外币业务决定 E1-1 sheet 可见性
   */
  function applyForeignCurrencyVisibility() {
    if (!triggers.isECycle.value) return
    if (!wpCode.value.startsWith('E1')) return
    sheetNav.applyForeignCurrencyVisibility()
  }

  const handlers: ECycleHandlers = {
    applyForeignCurrencyVisibility,
  }

  return { dialogs, triggers, handlers }
}
