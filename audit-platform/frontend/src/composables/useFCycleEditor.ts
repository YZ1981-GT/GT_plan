/**
 * useFCycleEditor — F 采购存货循环专属逻辑 composable
 *
 * 锚定 spec workpaper-editor-refactor Phase 3 Task 3.2
 *
 * F 循环在 WorkpaperEditor.vue 中的独占代码：
 * - F2 存货监盘弹窗（InventoryStocktakeDialog）触发
 * - F2 计价测试自动抽样（onTriggerValuationSample）
 * - F2 跌价准备 AI 分析弹窗（InventoryImpairmentDialog）触发
 *
 * 本 composable 封装：
 * 1. F 循环弹窗 visible refs（委托 useCycleDialogs 已有的 stocktake/valuation/impairment）
 * 2. F 循环特有的 trigger 判定（基于 wpCode + activeSheetId）
 * 3. onTriggerValuationSample handler（F2 计价测试自动抽样 API 调用）
 * 4. onImpairmentApplied handler（跌价分析写回通知）
 *
 * 遵循 CycleEditorAPI 接口模式（design.md）：
 * - dialogs: { [key]: Ref<boolean> }
 * - triggers: { [key]: ComputedRef<boolean> }
 * - handlers: { [key]: (...args) => void | Promise<void> }
 */
import { computed, type Ref, type ComputedRef } from 'vue'
import { ElMessage } from 'element-plus'
import { api as httpApi } from '@/services/apiProxy'
import { eventBus } from '@/utils/eventBus'
import { handleApiError } from '@/utils/errorHandler'
import type { CycleDialogsAPI } from './useCycleDialogs'
import type { SheetNavFacadeAPI } from './useSheetNavFacade'

// ─── 接口定义 ─────────────────────────────────────────────────────────────────

export interface FCycleDialogs {
  /** 存货监盘弹窗 visible（委托 useCycleDialogs.stocktake） */
  stocktakeDialogVisible: Ref<boolean>
  /** 跌价准备 AI 分析弹窗 visible（委托 useCycleDialogs.impairment） */
  impairmentDialogVisible: Ref<boolean>
}

export interface FCycleTriggers {
  /** 是否为 F 循环底稿 */
  isFCycle: ComputedRef<boolean>
  /** 是否显示监盘触发按钮（F2-21~F2-26 sheet） */
  showStocktakeTrigger: ComputedRef<boolean>
  /** 是否显示计价测试抽样按钮（F2-38~F2-44 sheet） */
  showValuationTrigger: ComputedRef<boolean>
  /** 是否显示跌价分析按钮（F2-47~F2-49 sheet） */
  showImpairmentTrigger: ComputedRef<boolean>
}

export interface FCycleHandlers {
  /** F2 计价测试自动抽样（调 API + 写回 sheet） */
  onTriggerValuationSample: () => Promise<void>
  /** 跌价分析写回通知 */
  onImpairmentApplied: (sheet: string) => void
}

export interface FCycleEditorAPI {
  dialogs: FCycleDialogs
  triggers: FCycleTriggers
  handlers: FCycleHandlers
  /** 计价测试加载状态（供模板 :loading 绑定） */
  valuationLoading: Ref<boolean>
}

// ─── Composable 实现 ──────────────────────────────────────────────────────────

/**
 * F 采购存货循环编辑器 composable
 *
 * @param wpDetail - 当前底稿详情（含 wp_code）
 * @param projectId - 当前项目 ID
 * @param wpId - 当前底稿 ID
 * @param sheetNav - Sheet 导航 facade（用于 activeSheetId）
 * @param cycleDialogs - 统一弹窗管理（委托 visible/trigger/onApplied）
 */
export function useFCycleEditor(
  wpDetail: Ref<{ wp_code?: string | null } | null>,
  projectId: Ref<string>,
  wpId: Ref<string>,
  sheetNav: SheetNavFacadeAPI,
  cycleDialogs: CycleDialogsAPI,
): FCycleEditorAPI {
  // ─── Dialogs（委托 useCycleDialogs 已有的 F 循环弹窗） ─────────────────────────
  const dialogs: FCycleDialogs = {
    stocktakeDialogVisible: cycleDialogs.stocktake.visible,
    impairmentDialogVisible: cycleDialogs.impairment.visible,
  }

  // ─── Triggers（委托 useCycleDialogs 已有的 trigger computed） ───────────────────
  const wpCode = computed(() => (wpDetail.value?.wp_code || '').toUpperCase())

  const triggers: FCycleTriggers = {
    isFCycle: computed(() => /^F\d/.test(wpCode.value)),
    showStocktakeTrigger: cycleDialogs.stocktake.trigger,
    showValuationTrigger: cycleDialogs.valuation.trigger,
    showImpairmentTrigger: cycleDialogs.impairment.trigger,
  }

  // ─── Handlers ──────────────────────────────────────────────────────────────

  /**
   * F-purchase-inventory F-F11 Task 3.2: F2-38~F2-44 计价测试自动抽样
   * 调用后端 API 执行加权平均抽样，写回当前 sheet
   */
  async function onTriggerValuationSample() {
    cycleDialogs.valuation.loading.value = true
    try {
      const year = new Date().getFullYear()
      const activeSheet = sheetNav.activeSheetId.value || ''
      const resp: any = await httpApi.post(
        `/api/projects/${projectId.value}/workpapers/${wpId.value}/f2/valuation-sample`,
        {
          method: 'weighted_average',
          account_code: '1403',
          year,
          sample_size: 20,
          high_value_threshold: 100000,
          period: '全年',
          apply_to_sheet: activeSheet,
        },
      )
      if (resp?.applied_to_sheet) {
        ElMessage.success(`已抽样 ${resp?.total_samples || 0} 笔并写回 ${resp.applied_to_sheet}`)
        eventBus.emit('workpaper:saved', { wp_id: wpId.value } as any)
      } else {
        ElMessage.success(`已抽样 ${resp?.total_samples || 0} 笔（${resp?.method}），未写回`)
      }
    } catch (e: any) {
      handleApiError(e, '抽样')
    } finally {
      cycleDialogs.valuation.loading.value = false
    }
  }

  /** 跌价分析写回通知（委托 useCycleDialogs.impairment.onApplied） */
  function onImpairmentApplied(sheet: string) {
    cycleDialogs.impairment.onApplied(sheet)
  }

  const handlers: FCycleHandlers = {
    onTriggerValuationSample,
    onImpairmentApplied,
  }

  return {
    dialogs,
    triggers,
    handlers,
    valuationLoading: cycleDialogs.valuation.loading,
  }
}
