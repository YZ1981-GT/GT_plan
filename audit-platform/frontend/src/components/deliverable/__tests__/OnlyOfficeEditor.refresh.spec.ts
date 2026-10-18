/**
 * OnlyOfficeEditor —— 章节刷新后切到新版本 + 会话内修改检测（spec deliverable-trio-generation-accuracy Task 16b）
 *
 * 🔴 原实现刷新后编辑器仍是旧版本：用户看不到刷新结果，接着编辑保存（OnlyOffice 回调不比对版本）会盖掉刷新。
 */
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { mockConfig, mockDownload, mockWarning, mockStates } = vi.hoisted(() => ({
  mockConfig: vi.fn(),
  mockDownload: vi.fn(),
  mockWarning: vi.fn(),
  mockStates: vi.fn(),
}))

vi.mock('@/services/deliverableApi', () => ({
  fetchOnlyOfficeHealth: async () => ({ enabled: true, available: true }),
  fetchOnlyOfficeConfig: (...args: any[]) => mockConfig(...args),
  // 与真实端点同形：{ sections: [...] }
  fetchSectionStates: (...args: any[]) => mockStates(...args),
  deliverableDownloadUrl: (_p: string, _t: string, v: number) => `/download/v${v}.docx`,
}))
vi.mock('@/utils/http', () => ({ downloadFile: (...args: any[]) => mockDownload(...args) }))
vi.mock('element-plus', async () => {
  const real = await vi.importActual<any>('element-plus')
  return { ...real, ElMessage: { ...real.ElMessage, warning: (...a: any[]) => mockWarning(...a) } }
})

import OnlyOfficeEditor from '../OnlyOfficeEditor.vue'

interface FakeEditor {
  id: string
  config: Record<string, any>
  destroyed: boolean
}
let editors: FakeEditor[] = []

class FakeDocEditor {
  record: FakeEditor
  constructor(id: string, config: Record<string, any>) {
    this.record = { id, config, destroyed: false }
    editors.push(this.record)
  }
  destroyEditor() {
    this.record.destroyed = true
  }
}

const LineageStub = defineComponent({
  name: 'LineagePanel',
  props: ['projectId', 'wordExportTaskId', 'year', 'deliverableStatus', 'hasNoAnchors',
    'supportsSectionRefresh', 'editorHasUnsavedEdits'],
  emits: ['refreshed'],
  setup: () => () => h('div', { class: 'lineage-stub' }),
})

function mountEditor() {
  return mount(OnlyOfficeEditor, {
    props: {
      projectId: 'p1', taskId: 't1', versionNo: 1, year: 2025, title: 'disclosure_notes_2025.docx',
      previewType: 'docx' as const, previewUrl: '/download/v1.docx', deliverableStatus: 'editing',
      supportsSectionRefresh: true, docType: 'disclosure_notes',
    },
    global: {
      stubs: {
        'el-dialog': {
          template: '<div class="dialog-stub"><slot name="header" :close="() => {}" title-id="t" title-class="c" />'
            + '<slot /><slot name="footer" /></div>',
        },
        'el-button': { template: '<button class="btn-stub" @click="$emit(\'click\')"><slot /></button>', emits: ['click'] },
        'el-alert': true,
        'el-skeleton': true,
        LineagePanel: LineageStub,
        WritebackResultPanel: true,
        WritebackConflictDialog: true,
        DeliverablePreview: true,
      },
    },
  })
}

async function openLineage(wrapper: ReturnType<typeof mountEditor>) {
  const toggle = wrapper.findAll('.btn-stub').find((b) => b.text() === '查看溯源')
  await toggle!.trigger('click')
  return wrapper.findComponent(LineageStub)
}

describe('OnlyOfficeEditor —— 章节刷新后切到新版本（16b）', () => {
  beforeEach(() => {
    editors = []
    mockConfig.mockReset()
    mockDownload.mockReset()
    mockWarning.mockReset()
    mockConfig.mockImplementation(async (_p: string, _t: string, v: number) => ({
      config: { document: { key: `key-v${v}` } }, token: `jwt-v${v}`,
    }))
    mockStates.mockReset()
    mockStates.mockResolvedValue({ sections: [{ section_code: '八、1' }] })
    ;(window as any).DocsAPI = { DocEditor: FakeDocEditor }
  })
  afterEach(() => {
    delete (window as any).DocsAPI
  })

  it('打开时按传入版本建编辑器（token 并入配置）', async () => {
    mountEditor()
    await flushPromises()
    expect(editors).toHaveLength(1)
    expect(editors[0].config.document.key).toBe('key-v1')
    expect(editors[0].config.token).toBe('jwt-v1')
  })

  it('刷新落新版本 ⇒ 取新版本配置、销毁旧编辑器、在同一容器建新编辑器，并通知交付中心', async () => {
    const wrapper = mountEditor()
    await flushPromises()
    const panel = await openLineage(wrapper)
    panel.vm.$emit('refreshed', 15)
    await flushPromises()

    expect(mockConfig).toHaveBeenLastCalledWith('p1', 't1', 15, 2025)
    expect(editors).toHaveLength(2)
    expect(editors[0].destroyed).toBe(true)
    expect(editors[1].config.document.key).toBe('key-v15')
    expect(editors[1].id).toBe(editors[0].id)
    expect(wrapper.emitted('version-changed')).toEqual([[15]])
    // 标题注明已切换（打开时的文件名是旧版本的）
    expect(wrapper.find('.onlyoffice-editor__title').text()).toBe('disclosure_notes_2025.docx（已切换到第 15 版）')

    // 下载按钮下载的是新版本，文件名同后端刷新落盘口径
    await wrapper.findAll('.btn-stub').find((b) => b.text() === '下载')!.trigger('click')
    expect(mockDownload).toHaveBeenCalledWith('/download/v15.docx', { fileName: 'disclosure_notes_v15.docx' })
  })

  it('未切换版本时标题与下载沿用打开时的文件名', async () => {
    const wrapper = mountEditor()
    await flushPromises()
    expect(wrapper.find('.onlyoffice-editor__title').text()).toBe('disclosure_notes_2025.docx')
    await wrapper.findAll('.btn-stub').find((b) => b.text() === '下载')!.trigger('click')
    expect(mockDownload).toHaveBeenCalledWith('/download/v1.docx', { fileName: 'disclosure_notes_2025.docx' })
  })

  it('新版本配置取不到 ⇒ 保留旧编辑器并提示重新打开', async () => {
    const wrapper = mountEditor()
    await flushPromises()
    const panel = await openLineage(wrapper)
    mockConfig.mockRejectedValueOnce(new Error('429'))
    panel.vm.$emit('refreshed', 16)
    await flushPromises()

    expect(editors).toHaveLength(1)
    expect(editors[0].destroyed).toBe(false)
    expect(mockWarning).toHaveBeenCalledWith(expect.stringContaining('已另存为第 16 版'))
    expect(wrapper.emitted('version-changed')).toEqual([[16]])
  })

  it('无锚点判定按端点真实形态（{ sections }）：空 ⇒ 面板提示不支持溯源；非空 ⇒ 不提示', async () => {
    mockStates.mockResolvedValue({ sections: [] })
    const empty = mountEditor()
    await flushPromises()
    expect((await openLineage(empty)).props('hasNoAnchors')).toBe(true)

    mockStates.mockResolvedValue({ sections: [{ section_code: '八、1' }] })
    const anchored = mountEditor()
    await flushPromises()
    expect((await openLineage(anchored)).props('hasNoAnchors')).toBe(false)
  })

  it('会话内修改：文档载入后的修改才算；切到新版本后清零', async () => {
    const wrapper = mountEditor()
    await flushPromises()
    const panel = await openLineage(wrapper)
    const events = editors[0].config.events

    events.onDocumentStateChange({ data: true }) // 载入完成前（字段更新等）不算
    await flushPromises()
    expect(panel.props('editorHasUnsavedEdits')).toBe(false)

    events.onDocumentReady()
    events.onDocumentStateChange({ data: false })
    await flushPromises()
    expect(panel.props('editorHasUnsavedEdits')).toBe(false)
    events.onDocumentStateChange({ data: true })
    await flushPromises()
    expect(panel.props('editorHasUnsavedEdits')).toBe(true)

    panel.vm.$emit('refreshed', 15)
    await flushPromises()
    expect(panel.props('editorHasUnsavedEdits')).toBe(false)
  })
})
