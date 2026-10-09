import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'

const { api, message } = vi.hoisted(() => ({
  api: {
    getConsolPushRuns: vi.fn(), getConsolPushStatus: vi.fn(), pushConsolidation: vi.fn(),
  } as Record<string, ReturnType<typeof vi.fn>>,
  message: { success: vi.fn(), info: vi.fn() },
}))
vi.mock('@/services/consolidationApi', () => Object.fromEntries(
  Object.keys(api).map((key) => [key, (...args: any[]) => api[key](...args)]),
))
vi.mock('element-plus', () => ({ ElMessage: message }))

import ConsolPushPanel from '../ConsolPushPanel.vue'
import {
  stepStatusLabel, stepStatusType,
} from '../composables/consolTrialView'
import {
  CONSOL_PUSH_EVENTS, isCurrentConsolPushEvent, isFailedPushStatus,
  isPartialPushStatus, pushEventMessage,
} from '../composables/consolPushEvents'

const RUN = {
  id: 'r1', project_id: 'p1', year: 2025, trigger_source: 'formula_changed',
  trigger_label: '公式变更', triggered_by: 'u1', status: 'partial',
  steps: [
    { project_id: 'p1', project_name: '甲集团', step: 'worksheet', step_label: '重算差额表', status: 'succeeded', detail: '节点 3 个' },
    { project_id: 'p1', project_name: '甲集团', step: 'report', step_label: '生成合并报表', status: 'failed', detail: '公式错误' },
    { project_id: 'p1', project_name: '甲集团', step: 'notes', step_label: '标记合并附注待更新', status: 'skipped', detail: '上一步失败' },
  ],
  warnings: ['利润表一行取不到数'], started_at: '2026-10-01T01:00:00Z', finished_at: '2026-10-01T01:00:05Z',
}
const Table = defineComponent({
  props: ['data'],
  provide() { return { rows: () => (this as any).data || [] } },
  setup(_, { slots, attrs }) { return () => h('div', { 'data-testid': (attrs as any)['data-testid'] }, slots.default?.()) },
})
const Column = defineComponent({
  inject: ['rows'], props: ['label', 'type'],
  setup(props, { slots }) {
    return function (this: any) {
      return h('section', { 'data-label': props.label || props.type }, this.rows().map((row: any) => h('div', slots.default?.({ row }))))
    }
  },
})
const Button = defineComponent({
  emits: ['click'],
  setup(_, { slots, emit, attrs }) {
    return () => h('button', { 'data-testid': (attrs as any)['data-testid'], onClick: () => emit('click') }, slots.default?.())
  },
})
const Pass = defineComponent({
  setup(_, { slots, attrs }) { return () => h('div', { 'data-testid': (attrs as any)['data-testid'] }, [slots.default?.(), slots.title?.()]) },
})
const STUBS = {
  'el-table': Table, 'el-table-column': Column, 'el-button': Button,
  'el-alert': Pass, 'el-tag': Pass,
}

function create(props: Record<string, unknown> = {}) {
  return mount(ConsolPushPanel, {
    props: { projectId: 'p1', year: 2025, ...props },
    global: { stubs: STUBS, directives: { loading: {} } },
  })
}

describe('合并推送纯逻辑', () => {
  it('步骤状态与 raw SSE 事件判定完整', () => {
    expect(stepStatusLabel('succeeded')).toBe('成功')
    expect(stepStatusLabel('failed')).toBe('失败')
    expect(stepStatusLabel('skipped')).toBe('已跳过')
    expect(stepStatusType('skipped')).toBe('info')
    expect(Object.values(CONSOL_PUSH_EVENTS)).toEqual(['consol.pushed', 'consol.push_stale', 'consol.push_failed'])
    expect(isCurrentConsolPushEvent({ project_id: 'p1', year: 2025 }, 'p1', 2025)).toBe(true)
    expect(isCurrentConsolPushEvent({ project_id: 'p2', year: 2025 }, 'p1', 2025)).toBe(false)
    expect(isCurrentConsolPushEvent({ project_id: 'p1', year: 2024 }, 'p1', 2025)).toBe(false)
    expect(isFailedPushStatus('failed')).toBe(true)
    expect(isPartialPushStatus('partial')).toBe(true)
    expect(pushEventMessage({ warnings: ['具体错误'] }, '兜底')).toBe('具体错误')
  })
})

describe('ConsolPushPanel', () => {
  beforeEach(() => {
    Object.values(api).forEach((fn) => fn.mockReset())
    Object.values(message).forEach((fn) => fn.mockReset())
    api.getConsolPushRuns.mockResolvedValue([RUN])
    api.getConsolPushStatus.mockResolvedValue({ last_run: RUN, is_stale: true, stale_rows: 3 })
    api.pushConsolidation.mockResolvedValue({ queued: true, message: '已开始推送，完成后自动刷新', project_id: 'p1', year: 2025 })
  })

  it('加载当前项目最近 10 次，显示过期、运行、步骤和逐次警告', async () => {
    const wrapper = create()
    await flushPromises()
    expect(api.getConsolPushRuns).toHaveBeenCalledWith('p1', 2025, 10)
    expect(api.getConsolPushStatus).toHaveBeenCalledWith('p1', 2025)
    expect(wrapper.find('[data-testid="consol-push-stale"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="consol-push-status"]').text()).toContain('公式变更，部分成功')
    expect(wrapper.find('[data-testid="consol-push-runs"]').text()).toContain('利润表一行取不到数')
    expect((wrapper.vm as any).runs[0].steps.map((step: any) => step.step_label)).toContain('重算差额表')
    expect(wrapper.find('[data-testid="consol-push-steps"]').text()).toContain('已跳过')
  })

  it('立即推送发送 manual；queued=false 是并入排队，不是失败', async () => {
    api.pushConsolidation.mockResolvedValueOnce({ queued: false, message: '已有推送在排队，本次请求已并入', project_id: 'p1', year: 2025 })
    const wrapper = create()
    await flushPromises()
    await wrapper.find('[data-testid="consol-push-now"]').trigger('click')
    await flushPromises()
    expect(api.pushConsolidation).toHaveBeenCalledWith('p1', 2025, 'manual')
    expect(message.info).toHaveBeenCalledWith('已有推送在排队，本次请求已并入')
    expect(wrapper.emitted('queued')).toHaveLength(1)
    expect(api.getConsolPushRuns).toHaveBeenCalledTimes(2)
  })

  it('项目或年度变化自动重载；无推送权限时点击不发请求', async () => {
    const wrapper = create({ canPush: false })
    await flushPromises()
    await wrapper.find('[data-testid="consol-push-now"]').trigger('click')
    expect(api.pushConsolidation).not.toHaveBeenCalled()
    await wrapper.setProps({ projectId: 'p2', year: 2024 })
    await flushPromises()
    expect(api.getConsolPushRuns).toHaveBeenLastCalledWith('p2', 2024, 10)
  })
})
