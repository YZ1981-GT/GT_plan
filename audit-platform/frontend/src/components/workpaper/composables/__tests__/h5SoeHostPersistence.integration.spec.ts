/** H5 国企补充披露：真实宿主 adapter → 共享 Map → checklist 保存。 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { nextTick, ref } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'

const h = vi.hoisted(() => ({ apiGet: vi.fn(), apiPut: vi.fn(), httpGet: vi.fn(), httpPost: vi.fn(), httpPut: vi.fn() }))
vi.mock('@/services/apiProxy', () => {
  const api = { get: h.apiGet, put: h.apiPut }
  return { api, apiProxy: api, default: api }
})
vi.mock('@/utils/http', () => ({ default: { get: h.httpGet, post: h.httpPost, put: h.httpPut } }))
vi.mock('@/composables/useAuditContext', () => ({ useAuditContext: () => ({ year: ref(2025) }) }))
vi.mock('../useHSyncMode', async () => {
  const vue = await vi.importActual<typeof import('vue')>('vue')
  return {
    useHSyncMode: () => ({
      syncHostRef: vue.ref(null), isManagedSheet: vue.ref(false), modeOptions: vue.ref([]),
      renderMode: vue.ref('html'), descriptor: vue.ref(null), syncBridge: {}, sheetKey: vue.ref(''),
      syncStateTag: vue.ref({ type: 'info', text: '结构化视图' }), switchMode: vi.fn(),
    }),
  }
})
vi.mock('../sync/workpaperSyncApi', () => ({ readStoreProjection: vi.fn() }))
vi.mock('../sync/hPendingWrites', () => ({ flushHPendingWrites: vi.fn(async () => undefined), registerHPendingFlusher: vi.fn(() => undefined), trackHPendingWrite: (p: Promise<unknown>) => p }))
vi.mock('vue-router', async () => ({
  ...(await vi.importActual<Record<string, unknown>>('vue-router')),
  useRouter: () => ({ push: vi.fn(async () => undefined) }),
}))

import GtH5OilGasAssets from '../../GtH5OilGasAssets.vue'
import H5TabDisclosureSoe from '../../h5/core/H5TabDisclosureSoe.vue'
import WpNoteTextArea from '../../shared/disclosure/WpNoteTextArea.vue'
import { H5_SOE_TEXT_ITEM } from '../h5SoeDisclosureForm'

const STUBS = {
  'el-skeleton': true,
  'el-empty': true,
  'el-segmented': true,
  'el-alert': true,
  'el-card': { template: '<section><header><slot name="header" /></header><slot /></section>' },
  'el-button': {
    props: ['disabled', 'loading'], emits: ['click'],
    template: '<button :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
  },
  'el-table': { template: '<table><slot /></table>' },
  'el-table-column': true,
  'el-input': {
    props: ['modelValue', 'disabled'], emits: ['update:modelValue', 'change'],
    template: '<textarea :disabled="disabled" :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" @change="$emit(\'change\')" />',
  },
  GtOnlyOfficeSheet: true,
  GtEntrySyncCapabilityNotice: true,
  WorkpaperSyncEditorHost: true,
  HiFourTableSourcePanel: true,
  WpDisclosureConsistencyPanel: true,
}

function htmlData(text = '原补充披露') {
  return {
    responses_snapshot: {
      'H5-1-cost-rows': { conclusion: null, remark: JSON.stringify([{ name: '探明矿区权益', audited: 1000 }]) },
      'H5-1-depletion-rows': { conclusion: null, remark: JSON.stringify([{ name: '探明矿区权益', audited: 100 }]) },
      [H5_SOE_TEXT_ITEM]: { conclusion: null, remark: text },
    },
  }
}

async function mountHost(readonly = false): Promise<VueWrapper> {
  const wrapper = mount(GtH5OilGasAssets, {
    props: {
      wpId: 'wp-h5', projectId: 'p1', sheetName: '附注披露信息（国有企业）',
      htmlData: htmlData(), readonly,
    },
    global: { stubs: STUBS },
  })
  await flushPromises()
  await nextTick()
  await flushPromises()
  expect(wrapper.findComponent(H5TabDisclosureSoe).exists(), 'H5 国企披露 Tab 未挂载').toBe(true)
  return wrapper
}

function currentTab(wrapper: VueWrapper) {
  return wrapper.findComponent(H5TabDisclosureSoe)
}

function currentNote(wrapper: VueWrapper) {
  return currentTab(wrapper).findComponent(WpNoteTextArea)
}

describe('GtH5OilGasAssets → H5TabDisclosureSoe 保存链', () => {
  beforeEach(() => {
    for (const fn of Object.values(h)) fn.mockReset()
    h.apiPut.mockResolvedValue([])
    h.httpPost.mockImplementation(async (url: string) => {
      if (url.endsWith('/review-dialog/ai-generate')) return { data: { generated_text: 'AI 回填的补充披露' } }
      return { data: { rows_synced: 4 } }
    })
  })

  afterEach(() => {
    vi.clearAllTimers()
    vi.useRealTimers()
  })

  it('编辑先更新宿主 Map 并走既有 checklist PUT，切走再切回仍读到该值', async () => {
    const wrapper = await mountHost()
    expect(currentNote(wrapper).props('modelValue')).toBe('原补充披露')

    currentNote(wrapper).vm.$emit('update:modelValue', '编辑后的补充披露')
    await nextTick()
    currentNote(wrapper).vm.$emit('change')
    await flushPromises()

    expect(h.apiPut).toHaveBeenCalledWith('/api/workpapers/wp-h5/checklist-responses', {
      project_id: 'p1',
      items: [{ item_id: H5_SOE_TEXT_ITEM, conclusion: null, remark: '编辑后的补充披露' }],
    })
    expect(currentTab(wrapper).props('allResponses').get(H5_SOE_TEXT_ITEM)?.remark).toBe('编辑后的补充披露')

    await wrapper.setProps({ sheetName: '未匹配的表' })
    await flushPromises()
    expect(wrapper.findComponent(H5TabDisclosureSoe).exists()).toBe(false)
    await wrapper.setProps({ sheetName: '附注披露信息（国有企业）' })
    await flushPromises()
    await nextTick()
    expect(currentNote(wrapper).props('modelValue')).toBe('编辑后的补充披露')
    wrapper.unmount()
  })

  it('AI 回填复用同一宿主 adapter，保存原始文字而不是 remark 包装对象', async () => {
    const wrapper = await mountHost()
    h.apiPut.mockClear()
    currentNote(wrapper).vm.$emit('ai')
    await flushPromises()
    await nextTick()

    expect(h.httpPost).toHaveBeenCalledWith('/api/workpapers/wp-h5/review-dialog/ai-generate', expect.any(Object))
    expect(h.apiPut).toHaveBeenCalledWith('/api/workpapers/wp-h5/checklist-responses', {
      project_id: 'p1',
      items: [{ item_id: H5_SOE_TEXT_ITEM, conclusion: null, remark: 'AI 回填的补充披露' }],
    })
    expect(currentNote(wrapper).props('modelValue')).toBe('AI 回填的补充披露')
    expect(currentTab(wrapper).props('allResponses').get(H5_SOE_TEXT_ITEM)?.remark).toBe('AI 回填的补充披露')
    wrapper.unmount()
  })

  it('只读时编辑、AI、手工同步及直接调用宿主 adapter 都不写', async () => {
    const wrapper = await mountHost(true)
    const tab = currentTab(wrapper)
    const note = currentNote(wrapper)
    const before = tab.props('allResponses').get(H5_SOE_TEXT_ITEM)?.remark

    note.vm.$emit('update:modelValue', '只读态强制改值')
    await nextTick()
    note.vm.$emit('change')
    note.vm.$emit('ai')
    await (tab.vm as any).syncToNote()
    await (tab.props('saveResponse') as (id: string, value: unknown) => Promise<void>)(H5_SOE_TEXT_ITEM, '绕过子组件')
    await flushPromises()

    expect(h.apiPut).not.toHaveBeenCalled()
    expect(h.httpPost).not.toHaveBeenCalled()
    expect(tab.props('allResponses').get(H5_SOE_TEXT_ITEM)?.remark).toBe(before)
    const sync = tab.findAll('button').find((button) => button.text().includes('同步到附注'))
    expect(sync?.attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })

  it('生产宿主显式传必填 adapter，Tab 不再默认注入 no-op', () => {
    const root = resolve(__dirname, '../..')
    const host = readFileSync(resolve(root, 'GtH5OilGasAssets.vue'), 'utf-8')
    const tab = readFileSync(resolve(root, 'h5/core/H5TabDisclosureSoe.vue'), 'utf-8')
    expect(host).toContain(':save-response="persistResponse"')
    expect(host).toMatch(/useH5FormData\(\{[\s\S]*?allResponses/)
    expect(tab).toContain('saveResponse: (itemId: string, value: any)')
    expect(tab).not.toMatch(/inject[^\n]*saveResponse/)
    expect(tab).not.toContain("inject<(id: string, val: any) => void>('saveResponse', () => {})")
  })
})
