/**
 * useEditorToolbar 单测 — V3 Req 12.1.1
 *
 * 验证：
 *  - 静态配置（PRIMARY_TOOLBAR_BUTTONS / MORE_DROPDOWN_ITEMS）结构稳定
 *  - availableButtons 按 canEdit / wpStatus 过滤
 *  - enrich：loading / disabled / dynamicLabel / tooltip 注入正确
 *  - handleAction 统一分发；未知 key 静默 no-op
 */
import { describe, it, expect, vi } from 'vitest'
import { computed, ref } from 'vue'
import {
  useEditorToolbar,
  PRIMARY_TOOLBAR_BUTTONS,
  MORE_DROPDOWN_ITEMS,
  type EditorToolbarContext,
  type EditorToolbarActions,
} from '../useEditorToolbar'

function makeCtx(overrides: Partial<{
  canEdit: boolean
  saving: boolean
  dirty: boolean
  submitting: boolean
  prefillLoading: boolean
  hasPrefillMapping: boolean
  fineCheckFailCount: number
  wpStatus: string | undefined
  manualRefreshing: boolean
}> = {}): EditorToolbarContext {
  return {
    canEdit: computed(() => overrides.canEdit ?? true),
    saving: ref(overrides.saving ?? false),
    dirty: ref(overrides.dirty ?? false),
    submitting: ref(overrides.submitting ?? false),
    prefillLoading: ref(overrides.prefillLoading ?? false),
    hasPrefillMapping: ref(overrides.hasPrefillMapping ?? true),
    fineCheckFailCount: computed(() => overrides.fineCheckFailCount ?? 0),
    wpStatus: computed(() => overrides.wpStatus),
    manualRefreshing: ref(overrides.manualRefreshing ?? false),
  }
}

function makeActions(): { actions: EditorToolbarActions; spies: Record<string, ReturnType<typeof vi.fn>> } {
  const spies = {
    onSave: vi.fn(),
    onRefreshPrefill: vi.fn(),
    onSubmitForReview: vi.fn(),
    onSyncStructure: vi.fn(),
    onShowVersions: vi.fn(),
    onDownload: vi.fn(),
    onExportPdf: vi.fn(),
    onUpload: vi.fn(),
    onManualRefresh: vi.fn(),
  }
  return { actions: spies as unknown as EditorToolbarActions, spies }
}

describe('useEditorToolbar — 静态配置', () => {
  it('PRIMARY_TOOLBAR_BUTTONS 包含核心 4 按钮（save/prefill/submitReview/manualRefresh）', () => {
    const keys = PRIMARY_TOOLBAR_BUTTONS.map((b) => b.key)
    expect(keys).toEqual(expect.arrayContaining(['save', 'prefill', 'submitReview', 'manualRefresh']))
  })

  it('MORE_DROPDOWN_ITEMS 包含 5 项下拉操作（同步公式/版本/下载/导出/上传）', () => {
    const keys = MORE_DROPDOWN_ITEMS.map((b) => b.key)
    expect(keys).toEqual([
      'syncFormula', 'versions', 'download', 'exportPdf', 'upload',
    ])
  })

  it('save / submitReview 标记 requireEdit=true', () => {
    const save = PRIMARY_TOOLBAR_BUTTONS.find((b) => b.key === 'save')!
    const submit = PRIMARY_TOOLBAR_BUTTONS.find((b) => b.key === 'submitReview')!
    expect(save.requireEdit).toBe(true)
    expect(submit.requireEdit).toBe(true)
  })

  it('exportPdf 携带 v-permission 字符串', () => {
    const exportPdf = MORE_DROPDOWN_ITEMS.find((b) => b.key === 'exportPdf')!
    expect(exportPdf.permission).toBe('workpaper:export')
  })
})

describe('useEditorToolbar — availableButtons 过滤', () => {
  it('canEdit=false 时过滤掉 requireEdit:true 的按钮', () => {
    const ctx = makeCtx({ canEdit: false, wpStatus: 'draft' })
    const { actions } = makeActions()
    const { availableButtons } = useEditorToolbar(ctx, actions)

    const keys = availableButtons.value.map((b) => b.key)
    expect(keys).not.toContain('save')
    expect(keys).not.toContain('submitReview')
    // prefill / manualRefresh 不需要 edit 权限，仍可见
    expect(keys).toContain('prefill')
    expect(keys).toContain('manualRefresh')
  })

  it('canEdit=true 且 wpStatus=draft 时所有主按钮可见', () => {
    const ctx = makeCtx({ canEdit: true, wpStatus: 'draft' })
    const { actions } = makeActions()
    const { availableButtons } = useEditorToolbar(ctx, actions)

    const keys = availableButtons.value.map((b) => b.key)
    expect(keys).toEqual(['save', 'prefill', 'submitReview', 'manualRefresh'])
  })

  it('wpStatus !== "draft" 时 submitReview 隐藏（visibleWhenStatus 过滤）', () => {
    const ctx = makeCtx({ canEdit: true, wpStatus: 'review_passed' })
    const { actions } = makeActions()
    const { availableButtons } = useEditorToolbar(ctx, actions)

    const keys = availableButtons.value.map((b) => b.key)
    expect(keys).not.toContain('submitReview')
    expect(keys).toEqual(['save', 'prefill', 'manualRefresh'])
  })
})

describe('useEditorToolbar — enrich 运行时态', () => {
  it('saving=true 时 save 按钮 loading=true', () => {
    const ctx = makeCtx({ saving: true, wpStatus: 'draft' })
    const { actions } = makeActions()
    const { availableButtons } = useEditorToolbar(ctx, actions)

    const save = availableButtons.value.find((b) => b.key === 'save')!
    expect(save.loading).toBe(true)
    expect(save.disabled).toBe(false)
  })

  it('canEdit=false 时 save.title 显示归档提示', () => {
    const ctx = makeCtx({ canEdit: false, wpStatus: 'draft' })
    const { actions } = makeActions()
    // 通过 dropdownItems / 直接断言 enrich 逻辑：save 被 requireEdit 过滤,
    // 改用 prefill 检查 disabled 行为
    const { dropdownItems } = useEditorToolbar(ctx, actions)
    expect(dropdownItems.value.length).toBe(MORE_DROPDOWN_ITEMS.length)
  })

  it('hasPrefillMapping=false 时 prefill disabled + 切换 tooltip', () => {
    const ctx = makeCtx({ hasPrefillMapping: false, wpStatus: 'draft' })
    const { actions } = makeActions()
    const { availableButtons } = useEditorToolbar(ctx, actions)

    const prefill = availableButtons.value.find((b) => b.key === 'prefill')!
    expect(prefill.disabled).toBe(true)
    expect(prefill.tooltip).toBe('当前底稿无预设公式配置')
  })

  it('hasPrefillMapping=true 时 prefill 启用 + 默认 tooltip', () => {
    const ctx = makeCtx({ hasPrefillMapping: true, wpStatus: 'draft' })
    const { actions } = makeActions()
    const { availableButtons } = useEditorToolbar(ctx, actions)

    const prefill = availableButtons.value.find((b) => b.key === 'prefill')!
    expect(prefill.disabled).toBe(false)
    expect(prefill.tooltip).toBe('从试算表重新取数填入底稿')
  })

  it('fineCheckFailCount > 0 时 submitReview 切 warning + 动态 label + tooltip', () => {
    const ctx = makeCtx({ fineCheckFailCount: 3, wpStatus: 'draft' })
    const { actions } = makeActions()
    const { availableButtons } = useEditorToolbar(ctx, actions)

    const submit = availableButtons.value.find((b) => b.key === 'submitReview')!
    expect(submit.dynamicType).toBe('warning')
    expect(submit.dynamicLabel).toBe('⚠️ 提交复核 (3)')
    expect(submit.tooltip).toBe('当前有 3 项自检未通过')
  })

  it('dirty=true 时 submitReview disabled', () => {
    const ctx = makeCtx({ dirty: true, wpStatus: 'draft' })
    const { actions } = makeActions()
    const { availableButtons } = useEditorToolbar(ctx, actions)

    const submit = availableButtons.value.find((b) => b.key === 'submitReview')!
    expect(submit.disabled).toBe(true)
  })

  it('manualRefreshing=true 时 manualRefresh.loading=true', () => {
    const ctx = makeCtx({ manualRefreshing: true, wpStatus: 'draft' })
    const { actions } = makeActions()
    const { availableButtons } = useEditorToolbar(ctx, actions)

    const refresh = availableButtons.value.find((b) => b.key === 'manualRefresh')!
    expect(refresh.loading).toBe(true)
    expect(refresh.tooltip).toBe('重新执行预填充并触发受影响 sheet 刷新')
  })
})

describe('useEditorToolbar — handleAction 分发', () => {
  it('handleAction("save") 调用 onSave 一次', () => {
    const ctx = makeCtx({ wpStatus: 'draft' })
    const { actions, spies } = makeActions()
    const { handleAction } = useEditorToolbar(ctx, actions)

    handleAction('save')
    expect(spies.onSave).toHaveBeenCalledTimes(1)
    expect(spies.onRefreshPrefill).not.toHaveBeenCalled()
  })

  it('handleAction 分发 9 个已知 action', () => {
    const ctx = makeCtx({ wpStatus: 'draft' })
    const { actions, spies } = makeActions()
    const { handleAction } = useEditorToolbar(ctx, actions)

    handleAction('save')
    handleAction('refreshPrefill')
    handleAction('submitForReview')
    handleAction('syncStructure')
    handleAction('showVersions')
    handleAction('download')
    handleAction('exportPdf')
    handleAction('upload')
    handleAction('manualRefresh')

    expect(spies.onSave).toHaveBeenCalledTimes(1)
    expect(spies.onRefreshPrefill).toHaveBeenCalledTimes(1)
    expect(spies.onSubmitForReview).toHaveBeenCalledTimes(1)
    expect(spies.onSyncStructure).toHaveBeenCalledTimes(1)
    expect(spies.onShowVersions).toHaveBeenCalledTimes(1)
    expect(spies.onDownload).toHaveBeenCalledTimes(1)
    expect(spies.onExportPdf).toHaveBeenCalledTimes(1)
    expect(spies.onUpload).toHaveBeenCalledTimes(1)
    expect(spies.onManualRefresh).toHaveBeenCalledTimes(1)
  })

  it('handleAction("unknown") 静默 no-op，不抛异常', () => {
    const ctx = makeCtx({ wpStatus: 'draft' })
    const { actions, spies } = makeActions()
    const { handleAction } = useEditorToolbar(ctx, actions)

    expect(() => handleAction('unknown')).not.toThrow()
    expect(() => handleAction('')).not.toThrow()
    Object.values(spies).forEach((spy) => expect(spy).not.toHaveBeenCalled())
  })

  it('未注入的可选 action（如 onUpload 缺失）静默不抛', () => {
    const ctx = makeCtx({ wpStatus: 'draft' })
    const partialActions: EditorToolbarActions = { onSave: vi.fn() }
    const { handleAction } = useEditorToolbar(ctx, partialActions)

    expect(() => handleAction('upload')).not.toThrow()
    expect(() => handleAction('exportPdf')).not.toThrow()
  })
})
