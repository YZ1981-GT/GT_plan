/**
 * FormulaPropagationStatus —— 公式变更联动状态（spec formula-management-repair-closure R1.4）
 *
 * 守护：失败显示条数与死信、可展开看原因；读取失败如实显示「联动状态未知」；处理中按 3 秒轮询、完成后停；
 * 切项目时上一个项目晚到的响应不覆盖；宿主调用 refresh 重新开始轮询。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { defineComponent } from 'vue'
import ElementPlus from 'element-plus'

const { api } = vi.hoisted(() => ({ api: { propagation: vi.fn() } }))
vi.mock('@/services/formulaSettingsApi', () => ({ formulaSettingsApi: api }))

import FormulaPropagationStatus from '../FormulaPropagationStatus.vue'

const PopoverStub = defineComponent({
  name: 'ElPopover',
  props: { disabled: { type: Boolean, default: false } },
  template: '<div><slot name="reference" /><div v-if="!disabled" class="pop"><slot /></div></div>',
})

function status(over: Record<string, unknown> = {}) {
  return {
    project_id: 'p1', window: 200, state: 'idle', counts: { pending: 0, failed: 0, published: 3 },
    retrying: 0, gave_up: 0, dead_letter: 0, max_attempts: 20, last_published_at: '2026-11-03T08:02:05',
    recent_failures: [], ...over,
  }
}

const FAILURES = [
  { outbox_id: 'o1', domain: 'cross_check', domain_label: '表间审核', source: 'global_publish', slot_count: 2,
    attempt_count: 20, gave_up: true, last_error: '表间审核重跑失败', created_at: '2026-11-03T08:05:00' },
  { outbox_id: 'o2', domain: 'report', domain_label: '报表', source: 'project_edit', slot_count: 1,
    attempt_count: 2, gave_up: false, last_error: '报表重算失败（过期标记已保留，将自动重试）：注入', created_at: null },
]

function mountIt(projectId = 'p1') {
  return mount(FormulaPropagationStatus, {
    props: { projectId },
    global: { plugins: [ElementPlus], stubs: { ElPopover: PopoverStub } },
  })
}

function tagText(w: ReturnType<typeof mountIt>) {
  return w.find('[data-testid="fm-propagation-status"]').text()
}

beforeEach(() => {
  api.propagation.mockReset()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('联动状态标签', () => {
  it('有失败：显示失败条数与需人工处理的死信，展开列出类别 / 次数 / 原因', async () => {
    api.propagation.mockResolvedValue(status({
      state: 'failed', counts: { pending: 0, failed: 2, published: 3 }, retrying: 1, gave_up: 1, dead_letter: 1,
      recent_failures: FAILURES,
    }))
    const w = mountIt()
    await flushPromises()
    expect(tagText(w)).toBe('联动失败 2，1 条需人工处理')
    const detail = w.find('[data-testid="fm-propagation-detail"]')
    expect(detail.exists()).toBe(true)
    expect(detail.text()).toContain('表间审核')
    expect(detail.text()).toContain('20 次·已停止')
    expect(detail.text()).toContain('将自动重试')
    expect(detail.text()).toContain('自动重试中 1、已停止 1')
  })

  it('读取失败：显示「联动状态未知」，不当作正常', async () => {
    api.propagation.mockRejectedValue({ response: { status: 500, data: { detail: '数据库不可用' } } })
    const w = mountIt()
    await flushPromises()
    expect(tagText(w)).toBe('联动状态未知')
    expect(w.find('[data-testid="fm-propagation-detail"]').exists()).toBe(false)
  })

  it('全部完成：显示「联动已完成」，没有可展开的明细', async () => {
    api.propagation.mockResolvedValue(status())
    const w = mountIt()
    await flushPromises()
    expect(tagText(w)).toBe('联动已完成')
    expect(w.find('[data-testid="fm-propagation-detail"]').exists()).toBe(false)
  })
})

describe('轮询与竞态', () => {
  it('处理中每 3 秒重取，完成后停止', async () => {
    vi.useFakeTimers()
    api.propagation
      .mockResolvedValueOnce(status({ state: 'running', counts: { pending: 2, failed: 0, published: 1 } }))
      .mockResolvedValueOnce(status({ state: 'running', counts: { pending: 1, failed: 0, published: 2 } }))
      .mockResolvedValue(status())
    const w = mountIt()
    await flushPromises()
    expect(tagText(w)).toBe('联动处理中 2')
    await vi.advanceTimersByTimeAsync(3000)
    expect(tagText(w)).toBe('联动处理中 1')
    await vi.advanceTimersByTimeAsync(3000)
    expect(tagText(w)).toBe('联动已完成')
    await vi.advanceTimersByTimeAsync(9000)
    expect(api.propagation).toHaveBeenCalledTimes(3)
  })

  it('切项目：上一个项目晚到的响应不覆盖', async () => {
    let releaseOld!: (v: unknown) => void
    api.propagation
      .mockImplementationOnce(() => new Promise((r) => { releaseOld = r }))
      .mockResolvedValueOnce(status({ project_id: 'p2' }))
    const w = mountIt('p1')
    await w.setProps({ projectId: 'p2' })
    await flushPromises()
    releaseOld(status({ state: 'failed', counts: { pending: 0, failed: 9, published: 0 }, recent_failures: FAILURES }))
    await flushPromises()
    expect(tagText(w)).toBe('联动已完成')
    expect(api.propagation.mock.calls.map((c) => c[0])).toEqual(['p1', 'p2'])
  })

  it('宿主保存后调用 refresh：重新取状态', async () => {
    api.propagation.mockResolvedValueOnce(status()).mockResolvedValueOnce(status({
      state: 'running', counts: { pending: 1, failed: 0, published: 3 },
    }))
    const w = mountIt()
    await flushPromises()
    await (w.vm as any).refresh()
    expect(tagText(w)).toBe('联动处理中 1')
    w.unmount() // 处理中会排下一轮轮询：卸载时必须清掉，不能串到别的用例
    expect(api.propagation).toHaveBeenCalledTimes(2)
  })
})
