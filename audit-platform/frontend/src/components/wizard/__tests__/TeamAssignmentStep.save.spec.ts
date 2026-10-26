/**
 * 团队分配「关闭即保存」（spec procedure-trim-generation-delegation-chain 任务 22 浏览器实测发现）：
 * 项目详情面板「人员委派」弹窗原先关闭只是隐藏，勾选的角色 / 循环从未落库 —— 审计员看得到哪些循环全靠这里。
 *
 * `save()`：有改动才提交（保存会重写全部分配并逐人发委派通知）；成员列表没加载成功不提交（免得空列表覆盖
 * 已有分配）；向导 store 里别的项目的团队不带进来；提交失败返回 false（弹窗不关）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, shallowMount } from '@vue/test-utils'

const mocks = vi.hoisted(() => ({
  listAssignments: vi.fn(),
  saveAssignments: vi.fn(),
  wizard: { projectId: '' as string, stepData: {} as any, saveStep: vi.fn() },
  success: vi.fn(),
  warning: vi.fn(),
  apiError: vi.fn(),
}))
vi.mock('@/services/staffApi', () => ({
  listStaff: vi.fn().mockResolvedValue({ items: [], total: 0 }),
  createStaff: vi.fn(),
  listAssignments: mocks.listAssignments,
  saveAssignments: mocks.saveAssignments,
}))
vi.mock('@/stores/wizard', () => ({ useWizardStore: () => mocks.wizard }))
vi.mock('@/services/apiProxy', () => ({ api: { get: vi.fn().mockResolvedValue([]) } }))
vi.mock('@/utils/errorHandler', () => ({ handleApiError: mocks.apiError }))
vi.mock('element-plus', () => ({
  ElMessage: { success: mocks.success, warning: mocks.warning, error: vi.fn(), info: vi.fn() },
  ElMessageBox: { confirm: vi.fn() },
}))

import TeamAssignmentStep from '../TeamAssignmentStep.vue'

const AUDITOR = { staff_id: 's1', staff_name: '甲', role: 'auditor', assigned_cycles: ['D'] }

async function mountStep(projectId = 'p1') {
  localStorage.setItem('gt_team_guide_dismissed', '1')
  // 表格列的作用域插槽不渲染（自动桩会不带 row 去调插槽）
  const w = shallowMount(TeamAssignmentStep, {
    props: { projectId },
    global: { stubs: { 'el-table-column': { template: '<i />' }, ElTableColumn: { template: '<i />' } } },
  })
  await flushPromises()
  return w.vm as any
}

beforeEach(() => {
  vi.clearAllMocks()
  mocks.wizard.projectId = ''
  mocks.wizard.stepData = {}
  mocks.saveAssignments.mockResolvedValue({ count: 1 })
})

describe('TeamAssignmentStep.save', () => {
  it('勾选改了 ⇒ 提交本项目的团队分配；再关一次没改动 ⇒ 不再提交', async () => {
    mocks.listAssignments.mockResolvedValue([])
    const vm = await mountStep()
    vm.members.push({ ...AUDITOR, staff_title: '', employee_no: '' })
    expect(await vm.save()).toBe(true)
    expect(mocks.saveAssignments).toHaveBeenCalledWith('p1', [{ staff_id: 's1', role: 'auditor', assigned_cycles: ['D'] }])
    expect(mocks.wizard.saveStep, '面板里只存团队分配，不写向导状态').not.toHaveBeenCalled()
    expect(await vm.save()).toBe(true)
    expect(mocks.saveAssignments).toHaveBeenCalledTimes(1)
  })

  it('打开就关、循环只是换了顺序 ⇒ 不提交（免得重写分配、逐人重发通知）', async () => {
    mocks.listAssignments.mockResolvedValue([{ ...AUDITOR, assigned_cycles: ['E', 'D'] }])
    const vm = await mountStep()
    expect(await vm.save()).toBe(true)
    vm.members[0].assigned_cycles = ['D', 'E']
    expect(await vm.save()).toBe(true)
    expect(mocks.saveAssignments).not.toHaveBeenCalled()
  })

  it('成员列表没加载成功 ⇒ 不提交、提示，弹窗照常关', async () => {
    mocks.listAssignments.mockRejectedValue(new Error('网络错误'))
    const vm = await mountStep()
    vm.members.push({ ...AUDITOR, staff_title: '', employee_no: '' })
    expect(await vm.save()).toBe(true)
    expect(mocks.saveAssignments).not.toHaveBeenCalled()
    expect(mocks.warning).toHaveBeenCalledWith('成员列表未加载成功，本次未保存团队分配')
  })

  it('向导 store 里是别的项目的团队 ⇒ 不带进本项目', async () => {
    mocks.listAssignments.mockResolvedValue([])
    mocks.wizard.projectId = 'other-project'
    mocks.wizard.stepData = { team_assignment: { members: [AUDITOR] } }
    const vm = await mountStep()
    expect(vm.members).toEqual([])
    expect(await vm.save()).toBe(true)
    expect(mocks.saveAssignments).not.toHaveBeenCalled()
  })

  it('没有项目 id ⇒ 不提交、也不提示「未加载成功」', async () => {
    const vm = await mountStep('')
    vm.members.push({ ...AUDITOR, staff_title: '', employee_no: '' })
    expect(await vm.save()).toBe(true)
    expect(mocks.saveAssignments).not.toHaveBeenCalled()
    expect(mocks.warning).not.toHaveBeenCalled()
  })

  it('提交失败 ⇒ 返回 false（弹窗不关）并提示原因', async () => {
    mocks.listAssignments.mockResolvedValue([])
    mocks.saveAssignments.mockRejectedValue({ response: { status: 409 } })
    const vm = await mountStep()
    vm.members.push({ ...AUDITOR, staff_title: '', employee_no: '' })
    expect(await vm.save()).toBe(false)
    expect(mocks.apiError).toHaveBeenCalled()
    expect(mocks.success).not.toHaveBeenCalled()
  })
})
