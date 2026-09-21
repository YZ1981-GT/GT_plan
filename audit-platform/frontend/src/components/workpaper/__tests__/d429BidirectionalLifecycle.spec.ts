import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, ref } from 'vue'
import { flushPromises, shallowMount } from '@vue/test-utils'
import D4TabCustomerDetail from '../d4/ipo/D4TabCustomerDetail.vue'

const mocks = vi.hoisted(() => ({ save: vi.fn(), read: vi.fn(), reload: vi.fn(), bridge: null as any }))
// 🔴 useD4SyncMode 在 mount 期会经 fetchOnlyOfficeHealthy() 探健康（读 data.healthy），
//    switchMode('在线编辑') 靠这个健康门禁放行；必须返回 healthy:true 否则 oo 分支永远短路。
vi.mock('@/utils/http', () => ({ default: { get: vi.fn(async () => ({ data: { healthy: true } })) } }))
vi.mock('../sync/workpaperSyncApi', () => ({ readStoreProjection: mocks.read }))
vi.mock('../sync/workpaperSyncCapability', () => ({ capabilityForEntry: () => 'bidirectional' }))
vi.mock('../composables/useD4ImportExport', () => ({ useD4ImportExport: () => ({ exportTemplate: vi.fn(), exportData: vi.fn(), importData: vi.fn(), importing: ref(false) }) }))
vi.mock('../d4/ipo/D4IpoFindingWriteback.vue', () => ({ default: defineComponent({ name: 'D4IpoFindingWriteback', render: () => h('span') }) }))
vi.mock('../GtIndexChip.vue', () => ({ default: defineComponent({ name: 'GtIndexChip', render: () => h('span') }) }))
vi.mock('../sync/WorkpaperSyncEditorHost.vue', () => ({ default: defineComponent({ name: 'WorkpaperSyncEditorHost', props: ['descriptor', 'bridge'], render: () => h('div') }) }))
// 🔴 2026-09-21 治本改造后：D4TabCustomerDetail 不再直连 useWorkpaperSyncBridge，而是经
//    共享 composable useD4SyncMode（../d4/composables/useD4SyncMode.ts）内部调用它。该
//    composable 还引用了本模块的 WP_BRIDGE_IN_FLIGHT_STATES（busy 判定），mock 必须一并
//    导出，否则 "No export is defined on mock" 报错（该常量并非本测试断言点，只需给出
//    与真实模块同构的只读数组，取用真实模块的部分状态即可，勿返回空数组—— busy 语义仍要成立）。
vi.mock('../sync/useWorkpaperSyncBridge', () => ({
  WP_BRIDGE_IN_FLIGHT_STATES: ['flushing', 'materializing', 'oo_loading'],
  useWorkpaperSyncBridge: (options: any) => {
    const bridge = {
      state: ref('html_idle'), mode: ref('html'), descriptor: ref<any>(null), lastError: ref(null),
      dirty: ref(false), feedback: ref({ message: '' }),
      switchToOnlyOffice: vi.fn(async () => {
        // 真实桥：flushHtml 抛错时先写 lastError（sticky，供 role=alert 展示）再重新
        // throw（不吞异常），见 useWorkpaperSyncBridge.ts fail()/switchToOnlyOffice。
        try {
          await options.flushHtml()
        } catch (e: any) {
          bridge.lastError.value = { message: e?.message ?? String(e) }
          throw e
        }
        bridge.descriptor.value = { documentKey: 'test-document' }
        bridge.mode.value = 'oo'
        bridge.state.value = 'oo_editing'
      }),
      switchToHtml: vi.fn(async () => {
        try {
          await options.reloadHtml(7)
        } catch (e: any) {
          bridge.lastError.value = { message: e?.message ?? String(e) }
          throw e
        }
        bridge.mode.value = 'html'
        bridge.state.value = 'html_idle'
      }),
    }
    mocks.bridge = bridge
    return bridge
  },
}))
// 🔴 2026-09-21 治本改造后：useD4SyncMode.modeOptions 是对象数组
//    `{ label, value, disabled }`（不再是纯字符串数组），el-segmented 真实组件按
//    option.value 取值、option.disabled 判每项禁用。stub 必须同构，否则 emit 出去的是
//    整个 option 对象（字符串比较永远 false）、disabled 永远读不到 per-option 值。
const Segmented = defineComponent({
  props: ['modelValue', 'options', 'disabled'], emits: ['update:modelValue'],
  setup(props, { emit }) {
    return () => h('nav', props.options.map((opt: any) => {
      const value = typeof opt === 'string' ? opt : opt.value
      const label = typeof opt === 'string' ? opt : opt.label
      const optDisabled = typeof opt === 'string' ? props.disabled : (opt.disabled || props.disabled)
      return h('button', { disabled: optDisabled, onClick: () => emit('update:modelValue', value) }, label)
    }))
  },
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
