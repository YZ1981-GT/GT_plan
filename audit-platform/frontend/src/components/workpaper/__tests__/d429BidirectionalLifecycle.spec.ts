import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, ref } from 'vue'
import { flushPromises, shallowMount } from '@vue/test-utils'
import D4TabCustomerDetail from '../d4/ipo/D4TabCustomerDetail.vue'

const mocks = vi.hoisted(() => ({ save: vi.fn(), read: vi.fn(), reload: vi.fn(), bridge: null as any }))
vi.mock('@/utils/http', () => ({ default: { get: vi.fn(async () => ({ data: { status: 'unavailable' } })) } }))
vi.mock('../sync/workpaperSyncApi', () => ({ readStoreProjection: mocks.read }))
vi.mock('../sync/workpaperSyncCapability', () => ({ capabilityForEntry: () => 'bidirectional' }))
vi.mock('../composables/useD4ImportExport', () => ({ useD4ImportExport: () => ({ exportTemplate: vi.fn(), exportData: vi.fn(), importData: vi.fn(), importing: ref(false) }) }))
vi.mock('../d4/ipo/D4IpoFindingWriteback.vue', () => ({ default: defineComponent({ name: 'D4IpoFindingWriteback', render: () => h('span') }) }))
vi.mock('../GtIndexChip.vue', () => ({ default: defineComponent({ name: 'GtIndexChip', render: () => h('span') }) }))
vi.mock('../sync/WorkpaperSyncEditorHost.vue', () => ({ default: defineComponent({ name: 'WorkpaperSyncEditorHost', props: ['descriptor', 'bridge'], render: () => h('div') }) }))
vi.mock('../sync/useWorkpaperSyncBridge', () => ({
  useWorkpaperSyncBridge: (options: any) => {
    const bridge = {
      state: ref('html_idle'), mode: ref('html'), descriptor: ref<any>(null), lastError: ref(null),
      switchToOnlyOffice: vi.fn(async () => {
        await options.flushHtml()
        bridge.descriptor.value = { documentKey: 'test-document' }
        bridge.mode.value = 'oo'
        bridge.state.value = 'oo_editing'
      }),
      switchToHtml: vi.fn(async () => {
        await options.reloadHtml(7)
        bridge.mode.value = 'html'
        bridge.state.value = 'html_idle'
      }),
    }
    mocks.bridge = bridge
    return bridge
  },
}))
const Segmented = defineComponent({
  props: ['modelValue', 'options', 'disabled'], emits: ['update:modelValue'],
  setup(props, { emit }) { return () => h('nav', props.options.map((label: string) => h('button', { disabled: props.disabled, onClick: () => emit('update:modelValue', label) }, label))) },
})
const Input = defineComponent({ props: ['modelValue'], render() { return h('textarea', { value: this.modelValue }) } })
const Card = defineComponent({ setup(_, { slots }) { return () => h('section', slots.default?.()) } })
const mounted: any[] = []
function responses(conclusion = '旧结论') {
  return new Map<string, any>([
    ['D4-29-customers', { item_id: 'D4-29-customers', remark: JSON.stringify([{ id: 'c1', name: '客户甲', fields: {} }]) }],
    ['D4-29-note', { item_id: 'D4-29-note', remark: '说明' }],
    ['D4-29-conclusion', { item_id: 'D4-29-conclusion', remark: conclusion }],
  ])
}
function mountDetail() {
  const wrapper = shallowMount(D4TabCustomerDetail, {
    props: { wpId: 'w', projectId: 'p', allResponses: responses(), isReadonly: false },
    global: {
      provide: { d4SaveItems: mocks.save, reloadWorkpaperData: mocks.reload },
      stubs: { 'el-segmented': Segmented, 'el-input': Input, 'el-card': Card, 'el-table': true, 'el-table-column': true, 'el-button': true, 'el-dropdown': true, 'el-dropdown-menu': true, 'el-dropdown-item': true, 'el-upload': true, 'el-tabs': true, 'el-tab-pane': true, 'el-select': true, 'el-option': true, 'el-icon': true, 'el-empty': true, 'el-tooltip': true },
    },
  })
  mounted.push(wrapper)
  return wrapper
}
async function choose(wrapper: any, index: number) { await wrapper.findAll('nav button')[index].trigger('click'); await flushPromises() }
describe('D4-29 bidirectional lifecycle', () => {
  beforeEach(() => {
    mocks.save.mockReset().mockResolvedValue(undefined)
    mocks.read.mockReset().mockResolvedValue({ expectedRevision: 7, projection: {} })
    mocks.reload.mockReset().mockResolvedValue(undefined)
  })
  afterEach(() => { mounted.splice(0).forEach(w => w.unmount()) })
  it('waits for durable save before projection and renders the editor', async () => {
    let resolve!: () => void
    mocks.save.mockImplementationOnce(() => new Promise<void>(r => { resolve = r }))
    const w = mountDetail()
    await choose(w, 2)
    expect(mocks.save).toHaveBeenCalledTimes(1)
    expect(mocks.read).not.toHaveBeenCalled()
    expect(w.findComponent({ name: 'WorkpaperSyncEditorHost' }).exists()).toBe(false)
    resolve(); await flushPromises()
    expect(mocks.read).toHaveBeenCalledTimes(1)
    expect(w.findComponent({ name: 'WorkpaperSyncEditorHost' }).exists()).toBe(true)
    expect(w.find('.card-content').exists()).toBe(false)
  })
  it('keeps HTML and exposes save failure without reading projection', async () => {
    mocks.save.mockRejectedValueOnce(new Error('保存失败测试'))
    const w = mountDetail()
    await choose(w, 2)
    expect(mocks.read).not.toHaveBeenCalled()
    expect(w.get('[role="alert"]').text()).toContain('保存失败测试')
    expect(w.find('.card-content').exists()).toBe(true)
    await choose(w, 2)
    expect(mocks.read).toHaveBeenCalledTimes(1)
  })
  it('allows leaving oo_editing and reloads before showing matrix', async () => {
    const w = mountDetail()
    await choose(w, 2)
    expect(mocks.bridge.state.value).toBe('oo_editing')
    expect(w.findAll('nav button')[1].attributes('disabled')).toBeUndefined()
    await choose(w, 1)
    expect(mocks.reload).toHaveBeenCalledTimes(1)
    expect(w.find('.matrix-table').exists()).toBe(true)
    expect(w.findComponent({ name: 'WorkpaperSyncEditorHost' }).exists()).toBe(false)
  })
  it('retains editor when reverse reload fails', async () => {
    const w = mountDetail()
    await choose(w, 2)
    mocks.reload.mockRejectedValueOnce(new Error('回读失败测试'))
    await choose(w, 0)
    expect(w.findComponent({ name: 'WorkpaperSyncEditorHost' }).exists()).toBe(true)
    expect(w.get('[role="alert"]').text()).toContain('回读失败测试')
  })
  it('reloads conclusion independently of unchanged note', async () => {
    const w = mountDetail()
    expect(w.findAll('textarea').some((e: any) => e.element.value === '旧结论')).toBe(true)
    await w.setProps({ allResponses: responses('Excel新结论') })
    expect(w.findAll('textarea').some((e: any) => e.element.value === 'Excel新结论')).toBe(true)
  })
})
