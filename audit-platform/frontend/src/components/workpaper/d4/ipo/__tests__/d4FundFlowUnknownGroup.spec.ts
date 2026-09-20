/**
 * D4-32 资金流水（D4TabFundFlow）——未知组保真 + 错误保留组件级判据。
 *
 * spec: d4-ipo-fraud-writeback-formula-io · Task 9（Requirements 5.2, 5.3）
 *
 * 覆盖：
 *  - R5.2：导入未知组别时，原始 label / 稳定 row id / 金额三态 / 账号中文 保留，
 *          落 __unknown__ 组待人工映射（不被猜测归并到六组任一）。
 *  - R5.3：JSON 非法 → 旧数据不清空 + 可见错误；保存失败 → 旧数据保留 + 可见错误。
 *
 * 组件走平台同步桥，这里 mock 桥/API/保存宿主，聚焦组件自身的
 * loadData 保真 + 错误呈现逻辑（非真 OO 往返，那属 Task 7/8 真栈范围）。
 */
import { describe, expect, it, vi } from 'vitest'
import { defineComponent, nextTick, ref } from 'vue'
import { mount } from '@vue/test-utils'

// ── 受控 saveError：由 useD4InterviewSave mock 暴露，测试可写以模拟保存失败 ──
const saveErrorRef = ref('')
const flushMock = vi.fn().mockResolvedValue(undefined)
const scheduleMock = vi.fn()

const elMessageErrorMock = vi.fn()
vi.mock('element-plus', () => ({
  ElMessage: { error: (...a: unknown[]) => elMessageErrorMock(...a), warning: vi.fn(), success: vi.fn() },
  ElMessageBox: { prompt: vi.fn(), confirm: vi.fn() },
}))
vi.mock('@/utils/http', () => ({
  default: { get: vi.fn().mockResolvedValue({ data: { status: 'healthy' } }), post: vi.fn() },
}))
vi.mock('../../composables/useD4ImportExport', () => ({
  useD4ImportExport: () => ({ exportTemplate: vi.fn(), exportData: vi.fn(), importData: vi.fn(), importing: false }),
}))
vi.mock('../useD4InterviewSync', () => ({
  useD4InterviewSave: () => ({ flush: flushMock, schedule: scheduleMock, saveError: saveErrorRef }),
  useD4InterviewMode: () => ({
    editorMode: ref('表格视图'),
    modeOptions: ref([{ label: '表格视图', value: '表格视图', disabled: false }]),
    busy: ref(false),
    feedback: ref(''),
  }),
}))
vi.mock('../../sync/useWorkpaperSyncBridge', () => ({
  WP_BRIDGE_IN_FLIGHT_STATES: [],
  useWorkpaperSyncBridge: () => ({ descriptor: ref(null), state: ref('html_idle'), mode: ref('html'), feedback: ref({ message: '' }) }),
}))
vi.mock('../../sync/workpaperSyncApi', () => ({ readStoreProjection: vi.fn() }))
vi.mock('../../sync/workpaperSyncCapability', () => ({ capabilityForEntry: () => ({}) }))

import D4TabFundFlow from '../D4TabFundFlow.vue'

const FindingStub = defineComponent({ props: ['findings'], template: '<span />' })
const stubs = {
  D4IpoFindingWriteback: FindingStub,
  WorkpaperSyncEditorHost: { template: '<div />' },
  GtIndexChip: { template: '<span />' },
  WpAmountInput: { props: ['modelValue'], template: '<input />' },
  Plus: { template: '<span />' },
  'el-alert': { props: ['title', 'type'], template: '<div class="stub-alert" :data-type="type"><span class="alert-title">{{ title }}</span><slot /></div>' },
  'el-button': { template: '<button><slot /></button>' },
  'el-segmented': { props: ['modelValue'], template: '<span />' },
  'el-dropdown': { template: '<div><slot /><slot name="dropdown" /></div>' },
  'el-dropdown-menu': { template: '<div><slot /></div>' },
  'el-dropdown-item': { template: '<div><slot /></div>' },
  'el-upload': { template: '<div><slot /></div>' },
  'el-input': { props: ['modelValue'], template: '<input />' },
  'el-select': { props: ['modelValue'], template: '<select><slot /></select>' },
  'el-option': { template: '<option><slot /></option>' },
  'el-table': { props: ['data'], template: '<div class="stub-table"><slot /></div>' },
  'el-table-column': { template: '<div />' },
  'el-card': { template: '<div><slot name="header" /><slot /></div>' },
  'el-icon': { template: '<span><slot /></span>' },
  'el-tooltip': { template: '<span><slot /></span>' },
  'el-popconfirm': { template: '<span><slot name="reference" /></span>' },
}

function mountFundFlow(remark: string, isReadonly = false) {
  const allResponses = new Map<string, any>([['D4-32-groups', { item_id: 'D4-32-groups', remark }]])
  const wrapper = mount(D4TabFundFlow, { props: { wpId: 'wp', projectId: 'p', allResponses, isReadonly }, global: { stubs } })
  return { wrapper, allResponses }
}

function groupsOf(wrapper: ReturnType<typeof mount>): any[] {
  return (wrapper.vm as any).groups
}

describe('D4-32 未知组保真（R5.2）', () => {
  it('未知组别原始 label / 稳定 id / 金额三态 / 账号中文 保留，落 __unknown__ 待映射', async () => {
    const remark = JSON.stringify([
      { key: 'supplier', rows: [] },
      { key: 'customer', rows: [] },
      { key: 'shareholder', rows: [] },
      { key: 'controller', rows: [] },
      { key: 'management', rows: [] },
      { key: 'related', rows: [] },
      {
        key: '__unknown__',
        rows: [
          { id: 'ff-known-0001', name: '神秘往来方', amount: 0, ratio: '', bank: '中国工商银行', account: '6222钱塘壹号', method: '银行流水', hasAnomaly: '是', indexRef: '', groupLabel: '潜在关联方' },
          { id: 'ff-known-0002', name: '空额对象', amount: '', ratio: '', bank: '', account: '农行62凯旋', method: '', hasAnomaly: '', indexRef: '', groupLabel: '潜在关联方' },
        ],
      },
    ])
    const { wrapper } = mountFundFlow(remark)
    await nextTick()
    const groups = groupsOf(wrapper)

    // 六组任一都不得被猜测塞入未知行
    for (const gkey of ['supplier', 'customer', 'shareholder', 'controller', 'management', 'related']) {
      const g = groups.find((x) => x.key === gkey)
      expect(g.rows).toEqual([])
    }
    // 未知组独立保留
    const unknown = groups.find((x) => x.key === '__unknown__')
    expect(unknown).toBeTruthy()
    expect(unknown.rows).toHaveLength(2)
    // 原始 label 保留（供人工映射显示「待映射：潜在关联方」）
    expect(unknown.label).toBe('潜在关联方')
    // 稳定 row id 保留
    expect(unknown.rows[0].id).toBe('ff-known-0001')
    expect(unknown.rows[1].id).toBe('ff-known-0002')
    // 金额三态：显式 0 与 空-未知 逐态保留（不静默互相变换）
    expect(unknown.rows[0].amount).toBe(0)
    expect(unknown.rows[1].amount).toBe('')
    // 账号中文原样保留
    expect(unknown.rows[0].account).toBe('6222钱塘壹号')
    expect(unknown.rows[1].account).toBe('农行62凯旋')
    wrapper.unmount()
  })
})

describe('D4-32 错误保留（R5.3）', () => {
  it('JSON 非法：旧数据不被清空 + 可见错误', async () => {
    // 先用合法数据挂载，产生「旧数据」
    const good = JSON.stringify([{ key: 'supplier', rows: [{ id: 'ff-x', name: '老王', amount: 100, ratio: '', bank: '', account: '', method: '', hasAnomaly: '否', indexRef: '' }] }])
    const { wrapper, allResponses } = mountFundFlow(good)
    await nextTick()
    expect(groupsOf(wrapper).find((g) => g.key === 'supplier').rows).toHaveLength(1)

    // 注入非法 JSON：换新对象引用使 watch(source=remark) 触发 loadData 非法分支
    const bad = new Map(allResponses)
    bad.set('D4-32-groups', { item_id: 'D4-32-groups', remark: '{不是合法 json' })
    await wrapper.setProps({ allResponses: bad })
    await nextTick()

    // 旧数据未被清空（loadData 非法分支 return，不覆盖 groups）
    const supplier = groupsOf(wrapper).find((g) => g.key === 'supplier')
    expect(supplier.rows).toHaveLength(1)
    expect(supplier.rows[0].name).toBe('老王')
    // 可见错误提示（ElMessage.error）
    expect(elMessageErrorMock).toHaveBeenCalled()
    expect(String(elMessageErrorMock.mock.calls[0][0])).toContain('保留原数据')
    wrapper.unmount()
  })

  it('保存失败：saveError 非空时页面显示可见错误提示（旧数据保留）', async () => {
    saveErrorRef.value = ''
    const good = JSON.stringify([{ key: 'supplier', rows: [{ id: 'ff-y', name: '张三', amount: 50, ratio: '', bank: '', account: '', method: '', hasAnomaly: '否', indexRef: '' }] }])
    const { wrapper } = mountFundFlow(good)
    await nextTick()
    // 初始无错误 alert
    expect(wrapper.find('.stub-alert').exists()).toBe(false)

    // 模拟保存失败：saveError 被 useD4InterviewSave 置为错误信息
    saveErrorRef.value = '桥接保存失败：网络中断'
    await nextTick()

    const alert = wrapper.find('.stub-alert')
    expect(alert.exists()).toBe(true)
    expect(alert.attributes('data-type')).toBe('error')
    expect(alert.text()).toContain('桥接保存失败：网络中断')

    // 旧数据仍在（保存失败不清空本地 store）
    expect(groupsOf(wrapper).find((g) => g.key === 'supplier').rows).toHaveLength(1)

    saveErrorRef.value = ''
    wrapper.unmount()
  })
})
