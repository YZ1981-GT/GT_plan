import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const SOURCES = {
  tab: '../components/workpaper/AttachmentTabPanel.vue',
  drawer: '../components/workpaper/WorkpaperAttachmentsDrawer.vue',
  dropZone: '../components/workpaper/AttachmentDropZone.vue',
  eye: '../components/attachment/AttachmentEyeButton.vue',
  picker: '../components/common/KnowledgePickerDialog.vue',
  knowledge: '../composables/useKnowledge.ts',
  knowledgeView: '../views/KnowledgeBase.vue',
  projectList: '../views/AttachmentManagement.vue',
  evidence: '../components/workpaper/EvidenceLinkPanel.vue',
  voucher: '../views/ledger/VoucherLinkTags.vue',
} as const

type SourceKey = keyof typeof SOURCES
function sourceOf(key: SourceKey): string {
  return readFileSync(resolve(__dirname, SOURCES[key]), 'utf8')
}

function hasRetryableListState(source: string, statusName: string, retryTestId: string): boolean {
  return source.includes(`${statusName} === 'error'`)
    && source.includes(`${statusName} === 'forbidden'`)
    && source.includes(`data-testid="${retryTestId}"`)
    && source.includes('role="alert"')
}

function hasResponsiveGuard(source: string): boolean {
  return source.includes('@media (max-width: 768px)')
    && source.includes('@media (max-width: 390px)')
}

function hasPreviewFocusReturn(source: string, visibleName: string): boolean {
  return source.includes('let previewOpener: HTMLElement | null = null')
    && source.includes('nextTick(() =>')
    && source.includes('if (opener.isConnected) opener.focus()')
    && source.includes(`watch(${visibleName}, (open) =>`)
}

function hasKeyboardPreviewButton(source: string): boolean {
  return source.includes('<button')
    && source.includes('class="gt-attach-tab__name"')
    && source.includes('@keydown="onItemKeydown($event, att)"')
    && source.includes(':aria-label="`预览附件 ${att.file_name}`"')
}

function hasPreviewAlternativeText(source: string): boolean {
  return source.includes(':alt="previewDoc.name"')
    && source.includes(':title="`预览：${previewDoc.name}`"')
}

function hasPickerFailureState(source: string): boolean {
  return source.includes("searchStatus === 'error' || searchStatus === 'forbidden'")
    && source.includes('data-testid="knowledge-picker-error"')
    && source.includes('aria-label="重试知识库搜索"')
}

describe('附件跨模块 F24-F26 前端可靠性守卫', () => {
  it('扫描到非空的真实附件/知识消费方集合', () => {
    const files = Object.values(SOURCES).map((rel) => resolve(__dirname, rel))
    expect(files.length).toBeGreaterThan(0)
    expect(files.every((file) => readFileSync(file, 'utf8').length > 0)).toBe(true)
  })

  it('底稿附件列表区分失败/无权与空态，并有取消、重试和窄屏键盘样式', () => {
    const tab = sourceOf('tab')
    const drawer = sourceOf('drawer')
    expect(hasRetryableListState(tab, 'listStatus', 'attachment-tab-retry')).toBe(true)
    expect(hasRetryableListState(drawer, 'loadStatus', 'wp-att-retry')).toBe(true)
    for (const source of [tab, drawer]) {
      expect(source).toContain('signal: controller.signal')
      expect(source).toContain('_dedupe: false')
      expect(hasResponsiveGuard(source)).toBe(true)
    }
  })

  it('项目附件页仍使用现有 page/page_size 服务端分页契约', () => {
    const source = sourceOf('projectList')
    expect(source).toContain('page: page.value')
    expect(source).toContain('page_size: pageSize.value')
    expect(source).toContain('<el-pagination')
    expect(source).toContain('gt-att-loading-state')
  })

  it('预览、知识搜索和上传互斥都保留取消/失败可见边界', () => {
    const eye = sourceOf('eye')
    const picker = sourceOf('picker')
    const knowledge = sourceOf('knowledge')
    const knowledgeView = sourceOf('knowledgeView')
    const dropZone = sourceOf('dropZone')
    expect(eye).toContain('openAbort?.abort()')
    expect(eye).toContain('signal: controller.signal')
    expect(eye).toContain('cancelOpen()')
    expect(eye).toContain(':title="`预览 ${displayName}`"')
    expect(picker).toContain('data-testid="knowledge-picker-error"')
    expect(picker).toContain('aria-label="重试知识库搜索"')
    expect(knowledge).toContain('searchStatus.value = status === 403 ? \'forbidden\' : \'error\'')
    expect(knowledge).toContain('throw error')
    expect(knowledgeView).toContain('v-if="docLoading"')
    expect(knowledgeView).toContain('正在加载文档列表')
    expect(knowledgeView).toContain('docError && selectedFolder')
    expect((dropZone.match(/if \(uploading\.value\)/g) || []).length).toBeGreaterThanOrEqual(2)
  })

  it('键盘入口和标题/可读名集合非空', () => {
    const tab = sourceOf('tab')
    const drawer = sourceOf('drawer')
    const picker = sourceOf('picker')
    expect(tab).toContain('@keydown="onItemKeydown($event, att)"')
    expect(tab).toContain(':aria-label="`预览附件 ${att.file_name}`"')
    expect(drawer).toContain('<button type="button" class="wp-att-item__name"')
    expect(drawer).toContain(':title="`预览 ${row.file_name || \'\'}`"')
    expect(picker).toContain('aria-label="搜索知识库文档"')
    expect([tab, drawer, picker].filter((source) => source.includes('aria-label')).length).toBe(3)
  })

  it('键盘、焦点、替代文本和断点契约覆盖真实消费方', () => {
    const tab = sourceOf('tab')
    const drawer = sourceOf('drawer')
    const eye = sourceOf('eye')
    const projectList = sourceOf('projectList')
    const picker = sourceOf('picker')
    const knowledgeView = sourceOf('knowledgeView')
    const evidence = sourceOf('evidence')
    const voucher = sourceOf('voucher')

    expect(hasKeyboardPreviewButton(tab)).toBe(true)
    expect(hasPreviewFocusReturn(tab, 'drawerOpen')).toBe(true)
    expect(hasPreviewFocusReturn(drawer, 'previewVisible')).toBe(true)
    expect(hasPreviewFocusReturn(eye, 'visible')).toBe(true)
    expect(hasPreviewFocusReturn(projectList, 'previewVisible')).toBe(true)
    expect(hasPreviewAlternativeText(knowledgeView)).toBe(true)
    expect(picker).toContain('ref="searchInputRef"')
    expect(evidence).toContain('aria-label="关联已有附件"')
    expect(voucher).toContain('aria-label="重试凭证挂接状态查询"')
    expect(voucher).toContain('aria-label="重试凭证证据查询"')

    for (const source of [tab, drawer, projectList, picker, knowledgeView, evidence, voucher]) {
      expect(hasResponsiveGuard(source)).toBe(true)
    }
  })

  it('正向守卫在关键行为被变异删除时失败，而不是恒绿', () => {
    const tab = sourceOf('tab')
    const eye = sourceOf('eye')
    const knowledgeView = sourceOf('knowledgeView')
    const voucher = sourceOf('voucher')

    const noKeyboard = tab.replace('@keydown="onItemKeydown($event, att)"', '')
    const noFocusGuard = tab.replace('if (opener.isConnected) opener.focus()', 'opener.focus()')
    const noAlt = knowledgeView.replace(':alt="previewDoc.name"', '')
    const noNarrowLayout = voucher.replace('@media (max-width: 390px)', '')

    expect(hasKeyboardPreviewButton(noKeyboard)).toBe(false)
    expect(hasPreviewFocusReturn(tab, 'drawerOpen')).toBe(true)
    expect(hasPreviewFocusReturn(noFocusGuard, 'drawerOpen')).toBe(false)
    expect(hasPreviewAlternativeText(noAlt)).toBe(false)
    expect(hasResponsiveGuard(noNarrowLayout)).toBe(false)
    expect(hasPreviewFocusReturn(eye, 'visible')).toBe(true)
  })

  it('反向变异会让守卫失败，防止把失败态/响应式断言改成恒绿', () => {
    const tab = sourceOf('tab')
    const picker = sourceOf('picker')
    const eye = sourceOf('eye')
    const narrowTab = tab.replace('@media (max-width: 390px)', '')
    const emptyTab = tab.replace("listStatus === 'error' || listStatus === 'forbidden'", "listStatus === 'empty'")
    const emptyPicker = picker.replace("searchStatus === 'error' || searchStatus === 'forbidden'", "searchStatus === 'empty'")
    const noAbortEye = eye.replaceAll('openAbort?.abort()', '')
    expect(hasResponsiveGuard(narrowTab)).toBe(false)
    expect(hasRetryableListState(emptyTab, 'listStatus', 'attachment-tab-retry')).toBe(false)
    expect(hasPickerFailureState(picker)).toBe(true)
    expect(hasPickerFailureState(emptyPicker)).toBe(false)
    expect(noAbortEye).not.toContain('openAbort?.abort()')
  })
})
