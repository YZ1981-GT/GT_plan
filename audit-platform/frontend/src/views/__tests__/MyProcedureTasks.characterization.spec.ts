// Feature: procedure-delegation-notification — Task 12 前端网络 payload 回归测试
//
// 旧 bug（Task 1 characterization 基线）：MyProcedureTasks 修改 execution_status 时调用
// updateProcedureTrim，且 payload 不含 execution_status → 状态永不持久化。
//
// 重构后（本测试锁定的正确行为，需求 9.7 / 14.3）：
//   - 状态动作 **必须** 调用 transition API（transitionProcedureRowTask），
//     payload 携带 request_id + expected_lock_version（acknowledge 还带 expected_assignment_version）。
//   - **绝不** 再调用 updateProcedureTrim 提交状态。
//   - 列表数据来自 listMyProcedureRowTasks（V105 任务真源），不再走 getMyProcedureTasks 前端聚合。
import { computed, defineComponent, h, inject, provide, type ComputedRef } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  listMyProcedureRowTasks: vi.fn(),
  transitionProcedureRowTask: vi.fn(),
  listProjects: vi.fn(),
  updateProcedureTrim: vi.fn(),
  getMyProcedureTasks: vi.fn(),
  routerPush: vi.fn(),
  messageSuccess: vi.fn(),
  messageWarning: vi.fn(),
}))

vi.mock('@/services/commonApi', () => ({
  listMyProcedureRowTasks: mocks.listMyProcedureRowTasks,
  transitionProcedureRowTask: mocks.transitionProcedureRowTask,
  listProjects: mocks.listProjects,
  updateProcedureTrim: mocks.updateProcedureTrim,
  getMyProcedureTasks: mocks.getMyProcedureTasks,
}))

vi.mock('@/utils/errorHandler', () => ({ handleApiError: vi.fn() }))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: mocks.routerPush, back: vi.fn() }),
}))

vi.mock('element-plus', () => ({
  ElMessage: { success: mocks.messageSuccess, error: vi.fn(), warning: mocks.messageWarning },
  ElMessageBox: {
    prompt: vi.fn().mockResolvedValue({ value: '需要补充证据' }),
    confirm: vi.fn().mockResolvedValue(true),
  },
}))

vi.mock('@element-plus/icons-vue', () => ({ Refresh: {} }))

import MyProcedureTasks from '../MyProcedureTasks.vue'

const tableRowsKey = Symbol('tableRows')

const ElTableStub = defineComponent({
  props: { data: { type: Array, default: () => [] } },
  setup(props, { slots }) {
    provide(tableRowsKey, computed(() => props.data as any[]))
    return () => h('div', { class: 'el-table-stub' }, slots.default?.())
  },
})

const ElTableColumnStub = defineComponent({
  setup(_, { slots }) {
    const rows = inject<ComputedRef<any[]>>(tableRowsKey, computed(() => []))
    return () => h(
      'div', { class: 'el-table-column-stub' },
      slots.default
        ? rows.value.map((row, index) => h('div', { class: 'el-table-cell', key: index }, slots.default?.({ row })))
        : [],
    )
  },
})

const ElButtonStub = defineComponent({
  emits: ['click'],
  setup(_, { slots, emit }) {
    return () => h('button', { class: 'gt-btn', onClick: () => emit('click') }, slots.default?.())
  },
})

const stubs = {
  'el-table': ElTableStub,
  'el-table-column': ElTableColumnStub,
  'el-button': ElButtonStub,
  'el-tag': { template: '<span><slot /></span>' },
  'el-tooltip': { template: '<span><slot /></span>' },
  'el-radio-group': { template: '<div><slot /></div>' },
  'el-radio-button': { template: '<span><slot /></span>' },
  'el-select': { template: '<div><slot /></div>' },
  'el-option': { template: '<div />' },
  'el-checkbox': { template: '<label><slot /></label>' },
  'el-pagination': true,
  'el-dialog': { template: '<div><slot /><slot name="footer" /></div>' },
  'el-form': { template: '<form><slot /></form>' },
  'el-form-item': { template: '<div><slot /></div>' },
  'el-input': { template: '<input />' },
  'el-empty': { template: '<div><slot /></div>' },
  GtPageHeader: { template: '<div><slot name="subtitle" /></div>' },
  GtEmpty: { template: '<div class="gt-empty" />' },
}

function makePage(item: any) {
  return { items: [item], pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 } }
}

async function mountWith(task: any) {
  mocks.listProjects.mockResolvedValue([{ id: 'project-1', project_name: '示例项目' }])
  mocks.listMyProcedureRowTasks.mockResolvedValue(makePage(task))
  mocks.transitionProcedureRowTask.mockResolvedValue({ changed: true })
  const wrapper = mount(MyProcedureTasks, { global: { stubs } })
  await flushPromises()
  return wrapper
}

function clickButtonByText(wrapper: any, text: string) {
  const btn = wrapper.findAll('button.gt-btn').find((b: any) => b.text() === text)
  if (!btn) throw new Error(`button not found: ${text}`)
  return btn.trigger('click')
}

const BASE_TASK = {
  task_id: 'task-1', project_id: 'project-1', wp_index_id: 'wpi-1', wp_id: 'wp-1',
  definition_key: 'D2A::D2A::abc', sheet_key: 'D2A', wp_code: 'D2', sheet_name: 'D2 明细',
  program_no: '1', procedure_text: '核对明细账与总账', audit_cycle_snapshot: 'D',
  applicability_status: 'execute', workflow_status: 'assigned', assignee_staff_id: 's1',
  reviewer_staff_id: null, assignment_version: 3, lock_version: 5, due_at: null,
  overdue: false, materialization_required: false, my_role: 'assignee',
}

describe('MyProcedureTasks payload regression (Task 12)', () => {
  beforeEach(() => vi.clearAllMocks())

  it('loads tasks from listMyProcedureRowTasks (V105 truth source), not the legacy aggregate', async () => {
    await mountWith(BASE_TASK)
    expect(mocks.listMyProcedureRowTasks).toHaveBeenCalled()
    expect(mocks.getMyProcedureTasks).not.toHaveBeenCalled()
  })

  it('acknowledge action calls transition API with request_id + expected lock & assignment versions', async () => {
    const wrapper = await mountWith({ ...BASE_TASK, workflow_status: 'assigned', my_role: 'assignee' })
    await clickButtonByText(wrapper, '确认接收')
    await flushPromises()

    expect(mocks.updateProcedureTrim).not.toHaveBeenCalled()
    expect(mocks.transitionProcedureRowTask).toHaveBeenCalledTimes(1)
    const [pid, taskId, body] = mocks.transitionProcedureRowTask.mock.calls[0]
    expect(pid).toBe('project-1')
    expect(taskId).toBe('task-1')
    expect(body.action).toBe('acknowledge')
    expect(typeof body.request_id).toBe('string')
    expect(body.request_id.length).toBeGreaterThan(0)
    expect(body.expected_lock_version).toBe(5)
    expect(body.expected_assignment_version).toBe(3)
    // 旧 bug 回归：绝不携带 execution_status
    expect(body).not.toHaveProperty('execution_status')
  })

  it('start action carries expected_lock_version and never touches updateProcedureTrim', async () => {
    const wrapper = await mountWith({ ...BASE_TASK, workflow_status: 'acknowledged', my_role: 'assignee' })
    await clickButtonByText(wrapper, '开始执行')
    await flushPromises()

    expect(mocks.updateProcedureTrim).not.toHaveBeenCalled()
    const [, , body] = mocks.transitionProcedureRowTask.mock.calls[0]
    expect(body.action).toBe('start')
    expect(body.expected_lock_version).toBe(5)
    expect(typeof body.request_id).toBe('string')
  })

  it('reviewer submitted task exposes review/request_changes calling transition API', async () => {
    const wrapper = await mountWith({
      ...BASE_TASK, workflow_status: 'submitted', my_role: 'reviewer',
      assignee_staff_id: null, reviewer_staff_id: 's1',
    })
    await clickButtonByText(wrapper, '复核通过')
    await flushPromises()

    expect(mocks.updateProcedureTrim).not.toHaveBeenCalled()
    const [, , body] = mocks.transitionProcedureRowTask.mock.calls[0]
    expect(body.action).toBe('review')
    expect(body.expected_lock_version).toBe(5)
  })

  it('nullable wp task does not build an editor deep link (shows empty state)', async () => {
    const wrapper = await mountWith({ ...BASE_TASK, wp_id: null, workflow_status: 'assigned' })
    // "打开底稿" 按钮仅在 wp_id 存在时渲染
    const openBtn = wrapper.findAll('button.gt-btn').find((b: any) => b.text() === '打开底稿')
    expect(openBtn).toBeUndefined()
    expect(mocks.routerPush).not.toHaveBeenCalled()
  })

  it('valid wp deep link carries task_id + sheet_key + definition_key', async () => {
    const wrapper = await mountWith({ ...BASE_TASK, wp_id: 'wp-1' })
    await clickButtonByText(wrapper, '打开底稿')
    await flushPromises()
    expect(mocks.routerPush).toHaveBeenCalledTimes(1)
    const arg = mocks.routerPush.mock.calls[0][0]
    expect(arg.query.task_id).toBe('task-1')
    expect(arg.query.sheet_key).toBe('D2A')
    expect(arg.query.definition_key).toBe('D2A::D2A::abc')
  })
})
