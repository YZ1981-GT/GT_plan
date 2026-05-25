/**
 * useDCycleEditor — D 销售循环专属逻辑 composable
 *
 * 锚定 spec workpaper-editor-refactor Phase 2 Task 2.2
 *
 * D 循环在 WorkpaperEditor.vue 中的独占代码极少（~15-20 行），原因：
 * - D 循环的 sheet 分组逻辑已通过 useDSalesCycleSheetGroups + useSheetNavFacade 外置
 * - D 循环的类型识别已通过 useCycleType 外置
 * - D 循环的专属弹窗（salesIPE / salesPenetration / confirmation）尚未实现
 *
 * 本 composable 封装：
 * 1. onCrossRefUpdated handler（D0 函证回函 → 刷新 sheet nav + prefill）
 * 2. onSSECrossRefUpdated handler（SSE cross_ref.updated → 转发 eventBus）
 * 3. 未来 D 循环弹窗的 placeholder dialog refs
 * 4. D 循环特有的 trigger 判定（基于 wpCode）
 * 5. 事件总线订阅/清理的生命周期管理
 *
 * 遵循 CycleEditorAPI 接口模式（design.md）：
 * - dialogs: { [key]: Ref<boolean> }
 * - triggers: { [key]: ComputedRef<boolean> }
 * - handlers: { [key]: (...args) => void | Promise<void> }
 */
import { ref, computed, onMounted, onUnmounted, type Ref, type ComputedRef } from 'vue'
import { eventBus, type CrossRefUpdatedPayload, type SyncEventPayload } from '@/utils/eventBus'
import type { CycleTypeFlags } from './useCycleType'
import type { SheetNavFacadeAPI } from './useSheetNavFacade'

// ─── 接口定义 ─────────────────────────────────────────────────────────────────

export interface DCycleDialogs {
  /** 销售 IPE 弹窗（D2 应收账款审定表专属，待实现） */
  salesIPEDialog: Ref<boolean>
  /** 销售穿透测试弹窗（D 循环穿透抽样，待实现） */
  salesPenetrationDialog: Ref<boolean>
  /** 函证确认弹窗（D0 函证回函确认，待实现） */
  confirmationDialog: Ref<boolean>
}

export interface DCycleTriggers {
  /** 是否显示销售 IPE 按钮（D2 开头的底稿） */
  showSalesIPE: ComputedRef<boolean>
  /** 是否显示穿透测试按钮（D 循环且有 D2 sheet） */
  showPenetration: ComputedRef<boolean>
  /** 是否显示函证确认按钮（D0 开头的底稿） */
  showConfirmation: ComputedRef<boolean>
}

export interface DCycleHandlers {
  /** D0 函证回函 → 刷新 sheet nav + prefill */
  onCrossRefUpdated: (payload: CrossRefUpdatedPayload) => void
  /** SSE cross_ref.updated → 转发为 eventBus cross-ref:updated */
  onSSECrossRefUpdated: (payload: SyncEventPayload) => void
}

export interface DCycleEditorAPI {
  dialogs: DCycleDialogs
  triggers: DCycleTriggers
  handlers: DCycleHandlers
}

// ─── Composable 实现 ──────────────────────────────────────────────────────────

/**
 * D 销售循环编辑器 composable
 *
 * @param wpDetail - 当前底稿详情（含 wp_code）
 * @param projectId - 当前项目 ID
 * @param sheetNav - Sheet 导航 facade（用于 refresh）
 * @param onRefreshPrefill - 刷新预填充回调（由主组件提供）
 */
export function useDCycleEditor(
  wpDetail: Ref<{ wp_code?: string | null } | null>,
  projectId: Ref<string>,
  sheetNav: SheetNavFacadeAPI,
  onRefreshPrefill: () => void | Promise<void>,
): DCycleEditorAPI {
  // ─── Dialogs（placeholder，待未来实现弹窗组件时激活） ─────────────────────────
  const dialogs: DCycleDialogs = {
    salesIPEDialog: ref(false),
    salesPenetrationDialog: ref(false),
    confirmationDialog: ref(false),
  }

  // ─── Triggers ──────────────────────────────────────────────────────────────
  const wpCode = computed(() => (wpDetail.value?.wp_code || '').toUpperCase())

  const triggers: DCycleTriggers = {
    showSalesIPE: computed(() => /^D2/.test(wpCode.value)),
    showPenetration: computed(() => /^D\d/.test(wpCode.value)),
    showConfirmation: computed(() => /^D0/.test(wpCode.value)),
  }

  // ─── Handlers ──────────────────────────────────────────────────────────────

  /**
   * F6 D 销售循环 task 2.12: 响应 cross-ref:updated 事件
   * 当 D0 函证回函触发 stale 传播后，如果当前打开的底稿是目标 wp_code，
   * 自动刷新 sheet nav + 重新触发 prefill 显示
   */
  function onCrossRefUpdated(payload: CrossRefUpdatedPayload) {
    const pid = projectId.value
    if (payload.projectId && payload.projectId !== pid) return
    // 仅当目标 wp_code 匹配当前底稿时刷新
    const currentWpCode = wpDetail.value?.wp_code
    if (payload.targetWpCode && currentWpCode && payload.targetWpCode !== currentWpCode) return
    // 刷新 sheet 分组 + 重新触发 prefill
    sheetNav.refresh()
    onRefreshPrefill()
  }

  /**
   * H-F8: SSE → cross-ref:updated 映射
   * 当后端发布 CROSS_REF_UPDATED 事件（如 H9→H8 租赁回填），
   * 将 SSE payload 转换为 cross-ref:updated eventBus 事件
   */
  function onSSECrossRefUpdated(payload: SyncEventPayload) {
    if (!payload || (payload.event_type as string) !== 'cross_ref.updated') return
    const extra = payload.extra || {}
    eventBus.emit('cross-ref:updated', {
      projectId: payload.project_id || '',
      targetWpCode: extra.target_wp_code || '',
      sourceWpCode: extra.source_wp_code || '',
      refId: extra.ref_id || '',
    })
  }

  const handlers: DCycleHandlers = {
    onCrossRefUpdated,
    onSSECrossRefUpdated,
  }

  // ─── 生命周期：事件总线订阅/清理 ──────────────────────────────────────────────
  onMounted(() => {
    eventBus.on('cross-ref:updated', onCrossRefUpdated)
    eventBus.on('sse:sync-event', onSSECrossRefUpdated)
  })

  onUnmounted(() => {
    eventBus.off('cross-ref:updated', onCrossRefUpdated)
    eventBus.off('sse:sync-event', onSSECrossRefUpdated)
  })

  return { dialogs, triggers, handlers }
}
