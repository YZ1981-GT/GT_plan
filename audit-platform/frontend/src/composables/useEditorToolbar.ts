/**
 * useEditorToolbar — 底稿编辑器工具栏配置声明式数组 [V3 Req 12.1.1]
 *
 * 将 WorkpaperEditor.vue 中的 toolbar 按钮逻辑抽离为声明式配置数组
 * + 统一 handleAction dispatcher，主组件通过 v-for 渲染。
 *
 * 设计原则：
 *  - 静态配置数组 PRIMARY_TOOLBAR_BUTTONS / MORE_DROPDOWN_ITEMS 作为声明式
 *    入口，单元测试可针对纯结构断言（key / label / requireEdit）。
 *  - 运行时通过 enrichedButtons computed 注入 loading / disabled / 动态
 *    label / type / tooltip / title，避免模板 if/else。
 *  - handleAction(key) 通过 actionMap 分发；未知 key 静默（no-op）。
 *
 * @example
 * const {
 *   availableButtons,        // primary 区按钮（含 requireEdit / wpStatus 过滤 + enrich）
 *   dropdownItems,           // 更多 ▾ 下拉项（含 enrich）
 *   handleAction,            // 统一分发
 *   PRIMARY_TOOLBAR_BUTTONS, // 静态配置（测试用）
 *   MORE_DROPDOWN_ITEMS,     // 静态配置（测试用）
 * } = useEditorToolbar(
 *   { canEdit, saving, dirty, submitting, prefillLoading, hasPrefillMapping,
 *     fineCheckFailCount, wpStatus, manualRefreshing },
 *   { onSave, onRefreshPrefill, onSubmitForReview, onSyncStructure,
 *     onShowVersions, onDownload, onExportPdf, onUpload, onManualRefresh },
 * )
 */
import { computed, type Ref, type ComputedRef } from 'vue'

/** 静态按钮声明 — 测试可断言纯结构 */
export interface ToolbarButton {
  key: string
  label: string
  action: string
  type?: '' | 'primary' | 'success' | 'warning' | 'danger' | 'info'
  plain?: boolean
  /** 快捷键提示（仅展示，dispatch 由 handleAction 触发） */
  shortcut?: string
  /** 需要编辑权限（canEdit=false 时被 availableButtons 过滤） */
  requireEdit?: boolean
  /** dropdown item 上方分隔线 */
  divided?: boolean
  /** v-permission 指令值（dropdown item 用） */
  permission?: string
  /** 仅当 wpStatus === 该值时可见（如 submitReview 仅在 draft 显示） */
  visibleWhenStatus?: string
  /** 静态 tooltip 文本（动态文本走 enriched.tooltip） */
  staticTooltip?: string
  group?: 'primary' | 'standalone' | 'more'
}

/** v-for 渲染时使用的运行时按钮（注入了响应式状态） */
export interface EnrichedToolbarButton extends ToolbarButton {
  /** 动态 label（如 "提交复核 (3)"），优先于静态 label */
  dynamicLabel?: string
  /** 动态 type（如 fineCheckFailCount>0 时切 warning） */
  dynamicType?: ToolbarButton['type']
  /** 当前是否 loading */
  loading: boolean
  /** 当前是否 disabled */
  disabled: boolean
  /** 完整 tooltip 内容（运行时计算，null = 不渲染 el-tooltip 包裹） */
  tooltip: string | null
  /** 原生 title 属性（hover 灰提示，常用于 disabled 解释） */
  title: string
}

export interface EditorToolbarContext {
  canEdit: ComputedRef<boolean>
  saving: Ref<boolean>
  dirty: Ref<boolean>
  submitting?: Ref<boolean>
  prefillLoading?: Ref<boolean>
  hasPrefillMapping?: Ref<boolean> | ComputedRef<boolean>
  fineCheckFailCount?: Ref<number> | ComputedRef<number>
  wpStatus?: Ref<string | undefined> | ComputedRef<string | undefined>
  manualRefreshing?: Ref<boolean>
}

export interface EditorToolbarActions {
  onSave: () => void | Promise<unknown>
  onRefreshPrefill?: () => void | Promise<unknown>
  onSubmitForReview?: () => void | Promise<unknown>
  onSyncStructure?: () => void | Promise<unknown>
  onShowVersions?: () => void | Promise<unknown>
  onDownload?: () => void | Promise<unknown>
  onExportPdf?: () => void | Promise<unknown>
  onUpload?: () => void | Promise<unknown>
  onManualRefresh?: () => void | Promise<unknown>
}

/**
 * 主操作区按钮（保存 / 一键填充 / 提交复核 / 刷新取数）
 * — 一键填充 / 提交复核 / 刷新取数的 tooltip / type / label 在 enrichButton 内动态计算。
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
  },
  {
    key: 'submitReview',
    label: '📨 提交复核',
    action: 'submitForReview',
    type: 'success',
    group: 'primary',
    requireEdit: true,
    visibleWhenStatus: 'draft',
  },
  {
    key: 'manualRefresh',
    label: '🔄 刷新取数',
    action: 'manualRefresh',
    plain: true,
    group: 'standalone',
    staticTooltip: '重新执行预填充并触发受影响 sheet 刷新',
  },
]

/** 更多 ▾ 下拉菜单 */
export const MORE_DROPDOWN_ITEMS: ToolbarButton[] = [
  { key: 'syncFormula', label: '🔄 同步公式', action: 'syncStructure', group: 'more' },
  { key: 'versions', label: '📋 版本历史', action: 'showVersions', group: 'more' },
  { key: 'download', label: '📥 下载', action: 'download', group: 'more' },
  { key: 'exportPdf', label: '📄 导出 PDF', action: 'exportPdf', group: 'more', permission: 'workpaper:export' },
  { key: 'upload', label: '📤 上传新版本', action: 'upload', group: 'more', divided: true },
]

/**
 * 主 composable：根据上下文计算可用按钮 + enrich 运行时态 + 统一 dispatch
 */
export function useEditorToolbar(
  ctx: EditorToolbarContext,
  actions: EditorToolbarActions,
) {
  const actionMap: Record<string, (() => void | Promise<unknown>) | undefined> = {
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

  /** 注入运行时态：loading / disabled / 动态 label / 动态 type / tooltip / title */
  function enrichButton(btn: ToolbarButton): EnrichedToolbarButton {
    const archivedTitle = !ctx.canEdit.value ? '项目已归档,无法编辑' : ''
    const dirty = ctx.dirty.value
    const failCount = ctx.fineCheckFailCount?.value ?? 0
    const hasPrefill = ctx.hasPrefillMapping?.value ?? true

    let dynamicLabel: string | undefined
    let dynamicType: ToolbarButton['type'] | undefined
    let loading = false
    let disabled = false
    let tooltip: string | null = btn.staticTooltip ?? null
    let title = ''

    switch (btn.action) {
      case 'save':
        loading = ctx.saving.value
        disabled = !ctx.canEdit.value
        title = archivedTitle
        break
      case 'refreshPrefill':
        loading = !!ctx.prefillLoading?.value
        disabled = !hasPrefill
        tooltip = hasPrefill ? '从试算表重新取数填入底稿' : '当前底稿无预设公式配置'
        break
      case 'submitForReview':
        loading = !!ctx.submitting?.value
        disabled = !ctx.canEdit.value || dirty
        title = archivedTitle
        if (failCount > 0) {
          dynamicLabel = `⚠️ 提交复核 (${failCount})`
          dynamicType = 'warning'
          tooltip = `当前有 ${failCount} 项自检未通过`
        }
        break
      case 'manualRefresh':
        loading = !!ctx.manualRefreshing?.value
        break
      default:
        // dropdown items: no extra runtime state
        break
    }

    return { ...btn, dynamicLabel, dynamicType, loading, disabled, tooltip, title }
  }

  /** 主操作区可见按钮：requireEdit + visibleWhenStatus 过滤后 enrich */
  const availableButtons = computed<EnrichedToolbarButton[]>(() => {
    const status = ctx.wpStatus?.value ?? ''
    return PRIMARY_TOOLBAR_BUTTONS
      .filter((btn) => {
        if (btn.requireEdit && !ctx.canEdit.value) return false
        if (btn.visibleWhenStatus && status !== btn.visibleWhenStatus) return false
        return true
      })
      .map(enrichButton)
  })

  /** 下拉项 enrich（permission 由模板 v-permission 处理） */
  const dropdownItems = computed<EnrichedToolbarButton[]>(() =>
    MORE_DROPDOWN_ITEMS.map(enrichButton),
  )

  /** 统一 action 分发（未知 key 静默 no-op） */
  function handleAction(actionKey: string) {
    const fn = actionMap[actionKey]
    if (fn) fn()
  }

  return {
    availableButtons,
    dropdownItems,
    handleAction,
    PRIMARY_TOOLBAR_BUTTONS,
    MORE_DROPDOWN_ITEMS,
  }
}
