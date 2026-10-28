/**
 * 项目详情面板「人员委派」弹窗关闭即保存（spec procedure-trim-generation-delegation-chain 任务 22 浏览器实测发现）：
 * 原先关闭只是隐藏，勾选的角色 / 循环从未落库。底部「关闭」与右上角 × / ESC（before-close）都先调
 * TeamAssignmentStep.save()；保存失败（返回 false）弹窗不关；保存中再点关闭不重复提交。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, shallowMount, type VueWrapper } from '@vue/test-utils'
import { defineComponent, h } from 'vue'

const mocks = vi.hoisted(() => ({ save: vi.fn() }))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn(), resolve: vi.fn(() => ({ href: '' })) }),
  useRoute: () => ({ params: {}, query: {} }),
}))
vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
  ElNotification: vi.fn(),
  ElMessageBox: { confirm: vi.fn() },
}))
vi.mock('@/utils/confirm', () => ({ confirmForceReset: vi.fn(), confirmDangerous: vi.fn() }))
vi.mock('@/services/apiProxy', () => ({ api: { get: vi.fn().mockResolvedValue(null), post: vi.fn() } }))
vi.mock('@/utils/errorHandler', () => ({ handleApiError: vi.fn() }))
vi.mock('@/composables/useNavigationStack', () => ({ useNavigationStack: () => ({ push: vi.fn() }) }))
vi.mock('@/stores/displayPrefs', () => ({ useDisplayPrefsStore: () => ({ fmt: (v: number) => String(v) }) }))
vi.mock('@/utils/openLedgerWindow', () => ({ openLedgerWindow: vi.fn() }))
vi.mock('@/components/layout/PlatformUserGuideDialog.vue', () => ({ default: { name: 'PlatformUserGuideDialog', render: () => null } }))
vi.mock('@/components/wizard/TeamAssignmentStep.vue', () => ({ default: { name: 'TeamAssignmentStep', render: () => null } }))

import DetailProjectPanel from '../DetailProjectPanel.vue'

/** 团队分配步骤桩：只暴露 save（面板通过 ref 调它） */
const TeamStub = defineComponent({
  name: 'TeamAssignmentStep',
  props: { projectId: String },
  setup(_props, { expose }) {
    expose({ save: mocks.save })
    return () => h('i')
  },
})
/** 弹窗桩：打开时渲染正文与底部插槽，before-close 留在 props 上供测试直接调用 */
const DialogStub = defineComponent({
  name: 'ElDialog',
  props: { modelValue: Boolean, beforeClose: Function, title: String },
  setup(props, { slots }) {
    return () => (props.modelValue ? h('section', [slots.default?.(), slots.footer?.()]) : null)
  },
})
const ButtonStub = defineComponent({
  name: 'ElButton',
  emits: ['click'],
  setup(_props, { slots, emit }) {
    return () => h('button', { onClick: () => emit('click') }, slots.default?.())
  },
})

let wrapper: VueWrapper<any> | null = null

async function openTeamDialog() {
  wrapper = shallowMount(DetailProjectPanel, {
    props: { project: { id: 'p1', name: '【测试】甲', audit_year: 2025 } },
    global: {
      stubs: {
        TeamAssignmentStep: TeamStub,
        'el-dialog': DialogStub, ElDialog: DialogStub,
        'el-button': ButtonStub, ElButton: ButtonStub,
      },
    },
  })
  await flushPromises()
  wrapper.vm.showTeamAssign = true
  await flushPromises()
  const dialog = wrapper.findAllComponents(DialogStub).find(d => d.props('title') === '人员委派')
  expect(dialog, '人员委派弹窗已打开').toBeTruthy()
  return dialog!
}

beforeEach(() => {
  vi.clearAllMocks()
  // 清掉上一例没用完的 mockResolvedValueOnce 队列（clearAllMocks 不清实现），免得一例失败连带下一例
  mocks.save.mockReset()
})
afterEach(() => {
  wrapper?.unmount()
  wrapper = null
})

describe('DetailProjectPanel 人员委派弹窗关闭即保存', () => {
  it('点底部「关闭」：先保存，保存成功才关', async () => {
    mocks.save.mockResolvedValue(true)
    const dialog = await openTeamDialog()
    await dialog.find('button').trigger('click')
    await flushPromises()
    expect(mocks.save).toHaveBeenCalledTimes(1)
    expect(wrapper!.vm.showTeamAssign).toBe(false)
  })

  it('保存失败 ⇒ 弹窗不关，留在里面改', async () => {
    mocks.save.mockResolvedValue(false)
    const dialog = await openTeamDialog()
    await dialog.find('button').trigger('click')
    await flushPromises()
    expect(mocks.save).toHaveBeenCalledTimes(1)
    expect(wrapper!.vm.showTeamAssign).toBe(true)
  })

  it('右上角 × / ESC（before-close）同样先保存：失败不调 done，成功才调', async () => {
    mocks.save.mockResolvedValueOnce(false).mockResolvedValueOnce(true)
    const dialog = await openTeamDialog()
    const beforeClose = dialog.props('beforeClose') as ((done: () => void) => Promise<void>) | undefined
    expect(typeof beforeClose, '弹窗挂了 before-close').toBe('function')
    const done = vi.fn()
    await beforeClose!(done)
    expect(done).not.toHaveBeenCalled()
    await beforeClose!(done)
    expect(done).toHaveBeenCalledTimes(1)
    expect(mocks.save).toHaveBeenCalledTimes(2)
  })

  it('保存中再点「关闭」⇒ 不重复提交', async () => {
    let resolveSave!: (ok: boolean) => void
    mocks.save.mockReturnValue(new Promise<boolean>((r) => { resolveSave = r }))
    const dialog = await openTeamDialog()
    const button = dialog.find('button')
    await button.trigger('click')
    await button.trigger('click')
    expect(mocks.save).toHaveBeenCalledTimes(1)
    resolveSave(true)
    await flushPromises()
    expect(wrapper!.vm.showTeamAssign).toBe(false)
  })
})
