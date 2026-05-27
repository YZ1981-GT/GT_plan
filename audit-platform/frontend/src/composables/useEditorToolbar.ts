/**
 * useEditorToolbar — 底稿编辑器工具栏配置声明式数组 [V3 Req 12.1.1]
 *
 * 骨架已建 + 示范提取，完整瘦身需独立 Sprint。
 * 将 WorkpaperEditor.vue 中的 toolbar 按钮逻辑抽离为声明式配置，
 * 主组件通过 v-for 渲染，减少 ~300 行 if/else 模板代码。
 *
 * @example
 * const { availableButtons, handleAction } = useEditorToolbar({
 *   canEdit, saving, dirty, wpDetail, hasPrefillMapping, prefillLoading, submitting,
 *   onSave, onRefreshPrefill, onSubmitForReview, onSyncStructure, onShowVersions,
 *   onDownload, onExportPdf, onUpload,
 * })
 */
import { computed, type Ref, type ComputedRef } from 'vue'

export interface ToolbarButton {
  key: string
  label: string
  icon?: string
  action: string
  /** 按钮类型 */
  type?: 'primary' | 'success' | 'warning' | 'danger' | 'info' | ''
  /** 是否 plain 样式 */
  plain?: boolean
  /** 快捷键提示 */
  shortcut?: string
  /** 需要编辑权限 */
  requireEdit?: boolean
  /** 需要选区 */
  requireSelection?: boolean
  /** 分组标识 */
  group?: 'primary' | 'secondary' | 'more'
  /** 是否 loading */
  loading?: ComputedRef<boolean> | Ref<boolean>
  /** 是否 disabled */
  disabled?: ComputedRef<boolean> | Ref<boolean>
  /** tooltip 内容 */
  tooltip?: string | ComputedRef<string>
}

export interface EditorToolbarContext {
  canEdit: ComputedRef<boolean>
  saving: Ref<boolean>
  dirty: Ref<boolean>
  submitting?: Ref<boolean>
  prefillLoading?: Ref<boolean>
  hasPrefillMapping?: ComputedRef<boolean>
  fineCheckFailCount?: ComputedRef<number>
  wpStatus?: ComputedRef<string>
}

export interface EditorToolbarActions {
  onSave: () => void
  onRefreshPrefill?: () => void
  onSubmitForReview?: () => void
  onSyncStructure?: () => void
  onShowVersions?: () => void
  onDownload?: () => void
  onExportPdf?: () => void
  onUpload?: () => void
  onManualRefresh?: () => void
}

/**
 * 工具栏按钮声明式配置（示范：主要操作组）
 * 完整迁移时将 WorkpaperEditor.vue 模板中 ~300 行按钮逻辑替换为 v-for 渲染
 */
export const PRIMARY_TOOLBAR_BUTTONS: ToolbarButton[] = [
  {
    key: 'save',
    label: '💾 保存',
    action: 'save',
    type: 'primary',
    group: 'primary',
    requireEdit: true,
    shortcut: 'Ctrl+S',
  },
  {
    key: 'prefill',
    label: '📊 一键填充',
    action: 'refreshPrefill',
    type: 'primary',
    plain: true,
    group: 'primary',
    tooltip: '从试算表重新取数填入底稿',
  },
  {
    key: 'submitReview',
    label: '📨 提交复核',
    action: 'submitForReview',
    type: 'success',
    group: 'primary',
    requireEdit: true,
  },
]

export const MORE_DROPDOWN_ITEMS: ToolbarButton[] = [
  { key: 'syncFormula', label: '🔄 同步公式', action: 'syncStructure', group: 'more' },
  { key: 'versions', label: '📋 版本历史', action: 'showVersions', group: 'more' },
  { key: 'download', label: '📥 下载', action: 'download', group: 'more' },
  { key: 'exportPdf', label: '📄 导出 PDF', action: 'exportPdf', group: 'more' },
  { key: 'upload', label: '📤 上传新版本', action: 'upload', group: 'more' },
]

/**
 * 示范 composable：根据上下文计算可用按钮列表 + 统一 action dispatcher
 */
export function useEditorToolbar(
  ctx: EditorToolbarContext,
  actions: EditorToolbarActions,
) {
  const actionMap: Record<string, (() => void) | undefined> = {
    save: actions.onSave,
    refreshPrefill: actions.onRefreshPrefill,
    submitForReview: actions.onSubmitForReview,
    syncStructure: actions.onSyncStructure,
    showVersions: actions.onShowVersions,
    download: actions.onDownload,
    exportPdf: actions.onExportPdf,
    upload: actions.onUpload,
    manualRefresh: actions.onManualRefresh,
  }

  /** 根据当前状态过滤可用按钮 */
  const availableButtons = computed(() => {
    return PRIMARY_TOOLBAR_BUTTONS.filter((btn) => {
      if (btn.requireEdit && !ctx.canEdit.value) return false
      return true
    })
  })

  /** 统一 action 分发 */
  function handleAction(actionKey: string) {
    const fn = actionMap[actionKey]
    if (fn) fn()
  }

  return { availableButtons, handleAction, PRIMARY_TOOLBAR_BUTTONS, MORE_DROPDOWN_ITEMS }
}
