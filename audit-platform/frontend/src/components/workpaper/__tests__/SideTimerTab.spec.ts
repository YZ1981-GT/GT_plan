/**
 * SideTimerTab.spec.ts — A-5 底稿内计时器 vitest
 *
 * spec proposal-remaining-18 task 1.4
 *
 * 验证：
 * 1. 启动计时 + advanceTimersByTime 5s → 显示 00:00:05
 * 2. 暂停/恢复 → 累计正确
 * 3. 停止 → 调 api.post 验证 payload (hours, wp_code, date, description)
 * 4. localStorage 持久化：mount 时按 status=running + startedAt 恢复，UI 反映恢复状态
 * 5. 切换 wpId 时清除当前状态并恢复新 wpId 的状态
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { nextTick } from 'vue'
import SideTimerTab from '../SideTimerTab.vue'

const mockPost = vi.fn()

vi.mock('@/services/apiProxy', () => ({
  api: {
    get: vi.fn(),
    post: (...args: unknown[]) => mockPost(...args),
  },
}))

vi.mock('element-plus', () => ({
  ElMessage: {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
    info: vi.fn(),
  },
}))

const mockOn = vi.fn()
const mockOff = vi.fn()
vi.mock('@/utils/eventBus', () => ({
  eventBus: {
    on: (...args: unknown[]) => mockOn(...args),
    off: (...args: unknown[]) => mockOff(...args),
    emit: vi.fn(),
  },
}))

const globalStubs = {
  stubs: {
    'el-button': {
      template:
        '<button :disabled="disabled" :data-loading="loading" @click="$emit(\'click\')"><slot /></button>',
      props: ['disabled', 'loading', 'type', 'size', 'text'],
    },
    'el-tag': {
      template: '<span class="stub-tag" :data-type="type"><slot /></span>',
      props: ['type', 'size'],
    },
  },
}

const baseProps = {
  projectId: 'proj-1',
  wpId: 'wp-D2-1',
  wpCode: 'D2-1',
}

describe('SideTimerTab — 启动计时器', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-05-22T08:00:00Z'))
    mockPost.mockReset()
    localStorage.clear()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('启动后 5 秒显示 00:00:05', async () => {
    const wrapper = mount(SideTimerTab, {
      props: baseProps,
      global: globalStubs,
    })

    const startBtn = wrapper.findAll('button').find((b) => b.text().includes('开始'))
    expect(startBtn).toBeDefined()
    await startBtn!.trigger('click')

    // 推进 5 秒（4 次 1s tick 已足够；推进 5000 触发 5 次 tick handler）
    vi.advanceTimersByTime(5000)
    await nextTick()

    expect(wrapper.find('.gt-timer-display').text()).toBe('00:00:05')
  })

  it('启动 1 小时后显示 01:00:00', async () => {
    const wrapper = mount(SideTimerTab, {
      props: baseProps,
      global: globalStubs,
    })
    await wrapper
      .findAll('button')
      .find((b) => b.text().includes('开始'))!
      .trigger('click')
    vi.advanceTimersByTime(3600 * 1000)
    await nextTick()
    expect(wrapper.find('.gt-timer-display').text()).toBe('01:00:00')
  })
})

describe('SideTimerTab — 暂停/恢复 累计正确', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-05-22T08:00:00Z'))
    mockPost.mockReset()
    localStorage.clear()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('启动 10s → 暂停 → 5s 后再启动 → 7s → 总累计 17s', async () => {
    const wrapper = mount(SideTimerTab, {
      props: baseProps,
      global: globalStubs,
    })

    // 第一段：10s
    await wrapper
      .findAll('button')
      .find((b) => b.text().includes('开始'))!
      .trigger('click')
    vi.advanceTimersByTime(10_000)
    await nextTick()

    // 暂停
    await wrapper
      .findAll('button')
      .find((b) => b.text().includes('暂停'))!
      .trigger('click')
    expect(wrapper.find('.gt-timer-display').text()).toBe('00:00:10')

    // 暂停期间 5s 不计
    vi.advanceTimersByTime(5_000)
    await nextTick()
    expect(wrapper.find('.gt-timer-display').text()).toBe('00:00:10')

    // 恢复 → 7s
    await wrapper
      .findAll('button')
      .find((b) => b.text().includes('开始'))!
      .trigger('click')
    vi.advanceTimersByTime(7_000)
    await nextTick()
    expect(wrapper.find('.gt-timer-display').text()).toBe('00:00:17')
  })
})

describe('SideTimerTab — 停止时 POST /api/projects/{pid}/workhours', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-05-22T08:00:00Z'))
    mockPost.mockReset()
    mockPost.mockResolvedValue({ id: 'wh-1' })
    localStorage.clear()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('停止时按 hours = ms/3600000 提交工时（含 wp_code、date、description）', async () => {
    const wrapper = mount(SideTimerTab, {
      props: baseProps,
      global: globalStubs,
    })

    await wrapper
      .findAll('button')
      .find((b) => b.text().includes('开始'))!
      .trigger('click')
    // 36 秒 = 0.01h（最小可提交单位）
    vi.advanceTimersByTime(36_000)
    await nextTick()

    const stopBtn = wrapper.findAll('button').find((b) => b.text().includes('停止'))
    expect(stopBtn).toBeDefined()
    await stopBtn!.trigger('click')
    await flushPromises()

    expect(mockPost).toHaveBeenCalledTimes(1)
    const [url, payload] = mockPost.mock.calls[0]
    expect(url).toBe('/api/projects/proj-1/workhours')
    expect(payload).toMatchObject({
      hours: 0.01,
      wp_code: 'D2-1',
      description: expect.stringContaining('计时器'),
    })
    expect(payload.date).toMatch(/^\d{4}-\d{2}-\d{2}$/)
  })

  it('累计不足 0.01h 时不调 API（只警告）', async () => {
    const wrapper = mount(SideTimerTab, {
      props: baseProps,
      global: globalStubs,
    })

    await wrapper
      .findAll('button')
      .find((b) => b.text().includes('开始'))!
      .trigger('click')
    // 仅 10s ≈ 0.0028h，四舍五入为 0
    vi.advanceTimersByTime(10_000)
    await nextTick()

    await wrapper
      .findAll('button')
      .find((b) => b.text().includes('停止'))!
      .trigger('click')
    await flushPromises()

    expect(mockPost).not.toHaveBeenCalled()
  })

  it('提交成功后清空 localStorage 与显示', async () => {
    const wrapper = mount(SideTimerTab, {
      props: baseProps,
      global: globalStubs,
    })

    await wrapper
      .findAll('button')
      .find((b) => b.text().includes('开始'))!
      .trigger('click')
    vi.advanceTimersByTime(36_000)
    await nextTick()

    expect(localStorage.getItem('gt:wp-timer:proj-1:wp-D2-1')).not.toBeNull()

    await wrapper
      .findAll('button')
      .find((b) => b.text().includes('停止'))!
      .trigger('click')
    await flushPromises()
    await nextTick()

    expect(localStorage.getItem('gt:wp-timer:proj-1:wp-D2-1')).toBeNull()
    expect(wrapper.find('.gt-timer-display').text()).toBe('00:00:00')
  })
})

describe('SideTimerTab — localStorage 持久化', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-05-22T08:00:00Z'))
    mockPost.mockReset()
    localStorage.clear()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('mount 时从 localStorage 恢复 paused 状态与累计时间', async () => {
    localStorage.setItem(
      'gt:wp-timer:proj-1:wp-D2-1',
      JSON.stringify({
        status: 'paused',
        startedAt: null,
        accumulatedMs: 12_000,
      }),
    )

    const wrapper = mount(SideTimerTab, {
      props: baseProps,
      global: globalStubs,
    })
    await nextTick()

    expect(wrapper.find('.gt-timer-display').text()).toBe('00:00:12')
    expect(wrapper.text()).toContain('已暂停')
  })

  it('mount 时从 localStorage 恢复 running 状态（继续计时）', async () => {
    const now = Date.now()
    localStorage.setItem(
      'gt:wp-timer:proj-1:wp-D2-1',
      JSON.stringify({
        status: 'running',
        startedAt: now - 8_000, // 已跑 8 秒
        accumulatedMs: 4_000, // 之前累计 4 秒
      }),
    )

    const wrapper = mount(SideTimerTab, {
      props: baseProps,
      global: globalStubs,
    })
    await nextTick()
    // 4s + 8s = 12s
    expect(wrapper.find('.gt-timer-display').text()).toBe('00:00:12')
    expect(wrapper.text()).toContain('计时中')

    // 继续推进 3s → 总计 15s
    vi.advanceTimersByTime(3_000)
    await nextTick()
    expect(wrapper.find('.gt-timer-display').text()).toBe('00:00:15')
  })

  it('localStorage key 包含 projectId + wpId namespace', async () => {
    const wrapper = mount(SideTimerTab, {
      props: baseProps,
      global: globalStubs,
    })

    await wrapper
      .findAll('button')
      .find((b) => b.text().includes('开始'))!
      .trigger('click')

    expect(localStorage.getItem('gt:wp-timer:proj-1:wp-D2-1')).not.toBeNull()
    // 不会污染其他底稿命名空间
    expect(localStorage.getItem('gt:wp-timer:proj-1:wp-other')).toBeNull()
  })

  it('损坏的 localStorage JSON 不抛错', () => {
    localStorage.setItem('gt:wp-timer:proj-1:wp-D2-1', '{not-json')
    expect(() =>
      mount(SideTimerTab, { props: baseProps, global: globalStubs }),
    ).not.toThrow()
  })
})

describe('SideTimerTab — wpId 切换', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-05-22T08:00:00Z'))
    mockPost.mockReset()
    localStorage.clear()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('切换 wpId 时持久化旧底稿状态并加载新底稿', async () => {
    const wrapper = mount(SideTimerTab, {
      props: baseProps,
      global: globalStubs,
    })

    await wrapper
      .findAll('button')
      .find((b) => b.text().includes('开始'))!
      .trigger('click')
    vi.advanceTimersByTime(8_000)
    await nextTick()
    expect(wrapper.find('.gt-timer-display').text()).toBe('00:00:08')

    // 切到另一个底稿（已有持久化数据）
    localStorage.setItem(
      'gt:wp-timer:proj-1:wp-D2-2',
      JSON.stringify({ status: 'paused', startedAt: null, accumulatedMs: 30_000 }),
    )
    await wrapper.setProps({ ...baseProps, wpId: 'wp-D2-2', wpCode: 'D2-2' })
    await nextTick()
    expect(wrapper.find('.gt-timer-display').text()).toBe('00:00:30')

    // 旧底稿持久化为 paused 状态
    const old = JSON.parse(localStorage.getItem('gt:wp-timer:proj-1:wp-D2-1')!)
    expect(old.status).toBe('paused')
    expect(old.accumulatedMs).toBeGreaterThanOrEqual(8_000)
  })
})

describe('SideTimerTab — 缺少 wpId 时不渲染计时面板', () => {
  beforeEach(() => {
    mockPost.mockReset()
    localStorage.clear()
  })

  it('wpId 为空时显示占位文案', () => {
    const wrapper = mount(SideTimerTab, {
      props: { projectId: 'proj-1', wpId: undefined, wpCode: undefined },
      global: globalStubs,
    })
    expect(wrapper.text()).toContain('请先选择底稿')
    expect(wrapper.find('.gt-timer-display').exists()).toBe(false)
  })
})
